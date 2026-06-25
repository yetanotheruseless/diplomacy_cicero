# Modal Validation — modern Cicero on Linux x86_64 / CUDA

Companion to `MODERNIZATION_REPORT.md`. The report proved the modernization
recipe on **macOS/arm64 (CPU)** and left four blockers explicitly "needs the
container/Modal env to validate". This document records running the **modern**
stack on **Modal (Linux x86_64, A10G GPU)** and closing all four.

**Harness:** `modal_modern.py` (committed). It builds the modern stack — Python
3.11, **torch 2.6.0**, **protobuf 7.35.1**, the rewritten `heyhi/bin/patch_protos.py`,
the pure-Python `nest` shim, and `pydipcc` compiled with the CMake/`int64_t`
fixes — and exposes three entrypoints. `pydipcc` is built against **CPU** torch
(modern `find_package(Torch)` requires the CUDA toolkit at *build* time when a
CUDA wheel is installed, which a non-GPU builder lacks), then the GPU image swaps
in the **same-version** CUDA wheel for runtime (ABI-compatible libtorch; pydipcc's
rpath re-pointed).

**Models:** real checkpoints from the existing `cicero-models` Modal Volume,
mounted at `/app/models` (verified present via `os.walk` before any GPU spend).

**Cost discipline:** B5 + B1 ran on **CPU** containers. Only B2/B3 used a **single,
short A10G** run.

---

## Results — all four blockers CLEARED

| Blocker | Where | Status | Evidence (from `modal run` output) |
|---|---|---|---|
| **B5** dipcc Linux build + adjudication | CPU | **PASS** | `[100%] Built target pydipcc` → `pydipcc.cpython-311-x86_64-linux-gnu.so`; `torch 2.6.0+cpu`, `protobuf runtime 7.35.1`; multi-turn play → `phase S1902M SC {AUSTRIA:4, ENGLAND:3, FRANCE:3, GERMANY:6, ITALY:3, RUSSIA:4, TURKEY:3}` (matches the arm64 run exactly) |
| **B1** real-weight load into modern nn.Module | CPU | **PASS (4/4)** | `torch.load(weights_only=False)` + `load_base_strategy_model_model` → `BaseStrategyModelV2`: `no_press_human_imitation_policy` 8.1M, `rl_search_orders` 8.1M, `rl_value_function` 3.5M, `diplodocus_high_rl_policy` 8.1M |
| **B2** base_strategy_model GPU inference | A10G | **PASS** | `torch 2.6.0+cu124 cuda 12.4 avail True dev NVIDIA A10`; `forward_policy(..., half_precision=True)` → valid orders for all powers, e.g. `[('A VIE - GAL','F TRI - VEN','A BUD - SER'), ('F EDI - NWG','F LON - NTH','A LVP - EDI'), ...]` |
| **B3** ParlAI/BART dialogue forward pass | A10G | **PASS** | ParlAI `create_agent_from_model_file('cicero_imitation_bilateral_orders_prefix')` → `Using CUDA`, `Loading existing model params`; `agent.act()` produced output `A BEL  A MUN` |

```
modal run modal_modern.py::build_and_adjudicate   # B5 (CPU)
modal run modal_modern.py::load_weights           # B1 (CPU)
modal run modal_modern.py::gpu_checks             # B2 + B3 (A10G)
```

### What each result proves

- **B5** — the `int64_t`/`reinterpret_cast<long*>` change (needed for the arm64
  `data_ptr<long>` symbol) **also compiles cleanly on Linux x86_64**, where
  `long == int64_t` makes it a no-op; no Linux-specific regressions. The modern
  protobuf regen + `patch_protos.py` + pure-Python `nest` shim all work on Linux,
  and adjudication is byte-for-byte consistent with the arm64 run.

- **B1** — the `weights_only=False` fix (`load_model.py`) lets torch ≥2.6
  deserialize Cicero's **full-pickle** checkpoints (they embed an `args`
  `TrainTask` config object — note `'args'` in the top-level keys — alongside
  `'model'` weights). The deserialized state_dict loads into the **modern**
  `BaseStrategyModelV2` `nn.Module` built from the modern protobuf-backed config.
  This is the end-to-end proof that modern-protobuf config + modern-torch +
  modern model code interoperate with **real production weights**.

- **B2** — the GPU-only **fp16** path (`half_precision=True`) that could not run
  on CPU executes on the modern CUDA wheel (cu124 / CUDA 12.4) on an A10G.

- **B3** — ParlAI 1.5.1 (the pinned commit), suspected to be the hard wall, not
  only **imports** on Python 3.11 (per the report) but runs a **real dialogue
  forward pass** on CUDA with a real Cicero dialogue checkpoint. The only gaps
  were ordinary pip deps (`regex`, `sentencepiece`, `ftfy`, `emoji`).

---

## Notes / honesty caveats

- `pydipcc` is built against CPU torch and run against the same-version CUDA
  wheel (standard Cicero pattern; ABI-compatible since pydipcc only links
  `libtorch_cpu.so`/`libc10.so`). A direct CUDA-toolkit build of pydipcc was not
  attempted — it isn't needed (pydipcc has no CUDA kernels).
- B3 used `cicero_imitation_bilateral_orders_prefix`, an **orders-prefix**
  dialogue model, so its generated tokens are order strings (`A BEL  A MUN`) —
  correct for that checkpoint. A free-text message model would emit prose; the
  mechanism (load on CUDA + `act()` generation) is identical and proven.
- A benign `parlai 1.5.1 requires gitdb2` pip warning appears (wandb/git
  integration, unused here) and does not affect the forward pass.
- Distributed RL self-play (`fairdiplomacy/selfplay/cc`, postman/grpc) remains
  out of scope (B5 note in the report) — not needed for agent play/inference.

## Verdict

**All four "needs-the-container" blockers (B1, B2, B3, B5) are CLEARED on real
Modal Linux x86_64 + CUDA, with `modal run` logs as evidence.** Combined with the
arm64 work, the modern stack (Python 3.11 / torch 2.6 / protobuf 7.35 / ParlAI
pinned-commit) **builds, loads real weights, and runs both strategy-model GPU
inference and ParlAI dialogue generation.** Full modernization is **not** blocked
by a C++, protobuf, or ParlAI wall.
