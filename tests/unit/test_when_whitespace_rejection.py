"""Unit tests for hq-f0w.34: whitespace-only ``when`` must be rejected the
same way ``when=''`` is rejected (hq-nxu.9's structured "use when='anytime'
or when='someday' to unschedule" hint), instead of being silently treated
as "no change requested".

Before this fix, the 5 server.py when-sites (add_todo, update_todo,
bulk_update_todos, add_project, update_project) pre-validated ``when`` with
``if when:`` (true for a whitespace-only string like '   ') and then
assigned the *normalized* return of
``ParameterValidator.validate_date_format(when, ..., allow_relative=True)``,
which strips the string and returns ``None`` for whitespace-only input
without raising. That silently turned ``when='   '`` into
``when=None`` (treated as "omitted") rather than surfacing the same
structured VALIDATION_ERROR that ``when=''`` already produces via
``ParameterValidator.validate_update_params`` downstream.

Also covers the accompanying validate_date_format() wording fix: when
``allow_relative=False`` (deadline validation), the rejection message must
not claim relative dates like 'today' are accepted.

These tests exercise the real ThingsMCPServer + FastMCP tool registration
via an in-memory fastmcp.Client (no stdio, no real Things 3), with
self.tools mocked out, matching the test_when_tonight_server_normalization.py
/ test_unknown_tag_structured_error.py pattern.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp import Client as FastMCPClient

from things_mcp.server import ThingsMCPServer
from things_mcp.parameter_validator import ParameterValidator, ValidationError


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


EXPECTED_WHEN_MESSAGE = "use when='anytime' or when='someday' to unschedule"


class TestUpdateTodoWhenWhitespaceRejected:
    """update_todo(when='   ') must be rejected, not silently treated as omitted."""

    @pytest.mark.asyncio
    async def test_whitespace_when_returns_validation_error(self):
        server = _make_server_with_mock_tools(
            update_todo={"success": True, "message": "Todo updated"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "TODO-1", "when": "   "}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "when"
        assert EXPECTED_WHEN_MESSAGE in sc["message"]
        # The underlying tools layer must never be reached - the request is
        # rejected before self.tools.update_todo is called.
        server.tools.update_todo.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_valid_when_still_succeeds(self):
        """Sanity check: a real when value is unaffected by the new guard."""
        server = _make_server_with_mock_tools(
            update_todo={"success": True, "message": "Todo updated"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "TODO-1", "when": "today"}
            )

        assert result.structured_content["success"] is True
        server.tools.update_todo.assert_awaited_once()


class TestBulkUpdateTodosWhenWhitespaceRejected:
    """bulk_update_todos(when='  ') must be rejected the same way."""

    @pytest.mark.asyncio
    async def test_whitespace_when_returns_validation_error(self):
        server = _make_server_with_mock_tools(
            bulk_update_todos={"success": True, "message": "Todos updated"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "bulk_update_todos", {"todo_ids": "TODO-1,TODO-2", "when": "  "}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "when"
        assert EXPECTED_WHEN_MESSAGE in sc["message"]
        server.tools.bulk_update_todos.assert_not_awaited()


class TestAddTodoWhenWhitespaceRejected:
    """add_todo(when='   ') must be rejected."""

    @pytest.mark.asyncio
    async def test_whitespace_when_returns_validation_error(self):
        server = _make_server_with_mock_tools(
            add_todo={"success": True, "todo_id": "abc123", "message": "Todo created successfully"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_todo", {"title": "Some task", "when": "   "}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "when"
        assert EXPECTED_WHEN_MESSAGE in sc["message"]
        server.tools.add_todo.assert_not_awaited()


class TestAddProjectWhenWhitespaceRejected:
    """add_project(when='   ') must be rejected."""

    @pytest.mark.asyncio
    async def test_whitespace_when_returns_validation_error(self):
        server = _make_server_with_mock_tools(
            add_project={"success": True, "project_id": "proj123", "message": "Project created successfully"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_project", {"title": "Some project", "when": "   "}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "when"
        assert EXPECTED_WHEN_MESSAGE in sc["message"]
        server.tools.add_project.assert_not_awaited()


class TestUpdateProjectWhenWhitespaceRejected:
    """update_project(when='   ') must be rejected."""

    @pytest.mark.asyncio
    async def test_whitespace_when_returns_validation_error(self):
        server = _make_server_with_mock_tools(
            update_project={"success": True, "message": "Project updated"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_project", {"id": "PROJ-1", "when": "   "}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "when"
        assert EXPECTED_WHEN_MESSAGE in sc["message"]
        server.tools.update_project.assert_not_awaited()


class TestDeadlineRejectionMessageWording:
    """validate_date_format(allow_relative=False) must not claim relative
    dates like 'today' are accepted (they are rejected for deadline)."""

    def test_relative_deadline_message_does_not_mention_relative_dates(self):
        with pytest.raises(ValidationError) as exc_info:
            ParameterValidator.validate_date_format(
                "today", "deadline", allow_relative=False
            )

        message = exc_info.value.message
        assert "relative date" not in message
        assert "today, tomorrow" not in message
        assert "YYYY-MM-DD" in message

    @pytest.mark.asyncio
    async def test_update_todo_deadline_today_message_via_client(self):
        server = _make_server_with_mock_tools(
            update_todo={"success": True, "message": "Todo updated"}
        )

        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "TODO-1", "deadline": "today"}
            )

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert "relative date" not in sc["message"]
        assert "today, tomorrow" not in sc["message"]

    def test_relative_dates_still_allowed_when_allow_relative_true(self):
        """Sanity check: the allow_relative=True path is unaffected by the
        wording fix."""
        result = ParameterValidator.validate_date_format(
            "today", "when", allow_relative=True
        )
        assert result == "today"
