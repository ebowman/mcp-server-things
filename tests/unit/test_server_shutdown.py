"""Tests for clean server shutdown after the MCP event loop exits."""

import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest

from things_mcp.server import ThingsMCPServer


def test_stop_cleans_up_after_event_loop_has_closed(caplog):
    """A normal stdio disconnect must not leave cleanup without an event loop."""
    server = object.__new__(ThingsMCPServer)
    try:
        previous_loop = asyncio.get_event_loop()
    except RuntimeError:
        previous_loop = None

    try:
        asyncio.set_event_loop(None)
        with patch(
            "things_mcp.server.shutdown_operation_queue", new_callable=AsyncMock
        ) as shutdown:
            with caplog.at_level(logging.ERROR, logger="things_mcp.server"):
                server.stop()
    finally:
        asyncio.set_event_loop(previous_loop)

    shutdown.assert_awaited_once_with()
    assert "Error stopping operation queue" not in caplog.text


@pytest.mark.asyncio
async def test_stop_schedules_cleanup_on_running_event_loop():
    """Stopping inside FastMCP's loop must not try to nest a new event loop."""
    server = object.__new__(ThingsMCPServer)
    cleaned_up = asyncio.Event()

    async def cleanup():
        cleaned_up.set()

    with patch(
        "things_mcp.server.shutdown_operation_queue",
        new_callable=AsyncMock,
        side_effect=cleanup,
    ) as shutdown:
        server.stop()
        await asyncio.wait_for(cleaned_up.wait(), timeout=1)

    shutdown.assert_awaited_once_with()
