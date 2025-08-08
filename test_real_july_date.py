#!/usr/bin/env python3
"""Test July 1, 2025 with numeric month and safe ordering."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.applescript_manager import AppleScriptManager

async def test_real_july():
    """Test with the exact approach our code uses."""
    
    print("Testing July 1, 2025 with numeric month and safe ordering...")
    print("=" * 50)
    
    manager = AppleScriptManager()
    
    # Test with exact pattern from our code
    script = '''
    tell application "Things3"
        -- Create test todo
        set newTodo to make new to do with properties {name:"July 2025 Safe Order Test", notes:"Testing safe date construction"}
        set todoId to id of newTodo
        
        -- Construct date with safe ordering (as in our fix)
        set targetDate to (current date)
        set time of targetDate to 0  -- Reset time first
        set day of targetDate to 1   -- Set to safe day first to avoid overflow
        set year of targetDate to 2025
        set month of targetDate to 7  -- Numeric month
        set day of targetDate to 1   -- Set actual day last
        
        -- Schedule the todo
        schedule newTodo for targetDate
        
        -- Get the actual scheduled date
        set actualDate to scheduled date of newTodo
        if actualDate is not missing value then
            set yearStr to year of actualDate as string
            set monthStr to month of actualDate as integer as string
            set dayStr to day of actualDate as string
            return todoId & "|" & yearStr & "-" & monthStr & "-" & dayStr
        else
            return todoId & "|NO_DATE"
        end if
    end tell
    '''
    
    result = await manager.execute_applescript(script)
    if result.get("success"):
        output = result.get("output", "").strip()
        parts = output.split("|")
        if len(parts) >= 2:
            todo_id = parts[0]
            actual_date = parts[1]
            print(f"Created todo: {todo_id}")
            print(f"Expected: 2025-7-1")
            print(f"Actual:   {actual_date}")
            
            if "2025-7-1" in actual_date:
                print("✅ SUCCESS! Safe ordering with numeric month works!")
            elif "2036" in actual_date:
                print("❌ BUG! Even with safe ordering, date is wrong!")
                
                # Let's debug what's happening
                print("\nDebugging: Getting current date info...")
                debug_script = '''
                set currentDate to (current date)
                set yearStr to year of currentDate as string
                set monthStr to month of currentDate as integer as string
                set dayStr to day of currentDate as string
                return "Current: " & yearStr & "-" & monthStr & "-" & dayStr
                '''
                debug_result = await manager.execute_applescript(debug_script)
                if debug_result.get("success"):
                    print(f"   {debug_result.get('output', '').strip()}")
            else:
                print(f"⚠️ Unexpected date: {actual_date}")
            
            # Clean up
            cleanup_script = f'''
            tell application "Things3"
                set theTodo to to do id "{todo_id}"
                move theTodo to list "Trash"
                return "cleaned"
            end tell
            '''
            await manager.execute_applescript(cleanup_script)
            print("\nCleaned up test todo")
    else:
        print(f"Failed: {result.get('error')}")
    
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_real_july())