"""Behavioral tests for AppleScript CLI execution configuration."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from things_mcp.config import ThingsMCPConfig
from things_mcp.main import ServerManager, create_parser, main
from things_mcp.server import ThingsMCPServer


def test_server_manager_forwards_cli_execution_settings():
    """Normal startup forwards explicit CLI settings to the live server."""
    with patch("things_mcp.main.ThingsMCPServer") as server_class:
        manager = ServerManager()
        manager.start(timeout=17, retry_count=2)

    server_class.assert_called_once_with(
        env_file=None,
        timeout=17,
        retry_count=2,
    )


def test_omitted_cli_settings_preserve_loaded_configuration():
    """Omitted CLI flags remain unset so environment configuration can win."""
    args = create_parser().parse_args([])

    assert args.timeout is None
    assert args.retry_count is None


def test_health_check_uses_loaded_execution_configuration():
    """Utility commands resolve omitted CLI values from the same configuration."""
    config = ThingsMCPConfig(
        applescript_timeout=19.5,
        applescript_retry_count=4,
    )
    health_check = AsyncMock(return_value=0)

    with patch("sys.argv", ["things-mcp", "--health-check"]), patch(
        "things_mcp.main.arm_boot_watchdog"
    ), patch("things_mcp.main.load_config_from_env", return_value=config), patch(
        "things_mcp.main.perform_health_check", health_check
    ):
        result = main()

    assert result == 0
    health_check.assert_awaited_once_with(19.5, 4)


def test_server_applies_execution_overrides_to_applescript_manager():
    """CLI execution settings reach the adapter that performs writes."""
    with patch("things_mcp.server.AppleScriptManager") as manager:
        server = ThingsMCPServer(timeout=17, retry_count=2)

    manager.assert_called_once_with(timeout=17, retry_count=2, config=server.config)


def test_server_applies_loaded_execution_config_without_overrides():
    """Loaded timeout and retry settings reach the executor when CLI omits them."""
    config = ThingsMCPConfig(
        applescript_timeout=19.5,
        applescript_retry_count=4,
    )

    with patch("things_mcp.server.load_config_from_env", return_value=config), patch(
        "things_mcp.server.AppleScriptManager"
    ) as manager:
        server = ThingsMCPServer()

    manager.assert_called_once_with(timeout=19.5, retry_count=4, config=server.config)


@pytest.mark.parametrize(
    "override",
    [
        {"timeout": 0},
        {"retry_count": 11},
    ],
)
def test_server_validates_execution_overrides(override):
    """CLI overrides obey the same bounds as environment configuration."""
    with patch("things_mcp.server.AppleScriptManager") as manager:
        with pytest.raises(ValidationError):
            ThingsMCPServer(**override)

    manager.assert_not_called()


# --- Issue #17: retry_count means retries after the initial attempt ---

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from things_mcp.services.applescript.executor import AppleScriptExecutor


def _failing_process():
    proc = AsyncMock()
    proc.communicate.return_value = (b"", b"boom")
    proc.returncode = 1
    return proc


def _ok_process():
    proc = AsyncMock()
    proc.communicate.return_value = (b"fine", b"")
    proc.returncode = 0
    return proc


async def _run(executor, procs):
    with patch("asyncio.create_subprocess_exec", side_effect=procs) as create, \
         patch("asyncio.sleep") as sleep:
        result = await executor.execute_script('return 1')
    return result, create.call_count, sleep.call_count


@pytest.mark.asyncio
async def test_retry_count_zero_runs_exactly_once_without_sleep():
    result, runs, sleeps = await _run(
        AppleScriptExecutor(timeout=5, retry_count=0),
        [_failing_process() for _ in range(5)],
    )
    assert runs == 1
    assert sleeps == 0
    assert result["success"] is False
    assert "Failed after 1 attempt(s)" in result["error"]


@pytest.mark.asyncio
async def test_retry_count_one_runs_twice_with_one_sleep():
    result, runs, sleeps = await _run(
        AppleScriptExecutor(timeout=5, retry_count=1),
        [_failing_process() for _ in range(5)],
    )
    assert runs == 2
    assert sleeps == 1
    assert "Failed after 2 attempt(s)" in result["error"]


@pytest.mark.asyncio
async def test_success_on_first_try_runs_once():
    result, runs, sleeps = await _run(
        AppleScriptExecutor(timeout=5, retry_count=3),
        [_ok_process() for _ in range(5)],
    )
    assert result["success"] is True
    assert runs == 1
    assert sleeps == 0


@pytest.mark.asyncio
async def test_default_executor_makes_three_total_attempts():
    executor = AppleScriptExecutor(timeout=5)
    assert executor.retry_count == 2
    result, runs, sleeps = await _run(
        executor, [_failing_process() for _ in range(5)]
    )
    assert runs == 3
    assert sleeps == 2
    assert "Failed after 3 attempt(s)" in result["error"]


def test_negative_retry_count_raises_value_error():
    with pytest.raises(ValueError):
        AppleScriptExecutor(timeout=5, retry_count=-1)


def test_config_default_retry_count_is_two_and_zero_allowed():
    from things_mcp.config import ThingsMCPConfig

    assert ThingsMCPConfig().applescript_retry_count == 2
    assert ThingsMCPConfig(applescript_retry_count=0).applescript_retry_count == 0
