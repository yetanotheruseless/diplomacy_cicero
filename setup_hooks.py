# 
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
import glob
import subprocess
import sys
from pathlib import Path

def post_install(project_dir=None):
    """Compile protobuf schemas after installation.
    
    This is equivalent to the post-install hook in the original setup.py
    """
    # Compiling the schema - skip mypy output if protoc-gen-mypy is not available
    try:
        # Try to compile with mypy output
        subprocess.check_output(
            ["protoc"] + list(glob.glob("conf/*.proto")) + ["--python_out", "./", "--mypy_out", "./"]
        )
        print("Protobuf schemas compiled successfully with mypy types")
    except subprocess.CalledProcessError:
        print("Could not generate mypy types, trying without...")
        try:
            # Try to compile without mypy output
            subprocess.check_output(
                ["protoc"] + list(glob.glob("conf/*.proto")) + ["--python_out", "./"]
            )
            print("Protobuf schemas compiled successfully without mypy types")
            print("To generate mypy types, install mypy-protobuf and ensure protoc-gen-mypy is in your PATH")
        except subprocess.CalledProcessError as e:
            print(f"Failed to compile protobuf schemas: {e}")
            sys.exit(1)

if __name__ == "__main__":
    post_install()