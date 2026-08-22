"""Unit tests for hq-yxu: AppleScriptExecutor's serialization lock must not
bind itself to a single event loop.

Background: AppleScriptExecutor._applescript_lock used to be a single
class-level asyncio.Lock() created at import time. CPython's asyncio.Lock
only binds its internal loop reference on a CONTENDED acquire (a second
waiter queueing while the lock is already held) - an uncontended acquire
never binds. Once a contended acquire happens on event loop A, the lock is
permanently bound to loop A; a later contended acquire from a *different*
loop B then raises "RuntimeError: ... is bound to a different event loop"
instead of serializing, poisoning the executor for the rest of the process.

This is the exact scenario the regression harness hits: each mcp.call_sync
runs in its own asyncio.run() loop, and bulk_move_records with
max_concurrent > 1 creates genuine intra-loop contention.

Fix (mirrors hq-5xa's operation_queue fix): key the lock by the currently
running event loop in a weakref.WeakKeyDictionary, lazily creating one Lock
per loop at acquire time via AppleScriptExecutor._get_lock().

Every test that spans multiple event loops runs the actual asyncio.run()
calls in a background thread and joins with a hard timeout, so a regression
to hanging/poisoning behavior fails the test instead of wedging the suite.
"""

from __future__ import annotations

import asyncio
import queue as thread_queue
import threading
from unittest.mock import AsyncMock, patch

import pytest

from things_mcp.services.applescript.executor import AppleScriptExecutor


def _run_in_thread(coro_factory, timeout: float = 10.0):
    """Run `asyncio.run(coro_factory())` in a background thread, joined with
    a hard timeout.

    Returns the coroutine's return value, or raises AssertionError if the
    thread is still alive after `timeout` seconds (i.e. it hung), or
    re-raises any exception the coroutine raised (including a RuntimeError
    from a poisoned cross-loop lock).
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
            "AppleScriptExecutor cross-loop hang regression (hq-yxu)"
        )

    status, payload = result_box.get_nowait()
    if status == "error":
        raise payload
    return payload


def _mock_subprocess_exec_factory(sleep_seconds: float = 0.0):
    """Build a stand-in for asyncio.create_subprocess_exec that returns a
    fake process whose communicate() optionally sleeps, letting us create
    genuine intra-loop contention on the executor's lock.
    """

    async def _fake_create_subprocess_exec(*args, **kwargs):
        process = AsyncMock()

        async def _communicate():
            if sleep_seconds:
                await asyncio.sleep(sleep_seconds)
            return (b"ok", b"")

        process.communicate = _communicate
        process.returncode = 0
        process.kill = lambda: None
        process.wait = AsyncMock(return_value=0)
        return process

    return _fake_create_subprocess_exec


class TestAppleScriptExecutorCrossLoop:
    def test_contended_acquire_in_two_different_loops_does_not_raise(self):
        """The core hq-yxu regression: a contended acquire (two concurrent
        executions racing for the lock) in loop A, followed by a contended
        acquire in a fresh loop B, must both complete without
        'bound to a different event loop' RuntimeError."""

        async def _contended_round():
            executor = AppleScriptExecutor(timeout=5, retry_count=1)
            with patch(
                "asyncio.create_subprocess_exec",
                new=_mock_subprocess_exec_factory(sleep_seconds=0.05),
            ):
                # Two concurrent executions on the same loop force a
                # contended acquire on the per-loop lock.
                results = await asyncio.gather(
                    executor.execute_script('tell application "Things3" to return 1'),
                    executor.execute_script('tell application "Things3" to return 2'),
                )
            return [r["success"] for r in results]

        first = _run_in_thread(_contended_round, timeout=10.0)
        second = _run_in_thread(_contended_round, timeout=10.0)

        assert first == [True, True]
        assert second == [True, True]

    def test_same_loop_repeat_uses_same_lock_instance(self):
        """Within a single running loop, repeated _get_lock() calls must
        keep returning the identical Lock instance (unchanged single-loop
        behavior)."""

        async def _same_loop_check():
            lock1 = AppleScriptExecutor._get_lock()
            lock2 = AppleScriptExecutor._get_lock()
            return lock1 is lock2

        identical = _run_in_thread(_same_loop_check, timeout=10.0)
        assert identical is True

    def test_two_loops_get_distinct_lock_instances(self):
        """Two different, simultaneously alive event loops (run in parallel
        threads, synchronized with a barrier so neither Lock is garbage
        collected before the other is created) must each get their own Lock
        instance."""

        barrier = threading.Barrier(2, timeout=10.0)

        async def _get_lock_identity():
            lock = AppleScriptExecutor._get_lock()
            lock_id = id(lock)

            # Hold a reference (via the closure) until the other thread has
            # also created and inspected its own lock, so both objects are
            # guaranteed to coexist when we compare ids below.
            await asyncio.get_event_loop().run_in_executor(None, barrier.wait)
            return lock_id

        results: dict = {}
        errors: dict = {}

        def _worker(key):
            try:
                results[key] = asyncio.run(_get_lock_identity())
            except BaseException as exc:  # noqa: BLE001 - surface to main thread
                errors[key] = exc

        t1 = threading.Thread(target=_worker, args=("loop1",), daemon=True)
        t2 = threading.Thread(target=_worker, args=("loop2",), daemon=True)
        t1.start()
        t2.start()
        t1.join(timeout=15.0)
        t2.join(timeout=15.0)

        assert not t1.is_alive(), "loop1 thread did not complete - cross-loop hang regression (hq-yxu)"
        assert not t2.is_alive(), "loop2 thread did not complete - cross-loop hang regression (hq-yxu)"
        if errors:
            raise next(iter(errors.values()))
        assert "loop1" in results and "loop2" in results
        assert results["loop1"] != results["loop2"]

    def test_serialization_still_holds_within_a_loop(self):
        """Two concurrent executions within the same loop must never overlap
        - the lock still serializes AppleScript calls within a single event
        loop, exactly as before this change."""

        async def _check_serialization():
            executor = AppleScriptExecutor(timeout=5, retry_count=1)
            active_count = 0
            max_observed = 0
            order: list = []

            async def _fake_create_subprocess_exec(*args, **kwargs):
                nonlocal active_count, max_observed
                process = AsyncMock()

                async def _communicate():
                    nonlocal active_count, max_observed
                    active_count += 1
                    max_observed = max(max_observed, active_count)
                    order.append("start")
                    await asyncio.sleep(0.05)
                    order.append("end")
                    active_count -= 1
                    return (b"ok", b"")

                process.communicate = _communicate
                process.returncode = 0
                process.kill = lambda: None
                process.wait = AsyncMock(return_value=0)
                return process

            with patch("asyncio.create_subprocess_exec", new=_fake_create_subprocess_exec):
                results = await asyncio.gather(
                    executor.execute_script('tell application "Things3" to return 1'),
                    executor.execute_script('tell application "Things3" to return 2'),
                    executor.execute_script('tell application "Things3" to return 3'),
                )

            return max_observed, order, [r["success"] for r in results]

        max_observed, order, successes = _run_in_thread(_check_serialization, timeout=10.0)

        # Never more than one execution "in flight" (holding the lock) at once.
        assert max_observed == 1
        # Each start must be immediately followed by its own end before the
        # next start begins - a fully serialized start/end/start/end/... order.
        assert order == ["start", "end", "start", "end", "start", "end"]
        assert successes == [True, True, True]
