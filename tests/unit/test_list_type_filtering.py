"""Tests for type filtering (to-do/project/heading) on list-based read tools.

Design decision (GH#9 items 1-2 + sweep C6): headings are NEVER returned by
get_inbox/get_today/get_upcoming/get_anytime/get_someday/get_trash. Projects
are excluded by default and opt-in via include_projects=True (inbox has no
flag - it can never contain projects). These tests mock the things.py list
functions to return a mix of to-do/project/heading dicts and verify:
  - the things.<list>() call is made with type='to-do' by default (filtering
    happens in the query, not only post-hoc)
  - default responses never contain type 'project' or 'heading'
  - include_projects=True includes projects but still excludes headings
"""

import pytest
from unittest.mock import patch

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager
from unittest.mock import MagicMock

from fixtures.things_realistic import REALISTIC_MIXED_LIST


TODO = {'uuid': 'todo-1', 'title': 'A todo', 'type': 'to-do', 'status': 'incomplete'}
PROJECT = {'uuid': 'proj-1', 'title': 'A project', 'type': 'project', 'status': 'incomplete'}
HEADING = {'uuid': 'head-1', 'title': 'A heading', 'type': 'heading'}
MIXED = [TODO, PROJECT, HEADING]


@pytest.fixture
def mock_applescript_manager():
    manager = MagicMock(spec=AppleScriptManager)
    return manager


@pytest.fixture
def tools(mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


def _uuids(items):
    return {item['uuid'] for item in items}


# ============================================================================
# get_inbox - no include_projects flag; inbox can never contain projects
# ============================================================================

@pytest.mark.asyncio
async def test_get_inbox_default_type_filter_called(tools):
    """things.inbox() is called with type='to-do' (query-level filtering)."""
    with patch('things_mcp.tools_helpers.read_operations.things.inbox',
               return_value=[TODO]) as mock_inbox:
        result = await tools.get_inbox()
        mock_inbox.assert_called_once_with(type='to-do')
        assert _uuids(result) == {'todo-1'}


@pytest.mark.asyncio
async def test_get_inbox_excludes_project_and_heading_defensively(tools):
    """Even if a mock/old things.py ignores type=, project/heading are filtered post-hoc."""
    with patch('things_mcp.tools_helpers.read_operations.things.inbox', return_value=MIXED):
        result = await tools.get_inbox()
        uuids = _uuids(result)
        assert 'proj-1' not in uuids
        assert 'head-1' not in uuids
        assert 'todo-1' in uuids


# ============================================================================
# get_today
# ============================================================================

@pytest.mark.asyncio
async def test_get_today_default_type_filter_called(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.today',
               return_value=[TODO]) as mock_today:
        await tools.get_today()
        mock_today.assert_called_once_with(type='to-do')


@pytest.mark.asyncio
async def test_get_today_default_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.today', return_value=MIXED):
        result = await tools.get_today()
        uuids = _uuids(result)
        assert uuids == {'todo-1'}


@pytest.mark.asyncio
async def test_get_today_include_projects_true(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.today',
               return_value=MIXED) as mock_today:
        result = await tools.get_today(include_projects=True)
        mock_today.assert_called_once_with()
        uuids = _uuids(result)
        assert 'proj-1' in uuids
        assert 'head-1' not in uuids
        assert 'todo-1' in uuids


# ============================================================================
# get_upcoming
# ============================================================================

@pytest.mark.asyncio
async def test_get_upcoming_default_type_filter_called(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.upcoming',
               return_value=[TODO]) as mock_upcoming:
        await tools.get_upcoming()
        mock_upcoming.assert_called_once_with(type='to-do')


@pytest.mark.asyncio
async def test_get_upcoming_default_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.upcoming', return_value=MIXED):
        result = await tools.get_upcoming()
        assert _uuids(result) == {'todo-1'}


@pytest.mark.asyncio
async def test_get_upcoming_include_projects_true(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.upcoming',
               return_value=MIXED) as mock_upcoming:
        result = await tools.get_upcoming(include_projects=True)
        mock_upcoming.assert_called_once_with()
        uuids = _uuids(result)
        assert 'proj-1' in uuids
        assert 'head-1' not in uuids


# ============================================================================
# get_anytime
# ============================================================================

@pytest.mark.asyncio
async def test_get_anytime_default_type_filter_called(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.anytime',
               return_value=[TODO]) as mock_anytime:
        await tools.get_anytime()
        mock_anytime.assert_called_once_with(type='to-do')


@pytest.mark.asyncio
async def test_get_anytime_default_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.anytime', return_value=MIXED):
        result = await tools.get_anytime()
        assert _uuids(result) == {'todo-1'}


@pytest.mark.asyncio
async def test_get_anytime_include_projects_true(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.anytime',
               return_value=MIXED) as mock_anytime:
        result = await tools.get_anytime(include_projects=True)
        mock_anytime.assert_called_once_with()
        uuids = _uuids(result)
        assert 'proj-1' in uuids
        assert 'head-1' not in uuids


# ============================================================================
# get_someday
# ============================================================================

@pytest.mark.asyncio
async def test_get_someday_default_type_filter_called(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.someday',
               return_value=[TODO]) as mock_someday:
        await tools.get_someday()
        mock_someday.assert_called_once_with(type='to-do')


@pytest.mark.asyncio
async def test_get_someday_default_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.someday', return_value=MIXED):
        result = await tools.get_someday()
        assert _uuids(result) == {'todo-1'}


@pytest.mark.asyncio
async def test_get_someday_include_projects_true(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.someday',
               return_value=MIXED) as mock_someday:
        result = await tools.get_someday(include_projects=True)
        mock_someday.assert_called_once_with()
        uuids = _uuids(result)
        assert 'proj-1' in uuids
        assert 'head-1' not in uuids


@pytest.mark.asyncio
async def test_get_someday_include_projects_independent_of_include_project_tasks(tools):
    """include_projects and include_project_tasks are independent flags."""
    with patch('things_mcp.tools_helpers.read_operations.things.someday',
               return_value=[TODO, PROJECT]), \
         patch('things_mcp.tools_helpers.read_operations.things.todos', return_value=[]):
        result = await tools.get_someday(include_project_tasks=True, include_projects=False)
        uuids = _uuids(result)
        assert 'proj-1' not in uuids
        assert 'todo-1' in uuids


# ============================================================================
# get_trash
# ============================================================================

@pytest.mark.asyncio
async def test_get_trash_default_type_filter_called(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.trash',
               return_value=[TODO]) as mock_trash:
        await tools.get_trash()
        mock_trash.assert_called_once_with(type='to-do')


@pytest.mark.asyncio
async def test_get_trash_default_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=MIXED):
        result = await tools.get_trash()
        uuids = _uuids(result['items'])
        assert uuids == {'todo-1'}
        assert result['total_count'] == 1


@pytest.mark.asyncio
async def test_get_trash_include_projects_true(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.trash',
               return_value=MIXED) as mock_trash:
        result = await tools.get_trash(include_projects=True)
        mock_trash.assert_called_once_with()
        uuids = _uuids(result['items'])
        assert 'proj-1' in uuids
        assert 'head-1' not in uuids
        assert result['total_count'] == 2


# ============================================================================
# Edge case: items lacking a 'type' key are treated as to-do
# ============================================================================

@pytest.mark.asyncio
async def test_missing_type_key_treated_as_todo(tools):
    untyped_todo = {'uuid': 'untyped-1', 'title': 'No type key', 'status': 'incomplete'}
    with patch('things_mcp.tools_helpers.read_operations.things.anytime',
               return_value=[untyped_todo]):
        result = await tools.get_anytime()
        assert _uuids(result) == {'untyped-1'}


# ============================================================================
# Realistic fixtures (hq-f0w.10): the minimal MIXED list above deliberately
# has exactly one row per type to keep the type-filtering assertions above
# crisp. These supplementary tests re-run the same default-exclusion checks
# against tests/fixtures/things_realistic.py's REALISTIC_MIXED_LIST, which
# carries a fuller realistic shape (headings under a Someday project,
# punctuation/notes variety, tags, checklist flags) so a project/heading
# leak can't hide behind an artificially narrow mock.
# ============================================================================

@pytest.mark.asyncio
async def test_get_today_realistic_mixed_list_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.today', return_value=REALISTIC_MIXED_LIST):
        result = await tools.get_today()
        types = {item.get('type') for item in result}
        assert 'project' not in types
        assert 'heading' not in types
        assert types == {'to-do'}


@pytest.mark.asyncio
async def test_get_anytime_realistic_mixed_list_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.anytime', return_value=REALISTIC_MIXED_LIST):
        result = await tools.get_anytime()
        types = {item.get('type') for item in result}
        assert 'project' not in types
        assert 'heading' not in types


@pytest.mark.asyncio
async def test_get_upcoming_realistic_mixed_list_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.upcoming', return_value=REALISTIC_MIXED_LIST):
        result = await tools.get_upcoming()
        types = {item.get('type') for item in result}
        assert 'project' not in types
        assert 'heading' not in types


@pytest.mark.asyncio
async def test_get_inbox_realistic_mixed_list_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.inbox', return_value=REALISTIC_MIXED_LIST):
        result = await tools.get_inbox()
        types = {item.get('type') for item in result}
        assert 'project' not in types
        assert 'heading' not in types


@pytest.mark.asyncio
async def test_get_someday_realistic_mixed_list_excludes_project_and_heading(tools):
    with patch('things_mcp.tools_helpers.read_operations.things.someday', return_value=REALISTIC_MIXED_LIST), \
         patch('things_mcp.tools_helpers.read_operations.things.projects', return_value=[]):
        result = await tools.get_someday()
        types = {item.get('type') for item in result}
        assert 'project' not in types
        assert 'heading' not in types
