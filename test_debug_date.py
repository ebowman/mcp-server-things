#!/usr/bin/env python3
"""Debug the date scheduling to see what AppleScript is being generated."""

import asyncio
import sys
import os
from datetime import date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def debug_date():
    """Debug what AppleScript is being generated."""
    
    target_date = date(2025, 7, 1)
    
    # Map numeric months to AppleScript month constants
    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    month_constant = month_names[target_date.month]
    
    # This is what our code generates
    script = f'''
    tell application "Things3"
        try
            set theTodo to to do id "TEST_ID"
            
            -- Construct date object safely to avoid month overflow bug
            set targetDate to (current date)
            set time of targetDate to 0  -- Reset time first
            set day of targetDate to 1   -- Set to safe day first to avoid overflow
            set year of targetDate to {target_date.year}
            set month of targetDate to {month_constant}  -- Use month constant, not numeric
            set day of targetDate to {target_date.day}   -- Set actual day last
            
            -- Schedule using the constructed date object
            schedule theTodo for targetDate
            return "scheduled_objects"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    
    print("Generated AppleScript:")
    print("=" * 50)
    print(script)
    print("=" * 50)
    print(f"\nThe month line is: set month of targetDate to {month_constant}")
    print(f"This outputs: set month of targetDate to July")
    print(f"AppleScript needs: set month of targetDate to July (without quotes)")
    print("\nThe f-string is working correctly - July is output without quotes.")
    print("The issue must be something else...")

if __name__ == "__main__":
    asyncio.run(debug_date())