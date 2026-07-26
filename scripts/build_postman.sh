#!/usr/bin/env bash
#
# Build and test Postman tensor RPC on Cicero's canonical modern runtime.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ROOT
readonly POSTMAN_ROOT="${ROOT}/thirdparty/github/fairinternal/postman"
readonly POSTMAN_SOURCE="${POSTMAN_ROOT}/postman"
BUILD_DIR="${CICERO_POSTMAN_BUILD_DIR:-${ROOT}/build/postman-rpc}"
DEPS_DIR="${CICERO_POSTMAN_DEPS_DIR:-${ROOT}/build/postman-deps}"
readonly PYTHON_BIN="${CICERO_POSTMAN_PYTHON:-python}"
readonly JOBS="${N_POSTMAN_JOBS:-4}"
readonly GRPC_VERSION="1.83.0"
readonly GRPC_COMMIT="c876f4da50f7da2f331888b88b2a7243514139fe"
readonly PROTOBUF_COMMIT="35cd01f9fe9afbeea38cc7b979a3b6bfcde82c03"
readonly MACOS_DEPLOYMENT_TARGET="14.0"

mode="all"

usage() {
    cat <<'EOF'
Usage: scripts/build_postman.sh [--build-only | --test-only]

Build and test Postman RPC against Cicero's canonical Python 3.12,
PyTorch 2.13.0, pybind11 3.0.4, protobuf 35.1/7.35.1, gRPC 1.83.0,
and C++20 runtime.

Environment:
  CICERO_POSTMAN_PYTHON     Python interpreter to build against (default: python)
  CICERO_POSTMAN_BUILD_DIR  Out-of-tree Postman CMake build directory
  CICERO_POSTMAN_DEPS_DIR   Out-of-tree source dependency cache
  N_POSTMAN_JOBS            Parallel build jobs (default: 4)
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build-only)
            mode="build"
            shift
            ;;
        --test-only)
            mode="test"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

for tool in cmake ninja git; do
    if ! command -v "${tool}" >/dev/null 2>&1; then
        echo "Cicero Postman requires ${tool} on PATH" >&2
        exit 1
    fi
done
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
    echo "Cicero Postman Python interpreter not found: ${PYTHON_BIN}" >&2
    exit 1
fi

mkdir -p "${BUILD_DIR}" "${DEPS_DIR}"
BUILD_DIR="$(cd "${BUILD_DIR}" && pwd -P)"
DEPS_DIR="$(cd "${DEPS_DIR}" && pwd -P)"
readonly BUILD_DIR DEPS_DIR
readonly GRPC_SOURCE_DIR="${DEPS_DIR}/grpc-v${GRPC_VERSION}"
HOST_SYSTEM="$(uname -s)"
readonly HOST_SYSTEM
if [[ "${HOST_SYSTEM}" == "Darwin" ]]; then
    export MACOSX_DEPLOYMENT_TARGET="${MACOS_DEPLOYMENT_TARGET}"
fi

runtime_output="$(
    "${PYTHON_BIN}" - <<'PY'
import importlib.metadata
import pathlib
import sys

import google.protobuf
import pybind11
import torch

if sys.version_info[:2] != (3, 12):
    raise RuntimeError(f"expected Python 3.12, found {sys.version.split()[0]}")
if torch.__version__.split("+", 1)[0] != "2.13.0":
    raise RuntimeError(f"expected torch 2.13.0, found {torch.__version__}")
if pybind11.__version__ != "3.0.4":
    raise RuntimeError(f"expected pybind11 3.0.4, found {pybind11.__version__}")
if google.protobuf.__version__ != "7.35.1":
    raise RuntimeError(
        f"expected Python protobuf 7.35.1, found {google.protobuf.__version__}"
    )
if importlib.metadata.version("scikit-build-core") != "1.0.3":
    raise RuntimeError(
        "expected scikit-build-core 1.0.3; install the project build extra"
    )

print(pathlib.Path(torch.__file__).parent / "lib")
PY
)"
torch_lib_dir="$(printf '%s\n' "${runtime_output}" | sed -n '1p')"
readonly torch_lib_dir

if [[ "${mode}" != "test" ]]; then
    mkdir -p "${DEPS_DIR}"
    if [[ ! -e "${GRPC_SOURCE_DIR}" ]]; then
        git clone \
            --branch "v${GRPC_VERSION}" \
            --depth 1 \
            https://github.com/grpc/grpc.git \
            "${GRPC_SOURCE_DIR}"
    fi
    if [[ ! -d "${GRPC_SOURCE_DIR}/.git" ]]; then
        echo "gRPC dependency path is not a git checkout: ${GRPC_SOURCE_DIR}" >&2
        exit 1
    fi

    actual_grpc_commit="$(git -C "${GRPC_SOURCE_DIR}" rev-parse HEAD)"
    if [[ "${actual_grpc_commit}" != "${GRPC_COMMIT}" ]]; then
        echo \
            "Expected gRPC v${GRPC_VERSION} commit ${GRPC_COMMIT}; " \
            "found ${actual_grpc_commit} in ${GRPC_SOURCE_DIR}" >&2
        exit 1
    fi

    git -C "${GRPC_SOURCE_DIR}" submodule sync --quiet
    git -C "${GRPC_SOURCE_DIR}" submodule update \
        --init \
        --depth 1 \
        third_party/abseil-cpp \
        third_party/boringssl-with-bazel \
        third_party/cares/cares \
        third_party/protobuf \
        third_party/re2 \
        third_party/zlib

    required_submodules=(
        third_party/abseil-cpp
        third_party/boringssl-with-bazel
        third_party/cares/cares
        third_party/protobuf
        third_party/re2
        third_party/zlib
    )
    for dependency in "${required_submodules[@]}"; do
        dependency_status="$(
            git -C "${GRPC_SOURCE_DIR}/${dependency}" status \
                --porcelain \
                --untracked-files=all
        )"
        if [[ -n "${dependency_status}" ]]; then
            echo "Dirty gRPC dependency cache: ${GRPC_SOURCE_DIR}/${dependency}" >&2
            printf '%s\n' "${dependency_status}" >&2
            exit 1
        fi
    done
    grpc_status="$(
        git -C "${GRPC_SOURCE_DIR}" status \
            --porcelain \
            --untracked-files=all
    )"
    if [[ -n "${grpc_status}" ]]; then
        echo "Dirty gRPC dependency cache: ${GRPC_SOURCE_DIR}" >&2
        printf '%s\n' "${grpc_status}" >&2
        exit 1
    fi

    actual_protobuf_commit="$(
        git -C "${GRPC_SOURCE_DIR}/third_party/protobuf" rev-parse HEAD
    )"
    if [[ "${actual_protobuf_commit}" != "${PROTOBUF_COMMIT}" ]]; then
        echo \
            "Expected protobuf 35.1 commit ${PROTOBUF_COMMIT}; " \
            "found ${actual_protobuf_commit}" >&2
        exit 1
    fi

    wheel_dir="$(mktemp -d "${BUILD_DIR}/wheelhouse.XXXXXX")"
    readonly wheel_dir
    CICERO_GRPC_SOURCE_DIR="${GRPC_SOURCE_DIR}" \
    CMAKE_BUILD_PARALLEL_LEVEL="${JOBS}" \
    SKBUILD_BUILD_DIR="${BUILD_DIR}" \
    "${PYTHON_BIN}" -m pip wheel \
        --disable-pip-version-check \
        --no-build-isolation \
        --no-deps \
        --wheel-dir "${wheel_dir}" \
        "${POSTMAN_ROOT}"

    wheel_paths=("${wheel_dir}"/postman-*.whl)
    if [[ "${#wheel_paths[@]}" -ne 1 || ! -f "${wheel_paths[0]}" ]]; then
        echo "Expected exactly one Postman wheel in ${wheel_dir}" >&2
        exit 1
    fi
    wheel_path="${wheel_paths[0]}"
    if [[ "${HOST_SYSTEM}" == "Darwin" ]]; then
        expected_wheel_platform="macosx_14_0_$(uname -m)"
        readonly expected_wheel_platform
        if [[ "$(basename "${wheel_path}")" != *-"${expected_wheel_platform}.whl" ]]; then
            echo \
                "Expected Postman wheel platform ${expected_wheel_platform}; " \
                "found $(basename "${wheel_path}")" >&2
            exit 1
        fi
    fi

    "${PYTHON_BIN}" - "${wheel_path}" <<'PY'
import pathlib
import sys
import zipfile

wheel = pathlib.Path(sys.argv[1])
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
    extensions = [
        name
        for name in names
        if name.startswith("postman/rpc")
        and name.endswith((".so", ".dylib", ".pyd"))
    ]
    if len(extensions) != 1:
        raise RuntimeError(f"expected one native rpc extension, found {extensions}")
    wheel_metadata_path = next(
        name for name in names if name.endswith(".dist-info/WHEEL")
    )
    wheel_metadata = archive.read(wheel_metadata_path).decode()
    if "Root-Is-Purelib: false" not in wheel_metadata:
        raise RuntimeError(wheel_metadata)
    if any(line.endswith("-none-any") for line in wheel_metadata.splitlines()):
        raise RuntimeError(f"native Postman wheel has a universal tag:\n{wheel_metadata}")

print(f"Postman platform wheel: {wheel.name}")
PY
    artifact_root="$(mktemp -d "${BUILD_DIR}/wheel-artifact.XXXXXX")"
    readonly artifact_root
    extension_path="$(
        "${PYTHON_BIN}" - "${wheel_path}" "${artifact_root}" <<'PY'
import pathlib
import sys
import zipfile

wheel = pathlib.Path(sys.argv[1])
destination = pathlib.Path(sys.argv[2])
with zipfile.ZipFile(wheel) as archive:
    extensions = [
        name
        for name in archive.namelist()
        if name.startswith("postman/rpc")
        and name.endswith((".so", ".dylib", ".pyd"))
    ]
    if len(extensions) != 1:
        raise RuntimeError(f"expected one native rpc extension, found {extensions}")
    archive.extract(extensions[0], destination)
print((destination / extensions[0]).resolve())
PY
    )"
    readonly extension_path
    case "${HOST_SYSTEM}" in
        Darwin)
            if ! command -v otool >/dev/null 2>&1; then
                echo "otool is required to verify the Postman wheel RPATH" >&2
                exit 1
            fi
            rpath_output="$(
                otool -l "${extension_path}" |
                    awk '
                        $1 == "cmd" {
                            in_rpath = ($2 == "LC_RPATH")
                            next
                        }
                        in_rpath && $1 == "path" {
                            print $2
                            in_rpath = 0
                        }
                    '
            )"
            expected_rpath="@loader_path/../torch/lib"
            if ! otool -l "${extension_path}" |
                awk -v expected="${MACOS_DEPLOYMENT_TARGET}" '
                    $1 == "minos" {
                        seen = 1
                        if ($2 != expected) {
                            invalid = 1
                        }
                    }
                    END {
                        exit !(seen && !invalid)
                    }
                '
            then
                echo \
                    "Postman wheel must target macOS ${MACOS_DEPLOYMENT_TARGET}" >&2
                otool -l "${extension_path}" |
                    awk '$1 == "minos" {print "found minos " $2}' >&2
                exit 1
            fi
            ;;
        Linux)
            if ! command -v readelf >/dev/null 2>&1; then
                echo "readelf is required to verify the Postman wheel RPATH" >&2
                exit 1
            fi
            rpath_output="$(
                readelf -d "${extension_path}" |
                    awk '/\(RPATH\)|\(RUNPATH\)/'
            )"
            expected_rpath="\$ORIGIN/../torch/lib"
            ;;
        *)
            echo "Unsupported Postman build platform: $(uname -s)" >&2
            exit 1
            ;;
    esac
    readonly rpath_output expected_rpath
    if ! grep -Fq "${expected_rpath}" <<<"${rpath_output}"; then
        echo "Postman wheel is missing relative Torch RPATH ${expected_rpath}" >&2
        printf '%s\n' "${rpath_output}" >&2
        exit 1
    fi
    for forbidden_path in "${ROOT}" "${BUILD_DIR}" "${DEPS_DIR}"; do
        if grep -Fq "${forbidden_path}" <<<"${rpath_output}"; then
            echo "Postman wheel contains an absolute build RPATH: ${forbidden_path}" >&2
            printf '%s\n' "${rpath_output}" >&2
            exit 1
        fi
    done
    echo "Postman relative Torch RPATH: ${expected_rpath}"

    "${PYTHON_BIN}" -m pip install \
        --disable-pip-version-check \
        --no-deps \
        --force-reinstall \
        "${wheel_path}"
    printf '%s\n' "${wheel_path}" > "${BUILD_DIR}/postman-wheel-path.txt"
fi

if [[ "${mode}" != "build" ]]; then
    if [[ ! -x "${BUILD_DIR}/postman_native_test" ]]; then
        echo "No Postman test build found in ${BUILD_DIR}; run without --test-only first" >&2
        exit 1
    fi

    wheel_record="${BUILD_DIR}/postman-wheel-path.txt"
    if [[ ! -f "${wheel_record}" ]]; then
        echo "No Postman wheel record found; run without --test-only first" >&2
        exit 1
    fi
    wheel_path="$(sed -n '1p' "${wheel_record}")"
    if [[ ! -f "${wheel_path}" ]]; then
        echo "Recorded Postman wheel does not exist: ${wheel_path}" >&2
        exit 1
    fi

    smoke_root="$(mktemp -d "${BUILD_DIR}/wheel-smoke.XXXXXX")"
    readonly smoke_root
    "${PYTHON_BIN}" -m pip install \
        --disable-pip-version-check \
        --no-compile \
        --no-deps \
        --target "${smoke_root}" \
        "${wheel_path}"
    torch_package="$(
        "${PYTHON_BIN}" -c \
            'import pathlib, torch; print(pathlib.Path(torch.__file__).parent)'
    )"
    ln -s "${torch_package}" "${smoke_root}/torch"
    env \
        -u DYLD_LIBRARY_PATH \
        -u LD_LIBRARY_PATH \
        PYTHONPATH="${smoke_root}" \
        POSTMAN_SMOKE_ROOT="${smoke_root}" \
        "${PYTHON_BIN}" - <<'PY'
import os
import pathlib

import postman
from postman import rpc

root = pathlib.Path(os.environ["POSTMAN_SMOKE_ROOT"]).resolve()
module = pathlib.Path(postman.__file__).resolve()
if not module.is_relative_to(root):
    raise RuntimeError(f"wheel smoke imported {module}, not a clean target under {root}")
if rpc.__grpc_version__ != "1.83.0":
    raise RuntimeError(rpc.__grpc_version__)
if rpc.__protobuf_version__ != "35.1":
    raise RuntimeError(rpc.__protobuf_version__)
if rpc.__torch_version__ != "2.13.0":
    raise RuntimeError(rpc.__torch_version__)
print(f"Clean wheel import: {module}")
PY

    case "${HOST_SYSTEM}" in
        Darwin)
            export DYLD_LIBRARY_PATH="${torch_lib_dir}${DYLD_LIBRARY_PATH:+:${DYLD_LIBRARY_PATH}}"
            ;;
        *)
            export LD_LIBRARY_PATH="${torch_lib_dir}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
            ;;
    esac

    ctest --test-dir "${BUILD_DIR}" --output-on-failure
    "${PYTHON_BIN}" -m pytest \
        -q \
        "${POSTMAN_SOURCE}/tests/python"
fi

echo "Cicero Postman RPC ${mode} completed successfully."
