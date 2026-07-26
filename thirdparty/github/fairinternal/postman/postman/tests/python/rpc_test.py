#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
from __future__ import annotations

import queue
import socket
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, wait
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


def _address(server: postman.Server) -> str:
    return f"127.0.0.1:{server.port()}"


def _stop_and_wait(server: postman.Server) -> None:
    server.stop()
    _call_with_timeout(server.wait)


def _connected_client(server: postman.Server) -> postman.Client:
    client = postman.Client(_address(server))
    client.connect(RPC_TIMEOUT_SECONDS)
    return client


def _unused_local_address() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return f"127.0.0.1:{listener.getsockname()[1]}"


def test_python_rpc_batches_concurrent_clients() -> None:
    num_clients = 4
    calls: defaultdict[str, int] = defaultdict(int)

    def python_function(
        tensor: torch.Tensor,
        sequence: torch.Tensor,
        nested: tuple[torch.Tensor, torch.Tensor],
    ) -> torch.Tensor:
        calls["python_function"] += 1
        assert tensor.shape == (1, 1, 2)
        assert sequence.shape == (1, 10)
        assert nested[0].shape == (1, 2, 3)
        assert nested[1].shape == (1, 1, 2)
        return tensor + 3

    def batched_function(tensor: torch.Tensor) -> torch.Tensor:
        calls["batched_function"] += 1
        assert tensor.shape == (num_clients, 1, 2)
        return tensor + 5

    server = postman.Server("127.0.0.1:0")
    server.bind("python_function", python_function, batch_size=1)
    server.bind(
        "batched_function",
        batched_function,
        batch_size=num_clients,
        wait_till_full=True,
    )
    server.run()

    start = threading.Barrier(num_clients)

    def run_client() -> tuple[torch.Tensor, torch.Tensor]:
        client = _connected_client(server)
        start.wait(RPC_TIMEOUT_SECONDS)
        direct = client.python_function(
            torch.zeros((1, 2)),
            torch.arange(10),
            (torch.empty(2, 3), torch.ones((1, 2))),
        )
        batched = client.batched_function(torch.zeros((1, 2)))
        return direct, batched

    executor = ThreadPoolExecutor(max_workers=num_clients, thread_name_prefix="postman-client")
    futures = [executor.submit(run_client) for _ in range(num_clients)]
    try:
        done, not_done = wait(futures, timeout=RPC_TIMEOUT_SECONDS)
        assert not not_done, "concurrent RPC clients timed out"
        assert len(done) == num_clients
        for future in futures:
            direct, batched = future.result()
            torch.testing.assert_close(direct, torch.full((1, 2), 3.0))
            torch.testing.assert_close(batched, torch.full((1, 2), 5.0))
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
        _stop_and_wait(server)

    assert calls["python_function"] == num_clients
    assert calls["batched_function"] == 1


def test_none_return_is_an_empty_tuple() -> None:
    def get_tensor() -> torch.Tensor:
        return torch.arange(2).reshape(1, 2)

    def return_none(_tensor: torch.Tensor) -> None:
        return None

    def implicit_none() -> None:
        return None

    server = postman.Server("127.0.0.1:0")
    server.bind("get_tensor", get_tensor, batch_size=1)
    server.bind("return_none", return_none, batch_size=1)
    server.bind("implicit_none", implicit_none, batch_size=1)
    server.run()
    try:
        client = _connected_client(server)
        torch.testing.assert_close(client.get_tensor(), torch.arange(2))
        assert client.return_none(torch.tensor(10)) == ()
        assert client.implicit_none() == ()
    finally:
        _stop_and_wait(server)


def test_server_lifecycle_is_one_shot_and_cleanup_is_idempotent() -> None:
    server = postman.Server("127.0.0.1:0")
    server.bind("identity", lambda tensor: tensor, batch_size=1, num_threads=2)
    server.run()

    assert server.port() > 0
    assert server.running()
    assert len(server.threads) == 2
    assert all(thread.is_alive() for thread in server.threads)

    with pytest.raises(RuntimeError, match="after the server has started"):
        server.bind("late", lambda tensor: tensor, batch_size=1)
    with pytest.raises(RuntimeError, match="only be called once"):
        server.run()

    server.stop()
    server.stop()
    _call_with_timeout(server.wait)
    _call_with_timeout(server.wait)

    assert not server.running()
    assert all(not thread.is_alive() for thread in server.threads)


def test_server_rejects_invalid_worker_configuration() -> None:
    server = postman.Server("127.0.0.1:0")

    with pytest.raises(TypeError, match="callable"):
        server.bind("invalid", object(), batch_size=1)
    for num_threads in (0, -1, True, 1.5):
        with pytest.raises(ValueError, match="positive integer"):
            server.bind(
                f"invalid_threads_{num_threads}",
                lambda tensor: tensor,
                batch_size=1,
                num_threads=num_threads,
            )

    # Stopping a server that was never started is a safe no-op.
    server.stop()
    server.stop()
    with pytest.raises(RuntimeError, match="has not been run"):
        server.wait()


def test_remote_function_error_does_not_kill_worker() -> None:
    def validate(tensor: torch.Tensor) -> torch.Tensor:
        if torch.any(tensor < 0):
            raise ValueError("negative values are not accepted")
        return tensor + 1

    server = postman.Server("127.0.0.1:0")
    server.bind("validate", validate, batch_size=1)
    server.run()
    try:
        client = _connected_client(server)
        with pytest.raises(ValueError, match="negative values are not accepted"):
            client.validate(torch.tensor(-1))
        torch.testing.assert_close(client.validate(torch.tensor(2)), torch.tensor(3))
        assert server.threads[0].is_alive()
    finally:
        _stop_and_wait(server)


def test_bind_queue_batched_supports_runtime_batch_size_changes() -> None:
    initial_batch_size = 3
    final_batch_size = 2
    computation_queue = postman.ComputationQueue(batch_size=initial_batch_size)
    server = postman.Server("127.0.0.1:0")
    server.bind_queue_batched("identity", computation_queue)
    server.run()

    outcomes: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def run_client() -> None:
        try:
            client = _connected_client(server)
            first = client.identity(torch.arange(initial_batch_size * 2).reshape(-1, 2))
            second = client.identity(torch.arange(final_batch_size * 2).reshape(-1, 2))
            outcomes.put((True, (first, second)))
        except Exception as error:  # noqa: BLE001 - forward failures to the test thread.
            outcomes.put((False, error))

    client_thread = threading.Thread(target=run_client, name="postman-batched-client", daemon=True)
    client_thread.start()

    try:
        with computation_queue.get(wait_till_full=True) as computation:
            inputs = computation.get_inputs()[0]
            computation.set_outputs(inputs)

        computation_queue.set_batch_size(final_batch_size)

        with computation_queue.get(wait_till_full=True) as computation:
            inputs = computation.get_inputs()[0]
            computation.set_outputs(inputs)

        client_thread.join(RPC_TIMEOUT_SECONDS)
        assert not client_thread.is_alive(), "batched RPC client timed out"
        succeeded, outcome = outcomes.get_nowait()
        if not succeeded:
            raise outcome

        first, second = outcome
        torch.testing.assert_close(
            first,
            torch.arange(initial_batch_size * 2).reshape(-1, 2),
        )
        torch.testing.assert_close(
            second,
            torch.arange(final_batch_size * 2).reshape(-1, 2),
        )
    finally:
        computation_queue.close()
        _stop_and_wait(server)


@pytest.mark.parametrize("client_kind", ["sync", "async"])
def test_connect_releases_gil_while_waiting_for_server(client_kind: str) -> None:
    address = _unused_local_address()
    server = postman.Server(address)
    delayed_start_ready = threading.Event()
    startup_outcomes: queue.Queue[Exception | None] = queue.Queue(maxsize=1)

    def start_server_later() -> None:
        delayed_start_ready.set()
        time.sleep(0.1)
        try:
            server.run()
            startup_outcomes.put(None)
        except Exception as error:  # noqa: BLE001 - forward failures to the test thread.
            startup_outcomes.put(error)

    startup_thread = threading.Thread(
        target=start_server_later,
        name=f"postman-delayed-{client_kind}-server",
        daemon=True,
    )
    startup_thread.start()
    assert delayed_start_ready.wait(RPC_TIMEOUT_SECONDS)

    streams: Any | None = None
    client: Any
    try:
        if client_kind == "sync":
            client = postman.Client(address)
            client.connect(3)
        else:
            client = postman.AsyncClient(address)
            streams = client.connect(3)

        startup_thread.join(RPC_TIMEOUT_SECONDS)
        assert not startup_thread.is_alive(), "delayed server startup timed out"
        startup_error = startup_outcomes.get_nowait()
        if startup_error is not None:
            raise startup_error
    finally:
        startup_thread.join(RPC_TIMEOUT_SECONDS)
        if streams is not None:
            _call_with_timeout(streams.close)
        if client_kind == "sync" and "client" in locals():
            _call_with_timeout(client.close)
        if server.running():
            _stop_and_wait(server)


def test_computation_queue_rpc_can_wait_longer_than_five_seconds() -> None:
    computation_queue = postman.ComputationQueue(batch_size=1, max_pending_batches=2)
    server = postman.Server("127.0.0.1:0")
    server.bind_queue("identity", computation_queue)
    server.run()
    client = _connected_client(server)
    outcomes: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def run_client() -> None:
        try:
            outcomes.put((True, client.identity(torch.tensor(7))))
        except Exception as error:  # noqa: BLE001 - forward failures to the test thread.
            outcomes.put((False, error))

    client_thread = threading.Thread(
        target=run_client,
        name="postman-slow-computation-client",
        daemon=True,
    )
    client_thread.start()

    try:
        with computation_queue.get(wait_till_full=True) as computation:
            inputs = computation.get_inputs()[0]
            time.sleep(5.25)
            computation.set_outputs(inputs)

        client_thread.join(RPC_TIMEOUT_SECONDS)
        assert not client_thread.is_alive(), "slow queued RPC timed out"
        succeeded, outcome = outcomes.get_nowait()
        if not succeeded:
            raise outcome
        torch.testing.assert_close(outcome, torch.tensor(7))
    finally:
        computation_queue.close()
        _call_with_timeout(client.close)
        _stop_and_wait(server)
