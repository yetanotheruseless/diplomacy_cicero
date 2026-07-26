#!/usr/bin/env bash
#
# Reproducible local CPU build for the canonical runtime stack:
# Python 3.12, torch 2.13.0, protobuf 7.35.1, and protoc 35.1.
#
# The Modal CPU and GPU images follow the same steps independently, with the GPU
# image installing its final cu130 wheel before compiling pydipcc.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
readonly ROOT
readonly VENV="$ROOT/.venv-modern"
readonly PYTHON_VERSION="3.12"
readonly TORCH_VERSION="2.13.0"
readonly PROTOBUF_VERSION="7.35.1"
readonly PROTOC_VERSION="35.1"
readonly PIP_VERSION="26.1.2"
readonly SETUPTOOLS_VERSION="83.0.0"
readonly WHEEL_VERSION="0.47.0"

echo "== 1. uv venv (Python ${PYTHON_VERSION}) =="
uv venv --python "$PYTHON_VERSION" "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "== 2. pinned protoc ${PROTOC_VERSION} =="
PROTOC_VERSION="$PROTOC_VERSION" PROTOC_PREFIX="$VENV" ./scripts/install_protoc.sh

echo "== 3. final CPU torch + editable runtime extras =="
if [[ "$(uname -s)" == "Linux" ]]; then
  uv pip install "torch==${TORCH_VERSION}+cpu" \
    --index-url https://download.pytorch.org/whl/cpu
else
  uv pip install "torch==${TORCH_VERSION}"
fi
uv pip install \
  "pip==${PIP_VERSION}" "setuptools==${SETUPTOOLS_VERSION}" "wheel==${WHEEL_VERSION}" \
  --upgrade
python -m pip install --no-cache-dir --editable ".[build,dialogue,dev]"
python -m pip check

# Install the pinned source through the repository's compatibility patch. Its
# wheel metadata and pkg_resources usage are modernized before installation.
./scripts/install_parlai.sh

python - <<PY
import importlib.metadata
import sys

import google.protobuf
import numpy
import parlai
import torch

if sys.version_info[:2] != (3, 12):
    raise RuntimeError(sys.version)
if torch.__version__.split("+", 1)[0] != "${TORCH_VERSION}":
    raise RuntimeError(torch.__version__)
if google.protobuf.__version__ != "${PROTOBUF_VERSION}":
    raise RuntimeError(google.protobuf.__version__)
if numpy.__version__ != "2.4.6":
    raise RuntimeError(numpy.__version__)
for package, expected in {
    "pip": "${PIP_VERSION}",
    "setuptools": "${SETUPTOOLS_VERSION}",
    "wheel": "${WHEEL_VERSION}",
    "parlai": "1.5.1+cicero1",
}.items():
    actual = importlib.metadata.version(package)
    if actual != expected:
        raise RuntimeError(f"{package}: expected {expected}, got {actual}")
print("versions:", sys.version.split()[0], torch.__version__, google.protobuf.__version__)
PY

echo "== 4. canonical protobuf generation =="
make protos

echo "== 5. build pydipcc =="
if [[ "$(uname -s)" == "Darwin" ]]; then
  brew list glog >/dev/null 2>&1 || brew install glog gflags
fi
PYDIPCC_OUT_DIR="$ROOT/fairdiplomacy" N_DIPCC_JOBS="${N_DIPCC_JOBS:-4}" ./dipcc/compile.sh

echo "== 6. evidence checks =="
PYTHONPATH="$ROOT" python -m pytest heyhi/tests/test_conf.py -q
PYTHONPATH="$ROOT" python - <<'PY'
import torch, importlib.util, glob
so = glob.glob("fairdiplomacy/pydipcc*.so")[0]
spec = importlib.util.spec_from_file_location("pydipcc", so)
pydipcc = importlib.util.module_from_spec(spec); spec.loader.exec_module(pydipcc)
g = pydipcc.Game(); g.process()
print("pydipcc adjudication OK; phase ->", g.current_short_phase)
import fairdiplomacy
from fairdiplomacy.agents import build_agent_from_cfg
import conf.agents_cfgs as ag
agent = build_agent_from_cfg(ag.Agent(random=ag.RandomAgent()).to_frozen())
st = agent.initialize_state("FRANCE")
print("RandomAgent orders:", sorted(agent.get_orders(pydipcc.Game(), "FRANCE", st)))
print("full-press import:", __import__("fairdiplomacy.agents.parlai_full_press_agent",
      fromlist=["ParlaiFullPressAgent"]).ParlaiFullPressAgent.__name__)
PY

echo "== done =="
