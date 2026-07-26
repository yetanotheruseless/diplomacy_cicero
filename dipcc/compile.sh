#!/bin/bash -e
#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#

MODE="${MODE:-Release}"
N_DIPCC_JOBS="${N_DIPCC_JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)}"
DIPCC_TARGET="${DIPCC_TARGET:-pydipcc}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

PYBIND11_DIR="$(python -m pybind11 --cmakedir)"

cmake \
    --fresh \
    -S . \
    -B build \
    -G Ninja \
    -DCMAKE_BUILD_TYPE="${MODE}" \
    -DPython_EXECUTABLE="$(command -v python)" \
    -Dpybind11_DIR="${PYBIND11_DIR}"
cmake --build build --target "${DIPCC_TARGET}" --parallel "${N_DIPCC_JOBS}"
