"""Unit tests for hq-nxu.5:

get_tagged_items / search_advanced must surface a structured
{"success": False, "error": "unknown_tag", "tag": ..., "suggestions": [...]}
error when things.py rejects an unknown or wrong-case tag (raising
ValueError), rather than silently returning an empty list that is
indistinguishable from a genuinely empty tag.

These tests exercise the real ThingsMCPServer + FastMCP tool registration via
an in-memory fastmcp.Client (no stdio, no real Things 3), confirming the
structured error dict built in tools_helpers/read_operations.py actually
reaches the MCP caller through the server.py tool layer's structured_content.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp import Client

from things_mcp.server import ThingsMCPServer


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


UNKNOWN_TAG_ERROR = {
    "success": False,
    "error": "unknown_tag",
    "tag": "LLM-WIKI",
    "suggestions": ["llm-wiki"],
}


class TestGetTaggedItemsUnknownTagServerLayer:
    """get_tagged_items must pass the structured error through unmodified."""

    @pytest.mark.asyncio
    async def test_unknown_tag_returns_structured_error(self):
        server = _make_server_with_mock_tools(get_tagged_items=dict(UNKNOWN_TAG_ERROR))

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_tagged_items", {"tag": "LLM-WIKI"}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "unknown_tag"
        assert sc["tag"] == "LLM-WIKI"
        assert sc["suggestions"] == ["llm-wiki"]

    @pytest.mark.asyncio
    async def test_known_tag_still_returns_normal_list_result(self):
        """Sanity check: the normal (non-error) path is unaffected."""
        server = _make_server_with_mock_tools(
            get_tagged_items=[{"uuid": "1", "title": "Task 1"}]
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "get_tagged_items", {"tag": "Work"}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["items"] == [{"uuid": "1", "title": "Task 1"}]
        assert sc["count"] == 1
        assert sc["tag"] == "Work"
        assert "error" not in sc


class TestSearchAdvancedUnknownTagServerLayer:
    """search_advanced must unwrap the single-element error list into a plain dict."""

    @pytest.mark.asyncio
    async def test_unknown_tag_returns_structured_error(self):
        server = _make_server_with_mock_tools(search_advanced=[dict(UNKNOWN_TAG_ERROR)])

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "search_advanced", {"tag": "LLM-WIKI"}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "unknown_tag"
        assert sc["tag"] == "LLM-WIKI"
        assert sc["suggestions"] == ["llm-wiki"]
