"""Tests for hq-f0w.37: mixed-list project rows (get_today/get_upcoming/
get_anytime/get_someday with include_projects=True, and search_advanced)
must be converted via ToolsHelpers.convert_project - not convert_todo - so
they carry area/areaTitle. Before this fix, these call sites converted every
row (regardless of its own 'type') via convert_todo(), which never emits
area/areaTitle since to-do rows never carry them.
"""

import pytest
from unittest.mock import patch, MagicMock

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools_helpers.read_operations import convert_item
from things_mcp.tools_helpers.helpers import ToolsHelpers

from fixtures.things_realistic import make_todo, make_project


TODO_ROW = make_todo('todo-1', 'A todo')
PROJECT_ROW = make_project('proj-1', 'A project', area='area-1', area_title='Home')
HEADING_ROW = {'uuid': 'head-1', 'title': 'A heading', 'type': 'heading'}
MIXED = [TODO_ROW, PROJECT_ROW, HEADING_ROW]


@pytest.fixture
def mock_applescript_manager():
    return MagicMock(spec=AppleScriptManager)


@pytest.fixture
def tools(mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


def _by_uuid(items, uuid):
    return next(item for item in items if item['uuid'] == uuid)


class TestConvertItemDispatch:
    """Unit tests for the convert_item() helper itself."""

    def test_convert_item_project_uses_convert_project(self):
        converted = convert_item(PROJECT_ROW)
        assert converted == ToolsHelpers.convert_project(PROJECT_ROW)
        assert converted.get('area') == 'area-1'
        assert converted.get('areaTitle') == 'Home'

    def test_convert_item_todo_uses_convert_todo(self):
        converted = convert_item(TODO_ROW)
        assert converted == ToolsHelpers.convert_todo(TODO_ROW)

    def test_convert_item_heading_uses_convert_todo(self):
        """Headings never appear in these mixed lists post-filtering, but
        convert_item must still default to convert_todo for any non-project
        type, matching the pre-existing behavior for headings elsewhere."""
        converted = convert_item(HEADING_ROW)
        assert converted == ToolsHelpers.convert_todo(HEADING_ROW)

    def test_convert_item_missing_type_uses_convert_todo(self):
        row = {'uuid': 'x', 'title': 'No type key'}
        converted = convert_item(row)
        assert converted == ToolsHelpers.convert_todo(row)


class TestGetTodayProjectRowsCarryArea:
    @pytest.mark.asyncio
    async def test_project_row_has_area_and_areaTitle(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.today', return_value=MIXED):
            result = await tools.get_today(include_projects=True)
        project_row = _by_uuid(result, 'proj-1')
        assert project_row.get('area') == 'area-1'
        assert project_row.get('areaTitle') == 'Home'

    @pytest.mark.asyncio
    async def test_todo_row_unaffected(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.today', return_value=MIXED):
            result = await tools.get_today(include_projects=True)
        todo_row = _by_uuid(result, 'todo-1')
        assert todo_row == ToolsHelpers.convert_todo(TODO_ROW)


class TestGetUpcomingProjectRowsCarryArea:
    @pytest.mark.asyncio
    async def test_project_row_has_area_and_areaTitle(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.upcoming', return_value=MIXED):
            result = await tools.get_upcoming(include_projects=True)
        project_row = _by_uuid(result, 'proj-1')
        assert project_row.get('area') == 'area-1'
        assert project_row.get('areaTitle') == 'Home'


class TestGetAnytimeProjectRowsCarryArea:
    @pytest.mark.asyncio
    async def test_project_row_has_area_and_areaTitle(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.anytime', return_value=MIXED):
            result = await tools.get_anytime(include_projects=True)
        project_row = _by_uuid(result, 'proj-1')
        assert project_row.get('area') == 'area-1'
        assert project_row.get('areaTitle') == 'Home'


class TestGetSomedayProjectRowsCarryArea:
    @pytest.mark.asyncio
    async def test_project_row_has_area_and_areaTitle(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.someday', return_value=MIXED):
            result = await tools.get_someday(include_projects=True)
        project_row = _by_uuid(result, 'proj-1')
        assert project_row.get('area') == 'area-1'
        assert project_row.get('areaTitle') == 'Home'


class TestGetTrashProjectRowsCarryArea:
    @pytest.mark.asyncio
    async def test_project_row_has_area_and_areaTitle(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=MIXED):
            result = await tools.get_trash(include_projects=True)
        project_row = _by_uuid(result['items'], 'proj-1')
        assert project_row.get('area') == 'area-1'
        assert project_row.get('areaTitle') == 'Home'

    @pytest.mark.asyncio
    async def test_todo_row_unaffected(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.trash', return_value=MIXED):
            result = await tools.get_trash(include_projects=True)
        todo_row = _by_uuid(result['items'], 'todo-1')
        assert todo_row == ToolsHelpers.convert_todo(TODO_ROW)


class TestSearchAdvancedProjectRowsCarryArea:
    @pytest.mark.asyncio
    async def test_project_type_filter_returns_area(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.tasks',
                   return_value=[PROJECT_ROW]):
            result = await tools.search_advanced(type='project')
        assert len(result) == 1
        assert result[0].get('area') == 'area-1'
        assert result[0].get('areaTitle') == 'Home'

    @pytest.mark.asyncio
    async def test_unfiltered_mixed_results_convert_project_rows_correctly(self, tools):
        with patch('things_mcp.tools_helpers.read_operations.things.todos',
                   return_value=[TODO_ROW, PROJECT_ROW]):
            result = await tools.search_advanced()
        project_row = _by_uuid(result, 'proj-1')
        todo_row = _by_uuid(result, 'todo-1')
        assert project_row.get('area') == 'area-1'
        assert project_row.get('areaTitle') == 'Home'
        assert todo_row == ToolsHelpers.convert_todo(TODO_ROW)
