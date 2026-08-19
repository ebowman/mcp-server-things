"""Pagination contract tests (hq-nxu.3).

CLAUDE.md documents `total` as "items available before any limit was applied".
These tests verify that contract holds for every list tool exercised here:
`total` must reflect the full pre-limit/offset match count, not just
`len(items)`, and offset windows over the same underlying data must be
disjoint and together cover the full set.

Two layers are exercised:
  - The ThingsTools/ReadOperations layer directly (things.py mocked), for
    search_todos/search_advanced/get_logbook - these now return a
    ``ListWithTotal`` whose `.total_count` carries the true pre-limit/offset
    count while still behaving exactly like `List[Dict]`.
  - The real ThingsMCPServer + in-memory fastmcp.Client, with the ThingsTools
    layer mocked - for get_inbox/get_today/get_upcoming/get_anytime/
    get_someday/get_logbook/search_todos/search_advanced, verifying `total`
    in `structured_content` is the pre-limit count and offset windows are
    disjoint/complete.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastmcp import Client

from things_mcp.server import ThingsMCPServer
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


# ============================================================================
# Shared fixtures / helpers
# ============================================================================

@pytest.fixture
def mock_applescript_manager():
    manager = MagicMock(spec=AppleScriptManager)
    return manager


@pytest.fixture
def tools(mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


def _make_server_with_mock_tools(**overrides):
    """Create a ThingsMCPServer with a MagicMock ThingsTools layer.

    Args:
        **overrides: AsyncMock return values keyed by ThingsTools method name.
    """
    server = ThingsMCPServer()
    mock_tools = MagicMock()
    mock_tools.tag_validation_service = None
    for method_name, return_value in overrides.items():
        setattr(mock_tools, method_name, AsyncMock(return_value=return_value))
    server.tools = mock_tools
    return server


SAMPLE_TODO = {
    "uuid": "abc123",
    "title": "Test todo",
    "status": "open",
    "notes": "Some notes",
    "tags": [],
    "dueDate": None,
}


def _todos(n, prefix="id"):
    return [dict(SAMPLE_TODO, uuid=f"{prefix}{i}", title=f"Todo {i}") for i in range(n)]


# ============================================================================
# get_inbox / get_today / get_upcoming / get_anytime / get_someday
# (server.py fetches the full unbounded set via ThingsTools, then slices to
# `limit` itself, per the get_upcoming(days=...) precedent.)
# ============================================================================

LIST_TOOLS_NO_OFFSET = ["get_inbox", "get_today", "get_upcoming", "get_anytime", "get_someday"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", LIST_TOOLS_NO_OFFSET)
async def test_total_exceeds_count_when_limit_truncates(tool_name):
    """total must equal the full unlimited set size, even though items/count
    are truncated to `limit`."""
    full = _todos(37)
    server = _make_server_with_mock_tools(**{tool_name: full})

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(tool_name, {"limit": 5})

    sc = result.structured_content
    assert sc["count"] == 5
    assert len(sc["items"]) == 5
    assert sc["total"] == 37
    assert sc["total"] > sc["count"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", LIST_TOOLS_NO_OFFSET)
async def test_total_equals_count_when_no_limit_applied(tool_name):
    """Without a limit, total and count must agree (both equal the full set)."""
    full = _todos(12)
    server = _make_server_with_mock_tools(**{tool_name: full})

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(tool_name, {})

    sc = result.structured_content
    assert sc["count"] == 12
    assert sc["total"] == 12


@pytest.mark.asyncio
async def test_get_upcoming_days_branch_total_is_pre_limit():
    """The days= branch of get_upcoming (a separate code path from the plain
    Upcoming-list branch) must also report the pre-limit total."""
    full = _todos(20)
    server = _make_server_with_mock_tools(get_todos_upcoming_in_days=full)

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool("get_upcoming", {"days": 7, "limit": 3})

    sc = result.structured_content
    assert sc["count"] == 3
    assert sc["total"] == 20


@pytest.mark.asyncio
async def test_get_anytime_limit_5_total_matches_unlimited_count():
    """Mirrors the bead's live done-criterion: get_anytime(limit=5).total
    equals the count of the unlimited call, using a mocked ThingsTools layer."""
    full = _todos(9)
    server = _make_server_with_mock_tools(get_anytime=full)

    client = Client(server.mcp)
    async with client:
        limited = await client.call_tool("get_anytime", {"limit": 5})
        unlimited = await client.call_tool("get_anytime", {})

    assert limited.structured_content["total"] == unlimited.structured_content["total"]
    assert limited.structured_content["total"] == 9
    assert limited.structured_content["count"] == 5


# ============================================================================
# search_todos / search_advanced / get_logbook - ThingsTools layer directly
# (things.py mocked). Verifies ListWithTotal.total_count is the true
# pre-limit/offset match count, and offset windows are disjoint/complete.
# ============================================================================

@pytest.mark.asyncio
async def test_search_todos_total_count_is_pre_limit(tools):
    """search_todos: total_count on the returned ListWithTotal reflects all
    matches, not just the limited page."""
    matching = [
        {"uuid": f"m{i}", "title": f"match {i}", "notes": "", "status": "incomplete"}
        for i in range(15)
    ]
    non_matching = [{"uuid": "n1", "title": "irrelevant", "notes": "", "status": "incomplete"}]

    with patch("things_mcp.tools_helpers.read_operations.things.todos",
               return_value=matching + non_matching):
        result = await tools.search_todos(query="match", limit=4)

    assert len(result) == 4
    assert result.total_count == 15


@pytest.mark.asyncio
async def test_search_todos_offset_windows_disjoint_and_complete(tools):
    """Two offset windows over the same match set must be disjoint and,
    together, cover the full match set exactly once."""
    matching = [
        {"uuid": f"m{i}", "title": f"match {i}", "notes": "", "status": "incomplete"}
        for i in range(10)
    ]

    with patch("things_mcp.tools_helpers.read_operations.things.todos", return_value=matching):
        page1 = await tools.search_todos(query="match", limit=6, offset=0)
        page2 = await tools.search_todos(query="match", limit=6, offset=6)

    uuids1 = {t["uuid"] for t in page1}
    uuids2 = {t["uuid"] for t in page2}

    assert len(page1) == 6
    assert len(page2) == 4  # only 4 remain after offset=6
    assert uuids1.isdisjoint(uuids2)
    assert uuids1 | uuids2 == {f"m{i}" for i in range(10)}
    assert page1.total_count == 10
    assert page2.total_count == 10


@pytest.mark.asyncio
async def test_search_advanced_total_count_is_pre_limit(tools):
    """search_advanced: total_count reflects the full filtered set before
    limit/offset."""
    todos = [{"uuid": f"t{i}", "title": f"Todo {i}", "notes": "", "status": "incomplete"}
             for i in range(23)]

    with patch("things_mcp.tools_helpers.read_operations.things.todos", return_value=todos):
        result = await tools.search_advanced(status="incomplete", limit=5)

    assert len(result) == 5
    assert result.total_count == 23


@pytest.mark.asyncio
async def test_search_advanced_offset_windows_disjoint_and_complete(tools):
    todos = [{"uuid": f"t{i}", "title": f"Todo {i}", "notes": "", "status": "incomplete"}
             for i in range(9)]

    with patch("things_mcp.tools_helpers.read_operations.things.todos", return_value=todos):
        page1 = await tools.search_advanced(status="incomplete", limit=5, offset=0)
        page2 = await tools.search_advanced(status="incomplete", limit=5, offset=5)

    uuids1 = {t["uuid"] for t in page1}
    uuids2 = {t["uuid"] for t in page2}

    assert len(page1) == 5
    assert len(page2) == 4
    assert uuids1.isdisjoint(uuids2)
    assert uuids1 | uuids2 == {f"t{i}" for i in range(9)}
    assert page1.total_count == 9
    assert page2.total_count == 9


@pytest.mark.asyncio
async def test_search_advanced_unknown_tag_error_unaffected_by_offset():
    """The unknown_tag structured-error convention (a plain single-element
    list) must keep working with the new offset parameter present."""
    from things_mcp.services.applescript_manager import AppleScriptManager as ASM
    manager = MagicMock(spec=ASM)
    tools = ThingsTools(manager)

    with patch("things_mcp.tools_helpers.read_operations.things.todos",
               side_effect=ValueError("Unrecognized tag type")), \
         patch("things_mcp.tools_helpers.read_operations.things.tags", return_value=[]):
        result = await tools.search_advanced(tag="totally-unknown", offset=5)

    assert len(result) == 1
    assert result[0]["success"] is False
    assert result[0]["error"] == "unknown_tag"


@pytest.mark.asyncio
async def test_get_logbook_total_count_is_pre_limit(tools):
    """get_logbook: total_count reflects all completed items within the
    period, before limit/offset."""
    from datetime import datetime

    completed = [
        {"uuid": f"c{i}", "title": f"Completed {i}", "status": "completed",
         "stop_date": datetime.now().isoformat()}
        for i in range(30)
    ]

    with patch("things_mcp.tools_helpers.read_operations.things.todos", return_value=completed):
        result = await tools.get_logbook(limit=10)

    assert len(result) == 10
    assert result.total_count == 30


@pytest.mark.asyncio
async def test_get_logbook_offset_windows_disjoint_and_complete(tools):
    from datetime import datetime, timedelta

    # Distinct stop_date per item so sort order (most recent first) is stable.
    now = datetime.now()
    completed = [
        {"uuid": f"c{i}", "title": f"Completed {i}", "status": "completed",
         "stop_date": (now - timedelta(minutes=i)).isoformat()}
        for i in range(14)
    ]

    with patch("things_mcp.tools_helpers.read_operations.things.todos", return_value=completed):
        page1 = await tools.get_logbook(limit=8, offset=0)
        page2 = await tools.get_logbook(limit=8, offset=8)

    uuids1 = {t["uuid"] for t in page1}
    uuids2 = {t["uuid"] for t in page2}

    assert len(page1) == 8
    assert len(page2) == 6
    assert uuids1.isdisjoint(uuids2)
    assert uuids1 | uuids2 == {f"c{i}" for i in range(14)}
    assert page1.total_count == 14
    assert page2.total_count == 14


# ============================================================================
# search_todos / search_advanced / get_logbook - through server.py
# (ThingsTools mocked). Verifies `total`/`offset` propagate correctly through
# _read_result's structured_content.
# ============================================================================

class _ListWithTotal(list):
    """Minimal stand-in mirroring read_operations.ListWithTotal, for tests
    that mock the ThingsTools layer directly (below server.py)."""

    def __init__(self, iterable, total_count):
        super().__init__(iterable)
        self.total_count = total_count


@pytest.mark.asyncio
async def test_server_search_todos_total_is_pre_limit_and_offset_threaded():
    page = _ListWithTotal(_todos(4, prefix="s"), total_count=40)
    server = _make_server_with_mock_tools(search_todos=page)

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(
            "search_todos", {"query": "todo", "limit": 4, "offset": 8}
        )

    sc = result.structured_content
    assert sc["total"] == 40
    assert sc["count"] == 4
    assert sc["offset"] == 8

    server.tools.search_todos.assert_awaited_once()
    _, kwargs = server.tools.search_todos.call_args
    assert kwargs.get("offset") == 8


@pytest.mark.asyncio
async def test_server_search_advanced_total_is_pre_limit_and_offset_threaded():
    page = _ListWithTotal(_todos(3, prefix="a"), total_count=50)
    server = _make_server_with_mock_tools(search_advanced=page)

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(
            "search_advanced", {"status": "incomplete", "limit": 3, "offset": 10}
        )

    sc = result.structured_content
    assert sc["total"] == 50
    assert sc["count"] == 3
    assert sc["offset"] == 10

    server.tools.search_advanced.assert_awaited_once()
    _, kwargs = server.tools.search_advanced.call_args
    assert kwargs.get("offset") == 10


@pytest.mark.asyncio
async def test_server_get_logbook_total_is_pre_limit_and_offset_threaded():
    page = _ListWithTotal(_todos(2, prefix="l"), total_count=17)
    server = _make_server_with_mock_tools(get_logbook=page)

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool("get_logbook", {"limit": 2, "offset": 4})

    sc = result.structured_content
    assert sc["total"] == 17
    assert sc["count"] == 2
    assert sc["offset"] == 4

    server.tools.get_logbook.assert_awaited_once()
    _, kwargs = server.tools.get_logbook.call_args
    assert kwargs.get("offset") == 4


@pytest.mark.asyncio
async def test_server_search_advanced_unknown_tag_error_bypasses_total():
    """The unknown_tag structured-error short-circuit must still fire even
    though search_advanced now also has an `offset` param."""
    error_payload = [{
        'success': False,
        'error': 'unknown_tag',
        'tag': 'Bogus',
        'suggestions': [],
    }]
    server = _make_server_with_mock_tools(search_advanced=error_payload)

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(
            "search_advanced", {"tag": "Bogus", "offset": 5}
        )

    sc = result.structured_content
    assert sc["success"] is False
    assert sc["error"] == "unknown_tag"
