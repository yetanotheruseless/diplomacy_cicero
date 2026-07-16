#!/usr/bin/env bash

# Source this after exporting Modal credentials, or point
# CICERO_MODAL_ENV_FILE at a local dotenv file containing them. The dotenv file
# is read explicitly so this helper never depends on a developer-specific path.
_cicero_load_modal_auth() {
    if [[ -n "${CICERO_MODAL_ENV_FILE:-}" ]]; then
        local env_file="$CICERO_MODAL_ENV_FILE"
        if [[ ! -r "$env_file" ]]; then
            echo "CICERO_MODAL_ENV_FILE is not readable" >&2
            return 1
        fi

        if [[ -z "${MODAL_TOKEN_ID:-}" ]]; then
            MODAL_TOKEN_ID="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_ID=' "$env_file" | head -1 | sed -E 's/^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_ID=//; s/^["'"'"']//; s/["'"'"']$//')"
            export MODAL_TOKEN_ID
        fi
        if [[ -z "${MODAL_TOKEN_SECRET:-}" ]]; then
            MODAL_TOKEN_SECRET="$(grep -E '^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_SECRET=' "$env_file" | head -1 | sed -E 's/^[[:space:]]*(export[[:space:]]+)?MODAL_TOKEN_SECRET=//; s/^["'"'"']//; s/["'"'"']$//')"
            export MODAL_TOKEN_SECRET
        fi
    fi

    if [[ -z "${MODAL_TOKEN_ID:-}" || -z "${MODAL_TOKEN_SECRET:-}" ]]; then
        echo "Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET, or set CICERO_MODAL_ENV_FILE." >&2
        return 1
    fi
}

if _cicero_load_modal_auth; then
    unset -f _cicero_load_modal_auth
    true
else
    unset -f _cicero_load_modal_auth
    false
fi
