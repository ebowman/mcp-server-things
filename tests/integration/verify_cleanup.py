#!/usr/bin/env python3
"""
Cleanup Verification Script for Integration Tests

This script verifies that no test data remains in Things 3 after integration test runs.
It searches for todos with test-related prefixes and reports any orphaned test data.

Usage:
    python verify_cleanup.py              # Check for test data
    python verify_cleanup.py --cleanup    # Clean up any found test data
"""

import asyncio
import sys
from datetime import datetime, timedelta

from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools


async def find_test_todos(tools: ThingsTools) -> list:
    """Find all todos with test-related prefixes.

    Returns:
        List of todos that appear to be test data
    """
    test_prefixes = [
        "test-",
        "Test ",
        "BulkTest_",
        "Today Test",
        "Tomorrow Test",
        "Someday Test",
        "Anytime Test",
        "Plus ",
        "Reschedule Test",
        "Clear Schedule Test",
        "Far Future Test"
    ]

    all_test_todos = []

    # Search for each prefix
    for prefix in test_prefixes:
        try:
            results = await tools.search_todos(query=prefix, limit=100)
            if results:
                all_test_todos.extend(results)
        except Exception as e:
            print(f"Error searching for '{prefix}': {e}")

    # Remove duplicates based on UUID
    seen_ids = set()
    unique_todos = []
    for todo in all_test_todos:
        todo_id = todo.get('uuid') or todo.get('id')  # Support both field names
        if todo_id and todo_id not in seen_ids:
            seen_ids.add(todo_id)
            unique_todos.append(todo)

    return unique_todos


async def find_test_projects(tools: ThingsTools) -> list:
    """Find all projects with test-related prefixes.

    Returns:
        List of projects that appear to be test data
    """
    try:
        all_projects = await tools.get_projects()
        test_projects = [
            p for p in all_projects
            if any(prefix in p.get('title', '') for prefix in ['BulkTest_', 'BulkMoveTest_', 'Test Project'])
        ]
        return test_projects
    except Exception as e:
        print(f"Error getting projects: {e}")
        return []


async def cleanup_test_data(tools: ThingsTools, todos: list, projects: list):
    """Clean up identified test data.

    Args:
        tools: ThingsTools instance
        todos: List of test todos to delete
        projects: List of test projects to cancel
    """
    print(f"\nCleaning up {len(todos)} todos and {len(projects)} projects...")

    # Delete todos
    deleted_count = 0
    for todo in todos:
        try:
            todo_id = todo.get('uuid') or todo.get('id')
            await tools.delete_todo(todo_id)
            deleted_count += 1
            print(f"  ✓ Deleted todo: {todo.get('title', 'Unknown')[:50]}")
        except Exception as e:
            todo_id = todo.get('uuid') or todo.get('id')
            print(f"  ✗ Failed to delete todo {todo_id}: {e}")

    # Cancel projects
    canceled_count = 0
    for project in projects:
        try:
            project_id = project.get('uuid') or project.get('id')
            await tools.update_project(project_id=project_id, canceled="true")
            canceled_count += 1
            print(f"  ✓ Canceled project: {project.get('title', 'Unknown')[:50]}")
        except Exception as e:
            project_id = project.get('uuid') or project.get('id')
            print(f"  ✗ Failed to cancel project {project_id}: {e}")

    print(f"\nCleanup complete: {deleted_count}/{len(todos)} todos, {canceled_count}/{len(projects)} projects")


async def verify_no_test_data():
    """Main verification function."""
    print("=" * 70)
    print("Things 3 Integration Test Cleanup Verification")
    print("=" * 70)

    manager = AppleScriptManager()
    tools = ThingsTools(manager)

    # Find test data
    print("\nSearching for test data in Things 3...")
    test_todos = await find_test_todos(tools)
    test_projects = await find_test_projects(tools)

    # Report findings
    print(f"\nFound {len(test_todos)} test todos")
    print(f"Found {len(test_projects)} test projects")

    if test_todos:
        print("\nTest Todos Found:")
        for todo in test_todos[:10]:  # Show first 10
            title = todo.get('title', 'Unknown')
            created = todo.get('creation_date', 'Unknown')
            print(f"  - {title[:60]} (created: {created})")
        if len(test_todos) > 10:
            print(f"  ... and {len(test_todos) - 10} more")

    if test_projects:
        print("\nTest Projects Found:")
        for project in test_projects[:10]:
            title = project.get('title', 'Unknown')
            created = project.get('creation_date', 'Unknown')
            print(f"  - {title[:60]} (created: {created})")
        if len(test_projects) > 10:
            print(f"  ... and {len(test_projects) - 10} more")

    # Check if cleanup is requested
    if '--cleanup' in sys.argv:
        if test_todos or test_projects:
            print("\n⚠️  Cleanup mode enabled - will delete test data")
            response = input("Continue? (yes/no): ")
            if response.lower() == 'yes':
                await cleanup_test_data(tools, test_todos, test_projects)
            else:
                print("Cleanup canceled")
        else:
            print("\n✓ No test data to clean up")
    else:
        # Report status
        if test_todos or test_projects:
            print("\n" + "=" * 70)
            print("❌ CLEANUP VERIFICATION FAILED")
            print("=" * 70)
            print(f"Test data found in Things 3: {len(test_todos)} todos, {len(test_projects)} projects")
            print("Run with --cleanup flag to remove test data")
            return False
        else:
            print("\n" + "=" * 70)
            print("✅ CLEANUP VERIFICATION PASSED")
            print("=" * 70)
            print("No test data found in Things 3")
            return True


if __name__ == "__main__":
    result = asyncio.run(verify_no_test_data())
    sys.exit(0 if result else 1)
