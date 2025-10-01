"""Test status filter functionality for get_todos."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from things_mcp.tools import ThingsTools


@pytest.fixture
def mock_things():
    """Mock the things module."""
    with patch('things_mcp.tools.things') as mock:
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
        """Test status=None returns all todos regardless of status."""
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Todo 1', 'status': 'incomplete'},
            {'uuid': '2', 'title': 'Todo 2', 'status': 'completed'},
            {'uuid': '3', 'title': 'Todo 3', 'status': 'canceled'}
        ]

        result = await tools.get_todos(status=None)

        mock_things.todos.assert_called_once_with(status=None)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_get_todos_project_with_status(self, tools, mock_things):
        """Test project filtering with status parameter."""
        project_uuid = 'project-123'
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Completed Todo', 'status': 'completed'}
        ]

        result = await tools.get_todos(project_uuid=project_uuid, status='completed')

        mock_things.todos.assert_called_once_with(project=project_uuid, status='completed')
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_todos_project_all_statuses(self, tools, mock_things):
        """Test getting all todos in a project regardless of status."""
        project_uuid = 'project-456'
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Incomplete', 'status': 'incomplete'},
            {'uuid': '2', 'title': 'Completed', 'status': 'completed'},
            {'uuid': '3', 'title': 'Canceled', 'status': 'canceled'}
        ]

        result = await tools.get_todos(project_uuid=project_uuid, status=None)

        mock_things.todos.assert_called_once_with(project=project_uuid, status=None)
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
