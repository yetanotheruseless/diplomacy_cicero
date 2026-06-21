"""
Run Meta/FAIR Cicero (Diplomacy AI) on a Modal GPU.

This rebuilds the legacy stack for x86_64 + CUDA (the local Mac image is arm64
and CPU-only). Key choices:
  * Base: python:3.9-slim (py3.9 is the newest with a torch 1.10.0 wheel).
  * torch==1.10.0+cu113 (real CUDA wheels exist for x86_64 cp39); the wheel
    bundles the CUDA runtime and Modal injects the driver — no CUDA base needed.
  * dipcc / pydipcc are recompiled for x86_64 inside the image (the repo's
    prebuilt .so is aarch64). The repo's generated conf/*_pb2.py + patched
    conf_cfgs.py are pure-Python and reused as-is, so no protobuf-from-source.
  * Models are served from a Modal Volume (`cicero-models`) at /app/models,
    populated by: modal volume put cicero-models .cicero_model_stage /
  * On GPU we keep half_precision (the config default) — it's GPU-only and was
    the thing that broke on CPU.

Usage:
  modal run modal_app.py::smoke                 # verify imports + pydipcc + GPU
  modal run modal_app.py::run_cicero            # full Cicero, Turkey, 1 turn
  modal run modal_app.py::run_cicero --mode policy --power AUSTRIA --max-turns 1
  modal run modal_app.py::serve --tiers searchbot,diplodocus_high   # tactics oracle
"""
import os
import pathlib
import secrets
import subprocess

import modal

REPO = pathlib.Path(__file__).parent

# The agentic-diplomacy oracle bridge lives in a sibling repo. `serve` stages its
# four sidecar files (flat) into the serving image and runs the HTTP front. Point
# AGENTIC_ORACLE_DIR at a different checkout if it isn't the default sibling path.
ORACLE_SRC = pathlib.Path(
    os.environ.get("AGENTIC_ORACLE_DIR", str(REPO.parent / "agentic-diplomacy" / "oracle"))
)

# Files/dirs that must NOT go into the image build context.
IGNORE = [
    ".git", "models", "models_encrypted", ".cicero_model_stage",
    "diplomacy_experiments", "*.log", "**/*.so", "dipcc_pkg",
    "dipcc/build", "**/__pycache__", "*.bak", "wandb",
    # driver/docs/outputs — not needed in the image; excluding keeps edits to
    # them from invalidating the (slow) nest/dipcc build layers.
    "modal_app.py", "*.md", "*.txt", "modal_cicero_*.json",
]

TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_CU_INDEX = "https://download.pytorch.org/whl/cu113"
TORCH_LIB = "/usr/local/lib/python3.9/site-packages/torch/lib"

# Install a modern patchelf (0.18) for --clear-execstack / --set-rpath.
PATCHELF = (
    "wget -q https://github.com/NixOS/patchelf/releases/download/0.18.0/patchelf-0.18.0-x86_64.tar.gz -O /tmp/patchelf.tgz && "
    "mkdir -p /tmp/pe && tar xzf /tmp/patchelf.tgz -C /tmp/pe && "
    "cp \"$(find /tmp/pe -type f -name patchelf | head -1)\" /usr/local/bin/patchelf && patchelf --version"
)

# The exact dependency layer that runs Cicero (mirrors the verified arm64 set,
# but with CUDA torch). transformers/tokenizers are intentionally omitted —
# ParlAI uses its own fairseq GPT-2 BPE.
PIP_DEPS = [
    "numpy==1.20.3", "protobuf==3.19.1", "pybind11", "cython==0.29.24",
    "tabulate==0.8.9", "termcolor==1.1.0", "joblib==1.1.0", "pygtrie==2.4.2",
    "typer==0.4.1", "tqdm==4.62.1", "psutil==5.9.0",
    "ephemeral-port-reserve==1.1.4", "dacite==1.6.0", "attrs==20.2.0",
    "colored==1.4.3", "requests==2.27.1", "tensorboard==2.8.0", "pyyaml",
    "scipy", "sentencepiece", "ftfy", "emoji", "tornado", "wandb", "iopath",
    "subword-nmt", "scikit-learn", "fairscale==0.4.6",
    # compatibility pins for ParlAI / Pillow against numpy 1.20 / py3.8
    "Pillow==9.5.0", "importlib-metadata==4.2.0", "markdown==3.3.2",
    "urllib3==1.26.18",
    # CRITICAL: setuptools<60 so torch 1.10 tensorboard import doesn't crash.
    "setuptools==59.5.0",
]

image = (
    # python:3.9-slim is the simplest Modal-compatible base (Modal runs its own
    # `python -m pip` bootstrap before our steps, so the base MUST already have
    # python; CUDA base images don't, and add_python can't do 3.9).
    #
    # We can't find_package(Torch) against the CUDA wheel without the CUDA
    # toolkit, which this base lacks. So: build pydipcc against CPU torch
    # 1.10.0 (no CUDA needed), then swap in torch 1.10.0+cu113 for runtime.
    # Same torch version => ABI-compatible libtorch_cpu.so/libc10.so, which is
    # all pydipcc links; we bake the cu113 torch/lib path into pydipcc's rpath.
    modal.Image.from_registry("python:3.9-slim")
    .apt_install(
        "build-essential", "cmake", "git", "wget", "curl",
        "libgoogle-glog-dev", "libgflags-dev",
    )
    .run_commands(PATCHELF)
    # Build-time torch: CPU build (cmake config doesn't require the CUDA toolkit).
    .pip_install("torch==1.10.0+cpu", index_url=TORCH_CPU_INDEX)
    .pip_install(*PIP_DEPS)
    # ParlAI at the pinned commit, no-deps so it can't move torch off 1.10.
    .pip_install(
        "git+https://github.com/facebookresearch/ParlAI.git@5214f42a2058ef335f91f5afe66b2bd9ebfb2fbe",
        extra_options="--no-deps",
    )
    # torch's libs have an executable stack that Modal's gVisor sandbox refuses
    # to load; clear it so torch imports during the build (and later at runtime).
    .run_commands(
        f"find {TORCH_LIB} -name '*.so*' -exec patchelf --clear-execstack {{}} + && "
        "python -c 'import torch; print(\"build torch\", torch.__version__)'"
    )
    # Bring in the repo source (no models / .git / stale .so).
    .add_local_dir(str(REPO), "/app", copy=True, ignore=IGNORE)
    # Build the vendored nest pybind11 extension.
    .run_commands(
        "cd /app && CXX=c++ pip install thirdparty/github/fairinternal/postman/nest/"
    )
    # Compile pydipcc (x86_64) against CPU torch, into fairdiplomacy/.
    .run_commands(
        "cd /app/dipcc && rm -rf build && mkdir -p build && cd build && "
        "PYBIND_DIR=$(python -c 'import pybind11;print(pybind11.get_cmake_dir())') && "
        "TORCH_CM=$(python -c 'import torch;print(torch.utils.cmake_prefix_path)') && "
        "echo \"pybind11_DIR=$PYBIND_DIR torch_cmake=$TORCH_CM\" && "
        "cmake -DCMAKE_BUILD_TYPE=Release "
        "-DPYTHON_EXECUTABLE=$(which python) "
        "-Dpybind11_DIR=\"$PYBIND_DIR\" "
        "-DCMAKE_PREFIX_PATH=\"$TORCH_CM;$PYBIND_DIR\" "
        ".. && make -j$(nproc) pydipcc && "
        "cp dipcc/python/pydipcc*.so /app/fairdiplomacy/ && "
        "ls -la /app/fairdiplomacy/pydipcc*.so"
    )
    # Swap in the CUDA torch for runtime, then fix pydipcc's rpath + execstack so
    # it loads the cu113 torch's libtorch_cpu.so/libc10.so.
    .pip_install(
        "torch==1.10.0+cu113", index_url=TORCH_CU_INDEX,
        extra_options="--no-deps --force-reinstall",
    )
    .run_commands(
        f"find {TORCH_LIB} -name '*.so*' -exec patchelf --clear-execstack {{}} + && "
        f"patchelf --set-rpath {TORCH_LIB} /app/fairdiplomacy/pydipcc*.so && "
        "patchelf --clear-execstack /app/fairdiplomacy/pydipcc*.so && "
        "python -c 'import torch; print(\"runtime torch\", torch.__version__, torch.version.cuda)'"
    )
    .env({
        "PYTHONPATH": "/app",
        "HH_EXP_DIR": "/app/diplomacy_experiments",
        "LD_LIBRARY_PATH": TORCH_LIB,
    })
)

app = modal.App("cicero")
models_volume = modal.Volume.from_name("cicero-models", create_if_missing=True)
VOL = {"/app/models": models_volume}

# Lightweight image just for fetching+decrypting weights straight into the
# Volume from Modal's datacenter (far faster than uploading 36GB from a laptop).
download_image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("gnupg", "wget", "ca-certificates")
)
MODELS_BASE_URL = "https://dl.fbaipublicfiles.com/diplomacy_cicero/models"


@app.function(image=download_image, volumes=VOL, timeout=3600, cpu=8.0,
              secrets=[modal.Secret.from_name("cicero-gpg")])
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
        subprocess.run(["wget", "-q", f"{MODELS_BASE_URL}/{rel}.gpg", "-O", gpg],
                       check=True)
        subprocess.run(["gpg", "--batch", "--yes", "--passphrase", pw,
                        "--output", out, "-d", gpg], check=True,
                       stderr=subprocess.DEVNULL)
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
def download(relpaths_file: str = "/tmp/cicero_subset_relpaths.txt"):
    relpaths = [l for l in pathlib.Path(relpaths_file).read_text().split("\n") if l.strip()]
    print(f"fetching {len(relpaths)} model files into volume cicero-models ...")
    n = fetch_models.remote(relpaths)
    print(f"done: {n} files present on volume")


def _run_args(mode: str, power: str, max_turns) -> str:
    """run.py CLI args for a given agent mode (space-joined)."""
    common = (f"--adhoc --cfg conf/c01_ag_cmp/cmp.prototxt "
              f"max_turns={max_turns} power_one={power}")
    if mode == "policy":
        extra = ("Iagent_one=agents/base_strategy_model "
                 "Iagent_six=agents/base_strategy_model")
    elif mode == "search":
        extra = ("agent_one.searchbot.n_rollouts=10 "
                 "agent_one.searchbot.rollouts_cfg.n_threads=8")
    elif mode == "cicero":
        # half_precision left at the config default (True) — works on GPU.
        # Documented matchup: full Cicero vs six imitation_only (press-capable,
        # required since the env forbids mixing press + no-press agents). Needs
        # the produce_action fix in ParlAIAllOrderIndependentRolloutWrapper.
        six = os.environ.get("SIX", "agents/ablations/cicero_imitation_only.prototxt")
        # max_msg_iters caps the simulated 24h negotiation so the phase actually
        # terminates (else it generates hundreds of messages).
        extra = ("Iagent_one=agents/cicero.prototxt "
                 f"Iagent_six={six} "
                 f"max_msg_iters={os.environ.get('MSG_ITERS', '30')}")
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

    threads = [threading.Thread(target=pump, args=(s,), daemon=True)
               for s in (proc.stdout, proc.stderr)]
    for t in threads:
        t.start()
    code = proc.wait()
    for t in threads:
        t.join(timeout=5)
    return code


# We drive Cicero with a Modal Sandbox rather than @app.function: the image runs
# Python 3.9 (required by torch 1.10), but @app.function needs >=3.10. A Sandbox
# just exec's commands in the image, so no version conflict. GPU + model Volume
# are attached the same way.
@app.local_entrypoint()
def smoke():
    """Verify torch+CUDA, pydipcc, agents import, and the model volume."""
    check = (
        "import torch;print('torch',torch.__version__,'cuda',torch.cuda.is_available());"
        "print('gpu',torch.cuda.get_device_name(0) if torch.cuda.is_available() else None);"
        "import fairdiplomacy;from fairdiplomacy.pydipcc import Game;"
        "print('pydipcc OK phase',Game().current_short_phase);"
        "import heyhi.conf;from fairdiplomacy.agents import build_agent_from_cfg;"
        "import os;print('models entries',len(os.listdir('/app/models')))"
    )
    sb = modal.Sandbox.create(app=app, image=image, gpu="A10G",
                              timeout=900, volumes=VOL)
    try:
        print("sandbox:", sb.object_id)
        code = _stream(sb.exec("bash", "-lc", f"cd /app && python -c \"{check}\""))
        print("exit", code)
    finally:
        sb.terminate()


@app.local_entrypoint()
def game(power: str = "TURKEY", max_year: str = "1907",
         max_msg_iters: str = "30", max_turns: str = "20"):
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
    cmd = (f"cd /app && pip install -q six regex sh nltk websocket-client && "
           f"OMP_NUM_THREADS=8 python run.py {runargs}")
    partial_local = pathlib.Path(f"modal_cicero_game_{power}.partial.json")
    final_local = pathlib.Path(f"modal_cicero_game_{power}.json")
    pull_partial = ("f=$(find /app/diplomacy_experiments -name output.json.partial "
                    "2>/dev/null | head -1); [ -n \"$f\" ] && cat \"$f\"")
    pull_final = ("f=$(ls -t $(find /app/diplomacy_experiments -name output.json) "
                  "2>/dev/null | head -1); [ -n \"$f\" ] && cat \"$f\"")

    sb = modal.Sandbox.create(app=app, image=image, gpu="A100-80GB",
                              timeout=14400, volumes=VOL, cpu=8.0, memory=49152)
    final = ""
    try:
        print(f"sandbox {sb.object_id}: game power={power} -> {max_year}, "
              f"max_msg_iters={max_msg_iters}")
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
                    print(f"[snapshot] {len(snap)}B -> {partial_local.name}; "
                          f"phases: {phases}")
                except Exception:
                    print(f"[snapshot] {len(snap)}B -> {partial_local.name}")
        runner.join(timeout=10)
        final = sb.exec("bash", "-lc", pull_final).stdout.read()
    finally:
        sb.terminate()
    if final.strip():
        final_local.write_text(final)
        print(f"wrote {final_local} ({len(final)} bytes)")
    elif partial_local.exists():
        print(f"no final output; latest partial kept at {partial_local}")


@app.local_entrypoint()
def main(mode: str = "cicero", power: str = "", max_turns: str = "1"):
    if not power:
        power = "TURKEY" if mode == "cicero" else "AUSTRIA"
    runargs = _run_args(mode, power, max_turns)
    # Deps missing from the baked image's x86_64 transitive closure; installed
    # at runtime during bring-up (fold into PIP_DEPS once stable).
    extra_pip = "six regex sh nltk websocket-client"
    cmd = (f"cd /app && pip install -q {extra_pip} && "
           f"PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:128 "
           f"OMP_NUM_THREADS=8 python run.py {runargs}")
    # Full Cicero (agent_one ~20GB VRAM) + six imitation agents (own dialogue/
    # order models) OOMs a 24GB A10G; A100-80GB fits both with headroom.
    sb = modal.Sandbox.create(app=app, image=image, gpu="A100-80GB",
                              timeout=3600, volumes=VOL, cpu=8.0, memory=49152)
    game_json = ""
    try:
        print(f"sandbox {sb.object_id}: mode={mode} power={power} turns={max_turns}")
        code = _stream(sb.exec("bash", "-lc", cmd))
        print("run.py exit:", code)
        cat = sb.exec("bash", "-lc",
                      "f=$(ls -t $(find /app/diplomacy_experiments -name output.json) "
                      "2>/dev/null | head -1); [ -n \"$f\" ] && cat \"$f\"")
        game_json = cat.stdout.read()
        cat.wait()
    finally:
        sb.terminate()
    if game_json.strip():
        outp = pathlib.Path(f"modal_cicero_{mode}_output.json")
        outp.write_text(game_json)
        print("wrote", outp, len(game_json), "bytes")


# --- tactics oracle: a warm HTTP front for the agentic-diplomacy MCP bridge ----
#
# `serve` boots a long-lived Sandbox running the agentic-diplomacy oracle HTTP
# front (oracle/server/oracle_server.py --transport http) over a Modal tunnel.
# The agentic-diplomacy MCP registry points an `http` tier at the printed URL +
# token (OracleClient.modal(url, token)). This is Option A of TACTICS_SERVING_
# DESIGN.md: simplest, warm GPU, no Python-3.9 jail issue (a Sandbox just exec's).
#
# Per-tier config: prototxt + value ckpt + search-budget overrides. Checkpoint
# names mirror what the cicero-models Volume holds; adjust to the actual volume
# contents (this whole entrypoint is gated on a live GPU smoke — see
# agentic-diplomacy/evals/README.md).
TIER_PRESETS = {
    "imitation": dict(
        config="conf/common/agents/base_strategy_model.prototxt",
        value="models/human_sl_value_function.ckpt",
        overrides=[],
    ),
    "searchbot": dict(
        config="conf/common/agents/searchbot.prototxt",
        value="models/rl_value_function.ckpt",
        overrides=["searchbot.n_rollouts=64"],
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


def _oracle_cmd(tiers, port, token):
    """Build the `oracle_server.py --transport http` argv for the given tiers."""
    args = [
        "python", "-u", "/opt/oracle/oracle_server.py",
        "--transport", "http", "--host", "0.0.0.0", "--port", str(port),
        "--device", "cuda",
    ]
    for tier in tiers:
        preset = TIER_PRESETS[tier]
        args += ["--agent", f"{tier}={preset['config']}"]
        if preset.get("value"):
            args += ["--value-model", f"{tier}={preset['value']}"]
        for ov in preset.get("overrides", []):
            args += ["--override", f"{tier}:{ov}"]
    # Token via env so it never lands in `ps`/logs.
    quoted = " ".join(args)
    return f"cd /app && PYTHONPATH=/app ORACLE_TOKEN={token} OMP_NUM_THREADS=8 {quoted}"


@app.local_entrypoint()
def serve(tiers: str = "searchbot", port: int = 8000, gpu: str = "A10G",
          timeout: int = 3600, token: str = ""):
    """Serve the agentic-diplomacy oracle HTTP front over a Modal tunnel.

    tiers:   comma-separated subset of TIER_PRESETS to load into one process
             (no-press tiers are light and co-resident; use a dedicated A100
             `serve` for `cicero`, e.g. --tiers cicero --gpu A100-80GB).
    Prints the tunnel URL + bearer token; wire them into the MCP registry as an
    `http` tier. The box stays up for `timeout` seconds (warm GPU); Ctrl-C ends it.
    """
    import time

    tier_list = [t.strip() for t in tiers.split(",") if t.strip()]
    unknown = [t for t in tier_list if t not in TIER_PRESETS]
    if unknown:
        raise ValueError(f"unknown tiers {unknown}; choose from {sorted(TIER_PRESETS)}")
    token = token or secrets.token_urlsafe(24)

    sb = modal.Sandbox.create(
        app=app, image=_serving_image(), gpu=gpu, volumes=VOL,
        encrypted_ports=[port], timeout=timeout, cpu=8.0, memory=49152,
    )
    try:
        proc = sb.exec("bash", "-lc", _oracle_cmd(tier_list, port, token))
        url = sb.tunnels()[port].url
        print("=" * 72)
        print(f"oracle serving tiers={tier_list} gpu={gpu}")
        print(f"  URL:   {url}")
        print(f"  TOKEN: {token}")
        print("  MCP registry tier spec:")
        print(f'    {{"transport": "http", "url": "{url}", "token_env": "ORACLE_TOKEN"}}')
        print("  (export ORACLE_TOKEN=<token> where the MCP server runs)")
        print("=" * 72, flush=True)
        # Stream the server's logs until the sandbox times out or is interrupted.
        _stream(proc)
    finally:
        sb.terminate()
