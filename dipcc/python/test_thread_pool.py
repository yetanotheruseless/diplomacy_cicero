#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#

from __future__ import annotations

import torch

from fairdiplomacy import pydipcc
from fairdiplomacy.models.state_space import (
    get_order_vocabulary,
    get_order_vocabulary_idxs_len,
)

OPENING = {
    "AUSTRIA": ["A BUD - SER", "F TRI - ALB", "A VIE - TRI"],
    "ENGLAND": ["F LON - ENG", "A LVP - YOR", "F EDI - NTH"],
    "FRANCE": ["A MAR - SPA", "A PAR - BUR", "F BRE - MAO"],
    "GERMANY": ["A MUN - RUH", "A BER - KIE", "F KIE - DEN"],
    "ITALY": ["A VEN H", "F NAP - ION", "A ROM - APU"],
    "RUSSIA": ["F SEV - BLA", "A WAR - GAL", "F STP/SC - BOT", "A MOS - UKR"],
    "TURKEY": ["A CON - BUL", "F ANK - BLA", "A SMY - ARM"],
}


def _new_games(count: int) -> list[pydipcc.Game]:
    games = [pydipcc.Game() for _ in range(count)]
    for game in games:
        for power, orders in OPENING.items():
            game.set_orders(power, orders)
    return games


def test_thread_pool_processes_and_encodes_modern_tensors() -> None:
    """Exercise the current tensor-returning thread-pool API."""
    vocabulary = get_order_vocabulary()
    order_to_index = {order: index for index, order in enumerate(vocabulary)}
    pool = pydipcc.ThreadPool(4, order_to_index, get_order_vocabulary_idxs_len())
    games = _new_games(16)

    pool.process_multi(games)
    assert all(game.current_short_phase == "F1901M" for game in games)

    fields = pool.encode_inputs_state_only_multi(games, pydipcc.max_input_version())
    assert fields["x_board_state"].shape[0] == len(games)
    assert fields["x_board_state"].dtype == torch.float32
    assert fields["x_prev_orders"].dtype == torch.int64
    assert torch.isfinite(fields["x_board_state"]).all()
