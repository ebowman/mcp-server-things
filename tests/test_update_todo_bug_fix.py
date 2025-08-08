#!/usr/bin/env python3
"""Test that the update_todo bug with undefined project_id is fixed."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from things_mcp.simple_server import ThingsMCPServer

async def test_update_todo_completion():
    """Test that updating a todo's completion status works without error."""
    server = ThingsMCPServer()
    
    print("Testing update_todo with completion status...")
    
    # First, create a test todo
    print("1. Creating test todo...")
    result = await server.tools.add_todo(
        title="Test Todo for Update Bug Fix",
        notes="This todo will be marked as completed"
    )
    
    if not result.get("success"):
        print(f"❌ Failed to create test todo: {result}")
        return False
    
    todo_id = result["todo"]["id"]
    print(f"✅ Created todo with ID: {todo_id}")
    
    # Now update it to mark as completed
    print("\n2. Updating todo to mark as completed...")
    try:
        update_result = await server.tools.update_todo(
            todo_id=todo_id,
            completed=True
        )
        
        if update_result.get("success"):
            print(f"✅ Successfully marked todo as completed!")
            print(f"   Message: {update_result.get('message')}")
            return True
        else:
            print(f"❌ Failed to update todo: {update_result}")
            return False
            
    except Exception as e:
        print(f"❌ Error updating todo: {e}")
        return False

async def main():
    """Run the test."""
    print("=" * 60)
    print("Testing update_todo bug fix (undefined project_id)")
    print("=" * 60)
    
    success = await test_update_todo_completion()
    
    print("\n" + "=" * 60)
    if success:
        print("✅ BUG FIX VERIFIED: update_todo works without project_id error!")
    else:
        print("❌ TEST FAILED: There may still be an issue")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())