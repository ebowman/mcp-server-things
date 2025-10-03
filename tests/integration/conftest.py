"""
Integration test fixtures for Things 3 MCP server.

Provides cleanup fixtures and utilities for integration tests that interact
with real Things 3 database.
"""

import pytest
import asyncio
from datetime import datetime
from typing import List, Dict
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
async def cleanup_test_todos():
    """
    Fixture that provides test data tracking and cleanup.

    Usage:
        @pytest.mark.asyncio
        async def test_something(self, cleanup_test_todos, mock_applescript_manager):
            tools = ThingsTools(mock_applescript_manager)

            # Create test data
            result = await tools.add_todo(
                title=f"Test todo {cleanup_test_todos['tag']}",
                tags=cleanup_test_todos['tag']
            )
            cleanup_test_todos['ids'].append(result['id'])

            # ... test assertions ...

            # Cleanup happens automatically after test

    Returns:
        dict: Contains 'tag' (unique test identifier) and 'ids' (list to track created items)
    """
    # Create unique tag for this test run
    test_tag = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    todo_ids = []
    project_ids = []

    test_data = {
        'tag': test_tag,
        'ids': todo_ids,
        'project_ids': project_ids
    }

    yield test_data

    # Cleanup phase - runs after test completes (even if it fails)
    if todo_ids or project_ids:
        try:
            manager = AppleScriptManager()
            tools = ThingsTools(manager)

            # Delete all tracked todos
            for todo_id in todo_ids:
                try:
                    await tools.delete_todo(todo_id=todo_id)
                except Exception as e:
                    print(f"Warning: Failed to cleanup todo {todo_id}: {e}")

            # Delete all tracked projects
            for project_id in project_ids:
                try:
                    # Delete project using update with canceled=true
                    await tools.update_project(id=project_id, canceled="true")
                    await tools.delete_todo(todo_id=project_id)
                except Exception as e:
                    print(f"Warning: Failed to cleanup project {project_id}: {e}")

            # Also try to find and delete by tag
            try:
                tagged_items = await tools.get_tagged_items(tag=test_tag)
                for item in tagged_items:
                    try:
                        await tools.delete_todo(todo_id=item['id'])
                    except Exception as e:
                        print(f"Warning: Failed to cleanup tagged item {item['id']}: {e}")
            except Exception as e:
                print(f"Warning: Failed to cleanup by tag: {e}")

        except Exception as e:
            print(f"Error during test cleanup: {e}")


@pytest.fixture
async def real_things_tools():
    """
    Fixture providing ThingsTools with real AppleScript manager.

    Use this for integration tests that need to interact with actual Things 3.
    """
    manager = AppleScriptManager()
    tools = ThingsTools(manager)
    yield tools


@pytest.fixture
def unique_test_id():
    """Generate a unique test identifier."""
    return f"test_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
