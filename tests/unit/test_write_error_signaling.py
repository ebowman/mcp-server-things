"""MCP-boundary isError signaling for write tools (hq-v9k)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import Client

from things_mcp.middleware import WRITE_TOOLS
from things_mcp.server import ThingsMCPServer

# Classification of every registered tool (CLAUDE.md lists). Adding a tool
# without classifying it here fails test_every_tool_is_classified.
READ_TOOLS = frozenset({
    "get_today", "get_inbox", "get_upcoming", "get_anytime", "get_someday",
    "get_logbook", "get_trash", "get_todos", "get_projects", "get_areas",
    "get_tags", "get_tagged_items", "get_recent", "search_todos",
    "search_advanced", "get_todo_by_id", "get_due_in_days",
    "get_activating_in_days", "get_tag_usage", "get_project_headings",
})
UTILITY_TOOLS = frozenset({
    "health_check", "queue_status", "context_stats",
    "get_server_capabilities", "get_usage_recommendations",
})
EXPECTED_WRITE = frozenset({
    "add_todo", "update_todo", "bulk_update_todos", "delete_todo",
    "add_project", "update_project", "add_area", "update_area", "add_tags",
    "remove_tags", "create_tag", "move_record", "bulk_move_records",
    "add_checklist_items", "prepend_checklist_items", "replace_checklist_items",
})


@pytest.mark.asyncio
async def test_every_tool_is_classified() -> None:
    server = ThingsMCPServer()
    registered = {t.name for t in await server.mcp.list_tools()}
    assert WRITE_TOOLS == EXPECTED_WRITE
    assert not (READ_TOOLS & UTILITY_TOOLS) and not (READ_TOOLS & WRITE_TOOLS)
    assert not (UTILITY_TOOLS & WRITE_TOOLS)
    assert registered == WRITE_TOOLS | READ_TOOLS | UTILITY_TOOLS


def _server() -> ThingsMCPServer:
    server = ThingsMCPServer()
    tools = MagicMock()
    tools.tag_validation_service = None
    server.tools = tools
    return server


async def _call(server, tool, args):
    async with Client(server.mcp) as client:
        return await client.call_tool(tool, args, raise_on_error=False)


@pytest.mark.asyncio
async def test_delete_todo_lower_snake_failure_is_flagged_payload_unchanged() -> None:
    payload = {"success": False, "error": "not_found", "message": "nope"}
    server = _server()
    server.tools.delete_todo = AsyncMock(return_value=dict(payload))
    result = await _call(server, "delete_todo", {"todo_id": "x"})
    assert result.is_error is True
    assert result.structured_content == payload


@pytest.mark.asyncio
async def test_bulk_update_all_failed_flagged_with_code() -> None:
    server = _server()
    server.tools.bulk_update_todos = AsyncMock(return_value={
        "success": False, "error": "BULK_OPERATION_FAILED", "updated_count": 0,
        "failed_count": 2, "total_requested": 2, "message": "m",
    })
    result = await _call(server, "bulk_update_todos", {"todo_ids": "a,b", "notes": "n"})
    assert result.is_error is True
    assert result.structured_content["error"] == "BULK_OPERATION_FAILED"


@pytest.mark.asyncio
async def test_bulk_update_partial_not_flagged() -> None:
    server = _server()
    server.tools.bulk_update_todos = AsyncMock(return_value={
        "success": True, "updated_count": 1, "failed_count": 1,
        "total_requested": 2, "message": "m",
    })
    result = await _call(server, "bulk_update_todos", {"todo_ids": "a,b", "notes": "n"})
    assert result.is_error is False


@pytest.mark.asyncio
async def test_bulk_move_failure_flagged_and_keeps_per_item_results() -> None:
    payload = {
        "success": False, "error": "BULK_OPERATION_FAILED", "total_requested": 2,
        "total_successful": 1, "total_failed": 1,
        "successful_moves": [{"id": "a"}], "failed_moves": [{"id": "b", "error": "X"}],
    }
    server = _server()
    server.tools.move_operations.bulk_move = AsyncMock(return_value=dict(payload))
    result = await _call(server, "bulk_move_records",
                         {"todo_ids": "a,b", "destination": "today"})
    assert result.is_error is True
    assert result.structured_content["successful_moves"] == [{"id": "a"}]
    assert result.structured_content["failed_moves"][0]["id"] == "b"


@pytest.mark.asyncio
async def test_read_tool_lower_snake_error_not_flagged() -> None:
    result = await _call(ThingsMCPServer(), "get_todos", {"status": "bogus"})
    assert result.structured_content["success"] is False
    assert result.is_error is False


@pytest.mark.asyncio
async def test_utility_tool_not_flagged() -> None:
    server = _server()
    result = await _call(server, "health_check", {})
    assert result.is_error is False
