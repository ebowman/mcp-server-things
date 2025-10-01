"""Test for bulk_update_todos tag string handling bug fix."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from things_mcp.tools import ThingsTools


class MockAppleScriptManager:
    """Mock AppleScript manager for testing."""

    def __init__(self):
        self.execution_calls = []

    async def execute_applescript(self, script: str):
        """Mock execute_applescript method."""
        self.execution_calls.append({"script": script})

        # Simulate successful execution
        return {
            "success": True,
            "output": "{successCount:1, errors:{}}",
            "error": None
        }


@pytest.fixture
def mock_applescript_manager():
    """Fixture for mock AppleScript manager."""
    return MockAppleScriptManager()


@pytest.fixture
def tools_with_mock(mock_applescript_manager):
    """Fixture for ThingsTools with mock AppleScript manager."""
    tools = ThingsTools(applescript_manager=mock_applescript_manager)
    return tools


class TestBulkUpdateTagsStringBug:
    """Test that bulk_update_todos handles tags string correctly (BUG FIX #8)."""

    @pytest.mark.asyncio
    async def test_bulk_update_with_string_tags_defensive(self, tools_with_mock, mock_applescript_manager):
        """Test that if tags is somehow passed as a string, it's handled correctly.

        This is a defensive test for BUG FIX #8 (Version 1.2.5).
        Even though server.py should convert tags to a list, we add defensive
        code in tools.py to handle the case where it's still a string.
        """
        # IDs
        todo_ids = ["todo1", "todo2"]

        # Simulate the bug scenario: tags passed as a string instead of a list
        # This could happen if there's a parameter binding issue or edge case
        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            tags="EvaColinWorkHomeEvaColinAnnaLuka"  # Single tag, no commas
        )

        # Should succeed
        assert result["success"] is True

        # Check the generated AppleScript
        assert len(mock_applescript_manager.execution_calls) >= 1
        bulk_script = mock_applescript_manager.execution_calls[0]["script"]

        # The tag should be treated as a single tag, not split into characters
        assert 'set tag names of targetTodo to "EvaColinWorkHomeEvaColinAnnaLuka"' in bulk_script

        # Should NOT have individual characters
        assert 'set tag names of targetTodo to "E, v, a, C, o, l, i, n' not in bulk_script

        print("✓ Bulk update correctly handles single-tag string without splitting into characters")

    @pytest.mark.asyncio
    async def test_bulk_update_with_comma_separated_string_tags(self, tools_with_mock, mock_applescript_manager):
        """Test that comma-separated tag string is properly split."""
        todo_ids = ["todo1"]

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            tags="tag1,tag2,tag3"  # Comma-separated
        )

        assert result["success"] is True

        bulk_script = mock_applescript_manager.execution_calls[0]["script"]

        # Should split into individual tags
        assert 'set tag names of targetTodo to "tag1, tag2, tag3"' in bulk_script

        print("✓ Bulk update correctly splits comma-separated tag string")

    @pytest.mark.asyncio
    async def test_bulk_update_with_list_tags(self, tools_with_mock, mock_applescript_manager):
        """Test that tags list (correct format) works as expected."""
        todo_ids = ["todo1"]

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            tags=["tag1", "tag2", "tag3"]  # Already a list (correct format)
        )

        assert result["success"] is True

        bulk_script = mock_applescript_manager.execution_calls[0]["script"]

        # Should handle list correctly
        assert 'set tag names of targetTodo to "tag1, tag2, tag3"' in bulk_script

        print("✓ Bulk update correctly handles tags as list")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
