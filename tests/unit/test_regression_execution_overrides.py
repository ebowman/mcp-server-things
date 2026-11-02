"""Offline execution-setting checks on the real regression server."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from regression.conftest import live_server
from things_mcp.server import ThingsMCPServer


@pytest.mark.parametrize(
    ("timeout", "retry_count"),
    [(None, None), ("90", None), (None, "0"), ("90", "0")],
)
def test_fixture_execution_overrides(
    timeout: str | None, retry_count: str | None
) -> None:
    """Keep normal config precedence and propagate zero to the executor."""
    # Restore even environment changes made by the real dotenv loader.
    with patch.dict(os.environ):
        os.environ.pop("THINGS_MCP_REG_APPLESCRIPT_TIMEOUT", None)
        os.environ.pop("THINGS_MCP_REG_APPLESCRIPT_RETRY_COUNT", None)
        baseline = ThingsMCPServer()
        if timeout is not None:
            os.environ["THINGS_MCP_REG_APPLESCRIPT_TIMEOUT"] = timeout
        if retry_count is not None:
            os.environ["THINGS_MCP_REG_APPLESCRIPT_RETRY_COUNT"] = retry_count

        # Invoke only the fixture body: no live probe, sandbox or MCP calls.
        server = live_server.__wrapped__()

        expected_timeout = (
            float(timeout)
            if timeout is not None
            else baseline.config.applescript_timeout
        )
        expected_retries = (
            int(retry_count)
            if retry_count is not None
            else baseline.config.applescript_retry_count
        )
        assert server.config.applescript_timeout == expected_timeout
        assert server.config.applescript_retry_count == expected_retries
        assert server.applescript_manager.timeout == expected_timeout
        assert server.applescript_manager.retry_count == expected_retries
        executor = server.applescript_manager.executor
        assert executor.timeout == expected_timeout
        assert executor.retry_count == expected_retries
        execution_fields = {"applescript_timeout", "applescript_retry_count"}
        assert server.config.model_dump(
            exclude=execution_fields
        ) == baseline.config.model_dump(exclude=execution_fields)
        # The REG settings must not affect ordinary server construction.
        ordinary = ThingsMCPServer()
        assert ordinary.config == baseline.config


@pytest.mark.parametrize(
    ("setting", "value", "error"),
    [
        ("TIMEOUT", "", ValueError),
        ("TIMEOUT", "invalid", ValueError),
        ("TIMEOUT", "0", ValidationError),
        ("TIMEOUT", "301", ValidationError),
        ("TIMEOUT", "nan", ValidationError),
        ("TIMEOUT", "inf", ValidationError),
        ("RETRY_COUNT", "", ValueError),
        ("RETRY_COUNT", "1.5", ValueError),
        ("RETRY_COUNT", "-1", ValidationError),
        ("RETRY_COUNT", "11", ValidationError),
    ],
)
def test_fixture_rejects_invalid_execution_overrides(
    setting: str, value: str, error: type[Exception]
) -> None:
    """Parsing and the constructor's real validation must fail loudly."""
    with patch.dict(os.environ):
        os.environ.pop("THINGS_MCP_REG_APPLESCRIPT_TIMEOUT", None)
        os.environ.pop("THINGS_MCP_REG_APPLESCRIPT_RETRY_COUNT", None)
        os.environ[f"THINGS_MCP_REG_APPLESCRIPT_{setting}"] = value
        with pytest.raises(error):
            live_server.__wrapped__()
