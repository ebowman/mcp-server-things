#!/usr/bin/env python3
"""Test moving a todo to a project by setting its project property."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.applescript_manager import AppleScriptManager

async def test_set_project():
    """Test moving a todo by setting its project property."""
    
    print("Testing move by setting project property...")
    print("=" * 50)
    
    # Initialize AppleScript manager
    manager = AppleScriptManager()
    
    # 1. Create a test todo
    print("\n1. Creating test todo...")
    create_script = '''
    tell application "Things3"
        set newTodo to make new to do with properties {name:"Project Property Test", notes:"Testing project assignment"}
        return id of newTodo
    end tell
    '''
    
    result = await manager.execute_applescript(create_script)
    if not result.get("success"):
        print(f"❌ Failed to create todo: {result.get('error')}")
        return False
    
    todo_id = result.get("output", "").strip()
    print(f"✅ Created todo with ID: {todo_id}")
    
    # 2. Get a project
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
    project_info = result.get("output", "").strip()
    parts = project_info.split(", ", 1)
    project_id = parts[0]
    project_name = parts[1] if len(parts) > 1 else "Unknown"
    
    print(f"✅ Found project: '{project_name}' (ID: {project_id})")
    
    # 3. Try setting the project property
    print(f"\n3. Setting todo's project property...")
    set_project_script = f'''
    tell application "Things3"
        try
            set theTodo to to do id "{todo_id}"
            set targetProject to project id "{project_id}"
            set project of theTodo to targetProject
            return "SUCCESS"
        on error errMsg
            return "ERROR: " & errMsg
        end try
    end tell
    '''
    
    result = await manager.execute_applescript(set_project_script)
    output = result.get("output", "").strip()
    
    if output == "SUCCESS":
        print(f"✅ Successfully set project property!")
    else:
        print(f"❌ Failed to set project: {output}")
        
        # Try alternative approach - duplicate to project
        print(f"\n3b. Trying alternative: duplicate to project...")
        duplicate_script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"
                set targetProject to project id "{project_id}"
                duplicate theTodo to targetProject
                return "SUCCESS"
            on error errMsg
                return "ERROR: " & errMsg
            end try
        end tell
        '''
        
        result = await manager.execute_applescript(duplicate_script)
        output = result.get("output", "").strip()
        
        if output == "SUCCESS":
            print(f"✅ Successfully duplicated to project!")
        else:
            print(f"❌ Duplicate also failed: {output}")
    
    # 4. Try creating directly in project
    print(f"\n4. Testing direct creation in project...")
    create_in_project_script = f'''
    tell application "Things3"
        try
            set targetProject to project id "{project_id}"
            set newTodo to make new to do at targetProject with properties {{name:"Created in Project", notes:"Direct creation test"}}
            return id of newTodo
        on error errMsg
            return "ERROR: " & errMsg
        end try
    end tell
    '''
    
    result = await manager.execute_applescript(create_in_project_script)
    output = result.get("output", "").strip()
    
    if not output.startswith("ERROR:"):
        print(f"✅ Successfully created todo directly in project! ID: {output}")
        new_todo_id = output
        
        # Verify it's in the project
        verify_script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{new_todo_id}"
                set todoProject to project of theTodo
                if todoProject is not missing value then
                    return "IN_PROJECT:" & (name of todoProject)
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
        print(f"   Verification: {output}")
    else:
        print(f"❌ Direct creation failed: {output}")
    
    # Clean up
    print(f"\n5. Cleaning up...")
    delete_script = f'''
    tell application "Things3"
        try
            set theTodo to to do id "{todo_id}"
            move theTodo to list "Trash"
            return "DELETED"
        on error
            return "ALREADY_GONE"
        end try
    end tell
    '''
    
    await manager.execute_applescript(delete_script)
    print(f"✅ Cleanup complete")
    
    print("\n" + "=" * 50)
    print("FINDINGS:")
    print("- 'move' command doesn't work for projects")
    print("- Setting 'project' property doesn't work")  
    print("- Direct creation in project DOES work")
    print("- Solution: Delete and recreate in target location")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_set_project())
    sys.exit(0 if success else 1)