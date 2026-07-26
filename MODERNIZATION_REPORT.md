# Cicero Modernization Report

## Status

This fork has migrated Cicero to one supported runtime:

| Component | Current contract |
|---|---|
| OS | Ubuntu 24.04 |
| Python | 3.12 |
| PyTorch | 2.13.0 (`+cpu` or `+cu130`) |
| CUDA | 13.0 userspace; 13.0.3 container images |
| NumPy | 2.4.6 |
| protobuf runtime | 7.35.1 |
| protoc | 35.1 |
| pybind11 | 3.0.4 |
| ParlAI | patched `1.5.1+cicero1` |
| C++ build | C++20, CMake 3.28+, Ninja, GCC 13 |

The original Python, PyTorch, CUDA, protobuf, and compiler environment is not a
supported fallback. CPU and CUDA images are variants of the table above.

## Outcome

The modernization removed the three assumed migration blockers:

1. modern protoc output now feeds HeyHi's frozen configuration layer;
2. `dipcc` builds as a Python 3.12 extension against PyTorch 2.13; and
3. the Cicero-compatible ParlAI source runs with the modern project dependency
   set after a small source/metadata patch.

The repository now has:

- one multi-stage `Dockerfile` for CPU and CUDA;
- Python dependency metadata in `pyproject.toml`;
- checksum-verified protoc installation;
- canonical protobuf generation through `make protos`;
- CMake-based `pydipcc` compilation using the active interpreter and PyTorch;
- a patched, versioned ParlAI installation path;
- fail-closed runtime verification; and
- matching local, Docker, CI, and Modal stack declarations.

## Modernization details

### Protobuf and HeyHi

Modern protoc no longer emits the Python source layout that the original
text-scraping `heyhi/bin/patch_protos.py` expected. Message discovery and
frozen-config attachment were updated for descriptor/builder-generated modules.

The supported generation path is:

```bash
PROTOC_PREFIX="$PWD/.venv-modern" ./scripts/install_protoc.sh
make protos
python scripts/validate_protobuf.py
python -m pytest heyhi/tests/test_conf.py -q
```

The installer is pinned to protoc 35.1 and verifies the official archive
checksum.

The protobuf Python runtime is independently pinned to 7.35.1. Compiler and
runtime versions are both asserted by the verification scripts.

### `dipcc` and `pydipcc`

The native build now uses:

- Python 3.12's CMake package and development module;
- pybind11 3 config mode;
- the active PyTorch 2.13 CMake package and `torch_python`;
- glog/gflags imported targets;
- position-independent C++20; and
- Ninja through `dipcc/compile.sh`.

Build after installing the final PyTorch wheel:

```bash
PYDIPCC_OUT_DIR="$PWD/fairdiplomacy" \
N_DIPCC_JOBS=4 \
./dipcc/compile.sh
```

The extension is ABI-coupled to the Python interpreter, PyTorch variant,
architecture, and native toolchain. A CPU-built extension is not promoted into
the CUDA image; each image compiles against its final wheel.

### RELA self-play replay

The optional `fairdiplomacy.selfplay.rela` prioritized-replay extension now
builds directly against the same Python 3.12, PyTorch 2.13, pybind11 3, and
C++20 contract. It no longer reaches through Postman's legacy submodules for
pybind11 or GoogleTest and does not hard-code CUDA architectures.

The canonical build and focused test command is:

```bash
./scripts/build_selfplay.sh
```

Postman tensor RPC now builds on the same runtime contract. The old gRPC 1.20
and pybind11 gitlinks were removed in favor of an exact gRPC 1.83.0 checkout
whose protobuf 35.1 source pin is verified before every build. A
scikit-build-core backend produces a platform-tagged native wheel; the canonical
gate verifies that wheel's relative Torch RPATH, macOS 14 deployment target
where applicable, and clean-target import; it then runs the C++20/header tests
and the extension-backed Python concurrency and lifecycle suite. Queue backlogs
and asynchronous calls are bounded; shutdown cancels active RPC contexts and
deterministically rejects queued work. See
[`docs/selfplay_runtime.md`](docs/selfplay_runtime.md) for the complete
distributed self-play contract.

### Python and checkpoint loading

The project requires Python 3.12 and pins the ABI-sensitive packages. Modern
PyTorch changed the default behavior of `torch.load`; trusted Cicero
checkpoints therefore use `weights_only=False` explicitly.

### ParlAI

The Cicero code relies on ParlAI commit
`5214f42a2058ef335f91f5afe66b2bd9ebfb2fbe`. Its original dependency metadata
pulls an obsolete scientific-Python stack and archived packages.

`scripts/install_parlai.sh` now:

1. fetches that exact commit;
2. applies `patches/parlai-modern-runtime.patch`;
3. builds/installs distribution version `1.5.1+cicero1` without the obsolete
   dependency metadata;
4. uses `pyproject.toml`'s `dialogue` extra as the dependency authority; and
5. verifies `pip check`, the distribution/module version, and BART import.

This is the only supported ParlAI installation route.

### Docker and CI

The Docker stages are:

| Target | Purpose |
|---|---|
| `cpu-build` | Complete CPU development/runtime image |
| `cpu-test` | CPU image plus build-time verification |
| `cuda-build` | CUDA 13.0 build image using `torch==2.13.0+cu130`; builds and tests Postman against that ABI |
| `cuda-runtime` | CUDA runtime image with the compiled project and Postman wheel |

GitHub Actions builds the CPU development image and runs
`verify_full_build.sh --accelerator cpu`. It also proves that `cuda-runtime`
constructs on every pull request. Actual GPU execution remains a GPU-worker
gate, not a GitHub-hosted-runner claim.

### Modal validation

`modal_modern.py` independently builds the final CPU and cu130 images from
Ubuntu 24.04/CUDA 13.0.3 bases. It validates exact versions before running:

- B5: Linux `pydipcc` build and adjudication;
- B1: real checkpoint loading;
- B2: CUDA kernel plus strategy-model inference; and
- B3: ParlAI/BART GPU dialogue generation.

See `MODAL_VALIDATION.md` for commands and acceptance criteria.

The current Python 3.12/CUDA 13 checkpoint passed B1, B2, B3, and B5 on
2026-07-26. The same commit was also deployed through `modal_serve.py`; both
the `imitation` and `searchbot` authenticated RPC tiers returned real orders
and the app scaled back to zero workers. Exact commit, worker, checkpoint, and
run identifiers are recorded in `MODAL_VALIDATION.md` and
`MODAL_ORACLE_SERVING.md`.

The distributed self-play CPU gate also passed on 2026-07-26 in Modal run
`ap-hdQ6Bho2Zynt2OKOUtqBVx`: RELA and Postman each passed CTest plus 15 Python
tests during image construction and again in the remote function. The Linux
Postman artifact was a native CPython 3.12/x86-64 wheel with a verified
`$ORIGIN` Torch RPATH.

## Current acceptance gates

```bash
# Container CPU contract
docker build --target cpu-build -t diplomacy-cicero:cpu .
docker run --rm diplomacy-cicero:cpu \
  ./scripts/verify_full_build.sh --accelerator cpu
docker run --rm diplomacy-cicero:cpu \
  ./scripts/build_postman.sh

# Container CUDA contract on a GPU host
docker build --target cuda-runtime -t diplomacy-cicero:cuda .
docker run --rm --gpus all diplomacy-cicero:cuda \
  ./scripts/verify_full_build.sh --accelerator cuda --require-gpu

# Cloud gates
uvx modal run modal_modern.py::build_and_adjudicate
uvx modal run modal_modern.py::load_weights
uvx modal run modal_modern.py::gpu_checks
uvx modal run modal_selfplay.py
```

A release claim requires the exact version assertions and functional checks,
not merely successful imports.

## Historical checkpoints — not supported runtime evidence

The modernization began with exploratory environments that established
feasibility before the final contract was selected:

| Historical experiment | What it established | Why it is not current evidence |
|---|---|---|
| macOS/arm64, Python 3.11.10, PyTorch 2.12.1, protoc 25.3 | Modern protobuf generation and an arm64 `pydipcc` build were feasible | Wrong OS, Python, PyTorch, and protoc |
| Modal Linux/x86_64, Python 3.11, PyTorch 2.6.0+cu124, CUDA 12.4 | Real checkpoints and GPU policy/dialogue paths could cross the initial migration boundary | Wrong Python, PyTorch wheel, and CUDA line |

Those results explain design decisions and may be useful when reading old
commits. They do not satisfy a current gate and must not be presented as the
runtime users should install.
