"""
Unit tests for bulk_update_todos functionality.
"""

import pytest
from unittest.mock import patch

from things_mcp.tools import ThingsTools


@pytest.fixture
def tools_with_mocks(mock_applescript_manager):
    """Fixture providing tools with all mocks."""
    from things_mcp.config import ThingsMCPConfig
    config = ThingsMCPConfig()
    return ThingsTools(mock_applescript_manager, config=config)


class TestBulkUpdateTodos:
    """Test bulk_update_todos functionality."""

    @pytest.mark.asyncio
    async def test_bulk_update_todos_mark_complete(self, tools_with_mocks):
        """Test marking multiple todos as complete."""
        todo_ids = ["todo-1", "todo-2", "todo-3"]

        # Mock the AppleScript execution
        with patch.object(tools_with_mocks.applescript, 'execute_applescript') as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": "successCount:3, errors:{}"
            }

            result = await tools_with_mocks.bulk_update_todos(
                todo_ids=todo_ids,
                completed=True
            )

            assert result["success"] is True
            assert result["updated_count"] == 3
            assert result["failed_count"] == 0
            assert result["total_requested"] == 3
            assert "Bulk update completed" in result["message"]

            # Verify the AppleScript was called
            mock_exec.assert_called_once()
            call_args = mock_exec.call_args[0][0]
            assert "tell application \"Things3\"" in call_args
            assert "set status of targetTodo to completed" in call_args
            assert 'to do id "todo-1"' in call_args
            assert 'to do id "todo-2"' in call_args
            assert 'to do id "todo-3"' in call_args

    @pytest.mark.asyncio
    async def test_bulk_update_todos_partial_success(self, tools_with_mocks):
        """Test when some todos fail to update."""
        todo_ids = ["todo-1", "todo-2", "todo-3"]

        with patch.object(tools_with_mocks.applescript, 'execute_applescript') as mock_exec:
            # Simulate partial success - only 2 out of 3 succeeded
            mock_exec.return_value = {
                "success": True,
                "output": "successCount:2, errors:{ID todo-3: not found}"
            }

            result = await tools_with_mocks.bulk_update_todos(
                todo_ids=todo_ids,
                completed=True
            )

            assert result["success"] is True  # Still success if any succeeded
            assert result["updated_count"] == 2
            assert result["failed_count"] == 1
            assert result["total_requested"] == 3
            assert "2/3" in result["message"]

    @pytest.mark.asyncio
    async def test_bulk_update_todos_empty_list(self, tools_with_mocks):
        """Test with empty todo list."""
        result = await tools_with_mocks.bulk_update_todos(
            todo_ids=[],
            completed=True
        )

        assert result["success"] is False
        # With new validation layer, error code is VALIDATION_ERROR and message contains details
        assert result["error"] == "VALIDATION_ERROR" or "No todo IDs provided" in str(result.get("message", result.get("error", "")))
        # Note: updated_count may not be present in validation error response
        assert result.get("updated_count", 0) == 0

    @pytest.mark.asyncio
    async def test_bulk_update_todos_with_tags(self, tools_with_mocks):
        """Test bulk update with tags (tags will be filtered if they don't exist)."""
        todo_ids = ["todo-1", "todo-2"]
        tags = ["work", "urgent"]

        with patch.object(tools_with_mocks.applescript, 'execute_applescript') as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": "successCount:2, errors:{}"
            }

            result = await tools_with_mocks.bulk_update_todos(
                todo_ids=todo_ids,
                tags=tags,
                completed=True
            )

            assert result["success"] is True
            assert result["updated_count"] == 2

            # Note: Tags may be filtered by tag validation service if they don't exist
            # This is expected behavior based on config.ai_can_create_tags setting

    @pytest.mark.asyncio
    async def test_bulk_update_todos_with_title_and_notes(self, tools_with_mocks):
        """Test bulk update with title and notes."""
        todo_ids = ["todo-1", "todo-2"]

        with patch.object(tools_with_mocks.applescript, 'execute_applescript') as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": "successCount:2, errors:{}"
            }

            result = await tools_with_mocks.bulk_update_todos(
                todo_ids=todo_ids,
                title="New Title",
                notes="New notes content"
            )

            assert result["success"] is True

            # Verify the AppleScript includes title and notes
            call_args = mock_exec.call_args[0][0]
            assert "set name of targetTodo" in call_args
            assert "set notes of targetTodo" in call_args

    @pytest.mark.asyncio
    async def test_bulk_update_todos_applescript_failure(self, tools_with_mocks):
        """Test when AppleScript execution fails completely."""
        todo_ids = ["todo-1", "todo-2"]

        with patch.object(tools_with_mocks.applescript, 'execute_applescript') as mock_exec:
            mock_exec.return_value = {
                "success": False,
                "error": "Things 3 not running"
            }

            result = await tools_with_mocks.bulk_update_todos(
                todo_ids=todo_ids,
                completed=True
            )

            assert result["success"] is False
            assert "Things 3 not running" in result["error"]
            assert result["updated_count"] == 0
            assert result["failed_count"] == 2

    @pytest.mark.asyncio
    async def test_bulk_update_todos_exception_handling(self, tools_with_mocks):
        """Test exception handling in bulk update."""
        todo_ids = ["todo-1"]

        with patch.object(tools_with_mocks.applescript, 'execute_applescript') as mock_exec:
            mock_exec.side_effect = Exception("Unexpected error")

            result = await tools_with_mocks.bulk_update_todos(
                todo_ids=todo_ids,
                completed=True
            )

            assert result["success"] is False
            assert "Unexpected error" in result["error"]
            assert result["updated_count"] == 0

    @pytest.mark.asyncio
    async def test_bulk_update_todos_with_scheduling(self, tools_with_mocks):
        """Test bulk update with scheduling (when/deadline)."""
        todo_ids = ["todo-1", "todo-2"]

        with patch.object(tools_with_mocks.applescript, 'execute_applescript') as mock_exec:
            mock_exec.return_value = {
                "success": True,
                "output": "successCount:2, errors:{}"
            }

            result = await tools_with_mocks.bulk_update_todos(
                todo_ids=todo_ids,
                when="today",
                deadline="2025-12-31"
            )

            assert result["success"] is True

            # Verify the AppleScript includes scheduling
            call_args = mock_exec.call_args[0][0]
            assert "activation date" in call_args or "activation date" in call_args.lower()
            assert "due date" in call_args or "due date" in call_args.lower()