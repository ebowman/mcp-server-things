"""Offline proof of the regression harness's MCP call contract (hq-090)."""

from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest
from fastmcp import Client

from regression.mcp_call import call_tool_structured
from things_mcp.server import ThingsMCPServer
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools


def _server(payload: Any = None, exc: Exception = None) -> ThingsMCPServer:
    manager = Mock(spec=AppleScriptManager)
    if exc is not None:
        manager.execute_url_scheme = AsyncMock(side_effect=exc)
    else:
        manager.execute_url_scheme = AsyncMock(return_value=payload)
    server = ThingsMCPServer()
    server.tools = ThingsTools(manager)
    return server


async def _call(server, tool, **kw) -> Dict[str, Any]:
    async with Client(server.mcp) as client:
        return await call_tool_structured(client, tool, kw)


@pytest.mark.asyncio
async def test_upper_snake_write_failure_returns_structured_dict():
    payload = {"success": False, "error": "AUTH_TOKEN_NOT_CONFIGURED", "message": "m", "hint": "h"}
    out = await _call(_server(payload), "replace_checklist_items", todo_id="T", items=["a"])
    assert out == payload


@pytest.mark.asyncio
async def test_success_returns_dict():
    out = await _call(_server({"success": True}), "replace_checklist_items", todo_id="T", items=["a"])
    assert out["success"] is True


@pytest.mark.asyncio
async def test_pydantic_validation_error_maps_to_tool_error():
    out = await _call(_server({"success": True}), "replace_checklist_items", todo_id="T", items="notalist")
    assert set(out) == {"tool_error"} and out["tool_error"]


@pytest.mark.asyncio
async def test_raised_tool_exception_maps_to_tool_error():
    server = _server()
    server.tools.get_todo_by_id = AsyncMock(side_effect=RuntimeError("boom from tool"))
    out = await _call(server, "get_todo_by_id", todo_id="any-id")
    assert "boom from tool" in out["tool_error"]
    assert set(out) == {"tool_error"} and out["tool_error"]
