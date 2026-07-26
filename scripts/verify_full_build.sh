#!/usr/bin/env bash
# Verify the already-built legacy CPU environment used by Docker/CI.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rebuild=0
for arg in "$@"; do
    case "$arg" in
        --rebuild) rebuild=1 ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: $0 [--rebuild]" >&2
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
import sys

import google.protobuf
import numpy
import torch

print("Python:", platform.python_version())
print("Platform:", platform.platform(), platform.machine())
print("NumPy:", numpy.__version__)
print("Torch:", torch.__version__, "CUDA runtime:", torch.version.cuda)
print("protobuf:", google.protobuf.__version__)

assert numpy.__version__ == "1.20.3", numpy.__version__
assert torch.__version__ == "1.10.0+cpu", torch.__version__
assert torch.version.cuda is None, torch.version.cuda
assert google.protobuf.__version__ == "3.19.1", google.protobuf.__version__
assert sys.version_info[:2] == (3, 8), sys.version
PY

python -m pip check

echo "Validating generated protobuf modules..."
python scripts/validate_protobuf.py

echo "Validating pydipcc..."
python test_pydipcc.py
python -m unittest unit_tests.test_full_integration

echo "Full build verification passed."
