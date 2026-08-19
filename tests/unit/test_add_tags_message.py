"""Unit tests for hq-u1i:

1. The `add_tags` MCP tool's message-enrichment block must read the `tag_info`
   keys that `write_operations._prepare_tags` / `_validate_tags_with_policy`
   actually produce (`created` / `filtered` / `existing` / `warnings` /
   `errors`), not the nonexistent `created_tags` / `filtered_tags` keys.
2. `server._parse_tag_list` must correctly parse comma-separated tag strings,
   dropping empty entries produced by inputs like "a,,b" or "a, ".

These tests exercise the real ThingsMCPServer + FastMCP tool registration via
an in-memory fastmcp.Client (no stdio, no real Things 3). The ThingsTools
layer is replaced with a mock so nothing touches AppleScript/things.py.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp import Client

from things_mcp.server import ThingsMCPServer, _parse_tag_list
from things_mcp.config import TagCreationPolicy


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


class TestAddTagsMessageEnrichment:
    """add_tags must report created/filtered tags using the real tag_info keys."""

    @pytest.mark.asyncio
    async def test_add_tags_message_reports_created_and_filtered_tags(self):
        add_tags_result = {
            "success": True,
            "message": "Tags added successfully.",
            "tag_info": {
                "created": ["new"],
                "filtered": ["bogus"],
                "existing": ["work"],
                "warnings": ["w"],
                "errors": [],
            },
        }
        server = _make_server_with_mock_tools(add_tags=add_tags_result)
        # Truthy tag_validation_service to enter the enrichment branch.
        server.tools.tag_validation_service = MagicMock()
        server.tools.config = MagicMock()
        server.tools.config.tag_creation_policy = TagCreationPolicy.FILTER_WARN

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_tags", {"todo_id": "abc123", "tags": "new,bogus,work"}
            )

        sc = result.structured_content
        assert sc is not None
        assert "Created new tags: new" in sc["message"]
        assert "Filtered tags per policy: bogus" in sc["message"]
        assert sc["tag_warnings"] == ["w"]


class TestParseTagList:
    """Unit tests for the shared _parse_tag_list helper."""

    def test_drops_empty_entries_from_double_comma(self):
        assert _parse_tag_list("a,,b") == ["a", "b"]

    def test_drops_empty_entry_from_trailing_comma_space(self):
        assert _parse_tag_list("a, ") == ["a"]

    def test_all_blank_entries_returns_none(self):
        assert _parse_tag_list(" , ") is None

    def test_none_input_returns_none(self):
        assert _parse_tag_list(None) is None

    def test_single_tag_returns_single_item_list(self):
        assert _parse_tag_list("x") == ["x"]


class TestAddTodoTagParsingThroughClient:
    """End-to-end: add_todo(tags='a,,b') must call ThingsTools.add_todo with a
    cleaned tag list (no empty entries)."""

    @pytest.mark.asyncio
    async def test_add_todo_strips_empty_tag_entries(self):
        add_todo_result = {"success": True, "message": "Todo added", "id": "t1"}
        server = _make_server_with_mock_tools(add_todo=add_todo_result)

        client = Client(server.mcp)
        async with client:
            await client.call_tool(
                "add_todo", {"title": "Test todo", "tags": "a,,b"}
            )

        server.tools.add_todo.assert_awaited_once()
        _, kwargs = server.tools.add_todo.call_args
        assert kwargs["tags"] == ["a", "b"]
