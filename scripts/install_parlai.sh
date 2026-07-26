#!/usr/bin/env bash

set -euo pipefail

readonly PARLAI_REF="${PARLAI_REF:-5214f42a2058ef335f91f5afe66b2bd9ebfb2fbe}"
readonly PARLAI_REPOSITORY="https://github.com/facebookresearch/ParlAI.git"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPO_ROOT
readonly PARLAI_PATCH="${REPO_ROOT}/patches/parlai-modern-runtime.patch"

# The pinned Cicero-compatible ParlAI commit publishes 2021 dependency metadata
# that requires NumPy <=1.21 and archived TorchText. Patch that metadata at the
# pinned source commit; pyproject.toml's dialogue extra is authoritative.
PARLAI_SOURCE="$(mktemp -d)"
readonly PARLAI_SOURCE
trap 'rm -rf "${PARLAI_SOURCE}"' EXIT

git -C "${PARLAI_SOURCE}" init --quiet
git -C "${PARLAI_SOURCE}" remote add origin "${PARLAI_REPOSITORY}"
git -C "${PARLAI_SOURCE}" fetch --quiet --depth=1 origin "${PARLAI_REF}"
git -C "${PARLAI_SOURCE}" checkout --quiet --detach FETCH_HEAD
git -C "${PARLAI_SOURCE}" apply --check "${PARLAI_PATCH}"
git -C "${PARLAI_SOURCE}" apply "${PARLAI_PATCH}"

python -m pip install --no-deps "${PARLAI_SOURCE}"
python -m pip check

python - <<'PY'
from importlib.metadata import version

import parlai
from parlai.agents.bart.bart import BartAgent

assert version("parlai") == "1.5.1+cicero1", version("parlai")
assert parlai.__version__ == "1.5.1+cicero1", parlai.__version__
print("ParlAI:", version("parlai"))
print("BART agent:", BartAgent.__name__)
PY
