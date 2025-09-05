#!/usr/bin/env python3
"""Test to see what fields todos actually have."""

import asyncio
import sys
from pathlib import Path

# Add src to path  
sys.path.insert(0, str(Path(__file__).parent))

from src.things_mcp.applescript_manager import AppleScriptManager
from src.things_mcp.tools import ThingsTools


async def main():
    am = AppleScriptManager()
    tools = ThingsTools(am)
    
    # Get all todos
    print("Getting todos...")
    todos = await tools.get_todos()
    
    print(f"Total todos: {len(todos)}")
    
    if not todos:
        print("No todos found!")
        return
    
    # Check first todo
    print("\nFirst todo structure:")
    todo = todos[0]
    for key, value in todo.items():
        print(f"  {key}: {value}")
    
    # Check what date fields exist across all todos
    print("\n\nDate field presence:")
    date_fields = ['due_date', 'deadline', 'start_date', 'activation_date', 
                   'scheduled_date', 'creation_date', 'modification_date', 
                   'completion_date']
    
    for field in date_fields:
        # Count how many todos have non-null values for this field
        count = sum(1 for t in todos if t.get(field) not in [None, '', []])
        if count > 0:
            print(f"  {field}: {count}/{len(todos)} todos")
            # Show a sample value
            for t in todos:
                if t.get(field) not in [None, '', []]:
                    print(f"    Sample value: {t.get(field)}")
                    break
    
    # Check if any todos are scheduled for today or future
    print("\n\nLooking for scheduled todos...")
    scheduled_count = 0
    for todo in todos:
        # Check all possible scheduling fields
        if (todo.get('scheduled_date') == 'today' or 
            todo.get('start_date') == 'today' or
            todo.get('activation_date') or
            todo.get('due_date')):
            scheduled_count += 1
            print(f"  - {todo.get('title', 'NO TITLE')}")
            print(f"    scheduled_date: {todo.get('scheduled_date')}")
            print(f"    start_date: {todo.get('start_date')}")
            print(f"    activation_date: {todo.get('activation_date')}")
            print(f"    due_date: {todo.get('due_date')}")
            if scheduled_count >= 5:
                print("  ... (showing first 5)")
                break


if __name__ == "__main__":
    asyncio.run(main())