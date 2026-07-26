# Diplomacy Cicero and Diplodocus

This fork runs Meta/FAIR's Cicero and Diplodocus Diplomacy agents on one
modern runtime. It contains inference and training code associated with:

- ["Human-Level Play in the Game of Diplomacy by Combining Language Models
  with Strategic Reasoning"](https://www.science.org/doi/10.1126/science.ade9097)
- ["Mastering the Game of No-Press Diplomacy via Human-Regularized
  Reinforcement Learning and Planning"](https://arxiv.org/abs/2210.05492)

## Supported runtime

There is one supported software stack. CPU and GPU are two builds of the same
stack, not separate compatibility tracks.

| Component | Supported version |
|---|---|
| Operating system | Ubuntu 24.04 |
| Python | 3.12 |
| PyTorch | 2.13.0 |
| CPU wheel | `torch==2.13.0+cpu` |
| GPU wheel | `torch==2.13.0+cu130` |
| CUDA userspace | 13.0 (`nvidia/cuda:13.0.3`) |
| NumPy | 2.4.6 |
| protobuf runtime | 7.35.1 |
| protobuf compiler | protoc 35.1 |
| pybind11 | 3.0.4 |
| ParlAI | Cicero-compatible commit `5214f42…`, patched and packaged as `1.5.1+cicero1` |
| C++ | C++20, CMake 3.28+, GCC 13 |

Do not install protobuf or ParlAI from unpinned system/package-manager
defaults. Generated protobuf modules, `pydipcc`, PyTorch, and ParlAI must all
come from this version contract.

## Quick start with Docker

Docker is the supported development and validation path. The repository has
one multi-stage [`Dockerfile`](Dockerfile):

- `cpu-build` contains the complete CPU development runtime.
- `cuda-runtime` contains the complete CUDA 13.0 runtime, including the
  Postman extension built against the cu130 PyTorch ABI.

Build and verify the CPU image:

```bash
docker build --target cpu-build -t diplomacy-cicero:cpu .
docker run --rm diplomacy-cicero:cpu \
  ./scripts/verify_full_build.sh --accelerator cpu
```

The equivalent Compose workflow is:

```bash
docker compose build diplomacy
docker compose --profile test run --rm diplomacy_test
docker compose run --rm diplomacy bash
```

On a Linux host with an NVIDIA driver compatible with CUDA 13.0, build and
verify the GPU image:

```bash
docker build --target cuda-runtime -t diplomacy-cicero:cuda .
docker run --rm --gpus all diplomacy-cicero:cuda \
  ./scripts/verify_full_build.sh --accelerator cuda --require-gpu
```

Docker Desktop on macOS can build and run the Ubuntu CPU image but does not
pass through an NVIDIA GPU. See [README_MACOS.md](README_MACOS.md).

## Local CPU development

Host-native setup is a developer convenience; Ubuntu 24.04 remains the release
runtime. Install Git, Make, `uv`, CMake 3.28+, Ninja, a C++20 compiler, glog,
gflags, `curl`, and `unzip`, then run:

```bash
./scripts/modernize_setup.sh
source .venv-modern/bin/activate
```

The setup script creates a Python 3.12 environment, installs checksum-verified
protoc 35.1, installs the final CPU PyTorch wheel and project extras,
regenerates protobuf modules, builds `pydipcc`, installs the patched ParlAI
wheel, and runs smoke tests.

For manual work inside an already prepared environment:

```bash
make protos
make dipcc
make test
```

Useful focused checks:

```bash
python scripts/validate_protobuf.py
python test_pydipcc.py
python -m unittest unit_tests.test_full_integration
python -m pytest path/to/test_file.py -q
```

`make test` covers the supported inference and dialogue runtime. The optional
RELA replay extension is built and tested separately:

```bash
make test_selfplay_rela
```

Postman tensor RPC is built and tested separately with:

```bash
make test_postman
```

The Postman gate produces a platform wheel, verifies its relative Torch RPATH
and macOS 14 deployment target where applicable, and exercises bounded
queueing, cancellation, lifecycle, and wire serialization. The Docker CUDA
build repeats that native build against the cu130 wheel; Postman still carries
RPC tensors through CPU memory and model servers move them to CUDA explicitly.

The broader `make test_selfplay` target builds RELA and Postman, runs both
focused native/Python gates, and then runs the rollout/model-server integration
tests.

## Why ParlAI is installed separately

Cicero depends on a specific 2021 ParlAI source revision. Its original package
metadata pins packages that cannot coexist with Python 3.12, NumPy 2.4, and
modern PyTorch. The project therefore:

1. installs dialogue dependencies from the `dialogue` extra in
   [`pyproject.toml`](pyproject.toml);
2. fetches the exact ParlAI commit;
3. applies [`patches/parlai-modern-runtime.patch`](patches/parlai-modern-runtime.patch);
4. installs the patched `1.5.1+cicero1` wheel without the obsolete dependency
   metadata; and
5. runs `pip check` and a BART import check.

Use:

```bash
./scripts/install_parlai.sh
```

Do not replace this with a direct `pip install parlai` or an unpatched Git URL.

## Cloud and GPU validation

The Modal harness builds the same Ubuntu 24.04 stack with either the CPU or
cu130 wheel. Keep the Modal CLI in a separate tool environment from the
project runtime, then run:

```bash
uvx modal run modal_modern.py::build_and_adjudicate
uvx modal run modal_modern.py::load_weights
uvx modal run modal_modern.py::gpu_checks
uvx modal run modal_selfplay.py
```

These gates validate:

- Linux/x86_64 `pydipcc` build and multi-turn adjudication;
- loading real strategy checkpoints under PyTorch 2.13;
- a real CUDA 13.0 tensor kernel and strategy-model forward pass; and
- a ParlAI/BART dialogue forward pass on a GPU; and
- Linux/x86-64 RELA and Postman native-wheel build/test gates.

See [MODAL_VALIDATION.md](MODAL_VALIDATION.md) for prerequisites and acceptance
criteria. Earlier Python 3.11/cu124 experiments are historical evidence only
and are not release gates for this stack.

## Model files

Model weights are distributed separately under CC-BY-NC 4.0:

```bash
bash bin/download_model_files.sh <PASSWORD>
```

The download is large and produces the local `models/` tree used by agent
configs. For Modal validation, upload the required files to the
`cicero-models` Volume before running checkpoint or GPU gates.

## Code map

- [`fairdiplomacy/agents`](fairdiplomacy/agents) — strategic agents and search
- [`fairdiplomacy/models/base_strategy_model`](fairdiplomacy/models/base_strategy_model)
  — strategy-model architecture and loading
- [`parlai_diplomacy`](parlai_diplomacy) — dialogue tasks, agents, and formatting
- [`dipcc`](dipcc) — C++ game engine and pybind11 bindings
- [`conf`](conf) — protobuf schemas and experiment/agent configurations
- [`heyhi`](heyhi) — configuration generation and runtime
- [`fairdiplomacy/selfplay`](fairdiplomacy/selfplay) — distributed training and self-play

The main task entry point is `run.py`. For example:

```bash
python run.py --adhoc \
  --cfg conf/c01_ag_cmp/cmp.prototxt \
  Iagent_one=agents/cicero.prototxt \
  Iagent_six=agents/ablations/cicero_imitation_only.prototxt \
  power_one=TURKEY
```

The HeyHi configuration system is described in
[`heyhi/README.md`](heyhi/README.md). Direct `pydipcc` usage is covered in
[`README_DIRECT_USAGE.md`](README_DIRECT_USAGE.md).

## Documentation

- [Docker guide](DOCKER_GUIDE.md)
- [dipcc build notes](DIPCC_BUILD_NOTES.md)
- [dipcc/Python integration](docs/dipcc_integration.md)
- [optional RELA self-play runtime](docs/selfplay_runtime.md)
- [modernization status](MODERNIZATION_REPORT.md)
- [Modal validation gates](MODAL_VALIDATION.md)
- [Modal oracle serving](MODAL_ORACLE_SERVING.md)

## Data and training scope

Redacted games and visualizations are in
[`data/cicero_redacted_games`](data/cicero_redacted_games). The human training
datasets used for the original supervised dialogue and policy training are not
included. Pretrained weights are available separately, and the original
Slurm-oriented training configurations remain in `conf/`.

## License

Code is MIT licensed except for
[`fairdiplomacy_external`](fairdiplomacy_external), which has its own license.
See [LICENSE.md](LICENSE.md).

Model weights use
[CC-BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/legalcode); see
[LICENSE_FOR_MODEL_WEIGHTS.txt](LICENSE_FOR_MODEL_WEIGHTS.txt).
