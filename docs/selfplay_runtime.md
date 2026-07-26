# Optional distributed self-play runtime

Cicero's supported inference path does not need the native self-play
dependencies. Distributed RL training adds two separate native pieces:

- `fairdiplomacy.selfplay.rela`, the prioritized-replay buffer; and
- Postman, the tensor RPC transport used by rollout workers.

## RELA: canonical build and test

RELA now builds directly from the active Python environment. It no longer
depends on Postman's empty `grpc` and `pybind11` submodules, and it does not set
GPU architecture flags. PyTorch's CMake package supplies the correct CPU or
CUDA libraries and C++ ABI for the wheel installed in the environment.

Requirements:

- Python 3.12
- PyTorch 2.13.0 (CPU or CUDA 13 wheel)
- pybind11 3.x
- CMake 3.28 or newer
- Ninja and a C++20 compiler
- pytest for the Python binding tests

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

`make selfplay` builds RELA only, and `make test_selfplay_rela` runs its focused
native tests. `make test_selfplay` also runs the broader self-play Python
integration tests and therefore requires Postman RPC.

## Postman RPC: separate opt-in dependency

RELA does not use Postman. The rollout and model-server modules do, but the
checked-in Postman repository still points at 2019-era gRPC and pybind11
gitlinks that are not initialized by default. Those pins do not represent the
canonical protobuf 7.35/protoc 35 runtime and are not silently downloaded or
labeled supported by the RELA build.

Until Postman is moved to a current, explicitly pinned gRPC/protobuf toolchain,
installing it remains a separate opt-in step. A missing `postman` import in the
broader integration tests means the RPC dependency is absent; it does not
invalidate the independently built and tested RELA replay buffer.

The checked-in Postman state has been probed rather than assumed. With its two
gitlinks uninitialized:

```text
-cce8017... thirdparty/github/fairinternal/postman/third_party/grpc
-a1b71df... thirdparty/github/fairinternal/postman/third_party/pybind11
```

this configuration command:

```bash
cmake --fresh \
  -S thirdparty/github/fairinternal/postman/postman \
  -B /tmp/cicero-postman-probe \
  -DPYTHON_EXECUTABLE=/path/to/python3.12 \
  -DCMAKE_BUILD_TYPE=Release
```

fails because both dependency directories lack `CMakeLists.txt` and therefore
`pybind11_add_module` is unavailable. Before failing, the legacy CMake also
demonstrates why it is not a modern build: `FindPythonInterp` selects the
requested Python 3.12 executable while `FindPythonLibs` can independently select
a Python 3.13 library, and its bare `python` Torch probe can select a different
environment. Postman's own CMake additionally fixes C++17, a PyTorch-1.5-era
`libtorch_python.so` path, and CUDA architectures 6.0/7.0. Consequently this
branch does not claim that Postman RPC works on the canonical runtime.

CUDA builds should select architectures at deployment time through the normal
CMake/PyTorch controls. This repository intentionally does not restore the
legacy Pascal/Volta-only `TORCH_CUDA_ARCH_LIST=6.0;7.0` setting.

The focused suite is validated on macOS/arm64 and Ubuntu 24.04/x86_64 CPU. The
CUDA 13 wheel follows the same Torch-provided CMake ABI and intentionally has
no repository-wide architecture list, but this focused harness does not claim a
GPU execution test.

The reproducible Linux CPU validation is:

```bash
modal run modal_selfplay.py
```

That image pins Ubuntu 24.04, Python 3.12, GCC 13, PyTorch 2.13.0 CPU,
pybind11 3.0.4, and protobuf 7.35.1, then runs the same canonical build and test
command during image construction and again in the remote function.
