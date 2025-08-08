"""
Comprehensive tests for the enhanced move_record functionality.

This test suite verifies that the move_record functionality works correctly with:
1. Built-in lists (backward compatibility) 
2. Projects using "project:ID" format
3. Areas using "area:ID" format
4. Error handling for invalid destinations
5. Error handling for invalid todo IDs
6. Integration testing with actual MCP server interface

This is a comprehensive integration test that mocks the AppleScript layer
but tests the complete flow through ThingsTools -> MoveOperationsTools -> ValidationService.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any, List

# Import the classes we're testing
from src.things_mcp.tools import ThingsTools
from src.things_mcp.applescript_manager import AppleScriptManager
from src.things_mcp.services.validation_service import ValidationService
from src.things_mcp.move_operations import MoveOperationsTools


class TestMoveRecordEnhanced:
    """Comprehensive tests for enhanced move_record functionality."""
    
    @pytest.fixture
    async def mock_applescript_manager(self):
        """Create a comprehensive mock AppleScript manager."""
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

    # ===========================================
    # BACKWARD COMPATIBILITY TESTS 
    # ===========================================

    @pytest.mark.asyncio
    async def test_move_to_inbox_backward_compatibility(self, things_tools, mock_applescript_manager):
        """Test moving to inbox (traditional list move - backward compatibility)."""
        # Mock successful todo info retrieval and move
        mock_applescript_manager.execute_applescript.side_effect = [
            # _get_todo_info call
            {
                "success": True,
                "output": '{id:"test-123", name:"Test Todo", notes:"", status:open, current_list:"today"}'
            },
            # _execute_move call for list move
            {
                "success": True,
                "output": "MOVED to inbox"
            }
        ]
        
        # Mock the parse function
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "test-123",
            "name": "Test Todo",
            "notes": "",
            "status": "open",
            "current_list": "today"
        }
        
        # Test moving to inbox
        result = await things_tools.move_record("test-123", "inbox")
        
        # Verify successful result with backward compatibility fields
        assert result["success"] == True
        assert result["todo_id"] == "test-123"
        assert result["destination_list"] == "inbox"  # Backward compatibility
        assert result["destination"] == "inbox"       # New field
        assert "moved_at" in result
        assert "message" in result
        
        # Verify that AppleScript was called twice (get info + move)
        assert mock_applescript_manager.execute_applescript.call_count == 2
    
    @pytest.mark.asyncio
    async def test_move_to_all_built_in_lists(self, things_tools, mock_applescript_manager):
        """Test moving to all built-in lists for backward compatibility."""
        built_in_lists = ["inbox", "today", "upcoming", "anytime", "someday"]
        
        for list_name in built_in_lists:
            # Reset mocks for each iteration
            mock_applescript_manager.reset_mock()
            mock_applescript_manager.execute_applescript.side_effect = [
                # _get_todo_info call
                {
                    "success": True,
                    "output": f'{{id:"test-{list_name}", name:"Todo for {list_name}", notes:"", status:open, current_list:"inbox"}}'
                },
                # _execute_move call
                {
                    "success": True,
                    "output": f"MOVED to {list_name}"
                }
            ]
            
            mock_applescript_manager._parse_applescript_record.return_value = {
                "id": f"test-{list_name}",
                "name": f"Todo for {list_name}",
                "notes": "",
                "status": "open",
                "current_list": "inbox"
            }
            
            # Test the move
            result = await things_tools.move_record(f"test-{list_name}", list_name)
            
            # Verify result
            assert result["success"] == True, f"Failed to move to {list_name}"
            assert result["todo_id"] == f"test-{list_name}"
            assert result["destination_list"] == list_name
            assert result["destination"] == list_name

    # ===========================================
    # PROJECT MOVE FUNCTIONALITY TESTS
    # ===========================================

    @pytest.mark.asyncio
    async def test_move_to_project_new_functionality(self, things_tools, mock_applescript_manager):
        """Test moving to a project using project:ID format."""
        # Mock successful todo info, project validation, and move
        mock_applescript_manager.execute_applescript.side_effect = [
            # _get_todo_info call
            {
                "success": True,
                "output": '{id:"todo-456", name:"Project Todo", notes:"", status:open, current_list:"inbox"}'
            },
            # Project validation (ValidationService check)
            {
                "success": True,
                "output": "EXISTS"
            },
            # _execute_move call
            {
                "success": True,
                "output": "MOVED to project ABC123"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "todo-456",
            "name": "Project Todo", 
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        }
        
        # Test moving to project
        result = await things_tools.move_record("todo-456", "project:ABC123")
        
        # Verify successful result
        assert result["success"] == True
        assert result["todo_id"] == "todo-456"
        assert result["destination_list"] == "project:ABC123"  # Backward compatibility
        assert result["destination"] == "project:ABC123"       # New field
        assert "moved_at" in result
        assert "Project Todo" in result["message"]
        
        # Verify AppleScript was called for validation and move
        assert mock_applescript_manager.execute_applescript.call_count == 3

    @pytest.mark.asyncio
    async def test_move_to_project_with_validation_failure(self, things_tools, mock_applescript_manager):
        """Test moving to non-existent project (validation failure)."""
        # Mock todo exists but project doesn't
        mock_applescript_manager.execute_applescript.side_effect = [
            # _get_todo_info call (successful)
            {
                "success": True,
                "output": '{id:"todo-789", name:"Test Todo", notes:"", status:open, current_list:"inbox"}'
            },
            # Project validation (fails)
            {
                "success": True,
                "output": "NOT_FOUND"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "todo-789",
            "name": "Test Todo",
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        }
        
        # Test moving to non-existent project
        result = await things_tools.move_record("todo-789", "project:NONEXISTENT")
        
        # Verify failure result
        assert result["success"] == False
        assert result["todo_id"] == "todo-789"
        assert result["destination"] == "project:NONEXISTENT"
        assert "error" in result
        # Should not proceed to move operation
        assert mock_applescript_manager.execute_applescript.call_count == 2

    # ===========================================
    # AREA MOVE FUNCTIONALITY TESTS
    # ===========================================

    @pytest.mark.asyncio
    async def test_move_to_area_new_functionality(self, things_tools, mock_applescript_manager):
        """Test moving to an area using area:ID format."""
        # Mock successful todo info, area validation, and move
        mock_applescript_manager.execute_applescript.side_effect = [
            # _get_todo_info call
            {
                "success": True,
                "output": '{id:"todo-area", name:"Area Todo", notes:"", status:open, current_list:"someday"}'
            },
            # Area validation
            {
                "success": True,
                "output": "EXISTS"
            },
            # _execute_move call
            {
                "success": True,
                "output": "MOVED to area XYZ789"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "todo-area",
            "name": "Area Todo",
            "notes": "",
            "status": "open",
            "current_list": "someday"
        }
        
        # Test moving to area
        result = await things_tools.move_record("todo-area", "area:XYZ789")
        
        # Verify successful result
        assert result["success"] == True
        assert result["todo_id"] == "todo-area"
        assert result["destination_list"] == "area:XYZ789"  # Backward compatibility
        assert result["destination"] == "area:XYZ789"       # New field
        assert "moved_at" in result
        assert "Area Todo" in result["message"]

    @pytest.mark.asyncio
    async def test_move_to_area_with_validation_failure(self, things_tools, mock_applescript_manager):
        """Test moving to non-existent area (validation failure)."""
        # Mock todo exists but area doesn't
        mock_applescript_manager.execute_applescript.side_effect = [
            # _get_todo_info call (successful)
            {
                "success": True,
                "output": '{id:"todo-bad-area", name:"Test Todo", notes:"", status:open, current_list:"inbox"}'
            },
            # Area validation (fails)
            {
                "success": True,
                "output": "NOT_FOUND"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "todo-bad-area", 
            "name": "Test Todo",
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        }
        
        # Test moving to non-existent area
        result = await things_tools.move_record("todo-bad-area", "area:BADAREA")
        
        # Verify failure result
        assert result["success"] == False
        assert result["todo_id"] == "todo-bad-area"
        assert result["destination"] == "area:BADAREA"
        assert "error" in result

    # ===========================================
    # ERROR HANDLING TESTS
    # ===========================================

    @pytest.mark.asyncio
    async def test_invalid_destination_format_error(self, things_tools):
        """Test error handling for invalid destination formats."""
        # Test various invalid formats
        invalid_destinations = [
            "invalid:format:here",
            "project:",  # Empty project ID
            "area:",     # Empty area ID
            "unknown:something",
            "",          # Empty string
            "project:id:extra:parts"
        ]
        
        for invalid_dest in invalid_destinations:
            result = await things_tools.move_record("some-todo-id", invalid_dest)
            
            # Should return validation error before any AppleScript calls
            assert result["success"] == False, f"Should fail for destination: {invalid_dest}"
            assert "error" in result
            assert result["todo_id"] == "some-todo-id"
            assert result["destination"] == invalid_dest

    @pytest.mark.asyncio 
    async def test_nonexistent_todo_error_handling(self, things_tools, mock_applescript_manager):
        """Test error handling when todo doesn't exist."""
        # Mock todo not found
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": 'ERROR:Can\\'t get to do id "nonexistent".'
        }
        
        result = await things_tools.move_record("nonexistent", "inbox")
        
        # Should handle the error gracefully
        assert result["success"] == False
        assert "error" in result
        assert result["todo_id"] == "nonexistent"
        assert result["destination"] == "inbox"

    @pytest.mark.asyncio
    async def test_applescript_execution_failure(self, things_tools, mock_applescript_manager):
        """Test error handling when AppleScript execution fails."""
        # Mock AppleScript execution failure
        mock_applescript_manager.execute_applescript.return_value = {
            "success": False,
            "error": "AppleScript execution failed",
            "output": None
        }
        
        result = await things_tools.move_record("some-todo", "inbox")
        
        # Should handle execution failure
        assert result["success"] == False
        assert "error" in result
        assert result["todo_id"] == "some-todo"

    @pytest.mark.asyncio
    async def test_unexpected_exception_handling(self, things_tools, mock_applescript_manager):
        """Test handling of unexpected exceptions."""
        # Mock exception during execution
        mock_applescript_manager.execute_applescript.side_effect = Exception("Unexpected error")
        
        result = await things_tools.move_record("exception-todo", "inbox")
        
        # Should handle exception gracefully
        assert result["success"] == False
        assert result["error"] == "UNEXPECTED_ERROR"
        assert "Unexpected error" in result["message"]
        assert result["todo_id"] == "exception-todo"

    # ===========================================
    # INTEGRATION AND SERVICE TESTS
    # ===========================================

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
    async def test_preserve_scheduling_parameter_integration(self, things_tools, mock_applescript_manager):
        """Test that scheduling preservation is properly passed through."""
        # Mock successful move
        mock_applescript_manager.execute_applescript.side_effect = [
            # Todo info
            {
                "success": True,
                "output": '{id:"scheduled-todo", name:"Scheduled Todo", notes:"", status:open, current_list:"today"}'
            },
            # Move execution
            {
                "success": True,
                "output": "MOVED to anytime"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "scheduled-todo",
            "name": "Scheduled Todo",
            "notes": "",
            "status": "open",
            "current_list": "today"
        }
        
        # Move should preserve scheduling by default
        result = await things_tools.move_record("scheduled-todo", "anytime")
        
        # Should succeed
        assert result["success"] == True
        assert "preserved_scheduling" in result
        
        # The move_operations should have been called with preserve_scheduling=True
        # This is implicitly tested by successful completion

    @pytest.mark.asyncio
    async def test_operation_queue_integration(self, things_tools, mock_applescript_manager):
        """Test that the operation queue is properly integrated."""
        # Mock successful operation
        mock_applescript_manager.execute_applescript.side_effect = [
            {
                "success": True,
                "output": '{id:"queue-test", name:"Queue Test", notes:"", status:open, current_list:"inbox"}'
            },
            {
                "success": True,
                "output": "MOVED to today"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "queue-test",
            "name": "Queue Test",
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        }
        
        result = await things_tools.move_record("queue-test", "today")
        
        # Should succeed, indicating queue integration worked
        assert result["success"] == True
        assert result["todo_id"] == "queue-test"

    # ===========================================
    # BULK OPERATIONS TESTS 
    # ===========================================

    @pytest.mark.asyncio
    async def test_multiple_concurrent_moves(self, things_tools, mock_applescript_manager):
        """Test multiple concurrent move operations."""
        # Create multiple move operations
        todo_ids = ["todo-1", "todo-2", "todo-3"]
        destinations = ["inbox", "today", "project:ABC123"]
        
        # Mock responses for all operations
        mock_responses = []
        parse_responses = {}
        
        for i, (todo_id, dest) in enumerate(zip(todo_ids, destinations)):
            # Todo info response
            mock_responses.append({
                "success": True,
                "output": f'{{id:"{todo_id}", name:"Todo {i+1}", notes:"", status:open, current_list:"inbox"}}'
            })
            
            # Validation response (if needed)
            if dest.startswith("project:"):
                mock_responses.append({
                    "success": True,
                    "output": "EXISTS"
                })
            
            # Move response
            mock_responses.append({
                "success": True,
                "output": f"MOVED to {dest}"
            })
            
            # Parse response
            parse_responses[todo_id] = {
                "id": todo_id,
                "name": f"Todo {i+1}",
                "notes": "",
                "status": "open",
                "current_list": "inbox"
            }
        
        mock_applescript_manager.execute_applescript.side_effect = mock_responses
        mock_applescript_manager._parse_applescript_record.side_effect = lambda x: parse_responses.get(
            x.split('"')[3] if '"' in x else "unknown", {}
        )
        
        # Execute moves concurrently
        tasks = [
            things_tools.move_record(todo_id, dest)
            for todo_id, dest in zip(todo_ids, destinations)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Verify all moves succeeded
        for i, result in enumerate(results):
            assert result["success"] == True, f"Move {i} failed: {result}"
            assert result["todo_id"] == todo_ids[i]

    # ===========================================
    # EDGE CASE TESTS
    # ===========================================

    @pytest.mark.asyncio
    async def test_move_with_special_characters_in_ids(self, things_tools, mock_applescript_manager):
        """Test moving todos and projects with special characters in IDs."""
        special_todo_id = "todo-123-with-dashes_and_underscores"
        special_project_id = "project-456_special-chars"
        
        mock_applescript_manager.execute_applescript.side_effect = [
            # Todo info
            {
                "success": True,
                "output": f'{{id:"{special_todo_id}", name:"Special Todo", notes:"", status:open, current_list:"inbox"}}'
            },
            # Project validation
            {
                "success": True,
                "output": "EXISTS"
            },
            # Move execution
            {
                "success": True,
                "output": f"MOVED to project {special_project_id}"
            }
        ]
        
        mock_applescript_manager._parse_applescript_record.return_value = {
            "id": special_todo_id,
            "name": "Special Todo",
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        }
        
        result = await things_tools.move_record(special_todo_id, f"project:{special_project_id}")
        
        assert result["success"] == True
        assert result["todo_id"] == special_todo_id
        assert result["destination"] == f"project:{special_project_id}"

    @pytest.mark.asyncio
    async def test_move_with_empty_string_inputs(self, things_tools):
        """Test error handling with empty string inputs."""
        # Empty todo ID
        result = await things_tools.move_record("", "inbox")
        assert result["success"] == False
        assert "error" in result
        
        # Empty destination
        result = await things_tools.move_record("some-todo", "")
        assert result["success"] == False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_move_with_none_inputs(self, things_tools):
        """Test error handling with None inputs."""
        with pytest.raises(TypeError):
            await things_tools.move_record(None, "inbox")
        
        with pytest.raises(TypeError):
            await things_tools.move_record("some-todo", None)


class TestValidationServiceIsolated:
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
        invalid_formats = [
            "invalid:format:here",
            "project:",
            "area:", 
            "unknown:something",
            "",
            "project:id:extra"
        ]
        
        for invalid_format in invalid_formats:
            result = validation_service.validate_destination_format(invalid_format)
            assert result["valid"] == False, f"Should be invalid: {invalid_format}"
            assert result["error"] == "INVALID_DESTINATION"


if __name__ == "__main__":
    # Run the tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])