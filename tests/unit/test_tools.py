"""
Unit tests for Things 3 MCP tools.

Tests all MCP tool operations including CRUD operations, search functionality,
batch operations, and URL scheme integration with comprehensive mocking.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any, List

from src.things_mcp.tools import ThingsTools
from src.things_mcp.models import Todo, Project, Area


class TestThingsToolsInit:
    """Test ThingsTools initialization."""
    
    def test_init_with_applescript_manager(self, mock_applescript_manager):
        """Test initialization with AppleScript manager."""
        tools = ThingsTools(mock_applescript_manager)
        
        assert tools.applescript == mock_applescript_manager
    
    def test_init_logs_initialization(self, mock_applescript_manager):
        """Test that initialization is logged."""
        with patch('src.things_mcp.tools.logger') as mock_logger:
            tools = ThingsTools(mock_applescript_manager)
            
            mock_logger.info.assert_called_with("Things tools initialized")


class TestGetTodos:
    """Test get_todos functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_get_todos_all(self, tools_with_mock, sample_todo_data):
        """Test getting all todos."""
        # Configure mock to return sample data
        tools_with_mock.applescript.get_todos.return_value = [sample_todo_data]
        
        result = tools_with_mock.get_todos()
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == sample_todo_data["id"]
        assert result[0]["title"] == sample_todo_data["name"]
        assert result[0]["status"] == sample_todo_data["status"]
        
        # Verify AppleScript manager was called correctly
        tools_with_mock.applescript.get_todos.assert_called_once_with(None)
    
    def test_get_todos_by_project(self, tools_with_mock, sample_todo_data):
        """Test getting todos filtered by project."""
        project_uuid = "project-123"
        tools_with_mock.applescript.get_todos.return_value = [sample_todo_data]
        
        result = tools_with_mock.get_todos(project_uuid=project_uuid)
        
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["project_uuid"] == project_uuid
        
        # Verify AppleScript manager was called with project UUID
        tools_with_mock.applescript.get_todos.assert_called_once_with(project_uuid)
    
    def test_get_todos_empty_result(self, tools_with_mock):
        """Test getting todos when none exist."""
        tools_with_mock.applescript.get_todos.return_value = []
        
        result = tools_with_mock.get_todos()
        
        assert isinstance(result, list)
        assert len(result) == 0
    
    def test_get_todos_exception_handling(self, tools_with_mock):
        """Test exception handling in get_todos."""
        tools_with_mock.applescript.get_todos.side_effect = Exception("AppleScript error")
        
        with pytest.raises(Exception) as exc_info:
            tools_with_mock.get_todos()
        
        assert "AppleScript error" in str(exc_info.value)
    
    def test_get_todos_data_transformation(self, tools_with_mock):
        """Test data transformation from AppleScript format to standardized format."""
        applescript_data = {
            "id": "todo-456",
            "name": "AppleScript Todo",
            "notes": "Notes from AppleScript",
            "status": "completed",
            "creation_date": datetime.now(),
            "modification_date": datetime.now()
        }
        
        tools_with_mock.applescript.get_todos.return_value = [applescript_data]
        
        result = tools_with_mock.get_todos()
        
        assert len(result) == 1
        todo = result[0]
        
        # Check transformation
        assert todo["id"] == applescript_data["id"]
        assert todo["uuid"] == applescript_data["id"]  # ID used as UUID
        assert todo["title"] == applescript_data["name"]  # name -> title
        assert todo["notes"] == applescript_data["notes"]
        assert todo["status"] == applescript_data["status"]
        assert todo["creation_date"] == applescript_data["creation_date"]
        
        # Check default values
        assert todo["tags"] == []
        assert todo["checklist_items"] == []


class TestAddTodo:
    """Test add_todo functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_add_todo_minimal(self, tools_with_mock):
        """Test adding todo with minimal required data."""
        title = "New Todo"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.add_todo(title)
        
        assert result["success"] is True
        assert result["message"] == "Todo created successfully"
        assert result["todo"]["title"] == title
        assert "created_at" in result["todo"]
        
        # Verify URL scheme was called correctly
        tools_with_mock.applescript.execute_url_scheme.assert_called_once()
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][0] == "add"  # action
        assert call_args[0][1]["title"] == title
    
    def test_add_todo_full_parameters(self, tools_with_mock):
        """Test adding todo with all parameters."""
        todo_data = {
            "title": "Complex Todo",
            "notes": "Detailed notes",
            "tags": ["work", "urgent"],
            "when": "today",
            "deadline": "2024-12-31",
            "list_id": "project-123",
            "heading": "Important Tasks",
            "checklist_items": ["Step 1", "Step 2", "Step 3"]
        }
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {
            "success": True,
            "url": "things:///add?title=Complex%20Todo"
        }
        
        result = tools_with_mock.add_todo(**todo_data)
        
        assert result["success"] is True
        assert result["todo"]["title"] == todo_data["title"]
        assert result["todo"]["notes"] == todo_data["notes"]
        assert result["todo"]["tags"] == todo_data["tags"]
        assert result["todo"]["when"] == todo_data["when"]
        assert result["todo"]["deadline"] == todo_data["deadline"]
        assert result["todo"]["list_id"] == todo_data["list_id"]
        assert result["todo"]["heading"] == todo_data["heading"]
        assert result["todo"]["checklist_items"] == todo_data["checklist_items"]
        
        # Verify URL scheme parameters
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        params = call_args[0][1]
        assert params["title"] == todo_data["title"]
        assert params["notes"] == todo_data["notes"]
        assert params["tags"] == "work,urgent"
        assert params["when"] == todo_data["when"]
        assert params["deadline"] == todo_data["deadline"]
        assert params["list-id"] == todo_data["list_id"]
        assert params["heading"] == todo_data["heading"]
        assert params["checklist-items"] == "Step 1\nStep 2\nStep 3"
    
    def test_add_todo_with_list_title(self, tools_with_mock):
        """Test adding todo with list title instead of list ID."""
        title = "Todo in Project"
        list_title = "My Project"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.add_todo(title, list_title=list_title)
        
        assert result["success"] is True
        
        # Verify list title parameter
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        params = call_args[0][1]
        assert params["list"] == list_title
        assert "list-id" not in params
    
    def test_add_todo_failure(self, tools_with_mock):
        """Test add_todo when AppleScript operation fails."""
        title = "Failed Todo"
        error_message = "Things 3 not available"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {
            "success": False,
            "error": error_message
        }
        
        result = tools_with_mock.add_todo(title)
        
        assert result["success"] is False
        assert result["error"] == error_message
    
    def test_add_todo_exception_handling(self, tools_with_mock):
        """Test exception handling in add_todo."""
        title = "Exception Todo"
        
        tools_with_mock.applescript.execute_url_scheme.side_effect = Exception("Network error")
        
        with pytest.raises(Exception) as exc_info:
            tools_with_mock.add_todo(title)
        
        assert "Network error" in str(exc_info.value)


class TestUpdateTodo:
    """Test update_todo functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_update_todo_single_field(self, tools_with_mock):
        """Test updating a single field of a todo."""
        todo_id = "todo-123"
        new_title = "Updated Title"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.update_todo(todo_id, title=new_title)
        
        assert result["success"] is True
        assert result["message"] == "Todo updated successfully"
        assert result["todo_id"] == todo_id
        assert "updated_at" in result
        
        # Verify URL scheme call
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][0] == "update"
        params = call_args[0][1]
        assert params["id"] == todo_id
        assert params["title"] == new_title
    
    def test_update_todo_multiple_fields(self, tools_with_mock):
        """Test updating multiple fields of a todo."""
        todo_id = "todo-456"
        updates = {
            "title": "New Title",
            "notes": "New notes",
            "tags": ["updated", "todo"],
            "when": "tomorrow",
            "deadline": "2024-12-25",
            "completed": True
        }
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.update_todo(todo_id, **updates)
        
        assert result["success"] is True
        
        # Verify all parameters were passed
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        params = call_args[0][1]
        assert params["id"] == todo_id
        assert params["title"] == updates["title"]
        assert params["notes"] == updates["notes"]
        assert params["tags"] == "updated,todo"
        assert params["when"] == updates["when"]
        assert params["deadline"] == updates["deadline"]
        assert params["completed"] == "true"
    
    def test_update_todo_status_fields(self, tools_with_mock):
        """Test updating status fields (completed, canceled)."""
        todo_id = "todo-789"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        # Test completed = True
        result = tools_with_mock.update_todo(todo_id, completed=True)
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][1]["completed"] == "true"
        
        # Test completed = False
        tools_with_mock.update_todo(todo_id, completed=False)
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][1]["completed"] == "false"
        
        # Test canceled = True
        tools_with_mock.update_todo(todo_id, canceled=True)
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][1]["canceled"] == "true"
    
    def test_update_todo_none_values(self, tools_with_mock):
        """Test updating todo with None values (should not be included)."""
        todo_id = "todo-none"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.update_todo(
            todo_id,
            title=None,  # Should not be included
            notes="Valid notes",  # Should be included
            tags=None  # Should not be included
        )
        
        assert result["success"] is True
        
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        params = call_args[0][1]
        assert params["id"] == todo_id
        assert params["notes"] == "Valid notes"
        assert "title" not in params
        assert "tags" not in params
    
    def test_update_todo_failure(self, tools_with_mock):
        """Test update_todo when AppleScript operation fails."""
        todo_id = "nonexistent-todo"
        error_message = "Todo not found"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {
            "success": False,
            "error": error_message
        }
        
        result = tools_with_mock.update_todo(todo_id, title="New Title")
        
        assert result["success"] is False
        assert result["error"] == error_message


class TestGetTodoById:
    """Test get_todo_by_id functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_get_todo_by_id_success(self, tools_with_mock):
        """Test successfully getting a todo by ID."""
        todo_id = "todo-123"
        
        tools_with_mock.applescript.execute_applescript.return_value = {
            "success": True,
            "output": "todo data"
        }
        
        result = tools_with_mock.get_todo_by_id(todo_id)
        
        assert result["id"] == todo_id
        assert result["uuid"] == todo_id
        assert result["title"] == "Retrieved Todo"  # Placeholder value
        assert result["status"] == "open"
        assert "retrieved_at" in result
        
        # Verify AppleScript was called
        tools_with_mock.applescript.execute_applescript.assert_called_once()
        call_args = tools_with_mock.applescript.execute_applescript.call_args
        script = call_args[0][0]
        assert todo_id in script
        assert "Things3" in script
    
    def test_get_todo_by_id_failure(self, tools_with_mock):
        """Test get_todo_by_id when todo doesn't exist."""
        todo_id = "nonexistent-todo"
        
        tools_with_mock.applescript.execute_applescript.return_value = {
            "success": False,
            "error": "Todo not found"
        }
        
        with pytest.raises(Exception) as exc_info:
            tools_with_mock.get_todo_by_id(todo_id)
        
        assert f"Todo not found: {todo_id}" in str(exc_info.value)
    
    def test_get_todo_by_id_exception(self, tools_with_mock):
        """Test exception handling in get_todo_by_id."""
        todo_id = "error-todo"
        
        tools_with_mock.applescript.execute_applescript.side_effect = Exception("Script error")
        
        with pytest.raises(Exception) as exc_info:
            tools_with_mock.get_todo_by_id(todo_id)
        
        assert "Script error" in str(exc_info.value)


class TestDeleteTodo:
    """Test delete_todo functionality."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_delete_todo_success(self, tools_with_mock):
        """Test successfully deleting a todo."""
        todo_id = "todo-to-delete"
        
        tools_with_mock.applescript.execute_applescript.return_value = {
            "success": True,
            "output": "deleted"
        }
        
        result = tools_with_mock.delete_todo(todo_id)
        
        assert result["success"] is True
        assert result["message"] == "Todo deleted successfully"
        assert result["todo_id"] == todo_id
        assert "deleted_at" in result
        
        # Verify AppleScript was called with delete command
        call_args = tools_with_mock.applescript.execute_applescript.call_args
        script = call_args[0][0]
        assert todo_id in script
        assert "delete" in script.lower()
    
    def test_delete_todo_failure(self, tools_with_mock):
        """Test delete_todo when operation fails."""
        todo_id = "protected-todo"
        error_message = "Cannot delete completed todo"
        
        tools_with_mock.applescript.execute_applescript.return_value = {
            "success": False,
            "error": error_message
        }
        
        result = tools_with_mock.delete_todo(todo_id)
        
        assert result["success"] is False
        assert result["error"] == error_message
    
    def test_delete_todo_exception(self, tools_with_mock):
        """Test exception handling in delete_todo."""
        todo_id = "error-todo"
        
        tools_with_mock.applescript.execute_applescript.side_effect = Exception("Delete error")
        
        with pytest.raises(Exception) as exc_info:
            tools_with_mock.delete_todo(todo_id)
        
        assert "Delete error" in str(exc_info.value)


class TestProjectOperations:
    """Test project-related operations."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_get_projects(self, tools_with_mock, sample_project_data):
        """Test getting all projects."""
        tools_with_mock.applescript.get_projects.return_value = [sample_project_data]
        
        result = tools_with_mock.get_projects()
        
        assert isinstance(result, list)
        assert len(result) == 1
        
        project = result[0]
        assert project["id"] == sample_project_data["id"]
        assert project["title"] == sample_project_data["name"]
        assert project["status"] == sample_project_data["status"]
        assert project["todos"] == []  # Default empty list
        
        tools_with_mock.applescript.get_projects.assert_called_once()
    
    def test_get_projects_with_items(self, tools_with_mock, sample_project_data):
        """Test getting projects with include_items flag."""
        tools_with_mock.applescript.get_projects.return_value = [sample_project_data]
        
        result = tools_with_mock.get_projects(include_items=True)
        
        assert isinstance(result, list)
        assert len(result) == 1
        # TODO: When implementation supports include_items, verify todos are included
    
    def test_add_project_minimal(self, tools_with_mock):
        """Test adding project with minimal data."""
        title = "New Project"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.add_project(title)
        
        assert result["success"] is True
        assert result["project"]["title"] == title
        
        # Verify URL scheme call
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][0] == "add-project"
        assert call_args[0][1]["title"] == title
    
    def test_add_project_with_todos(self, tools_with_mock):
        """Test adding project with initial todos."""
        title = "Project with Todos"
        todos = ["Todo 1", "Todo 2", "Todo 3"]
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.add_project(title, todos=todos)
        
        assert result["success"] is True
        assert result["project"]["todos"] == todos
        
        # Verify todos parameter
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        params = call_args[0][1]
        assert params["to-dos"] == "Todo 1\nTodo 2\nTodo 3"
    
    def test_update_project(self, tools_with_mock):
        """Test updating a project."""
        project_id = "project-123"
        new_title = "Updated Project"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.update_project(project_id, title=new_title)
        
        assert result["success"] is True
        assert result["project_id"] == project_id
        
        # Verify URL scheme call
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][0] == "update"
        params = call_args[0][1]
        assert params["id"] == project_id
        assert params["title"] == new_title


class TestAreaOperations:
    """Test area-related operations."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_get_areas(self, tools_with_mock, sample_area_data):
        """Test getting all areas."""
        tools_with_mock.applescript.get_areas.return_value = [sample_area_data]
        
        result = tools_with_mock.get_areas()
        
        assert isinstance(result, list)
        assert len(result) == 1
        
        area = result[0]
        assert area["id"] == sample_area_data["id"]
        assert area["title"] == sample_area_data["name"]
        assert area["projects"] == []  # Default empty list
        assert area["todos"] == []  # Default empty list
        
        tools_with_mock.applescript.get_areas.assert_called_once()
    
    def test_get_areas_with_items(self, tools_with_mock, sample_area_data):
        """Test getting areas with include_items flag."""
        tools_with_mock.applescript.get_areas.return_value = [sample_area_data]
        
        result = tools_with_mock.get_areas(include_items=True)
        
        assert isinstance(result, list)
        assert len(result) == 1
        # TODO: When implementation supports include_items, verify projects/todos are included


class TestListOperations:
    """Test list-based operations (inbox, today, etc.)."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        tools = ThingsTools(mock_applescript_manager_with_data)
        # Mock the private _get_list_todos method
        tools._get_list_todos = MagicMock(return_value=[])
        return tools
    
    def test_get_inbox(self, tools_with_mock):
        """Test getting inbox todos."""
        result = tools_with_mock.get_inbox()
        
        assert isinstance(result, list)
        tools_with_mock._get_list_todos.assert_called_once_with("inbox")
    
    def test_get_today(self, tools_with_mock):
        """Test getting today's todos."""
        result = tools_with_mock.get_today()
        
        assert isinstance(result, list)
        tools_with_mock._get_list_todos.assert_called_once_with("today")
    
    def test_get_upcoming(self, tools_with_mock):
        """Test getting upcoming todos."""
        result = tools_with_mock.get_upcoming()
        
        assert isinstance(result, list)
        tools_with_mock._get_list_todos.assert_called_once_with("upcoming")
    
    def test_get_anytime(self, tools_with_mock):
        """Test getting anytime todos."""
        result = tools_with_mock.get_anytime()
        
        assert isinstance(result, list)
        tools_with_mock._get_list_todos.assert_called_once_with("anytime")
    
    def test_get_someday(self, tools_with_mock):
        """Test getting someday todos."""
        result = tools_with_mock.get_someday()
        
        assert isinstance(result, list)
        tools_with_mock._get_list_todos.assert_called_once_with("someday")
    
    def test_get_logbook(self, tools_with_mock):
        """Test getting logbook entries."""
        result = tools_with_mock.get_logbook(limit=25, period="14d")
        
        assert isinstance(result, list)
        tools_with_mock._get_list_todos.assert_called_once_with("logbook", limit=25)
    
    def test_get_trash(self, tools_with_mock):
        """Test getting trashed todos."""
        result = tools_with_mock.get_trash()
        
        assert isinstance(result, list)
        tools_with_mock._get_list_todos.assert_called_once_with("trash")


class TestSearchOperations:
    """Test search and filtering operations."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_search_todos(self, tools_with_mock):
        """Test basic todo search."""
        query = "meeting notes"
        
        result = tools_with_mock.search_todos(query)
        
        assert isinstance(result, list)
        # Note: Current implementation returns empty list (placeholder)
    
    def test_search_advanced(self, tools_with_mock):
        """Test advanced search with filters."""
        filters = {
            "status": "open",
            "type": "to-do",
            "tag": "work",
            "area": "Personal",
            "start_date": "2024-01-01",
            "deadline": "2024-12-31"
        }
        
        result = tools_with_mock.search_advanced(**filters)
        
        assert isinstance(result, list)
        # Note: Current implementation returns empty list (placeholder)
    
    def test_get_tagged_items(self, tools_with_mock):
        """Test getting items with specific tag."""
        tag = "urgent"
        
        result = tools_with_mock.get_tagged_items(tag)
        
        assert isinstance(result, list)
        # Note: Current implementation returns empty list (placeholder)
    
    def test_get_recent(self, tools_with_mock):
        """Test getting recent items."""
        period = "7d"
        
        result = tools_with_mock.get_recent(period)
        
        assert isinstance(result, list)
        # Note: Current implementation returns empty list (placeholder)


class TestUIIntegration:
    """Test UI integration operations."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_show_item_success(self, tools_with_mock):
        """Test showing an item in Things UI."""
        item_id = "today"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.show_item(item_id)
        
        assert result["success"] is True
        assert f"Successfully showed item: {item_id}" in result["message"]
        
        # Verify URL scheme call
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][0] == "show"
        assert call_args[0][1]["id"] == item_id
    
    def test_show_item_with_filters(self, tools_with_mock):
        """Test showing item with query and tag filters."""
        item_id = "anytime"
        query = "important"
        filter_tags = ["urgent", "work"]
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.show_item(item_id, query=query, filter_tags=filter_tags)
        
        assert result["success"] is True
        
        # Verify parameters
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        params = call_args[0][1]
        assert params["id"] == item_id
        assert params["query"] == query
        assert params["filter"] == "urgent,work"
    
    def test_show_item_failure(self, tools_with_mock):
        """Test show_item when operation fails."""
        item_id = "nonexistent"
        error_message = "Item not found"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {
            "success": False,
            "error": error_message
        }
        
        result = tools_with_mock.show_item(item_id)
        
        assert result["success"] is False
        assert result["error"] == error_message
    
    def test_search_items(self, tools_with_mock):
        """Test searching items in Things UI."""
        query = "project planning"
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        result = tools_with_mock.search_items(query)
        
        assert result["success"] is True
        assert f"Successfully searched for: {query}" in result["message"]
        
        # Verify URL scheme call
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        assert call_args[0][0] == "search"
        assert call_args[0][1]["query"] == query


class TestErrorHandlingAndLogging:
    """Test error handling and logging across all tools operations."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_operation_logging(self, tools_with_mock):
        """Test that operations are properly logged."""
        with patch('src.things_mcp.tools.logger') as mock_logger:
            tools_with_mock.applescript.get_todos.return_value = [{"id": "test"}]
            
            result = tools_with_mock.get_todos()
            
            # Verify success is logged
            mock_logger.info.assert_called_with("Retrieved 1 todos")
    
    def test_error_logging(self, tools_with_mock):
        """Test that errors are properly logged."""
        with patch('src.things_mcp.tools.logger') as mock_logger:
            tools_with_mock.applescript.get_todos.side_effect = Exception("Test error")
            
            with pytest.raises(Exception):
                tools_with_mock.get_todos()
            
            # Verify error is logged
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0][0]
            assert "Error getting todos" in error_call
    
    def test_add_todo_error_logging(self, tools_with_mock):
        """Test error logging for add_todo operations."""
        with patch('src.things_mcp.tools.logger') as mock_logger:
            tools_with_mock.applescript.execute_url_scheme.return_value = {
                "success": False,
                "error": "Things not available"
            }
            
            result = tools_with_mock.add_todo("Test Todo")
            
            # Verify error is logged
            mock_logger.error.assert_called()
            error_call = mock_logger.error.call_args[0][0]
            assert "Failed to create todo" in error_call
    
    def test_update_todo_success_logging(self, tools_with_mock):
        """Test success logging for update operations."""
        with patch('src.things_mcp.tools.logger') as mock_logger:
            tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
            
            result = tools_with_mock.update_todo("todo-123", title="Updated")
            
            # Verify success is logged
            mock_logger.info.assert_called()
            info_call = mock_logger.info.call_args[0][0]
            assert "Successfully updated todo" in info_call


class TestDataConsistency:
    """Test data consistency and transformation across operations."""
    
    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager_with_data):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager_with_data)
    
    def test_todo_id_uuid_consistency(self, tools_with_mock, sample_todo_data):
        """Test that ID and UUID fields are consistently set."""
        tools_with_mock.applescript.get_todos.return_value = [sample_todo_data]
        
        result = tools_with_mock.get_todos()
        
        todo = result[0]
        assert todo["id"] == todo["uuid"]  # Should be the same
        assert todo["id"] == sample_todo_data["id"]
    
    def test_name_title_transformation(self, tools_with_mock, sample_todo_data):
        """Test that 'name' field is transformed to 'title'."""
        tools_with_mock.applescript.get_todos.return_value = [sample_todo_data]
        
        result = tools_with_mock.get_todos()
        
        todo = result[0]
        assert todo["title"] == sample_todo_data["name"]
        assert "name" not in todo  # Original name field should not be present
    
    def test_default_field_values(self, tools_with_mock, sample_todo_data):
        """Test that default values are properly set for optional fields."""
        # Remove optional fields from sample data
        minimal_data = {
            "id": sample_todo_data["id"],
            "name": sample_todo_data["name"],
            "status": sample_todo_data["status"]
        }
        
        tools_with_mock.applescript.get_todos.return_value = [minimal_data]
        
        result = tools_with_mock.get_todos()
        
        todo = result[0]
        assert todo["tags"] == []  # Default empty list
        assert todo["checklist_items"] == []  # Default empty list
        assert todo["project_uuid"] is None  # Default None
    
    def test_tag_list_handling(self, tools_with_mock):
        """Test that tag lists are properly handled in URL parameters."""
        tags = ["work", "urgent", "important"]
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        tools_with_mock.add_todo("Test", tags=tags)
        
        # Verify tags are joined with commas
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        params = call_args[0][1]
        assert params["tags"] == "work,urgent,important"
    
    def test_checklist_items_handling(self, tools_with_mock):
        """Test that checklist items are properly formatted."""
        items = ["Item 1", "Item 2", "Item 3"]
        
        tools_with_mock.applescript.execute_url_scheme.return_value = {"success": True}
        
        tools_with_mock.add_todo("Test", checklist_items=items)
        
        # Verify items are joined with newlines
        call_args = tools_with_mock.applescript.execute_url_scheme.call_args
        params = call_args[0][1]
        assert params["checklist-items"] == "Item 1\nItem 2\nItem 3"