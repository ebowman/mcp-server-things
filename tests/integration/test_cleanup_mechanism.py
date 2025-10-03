"""
Test Cleanup Mechanism Verification

This is a standalone test to verify that the cleanup_test_todos fixture works correctly
BEFORE running the full integration test suite. This prevents test pollution.

Expected Behavior:
1. Test creates 5 todos with unique identifiers
2. Test passes
3. Cleanup fixture automatically deletes all 5 todos
4. Manual verification confirms no todos remain

Run this test FIRST:
    pytest tests/integration/test_cleanup_mechanism.py -v

Then verify cleanup:
    python tests/integration/verify_cleanup.py
"""

import pytest
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools


@pytest.fixture
def applescript_manager():
    """Create real AppleScript manager."""
    return AppleScriptManager()


@pytest.fixture
def things_tools(applescript_manager):
    """Create ThingsTools instance."""
    return ThingsTools(applescript_manager)


class TestCleanupMechanism:
    """Verify cleanup mechanism works correctly."""

    @pytest.mark.asyncio
    async def test_cleanup_deletes_all_todos(self, things_tools, cleanup_test_todos):
        """Create 5 todos, verify they're cleaned up automatically."""
        print(f"\n🧪 Testing cleanup mechanism with tag: {cleanup_test_todos['tag']}")

        # Create 5 test todos
        created_todos = []
        for i in range(5):
            result = await things_tools.add_todo(
                title=f"Cleanup Test {i} - {cleanup_test_todos['tag']}",
                notes=f"This is test todo {i} for cleanup verification"
            )

            assert result.get('success'), f"Failed to create todo {i}"
            todo_id = result['todo_id']
            cleanup_test_todos['ids'].append(todo_id)
            created_todos.append(todo_id)

            print(f"  ✓ Created todo {i+1}/5: {todo_id}")

        # Verify all todos exist
        print(f"\n📋 Verifying todos exist before cleanup...")
        for i, todo_id in enumerate(created_todos):
            todo = await things_tools.get_todo_by_id(todo_id=todo_id)
            assert todo is not None, f"Todo {i} not found"
            assert todo['uuid'] == todo_id, f"UUID mismatch: expected {todo_id}, got {todo.get('uuid')}"
            print(f"  ✓ Todo {i+1}/5 exists: {todo['title']}")

        print(f"\n✅ All 5 todos created successfully")
        print(f"🔄 Cleanup fixture will now delete them...")

        # Cleanup happens automatically after this test
        # User should manually verify with: python tests/integration/verify_cleanup.py

    @pytest.mark.asyncio
    async def test_cleanup_handles_already_deleted(self, things_tools, cleanup_test_todos):
        """Verify cleanup handles already-deleted todos gracefully."""
        print(f"\n🧪 Testing cleanup with pre-deleted todos: {cleanup_test_todos['tag']}")

        # Create todo
        result = await things_tools.add_todo(
            title=f"Pre-delete Test - {cleanup_test_todos['tag']}"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        print(f"  ✓ Created todo: {todo_id}")

        # Delete it manually
        await things_tools.delete_todo(todo_id)
        print(f"  ✓ Manually deleted todo")

        # Cleanup fixture should handle this gracefully (no error)
        print(f"🔄 Cleanup fixture will try to delete again (should be graceful)...")

    @pytest.mark.asyncio
    async def test_cleanup_with_project(self, things_tools, cleanup_test_todos):
        """Verify cleanup handles projects correctly."""
        print(f"\n🧪 Testing cleanup with project: {cleanup_test_todos['tag']}")

        # Create project
        result = await things_tools.add_project(
            title=f"Cleanup Project Test - {cleanup_test_todos['tag']}",
            notes="This project should be canceled by cleanup"
        )

        assert result.get('success')
        project_id = result['project_id']
        cleanup_test_todos['project_ids'].append(project_id)

        print(f"  ✓ Created project: {project_id}")

        # Cleanup fixture will cancel this project
        print(f"🔄 Cleanup fixture will cancel this project...")
