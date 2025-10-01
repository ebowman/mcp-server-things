"""Test delete_todo parameter validation.

This test verifies that delete_todo properly validates the todo_id parameter
before attempting to execute AppleScript, preventing cryptic errors like:
"Can't get to do id 'None'"
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript():
    """Create a mock AppleScript manager."""
    mock = MagicMock(spec=AppleScriptManager)
    mock.execute_applescript = AsyncMock(return_value={
        'success': True,
        'output': 'deleted'
    })
    return mock


@pytest.fixture
def tools(mock_applescript):
    """Create ThingsTools with mocked AppleScript."""
    return ThingsTools(mock_applescript)


@pytest.mark.asyncio
class TestDeleteValidation:
    """Test delete_todo parameter validation."""

    async def test_delete_with_none_fails(self, tools):
        """Test that delete_todo rejects None as todo_id."""
        result = await tools.delete_todo(None)

        assert result['success'] is False
        assert 'required' in result['error'].lower()
        assert 'todo_id' in result['error'].lower()

    async def test_delete_with_empty_string_fails(self, tools):
        """Test that delete_todo rejects empty string as todo_id."""
        result = await tools.delete_todo('')

        assert result['success'] is False
        assert 'empty' in result['error'].lower() or 'required' in result['error'].lower()
        assert 'todo_id' in result['error'].lower()

    async def test_delete_with_whitespace_only_fails(self, tools):
        """Test that delete_todo rejects whitespace-only todo_id."""
        result = await tools.delete_todo('   ')

        assert result['success'] is False
        assert 'empty' in result['error'].lower() or 'required' in result['error'].lower()

    async def test_delete_with_valid_id_succeeds(self, tools, mock_applescript):
        """Test that delete_todo works with valid todo_id."""
        result = await tools.delete_todo('ValidTodoID123')

        assert result['success'] is True
        assert 'successfully' in result['message'].lower()

        # Verify AppleScript was called
        mock_applescript.execute_applescript.assert_called_once()

        # Verify the script contains the todo ID
        call_args = mock_applescript.execute_applescript.call_args
        script = call_args[0][0]
        assert 'ValidTodoID123' in script
        assert 'delete' in script.lower()

    async def test_delete_error_handling(self, tools, mock_applescript):
        """Test that delete_todo handles AppleScript errors gracefully."""
        # Mock an AppleScript error
        mock_applescript.execute_applescript.return_value = {
            'success': False,
            'error': 'Can\'t get to do id "NonexistentID"'
        }

        result = await tools.delete_todo('NonexistentID')

        assert result['success'] is False
        assert 'error' in result or 'message' in result
