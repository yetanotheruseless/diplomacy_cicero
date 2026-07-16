# shellcheck shell=bash
# Source this to load Modal credentials from a shared sibling .env file.
# Override CICERO_ENV_FILE when credentials live elsewhere.
__SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
__ENVF="${CICERO_ENV_FILE:-$__SCRIPT_DIR/../../.env}"
if [[ ! -f "$__ENVF" ]]; then
    echo "Modal credential file not found: $__ENVF" >&2
    return 1
fi
MODAL_TOKEN_ID="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_ID=' "$__ENVF" | head -1 | sed -E 's/^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_ID=//; s/^["'"'"']//; s/["'"'"']$//')"
MODAL_TOKEN_SECRET="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_SECRET=' "$__ENVF" | head -1 | sed -E 's/^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_SECRET=//; s/^["'"'"']//; s/["'"'"']$//')"
if [[ -z "$MODAL_TOKEN_ID" || -z "$MODAL_TOKEN_SECRET" ]]; then
    echo "Modal credential file is missing MODAL_TOKEN_ID or MODAL_TOKEN_SECRET" >&2
    unset MODAL_TOKEN_ID MODAL_TOKEN_SECRET __ENVF __SCRIPT_DIR
    return 1
fi
export MODAL_TOKEN_ID MODAL_TOKEN_SECRET
unset __ENVF __SCRIPT_DIR
