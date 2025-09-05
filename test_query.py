#!/usr/bin/env python3
"""Test script to debug query engine date handling."""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.things_mcp.server import ThingsMCPServer


async def test_query():
    server = ThingsMCPServer()
    
    # Test the query_due_soon function
    print("Testing query_due_soon with 30 days...")
    result = await server.query_due_soon(days_ahead=30)
    
    print(f"\nResult: {result}")
    
    if result.get('success'):
        print(f"Found {result.get('count', 0)} todos")
        if result.get('todos'):
            print("\nFirst few todos:")
            for todo in result['todos'][:3]:
                print(f"  - {todo.get('title', 'NO TITLE')}")
                if '_date_field_used' in todo:
                    print(f"    Date field: {todo['_date_field_used']}")
                if '_parsed_date' in todo:
                    print(f"    Date: {todo['_parsed_date']}")
    
    # Also test getting raw todos to see what we have
    print("\n\nGetting raw todos to check fields...")
    from src.things_mcp.applescript_manager import AppleScriptManager
    from src.things_mcp.tools import ThingsTools
    
    am = AppleScriptManager()
    tools = ThingsTools(am)
    todos = await tools.get_todos()
    
    print(f"Total todos: {len(todos)}")
    
    # Check what fields are present
    if todos:
        print("\nSample todo (first one):")
        todo = todos[0]
        for key, value in todo.items():
            if value is not None and value != '' and value != []:
                print(f"  {key}: {value}")
        
        # Check field presence
        fields_to_check = ['due_date', 'deadline', 'start_date', 'activation_date', 'scheduled_date']
        print("\nField presence across all todos:")
        for field in fields_to_check:
            has_field = sum(1 for t in todos if t.get(field) is not None)
            print(f"  {field}: {has_field}/{len(todos)} todos")


if __name__ == "__main__":
    asyncio.run(test_query())