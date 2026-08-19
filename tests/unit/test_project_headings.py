"""Tests for get_project_headings: read-only heading structure of a project."""

import pytest
from unittest.mock import Mock, patch
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager."""
    return Mock(spec=AppleScriptManager)


@pytest.fixture
def things_tools(mock_applescript_manager):
    """Create ThingsTools instance with mocked AppleScript."""
    return ThingsTools(mock_applescript_manager)


PROJECT_UUID = "proj-1"


class TestGetProjectHeadingsBasic:
    """Core behavior: items, order, todoCount."""

    @pytest.mark.asyncio
    async def test_headings_returned_in_things_order_with_todo_counts(self, things_tools):
        """Headings should be returned in the order things.tasks() provides them,
        each carrying its title, index, and open-todo count."""
        with patch('things.get') as mock_get, \
             patch('things.tasks') as mock_tasks, \
             patch('things.todos') as mock_todos:

            mock_get.return_value = {'uuid': PROJECT_UUID, 'type': 'project', 'title': 'My Project'}
            mock_tasks.return_value = [
                {'uuid': 'h1', 'type': 'heading', 'title': 'First', 'index': -515},
                {'uuid': 'h2', 'type': 'heading', 'title': 'Second', 'index': -341},
                {'uuid': 'h3', 'type': 'heading', 'title': 'Third', 'index': 0},
            ]

            def todos_side_effect(heading=None, **kwargs):
                return {
                    'h1': [{'uuid': 't1'}, {'uuid': 't2'}],
                    'h2': [{'uuid': 't3'}],
                    'h3': [],
                }.get(heading, [])

            mock_todos.side_effect = todos_side_effect

            result = await things_tools.get_project_headings(project_id=PROJECT_UUID)

            assert 'error' not in result
            items = result['items']
            assert [i['title'] for i in items] == ['First', 'Second', 'Third']
            assert [i['uuid'] for i in items] == ['h1', 'h2', 'h3']
            assert [i['index'] for i in items] == [-515, -341, 0]
            assert [i['todoCount'] for i in items] == [2, 1, 0]

            mock_tasks.assert_called_once_with(type='heading', project=PROJECT_UUID)

    @pytest.mark.asyncio
    async def test_project_with_zero_headings_returns_empty_items(self, things_tools):
        """A project with no headings returns an empty items list, not an error."""
        with patch('things.get') as mock_get, \
             patch('things.tasks') as mock_tasks, \
             patch('things.todos') as mock_todos:

            mock_get.return_value = {'uuid': PROJECT_UUID, 'type': 'project', 'title': 'Empty Project'}
            mock_tasks.return_value = []

            result = await things_tools.get_project_headings(project_id=PROJECT_UUID)

            assert 'error' not in result
            assert result['items'] == []
            mock_todos.assert_not_called()

    @pytest.mark.asyncio
    async def test_heading_with_zero_todos_reports_zero_count(self, things_tools):
        """A heading with no open to-dos underneath it reports todoCount 0."""
        with patch('things.get') as mock_get, \
             patch('things.tasks') as mock_tasks, \
             patch('things.todos') as mock_todos:

            mock_get.return_value = {'uuid': PROJECT_UUID, 'type': 'project', 'title': 'Proj'}
            mock_tasks.return_value = [
                {'uuid': 'h1', 'type': 'heading', 'title': 'Lonely Heading', 'index': 0},
            ]
            mock_todos.return_value = []

            result = await things_tools.get_project_headings(project_id=PROJECT_UUID)

            assert result['items'][0]['todoCount'] == 0
            mock_todos.assert_called_once_with(heading='h1', status='incomplete')


class TestGetProjectHeadingsErrors:
    """Structured errors for ids that don't resolve to a project."""

    @pytest.mark.asyncio
    async def test_unknown_project_id_returns_structured_error(self, things_tools):
        """things.get returning None (unknown id) yields a structured error, not a raise."""
        with patch('things.get') as mock_get, \
             patch('things.tasks') as mock_tasks:

            mock_get.return_value = None

            result = await things_tools.get_project_headings(project_id="does-not-exist")

            assert result.get('success') is False
            assert result.get('error') == 'not_found'
            mock_tasks.assert_not_called()

    @pytest.mark.asyncio
    async def test_area_id_returns_structured_error(self, things_tools):
        """An id that resolves to an area (not a project) yields a structured error."""
        with patch('things.get') as mock_get, \
             patch('things.tasks') as mock_tasks:

            mock_get.return_value = {'uuid': 'area-1', 'type': 'area', 'title': 'Some Area'}

            result = await things_tools.get_project_headings(project_id="area-1")

            assert result.get('success') is False
            assert result.get('error') == 'invalid_type'
            mock_tasks.assert_not_called()

    @pytest.mark.asyncio
    async def test_todo_id_returns_structured_error(self, things_tools):
        """An id that resolves to a to-do (not a project) yields a structured error."""
        with patch('things.get') as mock_get, \
             patch('things.tasks') as mock_tasks:

            mock_get.return_value = {'uuid': 'todo-1', 'type': 'to-do', 'title': 'Some Todo'}

            result = await things_tools.get_project_headings(project_id="todo-1")

            assert result.get('success') is False
            assert result.get('error') == 'invalid_type'
            mock_tasks.assert_not_called()

    @pytest.mark.asyncio
    async def test_heading_id_returns_structured_error(self, things_tools):
        """An id that resolves to a heading (not a project) yields a structured error."""
        with patch('things.get') as mock_get, \
             patch('things.tasks') as mock_tasks:

            mock_get.return_value = {'uuid': 'heading-1', 'type': 'heading', 'title': 'Some Heading'}

            result = await things_tools.get_project_headings(project_id="heading-1")

            assert result.get('success') is False
            assert result.get('error') == 'invalid_type'
            mock_tasks.assert_not_called()


class TestGetProjectHeadingsStructuredContent:
    """Server-level structured_content shape via the registered MCP tool.

    Uses an in-memory fastmcp.Client against a ThingsMCPServer with a mocked
    ThingsTools layer, matching the convention in test_structured_output.py.
    """

    @pytest.mark.asyncio
    async def test_server_tool_returns_items_count_total_mode(self):
        """The registered get_project_headings MCP tool wraps the read-op result in
        the standard {items,count,total,mode,limit,offset} envelope. A default
        (mode-omitted, i.e. 'auto') call resolves to a concrete mode - the
        structured_content 'mode' field must never be the literal 'auto', per
        the Structured Output contract in CLAUDE.md."""
        from unittest.mock import AsyncMock, MagicMock
        from fastmcp import Client
        from things_mcp.server import ThingsMCPServer

        server = ThingsMCPServer()
        mock_tools = MagicMock()
        mock_tools.tag_validation_service = None
        mock_tools.get_project_headings = AsyncMock(return_value={
            'items': [
                {'uuid': 'h1', 'title': 'First', 'index': 0, 'todoCount': 1},
            ]
        })
        server.tools = mock_tools

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_project_headings", {"project_id": PROJECT_UUID})

        payload = result.structured_content
        assert {"items", "count", "total", "mode", "limit", "offset"}.issubset(payload.keys())
        assert payload['mode'] != 'auto'
        assert payload['requested_mode'] == 'auto'
        assert payload['count'] == 1
        assert payload['total'] == 1
        assert payload['items'][0]['title'] == 'First'
        assert payload['items'][0]['todoCount'] == 1
        # index/todoCount must survive whatever concrete mode AUTO picked -
        # these are the heading schema's own fields, distinct from the
        # todo/project/area field sets the generic filter otherwise applies.
        assert payload['items'][0]['index'] == 0

    @pytest.mark.asyncio
    async def test_server_tool_summary_mode_returns_summary_shape(self):
        """mode='summary' actually shapes the response via
        ProgressiveDisclosureEngine.create_summary_response (count/message,
        preview-only items) instead of relabeling the full item list."""
        from unittest.mock import AsyncMock, MagicMock
        from fastmcp import Client
        from things_mcp.server import ThingsMCPServer

        server = ThingsMCPServer()
        mock_tools = MagicMock()
        mock_tools.tag_validation_service = None
        mock_tools.get_project_headings = AsyncMock(return_value={
            'items': [
                {'uuid': 'h1', 'title': 'First', 'index': -515, 'todoCount': 2},
                {'uuid': 'h2', 'title': 'Second', 'index': -341, 'todoCount': 1},
            ]
        })
        server.tools = mock_tools

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_project_headings", {"project_id": PROJECT_UUID, "mode": "summary"}
            )

        payload = result.structured_content
        assert payload['mode'] == 'summary'
        assert payload['requested_mode'] == 'summary'
        # Summary mode is a lightweight preview, not the full item list -
        # count/total still reflect the true dataset size.
        assert payload['total'] == 2
        assert payload.get('message') == 'Found 2 items'
        assert payload.get('data_available') is True

    @pytest.mark.asyncio
    async def test_server_tool_minimal_and_standard_modes_keep_index_and_todo_count(self):
        """mode='minimal' and mode='standard' filter items through the
        method-specific heading field set (hq-f0w.6 review fix), not the
        global todo field sets - index/todoCount must survive both, and no
        stray todo-only fields should appear."""
        from unittest.mock import AsyncMock, MagicMock
        from fastmcp import Client
        from things_mcp.server import ThingsMCPServer

        for requested_mode in ("minimal", "standard"):
            server = ThingsMCPServer()
            mock_tools = MagicMock()
            mock_tools.tag_validation_service = None
            mock_tools.get_project_headings = AsyncMock(return_value={
                'items': [
                    {'uuid': 'h1', 'title': 'First', 'index': -515, 'todoCount': 2},
                    {'uuid': 'h2', 'title': 'Second', 'index': -341, 'todoCount': 1},
                ]
            })
            server.tools = mock_tools

            client = Client(server.mcp)
            async with client:
                result = await client.call_tool(
                    "get_project_headings", {"project_id": PROJECT_UUID, "mode": requested_mode}
                )

            payload = result.structured_content
            assert payload['mode'] == requested_mode
            for item in payload['items']:
                assert item['index'] in (-515, -341)
                assert 'todoCount' in item
                assert set(item.keys()) <= {'uuid', 'title', 'index', 'todoCount'}

    @pytest.mark.asyncio
    async def test_server_tool_rejects_invalid_mode(self):
        """An unrecognized mode value returns the standard structured error
        shape (matching get_projects/get_areas), not a silently-echoed mode."""
        from unittest.mock import AsyncMock, MagicMock
        from fastmcp import Client
        from things_mcp.server import ThingsMCPServer

        server = ThingsMCPServer()
        mock_tools = MagicMock()
        mock_tools.tag_validation_service = None
        mock_tools.get_project_headings = AsyncMock(return_value={
            'items': [{'uuid': 'h1', 'title': 'First', 'index': 0, 'todoCount': 0}]
        })
        server.tools = mock_tools

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_project_headings", {"project_id": PROJECT_UUID, "mode": "bogus"}
            )

        payload = result.structured_content
        assert payload.get('success') is False
        assert payload.get('error') == 'invalid_mode'

    @pytest.mark.asyncio
    async def test_server_tool_propagates_structured_error(self):
        """The registered MCP tool passes a structured error straight through
        rather than wrapping it as if it were a list of items."""
        from unittest.mock import AsyncMock, MagicMock
        from fastmcp import Client
        from things_mcp.server import ThingsMCPServer

        server = ThingsMCPServer()
        mock_tools = MagicMock()
        mock_tools.tag_validation_service = None
        mock_tools.get_project_headings = AsyncMock(return_value={
            'success': False,
            'error': 'not_found',
            'message': 'No item found with id: does-not-exist',
        })
        server.tools = mock_tools

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_project_headings", {"project_id": "does-not-exist"})

        payload = result.structured_content
        assert payload.get('success') is False
        assert payload.get('error') == 'not_found'
