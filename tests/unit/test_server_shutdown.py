"""Tests for operation-queue cleanup when the MCP server disconnects."""

import pytest
from fastmcp import Client

from things_mcp.operation_queue import get_operation_queue, shutdown_operation_queue
from things_mcp.server import ThingsMCPServer


@pytest.mark.asyncio
async def test_client_disconnect_stops_current_event_loop_queue():
    """Closing a client releases the queue owned by that server event loop."""
    server = ThingsMCPServer()

    async with Client(server.mcp):
        queue_during_session = await get_operation_queue()

    queue_after_disconnect = await get_operation_queue()
    try:
        assert queue_after_disconnect is not queue_during_session
    finally:
        await shutdown_operation_queue()
