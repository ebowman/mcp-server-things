#!/usr/bin/env python3
"""Test different July syntax options."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.applescript_manager import AppleScriptManager

async def test_july_syntax():
    """Test different ways to set July."""
    
    print("Testing different July syntax options...")
    print("=" * 50)
    
    manager = AppleScriptManager()
    
    # Test 1: Try with "of"
    print("\n1. Testing: set month of targetDate to July of targetDate")
    script1 = '''
    set targetDate to (current date)
    set month of targetDate to July of targetDate
    return (month of targetDate as string)
    '''
    
    result = await manager.execute_applescript(script1)
    if result.get("success"):
        print(f"   Result: {result.get('output')}")
    else:
        print(f"   Failed: {result.get('error')}")
    
    # Test 2: Try with numeric 7
    print("\n2. Testing: set month of targetDate to 7")
    script2 = '''
    set targetDate to (current date)
    set month of targetDate to 7
    return (month of targetDate as string)
    '''
    
    result = await manager.execute_applescript(script2)
    if result.get("success"):
        print(f"   Result: {result.get('output')}")
    else:
        print(f"   Failed: {result.get('error')}")
    
    # Test 3: Try constructing date differently
    print("\n3. Testing: date string construction")
    script3 = '''
    set targetDate to date "July 1, 2025"
    return (year of targetDate as string) & "-" & (month of targetDate as integer as string) & "-" & (day of targetDate as string)
    '''
    
    result = await manager.execute_applescript(script3)
    if result.get("success"):
        print(f"   Result: {result.get('output')}")
    else:
        print(f"   Failed: {result.get('error')}")
    
    # Test 4: Try with 'month' constant from current date
    print("\n4. Testing: Getting July from a known July date")
    script4 = '''
    set julyDate to date "July 1, 2025"
    set targetDate to (current date)
    set month of targetDate to (month of julyDate)
    return (year of targetDate as string) & "-" & (month of targetDate as integer as string) & "-" & (day of targetDate as string)
    '''
    
    result = await manager.execute_applescript(script4)
    if result.get("success"):
        print(f"   Result: {result.get('output')}")
    else:
        print(f"   Failed: {result.get('error')}")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    asyncio.run(test_july_syntax())