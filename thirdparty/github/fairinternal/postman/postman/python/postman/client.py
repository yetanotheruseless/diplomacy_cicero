#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
from __future__ import annotations

from typing import Any

import torch  # noqa: F401

from postman import rpc


class Client(rpc.Client):
    # TODO(heiner): Consider implementing this on the C++ side.
    def __getattr__(self, name: str) -> Any:
        return lambda *args: self.call(name, args)
