#!/usr/bin/env bash
#
# run_cicero_macos.sh — run a Diplomacy/Cicero agent in Docker on macOS.
#
# Usage:
#   scripts/run_cicero_macos.sh <mode> [power] [max_turns]
#
#   mode    one of:
#             policy  - base_strategy_model vs base_strategy_model (fast; pure
#                       neural policy, no search, no dialogue). ~10s/turn.
#             search  - searchbot (CFR/rollout no-press) vs base_strategy_model.
#                       ~1 min/turn.
#             cicero  - FULL Cicero (search + pseudo-orders + dialogue) vs six
#                       imitation agents. Generates real negotiation messages.
#                       VERY slow on CPU (minutes per power, ~50 GB RAM).
#   power   power for agent_one (default: AUSTRIA for policy/search, TURKEY for cicero)
#   max_turns  number of movement turns to play (default: 1)
#
# Requires the image built by scripts/setup_cicero_macos.sh and the decrypted
# model weights in ./models/. Output game JSON is written under
# ./diplomacy_experiments/adhoc/<timestamp>/.../output.json
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${IMAGE:-diplomacy-cicero:working}"
MODE="${1:-cicero}"
MAX_TURNS="${3:-1}"
cd "$REPO_DIR"

if ! ls models/blueprint.pt >/dev/null 2>&1; then
  echo "ERROR: models/ does not contain decrypted weights (e.g. models/blueprint.pt)." >&2
  echo "       Decrypt them first (see README_MACOS.md)." >&2
  exit 1
fi

CFG="conf/c01_ag_cmp/cmp.prototxt"
COMMON=(--adhoc --cfg "$CFG" "max_turns=$MAX_TURNS")

case "$MODE" in
  policy)
    POWER="${2:-AUSTRIA}"
    ARGS=(
      Iagent_one=agents/base_strategy_model
      Iagent_six=agents/base_strategy_model
      "power_one=$POWER"
    )
    ;;
  search)
    POWER="${2:-AUSTRIA}"
    ARGS=(
      agent_one.searchbot.n_rollouts=10
      agent_one.searchbot.rollouts_cfg.n_threads=8
      "power_one=$POWER"
    )
    ;;
  cicero)
    POWER="${2:-TURKEY}"
    ARGS=(
      Iagent_one=agents/cicero.prototxt
      Iagent_six=agents/ablations/cicero_imitation_only.prototxt
      # half precision is GPU-only; on CPU torch raises
      # "softmax_lastdim_kernel_impl not implemented for 'Half'".
      agent_one.bqre1p.base_searchbot_cfg.half_precision=false
      "power_one=$POWER"
    )
    ;;
  *)
    echo "Unknown mode '$MODE'. Use: policy | search | cicero" >&2
    exit 1
    ;;
esac

echo "==> mode=$MODE power=$POWER max_turns=$MAX_TURNS image=$IMAGE"
exec docker run --rm -it \
  -v "$REPO_DIR":/app -w /app \
  -e PYTHONPATH=/app \
  -e HH_EXP_DIR=/app/diplomacy_experiments \
  -e OMP_NUM_THREADS="${OMP_NUM_THREADS:-12}" \
  "$IMAGE" \
  python run.py "${COMMON[@]}" "${ARGS[@]}"
