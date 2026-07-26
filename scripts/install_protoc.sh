#!/usr/bin/env bash

set -euo pipefail

readonly PROTOC_VERSION="35.1"
readonly PROTOC_PREFIX="${PROTOC_PREFIX:-/usr/local}"

case "$(uname -s)-$(uname -m)" in
    Linux-x86_64|Linux-amd64)
        readonly PROTOC_ASSET="linux-x86_64"
        readonly PROTOC_SHA256="6930ebf62bd4ea607b98fff052596c6ee564b9835b4ce172c75a3f53ae9d91b7"
        ;;
    Linux-aarch64|Linux-arm64)
        readonly PROTOC_ASSET="linux-aarch_64"
        readonly PROTOC_SHA256="01bf9d08808c7f96678b63f4bd8efa559bb4f83d5a7a270d5edaf507f9d5d9cf"
        ;;
    Darwin-arm64)
        readonly PROTOC_ASSET="osx-aarch_64"
        readonly PROTOC_SHA256="193289af0470c6a1aada357d4fba0bbf8d78bfaac8b5e42ca30af2ef75583de2"
        ;;
    Darwin-x86_64)
        readonly PROTOC_ASSET="osx-x86_64"
        readonly PROTOC_SHA256="537d73604a344ded6fc94e98e07e529d4fe3e4a0b09e59905353950fafc2a1f7"
        ;;
    *)
        echo "Unsupported protoc platform: $(uname -s)-$(uname -m)" >&2
        exit 2
        ;;
esac

readonly PROTOC_URL="https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-${PROTOC_ASSET}.zip"
PROTOC_TMP_DIR="$(mktemp -d)"
readonly PROTOC_TMP_DIR
trap 'rm -rf "${PROTOC_TMP_DIR}"' EXIT

curl --fail --location --silent --show-error \
    "${PROTOC_URL}" \
    --output "${PROTOC_TMP_DIR}/protoc.zip"
if command -v sha256sum >/dev/null 2>&1; then
    printf '%s  %s\n' \
        "${PROTOC_SHA256}" \
        "${PROTOC_TMP_DIR}/protoc.zip" \
        | sha256sum --check -
else
    actual_sha256="$(shasum -a 256 "${PROTOC_TMP_DIR}/protoc.zip" | cut -d ' ' -f 1)"
    if [[ "${actual_sha256}" != "${PROTOC_SHA256}" ]]; then
        echo "protoc checksum mismatch: expected ${PROTOC_SHA256}, got ${actual_sha256}" >&2
        exit 1
    fi
fi
unzip -q -o "${PROTOC_TMP_DIR}/protoc.zip" -d "${PROTOC_PREFIX}"

installed_version="$("${PROTOC_PREFIX}/bin/protoc" --version)"
if [[ "${installed_version}" != "libprotoc ${PROTOC_VERSION}" ]]; then
    echo "Expected libprotoc ${PROTOC_VERSION}; found ${installed_version}" >&2
    exit 1
fi

echo "Installed ${installed_version} from ${PROTOC_ASSET}"
