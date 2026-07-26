#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
from __future__ import annotations

import threading
from typing import Any

import torch  # noqa: F401

from postman import rpc


class AsyncClient(rpc.AsyncClient):
    def connect(self, deadline_sec: int = 60) -> Streams:
        return Streams(super().connect(deadline_sec))


class Streams:
    def __init__(self, raw_stream: Any) -> None:
        self._raw_stream = raw_stream
        self._close_lock = threading.Lock()
        self._closed = False

    # TODO(heiner): Consider implementing this on the C++ side.
    def __getattr__(self, name: str) -> Any:
        def call(*args: Any) -> Any:
            with self._close_lock:
                if self._closed:
                    raise ConnectionError("Streams are closed")
                return self._raw_stream.call(name, args)

        return call

    def close(self) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
            self._raw_stream.close()
