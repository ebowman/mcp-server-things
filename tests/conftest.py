"""
Global pytest configuration and fixtures for Things 3 MCP server tests.

This module provides shared fixtures, mock implementations, and test utilities
for comprehensive testing of the Things 3 MCP server without requiring actual
Things 3 installation.
"""

import asyncio
import json
import pytest
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from things_mcp.models import Todo, Project, Area, Tag, TodoResult
from things_mcp.config import ThingsMCPConfig
from things_mcp.server import ThingsMCPServer
from things_mcp.services.applescript_manager import AppleScriptManager


# Test Data Fixtures
@pytest.fixture
def sample_todo_data():
    """Sample todo data for testing."""
    return {
        "id": "todo-123",
        "name": "Sample Todo",
        "notes": "This is a test todo item",
        "status": "open",
        "creation_date": datetime.now() - timedelta(days=1),
        "modification_date": datetime.now(),
        "due_date": None,
        "activation_date": None,
        "completion_date": None,
        "cancellation_date": None,
        "tag_names": ["urgent", "work"],
        "area_name": "Personal",
        "project_name": None,
        "contact_name": None
    }


@pytest.fixture
def sample_project_data():
    """Sample project data for testing."""
    return {
        "id": "project-456",
        "name": "Sample Project",
        "notes": "This is a test project",
        "status": "open",
        "creation_date": datetime.now() - timedelta(days=5),
        "modification_date": datetime.now(),
        "due_date": (datetime.now() + timedelta(days=30)).date(),
        "activation_date": datetime.now(),
        "completion_date": None,
        "cancellation_date": None,
        "tag_names": ["work", "important"],
        "area_name": "Work",
        "project_name": None,
        "contact_name": None
    }


@pytest.fixture
def sample_area_data():
    """Sample area data for testing."""
    return {
        "id": "area-789",
        "name": "Work Area",
        "collapsed": False,
        "tag_names": ["work"]
    }


@pytest.fixture
def sample_tag_data():
    """Sample tag data for testing."""
    return {
        "id": "tag-101",
        "name": "urgent",
        "keyboard_shortcut": "u",
        "parent_tag": None
    }


@pytest.fixture
def multiple_todos_data(sample_todo_data):
    """Multiple todos for list testing."""
    todos = []
    for i in range(5):
        todo = sample_todo_data.copy()
        todo["id"] = f"todo-{i+1}"
        todo["name"] = f"Todo {i+1}"
        todo["status"] = "completed" if i % 2 == 0 else "open"
        todos.append(todo)
    return todos


@pytest.fixture
def multiple_projects_data(sample_project_data):
    """Multiple projects for list testing."""
    projects = []
    for i in range(3):
        project = sample_project_data.copy()
        project["id"] = f"project-{i+1}"
        project["name"] = f"Project {i+1}"
        projects.append(project)
    return projects


# Mock AppleScript Manager
class MockAppleScriptManager:
    """Mock AppleScript manager for testing without Things 3 dependency."""
    
    def __init__(self, config=None, error_handler=None, cache_manager=None):
        self.config = config
        self.error_handler = error_handler
        self.cache_manager = cache_manager
        self.execution_calls = []
        self.url_scheme_calls = []
        self.mock_responses = {}
        self.should_fail = False
        self.failure_error = "Mock failure"
        
    async def execute_applescript(self, script: str, script_name: Optional[str] = None, cache_key: Optional[str] = None):
        """Mock AppleScript execution."""
        self.execution_calls.append({
            "script": script,
            "script_name": script_name,
            "cache_key": cache_key,
            "timestamp": datetime.now()
        })
        
        if self.should_fail:
            return {
                "success": False,
                "error": self.failure_error,
                "output": None,
                "method": "applescript"
            }
        
        # Return predefined mock response or default success
        mock_key = script_name or "default"
        if mock_key in self.mock_responses:
            return self.mock_responses[mock_key]
        
        return {
            "success": True,
            "output": "mock_output",
            "error": None,
            "method": "applescript"
        }
    
    async def execute_url_scheme(self, action: str, parameters: Optional[Dict[str, Any]] = None, cache_key: Optional[str] = None):
        """Mock URL scheme execution."""
        self.url_scheme_calls.append({
            "action": action,
            "parameters": parameters or {},
            "cache_key": cache_key,
            "timestamp": datetime.now()
        })
        
        if self.should_fail:
            return {
                "success": False,
                "error": self.failure_error,
                "method": "url_scheme"
            }
        
        # Return predefined mock response or default success
        mock_key = f"url_{action}"
        if mock_key in self.mock_responses:
            return self.mock_responses[mock_key]
        
        return {
            "success": True,
            "data": {"result": "success"},
            "method": "url_scheme"
        }
    
    async def check_things_availability(self):
        """Mock Things 3 availability check."""
        if self.should_fail:
            return {
                "success": False,
                "error": "Things 3 not available",
                "data": {}
            }
        
        return {
            "success": True,
            "data": {"version": "3.20.1", "available": True},
            "error": None
        }
    
    async def get_execution_stats(self):
        """Mock execution statistics."""
        return {
            "total_executions": len(self.execution_calls) + len(self.url_scheme_calls),
            "applescript_executions": len(self.execution_calls),
            "url_scheme_executions": len(self.url_scheme_calls),
            "cache_hits": 0,
            "cache_misses": 0,
            "average_execution_time": 0.1,
            "success_rate": 0.0 if self.should_fail else 1.0
        }
    
    def set_mock_response(self, key: str, response: Dict[str, Any]):
        """Set a mock response for specific operations."""
        self.mock_responses[key] = response
    
    def set_failure_mode(self, should_fail: bool, error: str = "Mock failure"):
        """Set failure mode for testing error conditions."""
        self.should_fail = should_fail
        self.failure_error = error
    
    def reset_calls(self):
        """Reset call tracking."""
        self.execution_calls.clear()
        self.url_scheme_calls.clear()
    
    # Add missing methods expected by tests
    async def get_todos(self, **kwargs):
        """Mock get_todos method."""
        return self.mock_responses.get("get_todos", {
            "success": True,
            "data": [],
            "error": None
        })
    
    async def get_projects(self, **kwargs):
        """Mock get_projects method."""
        return self.mock_responses.get("get_projects", {
            "success": True,
            "data": [],
            "error": None
        })
    
    async def get_areas(self, **kwargs):
        """Mock get_areas method.""" 
        return self.mock_responses.get("get_areas", {
            "success": True,
            "data": [],
            "error": None
        })
    
    async def add_todo(self, **kwargs):
        """Mock add_todo method."""
        return self.mock_responses.get("add_todo", {
            "success": True,
            "data": {"id": "new-todo-123"},
            "error": None
        })
    
    async def update_todo(self, **kwargs):
        """Mock update_todo method."""
        return self.mock_responses.get("update_todo", {
            "success": True,
            "data": {"id": kwargs.get("id", "todo-123"), "updated": True},
            "error": None
        })
    
    async def delete_todo(self, **kwargs):
        """Mock delete_todo method."""
        return self.mock_responses.get("delete_todo", {
            "success": True,
            "data": {"deleted": True},
            "error": None
        })


@pytest.fixture
def mock_applescript_manager():
    """Fixture providing mock AppleScript manager."""
    return MockAppleScriptManager()


@pytest.fixture
def mock_applescript_manager_with_data(mock_applescript_manager, sample_todo_data, sample_project_data, sample_area_data):
    """Mock AppleScript manager pre-configured with sample data."""
    # Configure mock responses for common operations
    mock_applescript_manager.set_mock_response("get_todos", {
        "success": True,
        "data": [sample_todo_data],
        "error": None
    })
    
    mock_applescript_manager.set_mock_response("get_projects", {
        "success": True,
        "data": [sample_project_data],
        "error": None
    })
    
    mock_applescript_manager.set_mock_response("get_areas", {
        "success": True,
        "data": [sample_area_data],
        "error": None
    })
    
    mock_applescript_manager.set_mock_response("url_add", {
        "success": True,
        "data": {"id": "new-todo-123"},
        "method": "url_scheme"
    })
    
    mock_applescript_manager.set_mock_response("url_update", {
        "success": True,
        "data": {"id": "todo-123", "updated": True},
        "method": "url_scheme"
    })
    
    return mock_applescript_manager


# Mock Service Classes
class MockErrorHandler:
    """Mock error handler for testing."""
    
    def __init__(self, enable_detailed_logging=False):
        self.enable_detailed_logging = enable_detailed_logging
        self.errors = []
    
    async def handle_error(self, error: Exception, context: str = ""):
        """Mock error handling."""
        self.errors.append({
            "error": str(error),
            "context": context,
            "timestamp": datetime.now()
        })
    
    async def get_error_statistics(self):
        """Mock error statistics."""
        return {
            "total_errors": len(self.errors),
            "recent_errors": self.errors[-10:] if self.errors else [],
            "error_rate": 0.1 if self.errors else 0.0
        }
    
    async def reset_statistics(self):
        """Reset error statistics."""
        self.errors.clear()


class MockCacheManager:
    """Mock cache manager for testing."""
    
    def __init__(self, max_size=1000, default_ttl=300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache = {}
        self.stats = {"hits": 0, "misses": 0}
    
    async def get(self, key: str):
        """Mock cache get."""
        if key in self.cache:
            self.stats["hits"] += 1
            return self.cache[key]
        self.stats["misses"] += 1
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Mock cache set."""
        self.cache[key] = value
    
    async def delete(self, key: str):
        """Mock cache delete."""
        self.cache.pop(key, None)
    
    async def clear(self):
        """Mock cache clear."""
        self.cache.clear()
        return True
    
    async def size(self):
        """Mock cache size."""
        return len(self.cache)
    
    async def get_memory_usage(self):
        """Mock memory usage."""
        return len(str(self.cache)) * 8  # Rough estimate
    
    async def initialize(self):
        """Mock initialization."""
        pass


class MockValidationService:
    """Mock validation service for testing."""
    
    def __init__(self, config=None):
        self.config = config
        self.validation_errors = []
    
    def validate_todo_data(self, data: Dict[str, Any]) -> bool:
        """Mock todo validation."""
        required_fields = ["title"]
        for field in required_fields:
            if field not in data or not data[field]:
                self.validation_errors.append(f"Missing required field: {field}")
                return False
        return True
    
    def validate_project_data(self, data: Dict[str, Any]) -> bool:
        """Mock project validation."""
        required_fields = ["title"]
        for field in required_fields:
            if field not in data or not data[field]:
                self.validation_errors.append(f"Missing required field: {field}")
                return False
        return True
    
    def get_validation_errors(self) -> List[str]:
        """Get validation errors."""
        return self.validation_errors.copy()
    
    def clear_errors(self):
        """Clear validation errors."""
        self.validation_errors.clear()


@pytest.fixture
def mock_error_handler():
    """Fixture providing mock error handler."""
    return MockErrorHandler()


@pytest.fixture
def mock_cache_manager():
    """Fixture providing mock cache manager."""
    return MockCacheManager()


@pytest.fixture
def mock_validation_service():
    """Fixture providing mock validation service."""
    return MockValidationService()


# Server Configuration
@pytest.fixture
def test_config():
    """Test configuration for Things MCP server."""
    return ThingsMCPConfig(
        applescript_timeout=5,
        applescript_retry_count=1,
        cache_max_size=100,
        cache_default_ttl=60,
        enable_caching=True,
        enable_detailed_logging=True,
        enable_debug_logging=False
    )


@pytest.fixture
async def mock_server(test_config, mock_applescript_manager_with_data, mock_error_handler, mock_cache_manager, mock_validation_service):
    """Fixture providing fully mocked Things MCP server."""
    with patch('things_mcp.server.AppleScriptManager') as mock_asm_class, \
         patch('things_mcp.server.ErrorHandler') as mock_eh_class, \
         patch('things_mcp.server.CacheManager') as mock_cm_class, \
         patch('things_mcp.server.ValidationService') as mock_vs_class:
        
        # Configure the mocked classes to return our mock instances
        mock_asm_class.return_value = mock_applescript_manager_with_data
        mock_eh_class.return_value = mock_error_handler
        mock_cm_class.return_value = mock_cache_manager
        mock_vs_class.return_value = mock_validation_service
        
        # Create server instance
        server = ThingsMCPServer(config=test_config)
        
        # Store references to mocks for test access
        server._mock_applescript_manager = mock_applescript_manager_with_data
        server._mock_error_handler = mock_error_handler
        server._mock_cache_manager = mock_cache_manager
        server._mock_validation_service = mock_validation_service
        
        yield server


# Test Utilities
@pytest.fixture
def assert_todo_structure():
    """Fixture providing todo structure assertion helper."""
    def _assert_todo_structure(todo_dict: Dict[str, Any]):
        """Assert that a dictionary has the expected todo structure."""
        required_fields = ["id", "title", "status"]
        optional_fields = ["notes", "tags", "creation_date", "modification_date", 
                          "due_date", "project_uuid", "area_name"]
        
        # Check required fields
        for field in required_fields:
            assert field in todo_dict, f"Missing required field: {field}"
            assert todo_dict[field] is not None, f"Required field {field} is None"
        
        # Check that optional fields exist (can be None)
        for field in optional_fields:
            assert field in todo_dict, f"Missing optional field: {field}"
        
        # Check data types
        assert isinstance(todo_dict["id"], str), "ID should be string"
        assert isinstance(todo_dict["title"], str), "Title should be string"
        assert todo_dict["status"] in ["open", "completed", "canceled"], "Invalid status"
        
        if todo_dict["tags"]:
            assert isinstance(todo_dict["tags"], list), "Tags should be list"
    
    return _assert_todo_structure


@pytest.fixture
def assert_project_structure():
    """Fixture providing project structure assertion helper."""
    def _assert_project_structure(project_dict: Dict[str, Any]):
        """Assert that a dictionary has the expected project structure."""
        required_fields = ["id", "title", "status"]
        optional_fields = ["notes", "tags", "creation_date", "modification_date", 
                          "due_date", "area_name", "todos"]
        
        # Check required fields
        for field in required_fields:
            assert field in project_dict, f"Missing required field: {field}"
            assert project_dict[field] is not None, f"Required field {field} is None"
        
        # Check that optional fields exist (can be None)
        for field in optional_fields:
            assert field in project_dict, f"Missing optional field: {field}"
        
        # Check data types
        assert isinstance(project_dict["id"], str), "ID should be string"
        assert isinstance(project_dict["title"], str), "Title should be string"
        assert project_dict["status"] in ["open", "completed", "canceled"], "Invalid status"
        
        if project_dict["todos"]:
            assert isinstance(project_dict["todos"], list), "Todos should be list"
    
    return _assert_project_structure


# Event Loop Configuration
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Async Test Markers
pytestmark = pytest.mark.asyncio


# Mock Response Builders
def build_applescript_success_response(data: Any = None):
    """Build a successful AppleScript response."""
    return {
        "success": True,
        "output": json.dumps(data) if data else "success",
        "error": None,
        "method": "applescript",
        "execution_time": 0.1
    }


def build_applescript_error_response(error: str = "Mock error"):
    """Build an error AppleScript response."""
    return {
        "success": False,
        "output": None,
        "error": error,
        "method": "applescript",
        "execution_time": 0.0
    }


def build_url_scheme_success_response(data: Any = None):
    """Build a successful URL scheme response."""
    return {
        "success": True,
        "data": data or {"result": "success"},
        "error": None,
        "method": "url_scheme"
    }


def build_url_scheme_error_response(error: str = "Mock URL scheme error"):
    """Build an error URL scheme response."""
    return {
        "success": False,
        "data": None,
        "error": error,
        "method": "url_scheme"
    }