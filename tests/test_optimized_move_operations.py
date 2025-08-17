"""
Test suite for optimized move operations with native location detection.

This test verifies that the move operations use efficient AppleScript
location detection instead of fetching and checking all list contents.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from src.things_mcp.move_operations import MoveOperationsTools
from src.things_mcp.services.applescript_manager import AppleScriptManager
from src.things_mcp.services.validation_service import ValidationService


class TestOptimizedMoveOperations:
    """Test optimized move operations with native location detection."""
    
    @pytest.fixture
    async def move_tools(self):
        """Create MoveOperationsTools instance with mocked dependencies."""
        applescript_manager = Mock(spec=AppleScriptManager)
        validation_service = Mock(spec=ValidationService)
        return MoveOperationsTools(applescript_manager, validation_service)
    
    @pytest.mark.asyncio
    async def test_efficient_location_detection_today(self, move_tools):
        """Test that Today list detection uses scheduled date properties."""
        # Mock AppleScript response for a todo in Today list
        today_todo_response = {
            "success": True,
            "output": '{id:"test-123", name:"Test Todo", notes:"", status:open, current_list:"today"}'
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(return_value=today_todo_response)
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "test-123",
            "name": "Test Todo", 
            "notes": "",
            "status": "open",
            "current_list": "today"
        })
        
        result = await move_tools._get_todo_info("test-123")
        
        assert result["success"] is True
        assert result["todo"]["current_list"] == "today"
        
        # Verify the AppleScript uses native properties, not list iteration
        called_script = move_tools.applescript.execute_applescript.call_args[0][0]
        assert "getCurrentLocation" in called_script
        assert "set todayItems to to dos of list" not in called_script
        assert "scheduled date" in called_script
    
    @pytest.mark.asyncio
    async def test_efficient_location_detection_upcoming(self, move_tools):
        """Test that Upcoming list detection uses scheduled date properties."""
        upcoming_todo_response = {
            "success": True,
            "output": '{id:"test-456", name:"Future Todo", notes:"", status:open, current_list:"upcoming"}'
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(return_value=upcoming_todo_response)
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "test-456",
            "name": "Future Todo",
            "notes": "",
            "status": "open", 
            "current_list": "upcoming"
        })
        
        result = await move_tools._get_todo_info("test-456")
        
        assert result["success"] is True
        assert result["todo"]["current_list"] == "upcoming"
        
        # Verify efficient detection logic
        called_script = move_tools.applescript.execute_applescript.call_args[0][0]
        assert "startOfTomorrow" in called_script
        assert "else if todoScheduledDate ≥ startOfTomorrow then" in called_script
    
    @pytest.mark.asyncio
    async def test_efficient_location_detection_someday(self, move_tools):
        """Test that Someday list detection uses targeted queries."""
        someday_todo_response = {
            "success": True,
            "output": '{id:"test-789", name:"Someday Todo", notes:"", status:open, current_list:"someday"}'
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(return_value=someday_todo_response)
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "test-789",
            "name": "Someday Todo",
            "notes": "",
            "status": "open",
            "current_list": "someday"
        })
        
        result = await move_tools._get_todo_info("test-789")
        
        assert result["success"] is True
        assert result["todo"]["current_list"] == "someday"
        
        # Verify targeted query instead of bulk list fetching
        called_script = move_tools.applescript.execute_applescript.call_args[0][0]
        assert "to dos whose id is" in called_script
        assert "set somedayTodos to to dos" not in called_script  # Should not fetch all todos
    
    @pytest.mark.asyncio
    async def test_project_location_detection(self, move_tools):
        """Test that project location is detected efficiently."""
        project_todo_response = {
            "success": True,
            "output": '{id:"test-proj", name:"Project Todo", notes:"", status:open, current_list:"project:proj-123"}'
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(return_value=project_todo_response)
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "test-proj",
            "name": "Project Todo",
            "notes": "",
            "status": "open",
            "current_list": "project:proj-123"
        })
        
        result = await move_tools._get_todo_info("test-proj")
        
        assert result["success"] is True
        assert result["todo"]["current_list"] == "project:proj-123"
        
        # Verify project detection uses direct property access
        called_script = move_tools.applescript.execute_applescript.call_args[0][0]
        assert "project of theTodo" in called_script
        assert "id of project of theTodo" in called_script
    
    @pytest.mark.asyncio
    async def test_area_location_detection(self, move_tools):
        """Test that area location is detected efficiently."""
        area_todo_response = {
            "success": True,
            "output": '{id:"test-area", name:"Area Todo", notes:"", status:open, current_list:"area:area-456"}'
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(return_value=area_todo_response)
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "test-area",
            "name": "Area Todo",
            "notes": "",
            "status": "open",
            "current_list": "area:area-456"
        })
        
        result = await move_tools._get_todo_info("test-area")
        
        assert result["success"] is True
        assert result["todo"]["current_list"] == "area:area-456"
        
        # Verify area detection uses direct property access
        called_script = move_tools.applescript.execute_applescript.call_args[0][0]
        assert "area of theTodo" in called_script
        assert "id of area of theTodo" in called_script
    
    @pytest.mark.asyncio 
    async def test_completed_todo_detection(self, move_tools):
        """Test that completed todos are detected as being in logbook."""
        completed_todo_response = {
            "success": True,
            "output": '{id:"test-done", name:"Completed Todo", notes:"", status:completed, current_list:"logbook"}'
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(return_value=completed_todo_response)
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "test-done",
            "name": "Completed Todo",
            "notes": "",
            "status": "completed",
            "current_list": "logbook"
        })
        
        result = await move_tools._get_todo_info("test-done")
        
        assert result["success"] is True
        assert result["todo"]["current_list"] == "logbook"
        
        # Verify status-based detection
        called_script = move_tools.applescript.execute_applescript.call_args[0][0]
        assert "if todoStatus is completed then" in called_script
        assert 'return "logbook"' in called_script
    
    @pytest.mark.asyncio
    async def test_canceled_todo_detection(self, move_tools):
        """Test that canceled todos are detected as being in trash."""
        canceled_todo_response = {
            "success": True,
            "output": '{id:"test-trash", name:"Canceled Todo", notes:"", status:canceled, current_list:"trash"}'
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(return_value=canceled_todo_response)
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "test-trash",
            "name": "Canceled Todo",
            "notes": "",
            "status": "canceled", 
            "current_list": "trash"
        })
        
        result = await move_tools._get_todo_info("test-trash")
        
        assert result["success"] is True
        assert result["todo"]["current_list"] == "trash"
        
        # Verify status-based detection
        called_script = move_tools.applescript.execute_applescript.call_args[0][0]
        assert "if todoStatus is canceled then" in called_script
        assert 'return "trash"' in called_script
    
    @pytest.mark.asyncio
    async def test_no_bulk_list_fetching(self, move_tools):
        """Test that the optimized version doesn't fetch entire list contents."""
        inbox_todo_response = {
            "success": True, 
            "output": '{id:"test-inbox", name:"Inbox Todo", notes:"", status:open, current_list:"inbox"}'
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(return_value=inbox_todo_response)
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "test-inbox",
            "name": "Inbox Todo",
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        })
        
        result = await move_tools._get_todo_info("test-inbox")
        
        assert result["success"] is True
        
        # Verify the old inefficient patterns are NOT present
        called_script = move_tools.applescript.execute_applescript.call_args[0][0]
        
        # These patterns should NOT exist in the optimized version
        assert "set todayItems to to dos of list" not in called_script
        assert "set upcomingItems to to dos of list" not in called_script
        assert "set anytimeItems to to dos of list" not in called_script
        assert "set somedayItems to to dos of list" not in called_script
        assert "set inboxItems to to dos of list" not in called_script
        assert "if theTodo is in todayItems then" not in called_script
        
        # These efficient patterns SHOULD exist
        assert "getCurrentLocation" in called_script
        assert "scheduled date" in called_script
        assert "to dos whose id is" in called_script

    @pytest.mark.asyncio
    async def test_move_operation_integration(self, move_tools):
        """Test that move operation works with optimized location detection."""
        # Mock validation
        move_tools.validator.validate_todo_id = AsyncMock(return_value={"valid": True})
        
        # Mock todo info with optimized detection
        todo_info_response = {
            "success": True,
            "output": '{id:"move-test", name:"Test Move", notes:"", status:open, current_list:"inbox"}'
        }
        
        # Mock move execution
        move_success_response = {
            "success": True,
            "output": "MOVED to today"
        }
        
        move_tools.applescript.execute_applescript = AsyncMock(side_effect=[
            todo_info_response,  # For _get_todo_info
            move_success_response  # For _execute_move
        ])
        move_tools.applescript._parse_applescript_record = Mock(return_value={
            "id": "move-test",
            "name": "Test Move",
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        })
        
        result = await move_tools.move_record("move-test", "today")
        
        assert result["success"] is True
        assert result["destination"] == "today"
        assert result["original_location"] == "inbox"
        
        # Verify optimized location detection was used
        first_call_script = move_tools.applescript.execute_applescript.call_args_list[0][0][0]
        assert "getCurrentLocation" in first_call_script


if __name__ == "__main__":
    pytest.main([__file__, "-v"])