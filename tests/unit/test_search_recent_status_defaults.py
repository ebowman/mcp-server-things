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
from copy import deepcopy
from functools import partial
from unittest.mock import Mock, AsyncMock, MagicMock, patch

from fastmcp import Client

from fixtures.things_realistic import make_heading, make_project, make_todo
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


@pytest.fixture(params=["todos", "advanced", "to-do", "project", "heading"])
def raw_search(request, tools, mock_things):
    """Real workers; advanced query is internal, not a public MCP parameter."""
    kind = request.param
    factory = make_todo
    if kind == "project":
        factory = partial(make_project, area="area-1", area_title="Work")
    elif kind == "heading":
        factory = partial(make_heading, project="proj-1", project_title="Work")
    typed = kind not in ("todos", "advanced")
    source = mock_things.tasks if typed else mock_things.todos

    async def search(rows, query="needle", **kwargs):
        source.return_value = rows
        if kind == "todos":
            result = await tools.search_todos(query=query, **kwargs)
            expected = {"status": kwargs.get("status", "incomplete")}
        else:
            filters = {"type": kind} if typed else {}
            result = await tools.search_advanced(
                query=query, **filters, **kwargs
            )
            expected = {"status": kwargs.get("status"), **filters}
        source.assert_called_once_with(**expected)
        other = mock_things.todos if typed else mock_things.tasks
        other.assert_not_called()
        return result

    return search, factory


class TestRawRowTextSearch:
    """Normalize nullable text only while matching, not in source/output."""

    @pytest.mark.parametrize("null_first", [True, False])
    async def test_null_row_does_not_discard_matches(
        self, raw_search, null_first
    ):
        search, factory = raw_search
        null_row = factory("null", "Unrelated", notes=None)
        match = factory("match", "A Needle!", notes="Original\nnotes.")
        rows = [null_row, match] if null_first else [match, null_row]
        before = deepcopy(rows)

        result = await search(rows)

        assert [row["uuid"] for row in result] == ["match"]
        assert result.total_count == 1
        assert result[0]["notes"] == "Original\nnotes."
        assert rows == before

    @pytest.mark.parametrize(
        "fields,query,matched",
        [
            ({"title": "NEEDLE", "notes": None}, "needle", True),
            ({"title": "NEEDLE"}, "needle", True),
            ({"title": None, "notes": "A Needle!\nNext"}, "nEEdLe!\nn", True),
            ({"notes": "A Needle!\nNext"}, "nEEdLe!\nn", True),
            ({"title": "", "notes": "Needle"}, "needle", True),
            ({"title": None, "notes": None}, "needle", False),
            ({}, "needle", False),
            ({"title": "", "notes": ""}, "needle", False),
            ({"title": "other", "notes": "nothing"}, "needle", False),
            # lower(), not casefold(): don't silently broaden string matching.
            ({"title": "Straße", "notes": None}, "STRASSE", False),
        ],
    )
    async def test_nullable_fields(self, raw_search, fields, query, matched):
        search, factory = raw_search
        row = factory("row", "placeholder")
        del row["title"]
        del row["notes"]
        row.update(fields)
        before = deepcopy(row)

        result = await search([row], query=query)

        assert result.total_count == int(matched)
        assert len(result) == int(matched)
        assert row == before
        if matched:
            assert result[0]["uuid"] == "row"
            assert result[0]["type"] == row["type"]
            for field in ("title", "notes"):
                if fields.get(field) is None:
                    assert field not in result[0]
                else:
                    assert result[0][field] == fields[field]
            if row["type"] == "project":
                assert result[0]["area"] == "area-1"
                assert result[0]["areaTitle"] == "Work"
            elif row["type"] == "heading":
                assert result[0]["project"] == "proj-1"

    async def test_empty_source(self, raw_search):
        search, _ = raw_search
        result = await search([])
        assert result == []
        assert result.total_count == 0

    async def test_source_failure_propagates(self, raw_search, mock_things):
        search, _ = raw_search
        error = RuntimeError("synthetic source failure")
        mock_things.todos.side_effect = error
        mock_things.tasks.side_effect = error
        with pytest.raises(RuntimeError) as raised:
            await search([])
        assert raised.value is error

    @pytest.mark.parametrize("field", ["title", "notes"])
    @pytest.mark.parametrize("bad", [0, False, 1, {}, [], b"needle", object()])
    async def test_malformed_text_raises_even_after_match(
        self, raw_search, field, bad
    ):
        search, factory = raw_search
        good = factory("good", "needle")
        broken = factory("broken", "needle", notes="needle")
        broken[field] = bad

        # A matching sibling field must not short-circuit validation; neither
        # a matching earlier row nor pagination may conceal corrupt data.
        with pytest.raises((TypeError, AttributeError)):
            await search([good, broken], limit=1)
        assert broken[field] is bad

    @pytest.mark.parametrize(
        "offset,expected", [(0, ["a"]), (1, ["b"]), (3, [])]
    )
    @pytest.mark.parametrize("status", [None, "completed", "canceled"])
    async def test_pagination_after_matching(
        self, raw_search, offset, expected, status
    ):
        search, factory = raw_search
        rows = [
            factory("skip", "Unrelated", notes=None),
            factory("a", "Needle", notes=None, status=status or "incomplete"),
            factory("skip2", "", notes=None),
            factory("b", "NEEDLE", status=status or "incomplete"),
            factory("c", "Needle", status=status or "incomplete"),
        ]

        result = await search(rows, limit=1, offset=offset, status=status)

        assert [row["uuid"] for row in result] == expected
        assert result.total_count == 3
        for row in result:
            assert row["status"] == (status or "incomplete")
            if row["uuid"] == "a":
                assert "notes" not in row


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
