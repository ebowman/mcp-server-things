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
            assert results[0].get('error') is True
            assert 'bogus-type' in results[0].get('message', '')
