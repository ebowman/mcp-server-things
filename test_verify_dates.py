#!/usr/bin/env python3
"""Verify the dates directly in Things 3."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.applescript_manager import AppleScriptManager

async def verify_dates():
    """Create a todo and check its dates directly."""
    
    print("Creating and verifying todo dates directly...")
    print("=" * 50)
    
    manager = AppleScriptManager()
    
    # Create a todo with both when and deadline
    script = '''
    tell application "Things3"
        -- Create the todo with basic properties
        set newTodo to make new to do with properties {name:"Date Fix Verification", notes:"Testing final fix"}
        set todoId to id of newTodo
        
        -- Schedule for July 1, 2025
        set scheduleDate to (current date)
        set time of scheduleDate to 0
        set day of scheduleDate to 1
        set year of scheduleDate to 2025
        set month of scheduleDate to 7
        set day of scheduleDate to 1
        
        schedule newTodo for scheduleDate
        
        -- Set deadline for September 30, 2025
        set dueDate to (current date)
        set time of dueDate to 0
        set day of dueDate to 1
        set year of dueDate to 2025
        set month of dueDate to 9
        set day of dueDate to 30
        
        set due date of newTodo to dueDate
        
        -- Now get the actual dates
        set actualScheduled to activation date of newTodo
        set actualDue to due date of newTodo
        
        set resultStr to todoId & "|"
        
        if actualScheduled is not missing value then
            set resultStr to resultStr & (year of actualScheduled as string) & "-"
            set resultStr to resultStr & (month of actualScheduled as integer as string) & "-"
            set resultStr to resultStr & (day of actualScheduled as string)
        else
            set resultStr to resultStr & "NO_SCHEDULE"
        end if
        
        set resultStr to resultStr & "|"
        
        if actualDue is not missing value then
            set resultStr to resultStr & (year of actualDue as string) & "-"
            set resultStr to resultStr & (month of actualDue as integer as string) & "-"
            set resultStr to resultStr & (day of actualDue as string)
        else
            set resultStr to resultStr & "NO_DEADLINE"
        end if
        
        return resultStr
    end tell
    '''
    
    result = await manager.execute_applescript(script)
    if result.get("success"):
        output = result.get("output", "").strip()
        parts = output.split("|")
        
        if len(parts) >= 3:
            todo_id = parts[0]
            scheduled = parts[1]
            deadline = parts[2]
            
            print(f"Todo ID: {todo_id}")
            print(f"Scheduled date: {scheduled}")
            print(f"Due date: {deadline}")
            
            # Check results
            print("\nVerification:")
            if "2025-7-1" in scheduled:
                print("✅ Scheduled date is CORRECT (July 1, 2025)")
            else:
                print(f"❌ Scheduled date is WRONG: {scheduled}")
            
            if "2025-9-30" in deadline:
                print("✅ Due date is CORRECT (September 30, 2025)")
            elif "2036" in deadline:
                print(f"❌ BUG STILL EXISTS! Due date shows as: {deadline}")
            else:
                print(f"⚠️ Unexpected due date: {deadline}")
            
            # Clean up
            cleanup_script = f'''
            tell application "Things3"
                set theTodo to to do id "{todo_id}"
                move theTodo to list "Trash"
                return "cleaned"
            end tell
            '''
            await manager.execute_applescript(cleanup_script)
            print("\nTest todo cleaned up")
    else:
        print(f"Failed: {result.get('error')}")
    
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(verify_dates())