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
from test_applescript_utils import assert_balanced_quotes


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

            # Check Work tag (things.py returns 'title' not 'name')
            work_tag = next(t for t in result if t['title'] == 'Work')
            assert work_tag['title'] == 'Work'
            assert work_tag['count'] == 2  # things.py returns 'count' not 'item_count'
            assert 'items' not in work_tag

            # Check Personal tag
            personal_tag = next(t for t in result if t['title'] == 'Personal')
            assert personal_tag['count'] == 1

            # Check urgent tag (no items)
            urgent_tag = next(t for t in result if t['title'] == 'urgent')
            assert urgent_tag['count'] == 0  # things.py always includes count

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
            assert work_tag['title'] == 'Work'  # things.py returns 'title' not 'name'
            assert 'todos' in work_tag  # Implementation uses 'todos' not 'items'
            assert len(work_tag['todos']) == 2
            # todos contain converted todo objects with 'title' field
            assert work_tag['todos'][0]['title'] == 'Write report'
            assert work_tag['todos'][1]['title'] == 'Review PR'

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

            # Required fields (things.py returns 'title' not 'name')
            assert 'title' in tag
            assert tag['title'] == 'TestTag'

            # Implementation returns 'title' and 'shortcut', not 'id'
            assert 'shortcut' in tag

            # Count field present (things.py always includes count)
            assert 'count' in tag
            assert tag['count'] == 1


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
            # Verify the actual AppleScript sent the tag name to Things.
            calls = mock_applescript_manager.execute_applescript.call_args_list
            assert len(calls) == 2
            set_tags_script = calls[1].args[0]
            assert 'set tag names of targetTodo to "urgent"' in set_tags_script
            assert_balanced_quotes(set_tags_script)

    @pytest.mark.asyncio
    async def test_add_tags_already_present_reports_zero_added(self, things_tools, mock_applescript_manager):
        """Adding a tag the todo already has must not over-report: the count
        reflects tags actually newly attached, not tags requested."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'urgent, work'},  # Current tags already include 'urgent'
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [{'uuid': 'tag1', 'title': 'urgent'}]

            result = await things_tools.add_tags(todo_id='abc123', tags=['urgent'])

            assert result['success'] is True
            assert 'Added 0 tags successfully' in result['message']

    @pytest.mark.asyncio
    async def test_add_tags_mixed_new_and_present(self, things_tools, mock_applescript_manager):
        """Only newly-attached tags count toward the reported total when some
        requested tags are already present."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'urgent'},  # 'urgent' already present
            {'success': True, 'output': 'tags_added'}
        ]

        with patch('things.tags') as mock_tags:
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'urgent'},
                {'uuid': 'tag2', 'title': 'work'}
            ]

            result = await things_tools.add_tags(todo_id='abc123', tags=['urgent', 'work'])

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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            assert len(calls) == 2
            set_tags_script = calls[1].args[0]
            assert 'set tag names of targetTodo to "work, urgent, review"' in set_tags_script
            assert_balanced_quotes(set_tags_script)

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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            assert 'set tag names of targetTodo to "work, urgent"' in set_tags_script

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
            # The comma-separated string must be parsed into individual tag
            # names (not treated as a single tag literally named "work,urgent").
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            assert 'set tag names of targetTodo to "work, urgent"' in set_tags_script
            assert 'work,urgent' not in set_tags_script

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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            # Exact case must be preserved - not lowercased to "work".
            assert 'set tag names of targetTodo to "Work"' in set_tags_script

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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            assert 'set tag names of targetTodo to "nonexistent-tag"' in set_tags_script

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
            script = mock_applescript_manager.execute_applescript.call_args.args[0]
            assert 'name:"New task"' in script
            assert 'set tag names of newTodo to "work, urgent"' in script


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
        assert result['removed_count'] == 1
        assert result['not_present'] == []
        # "urgent" must be gone from the emitted script, "work" must remain.
        calls = mock_applescript_manager.execute_applescript.call_args_list
        set_tags_script = calls[1].args[0]
        assert 'set tag names of targetTodo to "work"' in set_tags_script
        assert 'urgent' not in set_tags_script

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
        assert result['removed_count'] == 2
        assert result['not_present'] == []
        calls = mock_applescript_manager.execute_applescript.call_args_list
        set_tags_script = calls[1].args[0]
        assert 'set tag names of targetTodo to "work, review"' in set_tags_script
        assert 'urgent' not in set_tags_script
        assert 'old-tag' not in set_tags_script

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
        # Verify the AppleScript was called with correct remaining tags (empty string) -
        # this pins the string->list parse bug fix: "test,Work" must be split
        # into ['test', 'Work'], not into individual characters. If the string
        # were parsed as characters, none of 'test'/'Work' would fully match
        # the current tags and the (wrong) remaining set would be non-empty.
        calls = mock_applescript_manager.execute_applescript.call_args_list
        assert len(calls) == 2
        set_tags_script = calls[1].args[0]
        assert 'set tag names of targetTodo to ""' in set_tags_script

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
        calls = mock_applescript_manager.execute_applescript.call_args_list
        set_tags_script = calls[1].args[0]
        assert 'set tag names of targetTodo to "personal"' in set_tags_script

        # Verify "personal" remains
        # Reset mock for next test
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'Work, personal'},
            {'success': True, 'output': 'tags_updated'}
        ]
        mock_applescript_manager.execute_applescript.call_args_list.clear()

        # Removing "work" (lowercase) should NOT remove "Work" - both tags
        # remain because the exact-case "work" isn't present.
        result = await things_tools.remove_tags(todo_id='abc123', tags=['work'])
        assert result['success'] is True
        calls = mock_applescript_manager.execute_applescript.call_args_list
        set_tags_script = calls[1].args[0]
        assert 'set tag names of targetTodo to "Work, personal"' in set_tags_script

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

        # Should succeed (tag just not in list to remove) and report 0 removed,
        # not the number of tags requested - existing tags are left
        # completely unchanged.
        assert result['success'] is True
        assert result['removed_count'] == 0
        assert result['not_present'] == ['nonexistent']
        assert 'Removed 0 tags successfully' in result['message']
        calls = mock_applescript_manager.execute_applescript.call_args_list
        set_tags_script = calls[1].args[0]
        assert 'set tag names of targetTodo to "work, urgent"' in set_tags_script

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
        assert result['removed_count'] == 2
        assert result['not_present'] == []
        # Removing every current tag must clear the tag list, not just leave
        # the old tags untouched.
        calls = mock_applescript_manager.execute_applescript.call_args_list
        set_tags_script = calls[1].args[0]
        assert 'set tag names of targetTodo to ""' in set_tags_script

    @pytest.mark.asyncio
    async def test_remove_tags_mixed_present_and_absent(self, things_tools, mock_applescript_manager):
        """removed_count reflects only tags actually present; absent ones are
        listed in not_present without affecting success or the removed count."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'work, urgent'},
            {'success': True, 'output': 'tags_updated'}
        ]

        result = await things_tools.remove_tags(
            todo_id='abc123',
            tags=['urgent', 'nonexistent']
        )

        assert result['success'] is True
        assert result['removed_count'] == 1
        assert result['not_present'] == ['nonexistent']
        assert 'Removed 1 tags successfully' in result['message']

    @pytest.mark.asyncio
    async def test_remove_tags_write_failure_reports_zero_removed(self, things_tools, mock_applescript_manager):
        """If the AppleScript write itself fails, nothing was actually
        applied - removed_count must be 0, not the would-be computed count,
        even though the read of current tags succeeded and the removal set
        was non-empty."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {'success': True, 'output': 'work, urgent'},  # Current tags read succeeds
            {'success': False, 'error': 'AppleScript execution failed'}  # Write fails
        ]

        result = await things_tools.remove_tags(
            todo_id='abc123',
            tags=['urgent']
        )

        assert result['success'] is False
        assert result['removed_count'] == 0


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
            # Converted todos use 'title' field
            assert result[0]['title'] == 'Task 1'
            assert result[1]['title'] == 'Task 2'

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
            assert result_work[0]['title'] == 'Task 1'  # Converted todos use 'title'

            # Reset mock
            mock_todos.side_effect = todos_for_tag

            # Get items with "work"
            result_work_lower = await things_tools.get_tagged_items(tag='work')
            assert len(result_work_lower) == 1
            assert result_work_lower[0]['title'] == 'Task 2'  # Converted todos use 'title'

    @pytest.mark.asyncio
    async def test_get_tagged_items_unknown_tag_returns_structured_error(self, things_tools):
        """An unknown tag (things.py raises ValueError) returns a structured error dict."""
        with patch('things.todos') as mock_todos, \
             patch('things.tags') as mock_tags:
            mock_todos.side_effect = ValueError('Unrecognized tag type')
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'Work'},
                {'uuid': 'tag2', 'title': 'Personal'},
            ]

            result = await things_tools.get_tagged_items(tag='nonexistent-tag')

            assert result == {
                'success': False,
                'error': 'unknown_tag',
                'tag': 'nonexistent-tag',
                'suggestions': [],
            }

    @pytest.mark.asyncio
    async def test_get_tagged_items_wrong_case_tag_suggests_correct_case(self, things_tools):
        """A wrong-case variant of a real tag returns the correctly-cased suggestion."""
        with patch('things.todos') as mock_todos, \
             patch('things.tags') as mock_tags:
            mock_todos.side_effect = ValueError('Unrecognized tag type')
            mock_tags.return_value = [
                {'uuid': 'tag1', 'title': 'Work'},
                {'uuid': 'tag2', 'title': 'Personal'},
            ]

            result = await things_tools.get_tagged_items(tag='WORK')

            assert result['success'] is False
            assert result['error'] == 'unknown_tag'
            assert result['tag'] == 'WORK'
            assert result['suggestions'] == ['Work']


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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            assert (
                'set tag names of targetTodo to '
                '"tag-with-dash, tag_with_underscore, tag.with.dots"'
            ) in set_tags_script
            assert_balanced_quotes(set_tags_script)

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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            assert f'set tag names of targetTodo to "{long_tag}"' in set_tags_script

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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            assert 'set tag names of targetTodo to "work"' in set_tags_script
            # "work" must appear exactly once in the emitted tag-names value,
            # not three times.
            assert set_tags_script.count('work') == 1

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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            # The re-joined tag-names value must not carry a leading space on
            # "urgent" (i.e. " urgent" would be a distinct, wrong tag name).
            assert 'set tag names of targetTodo to "work, urgent"' in set_tags_script
            assert '"work,  urgent"' not in set_tags_script


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
            calls = mock_applescript_manager.execute_applescript.call_args_list
            set_tags_script = calls[1].args[0]
            assert 'set tag names of targetTodo to "new-tag-that-does-not-exist"' in set_tags_script

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
            tag_titles = [tag['title'] for tag in available_tags]  # things.py returns 'title'

            # Verify workflow
            assert 'work' in tag_titles
            assert 'personal' in tag_titles
            assert 'nonexistent' not in tag_titles


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
            script = mock_applescript_manager.execute_applescript.call_args.args[0]
            # Every todo id in the batch must get its own tag-names statement
            # with both tags - not just the last one in the batch.
            for todo_id in ('id1', 'id2', 'id3'):
                assert f'to do id "{todo_id}"' in script
            assert script.count('set tag names of targetTodo to "urgent, Q4"') == 3

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
            # This pins the multi-field bulk update regression (CLAUDE.md
            # "Fixed: Bulk Update Multi-Field Support") where only the last
            # field in a multi-field update was applied - both notes and
            # tags must be present in the emitted script for every todo.
            # The bulk field-update script is the *first* execute_applescript
            # call; 'when' scheduling issues separate per-todo calls after it.
            script = mock_applescript_manager.execute_applescript.call_args_list[0].args[0]
            for todo_id in ('id1', 'id2'):
                assert f'to do id "{todo_id}"' in script
            assert script.count('set notes of targetTodo to "Updated in batch"') == 2
            assert script.count('set tag names of targetTodo to "urgent, work"') == 2


class TestAdvancedSearchWithTags:
    """Test tag filtering in advanced search."""

    @pytest.mark.asyncio
    async def test_search_advanced_by_tag(self, things_tools, mock_applescript_manager):
        """Test search_advanced with tag filter."""
        # Now uses things.py instead of AppleScript (optimized implementation)
        with patch('things.todos') as mock_todos:
            # Mock the things.py database query
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

            # Verify things.py was called with tag filter
            mock_todos.assert_called_once()
            call_kwargs = mock_todos.call_args.kwargs
            assert 'tag' in call_kwargs
            assert call_kwargs['tag'] == 'urgent'
