#!/usr/bin/env python3
"""Test script for new efficient date-range query tools."""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.things_mcp.services.applescript_manager import AppleScriptManager
from src.things_mcp.tools import ThingsTools


async def test_date_queries():
    """Test the new efficient date-range query methods."""
    am = AppleScriptManager()
    tools = ThingsTools(am)
    
    print("=" * 60)
    print("Testing Efficient Date-Range Query Tools")
    print("=" * 60)
    
    # Test 1: Get todos due in next 30 days
    print("\n1. Testing get_todos_due_in_days(30)...")
    print("-" * 40)
    try:
        due_todos = await tools.get_todos_due_in_days(30)
        print(f"Found {len(due_todos)} todos due in next 30 days")
        
        if due_todos:
            print("\nFirst 3 todos with due dates:")
            for todo in due_todos[:3]:
                print(f"  - {todo.get('name', 'NO NAME')}")
                print(f"    Due: {todo.get('due_date', 'NO DUE DATE')}")
                print(f"    ID: {todo.get('id', 'NO ID')}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    # Test 2: Get todos activating in next 7 days
    print("\n2. Testing get_todos_activating_in_days(7)...")
    print("-" * 40)
    try:
        activating_todos = await tools.get_todos_activating_in_days(7)
        print(f"Found {len(activating_todos)} todos activating in next 7 days")
        
        if activating_todos:
            print("\nFirst 3 todos with activation dates:")
            for todo in activating_todos[:3]:
                print(f"  - {todo.get('name', 'NO NAME')}")
                print(f"    Activation: {todo.get('activation_date', 'NO ACTIVATION DATE')}")
                if todo.get('has_reminder'):
                    print(f"    Reminder: {todo.get('reminder_time', 'NO TIME')}")
                print(f"    ID: {todo.get('id', 'NO ID')}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    # Test 3: Get all upcoming todos in next 14 days (union)
    print("\n3. Testing get_todos_upcoming_in_days(14)...")
    print("-" * 40)
    try:
        upcoming_todos = await tools.get_todos_upcoming_in_days(14)
        print(f"Found {len(upcoming_todos)} todos upcoming in next 14 days")
        
        if upcoming_todos:
            print("\nFirst 5 upcoming todos:")
            for todo in upcoming_todos[:5]:
                print(f"  - {todo.get('name', 'NO NAME')}")
                if todo.get('due_date'):
                    print(f"    Due: {todo.get('due_date')}")
                if todo.get('activation_date'):
                    print(f"    Activation: {todo.get('activation_date')}")
                    if todo.get('has_reminder'):
                        print(f"    Reminder: {todo.get('reminder_time')}")
                if todo.get('tag_names'):
                    print(f"    Tags: {', '.join(todo.get('tag_names', []))}")
                print(f"    ID: {todo.get('id', 'NO ID')}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    # Test 4: Performance comparison
    print("\n4. Performance Comparison...")
    print("-" * 40)
    
    # Time the efficient query
    start = datetime.now()
    efficient_todos = await tools.get_todos_upcoming_in_days(30)
    efficient_time = (datetime.now() - start).total_seconds()
    
    # Time the traditional approach (get all, then filter)
    start = datetime.now()
    all_todos = await tools.get_todos()
    traditional_time = (datetime.now() - start).total_seconds()
    
    print(f"Efficient query (30 days): {efficient_time:.2f}s - {len(efficient_todos)} todos")
    print(f"Traditional (get all): {traditional_time:.2f}s - {len(all_todos)} todos total")
    print(f"Speed improvement: {traditional_time/efficient_time:.1f}x faster")
    
    print("\n" + "=" * 60)
    print("Test Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_date_queries())