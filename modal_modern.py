"""
Validate the MODERNIZED Cicero stack on Modal (Linux x86_64 [+ CUDA]).

This is the Linux/x86_64 counterpart to scripts/modernize_setup.sh. It builds
one pinned stack: Python 3.12, torch 2.13.0 (CPU or CUDA 13.0), protobuf 7.35.1,
protoc 35.1, the rewritten heyhi patch_protos.py, the pure-Python ``nest`` shim,
and pydipcc.

  B5  pydipcc builds on Linux x86_64 + multi-turn adjudication correct   (CPU)
  B1  torch.load(weights_only=False) a real base_strategy_model ckpt and
      load it into the modern nn.Module definitions                      (CPU)
  B2  base_strategy_model GPU inference (modern CUDA torch)               (GPU)
  B3  one ParlAI/BART dialogue forward pass                              (GPU)

Cost discipline: everything except B2/B3 runs on CPU. The GPU function is short.

Entrypoints:
  modal run modal_modern.py::build_and_adjudicate     # B5 (CPU)
  modal run modal_modern.py::load_weights             # B1 (CPU)
  modal run modal_modern.py::gpu_checks               # B2 + B3 (GPU)
"""

import pathlib

import modal

REPO = pathlib.Path(__file__).parent

IGNORE = [
    ".git",
    ".venv-modern",
    "models",
    "models_encrypted",
    ".cicero_model_stage",
    "diplomacy_experiments",
    "*.log",
    "**/*.so",
    "dipcc_pkg",
    "dipcc/build",
    "**/__pycache__",
    "*.bak",
    "wandb",
    "modal_app.py",
    "modal_modern.py",
    "*.md",
    "modal_cicero_*.json",
    # Drop the generated protos from context; we regenerate them in-image with
    # the modern protoc so the format matches the modern runtime exactly.
    "conf/*_pb2.py",
    "conf/*_pb2.pyi",
    "conf/*_cfgs.py",
    "conf/*_cfgs.pyi",
]

# The only supported cloud-validation line. Keep these exact: the image checks
# every value at build/runtime so version drift becomes a hard failure.
PYTHON_VERSION = "3.12"
TORCH_VERSION = "2.13.0"
CUDA_VERSION = "13.0"
CUDA_IMAGE_VERSION = "13.0.3"
PROTOBUF_VERSION = "7.35.1"
PROTOC_VERSION = "35.1"
NUMPY_VERSION = "2.4.6"

# Each image installs its final Torch variant before compiling pydipcc. The GPU
# build uses the same CUDA 13 development base and cu130 index as the Docker
# runtime-stack build; Modal supplies the host NVIDIA driver.
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_CUDA_INDEX = "https://download.pytorch.org/whl/cu130"
PACKAGING_TOOLS = ["pip==26.1.2", "setuptools==83.0.0", "wheel==0.47.0"]


def _build_runtime_cmds() -> list[str]:
    """Use the repository's canonical dependency/codegen/native build path."""
    return [
        f"cd /app && PROTOC_VERSION={PROTOC_VERSION} ./scripts/install_protoc.sh",
        "cd /app && python -m pip install --no-cache-dir --editable '.[build,dialogue,dev]' "
        "&& python -m pip check",
        "cd /app && make protos",
        "cd /app && PYDIPCC_OUT_DIR=/app/fairdiplomacy N_DIPCC_JOBS=4 ./dipcc/compile.sh",
        "cd /app && ./scripts/install_parlai.sh && python -m pip check",
    ]


def _base_image(want_cuda: bool) -> modal.Image:
    """Build one final CPU or CUDA runtime without cross-wheel swapping."""
    registry = (
        f"nvidia/cuda:{CUDA_IMAGE_VERSION}-cudnn-devel-ubuntu24.04"
        if want_cuda
        else "ubuntu:24.04"
    )
    torch_variant = f"{TORCH_VERSION}+{'cu130' if want_cuda else 'cpu'}"
    torch_index = TORCH_CUDA_INDEX if want_cuda else TORCH_CPU_INDEX
    img = (
        modal.Image.from_registry(registry, add_python=PYTHON_VERSION)
        .apt_install(
            "build-essential",
            "ca-certificates",
            "cmake",
            "git",
            "curl",
            "gcc-13",
            "g++-13",
            "ninja-build",
            "unzip",
            "libgoogle-glog-dev",
            "libgflags-dev",
        )
        .pip_install(
            f"torch=={torch_variant}",
            index_url=torch_index,
        )
        # Torch may select its own build-helper setuptools; restore the exact
        # repository toolchain before building the editable project.
        .pip_install(*PACKAGING_TOOLS)
        .add_local_dir(str(REPO), "/app", copy=True, ignore=IGNORE)
        .env(
            {
                "PYTHONPATH": "/app",
                "HH_EXP_DIR": "/app/diplomacy_experiments",
                "CC": "gcc-13",
                "CXX": "g++-13",
            }
        )
    )
    for cmd in _build_runtime_cmds():
        img = img.run_commands(cmd)
    if want_cuda:
        img = img.run_commands(
            'python -c "import importlib.metadata as m; import torch; '
            f"assert torch.__version__ == '{torch_variant}', torch.__version__; "
            f"assert torch.version.cuda == '{CUDA_VERSION}', torch.version.cuda; "
            "assert m.version('pip') == '26.1.2'; "
            "assert m.version('setuptools') == '83.0.0'; "
            "assert m.version('wheel') == '0.47.0'\""
        )
    else:
        img = img.run_commands(
            'python -c "import torch; '
            f"assert torch.__version__ == '{torch_variant}', torch.__version__; "
            'assert torch.version.cuda is None, torch.version.cuda"'
        )
    return img


cpu_image = _base_image(want_cuda=False)
gpu_image = _base_image(want_cuda=True)

app = modal.App("cicero-modern")
models_volume = modal.Volume.from_name("cicero-models", create_if_missing=True)
VOL = {"/app/models": models_volume}


def _validate_runtime(expect_cuda: bool) -> None:
    """Fail unless the container is running the exact supported stack."""
    import subprocess
    import sys
    from importlib.metadata import version

    import google.protobuf
    import numpy
    import torch

    def require(condition: bool, message: object) -> None:
        if not condition:
            raise RuntimeError(str(message))

    require(sys.version_info[:2] == (3, 12), sys.version)
    expected_torch = f"{TORCH_VERSION}+{'cu130' if expect_cuda else 'cpu'}"
    require(torch.__version__ == expected_torch, torch.__version__)
    require(google.protobuf.__version__ == PROTOBUF_VERSION, google.protobuf.__version__)
    require(numpy.__version__ == NUMPY_VERSION, numpy.__version__)
    require(version("pip") == "26.1.2", version("pip"))
    require(version("setuptools") == "83.0.0", version("setuptools"))
    require(version("wheel") == "0.47.0", version("wheel"))
    require(version("parlai") == "1.5.1+cicero1", version("parlai"))
    protoc_version = subprocess.check_output(["protoc", "--version"], text=True).strip()
    require(protoc_version == f"libprotoc {PROTOC_VERSION}", protoc_version)
    if expect_cuda:
        require(torch.version.cuda == CUDA_VERSION, torch.version.cuda)
        require(
            torch.cuda.is_available(),
            "CUDA 13.0 wheel loaded but no Modal GPU is available",
        )
        require(torch.cuda.device_count() > 0, "no CUDA devices visible")
    else:
        require(
            not torch.cuda.is_available(),
            "CPU validation image unexpectedly exposes CUDA",
        )


# --------------------------------------------------------------------------- B5
@app.function(image=cpu_image, cpu=4.0, timeout=900)
def _b5() -> bool:
    import torch
    import fairdiplomacy  # noqa: F401
    from fairdiplomacy.pydipcc import Game

    _validate_runtime(expect_cuda=False)
    print("torch", torch.__version__, "cuda?", torch.cuda.is_available())
    import google.protobuf

    print("protobuf runtime", google.protobuf.__version__)

    g = Game()
    if g.current_short_phase != "S1901M":
        raise RuntimeError(f"unexpected initial phase: {g.current_short_phase}")
    g.set_orders("AUSTRIA", ["A VIE - GAL", "A BUD - SER", "F TRI - ALB"])
    g.set_orders("RUSSIA", ["A WAR - GAL", "A MOS - UKR", "F SEV - BLA", "F STP/SC - BOT"])
    g.set_orders("GERMANY", ["A BER - KIE", "A MUN - RUH", "F KIE - DEN"])
    g.process()
    if g.current_short_phase != "F1901M":
        raise RuntimeError(f"unexpected adjudicated phase: {g.current_short_phase}")
    units = g.get_state()["units"]
    # VIE-GAL vs WAR-GAL bounce: both armies stay put.
    if "A VIE" not in units["AUSTRIA"] or "A WAR" not in units["RUSSIA"]:
        raise RuntimeError(f"GAL bounce adjudicated incorrectly: {units}")
    g.set_orders("GERMANY", ["A KIE - HOL", "A RUH - BEL", "F DEN - SWE"])
    g.process()  # F1901M
    g.process()  # builds/retreats -> next movement
    centers = {p: len(v) for p, v in g.get_state()["centers"].items() if v}
    print("phase", g.current_short_phase, "SC", centers)
    # JSON round-trip
    g2 = Game.from_json(g.to_json())
    if g2.current_short_phase != g.current_short_phase:
        raise RuntimeError(
            f"JSON phase mismatch: {g2.current_short_phase} != {g.current_short_phase}"
        )
    print("B5 PASS: pydipcc builds on Linux x86_64 + multi-turn adjudication correct")
    return True


@app.local_entrypoint()
def build_and_adjudicate() -> None:
    if _b5.remote() is not True:
        raise RuntimeError("B5 did not return its success sentinel")


# --------------------------------------------------------------------------- B1
@app.function(image=cpu_image, volumes=VOL, cpu=4.0, timeout=1200)
def _b1(ckpts: list[str]) -> dict[str, str]:
    """Load real base_strategy_model checkpoints with weights_only=False and
    instantiate the modern nn.Module from each (the load_model.py path)."""
    import os

    import torch
    import fairdiplomacy  # noqa: F401 - ensures pydipcc loads

    _validate_runtime(expect_cuda=False)
    print("torch", torch.__version__)
    results = {}
    for rel in ckpts:
        path = f"/app/models/{rel}"
        if not os.path.exists(path):
            raise FileNotFoundError(f"required B1 checkpoint is missing: {path}")

        # Cicero checkpoints are trusted full pickles, so torch 2.x must not use
        # the weights-only loader default.
        blob = torch.load(path, map_location="cpu", weights_only=False)
        keys = list(blob.keys()) if isinstance(blob, dict) else type(blob).__name__
        print(rel, "raw load OK; top-level keys:", keys)

        from fairdiplomacy.models.base_strategy_model.load_model import (
            load_base_strategy_model_model,
        )

        model = load_base_strategy_model_model(path, map_location="cpu", eval=True)
        n_params = sum(p.numel() for p in model.parameters())
        if n_params <= 0:
            raise RuntimeError(f"{rel} loaded an empty model")
        print(rel, f"-> nn.Module {type(model).__name__} loaded, {n_params / 1e6:.1f}M params")
        results[rel] = f"OK {type(model).__name__} {n_params / 1e6:.1f}M"
    print("=== B1 results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    return results


@app.local_entrypoint()
def load_weights() -> None:
    ckpts = [
        "no_press_human_imitation_policy.ckpt",
        "rl_search_orders.ckpt",
        "rl_value_function.ckpt",
        "diplodocus_high_rl_policy.ckpt",
    ]
    res = _b1.remote(ckpts)
    ok = sum(1 for v in res.values() if str(v).startswith("OK"))
    print(f"B1: {ok}/{len(res)} checkpoints loaded into modern nn.Module")
    if ok != len(ckpts):
        raise RuntimeError(f"B1 loaded {ok}/{len(ckpts)} required checkpoints")


# ------------------------------------------------------------------------- B2/B3
@app.function(image=gpu_image, volumes=VOL, gpu="A10G", timeout=1200)
def _b2_b3() -> dict[str, str]:
    import os

    import torch
    import fairdiplomacy  # noqa: F401
    from fairdiplomacy.pydipcc import Game

    _validate_runtime(expect_cuda=True)
    print(
        "torch",
        torch.__version__,
        "cuda",
        torch.version.cuda,
        "avail",
        torch.cuda.is_available(),
        "dev",
        torch.cuda.get_device_name(0),
    )

    # Exercise a real CUDA 13.0 kernel before model loading, then synchronize so
    # driver/runtime/kernel failures surface in this function.
    probe = torch.randn((512, 512), device="cuda", dtype=torch.float16)
    probe_result = probe @ probe
    torch.cuda.synchronize()
    if not torch.isfinite(probe_result).all().item():
        raise RuntimeError("CUDA matmul produced non-finite values")

    # ---- B2: base_strategy_model GPU inference ----
    candidates = [
        "/app/models/no_press_human_imitation_policy.ckpt",
        "/app/models/rl_search_orders.ckpt",
    ]
    ckpt = next((path for path in candidates if os.path.exists(path)), None)
    if ckpt is None:
        raise FileNotFoundError(f"B2 needs one of these checkpoints: {candidates}")
    from fairdiplomacy.agents.base_strategy_model_wrapper import BaseStrategyModelWrapper

    wrapper = BaseStrategyModelWrapper(ckpt, device="cuda", half_precision=True)
    model_parameter = next(wrapper.model.parameters(), None)
    if model_parameter is None or not model_parameter.is_cuda:
        raise RuntimeError("B2 strategy model did not load onto CUDA")
    orders, _ = wrapper.forward_policy(
        [Game()],
        has_press=False,
        agent_power=None,
        temperature=1.0,
        top_p=1.0,
    )
    torch.cuda.synchronize()
    if not orders or not orders[0]:
        raise RuntimeError(f"B2 returned no opening orders: {orders!r}")
    print("B2: base_strategy_model GPU forward ran; sample orders:", str(orders[0][:3]))

    # ---- B3: ParlAI / BART dialogue forward pass ----
    from parlai.core.agents import create_agent_from_model_file

    dialogue_model = "/app/models/cicero_imitation_bilateral_orders_prefix"
    if not os.path.exists(dialogue_model):
        raise FileNotFoundError(f"required B3 dialogue model is missing: {dialogue_model}")
    agent = create_agent_from_model_file(
        dialogue_model,
        opt_overrides={"skip_generation": False, "no_cuda": False, "gpu": 0},
    )
    dialogue_parameter = next(agent.model.parameters(), None)
    if dialogue_parameter is None or not dialogue_parameter.is_cuda:
        raise RuntimeError("B3 dialogue model did not load onto CUDA")
    agent.observe(
        {
            "text": "Hello, want to work together this game?",
            "episode_done": False,
        }
    )
    reply = agent.act()
    reply_text = reply.get("text")
    if not isinstance(reply_text, str) or not reply_text.strip():
        raise RuntimeError(f"B3 returned an invalid dialogue reply: {reply!r}")
    torch.cuda.synchronize()
    print("B3: ParlAI dialogue reply:", reply_text[:200])

    out = {"CUDA": "PASS", "B2": "PASS", "B3": "PASS"}
    print("=== B2/B3 results ===", out)
    return out


@app.local_entrypoint()
def gpu_checks() -> None:
    res = _b2_b3.remote()
    print("GPU checks:", res)
    expected = {"CUDA": "PASS", "B2": "PASS", "B3": "PASS"}
    if res != expected:
        raise RuntimeError(f"GPU validation returned an unexpected result: {res!r}")
