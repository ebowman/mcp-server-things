"""MCP-boundary tests for structured write-error signaling."""

from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client

from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.server import ThingsMCPServer
from things_mcp.tools import ThingsTools


def _server_with_url_scheme_result(payload: Dict[str, Any]) -> ThingsMCPServer:
    manager = Mock(spec=AppleScriptManager)
    manager.execute_url_scheme = AsyncMock(return_value=payload)
    server = ThingsMCPServer()
    server.tools = ThingsTools(manager)
    return server


@pytest.mark.asyncio
async def test_structured_write_failure_is_an_mcp_tool_error():
    payload = {
        "success": False,
        "error": "AUTH_TOKEN_NOT_CONFIGURED",
        "message": "Things URL-scheme auth token not configured",
        "hint": "Configure the Things auth token",
    }
    client = Client(_server_with_url_scheme_result(payload).mcp)

    async with client:
        result = await client.call_tool_mcp(
            "replace_checklist_items",
            {"todo_id": "TODO-1", "items": ["one"]},
        )

    assert result.isError is True
    assert result.structuredContent == payload


@pytest.mark.asyncio
async def test_successful_write_payload_is_unchanged():
    client = Client(_server_with_url_scheme_result({"success": True}).mcp)

    async with client:
        result = await client.call_tool_mcp(
            "replace_checklist_items", {"todo_id": "TODO-1", "items": ["one"]}
        )

    assert result.isError is False
    assert result.structuredContent == {
        "success": True,
        "message": "Replaced checklist with 1 items",
        "items_count": 1,
    }
