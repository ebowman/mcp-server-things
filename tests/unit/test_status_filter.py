"""Test status filter functionality for get_todos."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from things_mcp.tools import ThingsTools


@pytest.fixture
def mock_things():
    """Mock the things module."""
    with patch('things_mcp.tools_helpers.read_operations.things') as mock:
        yield mock


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager."""
    manager = Mock()
    manager.execute_script = Mock(return_value="success")
    return manager


@pytest.fixture
def tools(mock_things, mock_applescript_manager):
    """Create ThingsTools instance with mocked dependencies."""
    return ThingsTools(mock_applescript_manager)


class TestStatusFilter:
    """Test status filtering in get_todos."""

    @pytest.mark.asyncio
    async def test_get_todos_default_incomplete_status(self, tools, mock_things):
        """Test that default status is 'incomplete'."""
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Todo 1', 'status': 'incomplete'},
            {'uuid': '2', 'title': 'Todo 2', 'status': 'incomplete'}
        ]

        result = await tools.get_todos()

        # Verify things.todos was called with status='incomplete' (default)
        mock_things.todos.assert_called_once_with(status='incomplete')
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_todos_explicit_incomplete_status(self, tools, mock_things):
        """Test explicit status='incomplete'."""
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Todo 1', 'status': 'incomplete'}
        ]

        result = await tools.get_todos(status='incomplete')

        mock_things.todos.assert_called_once_with(status='incomplete')
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_todos_completed_status(self, tools, mock_things):
        """Test status='completed' returns completed todos."""
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Todo 1', 'status': 'completed'},
            {'uuid': '2', 'title': 'Todo 2', 'status': 'completed'}
        ]

        result = await tools.get_todos(status='completed')

        mock_things.todos.assert_called_once_with(status='completed')
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_todos_canceled_status(self, tools, mock_things):
        """Test status='canceled' returns canceled todos."""
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Todo 1', 'status': 'canceled'}
        ]

        result = await tools.get_todos(status='canceled')

        mock_things.todos.assert_called_once_with(status='canceled')
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_todos_all_status(self, tools, mock_things):
        """Test status=None returns all todos regardless of status.

        When status=None, the implementation makes 3 separate calls to things.todos()
        (one for each status: incomplete, completed, canceled).
        """
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Todo 1', 'status': 'incomplete'}
        ]

        result = await tools.get_todos(status=None)

        # Implementation makes 3 calls: incomplete, completed, canceled
        assert mock_things.todos.call_count == 3
        mock_things.todos.assert_any_call(status='incomplete')
        mock_things.todos.assert_any_call(status='completed')
        mock_things.todos.assert_any_call(status='canceled')
        # Result should contain all todos from all 3 calls
        assert len(result) == 3  # One from each call

    @pytest.mark.asyncio
    async def test_get_todos_project_with_status(self, tools, mock_things, mock_applescript_manager):
        """Test project filtering with status parameter.

        When project_uuid is provided, the implementation uses AppleScript (not things.py),
        then filters the results by status.
        """
        project_uuid = 'project-123'
        # Mock AppleScript to return todos with different statuses
        mock_applescript_manager.get_todos = AsyncMock(return_value=[
            {'id': '1', 'name': 'Completed Todo', 'status': 'completed'},
            {'id': '2', 'name': 'Open Todo', 'status': 'open'}
        ])

        result = await tools.get_todos(project_uuid=project_uuid, status='completed')

        # Should use AppleScript, not things.py
        mock_applescript_manager.get_todos.assert_called_once_with(project_uuid=project_uuid)
        # Should filter to only completed todos
        assert len(result) == 1
        assert result[0]['status'] == 'completed'

    @pytest.mark.asyncio
    async def test_get_todos_project_all_statuses(self, tools, mock_things, mock_applescript_manager):
        """Test getting all todos in a project regardless of status.

        When project_uuid is provided, the implementation uses AppleScript (not things.py),
        and when status=None, returns all todos without filtering.
        """
        project_uuid = 'project-456'
        # Mock AppleScript to return todos with different statuses
        mock_applescript_manager.get_todos = AsyncMock(return_value=[
            {'id': '1', 'name': 'Incomplete', 'status': 'open'},
            {'id': '2', 'name': 'Completed', 'status': 'completed'},
            {'id': '3', 'name': 'Canceled', 'status': 'canceled'}
        ])

        result = await tools.get_todos(project_uuid=project_uuid, status=None)

        # Should use AppleScript, not things.py
        mock_applescript_manager.get_todos.assert_called_once_with(project_uuid=project_uuid)
        # Should return all todos without filtering
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_backward_compatibility(self, tools, mock_things):
        """Test backward compatibility - no status param uses default 'incomplete'."""
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Todo 1', 'status': 'incomplete'}
        ]

        # Call without status parameter (backward compatible)
        result = await tools.get_todos()

        # Should default to 'incomplete'
        mock_things.todos.assert_called_once_with(status='incomplete')
        assert len(result) == 1
