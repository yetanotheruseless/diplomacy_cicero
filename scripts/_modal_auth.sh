# Source this to load Modal credentials from ../.env into the environment.
__ENVF="/Users/jake/src/open_src/.env"
export MODAL_TOKEN_ID="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_ID=' "$__ENVF" | head -1 | sed -E 's/^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_ID=//; s/^["'"'"']//; s/["'"'"']$//')"
export MODAL_TOKEN_SECRET="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_SECRET=' "$__ENVF" | head -1 | sed -E 's/^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_SECRET=//; s/^["'"'"']//; s/["'"'"']$//')"
unset __ENVF
