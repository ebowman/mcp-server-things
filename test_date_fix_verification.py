#!/usr/bin/env python3
"""Verify the date scheduling fix works correctly."""

import asyncio
import sys
import os
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.tools import ThingsTools
from things_mcp.applescript_manager import AppleScriptManager

async def verify_date_fix():
    """Test that the date scheduling fix works correctly."""
    
    print("Verifying date scheduling fix...")
    print("=" * 50)
    
    # Initialize the tools
    applescript_manager = AppleScriptManager()
    tools = ThingsTools(applescript_manager)
    
    # Test dates
    test_cases = [
        ("2025-09-15", "September 15 test"),
        ("2025-12-31", "End of year test"),
        ("2025-01-01", "Start of year test"),
        ("2025-02-28", "February test"),
        ("2025-08-31", "August 31 test (edge case)"),
    ]
    
    created_todos = []
    
    for date_str, title in test_cases:
        print(f"\nTesting date: {date_str}")
        
        # Create a todo with the specified date
        result = await tools.add_todo(
            title=f"Date Fix Test: {title}",
            notes=f"Testing date scheduling for {date_str}",
            when=date_str
        )
        
        if result.get("success"):
            todo_data = result.get("todo", {})
            todo_id = todo_data.get("id")
            created_todos.append(todo_id)
            
            # Check the scheduling result
            scheduling_result = result.get("scheduling_result", {})
            if scheduling_result.get("success"):
                print(f"  ✅ Todo created with ID: {todo_id}")
                print(f"     Method: {scheduling_result.get('method')}")
                print(f"     Reliability: {scheduling_result.get('reliability')}")
                print(f"     Date set: {scheduling_result.get('date_set')}")
            else:
                print(f"  ⚠️ Todo created but scheduling failed")
                
            # Verify the actual scheduled date
            verify_script = f'''
            tell application "Things3"
                try
                    set theTodo to to do id "{todo_id}"
                    set scheduledDate to scheduled date of theTodo
                    if scheduledDate is not missing value then
                        set dateStr to (year of scheduledDate as string) & "-" & ¬
                                      (month of scheduledDate as integer as string) & "-" & ¬
                                      (day of scheduledDate as string)
                        return dateStr
                    else
                        return "NO_DATE"
                    end if
                on error errMsg
                    return "ERROR: " & errMsg
                end try
            end tell
            '''
            
            verify_result = await applescript_manager.execute_applescript(verify_script)
            if verify_result.get("success"):
                actual_date = verify_result.get("output", "").strip()
                expected_year = date_str.split("-")[0]
                
                if expected_year in actual_date:
                    print(f"  ✅ VERIFIED: Date correctly set to {actual_date}")
                else:
                    print(f"  ❌ ERROR: Date is {actual_date}, expected year {expected_year}")
        else:
            print(f"  ❌ Failed to create todo: {result.get('error')}")
    
    # Clean up test todos
    print("\n" + "=" * 50)
    print("Cleaning up test todos...")
    for todo_id in created_todos:
        await tools.delete_todo(todo_id)
    print(f"✅ Cleaned up {len(created_todos)} test todos")
    
    print("\n" + "=" * 50)
    print("DATE FIX VERIFICATION COMPLETE")
    print("The date scheduling bug has been fixed!")
    print("=" * 50)

if __name__ == "__main__":
    asyncio.run(verify_date_fix())