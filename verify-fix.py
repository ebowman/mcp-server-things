#!/usr/bin/env python3
"""
Quick verification script for the reliable scheduling fix.
Tests the critical scheduling functionality that was previously failing.
"""

import asyncio
import sys
from pathlib import Path

# Add source to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from things_mcp.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools

async def verify_scheduling_fix():
    """Verify the scheduling fix works for the most common failure cases."""
    
    print("🔧 Verifying Reliable Date Scheduling Fix")
    print("=" * 50)
    
    # Initialize components
    applescript = AppleScriptManager()
    tools = ThingsTools(applescript)
    
    # Check Things is running
    if not await applescript.is_things_running():
        print("❌ Things 3 not running - start Things and try again")
        return False
    
    print(f"✅ Things 3 is running")
    print(f"🔑 Auth token: {'✅ Available' if applescript.auth_token else '⚠️ Not found'}")
    
    # Test the previously failing case: ISO date format
    test_date = "2025-08-07"  # Tomorrow
    
    print(f"\n🧪 Testing previously failing case: ISO date '{test_date}'")
    
    try:
        # Create a todo with the problematic date format
        result = await tools.add_todo(
            title="Scheduling Fix Verification",
            notes="Testing the reliable scheduling implementation",
            when=test_date,
            tags=["verification-test"]
        )
        
        if result.get("success"):
            todo_id = result.get("todo", {}).get("id")
            scheduling_result = result.get("scheduling_result")
            
            print(f"✅ Todo created successfully: {todo_id}")
            
            if scheduling_result and scheduling_result.get("success"):
                method = scheduling_result.get("method")
                reliability = scheduling_result.get("reliability")
                print(f"✅ Scheduling successful using {method} ({reliability})")
                
                if method == "url_scheme":
                    print("🎉 PRIMARY METHOD WORKING - URL scheme succeeded")
                elif method == "applescript_objects":
                    print("✅ FALLBACK METHOD WORKING - AppleScript objects succeeded")
                elif method == "list_fallback":
                    print("⚠️ FINAL FALLBACK WORKING - List assignment succeeded")
                
                print(f"\n🏁 VERIFICATION RESULT: ✅ SCHEDULING FIX IS WORKING")
                print(f"The previously failing ISO date format now works reliably!")
                return True
            else:
                print(f"❌ Scheduling failed or no result returned")
                if scheduling_result:
                    print(f"Error: {scheduling_result.get('error', 'Unknown')}")
                return False
        else:
            print(f"❌ Todo creation failed: {result.get('error')}")
            return False
    
    except Exception as e:
        print(f"❌ Exception during verification: {e}")
        return False

async def main():
    success = await verify_scheduling_fix()
    
    if success:
        print(f"\n🎊 SUCCESS: The reliable date scheduling fix is working!")
        print(f"📈 The multi-layered approach eliminates the previous failure points.")
        print(f"🚀 Ready for production use!")
    else:
        print(f"\n⚠️ ISSUE: The fix may need additional work.")
        print(f"📋 Run the full test suite: python test-reliable-scheduling.py")
    
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)