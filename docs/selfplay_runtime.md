# Optional distributed self-play runtime

Cicero's supported inference path does not need the native self-play
dependencies. Distributed RL training adds two separate native pieces:

- `fairdiplomacy.selfplay.rela`, the prioritized-replay buffer; and
- Postman, the tensor RPC transport used by rollout workers.

## RELA: canonical build and test

RELA now builds directly from the active Python environment. It no longer
depends on Postman's removed vendored `grpc` and `pybind11` gitlinks, and it
does not set GPU architecture flags. PyTorch's CMake package supplies the
correct CPU or CUDA libraries and C++ ABI for the wheel installed in the
environment.

Requirements:

- Python 3.12
- PyTorch 2.13.0 (CPU or CUDA 13 wheel)
- pybind11 3.x
- CMake 3.28 or newer
- Ninja and a C++20 compiler
- pytest for the Python binding tests

The broader distributed-training integration tests additionally require the
`training` extra:

```bash
python -m pip install -e ".[training]"
```

From the repository root, the canonical command is:

```bash
./scripts/build_selfplay.sh
```

It configures an out-of-tree Release build, creates
`fairdiplomacy/selfplay/rela.*`, runs the standalone C++ replay test through
CTest, and runs Python tests for sampling, asynchronous insertion, priority
updates, safe serialization, and save/load after ring-buffer eviction.

The binding smoke uses the production-qualified
`fairdiplomacy.selfplay.rela` import when `pydipcc` is present. In a focused
RELA-only build, `fairdiplomacy.__init__` cannot load the separately built
`pydipcc` extension, so the harness explicitly falls back to importing the same
RELA binary directly; application code continues to use the qualified path.

Replay checkpoints accept at most 4,096 tensor fields, 64 KiB per field name,
and 512 MiB per serialized sample payload. The writer and reader enforce the
same limits before allocating or emitting an incompatible checkpoint.

The interpreter and build directory can be selected without changing the
source tree:

```bash
CICERO_SELFPLAY_PYTHON=/path/to/python3.12 \
CICERO_SELFPLAY_BUILD_DIR=/tmp/cicero-selfplay-build \
N_SELFPLAY_JOBS=8 \
./scripts/build_selfplay.sh
```

`make selfplay` builds RELA only, `make postman` builds Postman only, and the
corresponding `make test_selfplay_rela` and `make test_postman` targets run their
focused gates. `make test_selfplay` builds both extensions and then runs the
broader rollout/model-server integration tests.

## Postman RPC: canonical tensor transport

RELA does not use Postman, but distributed rollout and model-server processes
do. Postman now builds on the same Python 3.12, PyTorch 2.13, pybind11 3, and
C++20 contract as the rest of Cicero. Its native dependency line is gRPC 1.83.0
at commit `c876f4da50f7da2f331888b88b2a7243514139fe` and protobuf/protoc
35.1 at commit `35cd01f9fe9afbeea38cc7b979a3b6bfcde82c03`.

The obsolete gRPC 1.20 and pybind11 gitlinks were removed. The canonical helper
clones the exact gRPC release into an ignored out-of-tree cache, initializes
only its pinned build dependencies, rejects dirty or mismatched caches, and
uses scikit-build-core to produce a native platform wheel:

```bash
./scripts/build_postman.sh
```

The focused gate builds the C++20 RPC core and every public header with warnings
as errors, generates the wire code with gRPC's source-built protoc 35.1, runs
CTest, builds and installs the platform wheel, verifies its relative Torch
RPATH and a clean-target import, and runs the real extension-backed Python
lifecycle/concurrency suite.

The interpreter and caches can be selected explicitly:

```bash
CICERO_POSTMAN_PYTHON=/path/to/python3.12 \
CICERO_POSTMAN_BUILD_DIR=/tmp/cicero-postman-build \
CICERO_POSTMAN_DEPS_DIR=/tmp/cicero-postman-deps \
N_POSTMAN_JOBS=8 \
./scripts/build_postman.sh
```

The helper is the supported source-build frontend. It deliberately disables
PEP 517 build isolation after verifying the exact active PyTorch wheel so a
CPU or cu130 build cannot silently resolve a different Torch flavor.

`ComputationQueue` admits at most 64 pending batches by default and rejects
overflow instead of retaining an unbounded tensor backlog. The limit is
configurable with `max_pending_batches`. `AsyncClient` similarly bounds active
and queued calls, while `close()` rejects queued calls and cancels active
contexts. A custom `max_concurrent_calls` must be at least the batch size of a
server function that uses `wait_till_full=True`.

Postman's transport serializes tensors through CPU memory. GPU model servers
receive CPU inputs and explicitly move them to the selected CUDA device before
inference. No Pascal/Volta architecture list is embedded; CUDA builds inherit
the architecture policy of the installed PyTorch wheel and deployment.

The obsolete Postman-local replay buffer was removed. Cicero has one supported
replay implementation: `fairdiplomacy.selfplay.rela`.

The focused suite is validated on macOS/arm64 with a macOS 14.0 wheel deployment
target and on Ubuntu 24.04/x86_64 CPU. The Docker `cuda-build` stage also builds
and tests the extension against
`torch==2.13.0+cu130`, and the runtime stage imports that exact wheel. This is
an ABI/build gate rather than a Postman GPU-execution claim because the wire
transport is CPU-based.

The reproducible Linux CPU validation is:

```bash
modal run modal_selfplay.py
```

That image pins Ubuntu 24.04, Python 3.12, GCC 13, PyTorch 2.13.0 CPU,
pybind11 3.0.4, and protobuf 7.35.1. It builds and tests both RELA and Postman
during image construction, then repeats both focused test gates in the remote
function.
