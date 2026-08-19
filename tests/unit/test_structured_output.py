"""Tests for FastMCP structured_content on read tools.

These tests exercise the real ThingsMCPServer + FastMCP tool registration via an
in-memory fastmcp.Client (no stdio, no real Things 3). The ThingsTools layer is
replaced with a mock so nothing touches AppleScript/things.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp import Client

from things_mcp.server import ThingsMCPServer


SAMPLE_TODO = {
    "uuid": "abc123",
    "title": "Test todo",
    "status": "open",
    "notes": "Some notes",
    "tags": ["work"],
    "dueDate": None,
}


def _make_server_with_mock_tools(**overrides):
    """Create a ThingsMCPServer with a MagicMock ThingsTools layer.

    Args:
        **overrides: AsyncMock return values keyed by ThingsTools method name.

    Returns:
        The configured ThingsMCPServer instance.
    """
    server = ThingsMCPServer()
    mock_tools = MagicMock()
    mock_tools.tag_validation_service = None
    for method_name, return_value in overrides.items():
        setattr(mock_tools, method_name, AsyncMock(return_value=return_value))
    server.tools = mock_tools
    return server


REQUIRED_LIST_KEYS = {"items", "count", "total", "mode", "limit", "offset"}


class TestStructuredContentShape:
    """Verify structured_content shape for representative read tools."""

    @pytest.mark.asyncio
    async def test_get_today_standard_mode_has_full_items(self):
        """get_today with no mode returns items/count/total/mode/limit/offset,
        with the full item list present (not a preview)."""
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(10)]
        server = _make_server_with_mock_tools(get_today=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_today", {})

        sc = result.structured_content
        assert sc is not None
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["count"] == 10
        assert sc["total"] == 10
        assert len(sc["items"]) == 10

        # Text content must also be present and carry the same data.
        assert result.content
        assert "Test todo" in result.content[0].text

    @pytest.mark.asyncio
    async def test_get_today_summary_mode_does_not_include_full_items(self):
        """Under mode=summary, structured_content must NOT contain the full item
        list - only a small preview - to avoid context explosion (per CLAUDE.md
        'NEVER use get_projects(include_items=true)' guidance applied generally
        to summary mode)."""
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}", notes="n" * 300) for i in range(30)]
        server = _make_server_with_mock_tools(get_today=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_today", {"mode": "summary"})

        sc = result.structured_content
        assert sc is not None
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["total"] == 30
        # Summary mode returns a small preview, never the full 30-item list.
        assert len(sc["items"]) < 30
        assert len(sc["items"]) <= 5

    @pytest.mark.asyncio
    async def test_get_todos_list_tool_summary_vs_standard(self):
        """get_todos (the general list tool) must shape structured items the same
        way it shapes text: summary has no full items, standard does."""
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(25)]
        server = _make_server_with_mock_tools(get_todos=todos)

        client = Client(server.mcp)
        async with client:
            summary_result = await client.call_tool("get_todos", {"mode": "summary"})
            standard_result = await client.call_tool("get_todos", {"mode": "standard"})

        summary_sc = summary_result.structured_content
        standard_sc = standard_result.structured_content

        assert REQUIRED_LIST_KEYS.issubset(summary_sc.keys())
        assert REQUIRED_LIST_KEYS.issubset(standard_sc.keys())

        assert summary_sc["total"] == 25
        assert len(summary_sc["items"]) < 25

        assert standard_sc["total"] == 25
        assert len(standard_sc["items"]) == 25

    @pytest.mark.asyncio
    async def test_get_todo_by_id_returns_single_item_shape(self):
        """Single-item read tools use {"item": {...}} instead of the items-list shape."""
        server = _make_server_with_mock_tools(get_todo_by_id=SAMPLE_TODO)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_todo_by_id", {"todo_id": "abc123"})

        sc = result.structured_content
        assert sc is not None
        assert set(sc.keys()) == {"item"}
        assert sc["item"]["uuid"] == "abc123"
        assert sc["item"]["title"] == "Test todo"

    @pytest.mark.asyncio
    async def test_get_inbox_bare_list_tool_does_not_crash(self):
        """get_inbox previously returned a bare list when mode was omitted, which
        crashes under FastMCP 3.x (structured_content must be a dict). Verify the
        fixed tool returns a well-formed dict instead."""
        todos = [SAMPLE_TODO]
        server = _make_server_with_mock_tools(get_inbox=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_inbox", {})

        assert result.is_error is False
        sc = result.structured_content
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["items"] == todos

    @pytest.mark.asyncio
    async def test_get_tags_bare_list_tool_does_not_crash(self):
        """get_tags previously declared -> List[Dict[str, Any]] and returned a bare
        list, which crashes under FastMCP 3.x. Verify it now returns a dict."""
        tags = [{"title": "work", "count": 3}, {"title": "home", "count": 1}]
        server = _make_server_with_mock_tools(get_tags=tags)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_tags", {})

        assert result.is_error is False
        sc = result.structured_content
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["items"] == tags
        assert sc["count"] == 2

    @pytest.mark.asyncio
    async def test_get_tag_usage_structured_content(self):
        """get_tag_usage rows are tags (not todos); verify items/count/total shape
        is applied on top of its existing custom mode shaping."""
        usage_payload = {
            "tag_count": 2,
            "unused_count": 0,
            "tags": [
                {"title": "work", "uuid": "t1", "open_count": 3, "total_count": 5},
                {"title": "home", "uuid": "t2", "open_count": 1, "total_count": 1},
            ],
        }
        server = _make_server_with_mock_tools(get_tag_usage=usage_payload)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_tag_usage", {"mode": "standard"})

        sc = result.structured_content
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["total"] == 2
        assert sc["count"] == 2
        assert sc["items"] == usage_payload["tags"]

    @pytest.mark.asyncio
    async def test_get_trash_preserves_pagination_fields(self):
        """get_trash already returns a pagination dict; verify the normalized
        envelope is added without dropping the existing total_count/has_more."""
        trash_payload = {
            "items": [SAMPLE_TODO],
            "total_count": 5,
            "limit": 1,
            "offset": 0,
            "has_more": True,
        }
        server = _make_server_with_mock_tools(get_trash=trash_payload)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_trash", {"limit": 1, "offset": 0})

        sc = result.structured_content
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["total"] == 5
        assert sc["count"] == 1
        assert sc["has_more"] is True
        assert sc["total_count"] == 5


class TestGetSomedayIncludeProjectTasks:
    """Verify the get_someday MCP tool threads include_project_tasks through to
    ThingsTools.get_someday, and defaults to False (opt-in inheritance)."""

    @pytest.mark.asyncio
    async def test_get_someday_default_does_not_include_project_tasks(self):
        """No include_project_tasks arg -> ThingsTools.get_someday called with
        include_project_tasks=False, and structured_content shape is intact."""
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(3)]
        server = _make_server_with_mock_tools(get_someday=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_someday", {})

        server.tools.get_someday.assert_awaited_once_with(
            limit=None, include_project_tasks=False
        )

        sc = result.structured_content
        assert sc is not None
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["count"] == 3
        assert sc["total"] == 3
        assert len(sc["items"]) == 3

    @pytest.mark.asyncio
    async def test_get_someday_include_project_tasks_true_threads_through(self):
        """include_project_tasks=True is passed through to ThingsTools.get_someday
        and inherited items (marked inheritedSomeday) flow through unchanged."""
        native = dict(SAMPLE_TODO, uuid="native1")
        inherited = dict(SAMPLE_TODO, uuid="inherited1", inheritedSomeday=True)
        todos = [native, inherited]
        server = _make_server_with_mock_tools(get_someday=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_someday", {"include_project_tasks": True}
            )

        server.tools.get_someday.assert_awaited_once_with(
            limit=None, include_project_tasks=True
        )

        sc = result.structured_content
        assert sc is not None
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["count"] == 2
        assert sc["total"] == 2
        uuids = {item["uuid"] for item in sc["items"]}
        assert uuids == {"native1", "inherited1"}
        inherited_item = next(i for i in sc["items"] if i["uuid"] == "inherited1")
        assert inherited_item.get("inheritedSomeday") is True
