#
# Copyright (c) Meta Platforms, Inc. and affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.
#
from __future__ import annotations

import threading
import traceback
from collections.abc import Callable
from typing import Any

from postman import rpc


def _target(
    queue: Any,
    function: Callable[..., Any],
    wait_till_full: bool,
    failure_callback: Callable[[Exception, str], None] | None = None,
) -> None:
    try:
        while True:
            with queue.get(wait_till_full=wait_till_full) as batch:
                batch.set_outputs(function(*batch.get_inputs()))
    except StopIteration:
        return
    except Exception as error:
        if failure_callback is None:
            raise
        failure_callback(error, traceback.format_exc())


class Server(rpc.Server):
    """RPC server with managed Python batching workers.

    A server is deliberately one-shot: functions are bound before ``run()``,
    and ``run()`` starts each configured worker exactly once. ``stop()`` and
    ``wait()`` are idempotent so cleanup can be unconditional in ``finally``
    blocks.
    """

    def __init__(self, address: str) -> None:
        super().__init__(address)
        self.threads: list[threading.Thread] = []
        self.queues: list[Any] = []

        self._lifecycle_lock = threading.RLock()
        self._wait_lock = threading.Lock()
        self._run_started = False
        self._rpc_started = False
        self._stop_requested = False
        self._wait_complete = False
        self._started_threads: list[threading.Thread] = []
        self._worker_failures: list[tuple[str, Exception, str]] = []
        self._run_failure: Exception | None = None

    def bind(
        self,
        name: str,
        function: Callable[..., Any],
        batch_size: int,
        num_threads: int = 1,
        wait_till_full: bool = False,
    ) -> None:
        if not callable(function):
            raise TypeError("function must be callable")
        if not isinstance(num_threads, int) or isinstance(num_threads, bool) or num_threads < 1:
            raise ValueError("num_threads must be a positive integer")

        with self._lifecycle_lock:
            if self._run_started:
                raise RuntimeError("Cannot bind functions after the server has started")

            queue = rpc.ComputationQueue(batch_size)
            self.bind_queue(name, queue)
            self.queues.append(queue)

            for index in range(num_threads):
                self.threads.append(
                    threading.Thread(
                        target=_target,
                        name=f"postman-{name}-{index}",
                        args=(
                            queue,
                            function,
                            wait_till_full,
                            self._record_worker_failure,
                        ),
                    )
                )

    def _record_worker_failure(self, error: Exception, formatted_traceback: str) -> None:
        thread_name = threading.current_thread().name
        with self._lifecycle_lock:
            self._worker_failures.append((thread_name, error, formatted_traceback))

        # A dead batching worker cannot serve its queue reliably. Shutting down
        # the server also guarantees that a thread blocked in wait() wakes up.
        try:
            self.stop()
        except RuntimeError as stop_error:
            with self._lifecycle_lock:
                self._worker_failures.append(
                    (
                        thread_name,
                        stop_error,
                        "Server cleanup failed after a worker failure",
                    )
                )

    def _raise_worker_failure(self) -> None:
        with self._lifecycle_lock:
            failures = tuple(self._worker_failures)
        if not failures:
            return

        details = "\n\n".join(
            f"{thread_name}: {error}\n{formatted_traceback}"
            for thread_name, error, formatted_traceback in failures
        )
        first_error = failures[0][1]
        raise RuntimeError(
            f"{len(failures)} Postman worker failure(s):\n{details}"
        ) from first_error

    def stop(self) -> None:
        with self._lifecycle_lock:
            if not self._run_started or self._stop_requested:
                return
            self._stop_requested = True
            queues = tuple(self.queues)
            stop_rpc = self._rpc_started

        cleanup_errors: list[RuntimeError] = []
        for queue in queues:
            try:
                queue.close()
            except RuntimeError as error:
                cleanup_errors.append(error)

        if stop_rpc:
            try:
                super().stop()
            except RuntimeError as error:
                cleanup_errors.append(error)

        if cleanup_errors:
            raise RuntimeError("Failed to stop the Postman server cleanly") from cleanup_errors[0]

    def run(self) -> None:
        with self._lifecycle_lock:
            if self._run_started:
                raise RuntimeError("Server.run() may only be called once")
            self._run_started = True

            try:
                super().run()
                self._rpc_started = True
                for thread in self.threads:
                    thread.start()
                    self._started_threads.append(thread)
            except Exception as error:
                self._run_failure = error
                try:
                    self.stop()
                except RuntimeError as cleanup_error:
                    error.add_note(f"Server cleanup also failed: {cleanup_error}")
                raise

    def wait(self) -> None:
        with self._wait_lock:
            with self._lifecycle_lock:
                if self._wait_complete:
                    self._raise_worker_failure()
                    return
                if not self._run_started:
                    raise RuntimeError("Cannot wait for a server that has not been run")
                if self._run_failure is not None:
                    raise RuntimeError("The Postman server failed to start") from self._run_failure
                wait_rpc = self._rpc_started
                started_threads = tuple(self._started_threads)

            if wait_rpc:
                super().wait()
            for thread in started_threads:
                thread.join()

            with self._lifecycle_lock:
                self._wait_complete = True
            self._raise_worker_failure()
