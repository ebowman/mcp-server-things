"""Tests for hq-f0w.4 step 4: get_todos(project_uuid=...) AppleScript-path
best-effort enrichment with heading/headingTitle/projectTitle/start from
things.py.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock

from things_mcp.tools import ThingsTools


@pytest.fixture
def mock_things():
    """Mock the things module used by read_operations.py."""
    with patch('things_mcp.tools_helpers.read_operations.things') as mock:
        yield mock


@pytest.fixture
def mock_applescript_manager():
    manager = Mock()
    manager.execute_script = Mock(return_value="success")
    return manager


@pytest.fixture
def tools(mock_things, mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


class TestGetTodosProjectEnrichment:
    @pytest.mark.asyncio
    async def test_todo_under_heading_gets_heading_title(self, tools, mock_things, mock_applescript_manager):
        """A todo under a heading returned by get_todos(project_uuid=...)
        carries headingTitle after enrichment."""
        project_uuid = 'project-123'
        mock_applescript_manager.get_todos = AsyncMock(return_value=[
            {'id': 'todo-1', 'name': 'Look at Calendar', 'status': 'open'},
        ])
        mock_things.todos.return_value = [
            {
                'uuid': 'todo-1',
                'title': 'Look at Calendar',
                'status': 'incomplete',
                'heading': 'heading-uuid',
                'heading_title': 'Review Calendar',
                'project_title': None,
                'start': 'Anytime',
            }
        ]

        result = await tools.get_todos(project_uuid=project_uuid, status=None)

        mock_things.todos.assert_called_once_with(project=project_uuid)
        assert len(result) == 1
        assert result[0]['heading'] == 'heading-uuid'
        assert result[0]['headingTitle'] == 'Review Calendar'
        assert result[0]['start'] == 'Anytime'

    @pytest.mark.asyncio
    async def test_todo_without_matching_row_left_unenriched(self, tools, mock_things, mock_applescript_manager):
        """If a things.py row is missing for a uuid, that todo is left as-is
        (no KeyError, no crash)."""
        project_uuid = 'project-456'
        mock_applescript_manager.get_todos = AsyncMock(return_value=[
            {'id': 'todo-missing', 'name': 'Orphan Todo', 'status': 'open'},
        ])
        mock_things.todos.return_value = []  # no matching rows

        result = await tools.get_todos(project_uuid=project_uuid, status=None)

        assert len(result) == 1
        assert 'heading' not in result[0] or result[0].get('heading') is None

    @pytest.mark.asyncio
    async def test_things_py_enrichment_failure_never_fails_the_call(self, tools, mock_things, mock_applescript_manager):
        """If things.todos(project=...) raises, the AppleScript-sourced
        result is still returned unmodified rather than the whole call
        failing."""
        project_uuid = 'project-789'
        mock_applescript_manager.get_todos = AsyncMock(return_value=[
            {'id': 'todo-1', 'name': 'A Todo', 'status': 'open'},
        ])
        mock_things.todos.side_effect = RuntimeError("things.py unavailable")

        result = await tools.get_todos(project_uuid=project_uuid, status=None)

        assert len(result) == 1
        assert result[0]['uuid'] == 'todo-1'
