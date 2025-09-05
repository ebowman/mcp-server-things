#!/usr/bin/env python3
"""Debug AppleScript for date queries."""

import subprocess
import asyncio

# Simple test AppleScript to check date filtering
test_script = '''
tell application "Things3"
    set nowDate to (current date)
    set cutoffDate to nowDate + (30 * days)
    
    -- Count todos with due dates
    set allTodos to to dos whose status is open
    set dueCount to 0
    set activationCount to 0
    
    repeat with t in allTodos
        try
            set d to due date of t
            if d is not missing value then
                set dueCount to dueCount + 1
            end if
        end try
        
        try
            set a to activation date of t
            if a is not missing value then
                set activationCount to activationCount + 1
            end if
        end try
    end repeat
    
    return "Total open todos: " & (count of allTodos) & ¬
        ", With due dates: " & dueCount & ¬
        ", With activation dates: " & activationCount
end tell
'''

async def test_applescript():
    """Run test AppleScript."""
    try:
        result = subprocess.run(
            ['osascript', '-e', test_script],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("Success:", result.stdout)
        else:
            print("Error:", result.stderr)
            
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == "__main__":
    asyncio.run(test_applescript())