#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
"""Binding-level tests for the optional RELA prioritized-replay extension."""

import importlib
import tempfile
import time
from struct import pack

import pytest
import torch

try:
    rela = importlib.import_module("fairdiplomacy.selfplay.rela")
except ImportError as error:
    if "cannot import name 'pydipcc'" not in str(error):
        raise
    rela = pytest.importorskip(
        "rela",
        reason="the optional RELA extension has not been built",
    )


def _sample(value: int) -> dict[str, torch.Tensor]:
    return {
        "value": torch.tensor([value], dtype=torch.float32),
        "flag": torch.tensor([value % 2], dtype=torch.int64),
    }


def test_add_sample_and_update_priority_with_prefetch() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=16,
        seed=7,
        alpha=0.6,
        beta=0.4,
        prefetch=2,
    )
    for value in range(8):
        replay.add_one(_sample(value), float(value + 1))

    batch, weights = replay.sample(4)
    assert batch["value"].shape == (1, 4)
    assert batch["flag"].shape == (1, 4)
    assert weights.shape == (4,)
    assert torch.isfinite(weights).all()

    replay.update_priority(torch.ones(4))
    next_batch, next_weights = replay.sample(4)
    assert next_batch["value"].shape == (1, 4)
    assert next_weights.shape == (4,)
    replay.keep_priority()


def test_add_batch_async() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=8,
        seed=3,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    future = replay.add_batch_async(
        [_sample(1), _sample(2), _sample(3)],
        torch.ones(3),
    )
    future.get()

    assert replay.size() == 3
    assert replay.num_add() == 3


def test_async_add_keeps_replay_alive_until_completion() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=25_000,
        seed=3,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    future = replay.add_batch_async(
        [_sample(value) for value in range(20_000)],
        torch.ones(20_000),
    )
    del replay

    future.get()


def test_public_preconditions_raise_python_exceptions() -> None:
    with pytest.raises(ValueError, match="capacity must be positive"):
        rela.NestPrioritizedReplay(
            capacity=0,
            seed=1,
            alpha=1.0,
            beta=0.0,
            prefetch=0,
        )

    replay = rela.NestPrioritizedReplay(
        capacity=8,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    with pytest.raises(RuntimeError, match="enough samples"):
        replay.sample(1)
    with pytest.raises(ValueError, match="match the number of samples"):
        replay.add_batch([_sample(1), _sample(2)], torch.ones(1))
    with pytest.raises(ValueError, match="dtype torch.float32"):
        replay.add_batch([_sample(1)], torch.ones(1, dtype=torch.float64))
    with pytest.raises(ValueError, match="contiguous"):
        replay.add_batch(
            [_sample(1), _sample(2)],
            torch.ones(4)[::2],
        )
    with pytest.raises(ValueError, match="positive values"):
        replay.add_one(_sample(1), 0.0)

    assert replay.size() == 0


def test_prefetch_rejects_a_changed_batch_size() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=16,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=2,
    )
    replay.add_batch([_sample(value) for value in range(8)], torch.ones(8))

    replay.sample(4)
    replay.keep_priority()
    with pytest.raises(ValueError, match="fixed sample batch size"):
        replay.sample(2)


def test_capacity_one_has_room_for_a_concurrent_producer() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=1,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    replay.add_one(_sample(1), 1.0)
    future = replay.add_batch_async([_sample(2)], torch.ones(1))

    replay.sample(1)
    replay.keep_priority()
    future.get()
    replay.sample(1)
    replay.keep_priority()

    assert replay.size() == 1


def test_sampling_while_a_block_append_is_reserved_is_safe() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=100,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    replay.add_one(_sample(0), 1.0)
    wide_sample = {
        f"value_{index}": torch.tensor([index], dtype=torch.float32) for index in range(256)
    }
    future = replay.add_batch_async([wide_sample] * 124, torch.ones(124))
    time.sleep(0.000_01)

    replay.sample(1)
    replay.keep_priority()
    future.get()
    replay.sample(1)
    replay.keep_priority()

    assert replay.size() == 100


def test_load_rejects_oversized_counts_before_allocating() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=4,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    with tempfile.NamedTemporaryFile() as buffer_file:
        buffer_file.write(pack("=iii", 575757, 0, 6))
        buffer_file.flush()
        with pytest.raises(RuntimeError, match="element count.*supported limit"):
            replay.load(buffer_file.name)


def test_save_rejects_content_that_its_loader_cannot_accept() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=4,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    replay.add_one(
        {"x" * (64 * 1024 + 1): torch.ones(1)},
        1.0,
    )

    with (
        tempfile.NamedTemporaryFile() as buffer_file,
        pytest.raises(RuntimeError, match="header name.*supported limit"),
    ):
        replay.save(buffer_file.name)


def test_load_rejects_oversized_tensor_payload_before_allocating() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=4,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    with tempfile.NamedTemporaryFile() as buffer_file:
        buffer_file.write(pack("=iii", 575757, 1, 1))
        buffer_file.write(b"x")
        buffer_file.write(pack("=ii", 1, 512 * 1024 * 1024 + 1))
        buffer_file.flush()
        with pytest.raises(RuntimeError, match="payload size.*supported limit"):
            replay.load(buffer_file.name)


def test_save_load_round_trip_includes_overflow_headroom() -> None:
    source = rela.NestPrioritizedReplay(
        capacity=4,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    for value in range(5):
        source.add_one(_sample(value), 1.0)

    with tempfile.NamedTemporaryFile() as buffer_file:
        source.save(buffer_file.name)
        restored = rela.NestPrioritizedReplay(
            capacity=4,
            seed=1,
            alpha=1.0,
            beta=0.0,
            prefetch=0,
        )
        restored.load(buffer_file.name)

    actual = [entry["value"].item() for entry in restored.get_all_content()[0]]
    assert actual == [0.0, 1.0, 2.0, 3.0, 4.0]


def test_save_load_preserves_ring_buffer_order_after_eviction() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=4,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    for value in range(5):
        replay.add_one(_sample(value), 1.0)

    replay.sample(4)
    replay.keep_priority()
    expected = [entry["value"].item() for entry in replay.get_all_content()[0]]
    assert expected == [1.0, 2.0, 3.0, 4.0]

    with tempfile.NamedTemporaryFile() as buffer_file:
        replay.save(buffer_file.name)
        restored = rela.NestPrioritizedReplay(
            capacity=4,
            seed=1,
            alpha=1.0,
            beta=0.0,
            prefetch=0,
        )
        restored.load(buffer_file.name)

    actual = [entry["value"].item() for entry in restored.get_all_content()[0]]
    assert actual == expected
    assert restored.size() == replay.size()
    assert restored.num_add() == 0


def test_save_empty_buffer_fails_without_crashing_python() -> None:
    replay = rela.NestPrioritizedReplay(
        capacity=4,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    with (
        tempfile.NamedTemporaryFile() as buffer_file,
        pytest.raises(RuntimeError, match="empty replay buffer"),
    ):
        replay.save(buffer_file.name)


def test_load_into_non_empty_buffer_fails_instead_of_blocking() -> None:
    source = rela.NestPrioritizedReplay(
        capacity=4,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    source.add_one(_sample(1), 1.0)

    destination = rela.NestPrioritizedReplay(
        capacity=4,
        seed=1,
        alpha=1.0,
        beta=0.0,
        prefetch=0,
    )
    destination.add_one(_sample(2), 1.0)

    with tempfile.NamedTemporaryFile() as buffer_file:
        source.save(buffer_file.name)
        with pytest.raises(RuntimeError, match="non-empty storage"):
            destination.load(buffer_file.name)


def test_save_can_snapshot_while_async_add_is_finishing() -> None:
    for iteration in range(10):
        replay = rela.NestPrioritizedReplay(
            capacity=64,
            seed=iteration,
            alpha=1.0,
            beta=0.0,
            prefetch=0,
        )
        for value in range(8):
            replay.add_one(_sample(value), 1.0)

        future = replay.add_batch_async(
            [_sample(value) for value in range(8, 24)],
            torch.ones(16),
        )
        with tempfile.NamedTemporaryFile() as buffer_file:
            replay.save(buffer_file.name)
            future.get()

            snapshot = rela.NestPrioritizedReplay(
                capacity=64,
                seed=iteration,
                alpha=1.0,
                beta=0.0,
                prefetch=0,
            )
            snapshot.load(buffer_file.name)

        assert 8 <= snapshot.size() <= 24
