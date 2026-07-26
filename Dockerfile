# syntax=docker/dockerfile:1.7

ARG UBUNTU_VERSION=24.04
ARG CUDA_VERSION=13.0.3
ARG PYTHON_VERSION=3.12
ARG TORCH_VERSION=2.13.0
ARG PROTOC_VERSION=35.1

FROM ubuntu:${UBUNTU_VERSION} AS cpu-build

ARG PYTHON_VERSION
ARG TORCH_VERSION
ARG PROTOC_VERSION
ENV DEBIAN_FRONTEND=noninteractive
ENV VIRTUAL_ENV=/opt/cicero
ENV PATH="${VIRTUAL_ENV}/bin:/usr/local/bin:${PATH}"
ENV PYTHONPATH=/app
ENV CC=gcc-13
ENV CXX=g++-13

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        g++-13 \
        gcc-13 \
        git \
        libgflags-dev \
        libgoogle-glog-dev \
        ninja-build \
        python${PYTHON_VERSION} \
        python${PYTHON_VERSION}-dev \
        python${PYTHON_VERSION}-venv \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN python${PYTHON_VERSION} -m venv "${VIRTUAL_ENV}" \
    && python -m pip install --no-cache-dir --upgrade \
        "pip==26.1.2" \
        "setuptools==83.0.0" \
        "wheel==0.47.0"

WORKDIR /app
COPY scripts/install_protoc.sh /tmp/install_protoc.sh
RUN PROTOC_VERSION="${PROTOC_VERSION}" bash /tmp/install_protoc.sh \
    && rm /tmp/install_protoc.sh

COPY . /app
RUN python -m pip install --no-cache-dir \
        "torch==${TORCH_VERSION}" \
        --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir --editable ".[build,dialogue,dev]" \
    && python -m pip check

RUN make protos \
    && PYDIPCC_OUT_DIR=/app/fairdiplomacy N_DIPCC_JOBS=4 make dipcc

RUN ./scripts/install_parlai.sh

FROM cpu-build AS cpu-test

RUN ./scripts/verify_full_build.sh

CMD ["/bin/bash"]


FROM nvidia/cuda:${CUDA_VERSION}-cudnn-devel-ubuntu${UBUNTU_VERSION} AS cuda-build

ARG PYTHON_VERSION
ARG TORCH_VERSION
ARG PROTOC_VERSION
ENV DEBIAN_FRONTEND=noninteractive
ENV VIRTUAL_ENV=/opt/cicero
ENV PATH="${VIRTUAL_ENV}/bin:/usr/local/bin:${PATH}"
ENV PYTHONPATH=/app
ENV CC=gcc-13
ENV CXX=g++-13

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        g++-13 \
        gcc-13 \
        git \
        libgflags-dev \
        libgoogle-glog-dev \
        ninja-build \
        python${PYTHON_VERSION} \
        python${PYTHON_VERSION}-dev \
        python${PYTHON_VERSION}-venv \
        unzip \
    && rm -rf /var/lib/apt/lists/*

RUN python${PYTHON_VERSION} -m venv "${VIRTUAL_ENV}" \
    && python -m pip install --no-cache-dir --upgrade \
        "pip==26.1.2" \
        "setuptools==83.0.0" \
        "wheel==0.47.0"

WORKDIR /app
COPY scripts/install_protoc.sh /tmp/install_protoc.sh
RUN PROTOC_VERSION="${PROTOC_VERSION}" bash /tmp/install_protoc.sh \
    && rm /tmp/install_protoc.sh

COPY . /app
RUN python -m pip install --no-cache-dir \
        "torch==${TORCH_VERSION}" \
        --index-url https://download.pytorch.org/whl/cu130 \
    && python -m pip install --no-cache-dir --editable ".[build,dialogue,dev]" \
    && python -m pip check

RUN make protos \
    && PYDIPCC_OUT_DIR=/app/fairdiplomacy N_DIPCC_JOBS=4 make dipcc

RUN ./scripts/install_parlai.sh \
    && python - <<'PY'
import torch

assert torch.__version__.split("+", 1)[0] == "2.13.0", torch.__version__
assert torch.version.cuda == "13.0", torch.version.cuda
print("CUDA build Torch:", torch.__version__, "CUDA:", torch.version.cuda)
PY

RUN rm -rf /app/dipcc/build

FROM nvidia/cuda:${CUDA_VERSION}-cudnn-runtime-ubuntu${UBUNTU_VERSION} AS cuda-runtime

ARG PYTHON_VERSION
ENV DEBIAN_FRONTEND=noninteractive
ENV VIRTUAL_ENV=/opt/cicero
ENV PATH="${VIRTUAL_ENV}/bin:/usr/local/bin:${PATH}"
ENV PYTHONPATH=/app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        libgflags2.2 \
        libgoogle-glog0v6t64 \
        python${PYTHON_VERSION} \
    && rm -rf /var/lib/apt/lists/*

COPY --from=cuda-build /opt/cicero /opt/cicero
COPY --from=cuda-build /app /app

WORKDIR /app
RUN python - <<'PY'
import torch
from fairdiplomacy import pydipcc

assert torch.__version__.split("+", 1)[0] == "2.13.0", torch.__version__
assert torch.version.cuda == "13.0", torch.version.cuda
game = pydipcc.Game()
game.process()
assert game.current_short_phase == "F1901M", game.current_short_phase
print("CUDA runtime smoke passed:", torch.__version__, torch.version.cuda)
PY

CMD ["/bin/bash"]
