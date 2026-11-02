"""bulk_move_records must report a per-item BaseException as a failed move (hq-oh8)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from things_mcp.move_operations import MoveOperationsTools


def _make_ops(side_effect):
    ops = MoveOperationsTools(MagicMock(), MagicMock())
    ops._validate_destination = AsyncMock(return_value={"valid": True})
    ops.move_record = AsyncMock(side_effect=side_effect)
    return ops


@pytest.mark.asyncio
async def test_cancelled_error_reported_as_failed_item():
    async def fake(todo_id, destination):
        if todo_id == "bad":
            raise asyncio.CancelledError()
        return {"success": True, "moved_at": "now"}

    result = await _make_ops(fake).bulk_move(["bad", "good"], "inbox")

    assert result["success"] is False
    assert [m["id"] for m in result["failed_moves"]] == ["bad"]
    assert result["failed_moves"][0]["error"] == "EXCEPTION"
    assert [m["id"] for m in result["successful_moves"]] == ["good"]


@pytest.mark.asyncio
async def test_plain_exception_reported_as_failed_item():
    async def fake(todo_id, destination):
        if todo_id == "bad":
            raise RuntimeError("boom")
        return {"success": True, "moved_at": "now"}

    result = await _make_ops(fake).bulk_move(["bad", "good"], "inbox")

    assert result["success"] is False
    assert result["failed_moves"][0]["id"] == "bad"
    assert result["failed_moves"][0]["error"] == "EXCEPTION"
    assert result["failed_moves"][0]["message"] == "boom"
    assert [m["id"] for m in result["successful_moves"]] == ["good"]
