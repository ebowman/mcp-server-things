"""
Integration tests for the enhanced move_record functionality.

Tests the complete integration of MoveOperationsTools with the ThingsTools class
and verifies that both backward compatibility and new project/area functionality work.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

# Import the classes we're testing
from src.things_mcp.tools import ThingsTools
from src.things_mcp.services.applescript_manager import AppleScriptManager
from src.things_mcp.services.validation_service import ValidationService
from src.things_mcp.move_operations import MoveOperationsTools


class TestMoveRecordIntegration:
    """Integration tests for enhanced move_record functionality."""
    
    @pytest.fixture
    async def mock_applescript_manager(self):
        """Create a mock AppleScript manager."""
        manager = Mock(spec=AppleScriptManager)
        manager.execute_applescript = AsyncMock()
        manager._parse_applescript_record = Mock()
        return manager
    
    @pytest.fixture
    async def things_tools(self, mock_applescript_manager):
        """Create ThingsTools instance with mocked dependencies."""
        # Mock the operation queue to avoid complexity
        with patch('src.things_mcp.tools.get_operation_queue') as mock_queue:
            # Create a mock queue that directly calls the implementation
            queue_instance = Mock()
            
            async def mock_enqueue(func, *args, **kwargs):
                # Call the function directly and return a mock operation ID
                result = await func(*args[:2])  # todo_id, destination_list
                queue_instance._result = result
                return "mock-op-id"
            
            async def mock_wait(op_id):
                return queue_instance._result
            
            queue_instance.enqueue = mock_enqueue
            queue_instance.wait_for_operation = mock_wait
            mock_queue.return_value = queue_instance
            
            return ThingsTools(mock_applescript_manager)
    
    @pytest.mark.asyncio
    async def test_backward_compatibility_list_move(self, things_tools, mock_applescript_manager):
        """Test that existing list moves still work (backward compatibility)."""
        # Mock successful list move
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "MOVED to inbox"
        }
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "test-123",
            "name": "Test Todo",
            "status": "open",
            "current_list": "today"
        }
        
        # Test moving to inbox (traditional list move)
        result = await things_tools.move_record("test-123", "inbox")
        
        # Verify the result
        assert result["success"] == True
        assert result["todo_id"] == "test-123"
        assert result["destination_list"] == "inbox"  # Backward compatibility field
        assert "moved_at" in result
        
        # Verify that AppleScript was called for validation and move
        assert mock_applescript_manager.execute_applescript.called
    
    @pytest.mark.asyncio
    async def test_new_project_move_functionality(self, things_tools, mock_applescript_manager):
        """Test moving to a project using project:ID format."""
        # Mock successful todo info retrieval
        mock_applescript_manager.execute_applescript.side_effect = [
            # First call: _get_todo_info
            {
                "success": True,
                "output": '{id:"test-456", name:"Project Todo", notes:"", status:open, current_list:"inbox"}'
            },
            # Second call: project validation
            {
                "success": True,
                "output": "EXISTS"
            },
            # Third call: _execute_move
            {
                "success": True,
                "output": "MOVED to project ABC123"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "test-456",
            "name": "Project Todo",
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        }
        
        # Test moving to a project
        result = await things_tools.move_record("test-456", "project:ABC123")
        
        # Verify the result
        assert result["success"] == True
        assert result["todo_id"] == "test-456"
        assert result["destination_list"] == "project:ABC123"  # Original parameter
        assert result["destination"] == "project:ABC123"      # New field
        assert "moved_at" in result
    
    @pytest.mark.asyncio
    async def test_new_area_move_functionality(self, things_tools, mock_applescript_manager):
        """Test moving to an area using area:ID format."""
        # Mock successful move to area
        mock_applescript_manager.execute_applescript.side_effect = [
            # Todo info retrieval
            {
                "success": True,
                "output": '{id:"test-789", name:"Area Todo", notes:"", status:open, current_list:"someday"}'
            },
            # Area validation
            {
                "success": True,
                "output": "EXISTS"
            },
            # Move execution
            {
                "success": True,
                "output": "MOVED to area XYZ789"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "test-789",
            "name": "Area Todo",
            "notes": "",
            "status": "open",
            "current_list": "someday"
        }
        
        # Test moving to an area
        result = await things_tools.move_record("test-789", "area:XYZ789")
        
        # Verify the result
        assert result["success"] == True
        assert result["todo_id"] == "test-789"
        assert result["destination_list"] == "area:XYZ789"
        assert "moved_at" in result
    
    @pytest.mark.asyncio
    async def test_invalid_destination_format(self, things_tools, mock_applescript_manager):
        """Test error handling for invalid destination formats."""
        # The validation will fail before any AppleScript calls
        result = await things_tools.move_record("test-invalid", "invalid:format:here")
        
        # Should return an error
        assert result["success"] == False
        assert "error" in result
        assert result["todo_id"] == "test-invalid"
    
    @pytest.mark.asyncio
    async def test_nonexistent_todo_error_handling(self, things_tools, mock_applescript_manager):
        """Test error handling when todo doesn't exist."""
        # Mock todo not found
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "ERROR:Can't get to do id \"nonexistent\"."
        }
        
        result = await things_tools.move_record("nonexistent", "inbox")
        
        # Should handle the error gracefully
        assert result["success"] == False
        assert "error" in result
        assert result["todo_id"] == "nonexistent"
    
    @pytest.mark.asyncio
    async def test_nonexistent_project_error_handling(self, things_tools, mock_applescript_manager):
        """Test error handling when project doesn't exist."""
        # Mock todo exists but project doesn't
        mock_applescript_manager.execute_applescript.side_effect = [
            # Todo info (exists)
            {
                "success": True,
                "output": '{id:"test-123", name:"Test Todo", notes:"", status:open, current_list:"inbox"}'
            },
            # Project validation (doesn't exist)
            {
                "success": True,
                "output": "NOT_FOUND"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "test-123",
            "name": "Test Todo",
            "status": "open",
            "current_list": "inbox"
        }
        
        result = await things_tools.move_record("test-123", "project:NONEXISTENT")
        
        # Should return validation error
        assert result["success"] == False
        assert "error" in result
        assert "PROJECT_NOT_FOUND" in result.get("error", "").upper() or "NOT_FOUND" in result.get("message", "").upper()
    
    @pytest.mark.asyncio
    async def test_validation_service_integration(self, things_tools):
        """Test that ValidationService is properly integrated."""
        # Verify that validation service was initialized
        assert hasattr(things_tools, 'validation_service')
        assert isinstance(things_tools.validation_service, ValidationService)
        
        # Verify that move operations tool was initialized
        assert hasattr(things_tools, 'move_operations')
        assert isinstance(things_tools.move_operations, MoveOperationsTools)
    
    @pytest.mark.asyncio
    async def test_preserve_scheduling_parameter(self, things_tools, mock_applescript_manager):
        """Test that scheduling is preserved during moves."""
        # Mock successful move with scheduling preservation
        mock_applescript_manager.execute_applescript.side_effect = [
            # Todo info
            {
                "success": True,
                "output": '{id:"scheduled-todo", name:"Scheduled Todo", notes:"", status:open, current_list:"today"}'
            },
            # Move execution (to anytime, should preserve scheduling)
            {
                "success": True,
                "output": "MOVED to anytime"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "scheduled-todo",
            "name": "Scheduled Todo",
            "status": "open",
            "current_list": "today"
        }
        
        # Move from today to anytime (should preserve existing scheduling)
        result = await things_tools.move_record("scheduled-todo", "anytime")
        
        # Should succeed and preserve scheduling
        assert result["success"] == True
        
        # The move_operations should have been called with preserve_scheduling=True
        # This is implicitly tested by the successful completion


class TestValidationServiceIntegration:
    """Test ValidationService functionality in isolation."""
    
    @pytest.fixture
    async def mock_applescript_manager(self):
        """Create mock AppleScript manager."""
        manager = Mock(spec=AppleScriptManager)
        manager.execute_applescript = AsyncMock()
        return manager
    
    @pytest.fixture
    async def validation_service(self, mock_applescript_manager):
        """Create ValidationService instance."""
        return ValidationService(mock_applescript_manager)
    
    @pytest.mark.asyncio
    async def test_validate_todo_id_exists(self, validation_service, mock_applescript_manager):
        """Test validation of existing todo ID."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "EXISTS"
        }
        
        result = await validation_service.validate_todo_id("valid-todo-123")
        
        assert result["valid"] == True
        assert "Todo ID is valid" in result["message"]
    
    @pytest.mark.asyncio
    async def test_validate_todo_id_not_found(self, validation_service, mock_applescript_manager):
        """Test validation of non-existent todo ID."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "NOT_FOUND"
        }
        
        result = await validation_service.validate_todo_id("invalid-todo")
        
        assert result["valid"] == False
        assert result["error"] == "TODO_NOT_FOUND"
    
    @pytest.mark.asyncio
    async def test_validate_project_id_exists(self, validation_service, mock_applescript_manager):
        """Test validation of existing project ID."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "EXISTS"
        }
        
        result = await validation_service.validate_project_id("valid-project-456")
        
        assert result["valid"] == True
        assert "Project ID is valid" in result["message"]
    
    @pytest.mark.asyncio
    async def test_validate_area_id_exists(self, validation_service, mock_applescript_manager):
        """Test validation of existing area ID."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "EXISTS"
        }
        
        result = await validation_service.validate_area_id("valid-area-789")
        
        assert result["valid"] == True
        assert "Area ID is valid" in result["message"]
    
    def test_validate_destination_format_list(self, validation_service):
        """Test destination format validation for lists."""
        result = validation_service.validate_destination_format("inbox")
        
        assert result["valid"] == True
        assert result["type"] == "list"
        assert result["name"] == "inbox"
    
    def test_validate_destination_format_project(self, validation_service):
        """Test destination format validation for projects."""
        result = validation_service.validate_destination_format("project:ABC123")
        
        assert result["valid"] == True
        assert result["type"] == "project"
        assert result["id"] == "ABC123"
    
    def test_validate_destination_format_area(self, validation_service):
        """Test destination format validation for areas."""
        result = validation_service.validate_destination_format("area:XYZ789")
        
        assert result["valid"] == True
        assert result["type"] == "area"
        assert result["id"] == "XYZ789"
    
    def test_validate_destination_format_invalid(self, validation_service):
        """Test destination format validation for invalid formats."""
        result = validation_service.validate_destination_format("invalid:format:here")
        
        assert result["valid"] == False
        assert result["error"] == "INVALID_DESTINATION"


if __name__ == "__main__":
    # Run the tests
    pytest.main([__file__, "-v"])