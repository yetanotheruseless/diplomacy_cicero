"""Scale-to-zero ORACLE SERVING Function for the MODERNIZED Cicero stack.

This is the capstone of the modernization spike: it serves the modern Cicero
(Python 3.11 / torch 2.6 cu124 / modern protobuf / pydipcc / pure-Python nest
shim — built and validated in ``modal_modern.py``) as live ``imitation`` and
``searchbot`` oracle tiers that ``agentic-diplomacy`` consumes over HTTP.

Why this is *simpler* than the legacy dual-python serving (``modal_function.py``
in the sibling worktree): that one had to overlay a Python-3.11 standalone next
to the load-bearing Python-3.9 Cicero and run the oracle in a 3.9 subprocess,
because the legacy stack is 3.9-only. The MODERN stack is already pure 3.11, so
Modal's function runtime and the oracle server share one interpreter — no
overlay, no cross-interpreter subprocess, no PATH juggling.

Architecture:
  * Image: ``modal_modern.gpu_image`` (the validated modern build) + the 4 oracle
    sidecar files staged FLAT into ``/opt/oracle`` (so the server's sibling
    imports ``import schema`` / ``from cicero_backend import ...`` resolve).
  * ``@app.cls`` + ``@modal.web_server(port)``: ``@modal.enter`` Popens the oracle
    HTTP server (``/opt/oracle/oracle_server.py --transport http``) bound to
    ``localhost:<port>`` IN THIS 3.11 INTERPRETER. Modal proxies inbound HTTP to
    that port. Scale-to-zero via ``scaledown_window``.

Wire contract (``agentic-diplomacy/oracle/transport.py::HttpTransport``):
  GET  /health  -> 200 {"status":"ok","ready":true}
  POST /rpc     -> {"id","method","params"} (+ ``Authorization: Bearer <token>``)
                   answered {"id","ok":true,"result":{...}}
  Bearer token read from the required ``ORACLE_TOKEN`` env (provided by a Modal
  Secret). Token values are never logged.

Both tiers are no-press. ``imitation`` serves the ``base_strategy_model`` agent
backed by ``no_press_human_imitation_policy.ckpt``; ``searchbot`` runs Cicero's
CFR search over ``rl_search_orders.ckpt`` and ``rl_value_function.ckpt``. The
models come from the ``cicero-models`` Volume.

Deploy + verify:
  modal deploy modal_serve.py
  modal run modal_serve.py::verify        # health + /rpc get_orders + scale-to-zero
"""
import os
import pathlib
import subprocess
import time

import modal

# Reuse the validated modern image + the models Volume from modal_modern.py.
from modal_modern import gpu_image, models_volume, VOL  # noqa: E402

REPO = pathlib.Path(__file__).parent

# The oracle HTTP server lives in the sibling agentic-diplomacy repo.
ORACLE_SRC = pathlib.Path(
    os.environ.get("AGENTIC_ORACLE_DIR", str(REPO.parent / "agentic-diplomacy" / "oracle"))
)
# (repo-relative src, flat dest name) — staged flat so sibling imports resolve.
ORACLE_FILES = [
    ("schema.py", "schema.py"),
    ("server/service.py", "service.py"),
    ("server/cicero_backend.py", "cicero_backend.py"),
    ("server/oracle_server.py", "oracle_server.py"),
]

# The imitation tier: the no-press base_strategy_model agent, with model_path
# overridden to the real human-imitation policy checkpoint on the Volume.
IMITATION_CONFIG = "conf/common/agents/base_strategy_model.prototxt"
IMITATION_MODEL = "models/no_press_human_imitation_policy.ckpt"
# The RL value net — served as `value` (per-power positional vector) on both tiers.
VALUE_MODEL = "models/rl_value_function.ckpt"
# The searchbot tier: CFR/bqre1p search (Cicero's tactical core) -> search-refined `policy`
# + `value`. Its `policy` comes from run_search (cicero_backend's existing path), giving
# search-refined candidates rather than the imitation blueprint.
SEARCHBOT_CONFIG = "conf/common/agents/searchbot.prototxt"
SEARCHBOT_MODEL = "models/rl_search_orders.ckpt"
SEARCHBOT_ROLLOUTS = int(
    os.environ.get("ORACLE_SEARCHBOT_ROLLOUTS", "8")
)  # small for serving latency
# Which tiers this Function loads (co-resident, no-press). Default: both.
TIERS = [
    tier.strip()
    for tier in os.environ.get("ORACLE_TIERS", "imitation,searchbot").split(",")
    if tier.strip()
]
SUPPORTED_TIERS = {"imitation", "searchbot"}
unsupported_tiers = set(TIERS) - SUPPORTED_TIERS
if not TIERS:
    raise ValueError("ORACLE_TIERS must select at least one tier")
if unsupported_tiers:
    raise ValueError(f"unsupported ORACLE_TIERS: {sorted(unsupported_tiers)}")

PORT = int(os.environ.get("ORACLE_PORT", "8000"))
GPU = os.environ.get("ORACLE_GPU", "A10G")
# Short window for the deploy/test; the runner can redeploy with a longer one.
SCALEDOWN_WINDOW = int(os.environ.get("ORACLE_SCALEDOWN_WINDOW", "120"))
# Model load + first encode is a couple minutes; the web_server/startup budgets
# must cover the time until the oracle binds its socket.
STARTUP_TIMEOUT = int(os.environ.get("ORACLE_STARTUP_TIMEOUT", "900"))
MIN_CONTAINERS = int(os.environ.get("ORACLE_MIN_CONTAINERS", "0"))


# Runtime deps the get_orders path pulls in transitively but that the B1/B2
# *import* checks never exercised (so they weren't in modal_modern's PIP_DEPS).
# Added as a post-build layer here to avoid invalidating the pydipcc build cache.
SERVING_RUNTIME_DEPS = ["Pillow", "matplotlib"]


def _serving_image() -> modal.Image:
    img = gpu_image.pip_install(*SERVING_RUNTIME_DEPS)
    # modal_serve imports modal_modern at module top-level; Modal re-imports the
    # class's module inside the container, so modal_modern must be importable
    # there too. Bake it onto the default sys.path (/root). It only builds lazy
    # Image objects at import (no eager FS access), so this is safe in-container.
    img = img.add_local_file(str(REPO / "modal_modern.py"), "/root/modal_modern.py", copy=True)
    for src_rel, dst_name in ORACLE_FILES:
        src = ORACLE_SRC / src_rel
        # The .exists() check only makes sense locally; inside a Modal container
        # the local oracle checkout isn't present (the files are already baked into
        # the image), so skip the check there.
        if modal.is_local() and not src.exists():
            raise FileNotFoundError(
                f"oracle source {src} not found; set AGENTIC_ORACLE_DIR to the "
                "agentic-diplomacy/oracle directory"
            )
        img = img.add_local_file(str(src), f"/opt/oracle/{dst_name}", copy=True)
    return img


def _oracle_argv(token: str) -> list:
    """argv for oracle_server.py serving the configured TIERS over HTTP on PORT.

    - imitation: base_strategy_model agent; `policy` = blueprint distribution sampled from the
      imitation policy net (cicero_backend._blueprint_policy, no search); `value` = RL value net.
    - searchbot: CFR/bqre1p search agent; `policy` = search-refined distribution (run_search);
      `value` = RL value net. Heavier per call; n_rollouts kept small for serving latency.
    Both tiers are no-press, so `value` is a positional read.
    """
    argv = [
        "python", "-u", "/opt/oracle/oracle_server.py",
        "--transport", "http", "--host", "0.0.0.0", "--port", str(PORT),
        "--device", "cuda",
    ]
    if "imitation" in TIERS:
        argv += [
            "--agent", f"imitation={IMITATION_CONFIG}",
            # base_strategy_model.prototxt hardcodes models/blueprint.pt (absent on the
            # Volume); point it at the real human-imitation policy checkpoint.
            "--override", f"imitation:base_strategy_model.model_path={IMITATION_MODEL}",
            "--value-model", f"imitation={VALUE_MODEL}",
            "--no-press", "imitation",
        ]
    if "searchbot" in TIERS:
        argv += [
            "--agent", f"searchbot={SEARCHBOT_CONFIG}",
            # searchbot.prototxt defaults model_path to the absent blueprint.pt; point it at
            # the RL search-orders net, and the CFR rollouts' value head at the RL value net.
            "--override", f"searchbot:searchbot.model_path={SEARCHBOT_MODEL}",
            "--override", f"searchbot:searchbot.value_model_path={VALUE_MODEL}",
            "--override", f"searchbot:searchbot.n_rollouts={SEARCHBOT_ROLLOUTS}",
            "--value-model", f"searchbot={VALUE_MODEL}",
            "--no-press", "searchbot",
        ]
    return argv


app = modal.App("cicero-modern-oracle")

# A stable bearer token across cold starts. Create once with:
#   modal secret create cicero-oracle-token ORACLE_TOKEN=<value>
# The server refuses to start without ORACLE_TOKEN; it never mints or logs one.
try:
    _TOKEN_SECRETS = [modal.Secret.from_name("cicero-oracle-token")]
except Exception:  # noqa: BLE001 - env injection remains available for local runs
    _TOKEN_SECRETS = []


@app.cls(
    image=_serving_image(),
    gpu=GPU,
    volumes=VOL,
    secrets=_TOKEN_SECRETS,
    scaledown_window=SCALEDOWN_WINDOW,
    min_containers=MIN_CONTAINERS,
    max_containers=1,  # HARD cap: never scale past ONE GPU (a single game's seats serialize fine)
    startup_timeout=STARTUP_TIMEOUT,
    timeout=24 * 3600,
)
@modal.concurrent(max_inputs=8)  # absorb the concurrent cicero-seat requests on the ONE capped GPU — do NOT scale out
class CiceroModernOracle:
    """Scale-to-zero modern-Cicero oracle for the configured tiers over HTTP."""

    @modal.enter()
    def _start(self) -> None:
        token = os.environ.get("ORACLE_TOKEN")
        if not token:
            raise RuntimeError(
                "ORACLE_TOKEN is required; provide it through the cicero-oracle-token "
                "Modal Secret"
            )
        env = dict(os.environ)
        env.setdefault("PYTHONPATH", "/app")
        env["ORACLE_TOKEN"] = token
        env.setdefault("OMP_NUM_THREADS", "8")
        argv = _oracle_argv(token)
        print(f"[enter] launching modern oracle (3.11): {' '.join(argv)}", flush=True)
        # Non-blocking; the oracle binds its socket after building the agent (the
        # base_strategy_model loads in the @modal.enter window). Modal's readiness
        # check is a TCP connect to PORT, governed by web_server.startup_timeout.
        # Stream the oracle's stdout/stderr into the container logs (no capture).
        self._proc = subprocess.Popen(argv, cwd="/app", env=env)
        self._token = token

    @modal.web_server(PORT, startup_timeout=STARTUP_TIMEOUT, label="cicero-modern-oracle")
    def web(self) -> None:
        """Expose the oracle's port. The subprocess (from _start) listens on it;
        Modal proxies. Empty body — web_server only needs the port open in time."""
        return None

    @modal.exit()
    def _stop(self) -> None:
        proc = getattr(self, "_proc", None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


# Standard S1901M opening (Cicero JSON), used by the /rpc verify.
_OPENING_GAME = {
    "id": "verify", "is_full_press": False, "map": "standard",
    "phases": [{"messages": {}, "name": "S1901M", "orders": {}, "state": {
        "centers": {"AUSTRIA": ["BUD", "TRI", "VIE"], "ENGLAND": ["EDI", "LON", "LVP"],
                    "FRANCE": ["BRE", "MAR", "PAR"], "GERMANY": ["BER", "KIE", "MUN"],
                    "ITALY": ["NAP", "ROM", "VEN"], "RUSSIA": ["MOS", "SEV", "STP", "WAR"],
                    "TURKEY": ["ANK", "CON", "SMY"]},
        "name": "S1901M",
        "units": {"AUSTRIA": ["A BUD", "A VIE", "F TRI"], "ENGLAND": ["A LVP", "F EDI", "F LON"],
                  "FRANCE": ["A MAR", "A PAR", "F BRE"], "GERMANY": ["A BER", "A MUN", "F KIE"],
                  "ITALY": ["A ROM", "A VEN", "F NAP"], "RUSSIA": ["A MOS", "A WAR", "F SEV", "F STP/SC"],
                  "TURKEY": ["A CON", "A SMY", "F ANK"]}}}],
}


def _web_url() -> str:
    """Resolve the deployed web_server URL from the class method."""
    return CiceroModernOracle().web.get_web_url()


@app.local_entrypoint()
def info() -> None:
    """Print the deployed URL + how to wire the runner (no GPU spent)."""
    print("Modern Cicero oracle Function:")
    print(f"  tiers            = {', '.join(TIERS)}")
    if "imitation" in TIERS:
        print(f"  imitation        = {IMITATION_CONFIG} + {IMITATION_MODEL} + {VALUE_MODEL}")
    if "searchbot" in TIERS:
        print(
            f"  searchbot        = {SEARCHBOT_CONFIG} + {SEARCHBOT_MODEL} + {VALUE_MODEL} "
            f"({SEARCHBOT_ROLLOUTS} rollouts)"
        )
    print(f"  gpu              = {GPU}")
    print(f"  port             = {PORT}")
    print(f"  scaledown_window = {SCALEDOWN_WINDOW}s")
    print(f"  startup_timeout  = {STARTUP_TIMEOUT}s")
    try:
        print(f"  URL              = {_web_url()}")
    except Exception as exc:  # noqa: BLE001
        print(f"  URL              = (deploy first; {type(exc).__name__}: {exc})")
    print()
    print("Deploy:  ORACLE_TOKEN=<tok> modal deploy modal_serve.py   (set token as a Secret for stability)")
    print("Verify:  modal run modal_serve.py::verify")
    print("Runner:  point --modal-url at the URL, token via ORACLE_TOKEN.")


@app.local_entrypoint()
def verify(url: str = "", token: str = "") -> None:
    """Cold-start health + a real /rpc get_orders + scale-to-zero confirmation.

    Pass --url/--token to hit an already-deployed Function; otherwise resolves the
    URL from the class and uses ORACLE_TOKEN from the env.
    """
    import json
    import urllib.request

    url = (url or _web_url()).rstrip("/")
    token = token or os.environ.get("ORACLE_TOKEN", "")
    print(f"[verify] url={url} token={'set' if token else 'MISSING'}")

    def _get(path, timeout):
        with urllib.request.urlopen(url + path, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())

    def _rpc(method, params, timeout):
        body = json.dumps({"id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(
            url + "/rpc", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())

    # 1) cold-start health (allow time for the container to boot + bind the port)
    deadline = time.time() + STARTUP_TIMEOUT
    last = None
    while time.time() < deadline:
        try:
            code, payload = _get("/health", timeout=30)
            print(f"[verify] /health -> {code} {payload}")
            if code == 200:
                break
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(5)
    else:
        raise SystemExit(f"/health never became ready: {last}")

    # 2) info
    info_resp = _rpc("info", {}, timeout=120)
    print(f"[verify] info -> {json.dumps(info_resp)[:300]}")

    # 3) real get_orders for FRANCE on the opening board, once per configured tier
    game_json = json.dumps(_OPENING_GAME)
    for tier in TIERS:
        res = _rpc(
            "get_orders",
            {"game_json": game_json, "power": "FRANCE", "tier": tier},
            timeout=600,
        )
        if not res.get("ok"):
            raise SystemExit(f"get_orders({tier}) failed: {res.get('error')}")
        orders = res["result"]["orders"]
        print(f"[verify] get_orders({tier}, FRANCE) -> {orders}")
        assert orders and all(isinstance(o, str) for o in orders), f"bad orders: {orders}"
    print(f"[verify] PASS: modern Cicero served valid orders for {', '.join(TIERS)}")

    # 4) scale-to-zero: wait past the window, then check task count via `modal app list`
    print(f"[verify] waiting {SCALEDOWN_WINDOW + 60}s for scale-to-zero ...")
    time.sleep(SCALEDOWN_WINDOW + 60)
    import subprocess as sp
    out = sp.run(["modal", "app", "list"], capture_output=True, text=True)
    print("[verify] `modal app list` (look for cicero-modern-oracle tasks=0):")
    for line in out.stdout.splitlines():
        if "cicero-modern-oracle" in line or "App ID" in line or "Tasks" in line:
            print("   " + line)
    print("[verify] done — confirm the app shows 0 running tasks above.")
