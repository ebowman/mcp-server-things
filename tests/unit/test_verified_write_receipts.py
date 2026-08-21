"""MCP-boundary receipts for successful single-todo mutations."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastmcp import Client

from things_mcp.server import ThingsMCPServer


TODO_ID = "todo-123"
UPDATED_TODO = {
    "uuid": TODO_ID,
    "type": "to-do",
    "title": "Updated title",
    "status": "incomplete",
}


def _server_with_mock_tools() -> ThingsMCPServer:
    server = ThingsMCPServer()
    tools = MagicMock()
    tools.tag_validation_service = None
    tools.update_todo = AsyncMock(
        return_value={"success": True, "message": "Todo updated successfully"}
    )
    tools.move_record = AsyncMock(
        return_value={
            "success": True,
            "message": "Todo moved successfully",
            "todo_id": TODO_ID,
            "destination": "today",
        }
    )
    tools.get_todo_by_id = AsyncMock(return_value=UPDATED_TODO)
    server.tools = tools
    return server


@pytest.mark.asyncio
async def test_update_todo_returns_target_id_and_final_item() -> None:
    server = _server_with_mock_tools()

    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "update_todo", {"id": TODO_ID, "title": "Updated title"}
        )

    assert result.structured_content == {
        "success": True,
        "message": "Todo updated successfully",
        "todo_id": TODO_ID,
        "verified": True,
        "item": UPDATED_TODO,
    }
    server.tools.update_todo.assert_awaited_once_with(
        todo_id=TODO_ID,
        title="Updated title",
        notes=None,
        tags=None,
        when=None,
        deadline=None,
        completed=None,
        canceled=None,
        heading=None,
        list_id=None,
        list_title=None,
    )
    server.tools.get_todo_by_id.assert_awaited_once_with(TODO_ID)


@pytest.mark.asyncio
async def test_move_record_returns_target_id_and_final_item() -> None:
    server = _server_with_mock_tools()

    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "move_record",
            {"todo_id": TODO_ID, "destination_list": "today"},
        )

    assert result.structured_content == {
        "success": True,
        "message": "Todo moved successfully",
        "todo_id": TODO_ID,
        "destination": "today",
        "verified": True,
        "item": UPDATED_TODO,
    }
    server.tools.move_record.assert_awaited_once_with(
        todo_id=TODO_ID, destination_list="today"
    )
    server.tools.get_todo_by_id.assert_awaited_once_with(TODO_ID)


@pytest.mark.asyncio
async def test_update_todo_preserves_failure_without_readback() -> None:
    server = _server_with_mock_tools()
    failure = {
        "success": False,
        "error": "NOT_FOUND",
        "message": "Todo not found",
        "details": "No to-do has that UUID",
    }
    server.tools.update_todo.return_value = failure

    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "update_todo", {"id": TODO_ID, "title": "Updated title"}
        )

    assert result.structured_content == failure
    server.tools.get_todo_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_move_record_preserves_failure_without_readback() -> None:
    server = _server_with_mock_tools()
    failure = {
        "success": False,
        "error": "TODO_NOT_FOUND",
        "message": "Todo not found",
        "todo_id": TODO_ID,
        "destination": "today",
    }
    server.tools.move_record.return_value = failure

    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "move_record",
            {"todo_id": TODO_ID, "destination_list": "today"},
        )

    assert result.structured_content == failure
    server.tools.get_todo_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_todo_readback_exception_keeps_write_success_explicit() -> None:
    server = _server_with_mock_tools()
    server.tools.get_todo_by_id.side_effect = RuntimeError("database unavailable")

    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "update_todo", {"id": TODO_ID, "title": "Updated title"}
        )

    assert result.structured_content == {
        "success": True,
        "message": "Todo updated successfully",
        "todo_id": TODO_ID,
        "verified": False,
        "verification_error": {
            "success": False,
            "error": "readback_failed",
            "message": "Final item readback failed.",
            "details": "database unavailable",
        },
        "warnings": [
            "Write succeeded, but final item state could not be verified; "
            "do not retry automatically."
        ],
    }


@pytest.mark.asyncio
async def test_move_record_structured_readback_error_is_verification_failure() -> None:
    server = _server_with_mock_tools()
    readback_error = {
        "success": False,
        "error": "not_found",
        "message": "Todo not found after move.",
    }
    server.tools.get_todo_by_id.return_value = readback_error

    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "move_record",
            {"todo_id": TODO_ID, "destination_list": "today"},
        )

    assert result.structured_content == {
        "success": True,
        "message": "Todo moved successfully",
        "todo_id": TODO_ID,
        "destination": "today",
        "verified": False,
        "verification_error": readback_error,
        "warnings": [
            "Write succeeded, but final item state could not be verified; "
            "do not retry automatically."
        ],
    }
