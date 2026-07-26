#!/usr/bin/env bash
# Verify the already-built legacy CPU environment used by Docker/CI.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

full_test=0
rebuild=0
for arg in "$@"; do
    case "$arg" in
        --full-test) full_test=1 ;;
        --rebuild) rebuild=1 ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: $0 [--rebuild] [--full-test]" >&2
            exit 2
            ;;
    esac
done

if [[ $rebuild -eq 1 ]]; then
    echo "Rebuilding generated protobuf modules and pydipcc..."
    make clean
    make protos_basic
    make dipcc
fi

python - <<'PY'
import platform

import google.protobuf
import numpy
import torch

print("Python:", platform.python_version())
print("Platform:", platform.platform(), platform.machine())
print("NumPy:", numpy.__version__)
print("Torch:", torch.__version__, "CUDA runtime:", torch.version.cuda)
print("protobuf:", google.protobuf.__version__)
PY

echo "Validating generated protobuf modules..."
python scripts/validate_protobuf.py

echo "Validating pydipcc..."
python test_pydipcc.py
python -m unittest unit_tests.test_full_integration

if [[ $full_test -eq 1 ]]; then
    echo "Running the full Python test suite without rebuilding native code..."
    python -m pytest heyhi/ fairdiplomacy/ parlai_diplomacy/ unit_tests/
fi

echo "Full build verification passed."
