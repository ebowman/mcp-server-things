"""Tests for FastMCP structured_content on read tools.

These tests exercise the real ThingsMCPServer + FastMCP tool registration via an
in-memory fastmcp.Client (no stdio, no real Things 3). Most mock ThingsTools;
search regressions use real ThingsTools with mocked source I/O.
"""

import pytest
import sqlite3
from copy import deepcopy
from functools import partial
from unittest.mock import AsyncMock, MagicMock, patch

from fastmcp import Client
from fastmcp.exceptions import ToolError

from fixtures.things_realistic import make_heading, make_project, make_todo
from things_mcp.server import ThingsMCPServer
from things_mcp.things_import import ScopedHelperAccessError, ScopedHelperError
from things_mcp.tools import ThingsTools


SAMPLE_TODO = {
    "uuid": "abc123",
    "title": "Test todo",
    "status": "incomplete",
    "notes": "Some notes",
    "tags": ["work"],
    "dueDate": None,
}

SAMPLE_PROJECT = {
    "uuid": "proj123",
    "title": "Test project",
    "type": "project",
    "status": "incomplete",
    "notes": "Some notes",
    "tags": ["work"],
    "area": "area-uuid",
    "areaTitle": "Work",
    "start": "Anytime",
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


REQUIRED_LIST_KEYS = {"items", "count", "total", "mode", "requested_mode", "limit", "offset"}


@pytest.fixture
def search_server():
    """Mock the entire I/O proxy, not the search result or worker."""
    with patch("things_mcp.tools_helpers.read_operations.things") as source:
        server = ThingsMCPServer()
        server.tools = ThingsTools(MagicMock())
        yield server, source


@pytest.mark.parametrize("tool", ["search_todos", "search_advanced"])
class TestRealSearchStructuredOutput:
    @pytest.mark.parametrize(
        "mode", ["auto", "summary", "minimal", "standard", "raw"]
    )
    async def test_nullable_notes_pagination(self, search_server, tool, mode):
        server, source = search_server
        rows = [
            make_todo("before", "Notes-only match", notes="A NEEdle!\nNext."),
            make_todo("null", "Needle", notes=None),
            make_todo("missing", "NEEDLE"),
            make_todo("empty", "Needle", notes=""),
            make_todo("after", "Needle", notes="Ordinary notes."),
        ]
        del rows[2]["notes"]
        before = deepcopy(rows)
        source.todos.return_value = rows
        # Public advanced search is FILTER-ONLY; do not pass internal query.
        args = {"query": "needle"} if tool == "search_todos" else {}
        async with Client(server.mcp) as client:
            # Full response (summary previews only three), interior page,
            # final page and an exhausted window all retain the true total.
            for limit, offset in [(50, 0), (2, 1), (2, 3), (2, 5)]:
                result = await client.call_tool(
                    tool, {**args, "mode": mode, "limit": limit,
                           "offset": offset}
                )
                sc = result.structured_content
                expected = rows[offset:offset + limit]
                if mode == "summary":
                    expected = expected[:3]
                assert not result.is_error
                assert REQUIRED_LIST_KEYS <= sc.keys()
                assert sc["total"] == 5
                assert sc["count"] == len(expected)
                assert sc["limit"] == limit
                assert sc["offset"] == offset
                assert sc["requested_mode"] == mode
                if mode == "auto":
                    # Empty auto responses resolve to standard.
                    assert sc["mode"] == (
                        "detailed" if expected else "standard"
                    )
                else:
                    assert sc["mode"] == mode
                assert [item["uuid"] for item in sc["items"]] == [
                    row["uuid"] for row in expected
                ]
                for item, row in zip(sc["items"], expected):
                    omit_notes = (
                        mode in ("summary", "minimal")
                        or row.get("notes") is None
                    )
                    if omit_notes:
                        assert "notes" not in item
                    else:
                        assert item["notes"] == row["notes"]
                more = bool(expected) and offset + len(expected) < 5
                if mode != "summary" and more:
                    assert sc["next_offset"] == offset + len(expected)
                else:
                    assert "next_offset" not in sc
        assert rows == before
        source.todos.assert_called_with(
            status="incomplete" if tool == "search_todos" else None
        )
        source.tasks.assert_not_called()

    @pytest.mark.parametrize("error_type,message", [
        (RuntimeError, "synthetic source failure"),
        (sqlite3.OperationalError, "database is locked"),
        (ScopedHelperError, "synthetic helper query failure"),
    ])
    async def test_source_failure_is_tool_error(
        self, search_server, tool, error_type, message
    ):
        server, source = search_server
        source.todos.side_effect = error_type(message)
        args = {"query": "needle"} if tool == "search_todos" else {}
        async with Client(server.mcp) as client:
            with pytest.raises(ToolError, match=message):
                await client.call_tool(tool, args)
        source.todos.assert_called_once()

    @pytest.mark.parametrize("error_type,message,hint", [
        (sqlite3.OperationalError, "unable to open database file",
         "Full Disk Access"),
        (ScopedHelperAccessError, "bookmark revoked", "select or re-select"),
    ])
    async def test_db_denial_retains_envelope(
        self, search_server, tool, error_type, message, hint
    ):
        server, source = search_server
        source.todos.side_effect = error_type(message)
        args = {"query": "needle"} if tool == "search_todos" else {}
        async with Client(server.mcp) as client:
            result = await client.call_tool(tool, args)
        sc = result.structured_content
        assert not result.is_error
        assert sc["success"] is False
        assert sc["error"] == "database_access_denied"
        assert hint in sc["hint"]
        assert "items" not in sc
        assert "total" not in sc
        source.todos.assert_called_once()

    async def test_real_empty_source(self, search_server, tool):
        server, source = search_server
        source.todos.return_value = []
        args = {"query": "needle"} if tool == "search_todos" else {}
        async with Client(server.mcp) as client:
            result = await client.call_tool(tool, args)
        sc = result.structured_content
        assert not result.is_error
        assert sc["items"] == []
        assert sc["count"] == sc["total"] == 0
        assert "error" not in sc
        assert "next_offset" not in sc
        source.todos.assert_called_once()


@pytest.mark.parametrize("kind,factory", [
    ("to-do", make_todo),
    ("project", make_project),
    ("heading", partial(make_heading, project="parent",
                        project_title="Parent")),
])
async def test_advanced_filter_only_keeps_nonmatching_rows(
    search_server, kind, factory
):
    """Internal no-query control and public typed filters use the same rows."""
    server, source = search_server
    source.tasks.return_value = [
        factory("null", "Unrelated", notes=None),
        factory("missing", "Also unrelated"),
        factory("ordinary", "Other", notes="Ordinary notes."),
    ]
    del source.tasks.return_value[1]["notes"]
    direct = await server.tools.search_advanced(type=kind)
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "search_advanced", {"type": kind, "mode": "raw"}
        )
    sc = result.structured_content
    assert not result.is_error
    assert sc["items"] == direct
    assert [item["uuid"] for item in sc["items"]] == [
        "null", "missing", "ordinary",
    ]
    assert sc["count"] == sc["total"] == direct.total_count == 3
    assert all(item["type"] == kind for item in sc["items"])
    assert "notes" not in sc["items"][0]
    assert "notes" not in sc["items"][1]
    assert sc["items"][2]["notes"] == "Ordinary notes."
    assert "next_offset" not in sc
    assert source.tasks.call_count == 2
    source.tasks.assert_called_with(type=kind, status=None)
    source.todos.assert_not_called()


async def test_malformed_search_row_is_tool_error(search_server):
    server, source = search_server
    row = make_todo("bad", "needle")
    row["notes"] = 0
    source.todos.return_value = [row]
    async with Client(server.mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("search_todos", {"query": "needle"})


@pytest.mark.parametrize(
    "message,code",
    [
        ("Unrecognized tag type: 'WORK'", "unknown_tag"),
        ("Invalid start_date argument", "invalid_parameter"),
    ],
)
async def test_real_advanced_search_validation_envelope(
    search_server, message, code
):
    server, source = search_server
    source.todos.side_effect = ValueError(message)
    source.tags.return_value = [{"uuid": "tag-1", "title": "Work"}]
    async with Client(server.mcp) as client:
        result = await client.call_tool("search_advanced", {"tag": "WORK"})
    sc = result.structured_content
    assert not result.is_error
    assert sc["success"] is False
    assert sc["error"] == code
    assert "items" not in sc
    assert "total" not in sc
    if code == "unknown_tag":
        assert sc["tag"] == "WORK"
        assert sc["suggestions"] == ["Work"]
    else:
        assert sc["message"] == message
        source.tags.assert_not_called()
    source.todos.assert_called_once()


async def test_public_advanced_search_has_no_query_parameter(search_server):
    server, source = search_server
    async with Client(server.mcp) as client:
        tools = await client.list_tools()
    advanced = next(tool for tool in tools if tool.name == "search_advanced")
    assert "query" not in advanced.inputSchema["properties"]
    source.todos.assert_not_called()
    source.tasks.assert_not_called()


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
    async def test_get_todo_by_id_tag_error_is_top_level_not_nested(self):
        """A tag id resolves to the canonical structured error
        ({"success": false, "error": "invalid_type", ...}) at the top level
        of structured_content, not nested under "item" (hq-f0w.23 review)."""
        tag_error = {
            "success": False,
            "error": "invalid_type",
            "message": "Item tag123 is a tag, not a retrievable item. Use get_tags() or get_tagged_items() for tags.",
        }
        server = _make_server_with_mock_tools(get_todo_by_id=tag_error)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_todo_by_id", {"todo_id": "tag123"})

        sc = result.structured_content
        assert sc is not None
        assert sc.get("success") is False
        assert sc.get("error") == "invalid_type"
        assert "item" not in sc

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
        # get_tags has no 'mode' parameter, so requested_mode must be None
        # (nothing was requested), while 'mode' still reports the effective
        # shape ('standard') of the returned items - hq-lsb.
        assert sc["requested_mode"] is None
        assert sc["mode"] == "standard"

    @pytest.mark.asyncio
    async def test_get_tag_usage_structured_content(self):
        """get_tag_usage rows are tags (not todos); verify items/count/total shape
        is applied on top of its existing custom mode shaping."""
        tag_rows = [
            {"title": "work", "uuid": "t1", "open_count": 3, "total_count": 5},
            {"title": "home", "uuid": "t2", "open_count": 1, "total_count": 1},
        ]
        usage_payload = {
            "tag_count": 2,
            "unused_count": 0,
            "tags": list(tag_rows),
        }
        server = _make_server_with_mock_tools(get_tag_usage=usage_payload)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_tag_usage", {"mode": "standard"})

        sc = result.structured_content
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["total"] == 2
        assert sc["count"] == 2
        assert sc["items"] == tag_rows

        # hq-wsa.2: 'tags' was the source key items was populated from - it must
        # not survive in the final envelope alongside 'items' (double serialization).
        assert "tags" not in sc
        assert "data" not in sc

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
        # get_trash has no 'mode' parameter, so requested_mode must be None
        # (hq-cal.3), while 'mode' still reports the effective shape.
        assert sc["mode"] == "standard"
        assert sc["requested_mode"] is None


class TestGetProjectsFieldFiltering:
    """hq-f0w.32: get_projects(mode='standard'/'minimal') must keep a
    project's area/areaTitle - the shared todo field sets used to be applied
    to project rows too, and never carried area/areaTitle."""

    @pytest.mark.asyncio
    async def test_standard_mode_keeps_area_fields(self):
        server = _make_server_with_mock_tools(get_projects=[SAMPLE_PROJECT])

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_projects", {"mode": "standard"})

        item = result.structured_content["items"][0]
        assert item["area"] == "area-uuid"
        assert item["areaTitle"] == "Work"

    @pytest.mark.asyncio
    async def test_minimal_mode_keeps_area_field(self):
        server = _make_server_with_mock_tools(get_projects=[SAMPLE_PROJECT])

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_projects", {"mode": "minimal"})

        item = result.structured_content["items"][0]
        assert item["area"] == "area-uuid"


class TestAutoModeReportsEffectiveMode:
    """mode='auto' (or omitted) must report the effective mode actually chosen by
    context_manager.optimize_response, not echo back 'auto' (hq-48d)."""

    @pytest.mark.asyncio
    async def test_get_todos_auto_mode_reports_effective_mode_not_auto(self):
        """With enough items that AUTO mode selection resolves to 'minimal',
        structured_content['mode'] must equal that resolved mode, not 'auto'."""
        # get_todos applies a default limit of 50 when none is given, so request
        # more items than that default *and* pass an explicit limit large enough
        # that AUTO mode selection sees the full 100-item set (not truncated to 50).
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(100)]
        server = _make_server_with_mock_tools(get_todos=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_todos", {"mode": "auto", "limit": 100}
            )

        sc = result.structured_content
        assert sc is not None
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())

        # The effective mode must be surfaced from meta['mode'], and must not be 'auto'.
        assert sc["mode"] != "auto"
        assert sc["mode"] == sc["meta"]["mode"]
        assert sc["mode"] == "minimal"

        # The originally-requested mode is preserved separately.
        assert sc["requested_mode"] == "auto"

    def test_read_result_auto_mode_prefers_meta_mode_directly(self):
        """Direct unit test of ThingsMCPServer._read_result: given a synthetic
        {"data": [...], "meta": {"mode": "minimal", ...}} payload and mode='auto',
        the resolved 'mode' key must come from meta['mode'], and 'requested_mode'
        must preserve the original 'auto' request."""
        server = ThingsMCPServer()
        synthetic_response = {
            "data": [{"uuid": "1", "title": "a"}, {"uuid": "2", "title": "b"}],
            "meta": {"mode": "minimal", "count": 2},
        }

        result = server._read_result(synthetic_response, mode="auto", total=2)

        assert result["mode"] == "minimal"
        assert result["requested_mode"] == "auto"
        assert result["count"] == 2
        assert result["total"] == 2

    def test_read_result_none_mode_prefers_meta_mode(self):
        """When mode is not passed at all (None), the effective mode from
        meta['mode'] should still be surfaced rather than left as None."""
        server = ThingsMCPServer()
        synthetic_response = {
            "data": [{"uuid": "1", "title": "a"}],
            "meta": {"mode": "summary", "count": 1},
        }

        result = server._read_result(synthetic_response, total=1)

        assert result["mode"] == "summary"
        assert result["requested_mode"] is None

    def test_read_result_explicit_mode_is_not_overridden_by_meta(self):
        """When the caller passes a concrete (non-auto) mode, that mode wins even
        if meta carries a different value - explicit requests are honored."""
        server = ThingsMCPServer()
        synthetic_response = {
            "data": [{"uuid": "1", "title": "a"}],
            "meta": {"mode": "minimal", "count": 1},
        }

        result = server._read_result(synthetic_response, mode="standard", total=1)

        assert result["mode"] == "standard"
        assert result["requested_mode"] == "standard"

    def test_read_result_auto_mode_prefers_top_level_mode_when_no_meta(self):
        """create_summary_response() (used when AUTO resolves to SUMMARY) returns a
        top-level 'mode': 'summary' key with NO 'meta' dict at all. mode='auto' must
        still resolve to 'summary' in that case, not fall through to 'auto'."""
        server = ThingsMCPServer()
        summary_shaped_response = {
            "success": True,
            "count": 150,
            "mode": "summary",
            "data_available": True,
            "message": "Found 150 items",
            "recent_preview": [{"uuid": "1", "title": "a"}],
        }

        result = server._read_result(summary_shaped_response, mode="auto", total=150)

        assert result["mode"] == "summary"
        assert result["requested_mode"] == "auto"

    @pytest.mark.asyncio
    async def test_get_todos_auto_mode_resolves_to_summary_not_auto(self):
        """End-to-end: enough items with large notes that AUTO mode selection
        resolves to SUMMARY (the create_summary_response shape, which carries no
        'meta'). structured_content['mode'] must be 'summary', not 'auto'."""
        todos = [
            dict(SAMPLE_TODO, uuid=f"id{i}", notes="n" * 800) for i in range(150)
        ]
        server = _make_server_with_mock_tools(get_todos=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_todos", {"mode": "auto", "limit": 200}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["mode"] == "summary"
        assert sc["requested_mode"] == "auto"


class TestEmptyResultsReportConcreteMode:
    """hq-f0w.26: empty results with mode omitted/'auto' must report a concrete
    effective mode (not the literal 'auto') per CLAUDE.md's Structured Output docs.
    context_manager.optimize_response's empty-data path now resolves AUTO to
    'standard' and records it in meta['mode']."""

    @pytest.mark.asyncio
    async def test_get_projects_empty_auto_mode_reports_standard_not_auto(self):
        server = _make_server_with_mock_tools(get_projects=[])

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_projects", {})

        sc = result.structured_content
        assert sc is not None
        assert sc["items"] == []
        assert sc["mode"] == "standard"
        assert sc["mode"] != "auto"
        assert sc["requested_mode"] == "auto"

    @pytest.mark.asyncio
    async def test_get_project_headings_empty_auto_mode_reports_standard_not_auto(self):
        server = _make_server_with_mock_tools(get_project_headings={"items": []})

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_project_headings", {"project_id": "proj123"}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["items"] == []
        assert sc["mode"] == "standard"
        assert sc["mode"] != "auto"
        assert sc["requested_mode"] == "auto"


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
            limit=None, include_project_tasks=False, include_projects=False
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
            limit=None, include_project_tasks=True, include_projects=False
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


class TestDueInDaysActivatingInDaysModeAndLimit:
    """hq-wsa.3: get_due_in_days/get_activating_in_days gained mode+limit
    params and now route through context_manager.optimize_response instead
    of shipping the raw, unfiltered convert_todo list. Verify mode actually
    shapes fields, limit truncates client-side while total stays pre-limit,
    and requested_mode echoes the caller's actual request (these two tools
    left the no-mode-parameter group)."""

    @pytest.mark.asyncio
    async def test_get_due_in_days_minimal_mode_excludes_notes(self):
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(3)]
        server = _make_server_with_mock_tools(get_todos_due_in_days=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_due_in_days", {"days": 7, "mode": "minimal"}
            )

        sc = result.structured_content
        assert sc is not None
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())
        assert sc["mode"] == "minimal"
        assert sc["requested_mode"] == "minimal"
        assert sc["count"] == 3
        assert sc["total"] == 3
        for item in sc["items"]:
            assert "notes" not in item, f"minimal mode must exclude notes, got {item}"

    @pytest.mark.asyncio
    async def test_get_due_in_days_standard_mode_includes_notes(self):
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(2)]
        server = _make_server_with_mock_tools(get_todos_due_in_days=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_due_in_days", {"days": 7, "mode": "standard"}
            )

        sc = result.structured_content
        assert sc["mode"] == "standard"
        assert sc["requested_mode"] == "standard"
        for item in sc["items"]:
            assert item.get("notes") == "Some notes"

    @pytest.mark.asyncio
    async def test_get_due_in_days_limit_truncates_but_total_is_pre_limit(self):
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(10)]
        server = _make_server_with_mock_tools(get_todos_due_in_days=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_due_in_days", {"days": 30, "mode": "standard", "limit": 4}
            )

        sc = result.structured_content
        assert sc["count"] == 4
        assert len(sc["items"]) == 4
        assert sc["total"] == 10, "total must be the pre-limit count, not len(items)"
        assert sc["limit"] == 4

    @pytest.mark.asyncio
    async def test_get_due_in_days_requested_mode_none_when_omitted(self):
        todos = [dict(SAMPLE_TODO, uuid="id0")]
        server = _make_server_with_mock_tools(get_todos_due_in_days=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_due_in_days", {"days": 7})

        sc = result.structured_content
        assert sc["requested_mode"] is None
        assert sc["mode"] != "auto"

    @pytest.mark.asyncio
    async def test_get_due_in_days_invalid_mode_returns_structured_error(self):
        server = _make_server_with_mock_tools(get_todos_due_in_days=[])

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_due_in_days", {"days": 7, "mode": "bogus"}
            )

        sc = result.structured_content
        assert sc["success"] is False
        assert sc["error"] == "invalid_mode"

    @pytest.mark.asyncio
    async def test_get_activating_in_days_minimal_mode_excludes_notes(self):
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(3)]
        server = _make_server_with_mock_tools(get_todos_activating_in_days=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_activating_in_days", {"days": 7, "mode": "minimal"}
            )

        sc = result.structured_content
        assert sc["mode"] == "minimal"
        assert sc["requested_mode"] == "minimal"
        for item in sc["items"]:
            assert "notes" not in item

    @pytest.mark.asyncio
    async def test_get_activating_in_days_limit_truncates_but_total_is_pre_limit(self):
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(8)]
        server = _make_server_with_mock_tools(get_todos_activating_in_days=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_activating_in_days", {"days": 30, "mode": "standard", "limit": 3}
            )

        sc = result.structured_content
        assert sc["count"] == 3
        assert len(sc["items"]) == 3
        assert sc["total"] == 8
        assert sc["limit"] == 3

    @pytest.mark.asyncio
    async def test_get_activating_in_days_requested_mode_none_when_omitted(self):
        todos = [dict(SAMPLE_TODO, uuid="id0")]
        server = _make_server_with_mock_tools(get_todos_activating_in_days=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_activating_in_days", {"days": 7})

        sc = result.structured_content
        assert sc["requested_mode"] is None
        assert sc["mode"] != "auto"

    @pytest.mark.asyncio
    async def test_get_activating_in_days_invalid_mode_returns_structured_error(self):
        server = _make_server_with_mock_tools(get_todos_activating_in_days=[])

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_activating_in_days", {"days": 7, "mode": "bogus"}
            )

        sc = result.structured_content
        assert sc["success"] is False
        assert sc["error"] == "invalid_mode"


class TestSearchTodosSummaryModePreview:
    """hq-cal.4: search_todos(mode='summary')'s structured_content['items'] must
    be populated from the search summarizer's 'result_preview' key (which
    _read_result's preview fallback previously did not check, so items was
    always [] under mode='summary' even though result_preview was populated)."""

    @pytest.mark.asyncio
    async def test_search_todos_summary_mode_returns_non_empty_preview(self):
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}", title=f"milk {i}") for i in range(10)]
        server = _make_server_with_mock_tools(search_todos=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "search_todos", {"query": "milk", "mode": "summary"}
            )

        sc = result.structured_content
        assert sc is not None
        assert REQUIRED_LIST_KEYS.issubset(sc.keys())

        # Previously items was always [] under mode='summary'; must now be
        # populated from the summarizer's result_preview.
        assert sc["items"] != []
        assert sc["count"] == len(sc["items"])
        assert sc["count"] > 0

        # Preview rows use the documented SUMMARY field set - a subset of
        # {uuid, title, status, tags, dueDate}, no other keys leak through.
        allowed_keys = {"uuid", "title", "status", "tags", "dueDate"}
        for item in sc["items"]:
            assert set(item.keys()) <= allowed_keys

        # total reflects the full pre-preview match count, not the preview size.
        assert sc["total"] == 10

    @pytest.mark.asyncio
    async def test_search_todos_summary_mode_no_total_matches_key_when_limited(self):
        """hq-wsa.5: _summarize_search_results previously emitted
        'total_matches': len(results) - but the data reaching it is already
        limit/offset-truncated (server.py passes the final window down), so
        a limit=1 call yielded total_matches=1 even though the true,
        pre-limit match count (correctly reported by the envelope's
        separately-injected 'total') was much larger. total_matches must be
        gone from the summary envelope entirely; 'total' remains the
        authoritative, correct, pre-limit count."""
        # Build a truncated window: only 1 todo reaches the summarizer even
        # though the underlying search matched many more (mocked total below).
        todos = [dict(SAMPLE_TODO, uuid="only-id", title="milk")]
        server = _make_server_with_mock_tools(search_todos=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "search_todos", {"query": "milk", "mode": "summary", "limit": 1}
            )

        sc = result.structured_content
        assert sc is not None
        assert "total_matches" not in sc, (
            f"total_matches must never appear in search summary envelopes: {sc!r}"
        )
        # total is the authoritative pre-limit count; with only 1 mocked
        # todo behind the mocked tools layer, total == 1 here (there is no
        # separate pre-limit source in this mock), which is exactly the
        # point: a stale 'total_matches': len(results) could never diverge
        # from 'total' in a way a caller could detect without a real
        # pre-limit total behind it - it's a dead, misleading duplicate key
        # that must be dropped rather than threaded through.
        assert sc["total"] == 1
        assert sc["count"] == 1


class TestNoDuplicatedPayloadKey:
    """hq-wsa.2: 'items' is the one canonical payload array in every structured
    envelope - the source key it was populated from ('data' from
    optimize_response, or whichever summary-preview key matched:
    'recent_preview'/'recent_projects'/'result_preview'/'tags'/'top') must never
    also survive in the final envelope (previously the same list object was
    aliased under both keys - byte-identical double serialization)."""

    LEGACY_KEYS = {"data", "recent_preview", "recent_projects", "result_preview", "top"}

    @pytest.mark.asyncio
    async def test_get_todos_standard_mode_no_legacy_data_key(self):
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(3)]
        server = _make_server_with_mock_tools(get_todos=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_todos", {"mode": "standard"})

        sc = result.structured_content
        assert sc["items"] == todos
        assert self.LEGACY_KEYS.isdisjoint(sc.keys())

    @pytest.mark.asyncio
    async def test_get_todos_summary_mode_no_legacy_preview_key(self):
        """AUTO/summary-shaped responses (create_summary_response) must not carry
        'recent_preview' alongside 'items'."""
        todos = [dict(SAMPLE_TODO, uuid=f"id{i}") for i in range(10)]
        server = _make_server_with_mock_tools(get_todos=todos)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_todos", {"mode": "summary"})

        sc = result.structured_content
        assert sc["items"] != []
        assert self.LEGACY_KEYS.isdisjoint(sc.keys())

    @pytest.mark.asyncio
    async def test_get_projects_summary_mode_no_legacy_preview_key(self):
        projects = [dict(SAMPLE_PROJECT, uuid=f"proj{i}") for i in range(5)]
        server = _make_server_with_mock_tools(get_projects=projects)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_projects", {"mode": "summary"})

        sc = result.structured_content
        assert sc["items"] != []
        assert self.LEGACY_KEYS.isdisjoint(sc.keys())

    @pytest.mark.asyncio
    async def test_get_tag_usage_no_legacy_tags_key(self):
        """Direct duplicate of TestStructuredContentShape's assertion, kept here
        as a representative-tool check grouped with the other legacy-key tests."""
        usage_payload = {
            "tag_count": 1,
            "unused_count": 0,
            "tags": [{"title": "work", "uuid": "t1", "open_count": 1, "total_count": 1}],
        }
        server = _make_server_with_mock_tools(get_tag_usage=usage_payload)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("get_tag_usage", {"mode": "standard"})

        sc = result.structured_content
        assert sc["items"] != []
        assert "tags" not in sc
        assert self.LEGACY_KEYS.isdisjoint(sc.keys())

    def test_read_result_pops_data_key_directly(self):
        """Direct unit test of _read_result: a synthetic {'data': [...], 'meta':
        {...}} payload must not carry 'data' in the returned envelope."""
        server = ThingsMCPServer()
        synthetic_response = {
            "data": [{"uuid": "1", "title": "a"}],
            "meta": {"mode": "standard", "count": 1},
        }

        result = server._read_result(synthetic_response, mode="standard", total=1)

        assert result["items"] == [{"uuid": "1", "title": "a"}]
        assert "data" not in result

    def test_read_result_pops_result_preview_key_directly(self):
        """Direct unit test of _read_result: a synthetic summary-shaped payload
        carrying 'result_preview' must not retain that key once 'items' is
        populated from it."""
        server = ThingsMCPServer()
        synthetic_response = {
            "success": True,
            "count": 3,
            "mode": "summary",
            "result_preview": [{"uuid": "1", "title": "a"}],
        }

        result = server._read_result(synthetic_response, mode="auto", total=3)

        assert result["items"] == [{"uuid": "1", "title": "a"}]
        assert "result_preview" not in result


class TestServerCapabilitiesTotalTools:
    """Verify get_server_capabilities.total_tools stays in sync with the real
    number of tools registered with the FastMCP server (hq-d9q)."""

    @pytest.mark.asyncio
    async def test_total_tools_matches_registered_tool_count(self):
        """The registered tool count from client.list_tools() must equal both
        server_info.total_tools and api_coverage.total_tools in the
        get_server_capabilities structured_content."""
        server = _make_server_with_mock_tools()

        client = Client(server.mcp)
        async with client:
            registered_tools = await client.list_tools()
            result = await client.call_tool("get_server_capabilities", {})

        sc = result.structured_content
        assert sc is not None

        registered_count = len(registered_tools)
        assert registered_count > 0
        assert sc["server_info"]["total_tools"] == registered_count
        assert sc["api_coverage"]["total_tools"] == registered_count
