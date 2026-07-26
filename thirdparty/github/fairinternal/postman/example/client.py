#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
from __future__ import annotations

import os

import torch

import postman


def main() -> None:
    client_id = os.getpid()
    print("Client id", client_id)

    client = postman.Client("127.0.0.1:12345")
    client.connect(deadline_sec=3)
    try:
        output = client.pyfunc(torch.zeros(1, 2))
        torch.testing.assert_close(output, torch.full((1, 2), 42.0))

        client_array = torch.tensor([0, client_id, 2 * client_id])
        inputs = (torch.tensor(0), torch.tensor(1), (client_array, torch.tensor(True)))
        client.identity(inputs)
        torch.testing.assert_close(client.identity(client_array), client_array)
        torch.testing.assert_close(client.batched_identity(client_array), client_array)
    finally:
        client.close()


if __name__ == "__main__":
    main()
