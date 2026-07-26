# Building `dipcc` and `pydipcc`

`dipcc` is the C++20 Diplomacy engine. `pydipcc` is its pybind11 extension,
imported as `fairdiplomacy.pydipcc`.

## Supported build contract

- Ubuntu 24.04
- Python 3.12 plus development headers
- PyTorch 2.13.0 (`+cpu` or `+cu130`)
- CMake 3.28+
- Ninja
- GCC/G++ 13
- pybind11 3.0.4
- glog and gflags development packages

The extension links against the active Python and PyTorch installations. Build
it only after installing the final Torch variant for the target image.

## Recommended build

The Dockerfile supplies the complete toolchain:

```bash
docker build --target cpu-build -t diplomacy-cicero:cpu .
docker run --rm diplomacy-cicero:cpu python test_pydipcc.py
```

For an already prepared local environment:

```bash
source .venv-modern/bin/activate
make protos
PYDIPCC_OUT_DIR="$PWD/fairdiplomacy" \
N_DIPCC_JOBS=4 \
./dipcc/compile.sh
```

`dipcc/compile.sh` configures a fresh Ninja build using the active `python`,
PyTorch's CMake prefix, and pybind11's CMake directory. The default target is
`pydipcc`.

Useful overrides:

```bash
MODE=Debug N_DIPCC_JOBS=2 ./dipcc/compile.sh
DIPCC_TARGET=profile_dipcc ./dipcc/compile.sh
```

## Build layout

```text
dipcc/
├── CMakeLists.txt
├── compile.sh
├── dipcc/cc/          C++ engine
├── dipcc/pybind/      Python bindings
├── dipcc/profiling/   profiling executables
└── build/             generated Ninja/CMake output
```

When `PYDIPCC_OUT_DIR` is set, CMake writes the extension directly to that
directory. The supported project build writes it to `fairdiplomacy/`.

## Validation

```bash
python -c \
  "from fairdiplomacy import pydipcc; print(pydipcc.Game().current_short_phase)"
python test_pydipcc.py
python -m unittest unit_tests.test_full_integration
python -m pytest dipcc/python/test_thread_pool.py -q
```

The first command should print `S1901M`.

## Troubleshooting

### CMake finds the wrong Python

Activate the Python 3.12 environment before configuring and remove stale build
state:

```bash
source .venv-modern/bin/activate
rm -rf dipcc/build
./dipcc/compile.sh
```

The configuration must report the same interpreter returned by:

```bash
command -v python
python -c "import sys; print(sys.executable)"
```

### Torch is not found

Install the final Torch wheel first and verify:

```bash
python -c \
  "import torch; print(torch.__version__, torch.utils.cmake_prefix_path)"
```

Do not compile against a CPU wheel and then replace it with a CUDA wheel.

### glog/gflags are not found

On Ubuntu 24.04, install `libgoogle-glog-dev` and `libgflags-dev`. The CMake
build requires their config-mode imported targets.

### Build runs out of memory

Reduce parallelism:

```bash
N_DIPCC_JOBS=1 ./dipcc/compile.sh
```

### Extension cannot be imported

Confirm that exactly one architecture/interpreter-compatible extension exists:

```bash
find fairdiplomacy -maxdepth 1 -name 'pydipcc*.so' -print
python -c "from fairdiplomacy import pydipcc; print(pydipcc.__file__)"
```

Rebuild whenever Python, PyTorch variant, architecture, or compiler ABI
changes.

See [docs/dipcc_integration.md](docs/dipcc_integration.md) for the runtime
boundary.
