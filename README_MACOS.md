# Running Cicero from macOS

The supported runtime remains Ubuntu 24.04. On macOS, run the CPU Docker target
instead of creating a separate macOS dependency stack.

## Requirements

- Docker Desktop
- enough Docker memory for the workload
- model files in `models/` when running real agents

Docker Desktop does not expose an NVIDIA GPU to Linux containers. Use this path
for builds, tests, engine work, and CPU inference; use a Linux CUDA host or the
Modal gates for GPU validation.

## Build and verify

On Apple Silicon, `linux/amd64` gives the same architecture used by CI and
Modal, at the cost of emulation:

```bash
docker build \
  --platform linux/amd64 \
  --target cpu-build \
  -t diplomacy-cicero:cpu .

docker run --rm \
  --platform linux/amd64 \
  diplomacy-cicero:cpu \
  ./scripts/verify_full_build.sh --accelerator cpu
```

Open a shell with model files mounted read-only:

```bash
docker run --rm -it \
  --platform linux/amd64 \
  -v "$PWD/models:/app/models:ro" \
  diplomacy-cicero:cpu bash
```

The container still runs the exact supported versions: Python 3.12, Torch
2.13.0 CPU, NumPy 2.4.6, protobuf 7.35.1, protoc 35.1, and patched ParlAI.

## Run an engine smoke test

```bash
docker run --rm \
  --platform linux/amd64 \
  diplomacy-cicero:cpu \
  python test_pydipcc.py
```

## Run a configured task

```bash
docker run --rm -it \
  --platform linux/amd64 \
  -v "$PWD/models:/app/models:ro" \
  diplomacy-cicero:cpu \
  python run.py --adhoc \
    --cfg conf/c01_ag_cmp/cmp.prototxt \
    Iagent_one=agents/cicero.prototxt \
    Iagent_six=agents/ablations/cicero_imitation_only.prototxt \
    power_one=TURKEY
```

Full Cicero model loading is memory intensive and CPU inference is slow.
Allocate substantial Docker memory or run on a CUDA 13.0 Linux worker.

## Optional host-native development

`scripts/modernize_setup.sh` supports a local CPU development environment when
Homebrew supplies CMake, Ninja, glog, and gflags:

```bash
brew install cmake ninja glog gflags uv
./scripts/modernize_setup.sh
source .venv-modern/bin/activate
```

This is useful for focused development but is not a second release target.
Demonstrate release behavior in the Ubuntu container.

## Model files

Download/decrypt the separately licensed weights before running real agents:

```bash
bash bin/download_model_files.sh <PASSWORD>
```

The download is large. Docker images intentionally do not embed it.
