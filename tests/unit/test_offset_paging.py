"""hq-gix: offset paging + next_offset for get_inbox/today/upcoming/anytime/someday."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp import Client
from fastmcp.exceptions import ToolError

from things_mcp.context_manager import ContextAwareResponseManager, ContextBudget
from things_mcp.server import ThingsMCPServer

TOOLS = ["get_inbox", "get_today", "get_upcoming", "get_anytime", "get_someday"]


def _items(n, note_size=10):
    return [
        {"uuid": f"id{i:04d}", "title": f"Todo {i}", "type": "to-do", "status": "incomplete",
         "notes": "x" * note_size, "tags": [], "dueDate": None, "project": None,
         "heading": None, "start": "Anytime"}
        for i in range(n)
    ]


def _server(tool, data, budget=None):
    server = ThingsMCPServer()
    mock_tools = MagicMock()
    mock_tools.tag_validation_service = None
    setattr(mock_tools, tool, AsyncMock(return_value=data))
    server.tools = mock_tools
    if budget:
        server.context_manager = ContextAwareResponseManager(ContextBudget(max_response_size=budget))
    return server


async def _call(server, tool, args):
    async with Client(server.mcp) as c:
        return (await c.call_tool(tool, args)).structured_content


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", TOOLS)
async def test_windows_disjoint_and_cover_full_set(tool):
    data = _items(23)
    server = _server(tool, data)
    seen, offset = [], 0
    while True:
        sc = await _call(server, tool, {"mode": "minimal", "limit": 5, "offset": offset})
        assert sc["total"] == 23
        assert sc["offset"] == offset
        seen += [i["uuid"] for i in sc["items"]]
        if "next_offset" not in sc:
            break
        assert sc["next_offset"] == offset + sc["count"]
        offset = sc["next_offset"]
    assert seen == [d["uuid"] for d in data]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", TOOLS)
async def test_offset_beyond_total_is_empty(tool):
    server = _server(tool, _items(7))
    sc = await _call(server, tool, {"mode": "minimal", "limit": 5, "offset": 50})
    assert sc["items"] == [] and sc["count"] == 0
    assert sc["total"] == 7
    assert "next_offset" not in sc
    assert "truncated" not in sc


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", TOOLS)
async def test_last_window_has_no_next_offset(tool):
    server = _server(tool, _items(10))
    sc = await _call(server, tool, {"mode": "minimal", "limit": 5, "offset": 5})
    assert sc["count"] == 5 and "next_offset" not in sc
    assert "truncated" not in sc and "truncation_hint" not in sc


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", TOOLS)
async def test_invalid_offset_rejected(tool):
    server = _server(tool, _items(3))
    with pytest.raises(ToolError):
        await _call(server, tool, {"offset": -1})


@pytest.mark.asyncio
@pytest.mark.parametrize("tool", TOOLS)
async def test_truncation_hint_reports_true_total_and_paging_reaches_all(tool):
    data = _items(60, note_size=400)
    server = _server(tool, data, budget=5_000)
    seen, offset, pages = [], 0, 0
    while True:
        sc = await _call(server, tool, {"mode": "standard", "limit": 50, "offset": offset})
        pages += 1
        assert pages < 50
        assert sc["total"] == 60
        seen += [i["uuid"] for i in sc["items"]]
        if sc.get("truncated"):
            assert "of 60 items" in sc["truncation_hint"]
            assert f"offset={offset + sc['count']}" in sc["truncation_hint"]
            assert sc["next_offset"] == offset + sc["count"]
        if "next_offset" not in sc:
            break
        offset = sc["next_offset"]
    assert pages > 1
    assert seen == [d["uuid"] for d in data]


@pytest.mark.asyncio
async def test_get_logbook_next_offset():
    server = ThingsMCPServer()
    mock_tools = MagicMock()
    mock_tools.tag_validation_service = None

    class _L(list):
        total_count = 20

    async def fake(limit=None, period=None, offset=0, include_canceled=True):
        return _L(_items(20)[offset:offset + limit])

    mock_tools.get_logbook = fake
    server.tools = mock_tools
    sc = await _call(server, "get_logbook", {"limit": 5})
    assert sc["total"] == 20 and sc["next_offset"] == 5
    sc = await _call(server, "get_logbook", {"limit": 5, "offset": 15})
    assert sc["count"] == 5 and "next_offset" not in sc
