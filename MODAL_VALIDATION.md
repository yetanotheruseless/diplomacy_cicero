# Modal Validation for the Supported Cicero Runtime

`modal_modern.py` is the GPU/cloud acceptance harness for the same stack used
by the repository Dockerfile:

| Component | Required value |
|---|---|
| Base OS | Ubuntu 24.04 |
| Python | 3.12 |
| CPU Torch | `2.13.0+cpu` |
| GPU Torch | `2.13.0+cu130` |
| CUDA | 13.0 |
| CUDA image | `nvidia/cuda:13.0.3-cudnn-devel-ubuntu24.04` |
| NumPy | 2.4.6 |
| protobuf runtime | 7.35.1 |
| protoc | 35.1 |
| ParlAI | `1.5.1+cicero1` |

The image builder asserts these values. A function cannot report success after
silently resolving a different runtime.

## Prerequisites

1. Authenticate the Modal CLI in your own workspace.
2. Keep the Modal CLI isolated from the Cicero virtual environment. The CLI's
   own protobuf dependency is not part of the project runtime; `uvx modal` is
   the simplest separation.
3. Create/populate the `cicero-models` Volume for B1–B3.

The current gates require:

```text
no_press_human_imitation_policy.ckpt
rl_search_orders.ckpt
rl_value_function.ckpt
diplodocus_high_rl_policy.ckpt
cicero_imitation_bilateral_orders_prefix
```

B5 does not require model files.

## Required gates

Run all three commands from the repository root:

```bash
uvx modal run modal_modern.py::build_and_adjudicate
uvx modal run modal_modern.py::load_weights
uvx modal run modal_modern.py::gpu_checks
```

### B5 — Linux native build and adjudication

`build_and_adjudicate` uses the CPU image and must prove:

- exact Python, Torch CPU, NumPy, protobuf, protoc, packaging-tool, and ParlAI
  versions;
- import of the freshly compiled `fairdiplomacy.pydipcc`;
- correct adjudication of a contested move;
- progression through multiple phases; and
- a game JSON round trip.

The success sentinel is:

```text
B5 PASS: pydipcc builds on Linux x86_64 + multi-turn adjudication correct
```

### B1 — real checkpoint loading

`load_weights` uses CPU workers and must load all four required strategy
checkpoints with the modern model definitions. It exercises both the trusted
pickle read and `load_base_strategy_model_model`, and rejects missing files,
empty models, or partial results.

The success condition is:

```text
B1: 4/4 checkpoints loaded into modern nn.Module
```

### B2 — CUDA strategy inference

The GPU half of `gpu_checks` must:

- assert `torch==2.13.0+cu130` and `torch.version.cuda == "13.0"`;
- see a real Modal GPU;
- run and synchronize a float16 CUDA matrix multiplication;
- load a real strategy model onto CUDA; and
- return valid opening orders from `forward_policy`.

An import-only or userspace-only CUDA check is insufficient.

### B3 — ParlAI/BART dialogue generation

The dialogue half of `gpu_checks` must:

- load the patched ParlAI distribution;
- load the real Cicero dialogue model on CUDA;
- perform `observe` followed by `act`;
- produce non-empty generated text; and
- synchronize CUDA so deferred kernel failures surface.

The combined return value must be exactly:

```python
{"CUDA": "PASS", "B2": "PASS", "B3": "PASS"}
```

## Current validation evidence

The supported stack was validated on 2026-07-26 at source commit
[`ee5b7d1f156ea5229354317f5c9e84f793f9615d`](https://github.com/yetanotheruseless/diplomacy_cicero/commit/ee5b7d1f156ea5229354317f5c9e84f793f9615d):

| Gate | Worker | Result | Evidence |
|---|---|---|---|
| B5 | Modal CPU, Linux/x86-64 | `pydipcc` compiled and multi-turn adjudication passed | [Modal run `ap-LVsETEth4kUcyNdS7mG0ty`](https://modal.com/apps/jakemannix/main/ap-LVsETEth4kUcyNdS7mG0ty) |
| B1 | Modal CPU | All four required checkpoints loaded into `BaseStrategyModelV2` modules | [Modal run `ap-fjKSR7SsGRzEUPgMeW5AvJ`](https://modal.com/apps/jakemannix/main/ap-fjKSR7SsGRzEUPgMeW5AvJ) |
| B2 | NVIDIA A10 | CUDA 13 tensor smoke and real strategy-policy forward passed | [Modal run `ap-dBuLxOX50w7kvbye2nZHAL`](https://modal.com/apps/jakemannix/main/ap-dBuLxOX50w7kvbye2nZHAL) |
| B3 | NVIDIA A10 | The 408.5M-parameter Cicero dialogue model generated a non-empty GPU reply | [Modal run `ap-dBuLxOX50w7kvbye2nZHAL`](https://modal.com/apps/jakemannix/main/ap-dBuLxOX50w7kvbye2nZHAL) |

B1 exercised `no_press_human_imitation_policy.ckpt`,
`rl_search_orders.ckpt`, `rl_value_function.ckpt`, and
`diplodocus_high_rl_policy.ckpt`. The B2/B3 worker reported
`torch 2.13.0+cu130`, CUDA 13.0, and an available NVIDIA A10 before running the
model checks.

## Relationship to Docker CI

GitHub Actions proves that:

1. the `cpu-build` target constructs and passes
   `scripts/verify_full_build.sh --accelerator cpu`; and
2. the complete `cuda-runtime` target constructs.

GitHub-hosted runners do not prove GPU execution. B2/B3 or an equivalent
CUDA-13 GPU run is therefore required before claiming the GPU runtime works.
Conversely, Modal success does not replace the Docker CPU gate.

## Recording current evidence

For each gate, retain:

- the git commit SHA;
- the complete version banner;
- the Modal call/function identifier;
- the GPU model for B2/B3;
- the success sentinel; and
- any checkpoint names exercised.

Do not copy a PASS status from an older stack. Rerun the command whenever the
Python, PyTorch, CUDA, protobuf, protoc, native build, ParlAI patch, or
checkpoint loader changes.

## Historical validation — not a current gate

An earlier modernization experiment ran on Python 3.11 with
`torch==2.6.0+cu124`, CUDA 12.4, and an earlier protoc toolchain. It successfully
demonstrated:

- Linux/x86_64 `pydipcc` compilation and adjudication;
- loading four real strategy checkpoints;
- base-strategy-model GPU inference on an A10G; and
- a real ParlAI/BART dialogue forward pass.

Those results were valuable feasibility evidence. They do not validate Python
3.12, Torch 2.13, cu130/CUDA 13.0, or protoc 35.1 and therefore must remain
labeled historical.

## Oracle validation

After the runtime gates pass, the scale-to-zero HTTP oracle has its own
end-to-end check:

```bash
uvx modal deploy modal_serve.py
ORACLE_TOKEN='<value matching the Modal Secret>' \
  uvx modal run modal_serve.py::verify
```

That check validates health, authentication, the `/rpc` wire contract, orders
for each configured tier, and scale-to-zero behavior. See
`MODAL_ORACLE_SERVING.md`.
