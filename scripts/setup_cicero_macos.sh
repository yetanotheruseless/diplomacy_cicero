#!/usr/bin/env bash
#
# setup_cicero_macos.sh
#
# Reproduces the `diplomacy-cicero:working` image used to run Cicero on an
# Apple-Silicon (arm64) Mac via Docker. See README_MACOS.md for the full story.
#
# What it does:
#   1. Verifies Docker is running.
#   2. Ensures a legacy base image exists (Python 3.8 + torch 1.10.0 +
#      protobuf 3.19.1 + gcc-9). By default it reuses the compose-built
#      `diplomacy_cicero-diplomacy:latest`; if absent it builds it from
#      Dockerfile.unified via `docker compose build`.
#   3. Makes the prebuilt Linux-aarch64 pydipcc.so visible to fairdiplomacy.
#   4. Layers the missing Python deps (with the exact pins that work on
#      arm64 + numpy 1.20 + torch 1.10) into a container and commits it as
#      `diplomacy-cicero:working`.
#
# This is the VERIFIED path: it layers onto the known-good base rather than
# attempting a fragile from-scratch reinstall of requirements.txt (several of
# whose pins, e.g. tokenizers==0.10.3, have no arm64 wheel).
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_IMAGE="${BASE_IMAGE:-diplomacy_cicero-diplomacy:latest}"
TARGET_IMAGE="${TARGET_IMAGE:-diplomacy-cicero:working}"
BUILD_CONTAINER="cicero-setup-$$"

cd "$REPO_DIR"

echo "==> [1/4] Checking Docker..."
if ! docker info >/dev/null 2>&1; then
  echo "ERROR: Docker daemon not reachable. Start Docker Desktop and retry." >&2
  echo "       (Recommended: Settings > Resources > Memory >= 48 GB; the full" >&2
  echo "        Cicero dialogue agent needs ~50 GB RAM on CPU.)" >&2
  exit 1
fi

echo "==> [2/4] Ensuring base image '$BASE_IMAGE' exists..."
if ! docker image inspect "$BASE_IMAGE" >/dev/null 2>&1; then
  echo "    Base image not found; building from Dockerfile.unified (slow: compiles"
  echo "    protobuf 3.19.1 from source + dipcc). This is a one-time cost."
  docker compose build diplomacy
  # docker compose tags it as <project>-diplomacy:latest, i.e. the default BASE_IMAGE.
fi

echo "==> [3/4] Ensuring fairdiplomacy can find pydipcc.so..."
# The prebuilt module is a Linux-aarch64 ELF; the host loader globs
# fairdiplomacy/pydipcc*.so. Copy it from dipcc_pkg/ if not already present.
if ! ls fairdiplomacy/pydipcc*.so >/dev/null 2>&1; then
  if [ -f dipcc_pkg/pydipcc.so ]; then
    cp -v dipcc_pkg/pydipcc.so fairdiplomacy/pydipcc.so
  else
    echo "WARNING: no prebuilt pydipcc*.so found in fairdiplomacy/ or dipcc_pkg/." >&2
    echo "         You will need to build dipcc inside the container first." >&2
  fi
fi

echo "==> [4/4] Layering Python deps into a container and committing '$TARGET_IMAGE'..."
docker rm -f "$BUILD_CONTAINER" >/dev/null 2>&1 || true
docker run -d --name "$BUILD_CONTAINER" \
  -v "$REPO_DIR":/app -w /app -e PYTHONPATH=/app \
  "$BASE_IMAGE" tail -f /dev/null >/dev/null

cleanup() { docker rm -f "$BUILD_CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT

# Pure-python / lightweight deps (no torch change).
docker exec "$BUILD_CONTAINER" pip install --no-input -q \
  tabulate==0.8.9 termcolor==1.1.0 joblib==1.1.0 pygtrie==2.4.2 typer==0.4.1 \
  tqdm==4.62.1 psutil==5.9.0 ephemeral-port-reserve==1.1.4 dacite==1.6.0 \
  attrs==20.2.0 colored==1.4.3 requests==2.27.1 tensorboard==2.8.0 \
  pyyaml scipy sentencepiece ftfy emoji tornado wandb iopath subword-nmt \
  scikit-learn fairscale==0.4.6

# Vendored 'nest' pybind11 extension (compiled with the image's gcc-9).
docker exec -e CXX=c++ "$BUILD_CONTAINER" \
  pip install --no-input -q thirdparty/github/fairinternal/postman/nest/

# Pinned ParlAI commit, WITHOUT deps so it can't upgrade torch off 1.10.
docker exec "$BUILD_CONTAINER" pip install --no-input --no-deps -q \
  "git+https://github.com/facebookresearch/ParlAI.git@5214f42a2058ef335f91f5afe66b2bd9ebfb2fbe"

# Versions that satisfy ParlAI/Pillow against the legacy numpy 1.20 / py3.8.
docker exec "$BUILD_CONTAINER" pip install --no-input -q \
  "Pillow==9.5.0" "importlib-metadata==4.2.0" "markdown==3.3.2" "urllib3==1.26.18"

# CRITICAL: setuptools<60 so torch 1.10's tensorboard import doesn't crash with
# "module 'distutils' has no attribute 'version'".
docker exec "$BUILD_CONTAINER" pip install --no-input -q "setuptools==59.5.0"

# NOTE: transformers / tokenizers are intentionally NOT installed. ParlAI uses
# its own fairseq GPT-2 BPE (downloads vocab.bpe/encoder.json at runtime), which
# avoids tokenizers==0.10.3 — that has no arm64 wheel and needs a Rust toolchain.

echo "    Verifying core imports..."
docker exec "$BUILD_CONTAINER" bash -lc '
  python - <<PY
import fairdiplomacy, heyhi.conf
from fairdiplomacy.pydipcc import Game
from fairdiplomacy.agents import build_agent_from_cfg
print("OK: pydipcc + heyhi + agents import; Game phase", Game().current_short_phase)
PY' 2>&1 | grep -vE "UserWarning|cpu = |Triggered|submitit not available|Found pydipcc"

docker commit "$BUILD_CONTAINER" "$TARGET_IMAGE" >/dev/null
echo "==> Done. Committed image: $TARGET_IMAGE"
echo "    Now run an agent with: scripts/run_cicero_macos.sh cicero"
