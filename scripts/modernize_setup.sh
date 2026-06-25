#!/bin/bash -e
#
# Reproducible setup for the Python-3.11 / modern-torch modernization spike.
# Builds a uv-managed venv, regenerates protobuf, builds pydipcc, and runs the
# evidence checks documented in MODERNIZATION_REPORT.md.
#
# macOS/arm64, CPU-only. See MODERNIZATION_REPORT.md for what each step proves
# and which steps need an x86_64+CUDA container to fully validate.

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
VENV="$ROOT/.venv-modern"

echo "== 1. uv venv (Python 3.11) =="
uv venv --python 3.11 "$VENV"
# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "== 2. modern Python deps =="
uv pip install \
  "protobuf>=5.0" "mypy-protobuf>=3.5" \
  "torch>=2.2" "numpy>=1.26,<2.3" \
  "pybind11>=2.10" \
  tabulate joblib pyarrow tqdm termcolor colored pygtrie \
  dacite attrs python-dateutil psutil \
  iopath requests scikit-learn subword-nmt "setuptools<81" \
  pytest pyyaml
# ParlAI at Cicero's pinned commit (no-deps; deps installed above as needed)
uv pip install --no-deps \
  "git+https://github.com/facebookresearch/ParlAI.git@5214f42a2058ef335f91f5afe66b2bd9ebfb2fbe"

echo "== 3. regenerate + heyhi-patch protobuf (modern protoc) =="
rm -f conf/*_pb2.py conf/*_pb2.pyi conf/*_cfgs.py conf/*_cfgs.pyi
rm -rf conf/__pycache__
protoc conf/*.proto --python_out=./ --mypy_out=./
PYTHONPATH="$ROOT" python heyhi/bin/patch_protos.py \
  conf/agents_pb2.py conf/common_pb2.py conf/misc_pb2.py conf/conf_pb2.py

echo "== 4. build pydipcc (macOS/arm64 against modern torch + Homebrew glog) =="
# Homebrew glog/gflags (modern glog needs GLOG_USE_GLOG_EXPORT, handled in CMake)
brew list glog >/dev/null 2>&1 || brew install glog gflags
export CONDA_PREFIX=/opt/homebrew
export CMAKE_PREFIX_PATH="/opt/homebrew/opt/glog:/opt/homebrew/opt/gflags:$(python -c 'import pybind11; print(pybind11.get_cmake_dir())')"
( cd dipcc && rm -rf build && mkdir build && cd build \
    && cmake -DCMAKE_BUILD_TYPE=Release .. \
    && make pydipcc )
cp dipcc/build/dipcc/python/pydipcc.cpython-*-darwin.so fairdiplomacy/

echo "== 5. evidence checks =="
PYTHONPATH="$ROOT" python -m pytest heyhi/tests/test_conf.py -q || true
PYTHONPATH="$ROOT" python - <<'PY'
import torch, importlib.util, glob
so = glob.glob("fairdiplomacy/pydipcc.cpython-*-darwin.so")[0]
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
