# Source this to load Modal credentials from ../.env into the environment.
__REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || return 1
__ENVF="${MODAL_ENV_FILE:-$(dirname "$__REPO_ROOT")/.env}"
unset __REPO_ROOT
if [ ! -r "$__ENVF" ]; then
    echo "Modal environment file is not readable: $__ENVF" >&2
    unset __ENVF
    return 1
fi
MODAL_TOKEN_ID="$(grep -m 1 -E '^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_ID=' "$__ENVF" | sed -E 's/^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_ID=//; s/^["'"'"']//; s/["'"'"']$//')"
MODAL_TOKEN_SECRET="$(grep -m 1 -E '^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_SECRET=' "$__ENVF" | sed -E 's/^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_SECRET=//; s/^["'"'"']//; s/["'"'"']$//')"
if [ -z "$MODAL_TOKEN_ID" ] || [ -z "$MODAL_TOKEN_SECRET" ]; then
    echo "Modal credentials are missing from $__ENVF" >&2
    unset __ENVF MODAL_TOKEN_ID MODAL_TOKEN_SECRET
    return 1
fi
export MODAL_TOKEN_ID MODAL_TOKEN_SECRET
unset __ENVF
