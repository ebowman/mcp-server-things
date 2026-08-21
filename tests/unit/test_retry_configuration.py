"""Behavioral tests for AppleScript retry configuration."""

from unittest.mock import AsyncMock, patch

import pytest

from things_mcp.services.applescript.executor import AppleScriptExecutor
from things_mcp.main import create_parser
from things_mcp.server import ThingsMCPServer
from things_mcp.config import ThingsMCPConfig


@pytest.mark.asyncio
async def test_zero_retries_still_executes_once():
    """Zero retries means one attempt, not zero attempts."""
    executor = AppleScriptExecutor(retry_count=0)
    executor._execute_script = AsyncMock(
        return_value={"success": False, "error": "temporary failure"}
    )

    with patch("asyncio.sleep") as sleep:
        result = await executor.execute_script("return false")

    assert executor._execute_script.await_count == 1
    sleep.assert_not_called()
    assert result == {
        "success": False,
        "error": "Failed after 1 attempt: temporary failure",
    }


def test_config_disables_automatic_retries_by_default():
    """Potentially mutating AppleScript calls are attempted once by default."""
    args = create_parser().parse_args([])

    assert args.retry_count is None
    assert ThingsMCPConfig().applescript_retry_count == 0


def test_server_applies_execution_overrides_to_applescript_manager():
    """CLI execution settings reach the adapter that performs writes."""
    with patch("things_mcp.server.AppleScriptManager") as manager:
        server = ThingsMCPServer(timeout=17, retry_count=0)

    manager.assert_called_once_with(timeout=17, retry_count=0, config=server.config)
