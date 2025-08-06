#!/usr/bin/env python3
"""
Test script for the newly implemented search and tag functionality.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from things_mcp.tools import ThingsTools
from things_mcp.applescript_manager import AppleScriptManager

def main():
    print("Testing newly implemented Things MCP functions...")
    
    # Initialize the tools
    applescript_manager = AppleScriptManager()
    tools = ThingsTools(applescript_manager)
    
    # Check if Things is running
    if not applescript_manager.is_things_running():
        print("❌ Things 3 is not running. Please open Things 3 and try again.")
        return
    
    print("✅ Things 3 is running")
    
    # Test 1: Get tags
    print("\n1. Testing get_tags()...")
    try:
        tags = tools.get_tags()
        print(f"✅ Found {len(tags)} tags")
        if tags:
            print(f"   First tag: {tags[0]}")
    except Exception as e:
        print(f"❌ get_tags() failed: {e}")
    
    # Test 2: Search todos
    print("\n2. Testing search_todos()...")
    try:
        todos = tools.search_todos("test")
        print(f"✅ Search found {len(todos)} todos matching 'test'")
        if todos:
            print(f"   First result: {todos[0]['title']}")
    except Exception as e:
        print(f"❌ search_todos() failed: {e}")
    
    # Test 3: Get recent items
    print("\n3. Testing get_recent()...")
    try:
        recent = tools.get_recent("7d")
        print(f"✅ Found {len(recent)} recent items from last 7 days")
        if recent:
            print(f"   First item: {recent[0]['title']}")
    except Exception as e:
        print(f"❌ get_recent() failed: {e}")
    
    # Test 4: Advanced search
    print("\n4. Testing search_advanced()...")
    try:
        results = tools.search_advanced(status="incomplete")
        print(f"✅ Advanced search found {len(results)} incomplete items")
        if results:
            print(f"   First result: {results[0]['title']}")
    except Exception as e:
        print(f"❌ search_advanced() failed: {e}")
    
    # Test 5: Get tagged items (if we have tags)
    if tags:
        print("\n5. Testing get_tagged_items()...")
        try:
            tag_name = tags[0]['name']
            tagged_items = tools.get_tagged_items(tag_name)
            print(f"✅ Found {len(tagged_items)} items with tag '{tag_name}'")
            if tagged_items:
                print(f"   First item: {tagged_items[0]['title']}")
        except Exception as e:
            print(f"❌ get_tagged_items() failed: {e}")
    
    print("\n✅ All tests completed!")

if __name__ == "__main__":
    main()