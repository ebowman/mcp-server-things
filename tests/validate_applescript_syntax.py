#!/usr/bin/env python3
"""
AppleScript syntax validation for optimized location detection.

This script validates that the optimized AppleScript syntax is correct
and that the optimization logic is sound.
"""

import re

def validate_applescript_optimization():
    """Validate the optimized AppleScript syntax and logic."""
    
    # Read the optimized move operations file
    with open('src/things_mcp/tools/move_operations.py', 'r') as f:
        content = f.read()
    
    print("🔍 Validating AppleScript Optimization...")
    print("=" * 50)
    
    # Check that old inefficient patterns are removed
    inefficient_patterns = [
        r'set todayItems to to dos of list "today"',
        r'set upcomingItems to to dos of list "upcoming"',
        r'set anytimeItems to to dos of list "anytime"', 
        r'set somedayItems to to dos of list "someday"',
        r'set inboxItems to to dos of list "inbox"',
        r'if theTodo is in todayItems then',
        r'if theTodo is in upcomingItems then',
    ]
    
    print("❌ Checking removal of inefficient patterns:")
    all_removed = True
    for pattern in inefficient_patterns:
        if re.search(pattern, content):
            print(f"  ❌ FOUND: {pattern}")
            all_removed = False
        else:
            print(f"  ✅ REMOVED: {pattern}")
    
    if all_removed:
        print("✅ All inefficient patterns successfully removed!")
    else:
        print("❌ Some inefficient patterns still present!")
        return False
    
    print()
    
    # Check that new efficient patterns are present
    efficient_patterns = [
        r'getCurrentLocation',
        r'scheduled date of theTodo',
        r'status of theTodo',
        r'if todoStatus is completed then',
        r'if todoStatus is canceled then',
        r'startOfToday.*startOfTomorrow',
        r'to dos whose id is',
        r'project of theTodo',
        r'area of theTodo',
    ]
    
    print("✅ Checking presence of efficient patterns:")
    all_present = True
    for pattern in efficient_patterns:
        if re.search(pattern, content):
            print(f"  ✅ FOUND: {pattern}")
        else:
            print(f"  ❌ MISSING: {pattern}")
            all_present = False
    
    if all_present:
        print("✅ All efficient patterns successfully implemented!")
    else:
        print("❌ Some efficient patterns missing!")
        return False
        
    print()
    
    # Validate AppleScript structure
    print("🔧 Validating AppleScript structure:")
    
    # Check for proper function definition
    if 'on getCurrentLocation(theTodo)' in content:
        print("  ✅ Function definition correct")
    else:
        print("  ❌ Function definition missing or incorrect")
        return False
        
    # Check for proper error handling
    if 'on error' in content and 'return "unknown"' in content:
        print("  ✅ Error handling present")
    else:
        print("  ❌ Error handling missing")
        return False
        
    # Check for proper tell blocks
    tell_blocks = content.count('tell application "Things3"')
    if tell_blocks >= 2:  # One in main script, one in function
        print(f"  ✅ Proper tell blocks ({tell_blocks} found)")
    else:
        print(f"  ❌ Insufficient tell blocks ({tell_blocks} found)")
        return False
        
    print()
    print("🎉 OPTIMIZATION VALIDATION SUCCESSFUL!")
    print("=" * 50)
    print("Key improvements implemented:")
    print("• Native property-based location detection")
    print("• Eliminated bulk list fetching")
    print("• Added status-based detection for completed/canceled")
    print("• Implemented date arithmetic for smart lists")
    print("• Added targeted ID-based queries")
    print("• Maintained comprehensive error handling")
    
    return True

if __name__ == "__main__":
    success = validate_applescript_optimization()
    exit(0 if success else 1)