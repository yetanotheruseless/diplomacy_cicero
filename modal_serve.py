"""Scale-to-zero ORACLE SERVING Function for the MODERNIZED Cicero stack.

This serves the single supported stack from ``modal_modern.py``: Python 3.12,
torch 2.13.0 cu130, protobuf 7.35.1/protoc 35.1, pydipcc, and the pure-Python
``nest`` shim. The ``imitation`` and ``searchbot`` tiers are consumed by
``agentic-diplomacy`` over HTTP.

Architecture:
  * Image: ``modal_modern.gpu_image`` (the validated modern build) + the 4 oracle
    sidecar files staged FLAT into ``/opt/oracle`` (so the server's sibling
    imports ``import schema`` / ``from cicero_backend import ...`` resolve).
  * ``@app.cls`` + ``@modal.web_server(port)``: ``@modal.enter`` Popens the oracle
    HTTP server (``/opt/oracle/oracle_server.py --transport http``) bound to
    ``localhost:<port>`` in the same Python 3.12 interpreter. Modal proxies inbound HTTP to
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
  uvx modal deploy modal_serve.py
  ORACLE_TOKEN=<token> uvx modal run modal_serve.py::verify
"""

import os
import pathlib
import subprocess
import time

import modal

# Reuse the validated modern image + the models Volume from modal_modern.py.
from modal_modern import (
    CUDA_VERSION,
    PROTOBUF_VERSION,
    PROTOC_VERSION,
    PYTHON_VERSION,
    TORCH_VERSION,
    VOL,
    gpu_image,
)

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


# Matplotlib is reached only by the oracle's get_orders integration. Pillow is
# already constrained by the canonical dialogue extra.
SERVING_RUNTIME_DEPS = ["matplotlib==3.11.1"]


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


def _oracle_argv() -> list[str]:
    """argv for oracle_server.py serving the configured TIERS over HTTP on PORT.

    - imitation: base_strategy_model agent; `policy` = blueprint distribution sampled from the
      imitation policy net (cicero_backend._blueprint_policy, no search); `value` = RL value net.
    - searchbot: CFR/bqre1p search agent; `policy` = search-refined distribution (run_search);
      `value` = RL value net. Heavier per call; n_rollouts kept small for serving latency.
    Both tiers are no-press, so `value` is a positional read.
    """
    argv = [
        "python",
        "-u",
        "/opt/oracle/oracle_server.py",
        "--transport",
        "http",
        "--host",
        "0.0.0.0",
        "--port",
        str(PORT),
        "--device",
        "cuda",
    ]
    if "imitation" in TIERS:
        argv += [
            "--agent",
            f"imitation={IMITATION_CONFIG}",
            # base_strategy_model.prototxt hardcodes models/blueprint.pt (absent on the
            # Volume); point it at the real human-imitation policy checkpoint.
            "--override",
            f"imitation:base_strategy_model.model_path={IMITATION_MODEL}",
            "--value-model",
            f"imitation={VALUE_MODEL}",
            "--no-press",
            "imitation",
        ]
    if "searchbot" in TIERS:
        argv += [
            "--agent",
            f"searchbot={SEARCHBOT_CONFIG}",
            # searchbot.prototxt defaults model_path to the absent blueprint.pt; point it at
            # the RL search-orders net, and the CFR rollouts' value head at the RL value net.
            "--override",
            f"searchbot:searchbot.model_path={SEARCHBOT_MODEL}",
            "--override",
            f"searchbot:searchbot.value_model_path={VALUE_MODEL}",
            "--override",
            f"searchbot:searchbot.n_rollouts={SEARCHBOT_ROLLOUTS}",
            "--value-model",
            f"searchbot={VALUE_MODEL}",
            "--no-press",
            "searchbot",
        ]
    return argv


app = modal.App("cicero-modern-oracle")

# A stable bearer token across cold starts. Create once with:
#   export ORACLE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
#   modal secret create cicero-oracle-token ORACLE_TOKEN="$ORACLE_TOKEN"
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
@modal.concurrent(
    max_inputs=8
)  # absorb the concurrent cicero-seat requests on the ONE capped GPU — do NOT scale out
class CiceroModernOracle:
    """Scale-to-zero modern-Cicero oracle for the configured tiers over HTTP."""

    @modal.enter()
    def _start(self) -> None:
        token = os.environ.get("ORACLE_TOKEN")
        if not token:
            raise RuntimeError(
                "ORACLE_TOKEN is required; provide it through the cicero-oracle-token Modal Secret"
            )
        env = dict(os.environ)
        env.setdefault("PYTHONPATH", "/app")
        env["ORACLE_TOKEN"] = token
        env.setdefault("OMP_NUM_THREADS", "8")
        argv = _oracle_argv()
        print(
            "[enter] launching modern oracle "
            f"(Python {PYTHON_VERSION}, torch {TORCH_VERSION} cu130/CUDA {CUDA_VERSION}, "
            f"protobuf {PROTOBUF_VERSION}/protoc {PROTOC_VERSION}): {' '.join(argv)}",
            flush=True,
        )
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
        return

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
    "id": "verify",
    "is_full_press": False,
    "map": "standard",
    "phases": [
        {
            "messages": {},
            "name": "S1901M",
            "orders": {},
            "state": {
                "centers": {
                    "AUSTRIA": ["BUD", "TRI", "VIE"],
                    "ENGLAND": ["EDI", "LON", "LVP"],
                    "FRANCE": ["BRE", "MAR", "PAR"],
                    "GERMANY": ["BER", "KIE", "MUN"],
                    "ITALY": ["NAP", "ROM", "VEN"],
                    "RUSSIA": ["MOS", "SEV", "STP", "WAR"],
                    "TURKEY": ["ANK", "CON", "SMY"],
                },
                "name": "S1901M",
                "units": {
                    "AUSTRIA": ["A BUD", "A VIE", "F TRI"],
                    "ENGLAND": ["A LVP", "F EDI", "F LON"],
                    "FRANCE": ["A MAR", "A PAR", "F BRE"],
                    "GERMANY": ["A BER", "A MUN", "F KIE"],
                    "ITALY": ["A ROM", "A VEN", "F NAP"],
                    "RUSSIA": ["A MOS", "A WAR", "F SEV", "F STP/SC"],
                    "TURKEY": ["A CON", "A SMY", "F ANK"],
                },
            },
        }
    ],
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
    print(
        f"  stack            = Python {PYTHON_VERSION}, torch {TORCH_VERSION}+cu130, "
        f"protobuf {PROTOBUF_VERSION}, protoc {PROTOC_VERSION}"
    )
    print(f"  port             = {PORT}")
    print(f"  scaledown_window = {SCALEDOWN_WINDOW}s")
    print(f"  startup_timeout  = {STARTUP_TIMEOUT}s")
    try:
        print(f"  URL              = {_web_url()}")
    except Exception as exc:  # noqa: BLE001
        print(f"  URL              = (deploy first; {type(exc).__name__}: {exc})")
    print()
    print(
        "Deploy:  uvx modal deploy modal_serve.py   (requires the cicero-oracle-token Secret)"
    )
    print("Verify:  ORACLE_TOKEN=<tok> uvx modal run modal_serve.py::verify")
    print("Runner:  point --modal-url at the URL, token via ORACLE_TOKEN.")


@app.local_entrypoint()
def verify(url: str = "", token: str = "") -> None:
    """Verify cold start, authentication, real orders, and scale-to-zero.

    Pass --url/--token to hit an already-deployed Function; otherwise resolves the
    URL from the class and uses ORACLE_TOKEN from the env.
    """
    import json
    import urllib.error
    import urllib.request

    url = (url or _web_url()).rstrip("/")
    token = token or os.environ.get("ORACLE_TOKEN", "")
    if not token:
        raise ValueError("ORACLE_TOKEN or --token is required for verification")
    print(f"[verify] url={url} token={'set' if token else 'MISSING'}")

    def _get(path: str, timeout: float) -> tuple[int, dict]:
        with urllib.request.urlopen(url + path, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())

    def _rpc(
        method: str,
        params: dict,
        timeout: float,
        *,
        bearer: str = token,
    ) -> dict:
        body = json.dumps({"id": 1, "method": method, "params": params}).encode()
        req = urllib.request.Request(
            url + "/rpc",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {bearer}"},
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
            if code == 200 and payload.get("status") == "ok" and payload.get("ready") is True:
                break
            last = RuntimeError(f"health endpoint returned a non-ready payload: {payload}")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(5)
    else:
        raise RuntimeError(f"/health never became ready: {last}")

    # 2) authentication must fail closed before exercising valid RPC calls.
    try:
        _rpc("info", {}, timeout=120, bearer="cicero-verifier-invalid-token")
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise RuntimeError(f"invalid bearer token returned HTTP {exc.code}, expected 401") from exc
        print("[verify] invalid bearer token -> 401")
    else:
        raise RuntimeError("invalid bearer token was accepted")

    # 3) info
    info_resp = _rpc("info", {}, timeout=120)
    if not info_resp.get("ok"):
        raise RuntimeError(f"info RPC failed: {info_resp.get('error')}")
    configured_tiers = set(TIERS)
    reported_tiers = set(info_resp.get("result", {}).get("tiers", []))
    if not configured_tiers.issubset(reported_tiers):
        raise RuntimeError(
            f"info RPC omitted configured tiers: expected {sorted(configured_tiers)}, "
            f"got {sorted(reported_tiers)}"
        )
    print(f"[verify] info -> {json.dumps(info_resp)[:300]}")

    # 4) real get_orders for FRANCE on the opening board, once per configured tier
    game_json = json.dumps(_OPENING_GAME)
    for tier in TIERS:
        res = _rpc(
            "get_orders",
            {"game_json": game_json, "power": "FRANCE", "tier": tier},
            timeout=600,
        )
        if not res.get("ok"):
            raise RuntimeError(f"get_orders({tier}) failed: {res.get('error')}")
        orders = res["result"]["orders"]
        print(f"[verify] get_orders({tier}, FRANCE) -> {orders}")
        if not orders or not all(isinstance(order, str) for order in orders):
            raise RuntimeError(f"get_orders({tier}) returned invalid orders: {orders!r}")
    print(f"[verify] PASS: modern Cicero served valid orders for {', '.join(TIERS)}")

    # 5) scale-to-zero: wait past the window, then assert active app task counts.
    print(f"[verify] waiting {SCALEDOWN_WINDOW + 60}s for scale-to-zero ...")
    time.sleep(SCALEDOWN_WINDOW + 60)
    import subprocess as sp

    out = sp.run(
        ["modal", "app", "list", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"`modal app list` failed: {out.stderr.strip()}")
    rows = json.loads(out.stdout)
    active_rows = [
        row
        for row in rows
        if row.get("Description") == "cicero-modern-oracle" and row.get("State") != "stopped"
    ]
    if not active_rows:
        raise RuntimeError("no active cicero-modern-oracle app found after verification")
    busy_rows = [row for row in active_rows if int(row.get("Tasks", -1)) != 0]
    if busy_rows:
        app_tasks = {row.get("App ID"): row.get("Tasks") for row in busy_rows}
        raise RuntimeError(f"oracle did not scale to zero: {app_tasks}")
    app_ids = ", ".join(str(row.get("App ID")) for row in active_rows)
    print(f"[verify] scale-to-zero PASS: {app_ids} tasks=0")
