#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
from __future__ import annotations

import time

import torch

import postman


def pyfunc(tensor: torch.Tensor) -> torch.Tensor:
    return 42 * (tensor + 1)


def identity(arg: object) -> object:
    print(arg)
    return arg


def main() -> None:
    server = postman.Server("127.0.0.1:12345")

    server.bind("pyfunc", pyfunc, batch_size=1)
    server.bind("identity", identity, batch_size=1)
    server.bind("batched_identity", identity, batch_size=2, wait_till_full=True)

    server.run()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
        server.wait()


if __name__ == "__main__":
    main()
