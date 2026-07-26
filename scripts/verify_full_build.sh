#!/usr/bin/env bash
# Verify an already-built modern Cicero CPU or CUDA environment.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

accelerator="auto"
rebuild=0
require_gpu=0

usage() {
    cat <<'EOF'
Usage: scripts/verify_full_build.sh [OPTIONS]

Options:
  --accelerator cpu|cuda  Require a CPU-only or CUDA 13.0 PyTorch build.
                          The default is to detect the wheel type.
  --require-gpu           Require a usable CUDA device and run a tensor smoke test.
  --rebuild               Regenerate protobuf modules and rebuild pydipcc first.
  -h, --help              Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --accelerator)
            if [[ $# -lt 2 ]]; then
                echo "--accelerator requires cpu or cuda" >&2
                exit 2
            fi
            accelerator="$2"
            shift 2
            ;;
        --require-gpu)
            require_gpu=1
            shift
            ;;
        --rebuild)
            rebuild=1
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

if [[ "${accelerator}" != "auto" && "${accelerator}" != "cpu" && "${accelerator}" != "cuda" ]]; then
    echo "--accelerator must be cpu or cuda" >&2
    exit 2
fi
if [[ ${require_gpu} -eq 1 && "${accelerator}" == "cpu" ]]; then
    echo "--require-gpu cannot be combined with --accelerator cpu" >&2
    exit 2
fi

if [[ ${rebuild} -eq 1 ]]; then
    for tool in cmake ninja protoc; do
        if ! command -v "${tool}" >/dev/null 2>&1; then
            echo "--rebuild requires ${tool}" >&2
            exit 1
        fi
    done
    echo "Rebuilding generated protobuf modules and pydipcc..."
    make clean
    make protos
    make dipcc
fi

detected_cuda="$(
    python - <<'PY'
import torch

print(torch.version.cuda or "")
PY
)"
if [[ "${accelerator}" == "auto" ]]; then
    if [[ -n "${detected_cuda}" ]]; then
        accelerator="cuda"
    else
        accelerator="cpu"
    fi
fi

CICERO_EXPECTED_ACCELERATOR="${accelerator}" \
CICERO_REQUIRE_GPU="${require_gpu}" \
python - <<'PY'
from importlib.metadata import version
import os
import platform
import sys

import google.protobuf
import numpy
import parlai
from parlai.agents.bart.bart import BartAgent
import parlai_diplomacy
import torch

EXPECTED_PYTHON = (3, 12)
EXPECTED_PIP = "26.1.2"
EXPECTED_SETUPTOOLS = "83.0.0"
EXPECTED_WHEEL = "0.47.0"
EXPECTED_NUMPY = "2.4.6"
EXPECTED_TORCH = "2.13.0"
EXPECTED_PROTOBUF = "7.35.1"
EXPECTED_PARLAI = "1.5.1+cicero1"
EXPECTED_CUDA = "13.0"

os_release = platform.freedesktop_os_release()
assert os_release["ID"] == "ubuntu", os_release
assert os_release["VERSION_ID"] == "24.04", os_release
assert sys.version_info[:2] == EXPECTED_PYTHON, sys.version
assert version("pip") == EXPECTED_PIP, version("pip")
assert version("setuptools") == EXPECTED_SETUPTOOLS, version("setuptools")
assert version("wheel") == EXPECTED_WHEEL, version("wheel")
assert numpy.__version__ == EXPECTED_NUMPY, numpy.__version__
assert torch.__version__.split("+", 1)[0] == EXPECTED_TORCH, torch.__version__
assert version("protobuf") == EXPECTED_PROTOBUF, version("protobuf")
assert google.protobuf.__version__ == EXPECTED_PROTOBUF, google.protobuf.__version__
assert version("parlai") == EXPECTED_PARLAI, version("parlai")
assert parlai.__version__ == EXPECTED_PARLAI, parlai.__version__

accelerator = os.environ["CICERO_EXPECTED_ACCELERATOR"]
require_gpu = os.environ["CICERO_REQUIRE_GPU"] == "1"
if accelerator == "cpu":
    assert torch.version.cuda is None, torch.version.cuda
    assert not require_gpu
else:
    assert accelerator == "cuda", accelerator
    assert torch.version.cuda == EXPECTED_CUDA, torch.version.cuda
    if require_gpu:
        assert torch.cuda.is_available(), "CUDA wheel is installed, but no CUDA device is usable"
        value = torch.ones(1, device="cuda").item()
        assert value == 1.0, value

assert BartAgent.__name__ == "BartAgent"
print("OS:", os_release["PRETTY_NAME"])
print("Python:", platform.python_version())
print(
    "Packaging:",
    f"pip {version('pip')}, setuptools {version('setuptools')}, wheel {version('wheel')}",
)
print("NumPy:", numpy.__version__)
print("Torch:", torch.__version__, "compiled CUDA:", torch.version.cuda)
print("CUDA device available:", torch.cuda.is_available())
print("protobuf runtime:", google.protobuf.__version__)
print("Accelerator contract:", accelerator)
print("ParlAI:", parlai.__version__, "BART:", BartAgent.__name__)
print("parlai_diplomacy:", parlai_diplomacy.__name__)
PY

python -m pip check

echo "Validating generated protobuf modules..."
if command -v protoc >/dev/null 2>&1; then
    python scripts/validate_protobuf.py
elif [[ "${accelerator}" == "cuda" ]]; then
    python scripts/validate_protobuf.py --runtime-only
else
    echo "The CPU build must include protoc 35.1" >&2
    exit 1
fi

echo "Validating HeyHi generated-config integration..."
python -m pytest -q heyhi/tests/test_conf.py

echo "Validating pydipcc..."
python test_pydipcc.py
python -m unittest unit_tests.test_full_integration

if [[ "${accelerator}" == "cuda" && ${require_gpu} -eq 0 ]]; then
    echo "CUDA userspace validated without a GPU; run again with --require-gpu on a GPU cloud worker."
fi
echo "Modern ${accelerator} build verification passed."
