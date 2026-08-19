"""Tests for filtering tasks that belong to Someday projects.

Things UI hides tasks that live inside a Someday project from Today,
Anytime, and Upcoming, even when things.py reports the individual task's
own start state as today/anytime. These tests verify the filtering helper
in read_operations.py and its application in get_today/get_anytime/
get_upcoming/get_someday and the date-window variants.
"""

import pytest
from unittest.mock import MagicMock, patch

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools_helpers.read_operations import (
    filter_someday_project_tasks,
    _is_in_someday_project,
    _get_someday_project_ids,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_applescript_manager():
    manager = MagicMock(spec=AppleScriptManager)
    return manager


@pytest.fixture
def tools(mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


SOMEDAY_PROJECT = {'uuid': 'proj-someday', 'title': 'Someday Project', 'start': 'Someday'}
ANYTIME_PROJECT = {'uuid': 'proj-anytime', 'title': 'Active Project', 'start': 'Anytime'}

TASK_DIRECT_SOMEDAY = {
    'uuid': 'task-direct', 'title': 'Direct someday task',
    'project': 'proj-someday', 'status': 'incomplete'
}
TASK_HEADING_SOMEDAY = {
    'uuid': 'task-heading', 'title': 'Heading someday task',
    'heading': 'heading-1', 'status': 'incomplete'
}
TASK_ANYTIME_PROJECT = {
    'uuid': 'task-anytime', 'title': 'Task in active project',
    'project': 'proj-anytime', 'status': 'incomplete'
}
TASK_STANDALONE = {
    'uuid': 'task-standalone', 'title': 'Standalone task',
    'status': 'incomplete'
}
HEADING_IN_SOMEDAY = {'uuid': 'heading-1', 'project': 'proj-someday', 'title': 'A heading'}


# ============================================================================
# Unit tests for filter_someday_project_tasks / _is_in_someday_project
# ============================================================================

class TestFilterSomedayProjectTasks:

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_filters_task_directly_in_someday_project(self, mock_projects):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        todos = [TASK_DIRECT_SOMEDAY, TASK_ANYTIME_PROJECT, TASK_STANDALONE]

        result = filter_someday_project_tasks(todos)

        uuids = {t['uuid'] for t in result}
        assert 'task-direct' not in uuids
        assert 'task-anytime' in uuids
        assert 'task-standalone' in uuids

    @patch('things_mcp.tools_helpers.read_operations.things.get')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_filters_task_under_heading_in_someday_project(self, mock_projects, mock_get):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_get.return_value = HEADING_IN_SOMEDAY

        todos = [TASK_HEADING_SOMEDAY, TASK_STANDALONE]

        result = filter_someday_project_tasks(todos)

        uuids = {t['uuid'] for t in result}
        assert 'task-heading' not in uuids
        assert 'task-standalone' in uuids
        mock_get.assert_called_with('heading-1')

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_keeps_task_in_non_someday_project(self, mock_projects):
        mock_projects.return_value = []  # No Someday projects
        todos = [TASK_ANYTIME_PROJECT]

        result = filter_someday_project_tasks(todos)

        assert len(result) == 1
        assert result[0]['uuid'] == 'task-anytime'

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_keeps_standalone_task_without_project(self, mock_projects):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        todos = [TASK_STANDALONE]

        result = filter_someday_project_tasks(todos)

        assert len(result) == 1
        assert result[0]['uuid'] == 'task-standalone'

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_no_someday_projects_returns_input_unchanged(self, mock_projects):
        mock_projects.return_value = []
        todos = [TASK_DIRECT_SOMEDAY, TASK_STANDALONE]

        result = filter_someday_project_tasks(todos)

        assert result == todos

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_empty_list(self, mock_projects):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        assert filter_someday_project_tasks([]) == []

    # -- Defensive / missing data cases --------------------------------

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_project_lookup_exception_keeps_all_todos(self, mock_projects):
        mock_projects.side_effect = Exception("db error")
        todos = [TASK_DIRECT_SOMEDAY, TASK_STANDALONE]

        result = filter_someday_project_tasks(todos)

        assert len(result) == 2

    @patch('things_mcp.tools_helpers.read_operations.things.get')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_missing_heading_keeps_todo(self, mock_projects, mock_get):
        """A heading that no longer exists (deleted) should not crash and
        the associated todo should be kept (treated as not-Someday)."""
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_get.return_value = None  # heading not found / deleted

        todos = [TASK_HEADING_SOMEDAY]

        result = filter_someday_project_tasks(todos)

        assert len(result) == 1
        assert result[0]['uuid'] == 'task-heading'

    @patch('things_mcp.tools_helpers.read_operations.things.get')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_heading_lookup_exception_keeps_todo(self, mock_projects, mock_get):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_get.side_effect = Exception("lookup failed")

        todos = [TASK_HEADING_SOMEDAY]

        result = filter_someday_project_tasks(todos)

        assert len(result) == 1
        assert result[0]['uuid'] == 'task-heading'

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_project_missing_uuid_ignored(self, mock_projects):
        """Someday projects without a uuid key should not blow up set building."""
        mock_projects.return_value = [{'title': 'No uuid'}, SOMEDAY_PROJECT]
        todos = [TASK_DIRECT_SOMEDAY]

        result = filter_someday_project_tasks(todos)

        assert result == []

    @patch('things_mcp.tools_helpers.read_operations.things.get')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_heading_cache_avoids_repeat_lookups(self, mock_projects, mock_get):
        """Multiple todos sharing a heading should only trigger one things.get call."""
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_get.return_value = HEADING_IN_SOMEDAY

        todos = [
            {'uuid': 't1', 'heading': 'heading-1'},
            {'uuid': 't2', 'heading': 'heading-1'},
        ]

        result = filter_someday_project_tasks(todos)

        assert result == []
        assert mock_get.call_count == 1


class TestGetSomedayProjectIds:

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_returns_uuid_set(self, mock_projects):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        result = _get_someday_project_ids()
        assert result == {'proj-someday'}
        mock_projects.assert_called_once_with(start='Someday')

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_exception_returns_empty_set(self, mock_projects):
        mock_projects.side_effect = Exception("boom")
        assert _get_someday_project_ids() == set()

    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    def test_none_return_value(self, mock_projects):
        mock_projects.return_value = None
        assert _get_someday_project_ids() == set()


# ============================================================================
# Integration-style tests through ThingsTools (get_today/anytime/upcoming/someday)
# ============================================================================

class TestReadToolsApplySomedayFilter:

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.today')
    async def test_get_today_filters_someday_project_tasks(self, mock_today, mock_projects, tools):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_today.return_value = [TASK_DIRECT_SOMEDAY, TASK_ANYTIME_PROJECT, TASK_STANDALONE]

        result = await tools.get_today()

        uuids = {t['uuid'] for t in result}
        assert 'task-direct' not in uuids
        assert 'task-anytime' in uuids
        assert 'task-standalone' in uuids

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.anytime')
    async def test_get_anytime_filters_someday_project_tasks(self, mock_anytime, mock_projects, tools):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_anytime.return_value = [TASK_DIRECT_SOMEDAY, TASK_ANYTIME_PROJECT]

        result = await tools.get_anytime()

        uuids = {t['uuid'] for t in result}
        assert 'task-direct' not in uuids
        assert 'task-anytime' in uuids

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.upcoming')
    async def test_get_upcoming_filters_someday_project_tasks(self, mock_upcoming, mock_projects, tools):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_upcoming.return_value = [TASK_DIRECT_SOMEDAY, TASK_ANYTIME_PROJECT]

        result = await tools.get_upcoming()

        uuids = {t['uuid'] for t in result}
        assert 'task-direct' not in uuids
        assert 'task-anytime' in uuids

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.get')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.upcoming')
    async def test_get_upcoming_filters_heading_tasks_in_someday_project(
        self, mock_upcoming, mock_projects, mock_get, tools
    ):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_get.return_value = HEADING_IN_SOMEDAY
        mock_upcoming.return_value = [TASK_HEADING_SOMEDAY, TASK_ANYTIME_PROJECT]

        result = await tools.get_upcoming()

        uuids = {t['uuid'] for t in result}
        assert 'task-heading' not in uuids
        assert 'task-anytime' in uuids

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.todos')
    async def test_get_due_in_days_filters_someday_project_tasks(self, mock_todos, mock_projects, tools):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_todos.return_value = [TASK_DIRECT_SOMEDAY, TASK_ANYTIME_PROJECT]

        result = await tools.get_due_in_days(7)

        uuids = {t['uuid'] for t in result}
        assert 'task-direct' not in uuids
        assert 'task-anytime' in uuids

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.todos')
    async def test_get_activating_in_days_filters_someday_project_tasks(self, mock_todos, mock_projects, tools):
        from datetime import date, timedelta
        tomorrow_str = (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')
        task_direct_someday = {**TASK_DIRECT_SOMEDAY, 'start_date': tomorrow_str}
        task_anytime_project = {**TASK_ANYTIME_PROJECT, 'start_date': tomorrow_str}

        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_todos.return_value = [task_direct_someday, task_anytime_project]

        result = await tools.get_activating_in_days(7)

        uuids = {t['uuid'] for t in result}
        assert 'task-direct' not in uuids
        assert 'task-anytime' in uuids


# ============================================================================
# get_someday: inherited Someday tasks (project is Someday, but things.py
# reports the task itself as Anytime/other)
# ============================================================================

class TestGetSomedayInheritsProjectTasks:

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.someday')
    async def test_get_someday_includes_native_someday_tasks(self, mock_someday, mock_projects, tools):
        mock_projects.return_value = []
        mock_someday.return_value = [TASK_STANDALONE]

        result = await tools.get_someday()

        uuids = {t['uuid'] for t in result}
        assert uuids == {'task-standalone'}
        assert 'inheritedSomeday' not in result[0]

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.todos')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.someday')
    async def test_get_someday_default_excludes_inherited_project_tasks(
        self, mock_someday, mock_projects, mock_todos, tools
    ):
        """By default (include_project_tasks=False), get_someday() must not include
        tasks inherited from Someday projects, and must not even scan all incomplete
        todos to look for them (avoids the cost on large databases)."""
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_someday.return_value = []  # things.py doesn't report it as Someday itself

        result = await tools.get_someday()

        assert result == []
        mock_todos.assert_not_called()

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.todos')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.someday')
    async def test_get_someday_adds_inherited_project_task_with_marker(
        self, mock_someday, mock_projects, mock_todos, tools
    ):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_someday.return_value = []  # things.py doesn't report it as Someday itself
        mock_todos.return_value = [TASK_DIRECT_SOMEDAY, TASK_ANYTIME_PROJECT]

        result = await tools.get_someday(include_project_tasks=True)

        by_uuid = {t['uuid']: t for t in result}
        assert 'task-direct' in by_uuid
        assert by_uuid['task-direct'].get('inheritedSomeday') is True
        assert 'task-anytime' not in by_uuid

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.todos')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.someday')
    async def test_get_someday_dedupes_already_present_uuid(
        self, mock_someday, mock_projects, mock_todos, tools
    ):
        """If things.someday() already returned the task, it shouldn't be duplicated
        even though it also shows up in the incomplete-todos scan."""
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_someday.return_value = [TASK_DIRECT_SOMEDAY]
        mock_todos.return_value = [TASK_DIRECT_SOMEDAY]

        result = await tools.get_someday(include_project_tasks=True)

        uuids = [t['uuid'] for t in result]
        assert uuids.count('task-direct') == 1
        # Not marked inherited since it came from things.someday() directly
        assert 'inheritedSomeday' not in result[0]

    @pytest.mark.asyncio
    @patch('things_mcp.tools_helpers.read_operations.things.get')
    @patch('things_mcp.tools_helpers.read_operations.things.todos')
    @patch('things_mcp.tools_helpers.read_operations.things.projects')
    @patch('things_mcp.tools_helpers.read_operations.things.someday')
    async def test_get_someday_adds_inherited_heading_task_with_marker(
        self, mock_someday, mock_projects, mock_todos, mock_get, tools
    ):
        mock_projects.return_value = [SOMEDAY_PROJECT]
        mock_someday.return_value = []
        mock_get.return_value = HEADING_IN_SOMEDAY
        mock_todos.return_value = [TASK_HEADING_SOMEDAY]

        result = await tools.get_someday(include_project_tasks=True)

        assert len(result) == 1
        assert result[0]['uuid'] == 'task-heading'
        assert result[0].get('inheritedSomeday') is True
