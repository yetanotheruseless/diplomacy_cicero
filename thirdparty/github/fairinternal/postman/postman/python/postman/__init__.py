#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
"""Postman tensor RPC bindings for Cicero's canonical modern runtime."""

import torch  # noqa: F401

try:
    from .asyncclient import AsyncClient, Streams
    from .client import Client
    from .rpc import ComputationQueue
    from .server import Server
except ImportError as error:
    if "postman.rpc" not in str(error):
        raise
    raise ImportError(
        "Postman RPC is not built for this interpreter. "
        "Run ./scripts/build_postman.sh with CICERO_POSTMAN_PYTHON set to "
        "the canonical Python 3.12 executable."
    ) from error

__all__ = ["AsyncClient", "Client", "ComputationQueue", "Server", "Streams"]
__version__ = "0.3.0"
