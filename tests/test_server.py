"""Tests for the Things MCP server implementation."""

import pytest
from unittest.mock import Mock, patch

from src.things_mcp.simple_server import ThingsMCPServer
from src.things_mcp.applescript_manager import AppleScriptManager
from src.things_mcp.tools import ThingsTools


class TestThingsMCPServer:
    """Test cases for the ThingsMCPServer."""
    
    def test_server_initialization(self):
        """Test that the server initializes correctly."""
        with patch('src.things_mcp.simple_server.AppleScriptManager') as mock_applescript:
            mock_applescript.return_value = Mock()
            
            server = ThingsMCPServer()
            
            assert server is not None
            assert server.mcp is not None
            assert server.applescript_manager is not None
            assert server.tools is not None
    
    def test_health_check(self):
        """Test the health check functionality."""
        with patch('src.things_mcp.simple_server.AppleScriptManager') as mock_applescript:
            mock_manager = Mock()
            mock_manager.is_things_running.return_value = True
            mock_manager._get_current_timestamp.return_value = "2023-01-01T00:00:00"
            mock_applescript.return_value = mock_manager
            
            server = ThingsMCPServer()
            
            # Since health_check is registered as a tool, we need to test it differently
            # This is a placeholder test structure
            assert hasattr(server, 'applescript_manager')
            assert hasattr(server, 'tools')


class TestAppleScriptManager:
    """Test cases for the AppleScriptManager."""
    
    def test_manager_initialization(self):
        """Test that the manager initializes with default values."""
        manager = AppleScriptManager()
        
        assert manager.timeout == 30
        assert manager.retry_count == 3
        assert manager._cache == {}
        assert manager._cache_ttl == 300
    
    def test_manager_initialization_with_params(self):
        """Test that the manager initializes with custom parameters."""
        manager = AppleScriptManager(timeout=60, retry_count=5)
        
        assert manager.timeout == 60
        assert manager.retry_count == 5
    
    @patch('subprocess.run')
    def test_execute_script_success(self, mock_run):
        """Test successful script execution."""
        mock_run.return_value = Mock(
            returncode=0,
            stdout="test output",
            stderr=""
        )
        
        manager = AppleScriptManager()
        result = manager._execute_script('return "test"')
        
        assert result["success"] is True
        assert result["output"] == "test output"
        assert "execution_time" in result
    
    @patch('subprocess.run')
    def test_execute_script_failure(self, mock_run):
        """Test failed script execution."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="",
            stderr="script error"
        )
        
        manager = AppleScriptManager()
        result = manager._execute_script('invalid script')
        
        assert result["success"] is False
        assert result["error"] == "script error"
        assert result["return_code"] == 1
    
    def test_build_things_url(self):
        """Test Things URL building."""
        manager = AppleScriptManager()
        
        # Test simple action
        url = manager._build_things_url("add", {})
        assert url == "things:///add"
        
        # Test with parameters
        url = manager._build_things_url("add", {"title": "Test Todo", "tags": ["work", "urgent"]})
        assert "things:///add?" in url
        assert "title=Test%20Todo" in url
        assert "tags=work%2Curgent" in url
    
    def test_cache_operations(self):
        """Test cache get and set operations."""
        manager = AppleScriptManager()
        
        # Test cache miss
        result = manager._get_cached_result("test_key")
        assert result is None
        
        # Test cache set and hit
        test_result = {"success": True, "output": "cached"}
        manager._cache_result("test_key", test_result)
        
        cached = manager._get_cached_result("test_key")
        assert cached == test_result
        
        # Test cache clear
        manager.clear_cache()
        cached = manager._get_cached_result("test_key")
        assert cached is None


class TestThingsTools:
    """Test cases for the ThingsTools."""
    
    def test_tools_initialization(self):
        """Test that tools initialize correctly."""
        mock_applescript = Mock()
        tools = ThingsTools(mock_applescript)
        
        assert tools.applescript == mock_applescript
    
    def test_get_todos_no_project(self):
        """Test getting all todos."""
        mock_applescript = Mock()
        mock_applescript.get_todos.return_value = [
            {"id": "1", "name": "Test Todo", "notes": "", "status": "open"}
        ]
        
        tools = ThingsTools(mock_applescript)
        result = tools.get_todos()
        
        assert len(result) == 1
        assert result[0]["title"] == "Test Todo"
        assert result[0]["id"] == "1"
    
    def test_get_todos_with_project(self):
        """Test getting todos for a specific project."""
        mock_applescript = Mock()
        mock_applescript.get_todos.return_value = []
        
        tools = ThingsTools(mock_applescript)
        result = tools.get_todos(project_uuid="project-123")
        
        mock_applescript.get_todos.assert_called_with("project-123")
        assert result == []
    
    def test_add_todo_success(self):
        """Test successful todo addition."""
        mock_applescript = Mock()
        mock_applescript.execute_url_scheme.return_value = {
            "success": True,
            "url": "things:///add?title=Test"
        }
        
        tools = ThingsTools(mock_applescript)
        result = tools.add_todo("Test Todo")
        
        assert result["success"] is True
        assert result["todo"]["title"] == "Test Todo"
    
    def test_add_todo_failure(self):
        """Test failed todo addition."""
        mock_applescript = Mock()
        mock_applescript.execute_url_scheme.return_value = {
            "success": False,
            "error": "Things not available"
        }
        
        tools = ThingsTools(mock_applescript)
        result = tools.add_todo("Test Todo")
        
        assert result["success"] is False
        assert result["error"] == "Things not available"


# Integration test
def test_server_tools_integration():
    """Test that server tools work together."""
    with patch('src.things_mcp.simple_server.AppleScriptManager') as mock_applescript_class:
        mock_applescript = Mock()
        mock_applescript.is_things_running.return_value = True
        mock_applescript._get_current_timestamp.return_value = "2023-01-01T00:00:00"
        mock_applescript_class.return_value = mock_applescript
        
        server = ThingsMCPServer()
        
        # Verify components are initialized
        assert server.applescript_manager == mock_applescript
        assert isinstance(server.tools, ThingsTools)
        assert server.tools.applescript == mock_applescript


if __name__ == "__main__":
    pytest.main([__file__])