#!/usr/bin/env python3
"""Debug month setting syntax."""

import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.applescript_manager import AppleScriptManager

async def test_month():
    """Test different month setting approaches."""
    
    print("Testing month setting approaches...")
    print("=" * 50)
    
    manager = AppleScriptManager()
    
    # Test 1: Direct numeric month
    print("\n1. Testing numeric month (7 for July)...")
    script1 = '''
    set testDate to (current date)
    set month of testDate to 7
    return (month of testDate as integer as string)
    '''
    
    result = await manager.execute_applescript(script1)
    if result.get("success"):
        print(f"   Success! Month is: {result.get('output', '').strip()}")
    else:
        print(f"   Failed: {result.get('error')}")
    
    # Test 2: Month as word
    print("\n2. Testing month as word (July)...")
    script2 = '''
    set testDate to (current date)
    set month of testDate to July
    return (month of testDate as integer as string)
    '''
    
    result = await manager.execute_applescript(script2)
    if result.get("success"):
        print(f"   Success! Month is: {result.get('output', '').strip()}")
    else:
        print(f"   Failed: {result.get('error')}")
    
    # Test 3: Month from another date
    print("\n3. Testing month from date string...")
    script3 = '''
    set sourceDate to date "July 1, 2025"
    set testDate to (current date)
    set month of testDate to (month of sourceDate)
    return (month of testDate as integer as string)
    '''
    
    result = await manager.execute_applescript(script3)
    if result.get("success"):
        print(f"   Success! Month is: {result.get('output', '').strip()}")
    else:
        print(f"   Failed: {result.get('error')}")
    
    # Test 4: Exact sequence from our code
    print("\n4. Testing exact sequence from our code...")
    script4 = '''
    set testDate to (current date)
    set time of testDate to 0
    set day of testDate to 1
    set year of testDate to 2025
    set month of testDate to 7
    set day of testDate to 1
    return (year of testDate as string) & "-" & (month of testDate as integer as string) & "-" & (day of testDate as string)
    '''
    
    result = await manager.execute_applescript(script4)
    if result.get("success"):
        print(f"   Success! Date is: {result.get('output', '').strip()}")
    else:
        print(f"   Failed: {result.get('error')}")
    
    print("\n" + "=" * 50)

if __name__ == "__main__":
    asyncio.run(test_month())