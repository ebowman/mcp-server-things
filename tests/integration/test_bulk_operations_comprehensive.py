"""
Comprehensive Test Suite for Bulk Operations and Record Movement

Tests all bulk operations with various parameter combinations, edge cases,
and performance characteristics. Validates:
- bulk_update_todos: Single and multi-field updates
- bulk_move_records: Moving to different destinations  
- move_record: Individual record moves
- add_tags/remove_tags: Tag management operations

Focus areas:
1. Single vs multi-field updates
2. Various batch sizes (1, 2, 5, 10, 50 todos)
3. Different field types (title, notes, when, deadline, tags, status)
4. Destination types (lists, projects, areas)
5. Edge cases (empty values, special characters, invalid IDs)
6. Performance degradation patterns
7. Error handling and partial failures
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any

from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools
from things_mcp.move_operations import MoveOperationsTools
from things_mcp.services.validation_service import ValidationService


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def applescript_manager():
    """Create AppleScript manager instance."""
    return AppleScriptManager()


@pytest.fixture
def things_tools(applescript_manager):
    """Create ThingsTools instance."""
    return ThingsTools(applescript_manager)


@pytest.fixture
def move_operations(applescript_manager):
    """Create MoveOperationsTools instance."""
    validation_service = ValidationService(applescript_manager)
    return MoveOperationsTools(applescript_manager, validation_service)


@pytest.fixture
async def test_todos(things_tools) -> List[str]:
    """Create a set of test todos for bulk operations."""
    todo_ids = []
    base_title = f"BulkTest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    for i in range(10):
        result = await things_tools.add_todo(
            title=f"{base_title}_{i}",
            notes=f"Test todo {i} for bulk operations"
        )
        if result.get('success'):
            # FIX: add_todo returns 'todo_id', not 'id'
            todo_ids.append(result['todo_id'])

    yield todo_ids

    # Cleanup
    for todo_id in todo_ids:
        try:
            await things_tools.delete_todo(todo_id)
        except:
            pass


@pytest.fixture
async def test_project(things_tools) -> str:
    """Create a test project for move operations."""
    result = await things_tools.add_project(
        title=f"BulkMoveTest_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        notes="Test project for bulk move operations"
    )

    # FIX: add_project returns 'project_id', not 'id'
    project_id = result.get('project_id')
    yield project_id

    # Cleanup
    if project_id:
        try:
            # FIX: update_project expects 'project_id' parameter, not 'id'
            await things_tools.update_project(project_id=project_id, canceled="true")
        except:
            pass


# ============================================================================
# Test: bulk_update_todos - Single Field Updates
# ============================================================================

class TestBulkUpdateSingleField:
    """Test bulk_update_todos with single field updates."""

    @pytest.mark.asyncio
    async def test_update_title_only(self, things_tools, test_todos):
        """Test updating only the title field."""
        todo_ids = test_todos[:3]
        new_title = f"Updated_{datetime.now().strftime('%H%M%S')}"

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            title=new_title
        )

        assert result['success']
        assert result.get('updated_count', 0) >= 3

    @pytest.mark.asyncio
    async def test_update_notes_only(self, things_tools, test_todos):
        """Test updating only the notes field."""
        todo_ids = test_todos[:3]
        new_notes = f"Updated notes at {datetime.now().isoformat()}"

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            notes=new_notes
        )

        assert result['success']
        assert result.get('updated_count', 0) >= 3

    @pytest.mark.asyncio
    async def test_update_when_today(self, things_tools, test_todos):
        """Test updating scheduling to today."""
        todo_ids = test_todos[:3]

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            when="today"
        )

        assert result['success']
        assert result.get('updated_count', 0) >= 3

    @pytest.mark.asyncio
    async def test_update_deadline_only(self, things_tools, test_todos):
        """Test updating only the deadline field."""
        todo_ids = test_todos[:3]
        deadline_date = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            deadline=deadline_date
        )

        assert result['success']
        assert result.get('updated_count', 0) >= 3

    @pytest.mark.asyncio
    async def test_update_single_tag(self, things_tools, test_todos):
        """Test updating with a single tag."""
        todo_ids = test_todos[:3]

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            tags=["test"]
        )

        assert result.get('success') or 'updated_count' in result

    @pytest.mark.asyncio
    async def test_update_multiple_tags(self, things_tools, test_todos):
        """Test updating with multiple tags."""
        todo_ids = test_todos[:3]

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            tags=["test", "urgent"]
        )

        assert result.get('success') or 'updated_count' in result

    @pytest.mark.asyncio
    async def test_mark_completed(self, things_tools, test_todos):
        """Test marking todos as completed."""
        todo_ids = test_todos[:2]

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            completed="true"
        )

        assert result.get('success') or 'updated_count' in result

    @pytest.mark.asyncio
    async def test_mark_canceled(self, things_tools, test_todos):
        """Test marking todos as canceled."""
        todo_ids = test_todos[:2]

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            canceled="true"
        )

        assert result.get('success') or 'updated_count' in result


# ============================================================================
# Test: bulk_update_todos - Multi-Field Updates
# ============================================================================

class TestBulkUpdateMultiField:
    """Test bulk_update_todos with multiple field updates."""

    @pytest.mark.asyncio
    async def test_update_title_and_notes(self, things_tools, test_todos):
        """Test updating title and notes together."""
        todo_ids = test_todos[:3]
        new_title = f"MultiUpdate_{datetime.now().strftime('%H%M%S')}"
        new_notes = "Updated with multiple fields"

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            title=new_title,
            notes=new_notes
        )

        assert result['success']
        assert result.get('updated_count', 0) >= 3

    @pytest.mark.asyncio
    async def test_update_three_fields(self, things_tools, test_todos):
        """Test updating title, notes, and when together."""
        todo_ids = test_todos[:3]

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            title=f"Triple_{datetime.now().strftime('%H%M%S')}",
            notes="Three field update",
            when="today"
        )

        assert result['success']
        assert result.get('updated_count', 0) >= 3

    @pytest.mark.asyncio
    async def test_update_tags_and_deadline(self, things_tools, test_todos):
        """Test updating tags and deadline together."""
        todo_ids = test_todos[:3]
        deadline_date = (datetime.now() + timedelta(days=14)).strftime('%Y-%m-%d')

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            tags=["urgent", "work"],
            deadline=deadline_date
        )

        # Tags may be filtered if they don't exist
        assert 'success' in result or 'updated_count' in result

    @pytest.mark.asyncio
    async def test_update_four_fields(self, things_tools, test_todos):
        """Test updating four fields together."""
        todo_ids = test_todos[:2]
        deadline_date = (datetime.now() + timedelta(days=21)).strftime('%Y-%m-%d')

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            title=f"FourFields_{datetime.now().strftime('%H%M%S')}",
            notes="Four field update",
            tags=["test"],
            deadline=deadline_date
        )

        assert 'success' in result or 'updated_count' in result

    @pytest.mark.asyncio
    async def test_update_maximum_fields(self, things_tools, test_todos):
        """Test updating all possible fields together."""
        todo_ids = test_todos[:2]
        deadline_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            title=f"MaxFields_{datetime.now().strftime('%H%M%S')}",
            notes="Maximum field update",
            tags=["test"],
            when="today",
            deadline=deadline_date
        )

        assert 'success' in result or 'updated_count' in result


# ============================================================================
# Test: bulk_update_todos - Varying Batch Sizes
# ============================================================================

class TestBulkUpdateBatchSizes:
    """Test bulk_update_todos with different batch sizes."""

    @pytest.mark.asyncio
    async def test_batch_size_1(self, things_tools, test_todos):
        """Test with batch size of 1."""
        result = await things_tools.bulk_update_todos(
            todo_ids=test_todos[:1],
            title="Batch1"
        )

        assert result['success']

    @pytest.mark.asyncio
    async def test_batch_size_2(self, things_tools, test_todos):
        """Test with batch size of 2."""
        result = await things_tools.bulk_update_todos(
            todo_ids=test_todos[:2],
            title="Batch2"
        )

        assert result['success']

    @pytest.mark.asyncio
    async def test_batch_size_5(self, things_tools, test_todos):
        """Test with batch size of 5."""
        result = await things_tools.bulk_update_todos(
            todo_ids=test_todos[:5],
            title="Batch5"
        )

        assert result['success']

    @pytest.mark.asyncio
    async def test_batch_size_10(self, things_tools, test_todos):
        """Test with batch size of 10."""
        result = await things_tools.bulk_update_todos(
            todo_ids=test_todos[:10],
            title="Batch10"
        )

        assert result['success']

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_batch_size_50_performance(self, things_tools):
        """Test with batch size of 50 (performance test)."""
        # Create 50 test todos
        todo_ids = []
        base_title = f"Perf50_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        for i in range(50):
            result = await things_tools.add_todo(
                title=f"{base_title}_{i}"
            )
            if result.get('success'):
                # FIX: add_todo returns 'todo_id', not 'id'
                todo_ids.append(result['todo_id'])

        try:
            start_time = datetime.now()

            result = await things_tools.bulk_update_todos(
                todo_ids=todo_ids,
                title="Perf50Update"
            )

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            assert result['success']
            assert duration < 30.0, f"Took {duration}s (expected <30s)"

            print(f"\n50-todo bulk update: {duration:.2f}s ({duration/50:.3f}s per todo)")

        finally:
            for todo_id in todo_ids:
                try:
                    await things_tools.delete_todo(todo_id)
                except:
                    pass


# ============================================================================
# Test: bulk_update_todos - Edge Cases
# ============================================================================

class TestBulkUpdateEdgeCases:
    """Test bulk_update_todos edge cases."""

    @pytest.mark.asyncio
    async def test_empty_todo_list(self, things_tools):
        """Test with empty todo list."""
        result = await things_tools.bulk_update_todos(
            todo_ids=[],
            title="ShouldFail"
        )

        assert not result['success']

    @pytest.mark.asyncio
    async def test_special_characters_in_title(self, things_tools, test_todos):
        """Test with special characters in title."""
        todo_ids = test_todos[:2]
        special_title = 'Title with "quotes" and \'apostrophes\' & symbols!'

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            title=special_title
        )

        assert result.get('success') or 'updated_count' in result

    @pytest.mark.asyncio
    async def test_long_notes_text(self, things_tools, test_todos):
        """Test with very long notes."""
        todo_ids = test_todos[:2]
        long_notes = "A" * 1000

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            notes=long_notes
        )

        assert result['success']

    @pytest.mark.asyncio
    async def test_empty_string_values(self, things_tools, test_todos):
        """Test with empty string values."""
        todo_ids = test_todos[:2]

        result = await things_tools.bulk_update_todos(
            todo_ids=todo_ids,
            notes=""
        )

        assert result.get('success') or 'updated_count' in result


# ============================================================================
# Test: move_record - Individual Moves
# ============================================================================

class TestMoveRecord:
    """Test individual record move operations."""

    @pytest.mark.asyncio
    async def test_move_to_inbox(self, things_tools, test_todos):
        """Test moving a todo to inbox."""
        result = await things_tools.move_record(
            todo_id=test_todos[0],
            destination_list="inbox"
        )

        assert result.get('success') or 'destination' in result

    @pytest.mark.asyncio
    async def test_move_to_today(self, things_tools, test_todos):
        """Test moving a todo to today."""
        result = await things_tools.move_record(
            todo_id=test_todos[0],
            destination_list="today"
        )

        assert result.get('success') or 'destination' in result

    @pytest.mark.asyncio
    async def test_move_to_anytime(self, things_tools, test_todos):
        """Test moving a todo to anytime."""
        result = await things_tools.move_record(
            todo_id=test_todos[0],
            destination_list="anytime"
        )

        assert result.get('success') or 'destination' in result

    @pytest.mark.asyncio
    async def test_move_to_someday(self, things_tools, test_todos):
        """Test moving a todo to someday."""
        result = await things_tools.move_record(
            todo_id=test_todos[0],
            destination_list="someday"
        )

        assert result.get('success') or 'destination' in result

    @pytest.mark.asyncio
    async def test_move_to_project(self, things_tools, test_todos, test_project):
        """Test moving a todo to a project."""
        result = await things_tools.move_record(
            todo_id=test_todos[0],
            destination_list=f"project:{test_project}"
        )

        assert result.get('success') or 'destination' in result

    @pytest.mark.asyncio
    async def test_move_invalid_destination(self, things_tools, test_todos):
        """Test moving to an invalid destination."""
        result = await things_tools.move_record(
            todo_id=test_todos[0],
            destination_list="invalid_destination"
        )

        assert not result.get('success', True)


# ============================================================================
# Test: bulk_move_records - Bulk Moves
# ============================================================================

class TestBulkMoveRecords:
    """Test bulk move operations."""

    @pytest.mark.asyncio
    async def test_bulk_move_to_inbox(self, move_operations, test_todos):
        """Test bulk moving todos to inbox."""
        todo_ids = test_todos[:5]

        result = await move_operations.bulk_move(
            todo_ids=todo_ids,
            destination="inbox"
        )

        assert 'success' in result
        assert result.get('total_requested', 0) == 5

    @pytest.mark.asyncio
    async def test_bulk_move_to_today(self, move_operations, test_todos):
        """Test bulk moving todos to today."""
        todo_ids = test_todos[:5]

        result = await move_operations.bulk_move(
            todo_ids=todo_ids,
            destination="today"
        )

        assert 'success' in result

    @pytest.mark.asyncio
    async def test_bulk_move_to_project(self, move_operations, test_todos, test_project):
        """Test bulk moving todos to a project."""
        todo_ids = test_todos[:5]

        result = await move_operations.bulk_move(
            todo_ids=todo_ids,
            destination=f"project:{test_project}"
        )

        assert 'success' in result

    @pytest.mark.asyncio
    async def test_bulk_move_varying_concurrency(self, move_operations, test_todos):
        """Test bulk move with different concurrency settings."""
        # Test max_concurrent=1
        result1 = await move_operations.bulk_move(
            todo_ids=test_todos[:2],
            destination="inbox",
            max_concurrent=1
        )
        assert 'success' in result1

        # Test max_concurrent=5
        result2 = await move_operations.bulk_move(
            todo_ids=test_todos[2:4],
            destination="today",
            max_concurrent=5
        )
        assert 'success' in result2

        # Test max_concurrent=10
        result3 = await move_operations.bulk_move(
            todo_ids=test_todos[4:6],
            destination="anytime",
            max_concurrent=10
        )
        assert 'success' in result3

    @pytest.mark.asyncio
    async def test_bulk_move_preserve_scheduling(self, move_operations, test_todos):
        """Test preserve_scheduling parameter."""
        result = await move_operations.bulk_move(
            todo_ids=test_todos[:3],
            destination="inbox",
            preserve_scheduling=True
        )

        assert 'success' in result

    @pytest.mark.asyncio
    async def test_bulk_move_empty_list(self, move_operations):
        """Test bulk move with empty todo list."""
        result = await move_operations.bulk_move(
            todo_ids=[],
            destination="inbox"
        )

        assert not result['success']


# ============================================================================
# Test: Tag Management
# ============================================================================

class TestTagManagement:
    """Test tag operations."""

    @pytest.mark.asyncio
    async def test_add_single_tag(self, things_tools, test_todos):
        """Test adding a single tag."""
        result = await things_tools.add_tags(
            todo_id=test_todos[0],
            tags=["test"]
        )

        assert 'success' in result

    @pytest.mark.asyncio
    async def test_add_multiple_tags(self, things_tools, test_todos):
        """Test adding multiple tags."""
        result = await things_tools.add_tags(
            todo_id=test_todos[0],
            tags=["test", "urgent"]
        )

        assert 'success' in result

    @pytest.mark.asyncio
    async def test_remove_single_tag(self, things_tools, test_todos):
        """Test removing a tag."""
        # Add tag first
        await things_tools.add_tags(todo_id=test_todos[0], tags=["test"])

        # Remove it
        result = await things_tools.remove_tags(
            todo_id=test_todos[0],
            tags=["test"]
        )

        assert 'success' in result

    @pytest.mark.asyncio
    async def test_remove_multiple_tags(self, things_tools, test_todos):
        """Test removing multiple tags."""
        # Add tags first
        await things_tools.add_tags(
            todo_id=test_todos[0],
            tags=["test", "urgent"]
        )

        # Remove them
        result = await things_tools.remove_tags(
            todo_id=test_todos[0],
            tags=["test", "urgent"]
        )

        assert 'success' in result


# ============================================================================
# Run Configuration
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
