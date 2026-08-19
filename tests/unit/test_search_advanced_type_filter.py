"""Tests for the search_advanced 'type' filter bug fix.

Regression test for: things.api.tasks() got multiple values for keyword
argument 'type'.

Root cause:
    ReadOperations._search_advanced_sync built a query_params dict that
    could include 'type', then always called things.todos(**query_params).
    things.todos() is a thin wrapper: tasks(uuid=uuid, type="to-do", **kwargs).
    When query_params already contained 'type', things.todos() raised a
    TypeError (duplicate keyword argument) because things.py passes both
    its own hardcoded type="to-do" and the caller-supplied type.

Fix:
    When the caller supplies a 'type' filter, call things.tasks(**query_params)
    directly instead of things.todos(**query_params). Also validate 'type'
    against the values things.py's tasks() accepts before making the call,
    returning a structured error for invalid values.
"""

import pytest
from unittest.mock import MagicMock, patch

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    return MagicMock(spec=AppleScriptManager)


@pytest.fixture
def tools(mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


SAMPLE_TODO = {
    'uuid': 'todo-1',
    'title': 'Sample To-Do',
    'notes': '',
    'type': 'to-do',
}

SAMPLE_PROJECT = {
    'uuid': 'proj-1',
    'title': 'Sample Project',
    'notes': '',
    'type': 'project',
}


class TestSearchAdvancedTypeFilter:
    """Verify search_advanced correctly handles the 'type' filter."""

    @pytest.mark.asyncio
    async def test_type_to_do_calls_things_tasks(self, tools):
        """type='to-do' should call things.tasks(type='to-do', ...) and not raise."""
        with patch('things_mcp.tools_helpers.read_operations.things.tasks') as mock_tasks, \
                patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_tasks.return_value = [SAMPLE_TODO]

            results = await tools.search_advanced(type='to-do')

            mock_tasks.assert_called_once()
            _, kwargs = mock_tasks.call_args
            assert kwargs.get('type') == 'to-do'
            mock_todos.assert_not_called()
            assert len(results) == 1
            assert 'error' not in results[0]

    @pytest.mark.asyncio
    async def test_type_project_calls_things_tasks(self, tools):
        """type='project' should call things.tasks(type='project', ...) and not raise."""
        with patch('things_mcp.tools_helpers.read_operations.things.tasks') as mock_tasks, \
                patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_tasks.return_value = [SAMPLE_PROJECT]

            results = await tools.search_advanced(type='project')

            mock_tasks.assert_called_once()
            _, kwargs = mock_tasks.call_args
            assert kwargs.get('type') == 'project'
            mock_todos.assert_not_called()
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_no_type_uses_things_todos(self, tools):
        """No 'type' filter should preserve the existing things.todos() path."""
        with patch('things_mcp.tools_helpers.read_operations.things.tasks') as mock_tasks, \
                patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_todos.return_value = [SAMPLE_TODO]

            results = await tools.search_advanced(tag='urgent')

            mock_todos.assert_called_once()
            _, kwargs = mock_todos.call_args
            assert 'type' not in kwargs
            mock_tasks.assert_not_called()
            assert len(results) == 1

    @pytest.mark.asyncio
    async def test_invalid_type_returns_structured_error(self, tools):
        """An invalid type value should not reach things.py; a structured error is returned."""
        with patch('things_mcp.tools_helpers.read_operations.things.tasks') as mock_tasks, \
                patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            results = await tools.search_advanced(type='bogus-type')

            mock_tasks.assert_not_called()
            mock_todos.assert_not_called()
            assert len(results) == 1
            assert results[0].get('success') is False
            assert results[0].get('error') == 'invalid_parameter'
            assert 'bogus-type' in results[0].get('message', '')

    @pytest.mark.asyncio
    async def test_unknown_tag_returns_structured_error(self, tools):
        """An unknown/wrong-case tag (things.py raises ValueError) returns a structured error."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos, \
                patch('things_mcp.tools_helpers.read_operations.things.tags') as mock_tags:
            mock_todos.side_effect = ValueError('Unrecognized tag type')
            mock_tags.return_value = [{'uuid': 'tag1', 'title': 'llm-wiki'}]

            results = await tools.search_advanced(tag='LLM-WIKI')

            assert len(results) == 1
            assert results[0] == {
                'success': False,
                'error': 'unknown_tag',
                'message': "Unknown tag 'LLM-WIKI'. Did you mean: llm-wiki?",
                'tag': 'LLM-WIKI',
                'suggestions': ['llm-wiki'],
            }

    @pytest.mark.asyncio
    async def test_unknown_tag_with_no_matches_returns_empty_suggestions(self, tools):
        """An unknown tag with no case-insensitive match returns an empty suggestions list."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos, \
                patch('things_mcp.tools_helpers.read_operations.things.tags') as mock_tags:
            mock_todos.side_effect = ValueError('Unrecognized tag type')
            mock_tags.return_value = [{'uuid': 'tag1', 'title': 'Work'}]

            results = await tools.search_advanced(tag='totally-nonexistent')

            assert len(results) == 1
            assert results[0]['success'] is False
            assert results[0]['error'] == 'unknown_tag'
            assert results[0]['suggestions'] == []

    @pytest.mark.asyncio
    async def test_value_error_without_tag_filter_is_not_treated_as_unknown_tag(self, tools):
        """A ValueError from things.py with no `tag` filter falls through to the generic handler."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_todos.side_effect = ValueError('some other things.py error')

            results = await tools.search_advanced(status='incomplete')

            # No tag filter was supplied, so this must not be reinterpreted as
            # an unknown_tag error - it surfaces as a structured
            # invalid_parameter error instead of the empty-list fallback.
            assert len(results) == 1
            assert results[0]['success'] is False
            assert results[0]['error'] == 'invalid_parameter'
            assert 'some other things.py error' in results[0]['message']

    @pytest.mark.asyncio
    async def test_tag_plus_bad_start_date_is_not_treated_as_unknown_tag(self, tools):
        """hq-f0w.18: a *valid* tag combined with an invalid start_date must not
        be misreported as unknown_tag - things.py's own ValueError for a bad
        start_date/deadline doesn't mention 'Unrecognized tag type', so the
        tag-specific short-circuit must not swallow it."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos, \
                patch('things_mcp.tools_helpers.read_operations.things.tags') as mock_tags:
            mock_todos.side_effect = ValueError(
                "Invalid start_date argument: '2024-1-5'\n"
                "Please see the documentation for `start_date` in `things.tasks`."
            )

            results = await tools.search_advanced(tag='llm-wiki', start_date='2024-1-5')

            assert len(results) == 1
            assert results[0]['success'] is False
            assert results[0]['error'] == 'invalid_parameter'
            assert results[0]['error'] != 'unknown_tag'
            assert '2024-1-5' in results[0]['message']
            # Must not have consulted things.tags() for suggestions - this
            # never took the unknown-tag path.
            mock_tags.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_tag_still_reported_as_unknown_tag_with_other_filters(self, tools):
        """Sanity check: a genuinely unknown tag combined with other filters is
        still reported as unknown_tag (not swallowed by the new guard)."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos, \
                patch('things_mcp.tools_helpers.read_operations.things.tags') as mock_tags:
            mock_todos.side_effect = ValueError("Unrecognized tag type: 'LLM-WIKI'")
            mock_tags.return_value = [{'uuid': 'tag1', 'title': 'llm-wiki'}]

            results = await tools.search_advanced(tag='LLM-WIKI', start_date='2025-01-01')

            assert len(results) == 1
            assert results[0]['success'] is False
            assert results[0]['error'] == 'unknown_tag'
            assert results[0]['tag'] == 'LLM-WIKI'
            assert results[0]['suggestions'] == ['llm-wiki']
