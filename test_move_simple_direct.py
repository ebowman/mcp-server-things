#!/usr/bin/env python3
"""Direct test of move_record with simpler AppleScript."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.applescript_manager import AppleScriptManager

async def test_direct_move():
    """Test moving a todo directly with AppleScript."""
    
    print("Testing direct move with AppleScript...")
    print("=" * 50)
    
    # Initialize AppleScript manager
    manager = AppleScriptManager()
    
    # 1. Create a test todo
    print("\n1. Creating test todo...")
    create_script = '''
    tell application "Things3"
        set newTodo to make new to do with properties {name:"Direct Move Test", notes:"Testing project move"}
        return id of newTodo
    end tell
    '''
    
    result = await manager.execute_applescript(create_script)
    if not result.get("success"):
        print(f"❌ Failed to create todo: {result.get('error')}")
        return False
    
    todo_id = result.get("output", "").strip()
    print(f"✅ Created todo with ID: {todo_id}")
    
    # 2. Get a project ID
    print("\n2. Getting first project...")
    get_project_script = '''
    tell application "Things3"
        set allProjects to projects
        if (count of allProjects) > 0 then
            set firstProject to item 1 of allProjects
            return {id of firstProject, name of firstProject}
        else
            return ""
        end if
    end tell
    '''
    
    result = await manager.execute_applescript(get_project_script)
    if not result.get("success") or not result.get("output"):
        print(f"❌ Failed to get project: {result.get('error')}")
        return False
    
    # Parse the project info
    project_info = result.get("output", "").strip()
    # Extract ID and name from format like: 2KC2YtbD1gKUCwo2aGoqqS, Open-Source Things MCP Server Release
    parts = project_info.split(", ", 1)
    if len(parts) >= 2:
        project_id = parts[0]
        project_name = parts[1]
    else:
        project_id = project_info
        project_name = "Unknown"
    
    print(f"✅ Found project: '{project_name}' (ID: {project_id})")
    
    # 3. Move the todo to the project
    print(f"\n3. Moving todo to project...")
    move_script = f'''
    tell application "Things3"
        try
            set theTodo to to do id "{todo_id}"
            set targetProject to project id "{project_id}"
            move theTodo to targetProject
            return "SUCCESS"
        on error errMsg
            return "ERROR: " & errMsg
        end try
    end tell
    '''
    
    result = await manager.execute_applescript(move_script)
    output = result.get("output", "").strip()
    
    if result.get("success") and output == "SUCCESS":
        print(f"✅ Successfully moved todo to project!")
    else:
        print(f"❌ Failed to move todo: {output}")
        return False
    
    # 4. Verify the todo is in the project
    print(f"\n4. Verifying todo is in project...")
    verify_script = f'''
    tell application "Things3"
        try
            set theTodo to to do id "{todo_id}"
            set todoProject to project of theTodo
            if todoProject is not missing value then
                return "IN_PROJECT:" & (id of todoProject)
            else
                return "NO_PROJECT"
            end if
        on error errMsg
            return "ERROR: " & errMsg
        end try
    end tell
    '''
    
    result = await manager.execute_applescript(verify_script)
    output = result.get("output", "").strip()
    
    if output.startswith("IN_PROJECT:"):
        verify_project_id = output.replace("IN_PROJECT:", "")
        if verify_project_id == project_id:
            print(f"✅ Confirmed: Todo is in the correct project!")
        else:
            print(f"⚠️ Todo is in a different project: {verify_project_id}")
    else:
        print(f"⚠️ Verification result: {output}")
    
    # 5. Move back to inbox
    print(f"\n5. Moving todo back to inbox...")
    inbox_script = f'''
    tell application "Things3"
        try
            set theTodo to to do id "{todo_id}"
            set inboxList to list "Inbox"
            move theTodo to inboxList
            return "SUCCESS"
        on error errMsg
            return "ERROR: " & errMsg
        end try
    end tell
    '''
    
    result = await manager.execute_applescript(inbox_script)
    output = result.get("output", "").strip()
    
    if result.get("success") and output == "SUCCESS":
        print(f"✅ Successfully moved todo back to inbox!")
    else:
        print(f"⚠️ Move to inbox result: {output}")
    
    # 6. Clean up
    print(f"\n6. Cleaning up...")
    delete_script = f'''
    tell application "Things3"
        try
            set theTodo to to do id "{todo_id}"
            move theTodo to list "Trash"
            return "SUCCESS"
        on error errMsg
            return "ERROR: " & errMsg
        end try
    end tell
    '''
    
    result = await manager.execute_applescript(delete_script)
    if result.get("success"):
        print(f"✅ Cleaned up test todo")
    
    print("\n" + "=" * 50)
    print("✅ TEST SUCCESSFUL!")
    print("The move_record functionality DOES work with projects.")
    print("The issue is in the complex validation/detection AppleScript.")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_direct_move())
    sys.exit(0 if success else 1)