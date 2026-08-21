"""Unit tests for hq-5xa: operation_queue must not bind its singleton to a
single event loop.

Background: get_operation_queue() used to hold a single module-level
OperationQueue instance whose worker task was created via
asyncio.create_task() - permanently binding that task to whichever event
loop was running at creation time. A second, later asyncio.run() call (a
fresh event loop) reusing that same instance would await/cancel a worker
task that belongs to a *different, closed* loop, which hangs instead of
completing.

Fix: key the queue by the currently-running event loop
(asyncio.get_running_loop()) in a WeakKeyDictionary, so each loop gets its
own OperationQueue + worker. Note: an *abandoned* loop's dict entry is not
actually garbage-collected by this alone - the still-running worker Task
strongly references its own loop (Task._loop), pinning the WeakKeyDictionary
key for the life of the process. This is a small, bounded leak (one inert
entry per abandoned loop), not unbounded growth or a hang.
shutdown_operation_queue() avoids even that for callers that control their
own loop lifecycle, by explicitly popping and stopping the current loop's
entry before the loop is discarded.

Every test here runs the actual asyncio.run() calls in a background thread
and joins with a hard timeout, so a regression to the old cross-loop-hang
behavior fails the test instead of wedging the whole suite.
"""

from __future__ import annotations

import asyncio
import queue as thread_queue
import threading

import pytest

from things_mcp.operation_queue import get_operation_queue, shutdown_operation_queue


def _run_in_thread(coro_factory, timeout: float = 10.0):
    """Run `asyncio.run(coro_factory())` in a background thread, joined with
    a hard timeout.

    Returns the coroutine's return value, or raises AssertionError if the
    thread is still alive after `timeout` seconds (i.e. it hung), or
    re-raises any exception the coroutine raised.
    """
    result_box: "thread_queue.Queue" = thread_queue.Queue()

    def _target():
        try:
            value = asyncio.run(coro_factory())
            result_box.put(("ok", value))
        except BaseException as exc:  # noqa: BLE001 - propagate anything to the caller
            result_box.put(("error", exc))

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout=timeout)

    if thread.is_alive():
        raise AssertionError(
            f"asyncio.run() did not complete within {timeout}s - "
            "operation_queue cross-loop hang regression (hq-5xa)"
        )

    status, payload = result_box.get_nowait()
    if status == "error":
        raise payload
    return payload


async def _touch_queue_and_get_status() -> dict:
    """Minimal queue interaction exercising the same path queue_status uses:
    get_operation_queue() + enqueue + wait_for_operation + get_queue_status.
    """
    q = await get_operation_queue()

    async def _trivial_op():
        return "done"

    op_id = await q.enqueue(_trivial_op, name="hq-5xa-trivial")
    result = await q.wait_for_operation(op_id, timeout=5.0)
    status = q.get_queue_status()
    await shutdown_operation_queue()
    return {"result": result, "status": status}


class TestOperationQueueCrossLoop:
    def test_two_sequential_asyncio_run_calls_both_complete(self):
        """The core hq-5xa regression: two separate event loops, each doing
        get_operation_queue() + a trivial op, must both complete without
        hanging."""
        first = _run_in_thread(_touch_queue_and_get_status, timeout=10.0)
        second = _run_in_thread(_touch_queue_and_get_status, timeout=10.0)

        assert first["result"] == "done"
        assert second["result"] == "done"
        # get_queue_status() returns a stats dict; confirm the op we ran is
        # reflected rather than just checking truthiness of the whole call.
        assert first["status"]["statistics"]["total_operations"] == 1
        assert second["status"]["statistics"]["total_operations"] == 1

    def test_same_loop_returns_same_instance(self):
        """Within a single running loop, repeated get_operation_queue()
        calls must keep returning the identical instance (unchanged
        single-loop behavior)."""

        async def _same_loop_check():
            q1 = await get_operation_queue()
            q2 = await get_operation_queue()
            identical = q1 is q2
            worker_task_identical = q1._worker_task is q2._worker_task
            await shutdown_operation_queue()
            return identical, worker_task_identical

        identical, worker_task_identical = _run_in_thread(_same_loop_check, timeout=10.0)
        assert identical is True
        assert worker_task_identical is True

    def test_two_loops_each_get_a_functional_independent_queue(self):
        """Two different, *simultaneously alive* event loops (run in
        parallel threads, synchronized with a barrier so neither queue is
        garbage-collected before the other is created - a sequential
        create/destroy/create can coincidentally reuse the same CPython
        object id, which would make an id() comparison meaningless) must
        each get their own queue instance and worker task bound to their own
        loop, and each must be independently functional."""

        barrier = threading.Barrier(2, timeout=10.0)

        async def _get_queue_identity_and_run_op():
            q = await get_operation_queue()
            queue_id = id(q)
            worker_loop = q._worker_task.get_loop()
            running_loop = asyncio.get_running_loop()
            same_loop = worker_loop is running_loop

            # Hold this queue alive (don't shut down yet) until the other
            # thread has also created and inspected its own queue, so both
            # objects are guaranteed to coexist when we compare ids below.
            await asyncio.get_event_loop().run_in_executor(None, barrier.wait)

            async def _trivial_op():
                return "ok"

            op_id = await q.enqueue(_trivial_op, name="hq-5xa-independent")
            result = await q.wait_for_operation(op_id, timeout=5.0)
            await shutdown_operation_queue()
            return queue_id, same_loop, result

        results: dict = {}
        errors: dict = {}

        def _worker(key):
            try:
                results[key] = asyncio.run(_get_queue_identity_and_run_op())
            except BaseException as exc:  # noqa: BLE001 - surface to main thread
                errors[key] = exc

        # Run both asyncio.run() calls concurrently in separate threads, each
        # joined with a hard timeout, so a cross-loop hang regression fails
        # the test instead of wedging the suite.
        t1 = threading.Thread(target=_worker, args=("loop1",), daemon=True)
        t2 = threading.Thread(target=_worker, args=("loop2",), daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=15.0)
        t2.join(timeout=15.0)

        assert not t1.is_alive(), "loop1 thread did not complete - cross-loop hang regression (hq-5xa)"
        assert not t2.is_alive(), "loop2 thread did not complete - cross-loop hang regression (hq-5xa)"
        if errors:
            raise next(iter(errors.values()))
        assert "loop1" in results and "loop2" in results

        loop1_id, loop1_same, loop1_result = results["loop1"]
        loop2_id, loop2_same, loop2_result = results["loop2"]

        # Each loop's worker task is bound to that same loop (not a foreign one).
        assert loop1_same is True
        assert loop2_same is True
        # Distinct queue instances per loop (a worker task can't be shared
        # cross-loop, so the queues backing them must differ too). Both
        # objects are alive simultaneously (synchronized via the barrier
        # above), so this id() comparison cannot coincidentally collide due
        # to one having already been garbage-collected.
        assert loop1_id != loop2_id
        # Both loops' queues are independently functional.
        assert loop1_result == "ok"
        assert loop2_result == "ok"

    def test_repeated_loops_without_explicit_shutdown_do_not_hang(self):
        """Even if a caller never calls shutdown_operation_queue() before its
        asyncio.run() returns (abandoning the worker task when the loop
        closes), a subsequent asyncio.run() calling get_operation_queue()
        again must still complete promptly rather than hang trying to await
        a foreign, abandoned worker task."""

        async def _no_shutdown_touch():
            q = await get_operation_queue()

            async def _trivial_op():
                return 7

            op_id = await q.enqueue(_trivial_op, name="hq-5xa-no-shutdown")
            result = await q.wait_for_operation(op_id, timeout=5.0)
            # Deliberately do NOT call shutdown_operation_queue() here.
            return result

        first = _run_in_thread(_no_shutdown_touch, timeout=10.0)
        second = _run_in_thread(_no_shutdown_touch, timeout=10.0)

        assert first == 7
        assert second == 7
