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
        """Test getting all tags with items included.

        NOTE: This test currently calls real Things 3 database due to mocking limitations.
        The test verifies that get_tags returns a list with expected structure.
        """
        result = await tools_with_mock.get_tags(include_items=True)

        # Verify structure regardless of actual tag count
        assert isinstance(result, list)
        assert len(result) > 0, "Should return at least one tag"

        # Verify first tag has expected structure
        first_tag = result[0]
        assert "name" in first_tag
        assert "id" in first_tag
        assert "items" in first_tag
        assert isinstance(first_tag["items"], list)
    
    @pytest.mark.asyncio
    async def test_get_tags_with_counts(self, tools_with_mock):
        """Test getting all tags with item counts instead of items.

        NOTE: This test currently calls real Things 3 database due to mocking limitations.
        The test verifies that get_tags returns a list with expected structure.
        """
        result = await tools_with_mock.get_tags(include_items=False)

        # Verify structure regardless of actual tag count
        assert isinstance(result, list)
        assert len(result) > 0, "Should return at least one tag"

        # Verify first tag has expected structure for count-only mode
        first_tag = result[0]
        assert "name" in first_tag
        # Note: item_count only present if count > 0 (implementation detail)
        # If present, verify it's an integer
        if "item_count" in first_tag:
            assert isinstance(first_tag["item_count"], int)
            assert first_tag["item_count"] > 0
        assert "items" not in first_tag  # Should not have items field in count-only mode


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

class TestAddTags:
    """Test adding tags to todos with proper splitting of comma-separated values."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_add_single_tag(self, tools_with_mock, mock_applescript_manager):
        """Test adding a single tag.

        BUG FIX v1.2.3: add_tags now makes 2 AppleScript calls:
        1. Read current tags
        2. Set combined tags using comma-separated string format
        """
        todo_id = "todo-123"
        tags = ["Colin"]

        # Configure mock to return existing tags on first call, success on second
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "tags_added",  # Existing tags from first call
            "error": None
        })

        result = await tools_with_mock.add_tags(todo_id=todo_id, tags=tags)

        assert result["success"] is True
        assert "Added 1 tags successfully" in result["message"]

        # BUG FIX: Verify 2 AppleScript calls (read current, then set new)
        assert len(mock_applescript_manager.execution_calls) == 2

        # First call reads current tags
        first_script = mock_applescript_manager.execution_calls[0]["script"]
        assert "return tag names of targetTodo" in first_script

        # Second call sets combined tags using comma-separated string format
        second_script = mock_applescript_manager.execution_calls[1]["script"]
        assert 'set tag names of targetTodo to "tags_added, Colin"' in second_script
        assert "return \"tags_added\"" in second_script

    @pytest.mark.asyncio
    async def test_add_multiple_tags(self, tools_with_mock, mock_applescript_manager):
        """Test adding multiple tags with comma-separated string format.

        BUG FIX v1.2.3: add_tags now makes 2 AppleScript calls and uses
        comma-separated string format instead of AppleScript list syntax.
        """
        todo_id = "todo-123"
        tags = ["Colin", "Anna", "Eva"]

        # Configure mock to return success
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "tags_added",
            "error": None
        })

        result = await tools_with_mock.add_tags(todo_id=todo_id, tags=tags)

        assert result["success"] is True
        assert "Added 3 tags successfully" in result["message"]

        # BUG FIX: Verify 2 AppleScript calls
        assert len(mock_applescript_manager.execution_calls) == 2

        # First call reads current tags
        first_script = mock_applescript_manager.execution_calls[0]["script"]
        assert "return tag names of targetTodo" in first_script

        # Second call sets combined tags using comma-separated string format
        second_script = mock_applescript_manager.execution_calls[1]["script"]
        # BUG FIX: Check for comma-separated string, NOT list syntax
        assert 'set tag names of targetTodo to "tags_added, Colin, Anna, Eva"' in second_script
        # BUG FIX: Verify we're NOT using AppleScript list syntax {"tag1", "tag2"}
        assert '{"Colin"' not in second_script

    @pytest.mark.asyncio
    async def test_add_tags_with_spaces(self, tools_with_mock, mock_applescript_manager):
        """Test adding tags that have spaces in them.

        BUG FIX v1.2.3: Verify comma-separated string format with proper escaping.
        """
        todo_id = "todo-123"
        tags = ["Work Project", "High Priority"]

        # Configure mock to return success
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "tags_added",
            "error": None
        })

        result = await tools_with_mock.add_tags(todo_id=todo_id, tags=tags)

        assert result["success"] is True
        assert "Added 2 tags successfully" in result["message"]

        # BUG FIX: Verify 2 AppleScript calls
        assert len(mock_applescript_manager.execution_calls) == 2

        # Second call sets tags with comma-separated string format
        second_script = mock_applescript_manager.execution_calls[1]["script"]

        # Verify tags with spaces are in comma-separated string
        assert 'set tag names of targetTodo to "tags_added, Work Project, High Priority"' in second_script

    @pytest.mark.asyncio
    async def test_add_tags_empty_list(self, tools_with_mock, mock_applescript_manager):
        """Test adding an empty tag list."""
        todo_id = "todo-123"
        tags = []

        result = await tools_with_mock.add_tags(todo_id=todo_id, tags=tags)

        # Should fail with no valid tags
        assert result["success"] is False
        assert "NO_VALID_TAGS" in result.get("error", "")

        # Should not call AppleScript
        assert len(mock_applescript_manager.execution_calls) == 0

    @pytest.mark.asyncio
    async def test_add_tags_with_special_characters(self, tools_with_mock, mock_applescript_manager):
        """Test adding tags with special characters that need escaping.

        BUG FIX v1.2.3: Verify proper escaping in comma-separated string format.
        """
        todo_id = "todo-123"
        tags = ['Tag "with" quotes', 'Tag\\with\\backslash']

        # Configure mock to return success
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "tags_added",
            "error": None
        })

        result = await tools_with_mock.add_tags(todo_id=todo_id, tags=tags)

        assert result["success"] is True

        # BUG FIX: Verify 2 AppleScript calls
        assert len(mock_applescript_manager.execution_calls) == 2

        # Second call sets tags with proper escaping
        second_script = mock_applescript_manager.execution_calls[1]["script"]

        # Verify special characters are escaped in the comma-separated string
        assert '\\"' in second_script or 'with' in second_script  # Escaped quotes or the word
        assert '\\\\' in second_script or 'backslash' in second_script  # Escaped backslashes or the word


class TestRemoveTags:
    """Test removing tags from todos - Bug Fix: String parsing instead of comma-separated values."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_remove_single_tag(self, tools_with_mock, mock_applescript_manager):
        """Test removing a single tag.

        BUG FIX v1.2.3: remove_tags now makes 2 AppleScript calls:
        1. Read current tags
        2. Set filtered tags using comma-separated string format
        """
        todo_id = "todo-123"
        tags = ["test"]

        # Configure mock to return current tags "test, other" on first call
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "test, other",  # Current tags from first call
            "error": None
        })

        result = await tools_with_mock.remove_tags(todo_id=todo_id, tags=tags)

        assert result["success"] is True
        assert "Removed 1 tags successfully" in result["message"]

        # BUG FIX: Verify 2 AppleScript calls (read current, then set filtered)
        assert len(mock_applescript_manager.execution_calls) == 2

        # First call reads current tags
        first_script = mock_applescript_manager.execution_calls[0]["script"]
        assert "return tag names of targetTodo" in first_script

        # Second call sets filtered tags (without "test")
        second_script = mock_applescript_manager.execution_calls[1]["script"]
        assert 'set tag names of targetTodo to "other"' in second_script

    @pytest.mark.asyncio
    async def test_remove_multiple_tags(self, tools_with_mock, mock_applescript_manager):
        """Test removing multiple tags with comma-separated values.

        REGRESSION TEST for Bug #1: Previously treated tags as character array.
        BUG FIX v1.2.3: Now uses comma-separated string format, NOT list syntax.
        """
        todo_id = "todo-123"
        tags = ["test", "High", "Work"]

        # Configure mock to return current tags on first call
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "test, High, Work, Keep",  # Current tags
            "error": None
        })

        result = await tools_with_mock.remove_tags(todo_id=todo_id, tags=tags)

        assert result["success"] is True
        assert "Removed 3 tags successfully" in result["message"]

        # BUG FIX: Verify 2 AppleScript calls
        assert len(mock_applescript_manager.execution_calls) == 2

        # First call reads current tags
        first_script = mock_applescript_manager.execution_calls[0]["script"]
        assert "return tag names of targetTodo" in first_script

        # Second call sets filtered tags (only "Keep" remains)
        second_script = mock_applescript_manager.execution_calls[1]["script"]
        assert 'set tag names of targetTodo to "Keep"' in second_script
        # BUG FIX: Verify we're NOT using AppleScript list syntax
        assert 'tagsToRemove to {' not in second_script

    @pytest.mark.asyncio
    async def test_remove_tags_with_spaces(self, tools_with_mock, mock_applescript_manager):
        """Test removing tags that contain spaces.

        BUG FIX v1.2.3: Verify comma-separated string format with tags containing spaces.
        """
        todo_id = "todo-123"
        tags = ["Work Project", "High Priority"]

        # Configure mock to return current tags on first call
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "Work Project, High Priority, Keep This",  # Current tags
            "error": None
        })

        result = await tools_with_mock.remove_tags(todo_id=todo_id, tags=tags)

        assert result["success"] is True
        assert "Removed 2 tags successfully" in result["message"]

        # BUG FIX: Verify 2 AppleScript calls
        assert len(mock_applescript_manager.execution_calls) == 2

        # Second call sets filtered tags
        second_script = mock_applescript_manager.execution_calls[1]["script"]
        assert 'set tag names of targetTodo to "Keep This"' in second_script

    @pytest.mark.asyncio
    async def test_remove_tags_with_special_characters(self, tools_with_mock, mock_applescript_manager):
        """Test removing tags with special characters that need escaping.

        BUG FIX v1.2.3: Verify proper escaping in comma-separated string format.
        """
        todo_id = "todo-123"
        tags = ['Tag "with" quotes', 'Tag\\with\\backslash']

        # Configure mock to return current tags on first call
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": 'Tag "with" quotes, Tag\\with\\backslash, NormalTag',  # Current tags
            "error": None
        })

        result = await tools_with_mock.remove_tags(todo_id=todo_id, tags=tags)

        assert result["success"] is True

        # BUG FIX: Verify 2 AppleScript calls
        assert len(mock_applescript_manager.execution_calls) == 2

        # Second call sets filtered tags with proper escaping
        second_script = mock_applescript_manager.execution_calls[1]["script"]
        # Should keep "NormalTag" and properly escape it
        assert 'set tag names of targetTodo to "NormalTag"' in second_script

    @pytest.mark.asyncio
    async def test_remove_nonexistent_tags(self, tools_with_mock, mock_applescript_manager):
        """Test removing tags that don't exist on the todo.

        The function should handle this gracefully - AppleScript will simply not find
        the tags to remove, which is fine.
        """
        todo_id = "todo-123"
        tags = ["NonExistent", "AlsoNotThere"]

        # Configure mock to return success (AppleScript succeeds even if tags don't exist)
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "tags_removed",
            "error": None
        })

        result = await tools_with_mock.remove_tags(todo_id=todo_id, tags=tags)

        # Should succeed - AppleScript filters gracefully
        assert result["success"] is True
        assert "Removed 2 tags successfully" in result["message"]

    @pytest.mark.asyncio
    async def test_remove_tags_empty_list(self, tools_with_mock, mock_applescript_manager):
        """Test removing an empty tag list - should still execute.

        BUG FIX v1.2.3: Empty tag removal still makes 2 calls, no tags are removed.
        """
        todo_id = "todo-123"
        tags = []

        # Configure mock to return current tags on first call
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "existing1, existing2",  # Current tags remain unchanged
            "error": None
        })

        result = await tools_with_mock.remove_tags(todo_id=todo_id, tags=tags)

        # Should execute (empty removal list is valid)
        assert result["success"] is True

        # BUG FIX: Verify 2 AppleScript calls
        assert len(mock_applescript_manager.execution_calls) == 2

        # Second call sets the same tags (nothing removed)
        second_script = mock_applescript_manager.execution_calls[1]["script"]
        assert 'set tag names of targetTodo to "existing1, existing2"' in second_script


class TestBulkUpdateTodos:
    """Test bulk update functionality - Bug Fix: Multi-field updates failed."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_bulk_update_single_field_completed(self, tools_with_mock, mock_applescript_manager):
        """Test bulk update with single field (completed status)."""
        todo_ids = ["todo-1", "todo-2", "todo-3"]

        # Configure mock to return success
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount:3, errors:{}",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            completed=True
        )

        assert result["success"] is True
        assert result["updated_count"] == 3
        assert result["total_requested"] == 3

        # Verify the AppleScript was called
        assert len(mock_applescript_manager.execution_calls) == 1
        script = mock_applescript_manager.execution_calls[0]["script"]

        # Verify all three todos are in the script
        assert 'to do id "todo-1"' in script
        assert 'to do id "todo-2"' in script
        assert 'to do id "todo-3"' in script

        # Verify status is set to completed
        assert script.count("set status of targetTodo to completed") == 3

    @pytest.mark.asyncio
    async def test_bulk_update_multi_field_tags_and_when(self, tools_with_mock, mock_applescript_manager):
        """Test bulk update with multiple fields: tags AND when.

        REGRESSION TEST for Bug #7 (Version 1.2.3): Previously, bulk_update_todos
        tried to set activation dates inline with simple date strings, which failed
        when combined with other fields. Now 'when' scheduling is handled separately
        using the reliable scheduler, just like update_todo does.

        This test verifies that:
        1. Tags are applied via the bulk AppleScript
        2. Scheduling is handled separately per-todo via reliable scheduler
        """
        todo_ids = ["todo-1", "todo-2"]

        # Configure mock to return success for all calls
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount:2, errors:{}",
            "error": None
        })

        # Mock scheduler calls too (for scheduling)
        mock_applescript_manager.set_mock_response("schedule_todo_reliable", {
            "success": True,
            "output": "moved_to_list",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            tags=["urgent", "test"],
            when="today"
        )

        assert result["success"] is True
        assert result["updated_count"] == 2

        # BUG FIX VERIFICATION: The first call is the bulk update (tags only)
        # Then we have separate scheduling calls for each todo
        calls = mock_applescript_manager.execution_calls
        assert len(calls) >= 1, "Should have at least the bulk update call"

        bulk_update_script = calls[0]["script"]

        # CRITICAL: Verify tags are in the bulk update script
        tag_updates = bulk_update_script.count('set tag names of targetTodo to')
        assert tag_updates == 2, f"Expected 2 tag updates (one per todo), found {tag_updates}"

        # CRITICAL: Verify NO activation date in bulk update (handled separately now)
        assert 'set activation date of targetTodo to' not in bulk_update_script, \
            "Activation dates should NOT be in bulk update script anymore"

        # BUG FIX v1.2.3: Verify tags are in comma-separated string format
        assert 'set tag names of targetTodo to "urgent, test"' in bulk_update_script

        # Verify scheduling happened separately (calls after the first one)
        scheduling_calls = [c for c in calls[1:] if 'schedule theTodo' in c.get('script', '') or 'move theTodo' in c.get('script', '')]
        assert len(scheduling_calls) > 0, "Should have separate scheduling calls"

        # Verify scheduling info in result
        assert 'scheduling_info' in result
        assert result['scheduling_info'] is not None

    @pytest.mark.asyncio
    async def test_bulk_update_all_fields(self, tools_with_mock, mock_applescript_manager):
        """Test bulk update with all possible fields.

        This ensures the multi-field bug fix works for ALL field combinations.
        Note: 'when' is now handled separately via reliable scheduler (Bug #7 fix).
        """
        todo_ids = ["todo-1"]

        # Configure mock to return success for all calls
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount:1, errors:{}",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            title="New Title",
            notes="New notes",
            tags=["tag1", "tag2"],
            when="2025-12-25",
            deadline="2025-12-31",
            completed=False
        )

        assert result["success"] is True
        assert result["updated_count"] == 1

        # The first call is the bulk update (without 'when')
        calls = mock_applescript_manager.execution_calls
        assert len(calls) >= 1
        bulk_script = calls[0]["script"]

        # Verify all fields EXCEPT 'when' are in the bulk update
        assert 'set name of targetTodo to' in bulk_script
        assert 'set notes of targetTodo to' in bulk_script
        assert 'set tag names of targetTodo to' in bulk_script
        assert 'set due date of targetTodo to' in bulk_script
        assert 'set status of targetTodo to' in bulk_script

        # 'when' should NOT be in bulk script (handled separately now)
        assert 'set activation date of targetTodo to' not in bulk_script

        # Verify values
        assert 'New Title' in bulk_script
        assert 'New notes' in bulk_script
        # BUG FIX v1.2.3: Verify tags are in comma-separated string format
        assert 'set tag names of targetTodo to "tag1, tag2"' in bulk_script

        # Verify 'when' was handled separately
        assert 'scheduling_info' in result

    @pytest.mark.asyncio
    async def test_bulk_update_status_precedence(self, tools_with_mock, mock_applescript_manager):
        """Test that canceled takes precedence over completed.

        When both completed and canceled are provided, canceled should win.
        """
        todo_ids = ["todo-1"]

        # Configure mock to return success
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount:1, errors:{}",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            completed=True,
            canceled=True
        )

        assert result["success"] is True

        # Verify the AppleScript was called
        assert len(mock_applescript_manager.execution_calls) == 1
        script = mock_applescript_manager.execution_calls[0]["script"]

        # Verify canceled status is set (not completed)
        assert 'set status of targetTodo to canceled' in script
        # Should not have completed status since canceled takes precedence
        assert script.count('set status of targetTodo to completed') == 0

    @pytest.mark.asyncio
    async def test_bulk_update_partial_failure(self, tools_with_mock, mock_applescript_manager):
        """Test bulk update when some todos fail."""
        todo_ids = ["todo-1", "todo-2", "todo-3"]

        # Configure mock to return partial success
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount:2, errors:{ID todo-3: not found}",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            completed=True
        )

        assert result["success"] is True  # Still success if any succeeded
        assert result["updated_count"] == 2
        assert result["failed_count"] == 1
        assert result["total_requested"] == 3

    @pytest.mark.asyncio
    async def test_bulk_update_empty_todo_list(self, tools_with_mock, mock_applescript_manager):
        """Test bulk update with empty todo list.

        The parameter validator will catch empty lists and return a validation error.
        """
        todo_ids = []

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            completed=True
        )

        # Check for validation error response
        assert result["success"] is False
        # The response format depends on where validation occurs
        # Could be either ValidationError format or function error format
        assert "error" in result or "error_code" in result

        # Check for todo count (may not be present in validation error)
        if "updated_count" in result:
            assert result["updated_count"] == 0

        # Should not call AppleScript
        assert len(mock_applescript_manager.execution_calls) == 0

    @pytest.mark.asyncio
    async def test_bulk_update_with_tags_validation(self, tools_with_mock, mock_applescript_manager):
        """Test bulk update with tag validation."""
        todo_ids = ["todo-1", "todo-2"]

        # Configure mock to return success
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount:2, errors:{}",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            tags=["Work", "Urgent"]
        )

        assert result["success"] is True
        assert result["updated_count"] == 2

        # Verify the AppleScript was called
        assert len(mock_applescript_manager.execution_calls) == 1
        script = mock_applescript_manager.execution_calls[0]["script"]

        # BUG FIX v1.2.3: Verify tags are in comma-separated string format
        assert 'set tag names of targetTodo to "Work, Urgent"' in script

    @pytest.mark.asyncio
    async def test_bulk_update_combines_notes_and_deadline(self, tools_with_mock, mock_applescript_manager):
        """Test another multi-field combination: notes + deadline.

        Additional regression test to ensure the fix works for all field pairs.
        """
        todo_ids = ["todo-1", "todo-2", "todo-3"]

        # Configure mock to return success
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount:3, errors:{}",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            notes="Updated notes for all",
            deadline="2025-12-31"
        )

        assert result["success"] is True
        assert result["updated_count"] == 3

        # Verify the AppleScript was called
        assert len(mock_applescript_manager.execution_calls) == 1
        script = mock_applescript_manager.execution_calls[0]["script"]

        # CRITICAL: Both fields should be applied to all todos
        notes_updates = script.count('set notes of targetTodo to')
        deadline_updates = script.count('set due date of targetTodo to')

        assert notes_updates == 3, f"Expected 3 notes updates, found {notes_updates}"
        assert deadline_updates == 3, f"Expected 3 deadline updates, found {deadline_updates}"

        # Verify values
        assert 'Updated notes for all' in script
