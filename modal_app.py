"""Run Meta/FAIR Cicero on the canonical modern Modal GPU image.

All entrypoints reuse ``modal_modern.gpu_image``: Python 3.12, torch 2.13.0
cu130, protobuf 7.35.1, protoc 35.1, and a pydipcc extension built against the
matching torch ABI. This module owns runners and model download helpers only;
the image definition and compatibility validation live in ``modal_modern.py``.

Usage:
  modal run modal_app.py::smoke                 # verify imports + pydipcc + GPU
  modal run modal_app.py::main                  # full Cicero, Turkey, 1 turn
  modal run modal_app.py::main --mode policy --power AUSTRIA --max-turns 1
  modal run modal_app.py::serve --tiers searchbot,diplodocus_high   # tactics oracle
"""

import os
import pathlib
import secrets

import modal

from modal_modern import (
    CUDA_VERSION,
    PROTOBUF_VERSION,
    PROTOC_VERSION,
    PYTHON_VERSION,
    TORCH_VERSION,
    VOL,
    gpu_image,
    models_volume,
)

REPO = pathlib.Path(__file__).parent

# The agentic-diplomacy oracle bridge lives in a sibling repo. `serve` stages its
# four sidecar files (flat) into the serving image and runs the HTTP front. Point
# AGENTIC_ORACLE_DIR at a different checkout if it isn't the default sibling path.
ORACLE_SRC = pathlib.Path(
    os.environ.get("AGENTIC_ORACLE_DIR", str(REPO.parent / "agentic-diplomacy" / "oracle"))
)

# Runners need the dialogue/game closure in addition to the validated base GPU
# image. Bake it once; never mutate the environment with runtime pip installs.
RUNNER_RUNTIME_DEPS = ["six", "regex", "sh", "nltk", "websocket-client"]
image = gpu_image.pip_install(*RUNNER_RUNTIME_DEPS)
app = modal.App("cicero-modern-runner")

# Lightweight image just for fetching+decrypting weights straight into the
# Volume from Modal's datacenter (far faster than uploading 36GB from a laptop).
download_image = modal.Image.debian_slim(python_version=PYTHON_VERSION).apt_install(
    "gnupg", "wget", "ca-certificates"
)
MODELS_BASE_URL = "https://dl.fbaipublicfiles.com/diplomacy_cicero/models"


@app.function(
    image=download_image,
    volumes=VOL,
    timeout=3600,
    cpu=8.0,
    secrets=[modal.Secret.from_name("cicero-gpg")],
)
def fetch_models(relpaths):
    """Download <relpath>.gpg from fbaipublicfiles and decrypt into the Volume.

    fbaipublicfiles (CloudFront) throttles a single connection to ~10 MB/s, so
    we fetch + decrypt files concurrently to use the datacenter's bandwidth.
    """
    import os
    import subprocess
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pw = os.environ["GPG_PASSWORD"]

    def fetch_one(rel):
        out = f"/app/models/{rel}"
        if os.path.exists(out) and os.path.getsize(out) > 0:
            return rel, "skip", os.path.getsize(out) // (1024 * 1024)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        gpg = out + ".gpg"
        subprocess.run(["wget", "-q", f"{MODELS_BASE_URL}/{rel}.gpg", "-O", gpg], check=True)
        subprocess.run(
            ["gpg", "--batch", "--yes", "--passphrase", pw, "--output", out, "-d", gpg],
            check=True,
            stderr=subprocess.DEVNULL,
        )
        os.remove(gpg)
        return rel, "ok", os.path.getsize(out) // (1024 * 1024)

    total = len(relpaths)
    done = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(fetch_one, r): r for r in relpaths}
        for f in as_completed(futs):
            rel, status, mb = f.result()
            done += 1
            print(f"[{done}/{total}] {status} {rel} ({mb} MB)", flush=True)
    models_volume.commit()
    return done


@app.local_entrypoint()
def download(relpaths_file: str = "/tmp/cicero_subset_relpaths.txt") -> None:
    relpaths = [
        line for line in pathlib.Path(relpaths_file).read_text().splitlines() if line.strip()
    ]
    print(f"fetching {len(relpaths)} model files into volume cicero-models ...")
    n = fetch_models.remote(relpaths)
    print(f"done: {n} files present on volume")


def _run_args(mode: str, power: str, max_turns) -> str:
    """run.py CLI args for a given agent mode (space-joined)."""
    common = f"--adhoc --cfg conf/c01_ag_cmp/cmp.prototxt max_turns={max_turns} power_one={power}"
    if mode == "policy":
        extra = "Iagent_one=agents/base_strategy_model Iagent_six=agents/base_strategy_model"
    elif mode == "search":
        extra = "agent_one.searchbot.n_rollouts=10 agent_one.searchbot.rollouts_cfg.n_threads=8"
    elif mode == "cicero":
        # half_precision left at the config default (True) — works on GPU.
        # Documented matchup: full Cicero vs six imitation_only (press-capable,
        # required since the env forbids mixing press + no-press agents). Needs
        # the produce_action fix in ParlAIAllOrderIndependentRolloutWrapper.
        six = os.environ.get("SIX", "agents/ablations/cicero_imitation_only.prototxt")
        # max_msg_iters caps the simulated 24h negotiation so the phase actually
        # terminates (else it generates hundreds of messages).
        extra = (
            "Iagent_one=agents/cicero.prototxt "
            f"Iagent_six={six} "
            f"max_msg_iters={os.environ.get('MSG_ITERS', '30')}"
        )
    else:
        raise ValueError(f"unknown mode {mode}")
    return f"{common} {extra}"


def _stream(proc):
    """Print a Modal ContainerProcess's stdout+stderr live; return exit code.

    run.py logs to stderr, so we drain both streams concurrently (threads) to
    get live progress instead of all-at-once when the process exits.
    """
    import threading

    def pump(stream):
        for line in stream:
            print(line, end="", flush=True)

    threads = [
        threading.Thread(target=pump, args=(s,), daemon=True) for s in (proc.stdout, proc.stderr)
    ]
    for t in threads:
        t.start()
    code = proc.wait()
    for t in threads:
        t.join(timeout=5)
    return code


# Sandboxes preserve the streaming and crash-snapshot behavior needed by the
# game runners while reusing the same validated modern image as Modal Functions.
@app.local_entrypoint()
def smoke() -> None:
    """Strictly verify the modern stack, CUDA kernel execution, and imports."""
    check = f"""
import os
import subprocess
import sys

import google.protobuf
import torch

def require(condition, message):
    if not condition:
        raise RuntimeError(str(message))

require(sys.version_info[:2] == (3, 12), sys.version)
require(torch.__version__ == "{TORCH_VERSION}+cu130", torch.__version__)
require(torch.version.cuda == "{CUDA_VERSION}", torch.version.cuda)
require(google.protobuf.__version__ == "{PROTOBUF_VERSION}", google.protobuf.__version__)
require(
    subprocess.check_output(["protoc", "--version"], text=True).strip() == "libprotoc {PROTOC_VERSION}",
    "wrong protoc version",
)
require(torch.cuda.is_available(), "Modal GPU is not visible")
probe = torch.randn((256, 256), device="cuda", dtype=torch.float16)
require(torch.isfinite(probe @ probe).all().item(), "CUDA matmul produced non-finite values")
torch.cuda.synchronize()
import fairdiplomacy
from fairdiplomacy.pydipcc import Game
import heyhi.conf
from fairdiplomacy.agents import build_agent_from_cfg
require(Game().current_short_phase == "S1901M", "pydipcc returned the wrong opening phase")
print("stack OK", sys.version, torch.__version__, torch.version.cuda, google.protobuf.__version__)
print("gpu", torch.cuda.get_device_name(0))
print("models entries", len(os.listdir("/app/models")))
"""
    sb = modal.Sandbox.create(app=app, image=image, gpu="A10G", timeout=900, volumes=VOL)
    try:
        print("sandbox:", sb.object_id)
        code = _stream(sb.exec("python", "-c", check))
        if code != 0:
            raise RuntimeError(f"modern GPU smoke failed with exit code {code}")
    finally:
        sb.terminate()


@app.local_entrypoint()
def game(
    power: str = "TURKEY", max_year: str = "1907", max_msg_iters: str = "30", max_turns: str = "20"
) -> None:
    """Play a multi-year full-press game (Cicero vs six imitation_only),
    polling the sandbox for the crash-safe output.json.partial every 60s so the
    latest game state is always saved locally even if the run wedges/dies."""
    import json
    import threading
    import time

    runargs = (
        "--adhoc --cfg conf/c01_ag_cmp/cmp.prototxt "
        "Iagent_one=agents/cicero.prototxt "
        "Iagent_six=agents/ablations/cicero_imitation_only.prototxt "
        f"power_one={power} max_year={max_year} max_turns={max_turns} "
        f"max_msg_iters={max_msg_iters}"
    )
    cmd = f"cd /app && OMP_NUM_THREADS=8 python run.py {runargs}"
    partial_local = pathlib.Path(f"modal_cicero_game_{power}.partial.json")
    final_local = pathlib.Path(f"modal_cicero_game_{power}.json")
    pull_partial = (
        "f=$(find /app/diplomacy_experiments -name output.json.partial "
        '2>/dev/null | head -1); [ -n "$f" ] && cat "$f"'
    )
    pull_final = (
        "f=$(ls -t $(find /app/diplomacy_experiments -name output.json) "
        '2>/dev/null | head -1); [ -n "$f" ] && cat "$f"'
    )

    sb = modal.Sandbox.create(
        app=app, image=image, gpu="A100-80GB", timeout=14400, volumes=VOL, cpu=8.0, memory=49152
    )
    final = ""
    code = None
    try:
        print(
            f"sandbox {sb.object_id}: game power={power} -> {max_year}, "
            f"max_msg_iters={max_msg_iters}"
        )
        proc = sb.exec("bash", "-lc", cmd)
        runner = threading.Thread(target=_stream, args=(proc,), daemon=True)
        runner.start()
        while runner.is_alive():
            time.sleep(60)
            try:
                snap = sb.exec("bash", "-lc", pull_partial).stdout.read()
            except Exception as e:
                print("[snapshot] poll failed:", e)
                continue
            if snap.strip():
                partial_local.write_text(snap)
                try:
                    phases = [p["name"] for p in json.loads(snap)["phases"]]
                    print(f"[snapshot] {len(snap)}B -> {partial_local.name}; phases: {phases}")
                except Exception:
                    print(f"[snapshot] {len(snap)}B -> {partial_local.name}")
        runner.join(timeout=10)
        code = proc.poll()
        final = sb.exec("bash", "-lc", pull_final).stdout.read()
    finally:
        sb.terminate()
    if code != 0:
        raise RuntimeError(f"full-press game failed with exit code {code}")
    if final.strip():
        final_local.write_text(final)
        print(f"wrote {final_local} ({len(final)} bytes)")
    elif partial_local.exists():
        raise RuntimeError(f"game produced no final output; latest partial is {partial_local}")
    else:
        raise RuntimeError("game completed without final or partial output")


@app.local_entrypoint()
def main(mode: str = "cicero", power: str = "", max_turns: str = "1") -> None:
    if not power:
        power = "TURKEY" if mode == "cicero" else "AUSTRIA"
    runargs = _run_args(mode, power, max_turns)
    cmd = (
        "cd /app && PYTORCH_ALLOC_CONF=max_split_size_mb:128 "
        f"OMP_NUM_THREADS=8 python run.py {runargs}"
    )
    # Full Cicero (agent_one ~20GB VRAM) + six imitation agents (own dialogue/
    # order models) OOMs a 24GB A10G; A100-80GB fits both with headroom.
    sb = modal.Sandbox.create(
        app=app, image=image, gpu="A100-80GB", timeout=3600, volumes=VOL, cpu=8.0, memory=49152
    )
    game_json = ""
    try:
        print(f"sandbox {sb.object_id}: mode={mode} power={power} turns={max_turns}")
        code = _stream(sb.exec("bash", "-lc", cmd))
        if code != 0:
            raise RuntimeError(f"run.py failed with exit code {code}")
        cat = sb.exec(
            "bash",
            "-lc",
            "f=$(ls -t $(find /app/diplomacy_experiments -name output.json) "
            '2>/dev/null | head -1); [ -n "$f" ] && cat "$f"',
        )
        game_json = cat.stdout.read()
        cat_code = cat.wait()
        if cat_code != 0:
            raise RuntimeError("run.py succeeded but no output.json was found")
    finally:
        sb.terminate()
    if game_json.strip():
        outp = pathlib.Path(f"modal_cicero_{mode}_output.json")
        outp.write_text(game_json)
        print("wrote", outp, len(game_json), "bytes")
    else:
        raise RuntimeError("run.py produced an empty output.json")


# --- tactics oracle: a warm HTTP front for the agentic-diplomacy MCP bridge ----
#
# `serve` boots a long-lived Sandbox running the agentic-diplomacy oracle HTTP
# front (oracle/server/oracle_server.py --transport http) over a Modal tunnel.
# The agentic-diplomacy MCP registry points an `http` tier at the printed URL +
# token (OracleClient.modal(url, token)). This is Option A of TACTICS_SERVING_
# DESIGN.md: simplest warm-GPU path, with a Sandbox streaming the server process.
#
# Per-tier config: prototxt + value ckpt + search-budget overrides. Checkpoint
# names mirror what the cicero-models Volume holds; adjust to the actual volume
# contents (this whole entrypoint is gated on a live GPU smoke — see
# agentic-diplomacy/evals/README.md).
# Checkpoints reference the cicero-models Volume. searchbot/imitation point at the
# RL nets (rl_search_orders.ckpt) rather than the absent blueprint.pt — i.e. the
# "searchbot fed by RL nets" that is Cicero's own tactical core (TACTICS_SERVING_
# DESIGN §3). diplodocus_* need a one-time `fetch_models` download of their 3 ckpts
# (not on the Volume by default).
TIER_PRESETS = {
    # "imitation-only" = Cicero with imitation orders + dialogue but no RL search
    # (the cicero_imitation_only ablation), i.e. a full-press tier.
    "imitation": dict(
        config="conf/common/agents/ablations/cicero_imitation_only.prototxt",
        value="models/rl_value_function.ckpt",
        overrides=[],
    ),
    "searchbot": dict(
        config="conf/common/agents/searchbot.prototxt",
        value="models/rl_value_function.ckpt",
        overrides=[
            # rl_search_orders is policy-only; the CFR rollouts need a value head,
            # so point value_model_path at the RL value net (mirrors cicero.prototxt).
            "searchbot.model_path=models/rl_search_orders.ckpt",
            "searchbot.value_model_path=models/rl_value_function.ckpt",
            "searchbot.n_rollouts=8",
        ],
    ),
    "diplodocus_high": dict(
        config="conf/common/agents/diplodocus_high.prototxt",
        value="models/diplodocus_high_rl_value_function.ckpt",
        overrides=["bqre1p.base_searchbot_cfg.n_rollouts=64"],
    ),
    "diplodocus_low": dict(
        config="conf/common/agents/diplodocus_low.prototxt",
        value="models/diplodocus_low_value_function.ckpt",
        overrides=["bqre1p.base_searchbot_cfg.n_rollouts=64"],
    ),
    "cicero": dict(
        config="conf/common/agents/cicero.prototxt",
        value="models/rl_value_function.ckpt",
        overrides=[],
    ),
}

# Files staged FLAT into /opt/oracle so oracle_server.py's sibling imports
# (`import schema`, `from service/cicero_backend import ...`) resolve — mirroring
# the local container's /tmp/oracle flat staging.
ORACLE_FILES = [
    ("schema.py", "schema.py"),
    ("server/service.py", "service.py"),
    ("server/cicero_backend.py", "cicero_backend.py"),
    ("server/oracle_server.py", "oracle_server.py"),
]


def _serving_image():
    """The Cicero image with the oracle sidecar files baked in (flat) at /opt/oracle."""
    img = image
    for src_rel, dst_name in ORACLE_FILES:
        src = ORACLE_SRC / src_rel
        if not src.exists():
            raise FileNotFoundError(
                f"oracle source {src} not found; set AGENTIC_ORACLE_DIR to the "
                "agentic-diplomacy/oracle directory"
            )
        img = img.add_local_file(str(src), f"/opt/oracle/{dst_name}", copy=True)
    return img


def _rollout_key(tier):
    """The heyhi n_rollouts override key for a tier's search budget (None = no search)."""
    if tier in ("diplodocus_high", "diplodocus_low", "cicero"):
        return "bqre1p.base_searchbot_cfg.n_rollouts"
    if tier == "searchbot":
        return "searchbot.n_rollouts"
    return None  # imitation / base_strategy_model: no search


def _oracle_cmd(tiers, port, token, rollouts=0):
    """Build the `oracle_server.py --transport http` argv for the given tiers.

    rollouts>0 caps each search tier's n_rollouts (cheap smokes); 0 = config default.
    """
    args = [
        "python",
        "-u",
        "/opt/oracle/oracle_server.py",
        "--transport",
        "http",
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--device",
        "cuda",
    ]
    for tier in tiers:
        preset = TIER_PRESETS[tier]
        args += ["--agent", f"{tier}={preset['config']}"]
        if preset.get("value"):
            args += ["--value-model", f"{tier}={preset['value']}"]
        for ov in preset.get("overrides", []):
            args += ["--override", f"{tier}:{ov}"]
        if rollouts and _rollout_key(tier):
            args += ["--override", f"{tier}:{_rollout_key(tier)}={rollouts}"]
    # Runner dependencies are baked into ``image``; execution never mutates the
    # environment with pip.
    quoted = " ".join(args)
    return f"cd /app && PYTHONPATH=/app ORACLE_TOKEN={token} OMP_NUM_THREADS=8 {quoted}"


# Standard S1901M opening in Cicero format (emitted by `dip dump-positions`),
# used by the inline `serve --smoke` check.
_OPENING_GAME = {
    "id": "smoke",
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


def _rpc(url, token, method, params, timeout=600):
    """One POST /rpc to the oracle HTTP front (raw urllib; no oracle deps)."""
    import json
    import urllib.request

    body = json.dumps({"id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/rpc",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode())
    if not resp.get("ok"):
        raise RuntimeError(f"{method} -> {resp.get('error')}")
    return resp["result"]


def _inline_smoke(url, token, tiers, full_press):
    """Drive info/get_orders/policy/value (+message) over the tunnel; print a report."""
    import json

    game = json.dumps(_OPENING_GAME)
    info = _rpc(url, token, "info", {})
    print("[smoke][info]", json.dumps(info))
    for tier in tiers:
        orders = _rpc(
            url, token, "get_orders", {"game_json": game, "power": "FRANCE", "tier": tier}
        )
        if not orders.get("orders"):
            raise RuntimeError(f"get_orders({tier}) returned no orders")
        print(f"[smoke][get_orders][{tier}] FRANCE -> {orders['orders']}")
        pol = _rpc(
            url,
            token,
            "policy",
            {"game_json": game, "power": "FRANCE", "tier": tier, "top_k": 3},
        )
        if not pol.get("policy"):
            raise RuntimeError(f"policy({tier}) returned no candidates")
        print(
            f"[smoke][policy][{tier}] top3 -> "
            f"{[(p['orders'], round(p['prob'], 3)) for p in pol['policy']]}"
        )
        val = _rpc(url, token, "value", {"game_json": game, "tier": tier})
        if not val.get("value"):
            raise RuntimeError(f"value({tier}) returned no values")
        print(
            f"[smoke][value][{tier}] -> "
            f"{json.dumps({k: round(v, 4) for k, v in val['value'].items()})}"
        )
        if full_press:
            msg = _rpc(
                url,
                token,
                "generate_message",
                {"game_json": game, "power": "FRANCE", "recipient": "ENGLAND", "tier": tier},
            )
            print(f"[smoke][message][{tier}] FRANCE->{msg.get('recipient')}: {msg.get('body')!r}")
    print("[smoke] ✅ PASSED")


@app.local_entrypoint()
def serve(
    tiers: str = "searchbot",
    port: int = 8000,
    gpu: str = "A10G",
    timeout: int = 3600,
    token: str = "",
    smoke: bool = False,
    full_press: bool = False,
    rollouts: int = 0,
) -> None:
    """Serve the agentic-diplomacy oracle HTTP front over a Modal tunnel.

    tiers:   comma-separated subset of TIER_PRESETS to load into one process
             (no-press tiers are light and co-resident; use a dedicated A100
             `serve` for `cicero`, e.g. --tiers cicero --gpu A100-80GB).
    smoke:   if set, run an inline info/get_orders/policy/value smoke against the
             tunnel (add --full-press to also exercise generate_message) and exit.
    Prints the tunnel URL + bearer token; wire them into the MCP registry as an
    `http` tier. Without --smoke the box stays warm until `timeout`.
    """
    import threading
    import time
    import urllib.request

    tier_list = [t.strip() for t in tiers.split(",") if t.strip()]
    if not tier_list:
        raise ValueError("tiers must select at least one oracle tier")
    unknown = [t for t in tier_list if t not in TIER_PRESETS]
    if unknown:
        raise ValueError(f"unknown tiers {unknown}; choose from {sorted(TIER_PRESETS)}")
    token = token or secrets.token_urlsafe(24)

    sb = modal.Sandbox.create(
        app=app,
        image=_serving_image(),
        gpu=gpu,
        volumes=VOL,
        encrypted_ports=[port],
        timeout=timeout,
        cpu=8.0,
        memory=49152,
    )
    try:
        proc = sb.exec("bash", "-lc", _oracle_cmd(tier_list, port, token, rollouts))
        # Stream server logs in the background so a crash's traceback is visible.
        for s in (proc.stdout, proc.stderr):
            threading.Thread(
                target=lambda st: [print(line, end="", flush=True) for line in st],
                args=(s,),
                daemon=True,
            ).start()
        url = sb.tunnels()[port].url
        print("=" * 72)
        print(f"oracle serving tiers={tier_list} gpu={gpu}")
        print(f"  URL:   {url}")
        print(f"  TOKEN: {token}")
        print('  MCP registry: {"transport":"http","url":"%s","token_env":"ORACLE_TOKEN"}' % url)
        print("=" * 72, flush=True)

        # Supervise: wait for /health, optionally smoke, then keep warm. Polling
        # /health from here (the local entrypoint) also keeps the sandbox alive
        # without depending on the server process to block the entrypoint.
        deadline = time.time() + timeout
        healthy = False
        while time.time() < deadline:
            rc = proc.poll()
            if rc is not None:
                raise RuntimeError(f"oracle process exited with code {rc}; see streamed logs")
            if not healthy:
                try:
                    with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=10) as r:
                        healthy = r.status == 200
                except Exception:
                    healthy = False
                if healthy:
                    print("[serve] /health OK — oracle ready", flush=True)
                    if smoke:
                        _inline_smoke(url, token, tier_list, full_press)
                        return
            time.sleep(5)
        if not healthy:
            raise TimeoutError(f"oracle did not become healthy within {timeout} seconds")
    finally:
        sb.terminate()
