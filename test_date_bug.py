#!/usr/bin/env python3
"""Test and fix the date scheduling bug."""

import asyncio
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.applescript_manager import AppleScriptManager

async def test_date_bug():
    """Reproduce and test the date bug."""
    
    print("Testing date scheduling bug...")
    print("=" * 50)
    
    manager = AppleScriptManager()
    
    # Test the problematic date
    test_date = datetime(2025, 9, 15)
    
    # 1. First, reproduce the bug with numeric month
    print("\n1. Testing BUGGY version (numeric month)...")
    buggy_script = f'''
    tell application "Things3"
        -- Create a test todo
        set newTodo to make new to do with properties {{name:"Date Bug Test (Buggy)", notes:"Testing date: 2025-09-15"}}
        set todoId to id of newTodo
        
        -- Buggy date construction (using numeric month)
        set targetDate to (current date)
        set year of targetDate to {test_date.year}
        set month of targetDate to {test_date.month}  -- BUG: numeric 9
        set day of targetDate to {test_date.day}
        set time of targetDate to 0
        
        -- Schedule the todo
        schedule newTodo for targetDate
        
        -- Return the actual scheduled date
        set actualDate to scheduled date of newTodo
        if actualDate is not missing value then
            set dateStr to (year of actualDate as string) & "-" & ¬
                          (month of actualDate as integer as string) & "-" & ¬
                          (day of actualDate as string)
            return "BUGGY|" & todoId & "|" & dateStr
        else
            return "BUGGY|" & todoId & "|NO_DATE"
        end if
    end tell
    '''
    
    result = await manager.execute_applescript(buggy_script)
    if result.get("success"):
        output = result.get("output", "").strip()
        parts = output.split("|")
        if len(parts) >= 3:
            todo_id = parts[1]
            actual_date = parts[2]
            print(f"   Created todo: {todo_id}")
            print(f"   Expected: 2025-09-15")
            print(f"   Actual:   {actual_date}")
            if "2036" in actual_date:
                print(f"   ❌ BUG REPRODUCED! Date is off by ~11 years!")
            
    # 2. Test the FIXED version with month constant
    print("\n2. Testing FIXED version (month constant)...")
    
    # Map numeric months to AppleScript constants
    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    month_constant = month_names[test_date.month]
    
    fixed_script = f'''
    tell application "Things3"
        -- Create a test todo
        set newTodo to make new to do with properties {{name:"Date Bug Test (Fixed)", notes:"Testing date: 2025-09-15"}}
        set todoId to id of newTodo
        
        -- FIXED date construction (using month constant)
        set targetDate to (current date)
        set time of targetDate to 0  -- Reset time first
        set day of targetDate to 1   -- Set to safe day first
        set year of targetDate to {test_date.year}
        set month of targetDate to {month_constant}  -- FIX: Use constant
        set day of targetDate to {test_date.day}
        
        -- Schedule the todo
        schedule newTodo for targetDate
        
        -- Return the actual scheduled date
        set actualDate to scheduled date of newTodo
        if actualDate is not missing value then
            set dateStr to (year of actualDate as string) & "-" & ¬
                          (month of actualDate as integer as string) & "-" & ¬
                          (day of actualDate as string)
            return "FIXED|" & todoId & "|" & dateStr
        else
            return "FIXED|" & todoId & "|NO_DATE"
        end if
    end tell
    '''
    
    result = await manager.execute_applescript(fixed_script)
    if result.get("success"):
        output = result.get("output", "").strip()
        parts = output.split("|")
        if len(parts) >= 3:
            todo_id = parts[1]
            actual_date = parts[2]
            print(f"   Created todo: {todo_id}")
            print(f"   Expected: 2025-09-15")
            print(f"   Actual:   {actual_date}")
            if "2025-9-15" in actual_date:
                print(f"   ✅ FIX WORKS! Date is correct!")
    
    # 3. Clean up test todos
    print("\n3. Cleaning up test todos...")
    cleanup_script = '''
    tell application "Things3"
        set testTodos to to dos whose name starts with "Date Bug Test"
        repeat with aTodo in testTodos
            move aTodo to list "Trash"
        end repeat
        return "cleaned"
    end tell
    '''
    
    await manager.execute_applescript(cleanup_script)
    print("   ✅ Test todos cleaned up")
    
    print("\n" + "=" * 50)
    print("DIAGNOSIS COMPLETE:")
    print("- BUG: Using numeric month value causes date overflow")
    print("- FIX: Use AppleScript month constants (January, February, etc.)")
    print("- ADDITIONAL: Set day to 1 first to avoid month overflow issues")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(test_date_bug())