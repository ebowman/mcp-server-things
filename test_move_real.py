#!/usr/bin/env python3
"""Test the actual move_record functionality with a real Things 3 operation."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.simple_server import ThingsMCPServer
from things_mcp.tools import ThingsTools
from things_mcp.applescript_manager import AppleScriptManager

async def test_real_move():
    """Test if move_record actually works with project moves."""
    
    print("Testing move_record with real Things 3...")
    print("=" * 50)
    
    # Initialize the tools directly
    applescript_manager = AppleScriptManager()
    tools = ThingsTools(applescript_manager)
    
    # First, create a test todo in the inbox
    print("\n1. Creating test todo in inbox...")
    todo_result = await tools.add_todo(
        title="Test Move to Project",
        notes="This todo will be moved to a project"
    )
    
    if not todo_result.get("success"):
        print(f"❌ Failed to create todo: {todo_result.get('error')}")
        return False
    
    # The todo_id is nested in the todo object
    todo_data = todo_result.get("todo", {})
    todo_id = todo_data.get("id") or todo_data.get("uuid")
    print(f"✅ Created todo with ID: {todo_id}")
    
    # Get list of projects to find a valid project ID
    print("\n2. Getting list of projects...")
    projects = await tools.get_projects()
    
    if not projects:
        print("⚠️ No projects found. Creating a test project...")
        project_result = await tools.add_project(
            title="Test Project for Move Operation",
            notes="Created for testing move_record functionality"
        )
        if project_result.get("success"):
            project_id = project_result.get("project_id")
            print(f"✅ Created test project with ID: {project_id}")
        else:
            print(f"❌ Failed to create project: {project_result.get('error')}")
            return False
    else:
        project_id = projects[0].get("id")
        project_title = projects[0].get("title")
        print(f"✅ Found existing project: '{project_title}' (ID: {project_id})")
    
    # Test moving to project
    print(f"\n3. Testing move to project...")
    destination = f"project:{project_id}"
    print(f"   Destination: {destination}")
    
    try:
        move_result = await tools.move_record(
            todo_id=todo_id,
            destination_list=destination
        )
        
        if move_result.get("success"):
            print(f"✅ Successfully moved todo to project!")
            print(f"   Result: {move_result}")
        else:
            print(f"❌ Failed to move todo to project")
            print(f"   Error: {move_result.get('error')}")
            print(f"   Message: {move_result.get('message')}")
            return False
            
    except Exception as e:
        print(f"❌ Exception during move: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Verify the todo is now in the project
    print(f"\n4. Verifying todo is in project...")
    verification_result = await tools.get_todo_by_id(todo_id)
    
    if verification_result:
        # Check if project_id is in the todo's data
        todo_project = verification_result.get("project_id") or verification_result.get("project")
        if todo_project:
            print(f"✅ Confirmed: Todo is now in project (project info: {todo_project})")
        else:
            print(f"⚠️ Todo retrieved but project info not clear in response")
            print(f"   Todo data: {verification_result}")
    
    # Test moving back to inbox
    print(f"\n5. Testing move back to inbox...")
    inbox_result = await tools.move_record(
        todo_id=todo_id,
        destination_list="inbox"
    )
    
    if inbox_result.get("success"):
        print(f"✅ Successfully moved todo back to inbox!")
    else:
        print(f"⚠️ Failed to move back to inbox: {inbox_result.get('error')}")
    
    # Clean up - delete the test todo
    print(f"\n6. Cleaning up...")
    delete_result = await tools.delete_todo(todo_id)
    if delete_result.get("success"):
        print(f"✅ Cleaned up test todo")
    else:
        print(f"⚠️ Failed to clean up: {delete_result.get('error')}")
    
    print("\n" + "=" * 50)
    print("✅ TEST SUCCESSFUL: move_record DOES support project moves!")
    print(f"   Use format: 'project:PROJECT_ID'")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_real_move())
    sys.exit(0 if success else 1)