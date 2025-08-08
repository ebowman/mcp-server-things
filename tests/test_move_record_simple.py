#!/usr/bin/env python3
"""
Simple focused tests for the enhanced move_record functionality.

This version focuses on testing the core move_record logic without 
complex async setup or operation queues. It directly tests the
MoveOperationsTools and ValidationService classes.
"""

import sys
import os
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# Add the src directory to the Python path
project_root = Path(__file__).parent.parent
src_path = project_root / "src"
sys.path.insert(0, str(src_path))

# Import the modules we're testing
try:
    from things_mcp.applescript_manager import AppleScriptManager
    from things_mcp.services.validation_service import ValidationService
    from things_mcp.move_operations import MoveOperationsTools
    print("✅ Successfully imported required modules")
except ImportError as e:
    print(f"❌ Failed to import required modules: {e}")
    sys.exit(1)


async def test_validation_service_basic():
    """Test basic ValidationService functionality."""
    print("\n🧪 Testing ValidationService basic functionality")
    
    # Create mock AppleScript manager
    mock_applescript = Mock(spec=AppleScriptManager)
    mock_applescript.execute_applescript = AsyncMock()
    
    # Create ValidationService
    validation_service = ValidationService(mock_applescript)
    
    # Test 1: Valid project destination format
    result = validation_service.validate_destination_format("project:ABC123")
    assert result["valid"] == True
    assert result["type"] == "project"
    assert result["id"] == "ABC123"
    print("✅ Project destination format validation passed")
    
    # Test 2: Valid area destination format
    result = validation_service.validate_destination_format("area:XYZ789")
    assert result["valid"] == True
    assert result["type"] == "area"
    assert result["id"] == "XYZ789"
    print("✅ Area destination format validation passed")
    
    # Test 3: Valid list destination format
    result = validation_service.validate_destination_format("inbox")
    assert result["valid"] == True
    assert result["type"] == "list"
    assert result["name"] == "inbox"
    print("✅ List destination format validation passed")
    
    # Test 4: Invalid destination format
    result = validation_service.validate_destination_format("invalid:format:here")
    assert result["valid"] == False
    assert result["error"] == "INVALID_DESTINATION"
    print("✅ Invalid destination format validation passed")
    
    # Test 5: Empty project ID
    result = validation_service.validate_destination_format("project:")
    assert result["valid"] == False
    assert result["error"] == "EMPTY_PROJECT_ID"
    print("✅ Empty project ID validation passed")
    
    # Test 6: Empty area ID
    result = validation_service.validate_destination_format("area:")
    assert result["valid"] == False
    assert result["error"] == "EMPTY_AREA_ID"
    print("✅ Empty area ID validation passed")


async def test_move_operations_basic():
    """Test basic MoveOperationsTools functionality."""
    print("\n🧪 Testing MoveOperationsTools basic functionality")
    
    # Create mock AppleScript manager
    mock_applescript = Mock(spec=AppleScriptManager)
    mock_applescript.execute_applescript = AsyncMock()
    mock_applescript._parse_applescript_record = Mock()
    
    # Create ValidationService
    validation_service = ValidationService(mock_applescript)
    
    # Create MoveOperationsTools
    move_ops = MoveOperationsTools(mock_applescript, validation_service)
    
    # Test 1: Move to inbox (backward compatibility)
    print("  Testing move to inbox (backward compatibility)")
    
    # Mock successful todo info and move
    mock_applescript.execute_applescript.side_effect = [
        # Todo info
        {
            "success": True,
            "output": '{id:"test-123", name:"Test Todo", notes:"", status:open, current_list:"today"}'
        },
        # Move operation
        {
            "success": True,
            "output": "MOVED to inbox"
        }
    ]
    
    mock_applescript._parse_applescript_record.return_value = {
        "id": "test-123",
        "name": "Test Todo",
        "notes": "",
        "status": "open",
        "current_list": "today"
    }
    
    result = await move_ops.move_record("test-123", "inbox")
    
    assert result["success"] == True
    assert result["todo_id"] == "test-123"
    assert result["destination"] == "inbox"
    print("✅ Move to inbox test passed")
    
    # Test 2: Move to project (new functionality)
    print("  Testing move to project (new functionality)")
    
    # Reset mock
    mock_applescript.reset_mock()
    mock_applescript.execute_applescript.side_effect = [
        # Todo info
        {
            "success": True,
            "output": '{id:"todo-456", name:"Project Todo", notes:"", status:open, current_list:"inbox"}'
        },
        # Project validation (skipped in simple test)
        # Move operation
        {
            "success": True,
            "output": "MOVED to project ABC123"
        }
    ]
    
    mock_applescript._parse_applescript_record.return_value = {
        "id": "todo-456",
        "name": "Project Todo",
        "notes": "",
        "status": "open",
        "current_list": "inbox"
    }
    
    result = await move_ops.move_record("todo-456", "project:ABC123")
    
    assert result["success"] == True
    assert result["todo_id"] == "todo-456"
    assert result["destination"] == "project:ABC123"
    print("✅ Move to project test passed")
    
    # Test 3: Move to area (new functionality)
    print("  Testing move to area (new functionality)")
    
    # Reset mock
    mock_applescript.reset_mock()
    mock_applescript.execute_applescript.side_effect = [
        # Todo info
        {
            "success": True,
            "output": '{id:"todo-789", name:"Area Todo", notes:"", status:open, current_list:"someday"}'
        },
        # Move operation
        {
            "success": True,
            "output": "MOVED to area XYZ789"
        }
    ]
    
    mock_applescript._parse_applescript_record.return_value = {
        "id": "todo-789",
        "name": "Area Todo",
        "notes": "",
        "status": "open",
        "current_list": "someday"
    }
    
    result = await move_ops.move_record("todo-789", "area:XYZ789")
    
    assert result["success"] == True
    assert result["todo_id"] == "todo-789"
    assert result["destination"] == "area:XYZ789"
    print("✅ Move to area test passed")


async def test_error_handling():
    """Test error handling scenarios."""
    print("\n🧪 Testing error handling scenarios")
    
    # Create mock AppleScript manager
    mock_applescript = Mock(spec=AppleScriptManager)
    mock_applescript.execute_applescript = AsyncMock()
    mock_applescript._parse_applescript_record = Mock()
    
    # Create ValidationService
    validation_service = ValidationService(mock_applescript)
    
    # Create MoveOperationsTools
    move_ops = MoveOperationsTools(mock_applescript, validation_service)
    
    # Test 1: Invalid destination format
    result = await move_ops.move_record("some-todo", "invalid:format:here")
    assert result["success"] == False
    assert "error" in result
    print("✅ Invalid destination format error handling passed")
    
    # Test 2: Todo not found
    mock_applescript.execute_applescript.return_value = {
        "success": True,
        "output": 'ERROR:Can\'t get to do id "nonexistent".'
    }
    
    result = await move_ops.move_record("nonexistent", "inbox")
    assert result["success"] == False
    assert "error" in result
    print("✅ Todo not found error handling passed")
    
    # Test 3: AppleScript execution failure
    mock_applescript.execute_applescript.return_value = {
        "success": False,
        "error": "AppleScript execution failed"
    }
    
    result = await move_ops.move_record("some-todo", "inbox")
    assert result["success"] == False
    assert "error" in result
    print("✅ AppleScript execution failure error handling passed")


async def test_all_built_in_lists():
    """Test moving to all built-in lists."""
    print("\n🧪 Testing moves to all built-in lists")
    
    built_in_lists = ["inbox", "today", "upcoming", "anytime", "someday"]
    
    # Create mock AppleScript manager
    mock_applescript = Mock(spec=AppleScriptManager)
    mock_applescript.execute_applescript = AsyncMock()
    mock_applescript._parse_applescript_record = Mock()
    
    # Create ValidationService
    validation_service = ValidationService(mock_applescript)
    
    # Create MoveOperationsTools
    move_ops = MoveOperationsTools(mock_applescript, validation_service)
    
    for list_name in built_in_lists:
        print(f"  Testing move to {list_name}")
        
        # Reset mock
        mock_applescript.reset_mock()
        mock_applescript.execute_applescript.side_effect = [
            # Todo info
            {
                "success": True,
                "output": f'{{id:"test-{list_name}", name:"Todo for {list_name}", notes:"", status:open, current_list:"inbox"}}'
            },
            # Move operation
            {
                "success": True,
                "output": f"MOVED to {list_name}"
            }
        ]
        
        mock_applescript._parse_applescript_record.return_value = {
            "id": f"test-{list_name}",
            "name": f"Todo for {list_name}",
            "notes": "",
            "status": "open",
            "current_list": "inbox"
        }
        
        result = await move_ops.move_record(f"test-{list_name}", list_name)
        
        assert result["success"] == True, f"Failed to move to {list_name}"
        assert result["todo_id"] == f"test-{list_name}"
        assert result["destination"] == list_name
    
    print("✅ All built-in list moves passed")


async def main():
    """Run all tests."""
    print("🧪 Simple Enhanced Move Record Functionality Tests")
    print("=" * 60)
    print()
    print("This simplified test suite verifies:")
    print("✅ ValidationService destination format parsing")
    print("✅ MoveOperationsTools basic move operations")
    print("✅ Backward compatibility with built-in lists")
    print("✅ New project and area move functionality")
    print("✅ Error handling for various failure scenarios")
    print()
    print("-" * 60)
    
    try:
        # Run all test functions
        await test_validation_service_basic()
        await test_move_operations_basic()
        await test_error_handling()
        await test_all_built_in_lists()
        
        print()
        print("-" * 60)
        print("🎉 All enhanced move_record functionality tests passed!")
        print()
        print("The following functionality has been verified:")
        print("  • ValidationService properly parses destination formats")
        print("  • MoveOperationsTools handles built-in list moves")
        print("  • MoveOperationsTools handles project moves (project:ID)")
        print("  • MoveOperationsTools handles area moves (area:ID)")
        print("  • Error handling for invalid destinations and missing todos")
        print("  • Error handling for AppleScript execution failures")
        print("  • All built-in lists (inbox, today, upcoming, anytime, someday)")
        print()
        print("✅ The enhanced move_record functionality is working correctly!")
        return 0
        
    except Exception as e:
        print()
        print("-" * 60)
        print(f"❌ Test failed with error: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)