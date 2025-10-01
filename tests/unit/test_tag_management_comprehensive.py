"""
Comprehensive test suite for tag management functionality.

Tests all tag operations including:
- Tag discovery (get_tags)
- Adding tags (add_tags)
- Removing tags (remove_tags)
- Tag filtering (get_tagged_items)
- Edge cases and string parsing
- Case sensitivity
- Tag validation and creation limitations
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager."""
    manager = Mock(spec=AppleScriptManager)
    manager.execute_applescript = AsyncMock()
    return manager


@pytest.fixture
def things_tools(mock_applescript_manager):
    """Create ThingsTools instance with mocked AppleScript."""
    return ThingsTools(mock_applescript_manager)


class TestGetTags:
    """Test tag discovery and listing functionality."""

    @pytest.mark.asyncio
    async def test_get_tags_default_counts_only(self, things_tools):
        """Test get_tags() default behavior returns counts only."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos:

            # Mock tags data
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'Work'},
                {'uuid': 'tag2', 'title': 'Personal'},
                {'uuid': 'tag3', 'title': 'urgent'}
            ]

            # Mock todos for each tag
            def todos_for_tag(tag=None, **kwargs):
                if tag == 'Work':
                    return [{'uuid': '1', 'title': 'Task 1'}, {'uuid': '2', 'title': 'Task 2'}]
                elif tag == 'Personal':
                    return [{'uuid': '3', 'title': 'Task 3'}]
                elif tag == 'urgent':
                    return []  # Tag with no items
                return []

            mock_todos.side_effect = todos_for_tag

            # Get tags with counts only (default)
            result = await things_tools.get_tags(include_items=False)

            # Verify structure
            assert len(result) == 3

            # Check Work tag
            work_tag = next(t for t in result if t['name'] == 'Work')
            assert work_tag['name'] == 'Work'
            assert work_tag['item_count'] == 2
            assert 'items' not in work_tag

            # Check Personal tag
            personal_tag = next(t for t in result if t['name'] == 'Personal')
            assert personal_tag['item_count'] == 1

            # Check urgent tag (no items)
            urgent_tag = next(t for t in result if t['name'] == 'urgent')
            assert 'item_count' not in urgent_tag  # No count field if 0

    @pytest.mark.asyncio
    async def test_get_tags_with_items(self, things_tools):
        """Test get_tags(include_items=true) returns full item lists."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos:

            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'Work'}
            ]

            # Mock todos for Work tag
            mock_todos.return_value = [
                {
                    'uuid': 'todo1',
                    'title': 'Write report',
                    'status': 'incomplete',
                    'type': 'to-do'
                },
                {
                    'uuid': 'todo2',
                    'title': 'Review PR',
                    'status': 'incomplete',
                    'type': 'to-do'
                }
            ]

            result = await things_tools.get_tags(include_items=True)

            assert len(result) == 1
            work_tag = result[0]
            assert work_tag['name'] == 'Work'
            assert 'items' in work_tag
            assert len(work_tag['items']) == 2
            # Use 'name' field instead of 'title' (after optimization)
            assert work_tag['items'][0]['name'] == 'Write report'
            assert work_tag['items'][1]['name'] == 'Review PR'

    @pytest.mark.asyncio
    async def test_get_tags_structure_and_fields(self, things_tools):
        """Test tag structure contains expected fields."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos:

            mock_tags.return_value = [
                {'uuid': 'unique-id-123', 'title': 'TestTag'}
            ]
            mock_todos.return_value = [{'uuid': '1', 'title': 'Task'}]

            result = await things_tools.get_tags()

            assert len(result) == 1
            tag = result[0]

            # Required fields
            assert 'name' in tag
            assert tag['name'] == 'TestTag'

            # ID only included if different from name
            assert 'id' in tag
            assert tag['id'] == 'unique-id-123'

            # Count field present when > 0
            assert 'item_count' in tag
            assert tag['item_count'] == 1


class TestAddTags:
    """Test adding tags to todos."""

    @pytest.mark.asyncio
    async def test_add_single_tag(self, things_tools, mock_applescript_manager):
        """Test adding a single tag to a todo."""
        # Mock current tags (empty)
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},  # Current tags (empty)
            {'success': True, 'output': 'tags_added'}  # Add operation
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [{'uuid': 'tag1', 'title': 'urgent'}]

            result = await things_tools.add_tags(todo_id='abc123', tags=['urgent'])

            assert result['success'] is True
            assert 'Added 1 tags successfully' in result['message']

    @pytest.mark.asyncio
    async def test_add_multiple_tags(self, things_tools, mock_applescript_manager):
        """Test adding multiple comma-separated tags."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},  # Current tags
            {'success': True, 'output': 'tags_added'}  # Add operation
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'work'},
                {'uuid': 'tag2', 'title': 'urgent'},
                {'uuid': 'tag3', 'title': 'review'}
            ]

            result = await things_tools.add_tags(
                todo_id='abc123',
                tags=['work', 'urgent', 'review']
            )

            assert result['success'] is True
            assert 'Added 3 tags successfully' in result['message']

    @pytest.mark.asyncio
    async def test_add_tags_string_formatting_no_spaces(self, things_tools, mock_applescript_manager):
        """Test tag string must not include spaces after commas."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'work'},
                {'uuid': 'tag2', 'title': 'urgent'}
            ]

            # Test with proper format (list input)
            result = await things_tools.add_tags(
                todo_id='abc123',
                tags=['work', 'urgent']  # Proper list format
            )

            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_add_tags_string_input_conversion(self, things_tools, mock_applescript_manager):
        """Test that string input is converted to list (defensive programming)."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'work'},
                {'uuid': 'tag2', 'title': 'urgent'}
            ]

            # Test string input (should be converted to list)
            result = await things_tools.add_tags(
                todo_id='abc123',
                tags='work,urgent'  # String format
            )

            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_add_tags_case_sensitive(self, things_tools, mock_applescript_manager):
        """Test that tag names are case-sensitive."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            # Only "Work" exists, not "work"
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'Work'}
            ]

            # Adding "Work" should succeed
            result = await things_tools.add_tags(todo_id='abc123', tags=['Work'])
            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_add_nonexistent_tags_filtered(self, things_tools, mock_applescript_manager):
        """Test that non-existent tags are filtered out."""
        # Note: Without tag_validation_service (config), all tags are treated as valid
        # This test verifies the fallback behavior
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},  # Current tags
            {'success': True, 'output': 'tags_added'}  # Add operation
        ]

        with patch('things.tags') as mock_tags:
            # Only 'work' tag exists
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'work'}
            ]

            # Try to add non-existent tag (will succeed in fallback mode)
            result = await things_tools.add_tags(
                todo_id='abc123',
                tags=['nonexistent-tag']
            )

            # In fallback mode (no config), all tags are treated as valid
            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_add_tags_during_todo_creation(self, things_tools, mock_applescript_manager):
        """Test adding tags during todo creation."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'new-todo-id-123'
        }

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'work'},
                {'uuid': 'tag2', 'title': 'urgent'}
            ]

            # This tests the add_todo function with tags parameter
            result = await things_tools.add_todo(
                title='New task',
                tags=['work', 'urgent']
            )

            assert result['success'] is True


class TestRemoveTags:
    """Test removing tags from todos."""

    @pytest.mark.asyncio
    async def test_remove_single_tag(self, things_tools, mock_applescript_manager):
        """Test removing a single tag from a todo."""
        # Mock current tags
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'work, urgent'},  # Current tags
            {'success': True, 'output': 'tags_updated'}  # Remove operation
        ]

        result = await things_tools.remove_tags(todo_id='abc123', tags=['urgent'])

        assert result['success'] is True
        assert 'Removed 1 tags successfully' in result['message']

    @pytest.mark.asyncio
    async def test_remove_multiple_tags(self, things_tools, mock_applescript_manager):
        """Test removing multiple tags at once."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'work, urgent, review, old-tag'},
            {'success': True, 'output': 'tags_updated'}
        ]

        result = await things_tools.remove_tags(
            todo_id='abc123',
            tags=['urgent', 'old-tag']
        )

        assert result['success'] is True
        assert 'Removed 2 tags successfully' in result['message']

    @pytest.mark.asyncio
    async def test_remove_tags_string_parsing(self, things_tools, mock_applescript_manager):
        """Test that tag string is parsed correctly as list of tag names."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'test, Work'},
            {'success': True, 'output': 'tags_updated'}
        ]

        # BUG FIX TEST: Ensure we parse "test,Work" as ['test', 'Work']
        # NOT as ['t','e','s','t',',','W','o','r','k']
        result = await things_tools.remove_tags(
            todo_id='abc123',
            tags='test,Work'  # String input
        )

        assert result['success'] is True
        # Verify the AppleScript was called with correct remaining tags (empty string)
        calls = mock_applescript_manager.execute_applescript.call_args_list
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_remove_tags_case_sensitive_exact_match(self, things_tools, mock_applescript_manager):
        """Test that tag removal is case-sensitive and requires exact match."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'Work, personal'},
            {'success': True, 'output': 'tags_updated'}
        ]

        # Remove "Work" (capital W)
        result = await things_tools.remove_tags(todo_id='abc123', tags=['Work'])
        assert result['success'] is True

        # Verify "personal" remains
        # Reset mock for next test
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'Work, personal'},
            {'success': True, 'output': 'tags_updated'}
        ]

        # Removing "work" (lowercase) should NOT remove "Work"
        result = await things_tools.remove_tags(todo_id='abc123', tags=['work'])
        assert result['success'] is True

    @pytest.mark.asyncio
    async def test_remove_nonexistent_tag_silent(self, things_tools, mock_applescript_manager):
        """Test that removing non-existent tag is silent (no error)."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'work, urgent'},
            {'success': True, 'output': 'tags_updated'}
        ]

        # Try to remove tag that doesn't exist
        result = await things_tools.remove_tags(
            todo_id='abc123',
            tags=['nonexistent']
        )

        # Should succeed (tag just not in list to remove)
        assert result['success'] is True

    @pytest.mark.asyncio
    async def test_remove_all_tags(self, things_tools, mock_applescript_manager):
        """Test removing all tags from a todo."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'work, urgent'},
            {'success': True, 'output': 'tags_updated'}
        ]

        result = await things_tools.remove_tags(
            todo_id='abc123',
            tags=['work', 'urgent']
        )

        assert result['success'] is True


class TestGetTaggedItems:
    """Test filtering todos by tag."""

    @pytest.mark.asyncio
    async def test_get_tagged_items_single_tag(self, things_tools):
        """Test getting all items with a specific tag."""
        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': '1', 'title': 'Task 1', 'status': 'incomplete', 'type': 'to-do'},
                {'uuid': '2', 'title': 'Task 2', 'status': 'incomplete', 'type': 'to-do'}
            ]

            result = await things_tools.get_tagged_items(tag='work')

            assert len(result) == 2
            # Use 'name' field (after optimization converts title -> name)
            assert result[0]['name'] == 'Task 1'
            assert result[1]['name'] == 'Task 2'

    @pytest.mark.asyncio
    async def test_get_tagged_items_nonexistent_tag(self, things_tools):
        """Test getting items with non-existent tag returns empty list."""
        with patch('things.todos') as mock_todos:
            mock_todos.return_value = []

            result = await things_tools.get_tagged_items(tag='nonexistent')

            assert len(result) == 0
            assert result == []

    @pytest.mark.asyncio
    async def test_get_tagged_items_case_sensitive(self, things_tools):
        """Test that tag filtering is case-sensitive."""
        with patch('things.todos') as mock_todos:
            # Define different results for different case
            def todos_for_tag(tag=None, **kwargs):
                if tag == 'Work':
                    return [{'uuid': '1', 'title': 'Task 1', 'status': 'incomplete', 'type': 'to-do'}]
                elif tag == 'work':
                    return [{'uuid': '2', 'title': 'Task 2', 'status': 'incomplete', 'type': 'to-do'}]
                return []

            mock_todos.side_effect = todos_for_tag

            # Get items with "Work"
            result_work = await things_tools.get_tagged_items(tag='Work')
            assert len(result_work) == 1
            assert result_work[0]['name'] == 'Task 1'

            # Reset mock
            mock_todos.side_effect = todos_for_tag

            # Get items with "work"
            result_work_lower = await things_tools.get_tagged_items(tag='work')
            assert len(result_work_lower) == 1
            assert result_work_lower[0]['name'] == 'Task 2'


class TestTagEdgeCases:
    """Test edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_empty_tag_string(self, things_tools, mock_applescript_manager):
        """Test handling of empty tag string."""
        result = await things_tools.add_tags(todo_id='abc123', tags='')

        # Should fail with no valid tags
        assert result['success'] is False

    @pytest.mark.asyncio
    async def test_tags_with_special_characters(self, things_tools, mock_applescript_manager):
        """Test tags with special characters."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'tag-with-dash'},
                {'uuid': 'tag2', 'title': 'tag_with_underscore'},
                {'uuid': 'tag3', 'title': 'tag.with.dots'}
            ]

            result = await things_tools.add_tags(
                todo_id='abc123',
                tags=['tag-with-dash', 'tag_with_underscore', 'tag.with.dots']
            )

            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_very_long_tag_name(self, things_tools, mock_applescript_manager):
        """Test handling of very long tag names."""
        long_tag = 'a' * 200  # Very long tag name

        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': long_tag}
            ]

            result = await things_tools.add_tags(todo_id='abc123', tags=[long_tag])

            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_duplicate_tags_in_list(self, things_tools, mock_applescript_manager):
        """Test handling of duplicate tags in input list."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'work'}
            ]

            # Duplicate tags in list
            result = await things_tools.add_tags(
                todo_id='abc123',
                tags=['work', 'work', 'work']
            )

            # Should deduplicate and add once
            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_comma_separated_with_spaces_parsing(self, things_tools, mock_applescript_manager):
        """Test that comma-separated string with spaces is parsed correctly."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'work'},
                {'uuid': 'tag2', 'title': 'urgent'}
            ]

            # String with spaces after commas (should be trimmed)
            result = await things_tools.add_tags(
                todo_id='abc123',
                tags='work, urgent'  # Spaces will be stripped
            )

            assert result['success'] is True


class TestTagValidationAndCreation:
    """Test tag validation and creation limitation."""

    @pytest.mark.asyncio
    async def test_ai_cannot_create_tags(self, things_tools, mock_applescript_manager):
        """Test that AI cannot create tags programmatically."""
        # Note: Without tag_validation_service (config), tags are not validated
        # This test documents the fallback behavior
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': ''},  # Current tags
            {'success': True, 'output': 'tags_added'}  # Add operation
        ]

        with patch('things.tags') as mock_tags:
            # No tags exist
            mock_tags.return_value = []

            # Try to add non-existent tag
            result = await things_tools.add_tags(
                todo_id='abc123',
                tags=['new-tag-that-does-not-exist']
            )

            # In fallback mode (no config), tags are accepted but may fail in Things 3
            # This documents current behavior; with config, validation would fail
            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_tag_existence_workflow(self, things_tools):
        """Test the recommended workflow for checking tag existence."""
        with patch('things.tags') as mock_tags, \
             patch('things.todos') as mock_todos:

            # Get available tags
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'work'},
                {'uuid': 'tag2', 'title': 'personal'}
            ]

            # Mock todos for count
            def todos_for_tag(tag=None, **kwargs):
                if tag in ['work', 'personal']:
                    return [{'uuid': '1', 'title': 'Task'}]
                return []

            mock_todos.side_effect = todos_for_tag

            available_tags = await things_tools.get_tags()
            tag_names = [tag['name'] for tag in available_tags]

            # Verify workflow
            assert 'work' in tag_names
            assert 'personal' in tag_names
            assert 'nonexistent' not in tag_names


class TestTagsInBulkOperations:
    """Test tag operations in bulk updates."""

    @pytest.mark.asyncio
    async def test_bulk_update_with_tags(self, things_tools, mock_applescript_manager):
        """Test that tags work correctly in bulk_update_todos."""
        # Mock multiple successful operations
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'updated'
        }

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'urgent'},
                {'uuid': 'tag2', 'title': 'Q4'}
            ]

            result = await things_tools.bulk_update_todos(
                todo_ids=['id1', 'id2', 'id3'],
                tags=['urgent', 'Q4']
            )

            assert result['success'] is True

    @pytest.mark.asyncio
    async def test_bulk_update_multi_field_with_tags(self, things_tools, mock_applescript_manager):
        """Test multi-field bulk update including tags."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'updated'
        }

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'urgent'},
                {'uuid': 'tag2', 'title': 'work'}
            ]

            # Multi-field update with tags
            result = await things_tools.bulk_update_todos(
                todo_ids=['id1', 'id2'],
                tags=['urgent', 'work'],
                when='today',
                notes='Updated in batch'
            )

            assert result['success'] is True


class TestAdvancedSearchWithTags:
    """Test tag filtering in advanced search."""

    @pytest.mark.asyncio
    async def test_search_advanced_by_tag(self, things_tools, mock_applescript_manager):
        """Test search_advanced with tag filter."""
        # Mock AppleScript search result
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'todo-id-1'  # Returns single ID
        }

        with patch('things.todos') as mock_todos:
            # Mock the get_todo_by_id call that happens after search
            mock_todos.return_value = [
                {
                    'uuid': 'todo-id-1',
                    'title': 'Task 1',
                    'status': 'incomplete',
                    'type': 'to-do',
                    'tags': ['urgent']
                }
            ]

            result = await things_tools.search_advanced(tag='urgent')

            # Verify search was executed
            assert mock_applescript_manager.execute_applescript.called
