"""
Validate the MODERNIZED Cicero stack on Modal (Linux x86_64 [+ CUDA]).

This is the Linux/x86_64 counterpart to scripts/modernize_setup.sh (which proved
the recipe on macOS/arm64). It builds the *modern* stack — Python 3.11, torch
2.x, protobuf 7.x, the rewritten heyhi patch_protos.py, the pure-Python `nest`
shim, and pydipcc compiled with the CMake/int64_t fixes — and runs the blocker
checks that could not execute on a CPU/arm64 laptop:

  B5  pydipcc builds on Linux x86_64 + multi-turn adjudication correct   (CPU)
  B1  torch.load(weights_only=False) a real base_strategy_model ckpt and
      load it into the modern nn.Module definitions                      (CPU)
  B2  base_strategy_model GPU inference (modern CUDA torch)               (GPU)
  B3  one ParlAI/BART dialogue forward pass                              (GPU)

Cost discipline: everything except B2/B3 runs on CPU. The GPU function is short.

Entrypoints:
  modal run modal_modern.py::build_and_adjudicate     # B5 (CPU)
  modal run modal_modern.py::load_weights             # B1 (CPU)
  modal run modal_modern.py::gpu_checks               # B2 (+B3 best-effort, GPU)
"""
import pathlib

import modal

REPO = pathlib.Path(__file__).parent

IGNORE = [
    ".git", ".venv-modern", "models", "models_encrypted", ".cicero_model_stage",
    "diplomacy_experiments", "*.log", "**/*.so", "dipcc_pkg",
    "dipcc/build", "**/__pycache__", "*.bak", "wandb",
    "modal_app.py", "modal_modern.py", "*.md", "modal_cicero_*.json",
    # Drop the generated protos from context; we regenerate them in-image with
    # the modern protoc so the format matches the modern runtime exactly.
    "conf/*_pb2.py", "conf/*_pb2.pyi", "conf/*_cfgs.py", "conf/*_cfgs.pyi",
]

# Modern torch CUDA wheels (cu124 has cp311 x86_64 wheels). The wheel bundles the
# CUDA runtime; Modal injects the driver. We build pydipcc against this same
# wheel (its libtorch is the ABI pydipcc links), so no build/runtime torch swap.
TORCH_VER = "2.6.0"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_CU_INDEX = "https://download.pytorch.org/whl/cu124"

# The dependency set proven locally (scripts/modernize_setup.sh), minus torch.
PIP_DEPS = [
    "protobuf>=5.0", "mypy-protobuf>=3.5", "pybind11>=2.10",
    "numpy>=1.26,<2.3",
    "tabulate", "joblib", "pyarrow", "tqdm", "termcolor", "colored", "pygtrie",
    "dacite", "attrs", "python-dateutil", "psutil",
    "iopath", "requests", "scikit-learn", "subword-nmt", "setuptools<81",
    "pytest", "pyyaml",
]

# ParlAI BART dialogue forward-pass runtime deps (B3). Kept in a separate layer
# (added after the pydipcc build) so adding them doesn't invalidate the slow
# C++ build cache.
PARLAI_RUNTIME_DEPS = ["regex", "sentencepiece", "ftfy", "emoji"]

PARLAI_PIN = (
    "git+https://github.com/facebookresearch/ParlAI.git"
    "@5214f42a2058ef335f91f5afe66b2bd9ebfb2fbe"
)


def _build_pydipcc_cmds():
    """Regen protos (modern protoc) + heyhi patch, then compile pydipcc."""
    return [
        # Modern protoc from the Debian repo; regenerate + heyhi-patch the protos.
        "cd /app && rm -f conf/*_pb2.py conf/*_pb2.pyi conf/*_cfgs.py conf/*_cfgs.pyi || true",
        "cd /app && protoc conf/*.proto --python_out=./ --mypy_out=./",
        "cd /app && PYTHONPATH=/app python heyhi/bin/patch_protos.py "
        "conf/agents_pb2.py conf/common_pb2.py conf/misc_pb2.py conf/conf_pb2.py",
        # Compile pydipcc against the in-image torch using our patched CMakeLists.
        "cd /app/dipcc && rm -rf build && mkdir -p build && cd build && "
        "PYBIND_DIR=$(python -c 'import pybind11;print(pybind11.get_cmake_dir())') && "
        "TORCH_CM=$(python -c 'import torch;print(torch.utils.cmake_prefix_path)') && "
        "cmake -DCMAKE_BUILD_TYPE=Release "
        "-DPYTHON_EXECUTABLE=$(which python) "
        "-Dpybind11_DIR=\"$PYBIND_DIR\" "
        "-DCMAKE_PREFIX_PATH=\"$TORCH_CM;$PYBIND_DIR\" .. && "
        "make -j$(nproc) pydipcc && "
        "cp dipcc/python/pydipcc*.so /app/fairdiplomacy/ && "
        "ls -la /app/fairdiplomacy/pydipcc*.so",
    ]


TORCH_LIB = "/usr/local/lib/python3.11/site-packages/torch/lib"


def _base_image(want_cuda: bool):
    """Build pydipcc against CPU torch (find_package(Torch) needs no CUDA toolkit
    at build time), then — for the GPU image — swap in the SAME-version CUDA wheel
    for runtime. Same torch version => ABI-compatible libtorch, which is all
    pydipcc links; we point pydipcc's rpath at the (swapped) torch/lib."""
    img = (
        modal.Image.from_registry("python:3.11-slim")
        .apt_install(
            "build-essential", "cmake", "git", "wget", "curl", "patchelf",
            "protobuf-compiler",
            "libgoogle-glog-dev", "libgflags-dev",
        )
        # Build-time torch is always the CPU wheel.
        .pip_install(f"torch=={TORCH_VER}+cpu", index_url=TORCH_CPU_INDEX)
        .pip_install(*PIP_DEPS)
        .pip_install(PARLAI_PIN, extra_options="--no-deps")
        .add_local_dir(str(REPO), "/app", copy=True, ignore=IGNORE)
    )
    for cmd in _build_pydipcc_cmds():
        img = img.run_commands(cmd)
    if want_cuda:
        # Swap to the CUDA wheel (same version => ABI-compatible) and re-point
        # pydipcc's rpath so it loads the CUDA torch's libtorch_cpu.so/libc10.so.
        img = (
            img.pip_install(*PARLAI_RUNTIME_DEPS)
            .pip_install(
                f"torch=={TORCH_VER}", index_url=TORCH_CU_INDEX,
                extra_options="--force-reinstall",
            )
            .run_commands(
                f"patchelf --set-rpath {TORCH_LIB} /app/fairdiplomacy/pydipcc*.so && "
                "python -c 'import torch;print(\"runtime torch\",torch.__version__,torch.version.cuda)'"
            )
        )
    return img.env({
        "PYTHONPATH": "/app",
        "HH_EXP_DIR": "/app/diplomacy_experiments",
        "LD_LIBRARY_PATH": TORCH_LIB,
    })


cpu_image = _base_image(want_cuda=False)
gpu_image = _base_image(want_cuda=True)

app = modal.App("cicero-modern")
models_volume = modal.Volume.from_name("cicero-models", create_if_missing=True)
VOL = {"/app/models": models_volume}


# --------------------------------------------------------------------------- B5
@app.function(image=cpu_image, cpu=4.0, timeout=900)
def _b5():
    import torch
    import fairdiplomacy
    from fairdiplomacy.pydipcc import Game

    print("torch", torch.__version__, "cuda?", torch.cuda.is_available())
    import google.protobuf
    print("protobuf runtime", google.protobuf.__version__)

    g = Game()
    assert g.current_short_phase == "S1901M"
    g.set_orders("AUSTRIA", ["A VIE - GAL", "A BUD - SER", "F TRI - ALB"])
    g.set_orders("RUSSIA", ["A WAR - GAL", "A MOS - UKR", "F SEV - BLA", "F STP/SC - BOT"])
    g.set_orders("GERMANY", ["A BER - KIE", "A MUN - RUH", "F KIE - DEN"])
    g.process()
    assert g.current_short_phase == "F1901M", g.current_short_phase
    units = g.get_state()["units"]
    # VIE-GAL vs WAR-GAL bounce: both armies stay put.
    assert "A VIE" in units["AUSTRIA"] and "A WAR" in units["RUSSIA"], units
    g.set_orders("GERMANY", ["A KIE - HOL", "A RUH - BEL", "F DEN - SWE"])
    g.process()  # F1901M
    g.process()  # builds/retreats -> next movement
    centers = {p: len(v) for p, v in g.get_state()["centers"].items() if v}
    print("phase", g.current_short_phase, "SC", centers)
    # JSON round-trip
    g2 = Game.from_json(g.to_json())
    assert g2.current_short_phase == g.current_short_phase
    print("B5 PASS: pydipcc builds on Linux x86_64 + multi-turn adjudication correct")
    return True


@app.local_entrypoint()
def build_and_adjudicate():
    _b5.remote()


# --------------------------------------------------------------------------- B1
@app.function(image=cpu_image, volumes=VOL, cpu=4.0, timeout=1200)
def _b1(ckpts):
    """Load real base_strategy_model checkpoints with weights_only=False and
    instantiate the modern nn.Module from each (the load_model.py path)."""
    import os
    import torch
    import fairdiplomacy  # noqa: ensures pydipcc loads

    print("torch", torch.__version__)
    results = {}
    for rel in ckpts:
        path = f"/app/models/{rel}"
        if not os.path.exists(path):
            results[rel] = f"MISSING ({path})"
            print(rel, "-> MISSING")
            continue
        try:
            # B1 core: torch>=2.6 defaults weights_only=True; Cicero ckpts are
            # full pickles, so we must pass weights_only=False.
            blob = torch.load(path, map_location="cpu", weights_only=False)
            keys = list(blob.keys()) if isinstance(blob, dict) else type(blob).__name__
            print(rel, "raw load OK; top-level keys:", keys if isinstance(keys, list) else keys)

            # Now go through the real loader, which builds the modern nn.Module
            # and loads the state_dict into it.
            from fairdiplomacy.models.base_strategy_model.load_model import (
                load_base_strategy_model_model,
            )
            model = load_base_strategy_model_model(path, map_location="cpu", eval=True)
            n_params = sum(p.numel() for p in model.parameters())
            print(rel, f"-> nn.Module {type(model).__name__} loaded, {n_params/1e6:.1f}M params")
            results[rel] = f"OK {type(model).__name__} {n_params/1e6:.1f}M"
        except Exception as e:
            import traceback
            traceback.print_exc()
            results[rel] = f"FAIL {type(e).__name__}: {str(e)[:200]}"
    print("=== B1 results ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    return results


@app.local_entrypoint()
def load_weights():
    ckpts = [
        "no_press_human_imitation_policy.ckpt",
        "rl_search_orders.ckpt",
        "rl_value_function.ckpt",
        "diplodocus_high_rl_policy.ckpt",
    ]
    res = _b1.remote(ckpts)
    ok = sum(1 for v in res.values() if str(v).startswith("OK"))
    print(f"B1: {ok}/{len(res)} checkpoints loaded into modern nn.Module")


# ------------------------------------------------------------------------- B2/B3
@app.function(image=gpu_image, volumes=VOL, gpu="A10G", timeout=1200)
def _b2_b3():
    import os
    import torch
    import fairdiplomacy  # noqa
    from fairdiplomacy.pydipcc import Game

    print("torch", torch.__version__, "cuda", torch.version.cuda,
          "avail", torch.cuda.is_available(),
          "dev", torch.cuda.get_device_name(0) if torch.cuda.is_available() else None)

    out = {}

    # ---- B2: base_strategy_model GPU inference ----
    try:
        ckpt = "/app/models/no_press_human_imitation_policy.ckpt"
        if not os.path.exists(ckpt):
            ckpt = "/app/models/rl_search_orders.ckpt"
        # The wrapper builds the modern nn.Module, moves it to CUDA, and (with
        # half_precision=True) exercises the GPU-only fp16 path that broke on CPU.
        from fairdiplomacy.agents.base_strategy_model_wrapper import BaseStrategyModelWrapper
        wrapper = BaseStrategyModelWrapper(ckpt, device="cuda", half_precision=True)
        g = Game()
        orders, logits = wrapper.forward_policy(
            [g], has_press=False, agent_power=None, temperature=1.0, top_p=1.0,
        )
        print("B2: base_strategy_model GPU forward ran; sample orders:",
              str(orders[0][:3]) if orders and orders[0] else orders)
        out["B2"] = "PASS"
    except Exception as e:
        import traceback
        traceback.print_exc()
        out["B2"] = f"FAIL {type(e).__name__}: {str(e)[:200]}"

    # ---- B3: ParlAI / BART dialogue forward pass (best-effort) ----
    try:
        from parlai.core.agents import create_agent_from_model_file
        dialogue_model = "/app/models/cicero_imitation_bilateral_orders_prefix"
        if os.path.exists(dialogue_model):
            agent = create_agent_from_model_file(
                dialogue_model, opt_overrides={"skip_generation": False, "no_cuda": False}
            )
            agent.observe({"text": "Hello, want to work together this game?",
                           "episode_done": False})
            reply = agent.act()
            print("B3: ParlAI dialogue reply:", str(reply.get("text"))[:200])
            out["B3"] = "PASS"
        else:
            out["B3"] = f"SKIP (no dialogue model at {dialogue_model})"
    except Exception as e:
        import traceback
        traceback.print_exc()
        out["B3"] = f"FAIL {type(e).__name__}: {str(e)[:200]}"

    print("=== B2/B3 results ===", out)
    return out


@app.local_entrypoint()
def gpu_checks():
    res = _b2_b3.remote()
    print("GPU checks:", res)
