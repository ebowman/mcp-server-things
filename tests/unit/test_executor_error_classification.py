"""Retry classification for AppleScript executor failures (hq-5j4)."""

from unittest.mock import AsyncMock, patch

import pytest

from things_mcp.services.applescript.executor import (
    AppleScriptExecutor,
    is_transient_error,
)

TRANSIENT = [
    "Script execution timed out after 45s",
    "Execution error: [Errno 24] Too many open files",
    "execution error: Things3 got an error: AppleEvent timed out. (-1712)",
    "Things3 got an error (-1712)",
    "Application isn't running. (-600)",
    "Things is not running",
    "Connection is invalid. (-609)",
    "Can't launch app (-10810)",
    "",
    None,
    "Unknown AppleScript error",
]

DETERMINISTIC = [
    'execution error: Things3 got an error: Can\'t get to do id "abc". (-1728)',
    "syntax error: Expected end of line but found identifier. (-2741)",
    "execution error: The variable foo is not defined. (-2753)",
    "execution error: Can't make \"x\" into type integer. (-1700)",
    "execution error: Things3 got an error: Invalid date and time (-30720)",
    "Invalid date",
    "Can't get date \"x\"",
    "execution error: Things3 doesn't understand the foo message. (-1708)",
    "Expected \"end\" but found \"tell\"",
    "A property can't go after this identifier.",
    "value can't be converted to type date",
]


@pytest.mark.parametrize("error", TRANSIENT)
def test_is_transient_error_true(error):
    assert is_transient_error(error) is True


@pytest.mark.parametrize("error", DETERMINISTIC)
def test_is_transient_error_false(error):
    assert is_transient_error(error) is False


def test_code_token_regex_requires_parenthesized_form():
    # "1712" / "-600" inside a title, without the "(-NNNN)" token, does not
    # match the code regex; it is deterministic (not transient) by default.
    assert is_transient_error('Can\'t get to do "Task 1712 -600 -609"') is False
    # A deterministic code token is not misread either.
    assert is_transient_error("Can't get to do id \"Task 1728\" (-1728)") is False


async def _run(retry_count, results):
    executor = AppleScriptExecutor(timeout=5, retry_count=retry_count)
    with patch.object(
        executor, "_execute_script", new=AsyncMock(side_effect=results)
    ) as ex, patch("asyncio.sleep", new=AsyncMock()) as sleep:
        result = await executor.execute_script("return 1")
    return result, ex.call_count, sleep.call_count


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [e for e in TRANSIENT if e is not None])
async def test_transient_errors_are_retried(error):
    fail = {"success": False, "error": error}
    result, calls, sleeps = await _run(2, [fail] * 5)
    assert calls == 3
    assert sleeps == 2
    assert result["success"] is False
    assert "Failed after 3 attempt(s)" in result["error"]


@pytest.mark.asyncio
async def test_missing_error_key_is_retried():
    result, calls, sleeps = await _run(2, [{"success": False}] * 5)
    assert calls == 3 and sleeps == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("error", DETERMINISTIC)
async def test_deterministic_errors_fail_after_one_attempt(error):
    result, calls, sleeps = await _run(2, [{"success": False, "error": error}] * 5)
    assert calls == 1
    assert sleeps == 0
    assert result["success"] is False
    assert "Failed after 1 attempt(s)" in result["error"]
    assert error in result["error"]


@pytest.mark.asyncio
async def test_transient_then_success_recovers():
    result, calls, sleeps = await _run(
        2,
        [
            {"success": False, "error": "Script execution timed out after 5s"},
            {"success": True, "output": "ok"},
        ],
    )
    assert result["success"] is True
    assert calls == 2 and sleeps == 1


@pytest.mark.asyncio
async def test_error_prefixed_stdout_still_retried():
    """hq-c7a regression guard: rc=0 'ERROR:' stdout keeps being retried."""
    bad = {"success": True, "output": "ERROR: Can't get to do id \"x\". (-1728)"}
    result, calls, sleeps = await _run(2, [bad] * 5)
    assert calls == 3
    assert sleeps == 2
    assert result == bad


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", ["Script execution timed out after 5s", "Invalid date and time"]
)
async def test_retry_count_zero_single_attempt(error):
    result, calls, sleeps = await _run(0, [{"success": False, "error": error}] * 3)
    assert calls == 1 and sleeps == 0
    assert "Failed after 1 attempt(s)" in result["error"]
