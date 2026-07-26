#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
from __future__ import annotations

import gc
import queue
import threading
from collections.abc import Callable
from typing import Any

import pytest
import torch

import postman

RPC_TIMEOUT_SECONDS = 15


def _call_with_timeout(
    function: Callable[[], Any],
    timeout: float = RPC_TIMEOUT_SECONDS,
) -> Any:
    outcomes: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def invoke() -> None:
        try:
            outcomes.put((True, function()))
        except Exception as error:  # noqa: BLE001 - forward failures to the test thread.
            outcomes.put((False, error))

    thread = threading.Thread(target=invoke, name="postman-test-call", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"Postman operation did not finish within {timeout} seconds")

    succeeded, outcome = outcomes.get_nowait()
    if succeeded:
        return outcome
    raise outcome


def _future_get(future: Any) -> Any:
    return _call_with_timeout(future.get)


def _address(server: postman.Server) -> str:
    return f"127.0.0.1:{server.port()}"


def _stop_and_wait(server: postman.Server) -> None:
    server.stop()
    _call_with_timeout(server.wait)


def _capture_error(function: Callable[[], Any]) -> Exception:
    try:
        function()
    except Exception as error:  # noqa: BLE001 - compare the public exception contract.
        return error
    raise AssertionError("Expected the operation to raise")


def test_async_calls_are_concurrent_and_close_is_idempotent() -> None:
    def increment(tensor: torch.Tensor) -> torch.Tensor:
        return tensor + 1

    server = postman.Server("127.0.0.1:0")
    server.bind("increment", increment, batch_size=8)
    server.run()
    streams = postman.AsyncClient(_address(server)).connect(RPC_TIMEOUT_SECONDS)
    try:
        futures = [streams.increment(torch.tensor(index)) for index in range(64)]
        results = [_future_get(future) for future in futures]
        for index, result in enumerate(results):
            torch.testing.assert_close(result, torch.tensor(index + 1))

        _call_with_timeout(streams.close)
        _call_with_timeout(streams.close)
        with pytest.raises(ConnectionError, match="closed"):
            streams.increment(torch.tensor(1))
    finally:
        _call_with_timeout(streams.close)
        _stop_and_wait(server)


def test_async_independent_functions_do_not_head_of_line_block() -> None:
    slow_started = threading.Event()
    release_slow = threading.Event()

    def slow(tensor: torch.Tensor) -> torch.Tensor:
        slow_started.set()
        if not release_slow.wait(RPC_TIMEOUT_SECONDS):
            raise TimeoutError("test did not release the slow RPC")
        return tensor + 1

    def fast(tensor: torch.Tensor) -> torch.Tensor:
        return tensor + 2

    server = postman.Server("127.0.0.1:0")
    server.bind("slow", slow, batch_size=1)
    server.bind("fast", fast, batch_size=1)
    server.run()
    streams = postman.AsyncClient(_address(server)).connect(RPC_TIMEOUT_SECONDS)
    try:
        slow_future = streams.slow(torch.zeros(()))
        assert slow_started.wait(RPC_TIMEOUT_SECONDS)

        fast_future = streams.fast(torch.zeros(()))
        torch.testing.assert_close(_future_get(fast_future), torch.full((), 2.0))

        release_slow.set()
        torch.testing.assert_close(_future_get(slow_future), torch.full((), 1.0))
    finally:
        release_slow.set()
        _call_with_timeout(streams.close)
        _stop_and_wait(server)


def test_streams_outlive_client_and_survive_reconnect() -> None:
    server = postman.Server("127.0.0.1:0")
    server.bind("identity", lambda tensor: tensor, batch_size=1)
    server.run()

    client = postman.AsyncClient(_address(server))
    first_streams = client.connect(RPC_TIMEOUT_SECONDS)
    second_streams = client.connect(RPC_TIMEOUT_SECONDS)
    del client
    gc.collect()

    try:
        torch.testing.assert_close(
            _future_get(first_streams.identity(torch.tensor(1))),
            torch.tensor(1),
        )
        torch.testing.assert_close(
            _future_get(second_streams.identity(torch.tensor(2))),
            torch.tensor(2),
        )
    finally:
        _call_with_timeout(first_streams.close)
        _call_with_timeout(first_streams.close)
        _call_with_timeout(second_streams.close)
        _call_with_timeout(second_streams.close)
        _stop_and_wait(server)


def test_async_and_sync_calls_preserve_remote_error_type_and_message() -> None:
    def fail(_tensor: torch.Tensor) -> torch.Tensor:
        raise ValueError("intentional remote failure")

    server = postman.Server("127.0.0.1:0")
    server.bind("fail", fail, batch_size=1)
    server.run()

    sync_client = postman.Client(_address(server))
    sync_client.connect(RPC_TIMEOUT_SECONDS)
    streams = postman.AsyncClient(_address(server)).connect(RPC_TIMEOUT_SECONDS)
    try:
        sync_error = _capture_error(lambda: sync_client.fail(torch.tensor(0)))
        async_future = streams.fail(torch.tensor(0))
        async_error = _capture_error(lambda: _future_get(async_future))

        assert type(async_error) is type(sync_error)
        assert isinstance(async_error, ValueError)
        assert str(async_error) == str(sync_error)
        assert "intentional remote failure" in str(async_error)
    finally:
        _call_with_timeout(streams.close)
        _stop_and_wait(server)


def test_close_cancels_an_inflight_call_without_waiting_for_server_work() -> None:
    call_started = threading.Event()
    release_call = threading.Event()

    def block(tensor: torch.Tensor) -> torch.Tensor:
        call_started.set()
        if not release_call.wait(RPC_TIMEOUT_SECONDS):
            raise TimeoutError("test did not release the in-flight RPC")
        return tensor + 1

    server = postman.Server("127.0.0.1:0")
    server.bind("block", block, batch_size=1)
    server.run()
    streams = postman.AsyncClient(_address(server)).connect(RPC_TIMEOUT_SECONDS)

    try:
        future = streams.block(torch.tensor(4))
        assert call_started.wait(RPC_TIMEOUT_SECONDS)

        _call_with_timeout(streams.close, timeout=2)
        assert future.wait_for(2), "cancelled asynchronous call did not become ready"
        with pytest.raises(ConnectionError):
            future.get()
        streams.close()
    finally:
        release_call.set()
        _call_with_timeout(streams.close)
        _stop_and_wait(server)


def test_async_capacity_is_bounded_and_close_rejects_queued_work() -> None:
    call_started = threading.Event()
    release_call = threading.Event()

    def block(tensor: torch.Tensor) -> torch.Tensor:
        call_started.set()
        if not release_call.wait(RPC_TIMEOUT_SECONDS):
            raise TimeoutError("test did not release the in-flight RPC")
        return tensor

    server = postman.Server("127.0.0.1:0")
    server.bind("block", block, batch_size=1)
    server.run()
    streams = postman.AsyncClient(
        _address(server),
        max_concurrent_calls=1,
        max_outstanding_calls=2,
    ).connect(RPC_TIMEOUT_SECONDS)

    try:
        active = streams.block(torch.tensor(1))
        assert call_started.wait(RPC_TIMEOUT_SECONDS)
        pending = streams.block(torch.tensor(2))

        with pytest.raises(ConnectionError, match="capacity"):
            streams.block(torch.tensor(3))

        _call_with_timeout(streams.close, timeout=2)
        assert active.wait_for(2), "active asynchronous call was not cancelled"
        assert pending.wait_for(2), "queued asynchronous call was not rejected"
        with pytest.raises(ConnectionError):
            active.get()
        with pytest.raises(ConnectionError):
            pending.get()
        with pytest.raises(ConnectionError, match="closed"):
            streams.block(torch.tensor(4))
    finally:
        release_call.set()
        _call_with_timeout(streams.close)
        _stop_and_wait(server)
