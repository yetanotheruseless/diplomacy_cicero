#!/usr/bin/env bash
#
# Build and test the optional RELA prioritized-replay extension on the
# canonical Cicero runtime: Python 3.12, PyTorch 2.13.0, and C++20.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT
readonly BUILD_DIR="${CICERO_SELFPLAY_BUILD_DIR:-${ROOT}/build/selfplay}"
readonly PYTHON_BIN="${CICERO_SELFPLAY_PYTHON:-python}"
readonly JOBS="${N_SELFPLAY_JOBS:-4}"

mode="all"

usage() {
    cat <<'EOF'
Usage: scripts/build_selfplay.sh [--build-only | --test-only]

Build and test Cicero's optional RELA prioritized-replay extension against the
canonical Python 3.12 / PyTorch 2.13.0 / C++20 runtime.

Environment:
  CICERO_SELFPLAY_PYTHON     Python interpreter to build against (default: python)
  CICERO_SELFPLAY_BUILD_DIR  Out-of-tree CMake build directory
  N_SELFPLAY_JOBS            Parallel build jobs (default: 4)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-only)
            mode="build"
            shift
            ;;
        --test-only)
            mode="test"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

for tool in cmake ninja; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "Cicero self-play requires ${tool} on PATH" >&2
        exit 1
    fi
done
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Cicero self-play Python interpreter not found: ${PYTHON_BIN}" >&2
    exit 1
fi

version_output="$(
    "${PYTHON_BIN}" - <<'PY'
import pathlib
import sys

import pybind11
import torch

if sys.version_info[:2] != (3, 12):
    raise RuntimeError(f"expected Python 3.12, found {sys.version.split()[0]}")
if torch.__version__.split("+", 1)[0] != "2.13.0":
    raise RuntimeError(f"expected torch 2.13.0, found {torch.__version__}")

print(pybind11.get_cmake_dir())
print(pathlib.Path(torch.__file__).parent / "lib")
PY
)"
pybind11_dir="${version_output%%$'\n'*}"
torch_lib_dir="${version_output#*$'\n'}"
readonly pybind11_dir torch_lib_dir

if [[ "${mode}" != "test" ]]; then
    cmake \
        --fresh \
        -S "${ROOT}/fairdiplomacy/selfplay/cc" \
        -B "${BUILD_DIR}" \
        -G Ninja \
        -DBUILD_TESTING=ON \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_LIBRARY_OUTPUT_DIRECTORY="${ROOT}/fairdiplomacy/selfplay" \
        -DPython_EXECUTABLE="$("${PYTHON_BIN}" -c 'import sys; print(sys.executable)')" \
        -Dpybind11_DIR="${pybind11_dir}"
    cmake \
        --build "${BUILD_DIR}" \
        --target rela prioritized_replay_test \
        --parallel "${JOBS}"
fi

if [[ "${mode}" != "build" ]]; then
    if [[ ! -x "${BUILD_DIR}/prioritized_replay_test" ]]; then
        echo "No self-play test build found in ${BUILD_DIR}; run without --test-only first" >&2
        exit 1
    fi

    case "$(uname -s)" in
        Darwin)
            export DYLD_LIBRARY_PATH="${torch_lib_dir}${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
            ;;
        *)
            export LD_LIBRARY_PATH="${torch_lib_dir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
            ;;
    esac
    export PYTHONPATH="${ROOT}/fairdiplomacy/selfplay:${ROOT}${PYTHONPATH:+:${PYTHONPATH}}"

    ctest --test-dir "${BUILD_DIR}" --output-on-failure
    "${PYTHON_BIN}" - <<'PY'
try:
    from fairdiplomacy.selfplay import rela
except ImportError as error:
    if "cannot import name 'pydipcc'" not in str(error):
        raise
    # RELA is independently testable before the separate pydipcc extension has
    # been built. Production code uses fairdiplomacy.selfplay.rela.
    import rela

print(f"RELA module: {rela.__file__}")
PY
    "${PYTHON_BIN}" -m pytest \
        -q \
        "${ROOT}/unit_tests/test_selfplay_rela.py"
fi

echo "Cicero RELA self-play ${mode} completed successfully."
