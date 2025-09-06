"""
Fixed unit tests for Things 3 MCP tools with proper operation queue mocking.
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

from things_mcp.tools import ThingsTools
from things_mcp.models import Todo, Project, Area


class TestThingsToolsInit:
    """Test ThingsTools initialization."""
    
    def test_init_with_applescript_manager(self, mock_applescript_manager):
        """Test initialization with AppleScript manager."""
        tools = ThingsTools(mock_applescript_manager)
        
        assert tools.applescript is mock_applescript_manager
        assert tools.validation_service is not None
        assert tools.move_operations is not None
        assert tools.reliable_scheduler is not None
        assert tools.tag_validation_service is None  # No config provided
    
    def test_init_with_config(self, mock_applescript_manager):
        """Test initialization with config."""
        from things_mcp.config import ThingsMCPConfig
        config = ThingsMCPConfig()
        
        tools = ThingsTools(mock_applescript_manager, config=config)
        
        assert tools.config is not None
        assert tools.tag_validation_service is not None  # Config provided
    
    def test_escape_applescript_string(self, mock_applescript_manager):
        """Test AppleScript string escaping."""
        tools = ThingsTools(mock_applescript_manager)
        
        # Test quote escaping
        result = tools._escape_applescript_string('Hello "World"')
        assert '"' not in result or '\\"' in result
        
        # Test backslash escaping  
        result = tools._escape_applescript_string('Path\\file')
        assert result is not None


class TestGetTodos:
    """Test get_todos functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_get_todos_all(self, tools_with_mock):
        """Test getting all todos."""
        # Mock operation queue to avoid timeout
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value=[{
                "id": "todo-123",
                "name": "Sample Todo",
                "status": "open"
            }])
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.get_todos()
            
            assert isinstance(result, list)
            assert len(result) > 0
    
    @pytest.mark.asyncio
    async def test_get_todos_by_project(self, tools_with_mock):
        """Test getting todos by project."""
        project_uuid = "project-456"
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value=[{
                "id": "todo-789",
                "name": "Project Todo",
                "project_id": project_uuid
            }])
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.get_todos(project_uuid=project_uuid)
            
            assert isinstance(result, list)


class TestAddTodo:
    """Test add_todo functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_add_todo_minimal(self, tools_with_mock):
        """Test adding todo with minimal required data."""
        title = "New Todo"
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value={
                "success": True,
                "todo_id": "new-todo-123"
            })
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.add_todo(title)
            
            assert isinstance(result, dict)
            assert result["success"] is True
    
    @pytest.mark.asyncio
    async def test_add_todo_with_options(self, tools_with_mock):
        """Test adding todo with additional options."""
        title = "Complex Todo"
        notes = "Test notes"
        tags = ["work", "urgent"]
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value={
                "success": True,
                "todo_id": "complex-todo-456"
            })
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.add_todo(title, notes=notes, tags=tags)
            
            assert isinstance(result, dict)
            assert result["success"] is True


class TestUpdateTodo:
    """Test update_todo functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_update_todo_basic(self, tools_with_mock):
        """Test updating a todo."""
        todo_id = "todo-123"
        new_title = "Updated Title"
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value={
                "success": True,
                "message": "Todo updated successfully"
            })
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.update_todo(todo_id=todo_id, title=new_title)
            
            assert isinstance(result, dict)
            assert result["success"] is True


class TestDeleteTodo:
    """Test delete_todo functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_delete_todo(self, tools_with_mock):
        """Test deleting a todo."""
        todo_id = "todo-123"
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value={
                "success": True,
                "message": "Todo deleted successfully"
            })
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.delete_todo(todo_id)
            
            assert isinstance(result, dict)
            assert result["success"] is True


class TestGetProjects:
    """Test get_projects functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_get_projects_all(self, tools_with_mock):
        """Test getting all projects."""
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value=[{
                "id": "project-456",
                "name": "Sample Project",
                "status": "open"
            }])
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.get_projects()
            
            assert isinstance(result, list)


class TestMoveOperations:
    """Test move operations."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_move_todo_to_list(self, tools_with_mock):
        """Test moving a todo to a different list."""
        todo_id = "todo-123"
        destination = "Today"
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value={
                "success": True,
                "message": f"Todo moved to {destination} successfully",
                "todo_id": todo_id,
                "destination": destination
            })
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.move_record(todo_id, destination)
            
            assert isinstance(result, dict)
            assert result["success"] is True
            assert result["destination"] == destination


class TestSearchOperations:
    """Test search operations."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_search_todos(self, tools_with_mock):
        """Test searching todos."""
        query = "test"
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value=[{
                "id": "todo-123",
                "name": "Test Todo",
                "status": "open"
            }])
            mock_get_queue.return_value = mock_queue
            
            result = await tools_with_mock.search_todos(query=query)
            
            assert isinstance(result, list)


class TestGetAreas:
    """Test get_areas functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_get_areas(self, tools_with_mock):
        """Test getting all areas."""
        # Mock the applescript manager's get_areas method directly
        tools_with_mock.applescript.get_areas = AsyncMock(return_value=[{
            "id": "area-789",
            "name": "Work Area",
            "collapsed": False
        }])
        
        result = await tools_with_mock.get_areas()
        
        assert isinstance(result, list)


class TestGetTags:
    """Test get_tags functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_get_tags_with_items(self, tools_with_mock):
        """Test getting all tags with items included."""
        # Mock the AppleScript execution for tags
        tools_with_mock.applescript.execute_applescript = AsyncMock(return_value={
            "success": True,
            "output": "tag-id-1\tWork, tag-id-2\tPersonal",
            "error": None
        })
        
        # Mock getting tagged items
        tools_with_mock.get_tagged_items = AsyncMock(return_value=[
            {"id": "todo1", "title": "Sample Todo"}
        ])
        
        result = await tools_with_mock.get_tags(include_items=True)
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "Work"
        assert "items" in result[0]
        assert isinstance(result[0]["items"], list)
    
    @pytest.mark.asyncio
    async def test_get_tags_with_counts(self, tools_with_mock):
        """Test getting all tags with item counts instead of items."""
        # Track calls to determine which response to return
        call_count = 0
        
        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            if "every tag" in args[0]:
                # Return tags list
                return {
                    "success": True,
                    "output": "tag-id-1\tWork, tag-id-2\tPersonal",
                    "error": None
                }
            else:
                # Return count for each tag
                counts = ["5", "3"]
                result = {"success": True, "output": counts[call_count]}
                call_count += 1
                return result
        
        tools_with_mock.applescript.execute_applescript = mock_execute
        
        result = await tools_with_mock.get_tags(include_items=False)
        
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "Work"
        assert "item_count" in result[0]
        assert result[0]["item_count"] == 5
        assert result[1]["name"] == "Personal"
        assert result[1]["item_count"] == 3
        assert "items" not in result[0]  # Should not have items field


class TestCompleteTodo:
    """Test completing a todo via update_todo."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_complete_todo(self, tools_with_mock):
        """Test completing a todo using update_todo."""
        todo_id = "todo-123"
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value={
                "success": True,
                "message": "Todo completed successfully"
            })
            mock_get_queue.return_value = mock_queue
            
            # Use update_todo with completed=True
            result = await tools_with_mock.update_todo(todo_id=todo_id, completed=True)
            
            assert isinstance(result, dict)
            assert result["success"] is True


class TestCancelTodo:
    """Test canceling a todo via update_todo."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    @pytest.mark.asyncio
    async def test_cancel_todo(self, tools_with_mock):
        """Test canceling a todo using update_todo."""
        todo_id = "todo-123"
        
        # Mock operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value={
                "success": True,
                "message": "Todo canceled successfully"
            })
            mock_get_queue.return_value = mock_queue
            
            # Use update_todo with canceled=True
            result = await tools_with_mock.update_todo(todo_id=todo_id, canceled=True)
            
            assert isinstance(result, dict)
            assert result["success"] is True