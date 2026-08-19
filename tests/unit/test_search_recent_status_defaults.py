"""Tests for hq-nxu.2: search_todos/search_advanced/get_recent status defaults
and empty-query rejection.

Covers:
- search_todos: new `status` param, default 'incomplete' (backward compatible),
  status=None searches all statuses, status='completed'/'canceled' work.
- search_advanced: when no status filter is given, ALL statuses are searched
  (things.todos/tasks is called with status=None, not left to its own
  'incomplete' default).
- get_recent: defaults to status=None, type=None (all statuses/types), and
  accepts optional status/type filters.
- search_todos: empty/whitespace query is rejected with a structured error
  at the server tool layer, before ever hitting things.py.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from fastmcp import Client

from things_mcp.tools import ThingsTools
from things_mcp.server import ThingsMCPServer


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


class TestSearchTodosStatusDefault:
    """search_todos gains a status param; default stays 'incomplete'."""

    @pytest.mark.asyncio
    async def test_default_status_is_incomplete(self, tools, mock_things):
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Buy milk', 'notes': '', 'status': 'incomplete'}
        ]

        result = await tools.search_todos(query='milk')

        mock_things.todos.assert_called_once_with(status='incomplete')
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_explicit_completed_status(self, tools, mock_things):
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Finished report', 'notes': '', 'status': 'completed'}
        ]

        result = await tools.search_todos(query='report', status='completed')

        mock_things.todos.assert_called_once_with(status='completed')
        assert len(result) == 1
        assert result[0]['status'] == 'completed'

    @pytest.mark.asyncio
    async def test_explicit_canceled_status(self, tools, mock_things):
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Old idea', 'notes': '', 'status': 'canceled'}
        ]

        result = await tools.search_todos(query='idea', status='canceled')

        mock_things.todos.assert_called_once_with(status='canceled')
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_status_none_searches_all(self, tools, mock_things):
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Report v1', 'notes': '', 'status': 'incomplete'},
            {'uuid': '2', 'title': 'Report v2', 'notes': '', 'status': 'completed'},
        ]

        result = await tools.search_todos(query='report', status=None)

        mock_things.todos.assert_called_once_with(status=None)
        assert len(result) == 2


class TestSearchAdvancedAllStatusesByDefault:
    """search_advanced with no status filter now searches ALL statuses."""

    @pytest.mark.asyncio
    async def test_no_status_filter_queries_status_none(self, tools, mock_things):
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Task', 'notes': '', 'status': 'incomplete'},
        ]

        await tools.search_advanced()

        # status=None must be passed explicitly so things.todos() doesn't
        # fall back to its own 'incomplete' default.
        mock_things.todos.assert_called_once_with(status=None)

    @pytest.mark.asyncio
    async def test_explicit_status_still_filters(self, tools, mock_things):
        mock_things.todos.return_value = [
            {'uuid': '1', 'title': 'Task', 'notes': '', 'status': 'completed'},
        ]

        await tools.search_advanced(status='completed')

        mock_things.todos.assert_called_once_with(status='completed')

    @pytest.mark.asyncio
    async def test_no_status_with_type_uses_tasks(self, tools, mock_things):
        mock_things.tasks.return_value = [
            {'uuid': '1', 'title': 'Project X', 'notes': '', 'status': 'completed', 'type': 'project'},
        ]

        await tools.search_advanced(type='project')

        # type filter routes through things.tasks(); status must still be
        # explicitly None so all statuses are included.
        mock_things.tasks.assert_called_once_with(status=None, type='project')


class TestGetRecentAllStatusesAndTypes:
    """get_recent defaults to all statuses/types, with optional filters."""

    @pytest.mark.asyncio
    async def test_default_includes_all_statuses_and_types(self, tools, mock_things):
        mock_things.tasks.return_value = []

        await tools.get_recent(period='7d')

        mock_things.tasks.assert_called_once_with(status=None, type=None)

    @pytest.mark.asyncio
    async def test_status_filter_passed_through(self, tools, mock_things):
        mock_things.tasks.return_value = []

        await tools.get_recent(period='7d', status='completed')

        mock_things.tasks.assert_called_once_with(status='completed', type=None)

    @pytest.mark.asyncio
    async def test_type_filter_passed_through(self, tools, mock_things):
        mock_things.tasks.return_value = []

        await tools.get_recent(period='7d', type='project')

        mock_things.tasks.assert_called_once_with(status=None, type='project')

    @pytest.mark.asyncio
    async def test_completed_todo_within_window_is_included(self, tools, mock_things):
        from datetime import datetime, timedelta

        recent_created = (datetime.now() - timedelta(days=1)).isoformat()
        mock_things.tasks.return_value = [
            {
                'uuid': '1', 'title': 'Completed task', 'notes': '',
                'status': 'completed', 'type': 'to-do', 'created': recent_created,
            },
        ]

        result = await tools.get_recent(period='7d')

        assert len(result) == 1
        assert result[0]['status'] == 'completed'

    @pytest.mark.asyncio
    async def test_project_within_window_is_included(self, tools, mock_things):
        from datetime import datetime, timedelta

        recent_created = (datetime.now() - timedelta(days=1)).isoformat()
        mock_things.tasks.return_value = [
            {
                'uuid': '1', 'title': 'New Project', 'notes': '',
                'status': 'incomplete', 'type': 'project', 'created': recent_created,
            },
        ]

        result = await tools.get_recent(period='7d')

        assert len(result) == 1
        assert result[0]['type'] == 'project'

    @pytest.mark.asyncio
    async def test_heading_within_window_is_dropped_by_default(self, tools, mock_things):
        """Epic-wide ruling (hq-f0w.3): list tools never return headings by
        default. get_recent must drop heading-type rows unless type='heading'
        was explicitly requested, even though things.tasks(type=None) itself
        returns headings mixed in with to-dos/projects."""
        from datetime import datetime, timedelta

        recent_created = (datetime.now() - timedelta(days=1)).isoformat()
        mock_things.tasks.return_value = [
            {
                'uuid': '1', 'title': 'A Heading', 'notes': '',
                'status': 'incomplete', 'type': 'heading', 'created': recent_created,
            },
            {
                'uuid': '2', 'title': 'A Todo', 'notes': '',
                'status': 'incomplete', 'type': 'to-do', 'created': recent_created,
            },
        ]

        result = await tools.get_recent(period='7d')

        assert len(result) == 1
        assert result[0]['type'] == 'to-do'

    @pytest.mark.asyncio
    async def test_heading_returned_when_type_heading_requested(self, tools, mock_things):
        """type='heading' explicitly requested must still return headings."""
        from datetime import datetime, timedelta

        recent_created = (datetime.now() - timedelta(days=1)).isoformat()
        mock_things.tasks.return_value = [
            {
                'uuid': '1', 'title': 'A Heading', 'notes': '',
                'status': 'incomplete', 'type': 'heading', 'created': recent_created,
            },
        ]

        result = await tools.get_recent(period='7d', type='heading')

        assert len(result) == 1
        assert result[0]['type'] == 'heading'


class TestSearchTodosEmptyQueryRejected:
    """search_todos rejects an empty/whitespace-only query at the server layer."""

    def _make_server_with_mock_tools(self):
        server = ThingsMCPServer()
        mock_tools = MagicMock()
        mock_tools.tag_validation_service = None
        mock_tools.search_todos = AsyncMock(return_value=[])
        server.tools = mock_tools
        return server

    @pytest.mark.asyncio
    async def test_empty_string_query_returns_structured_error(self):
        server = self._make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("search_todos", {"query": ""})

        sc = result.structured_content
        assert sc is not None
        assert sc.get("success") is False
        assert "query" in sc.get("message", "").lower()
        # Must never have reached the tools layer.
        server.tools.search_todos.assert_not_called()

    @pytest.mark.asyncio
    async def test_whitespace_only_query_returns_structured_error(self):
        server = self._make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("search_todos", {"query": "   "})

        sc = result.structured_content
        assert sc is not None
        assert sc.get("success") is False
        server.tools.search_todos.assert_not_called()

    @pytest.mark.asyncio
    async def test_nonblank_query_proceeds_normally(self):
        server = self._make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("search_todos", {"query": "milk"})

        sc = result.structured_content
        assert sc is not None
        assert "success" not in sc or sc.get("success") is not False
        server.tools.search_todos.assert_called_once()
