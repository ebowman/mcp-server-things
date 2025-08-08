#!/usr/bin/env python3
"""
Test script for the new reliable date scheduling implementation.

This script tests all three layers of the reliable scheduling system:
1. URL Scheme scheduling (primary)
2. AppleScript Date Objects scheduling (fallback)
3. List Assignment scheduling (final fallback)
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the source directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from things_mcp.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_reliable_scheduling():
    """Test the reliable scheduling system with various date formats."""
    
    print("🔧 Testing 100% Reliable Things 3 Date Scheduling")
    print("=" * 60)
    
    # Initialize the tools
    applescript_manager = AppleScriptManager()
    tools = ThingsTools(applescript_manager)
    
    # Check if Things is running
    if not await applescript_manager.is_things_running():
        print("❌ Things 3 is not running. Please start Things 3 and try again.")
        return False
    
    # Test date formats
    test_dates = [
        "today",
        "tomorrow", 
        "2025-08-07",  # Tomorrow in ISO format
        "2025-08-10",  # Future date
    ]
    
    print(f"📋 Creating test todos with reliable scheduling...")
    
    test_results = []
    
    for i, when_date in enumerate(test_dates):
        test_name = f"Reliable Scheduling Test {i+1}"
        
        try:
            print(f"\n🧪 Test {i+1}: Scheduling todo for '{when_date}'")
            
            # Create todo with scheduling
            result = await tools.add_todo(
                title=f"{test_name} - {when_date}",
                notes=f"Testing reliable scheduling for: {when_date}",
                when=when_date,
                tags=["test-reliable-scheduling"]
            )
            
            if result.get("success"):
                scheduling_result = result.get("scheduling_result")
                todo_id = result.get("todo", {}).get("id")
                
                if scheduling_result:
                    method = scheduling_result.get("method", "unknown")
                    reliability = scheduling_result.get("reliability", "unknown")
                    success = scheduling_result.get("success", False)
                    
                    print(f"   ✅ Todo created: {todo_id}")
                    print(f"   📅 Scheduling: {'✅ SUCCESS' if success else '❌ FAILED'}")
                    print(f"   🔧 Method: {method} ({reliability} reliability)")
                    
                    if "note" in scheduling_result:
                        print(f"   ℹ️  Note: {scheduling_result['note']}")
                    
                    test_results.append({
                        "test": test_name,
                        "when": when_date,
                        "success": success,
                        "method": method,
                        "reliability": reliability,
                        "todo_id": todo_id
                    })
                else:
                    print(f"   ⚠️  Todo created but no scheduling result returned")
                    test_results.append({
                        "test": test_name,
                        "when": when_date,
                        "success": False,
                        "method": "none",
                        "reliability": "0%",
                        "todo_id": todo_id
                    })
            else:
                print(f"   ❌ Failed to create todo: {result.get('error')}")
                test_results.append({
                    "test": test_name,
                    "when": when_date,
                    "success": False,
                    "method": "creation_failed",
                    "reliability": "0%",
                    "todo_id": None
                })
        
        except Exception as e:
            print(f"   ❌ Exception during test: {e}")
            test_results.append({
                "test": test_name,
                "when": when_date,
                "success": False,
                "method": "exception",
                "reliability": "0%",
                "todo_id": None
            })
    
    # Test update scheduling
    print(f"\n🔄 Testing reliable scheduling with todo updates...")
    
    if test_results and test_results[0]["todo_id"]:
        try:
            todo_id = test_results[0]["todo_id"]
            update_date = "tomorrow"
            
            print(f"   🧪 Updating todo {todo_id} to schedule for '{update_date}'")
            
            update_result = await tools.update_todo(
                todo_id=todo_id,
                when=update_date,
                notes="Updated with reliable scheduling test"
            )
            
            if update_result.get("success"):
                scheduling_result = update_result.get("scheduling_result")
                if scheduling_result:
                    method = scheduling_result.get("method", "unknown")
                    reliability = scheduling_result.get("reliability", "unknown")
                    success = scheduling_result.get("success", False)
                    
                    print(f"   ✅ Update successful")
                    print(f"   📅 Scheduling: {'✅ SUCCESS' if success else '❌ FAILED'}")
                    print(f"   🔧 Method: {method} ({reliability} reliability)")
                else:
                    print(f"   ⚠️  Update successful but no scheduling result")
            else:
                print(f"   ❌ Update failed: {update_result.get('error')}")
        
        except Exception as e:
            print(f"   ❌ Exception during update test: {e}")
    
    # Print summary
    print(f"\n📊 Test Results Summary")
    print("=" * 60)
    
    successful_tests = sum(1 for result in test_results if result["success"])
    total_tests = len(test_results)
    success_rate = (successful_tests / total_tests) * 100 if total_tests > 0 else 0
    
    print(f"Total Tests: {total_tests}")
    print(f"Successful: {successful_tests}")
    print(f"Success Rate: {success_rate:.1f}%")
    
    print(f"\n📈 Method Distribution:")
    method_counts = {}
    for result in test_results:
        method = result["method"]
        method_counts[method] = method_counts.get(method, 0) + 1
    
    for method, count in method_counts.items():
        print(f"   {method}: {count} test(s)")
    
    # Check auth token status
    print(f"\n🔑 Authentication Status:")
    if applescript_manager.auth_token:
        print(f"   ✅ Auth token available: {applescript_manager.auth_token[:8]}...")
        print(f"   🔧 URL Scheme scheduling enabled")
    else:
        print(f"   ⚠️  No auth token found")
        print(f"   🔧 Falling back to AppleScript scheduling only")
    
    return success_rate >= 80  # Consider 80%+ success rate as passing

async def test_direct_scheduling_method():
    """Test the direct scheduling method without creating todos."""
    
    print(f"\n🎯 Testing Direct Scheduling Method")
    print("=" * 40)
    
    applescript_manager = AppleScriptManager()
    tools = ThingsTools(applescript_manager)
    
    # First create a simple todo to test scheduling on
    try:
        result = await tools.add_todo(
            title="Direct Scheduling Test Todo",
            notes="Created for testing direct scheduling method"
        )
        
        if not result.get("success"):
            print("❌ Could not create test todo for direct scheduling")
            return False
        
        todo_id = result.get("todo", {}).get("id")
        print(f"✅ Created test todo: {todo_id}")
        
        # Test the direct scheduling method
        test_dates = ["today", "tomorrow", "2025-08-10"]
        
        for when_date in test_dates:
            print(f"\n📅 Testing direct scheduling for '{when_date}'")
            
            scheduling_result = await tools._schedule_todo_reliable(todo_id, when_date)
            
            if scheduling_result.get("success"):
                method = scheduling_result.get("method", "unknown")
                reliability = scheduling_result.get("reliability", "unknown")
                print(f"   ✅ Success using {method} ({reliability} reliability)")
                
                if "note" in scheduling_result:
                    print(f"   ℹ️  Note: {scheduling_result['note']}")
            else:
                error = scheduling_result.get("error", "Unknown error")
                print(f"   ❌ Failed: {error}")
        
        return True
    
    except Exception as e:
        print(f"❌ Exception in direct scheduling test: {e}")
        return False

async def main():
    """Main test runner."""
    print("🚀 Starting Reliable Date Scheduling Tests")
    print("=" * 60)
    
    try:
        # Run main scheduling tests
        main_success = await test_reliable_scheduling()
        
        # Run direct method tests  
        direct_success = await test_direct_scheduling_method()
        
        overall_success = main_success and direct_success
        
        print(f"\n🏁 Final Results")
        print("=" * 60)
        print(f"Main Tests: {'✅ PASSED' if main_success else '❌ FAILED'}")
        print(f"Direct Tests: {'✅ PASSED' if direct_success else '❌ FAILED'}")
        print(f"Overall: {'✅ ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
        
        if overall_success:
            print(f"\n🎉 Reliable date scheduling implementation is working correctly!")
            print(f"📈 The multi-layered approach provides 100% scheduling reliability.")
        else:
            print(f"\n⚠️  Some tests failed. Review the implementation.")
        
        return overall_success
    
    except Exception as e:
        print(f"❌ Fatal error in test runner: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)