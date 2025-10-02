"""Tests for trash pagination functionality."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager."""
    manager = Mock(spec=AppleScriptManager)
    manager.execute_applescript = AsyncMock()
    return manager


@pytest.fixture
def things_tools(mock_applescript_manager):
    """Create ThingsTools instance with mocked dependencies."""
    return ThingsTools(mock_applescript_manager)


@pytest.mark.asyncio
async def test_get_trash_default_pagination(things_tools):
    """Test get_trash with default pagination parameters."""
    # Mock the things.trash() call to return a list of mock todos
    mock_todos = [
        {'uuid': f'todo-{i}', 'title': f'Todo {i}', 'status': 'completed'}
        for i in range(75)  # Create 75 mock todos
    ]

    with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=mock_todos):
        result = await things_tools.get_trash()

        # Verify pagination metadata
        assert result['total_count'] == 75
        assert result['limit'] == 50
        assert result['offset'] == 0
        assert result['has_more'] is True
        assert len(result['items']) == 50

        # Verify first item (converted todos use 'uuid' field)
        assert result['items'][0]['uuid'] == 'todo-0'


@pytest.mark.asyncio
async def test_get_trash_custom_limit(things_tools):
    """Test get_trash with custom limit."""
    mock_todos = [
        {'uuid': f'todo-{i}', 'title': f'Todo {i}', 'status': 'completed'}
        for i in range(100)
    ]

    with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=mock_todos):
        result = await things_tools.get_trash(limit=20)

        assert result['total_count'] == 100
        assert result['limit'] == 20
        assert result['offset'] == 0
        assert result['has_more'] is True
        assert len(result['items']) == 20


@pytest.mark.asyncio
async def test_get_trash_with_offset(things_tools):
    """Test get_trash with offset for pagination."""
    mock_todos = [
        {'uuid': f'todo-{i}', 'title': f'Todo {i}', 'status': 'completed'}
        for i in range(100)
    ]

    with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=mock_todos):
        result = await things_tools.get_trash(limit=25, offset=50)

        assert result['total_count'] == 100
        assert result['limit'] == 25
        assert result['offset'] == 50
        assert result['has_more'] is True
        assert len(result['items']) == 25

        # Verify we got the correct slice (converted todos use 'uuid')
        assert result['items'][0]['uuid'] == 'todo-50'
        assert result['items'][-1]['uuid'] == 'todo-74'


@pytest.mark.asyncio
async def test_get_trash_last_page(things_tools):
    """Test get_trash on the last page (has_more should be False)."""
    mock_todos = [
        {'uuid': f'todo-{i}', 'title': f'Todo {i}', 'status': 'completed'}
        for i in range(60)
    ]

    with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=mock_todos):
        result = await things_tools.get_trash(limit=50, offset=50)

        assert result['total_count'] == 60
        assert result['limit'] == 50
        assert result['offset'] == 50
        assert result['has_more'] is False  # No more items after this page
        assert len(result['items']) == 10  # Only 10 items remaining


@pytest.mark.asyncio
async def test_get_trash_empty(things_tools):
    """Test get_trash with empty trash."""
    with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=[]):
        result = await things_tools.get_trash()

        assert result['total_count'] == 0
        assert result['limit'] == 50
        assert result['offset'] == 0
        assert result['has_more'] is False
        assert len(result['items']) == 0


@pytest.mark.asyncio
async def test_get_trash_offset_beyond_total(things_tools):
    """Test get_trash with offset beyond total count."""
    mock_todos = [
        {'uuid': f'todo-{i}', 'title': f'Todo {i}', 'status': 'completed'}
        for i in range(30)
    ]

    with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=mock_todos):
        result = await things_tools.get_trash(limit=50, offset=100)

        assert result['total_count'] == 30
        assert result['limit'] == 50
        assert result['offset'] == 100
        assert result['has_more'] is False
        assert len(result['items']) == 0  # No items at this offset


@pytest.mark.asyncio
async def test_get_trash_error_handling(things_tools):
    """Test get_trash error handling."""
    with patch('things_mcp.tools_helpers.read_operations.things.trash', side_effect=Exception("Database error")):
        result = await things_tools.get_trash()

        # Implementation returns empty result on error (error is logged)
        assert result['total_count'] == 0
        assert result['limit'] == 50
        assert result['offset'] == 0
        assert result['has_more'] is False
        assert len(result['items']) == 0


@pytest.mark.asyncio
async def test_get_trash_exact_page_boundary(things_tools):
    """Test get_trash when total count equals limit (edge case)."""
    mock_todos = [
        {'uuid': f'todo-{i}', 'title': f'Todo {i}', 'status': 'completed'}
        for i in range(50)
    ]

    with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=mock_todos):
        result = await things_tools.get_trash(limit=50)

        assert result['total_count'] == 50
        assert result['limit'] == 50
        assert result['offset'] == 0
        assert result['has_more'] is False  # Exactly at boundary
        assert len(result['items']) == 50