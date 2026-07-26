"""Validate modern RELA and Postman self-play extensions on Linux/x86_64 CPU.

Run with:

    modal run modal_selfplay.py
"""

from __future__ import annotations

import pathlib
import subprocess

import modal

REPO = pathlib.Path(__file__).parent

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install(
        "build-essential",
        "ca-certificates",
        "cmake",
        "g++-13",
        "gcc-13",
        "git",
        "ninja-build",
    )
    .pip_install(
        "torch==2.13.0+cpu",
        index_url="https://download.pytorch.org/whl/cpu",
    )
    .pip_install(
        "protobuf==7.35.1",
        "pybind11==3.0.4",
        "pytest>=9,<10",
        "scikit-build-core==1.0.3",
    )
    .add_local_dir(
        str(REPO),
        "/app",
        copy=True,
        ignore=[
            ".git",
            ".venv*",
            "build",
            "models",
            "models_encrypted",
            ".cicero_model_stage",
            "**/*.so",
            "**/__pycache__",
        ],
    )
    .env(
        {
            "CC": "gcc-13",
            "CXX": "g++-13",
            "CICERO_SELFPLAY_PYTHON": "python",
            "CICERO_POSTMAN_PYTHON": "python",
            "N_SELFPLAY_JOBS": "4",
            "N_POSTMAN_JOBS": "4",
        }
    )
    .run_commands("cd /app && ./scripts/build_selfplay.sh && ./scripts/build_postman.sh")
)

app = modal.App("cicero-selfplay-runtime")


@app.function(image=image, cpu=4.0, timeout=1200)
def validate() -> str:
    import platform
    import sys

    import google.protobuf
    import postman
    import torch
    from postman import rpc

    assert sys.version_info[:2] == (3, 12), sys.version
    assert torch.__version__ == "2.13.0+cpu", torch.__version__
    assert torch.version.cuda is None, torch.version.cuda
    assert google.protobuf.__version__ == "7.35.1", google.protobuf.__version__
    assert postman.__version__ == "0.3.0", postman.__version__
    assert rpc.__grpc_version__ == "1.83.0", rpc.__grpc_version__
    assert rpc.__protobuf_version__ == "35.1", rpc.__protobuf_version__

    subprocess.run(
        ["/app/scripts/build_selfplay.sh", "--test-only"],
        cwd="/app",
        check=True,
    )
    subprocess.run(
        ["/app/scripts/build_postman.sh", "--test-only"],
        cwd="/app",
        check=True,
    )
    result = (
        f"{platform.system()} {platform.machine()}; "
        f"Python {platform.python_version()}; Torch {torch.__version__}; "
        f"protobuf {google.protobuf.__version__}; "
        f"Postman gRPC {rpc.__grpc_version__}"
    )
    print(result)
    return result


@app.local_entrypoint()
def main() -> None:
    print(validate.remote())
