#!/usr/bin/env bash
# Run the canonical CPU, test, or CUDA Compose service.

set -euo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
    cat <<'EOF'
Usage: scripts/docker_run.sh [cpu|test|cuda] [COMMAND...]

Modes:
  cpu   Build and enter the canonical CPU service (default).
  test  Build the CPU service and run the full verification contract.
  cuda  Build and enter the CUDA 13.0 service with GPU access.

If COMMAND is supplied, it replaces the selected service's default command.
EOF
}

mode="cpu"
case "${1:-}" in
    cpu|test|cuda)
        mode="$1"
        shift
        ;;
    -h|--help)
        usage
        exit 0
        ;;
esac

compose_args=(docker compose)
run_args=(run --build --rm)
case "${mode}" in
    cpu)
        service="diplomacy"
        run_args+=(--service-ports)
        ;;
    test)
        compose_args+=(--profile test)
        service="diplomacy_test"
        ;;
    cuda)
        compose_args+=(--profile cuda)
        service="diplomacy_cuda"
        run_args+=(--service-ports)
        ;;
esac

exec "${compose_args[@]}" "${run_args[@]}" "${service}" "$@"
