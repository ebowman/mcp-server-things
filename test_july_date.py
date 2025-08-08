#!/usr/bin/env python3
"""Test July 1, 2025 date scheduling specifically."""

import asyncio
import sys
import os
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.applescript_manager import AppleScriptManager

async def test_july_date():
    """Test the exact date that's failing."""
    
    print("Testing July 1, 2025 date scheduling...")
    print("=" * 50)
    
    manager = AppleScriptManager()
    
    # Create a test todo and schedule it for July 1, 2025
    script = '''
    tell application "Things3"
        -- Create test todo
        set newTodo to make new to do with properties {name:"July 1 2025 Test", notes:"Testing date scheduling"}
        set todoId to id of newTodo
        
        -- Construct date for July 1, 2025
        set targetDate to (current date)
        set time of targetDate to 0
        set day of targetDate to 1
        set year of targetDate to 2025
        set month of targetDate to July
        set day of targetDate to 1
        
        -- Schedule the todo
        schedule newTodo for targetDate
        
        -- Get the actual scheduled date
        set actualDate to scheduled date of newTodo
        if actualDate is not missing value then
            set dateStr to (year of actualDate as string) & "-" & ¬
                          (month of actualDate as integer as string) & "-" & ¬
                          (day of actualDate as string)
            return todoId & "|" & dateStr
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
            print(f"Expected date: 2025-07-01")
            print(f"Actual date:   {actual_date}")
            
            if "2025-7-1" in actual_date:
                print("✅ SUCCESS! Date is correct!")
            elif "2036" in actual_date:
                print("❌ BUG STILL PRESENT! Date is off by 11 years!")
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
        print(f"Failed to execute: {result.get('error')}")
    
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_july_date())