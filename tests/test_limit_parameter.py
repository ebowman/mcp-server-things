#!/usr/bin/env python
"""Test limit parameter handling in get_todos."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.things_mcp.server import ThingsMCPServer


async def test_limit_parameter():
    """Test that the limit parameter works with various input types."""
    server = ThingsMCPServer()
    
    print("Testing limit parameter handling...")
    
    # Test 1: Integer limit
    print("\n1. Testing with integer limit=3")
    result = await server.get_todos(mode='minimal', limit=3)
    if 'error' not in result:
        print(f"   ✓ Integer limit works: returned {len(result.get('todos', []))} todos")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    # Test 2: String limit
    print("\n2. Testing with string limit='5'")
    result = await server.get_todos(mode='minimal', limit='5')
    if 'error' not in result:
        print(f"   ✓ String limit works: returned {len(result.get('todos', []))} todos")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    # Test 3: Float limit (should be converted)
    print("\n3. Testing with float limit=7.0")
    result = await server.get_todos(mode='minimal', limit=7.0)
    if 'error' not in result:
        print(f"   ✓ Float limit works: returned {len(result.get('todos', []))} todos")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    # Test 4: Invalid limit (out of range)
    print("\n4. Testing with invalid limit=600")
    result = await server.get_todos(mode='minimal', limit=600)
    if 'error' in result:
        print(f"   ✓ Invalid limit correctly rejected: {result.get('message')}")
    else:
        print(f"   ✗ Invalid limit not caught")
    
    # Test 5: None limit (should work)
    print("\n5. Testing with None limit")
    result = await server.get_todos(mode='summary', limit=None)
    if 'error' not in result:
        print(f"   ✓ None limit works: {result.get('count', 0)} todos available")
    else:
        print(f"   ✗ Error: {result.get('error')}")
    
    print("\n✅ All programmatic tests completed!")


if __name__ == "__main__":
    asyncio.run(test_limit_parameter())