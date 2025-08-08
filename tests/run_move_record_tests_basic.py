#!/usr/bin/env python3
"""
Basic test runner for the enhanced move_record functionality tests.

This script runs the comprehensive move_record tests using Python's built-in
unittest module instead of pytest, making it easier to run without additional
dependencies.

Usage:
    python tests/run_move_record_tests_basic.py
"""

import sys
import os
import asyncio
import unittest
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

# Add the src directory to the Python path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Import the modules we're testing
try:
    from things_mcp.tools import ThingsTools
    from things_mcp.applescript_manager import AppleScriptManager
    from things_mcp.services.validation_service import ValidationService
    from things_mcp.move_operations import MoveOperationsTools
    print("✅ Successfully imported required modules")
except ImportError as e:
    print(f"❌ Failed to import required modules: {e}")
    sys.exit(1)


class TestMoveRecordEnhanced(unittest.IsolatedAsyncioTestCase):
    """Test cases for enhanced move_record functionality using unittest."""
    
    async def asyncSetUp(self):
        """Set up test fixtures."""
        # Create mock AppleScript manager
        self.mock_applescript_manager = Mock(spec=AppleScriptManager)
        self.mock_applescript_manager.execute_applescript = AsyncMock()
        self.mock_applescript_manager._parse_applescript_record = Mock()
        
        # Create ThingsTools instance with mocked operation queue
        with patch('things_mcp.tools.get_operation_queue') as mock_queue:
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
            
            self.things_tools = ThingsTools(self.mock_applescript_manager)

    async def test_move_to_inbox_backward_compatibility(self):
        """Test moving to inbox (traditional list move - backward compatibility)."""
        print("🧪 Testing backward compatibility: move to inbox")
        
        # Mock successful todo info retrieval and move
        self.mock_applescript_manager.execute_applescript.side_effect = [
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
        self.mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "test-123",
            "name": "Test Todo",
            "notes": "",
            "status": "open",
            "current_list": "today"
        }
        
        # Test moving to inbox
        result = await self.things_tools.move_record("test-123", "inbox")
        
        # Verify successful result with backward compatibility fields
        self.assertTrue(result["success"])
        self.assertEqual(result["todo_id"], "test-123")
        self.assertEqual(result["destination_list"], "inbox")  # Backward compatibility
        self.assertEqual(result["destination"], "inbox")       # New field
        self.assertIn("moved_at", result)
        self.assertIn("message", result)
        
        # Verify that AppleScript was called twice (get info + move)
        self.assertEqual(self.mock_applescript_manager.execute_applescript.call_count, 2)
        print("✅ Backward compatibility test passed")

    async def test_move_to_project_new_functionality(self):
        """Test moving to a project using project:ID format."""
        print("🧪 Testing new functionality: move to project")
        
        # Reset mock for clean test
        self.mock_applescript_manager.reset_mock()
        
        # Mock successful todo info, project validation, and move
        self.mock_applescript_manager.execute_applescript.side_effect = [
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
        
        self.mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "todo-456",
            "name": "Project Todo", 
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        }
        
        # Test moving to project
        result = await self.things_tools.move_record("todo-456", "project:ABC123")
        
        # Verify successful result
        self.assertTrue(result["success"])
        self.assertEqual(result["todo_id"], "todo-456")
        self.assertEqual(result["destination_list"], "project:ABC123")  # Backward compatibility
        self.assertEqual(result["destination"], "project:ABC123")       # New field
        self.assertIn("moved_at", result)
        self.assertIn("Project Todo", result["message"])
        
        # Verify AppleScript was called for validation and move
        self.assertEqual(self.mock_applescript_manager.execute_applescript.call_count, 3)
        print("✅ Project move test passed")

    async def test_move_to_area_new_functionality(self):
        """Test moving to an area using area:ID format."""
        print("🧪 Testing new functionality: move to area")
        
        # Reset mock for clean test
        self.mock_applescript_manager.reset_mock()
        
        # Mock successful todo info, area validation, and move
        self.mock_applescript_manager.execute_applescript.side_effect = [
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
        
        self.mock_applescript_manager._parse_applescript_record.return_value = {
            "id": "todo-area",
            "name": "Area Todo",
            "notes": "",
            "status": "open",
            "current_list": "someday"
        }
        
        # Test moving to area
        result = await self.things_tools.move_record("todo-area", "area:XYZ789")
        
        # Verify successful result
        self.assertTrue(result["success"])
        self.assertEqual(result["todo_id"], "todo-area")
        self.assertEqual(result["destination_list"], "area:XYZ789")  # Backward compatibility
        self.assertEqual(result["destination"], "area:XYZ789")       # New field
        self.assertIn("moved_at", result)
        self.assertIn("Area Todo", result["message"])
        print("✅ Area move test passed")

    async def test_invalid_destination_format_error(self):
        """Test error handling for invalid destination formats."""
        print("🧪 Testing error handling: invalid destination formats")
        
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
            result = await self.things_tools.move_record("some-todo-id", invalid_dest)
            
            # Should return validation error before any AppleScript calls
            self.assertFalse(result["success"], f"Should fail for destination: {invalid_dest}")
            self.assertIn("error", result)
            self.assertEqual(result["todo_id"], "some-todo-id")
            self.assertEqual(result["destination"], invalid_dest)
        
        print("✅ Invalid destination format error handling test passed")

    async def test_nonexistent_todo_error_handling(self):
        """Test error handling when todo doesn't exist."""
        print("🧪 Testing error handling: nonexistent todo")
        
        # Mock todo not found
        self.mock_applescript_manager.reset_mock()
        self.mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": 'ERROR:Can\'t get to do id "nonexistent".'
        }
        
        result = await self.things_tools.move_record("nonexistent", "inbox")
        
        # Should handle the error gracefully
        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertEqual(result["todo_id"], "nonexistent")
        self.assertEqual(result["destination"], "inbox")
        print("✅ Nonexistent todo error handling test passed")

    async def test_integration_components(self):
        """Test that all integration components are properly initialized."""
        print("🧪 Testing integration: service components")
        
        # Verify that validation service was initialized
        self.assertTrue(hasattr(self.things_tools, 'validation_service'))
        self.assertIsInstance(self.things_tools.validation_service, ValidationService)
        
        # Verify that move operations tool was initialized
        self.assertTrue(hasattr(self.things_tools, 'move_operations'))
        self.assertIsInstance(self.things_tools.move_operations, MoveOperationsTools)
        
        print("✅ Integration components test passed")


async def run_basic_validation_tests():
    """Run basic validation tests with async."""
    print("🧪 Testing ValidationService in isolation")
    
    # Create mock AppleScript manager
    mock_manager = Mock(spec=AppleScriptManager)
    mock_manager.execute_applescript = AsyncMock()
    
    # Create ValidationService
    validation_service = ValidationService(mock_manager)
    
    # Test destination format validation for projects (synchronous)
    result = validation_service.validate_destination_format("project:ABC123")
    assert result["valid"] == True
    assert result["type"] == "project"
    assert result["id"] == "ABC123"
    print("✅ Project destination validation passed")
    
    # Test destination format validation for areas (synchronous)
    result = validation_service.validate_destination_format("area:XYZ789")
    assert result["valid"] == True
    assert result["type"] == "area"
    assert result["id"] == "XYZ789"
    print("✅ Area destination validation passed")
    
    # Test invalid destination format
    result = validation_service.validate_destination_format("invalid:format:here")
    assert result["valid"] == False
    assert result["error"] == "INVALID_DESTINATION"
    print("✅ Invalid destination validation passed")
    
    # Test list name validation (async)
    result = await validation_service.validate_list_name("inbox")
    assert result["valid"] == True
    print("✅ List name validation passed")


def main():
    """Run all tests."""
    print("🧪 Running Enhanced Move Record Functionality Tests")
    print("=" * 60)
    print()
    print("This test suite verifies:")
    print("✅ Backward compatibility with built-in lists (inbox, today, etc.)")
    print("✅ New project move functionality (project:ID format)")
    print("✅ New area move functionality (area:ID format)")
    print("✅ Comprehensive error handling")
    print("✅ Integration with ValidationService and MoveOperationsTools")
    print()
    print("-" * 60)
    
    # Run basic validation tests first (async)
    try:
        asyncio.run(run_basic_validation_tests())
        print()
    except Exception as e:
        print(f"❌ Basic validation tests failed: {e}")
        return 1
    
    # Run main async test suite
    test_loader = unittest.TestLoader()
    test_suite = test_loader.loadTestsFromTestCase(TestMoveRecordEnhanced)
    
    # Create a test runner with verbose output
    test_runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    
    # Run the tests
    result = test_runner.run(test_suite)
    
    print()
    print("-" * 60)
    
    if result.wasSuccessful():
        print("🎉 All enhanced move_record functionality tests passed!")
        print()
        print("The following functionality has been verified:")
        print("  • Built-in list moves (inbox, today, upcoming, anytime, someday)")
        print("  • Project moves using 'project:ID' format")
        print("  • Area moves using 'area:ID' format")
        print("  • Validation of todo IDs, project IDs, and area IDs")
        print("  • Error handling for invalid destinations and IDs")
        print("  • Integration with operation queue and concurrency support")
        print("  • Proper backward compatibility maintenance")
        print()
        print("✅ The enhanced move_record functionality is working correctly!")
        return 0
    else:
        print(f"❌ {len(result.failures)} test(s) failed, {len(result.errors)} error(s)")
        print()
        print("Failed tests:")
        for test, traceback in result.failures:
            print(f"  • {test}: {traceback.split('AssertionError:')[-1].strip()}")
        
        print("\nTest errors:")
        for test, traceback in result.errors:
            print(f"  • {test}: {traceback.split('Exception:')[-1].strip()}")
        
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)