"""Producer-level error codes for bulk tools (hq-v9k)."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from things_mcp.config import ThingsMCPConfig
from things_mcp.move_operations import MoveOperationsTools
from things_mcp.tools import ThingsTools


@pytest.fixture
def tools(mock_applescript_manager):
    return ThingsTools(mock_applescript_manager, config=ThingsMCPConfig())


async def _bulk_update(tools, output):
    with patch("things_mcp.tools_helpers.bulk_operations.things.get",
               return_value={"type": "to-do"}), \
         patch.object(tools.applescript, "execute_applescript") as ex:
        ex.return_value = {"success": True, "output": output}
        return await tools.bulk_update_todos(todo_ids=["t1", "t2"], completed=True)


@pytest.mark.asyncio
async def test_bulk_update_zero_successes_emits_code(tools):
    r = await _bulk_update(tools, "successCount:0, errors:{ID t1: x, ID t2: y}")
    assert r["success"] is False
    assert r["error"] == "BULK_OPERATION_FAILED"
    assert r["failed_count"] == 2


@pytest.mark.asyncio
async def test_bulk_update_partial_has_no_error_code(tools):
    r = await _bulk_update(tools, "successCount:1, errors:{ID t2: x}")
    assert r["success"] is True
    assert "error" not in r


def _move_ops(outcomes):
    ops = MoveOperationsTools(Mock(), Mock())
    ops._validate_destination = AsyncMock(return_value={"valid": True})
    ops.move_record = AsyncMock(side_effect=lambda tid, dest: outcomes[tid])
    return ops


@pytest.mark.asyncio
async def test_bulk_move_total_failure_code():
    ops = _move_ops({
        "a": {"success": False, "error": "TODO_NOT_FOUND", "message": "m"},
        "b": {"success": False, "error": "TODO_NOT_FOUND", "message": "m"},
    })
    r = await ops.bulk_move(["a", "b"], "today")
    assert r["success"] is False
    assert r["error"] == "BULK_OPERATION_FAILED"
    assert r["successful_moves"] == []
    assert [f["id"] for f in r["failed_moves"]] == ["a", "b"]


@pytest.mark.asyncio
async def test_bulk_move_partial_failure_code():
    ops = _move_ops({
        "a": {"success": True, "moved_at": "t"},
        "b": {"success": False, "error": "TODO_NOT_FOUND", "message": "m"},
    })
    r = await ops.bulk_move(["a", "b"], "today")
    assert r["success"] is False
    assert r["error"] == "BULK_PARTIAL_FAILURE"
    assert [m["id"] for m in r["successful_moves"]] == ["a"]
    assert [f["id"] for f in r["failed_moves"]] == ["b"]


@pytest.mark.asyncio
async def test_bulk_move_all_success_has_no_code():
    ops = _move_ops({"a": {"success": True}})
    r = await ops.bulk_move(["a"], "today")
    assert r["success"] is True and "error" not in r
