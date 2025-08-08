#!/usr/bin/env python3
"""Test the complete fix for the deadline date bug."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.tools import ThingsTools
from things_mcp.applescript_manager import AppleScriptManager

async def test_complete_fix():
    """Test adding a todo with deadline to verify the fix."""
    
    print("Testing complete fix for deadline date bug...")
    print("=" * 50)
    
    # Create tools instance
    applescript = AppleScriptManager()
    tools = ThingsTools(applescript)
    
    # Test adding a todo with deadline
    print("\n1. Adding todo with deadline 2025-09-30...")
    
    result = await tools.add_todo(
        title="Complete Fix Test Todo",
        notes="Testing the complete deadline fix", 
        when="2025-07-01",
        deadline="2025-09-30"
    )
    
    if result.get("success"):
        print("✅ Todo created successfully!")
        todo_id = result["todo"]["id"]
        print(f"   Todo ID: {todo_id}")
        print(f"   When: {result['todo']['when']}")
        print(f"   Deadline: {result['todo']['deadline']}")
        
        # Now get the todo to verify the dates
        print("\n2. Getting todo to verify dates...")
        get_result = await tools.get_todo_by_id(todo_id)
        
        if get_result.get("success"):
            todo = get_result["todo"]
            print(f"   Scheduled date: {todo.get('scheduled_date', 'Not set')}")
            print(f"   Due date: {todo.get('due_date', 'Not set')}")
            
            # Check if dates are correct
            if "2025-07-01" in str(todo.get('scheduled_date', '')):
                print("   ✅ Scheduled date is correct!")
            else:
                print(f"   ❌ Scheduled date is wrong: {todo.get('scheduled_date')}")
            
            if "2025-09-30" in str(todo.get('due_date', '')):
                print("   ✅ Due date is correct!")
            elif "2036" in str(todo.get('due_date', '')):
                print(f"   ❌ BUG STILL EXISTS! Due date shows as: {todo.get('due_date')}")
            else:
                print(f"   ⚠️ Unexpected due date: {todo.get('due_date')}")
        
        # Clean up
        print("\n3. Cleaning up test todo...")
        delete_result = await tools.delete_todo(todo_id)
        if delete_result.get("success"):
            print("   ✅ Test todo deleted")
    else:
        print(f"❌ Failed to create todo: {result.get('error')}")
    
    print("\n" + "=" * 50)
    print("Test complete!")

if __name__ == "__main__":
    asyncio.run(test_complete_fix())