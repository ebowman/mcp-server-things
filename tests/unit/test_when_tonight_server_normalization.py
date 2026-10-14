"""Unit tests for hq-nxu.10 review gap: server.py add_todo/add_project must
use the *normalized* return value of
ParameterValidator.validate_date_format(when, ..., allow_relative=True),
not the raw caller-supplied string.

Before this fix, server.py validated `when` for its side effect only and
discarded the return value, so add_todo(when='tonight')/add_todo(when='Tonight')
passed validation (since 'tonight' normalizes successfully) but then forwarded
the literal, un-normalized string 'tonight'/'Tonight' downstream to
self.tools.add_todo(). TodoOperations only recognizes the literal lowercase
'evening' when deciding to route through the Things URL scheme, so
'tonight' silently fell through to the AppleScript path, which has no
'tonight'/'evening' handling at all - a silent regression (before this bead,
'tonight' was rejected outright as an unrecognized relative date).

These tests exercise the real ThingsMCPServer + FastMCP tool registration via
an in-memory fastmcp.Client (no stdio, no real Things 3), with self.tools
mocked out, confirming the *normalized* 'evening' value (not the raw
'tonight'/'Tonight' input) is what reaches ThingsTools.add_todo /
ThingsTools.add_project - matching the test_unknown_tag_structured_error.py
pattern.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp import Client as FastMCPClient

from things_mcp.server import ThingsMCPServer


class Client(FastMCPClient):
    """Keep structured write errors inspectable instead of raising them."""

    async def call_tool(self, *args, **kwargs):
        kwargs.setdefault("raise_on_error", False)
        return await super().call_tool(*args, **kwargs)


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


class TestAddTodoTonightNormalization:
    """add_todo(when='tonight'/'Tonight') must reach ThingsTools.add_todo
    with the normalized when='evening', not the raw alias."""

    @pytest.mark.asyncio
    async def test_add_todo_tonight_normalizes_to_evening(self):
        server = _make_server_with_mock_tools(
            add_todo={"success": True, "todo_id": "abc123", "message": "Todo created successfully"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_todo", {"title": "Evening task", "when": "tonight"}
            )

        assert result.structured_content["success"] is True
        server.tools.add_todo.assert_awaited_once()
        _, kwargs = server.tools.add_todo.await_args
        assert kwargs["when"] == "evening"

    @pytest.mark.asyncio
    async def test_add_todo_tonight_case_insensitive_normalizes_to_evening(self):
        server = _make_server_with_mock_tools(
            add_todo={"success": True, "todo_id": "abc123", "message": "Todo created successfully"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_todo", {"title": "Evening task", "when": "Tonight"}
            )

        assert result.structured_content["success"] is True
        _, kwargs = server.tools.add_todo.await_args
        assert kwargs["when"] == "evening"

    @pytest.mark.asyncio
    async def test_add_todo_evening_literal_unaffected(self):
        """Regression guard: the literal 'evening' spelling still passes
        through unchanged."""
        server = _make_server_with_mock_tools(
            add_todo={"success": True, "todo_id": "abc123", "message": "Todo created successfully"}
        )

        client = Client(server.mcp)
        async with client:
            await client.call_tool("add_todo", {"title": "Evening task", "when": "evening"})

        _, kwargs = server.tools.add_todo.await_args
        assert kwargs["when"] == "evening"

    @pytest.mark.asyncio
    async def test_add_todo_today_unaffected_by_normalization_fix(self):
        """Regression guard: plain 'today' is unaffected by assigning the
        normalized return value back to `when`."""
        server = _make_server_with_mock_tools(
            add_todo={"success": True, "todo_id": "abc123", "message": "Todo created successfully"}
        )

        client = Client(server.mcp)
        async with client:
            await client.call_tool("add_todo", {"title": "Today task", "when": "today"})

        _, kwargs = server.tools.add_todo.await_args
        assert kwargs["when"] == "today"


class TestUpdateTodoTonightNormalization:
    @pytest.mark.asyncio
    async def test_update_todo_tonight_normalizes_to_evening(self):
        server = _make_server_with_mock_tools(
            update_todo={"success": True, "message": "Todo updated and scheduled for This Evening successfully"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "abc123", "when": "tonight"}
            )

        assert result.structured_content["success"] is True
        _, kwargs = server.tools.update_todo.await_args
        assert kwargs["when"] == "evening"


class TestBulkUpdateTodosTonightNormalization:
    @pytest.mark.asyncio
    async def test_bulk_update_todos_tonight_normalizes_to_evening(self):
        server = _make_server_with_mock_tools(
            bulk_update_todos={"success": True, "updated_count": 2, "message": "ok"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "bulk_update_todos", {"todo_ids": "id1,id2", "when": "tonight"}
            )

        assert result.structured_content["success"] is True
        _, kwargs = server.tools.bulk_update_todos.await_args
        assert kwargs["when"] == "evening"


class TestAddProjectTonightRejected:
    """add_project(when='tonight') must be rejected identically to
    add_project(when='evening') - Things has no This Evening concept for
    projects. This is a structured error returned directly by server.py's
    pre-validation and never reaches ThingsTools.add_project at all, since
    validate_date_format() itself doesn't reject 'evening'/'tonight' (that
    rejection happens downstream in TodoOperations.add_project) - this test
    instead confirms that the raw un-normalized 'tonight' does NOT silently
    slip past into ThingsTools.add_project unnormalized, which would let it
    bypass TodoOperations.add_project's literal 'evening' check entirely and
    silently fall back to AppleScript's plain "Today" fallback."""

    @pytest.mark.asyncio
    async def test_add_project_tonight_normalizes_to_evening_before_reaching_tools(self):
        server = _make_server_with_mock_tools(
            add_project={"success": True, "project_id": "proj123", "message": "Project created successfully"}
        )

        client = Client(server.mcp)
        async with client:
            await client.call_tool(
                "add_project", {"title": "Evening project", "when": "tonight"}
            )

        _, kwargs = server.tools.add_project.await_args
        assert kwargs["when"] == "evening"

    @pytest.mark.asyncio
    async def test_add_project_tonight_rejected_end_to_end_with_real_tools(self):
        """End-to-end (real ThingsTools -> TodoOperations, AppleScript
        mocked) confirms 'tonight' is rejected exactly like 'evening' is -
        the normalization fix in server.py must not create a loophole where
        the alias bypasses TodoOperations.add_project's literal check."""
        from unittest.mock import Mock
        from things_mcp.tools import ThingsTools
        from things_mcp.services.applescript_manager import AppleScriptManager

        real_manager = MagicMock(spec=AppleScriptManager)
        real_manager.auth_token = "test-token"
        real_manager.execute_applescript = AsyncMock(return_value={"success": True, "output": "proj123"})

        server = ThingsMCPServer()
        server.tools = ThingsTools(real_manager)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_project", {"title": "Evening project", "when": "tonight"}
            )

        sc = result.structured_content
        assert sc["success"] is False
        assert sc["error"] == "UNSUPPORTED_FOR_PROJECTS"
        assert "not supported for projects" in sc["message"]
        real_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_project_tonight_rejected_end_to_end_with_real_tools(self):
        from things_mcp.tools import ThingsTools
        from things_mcp.services.applescript_manager import AppleScriptManager

        real_manager = MagicMock(spec=AppleScriptManager)
        real_manager.auth_token = "test-token"
        real_manager.execute_applescript = AsyncMock(return_value={"success": True, "output": "updated"})

        server = ThingsMCPServer()
        server.tools = ThingsTools(real_manager)

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_project", {"id": "proj123", "when": "tonight"}
            )

        sc = result.structured_content
        assert sc["success"] is False
        assert sc["error"] == "UNSUPPORTED_FOR_PROJECTS"
        assert "not supported for projects" in sc["message"]
        real_manager.execute_applescript.assert_not_awaited()
