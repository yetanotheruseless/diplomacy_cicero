# Development Guide

This fork has one supported runtime. Do not restore, preserve, or add a second
compatibility path for the original Cicero environment.

## Runtime contract

| Component | Required |
|---|---|
| OS | Ubuntu 24.04 |
| Python | 3.12 |
| PyTorch | 2.13.0 |
| CPU variant | `2.13.0+cpu` |
| GPU variant | `2.13.0+cu130` |
| CUDA | 13.0 userspace; current base images use 13.0.3 |
| NumPy | 2.4.6 |
| protobuf runtime | 7.35.1 |
| protoc | 35.1 |
| pybind11 | 3.0.4 |
| ParlAI | patched `1.5.1+cicero1` from commit `5214f42…` |
| native build | C++20, CMake 3.28+, Ninja, GCC 13 |

CPU and CUDA are variants of this one contract. Compile `pydipcc` only after
the final PyTorch variant is installed.

## Canonical setup paths

Docker is authoritative:

```bash
docker build --target cpu-build -t diplomacy-cicero:cpu .
docker run --rm diplomacy-cicero:cpu \
  ./scripts/verify_full_build.sh --accelerator cpu

docker build --target cuda-runtime -t diplomacy-cicero:cuda .
docker run --rm --gpus all diplomacy-cicero:cuda \
  ./scripts/verify_full_build.sh --accelerator cuda --require-gpu
```

Local CPU development uses:

```bash
./scripts/modernize_setup.sh
source .venv-modern/bin/activate
```

Do not direct users to distro protobuf packages, unpatched ParlAI, Conda setup,
deleted Dockerfiles, or old Python/CUDA environments.

## Build order

The ordering is part of the ABI and generated-code contract:

1. Install the final CPU or cu130 PyTorch 2.13 wheel.
2. Install `.[build,dialogue,dev]`.
3. Install checksum-verified protoc 35.1 with
   `scripts/install_protoc.sh`.
4. Run `make protos`.
5. Compile `pydipcc` with `dipcc/compile.sh`.
6. Install patched ParlAI with `scripts/install_parlai.sh`.
7. Run `python -m pip check` and the runtime verifier.

Generated `conf/*_pb2.py`, `conf/*_pb2.pyi`, and `conf/*_cfgs.py` files must be
regenerated together. Never hand-edit generated files.

## Commands

```bash
# Supported inference/dialogue build and tests
make compile
make test

# Focused checks
make protos
make validate_protos
make dipcc
python test_pydipcc.py
python -m unittest unit_tests.test_full_integration
python -m pytest path/to/test_file.py -q

# Optional distributed self-play subsystem
make test_selfplay

# Style/type checks
ruff check .
ruff format --check .
./bin/pyright_local.py
```

`make test` intentionally covers the supported runtime and thread-pool tests.
The distributed self-play C++ target has additional dependencies and remains
an explicit opt-in gate.

## Cloud gates

Use an isolated Modal CLI environment so its own protobuf requirement does not
modify the Cicero runtime:

```bash
uvx modal run modal_modern.py::build_and_adjudicate
uvx modal run modal_modern.py::load_weights
uvx modal run modal_modern.py::gpu_checks
```

The three commands are the current B5, B1, and B2/B3 gates respectively. Do not
cite Python 3.11, cu124, or protoc 25 results as validation for the current
stack.

## Code map

- `fairdiplomacy/agents/` — search, rollout, and agent orchestration
- `fairdiplomacy/models/base_strategy_model/` — model definitions and checkpoint loading
- `fairdiplomacy/selfplay/` — distributed training and self-play
- `parlai_diplomacy/` — dialogue tasks, formatting, and ParlAI agents
- `dipcc/` — C++ game engine and Python bindings
- `conf/` — protobuf schemas and generated config modules
- `heyhi/` — configuration generation/runtime
- `modal_modern.py` — exact-stack cloud validation images and gates

## Engineering conventions

- Target Python 3.12 and add type annotations to changed functions.
- Format Python with Ruff using the repository configuration.
- Keep imports grouped as standard library, third-party, then project imports.
- Use descriptive errors and comments that explain why.
- Add focused pytest coverage for behavior changes.
- Preserve unrelated work in the shared worktree.
- Use `apply_patch` for hand edits and never overwrite concurrent changes.

## Native and checkpoint caveats

- `pydipcc` links against PyTorch libraries and must be rebuilt when the
  interpreter, PyTorch variant, toolchain, or architecture changes.
- Real Cicero checkpoints are trusted full pickles. Their loader must explicitly
  use `torch.load(..., weights_only=False)` under modern PyTorch.
- The pinned ParlAI source metadata is intentionally replaced by the project's
  `dialogue` extra. `scripts/install_parlai.sh` verifies the patched distribution
  version and BART import.
- Host-native macOS can be useful for CPU development, but release claims must
  be demonstrated in Ubuntu 24.04 containers or the matching Modal image.

## Documentation

When the runtime changes, update these together:

- `README.md`
- `CLAUDE.md`
- `MODERNIZATION_REPORT.md`
- `MODAL_VALIDATION.md`
- Docker and dipcc guides linked from the README

Historical experiments may remain only when they are clearly labeled
historical and not presented as supported commands or release evidence.
