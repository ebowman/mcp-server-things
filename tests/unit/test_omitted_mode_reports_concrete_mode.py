"""hq-f0w.39: list tools with an `if mode:` gate must not skip the context
manager when `mode` is omitted.

Before this fix, get_inbox/get_today/get_upcoming/get_anytime/get_someday
short-circuited past `context_manager.optimize_response` whenever the caller
omitted `mode`, so `structured_content["mode"]` was left as the literal
`None` - inconsistent with CLAUDE.md's documented contract that an omitted
(or 'auto') mode reports the concrete mode AUTO actually resolved to. This
test verifies that mode is always a concrete resolved value (never None,
never the literal 'auto'), for both the omitted-mode and explicit mode='auto'
cases, while explicit non-auto modes continue to be honored verbatim.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from fastmcp import Client

from things_mcp.server import ThingsMCPServer


def _make_server_with_mock_tools(**overrides):
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


def _todos(n):
    return [dict(SAMPLE_TODO, uuid=f"id{i}", title=f"Todo {i}") for i in range(n)]


LIST_TOOLS_WITH_MODE_GATE = ["get_inbox", "get_today", "get_upcoming", "get_anytime", "get_someday"]


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", LIST_TOOLS_WITH_MODE_GATE)
async def test_omitted_mode_resolves_to_concrete_mode(tool_name):
    """Calling with mode omitted entirely must still route through the
    context manager: structured_content['mode'] must be a concrete mode
    string, never None and never the literal 'auto'."""
    full = _todos(5)
    server = _make_server_with_mock_tools(**{tool_name: full})

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(tool_name, {})

    sc = result.structured_content
    assert sc["mode"] is not None
    assert sc["mode"] != "auto"
    assert sc["requested_mode"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", LIST_TOOLS_WITH_MODE_GATE)
async def test_explicit_auto_mode_resolves_to_concrete_mode(tool_name):
    """Explicit mode='auto' must resolve identically to an omitted mode."""
    full = _todos(5)
    server = _make_server_with_mock_tools(**{tool_name: full})

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(tool_name, {"mode": "auto"})

    sc = result.structured_content
    assert sc["mode"] is not None
    assert sc["mode"] != "auto"
    assert sc["requested_mode"] == "auto"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", LIST_TOOLS_WITH_MODE_GATE)
async def test_explicit_concrete_mode_is_honored(tool_name):
    """An explicit non-auto mode continues to be honored verbatim."""
    full = _todos(5)
    server = _make_server_with_mock_tools(**{tool_name: full})

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool(tool_name, {"mode": "minimal"})

    sc = result.structured_content
    assert sc["mode"] == "minimal"
    assert sc["requested_mode"] == "minimal"


@pytest.mark.asyncio
async def test_get_upcoming_days_branch_omitted_mode_resolves_to_concrete_mode():
    """The days= branch of get_upcoming is a separate code path from the
    plain Upcoming-list branch and must also resolve mode when omitted."""
    full = _todos(5)
    server = _make_server_with_mock_tools(get_todos_upcoming_in_days=full)

    client = Client(server.mcp)
    async with client:
        result = await client.call_tool("get_upcoming", {"days": 7})

    sc = result.structured_content
    assert sc["mode"] is not None
    assert sc["mode"] != "auto"
    assert sc["requested_mode"] is None
    assert sc["days"] == 7
