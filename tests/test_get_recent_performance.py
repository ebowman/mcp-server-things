#!/usr/bin/env python3
"""Test the optimized get_recent performance."""

import asyncio
import time
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


async def test_get_recent_performance():
    """Test the performance of get_recent with different periods."""
    
    # Initialize the tools
    applescript_manager = AppleScriptManager()
    tools = ThingsTools(applescript_manager)
    
    test_periods = ['1d', '3d', '7d']
    
    for period in test_periods:
        print(f"\nTesting get_recent with period: {period}")
        
        start_time = time.time()
        try:
            results = await tools.get_recent(period)
            elapsed = time.time() - start_time
            
            print(f"  ✓ Completed in {elapsed:.2f} seconds")
            print(f"  ✓ Found {len(results)} items")
            
            # Show first few items as sample
            if results:
                print(f"  Sample items:")
                for item in results[:3]:
                    print(f"    - {item.get('title', 'Unknown')} ({item.get('item_type', 'unknown')})")
                    
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"  ✗ Failed after {elapsed:.2f} seconds: {e}")
    
    print("\n✅ Performance test complete")


if __name__ == "__main__":
    asyncio.run(test_get_recent_performance())