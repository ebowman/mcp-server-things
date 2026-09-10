"""Tests for the database_access_denied structured read-tool error.

Covers is_db_access_error's classification and an end-to-end check that a
TCC/Full-Disk-Access denial reading the Things database surfaces through a
read tool (get_today) as a structured database_access_denied error rather
than an opaque internal_error/ToolError.
"""

import os
import sqlite3
import sys
from unittest.mock import patch

import pytest
from unittest.mock import AsyncMock, MagicMock

from fastmcp import Client

from things_mcp.server import ThingsMCPServer
from things_mcp.tools_helpers.read_operations import (
    is_db_access_error,
    read_error_from_exception,
)


class TestIsDbAccessError:
    """is_db_access_error classification."""

    def test_operational_error_unable_to_open_database_file(self):
        exc = sqlite3.OperationalError("unable to open database file")
        assert is_db_access_error(exc) is True

    def test_operational_error_authorization_denied(self):
        exc = sqlite3.OperationalError("authorization denied")
        assert is_db_access_error(exc) is True

    def test_permission_error_on_things_database_container(self):
        exc = PermissionError(
            13,
            "Operation not permitted",
        )
        exc.filename = (
            "/Users/x/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/"
            "ThingsData-abc123/Things Database.thingsdatabase/main.sqlite"
        )
        assert is_db_access_error(exc) is True

    def test_permission_error_on_unrelated_file_is_not_classified(self):
        exc = PermissionError(13, "Operation not permitted")
        exc.filename = "/some/other/file"
        assert is_db_access_error(exc) is False

    def test_permission_error_with_no_filename_is_not_classified(self):
        exc = PermissionError("Operation not permitted")
        assert is_db_access_error(exc) is False

    def test_operational_error_unrelated_message_is_not_classified(self):
        exc = sqlite3.OperationalError("no such table: TMTask")
        assert is_db_access_error(exc) is False

    def test_value_error_is_not_classified(self):
        exc = ValueError("bogus")
        assert is_db_access_error(exc) is False


class TestReadErrorFromException:
    """read_error_from_exception's dispatch between the two error shapes."""

    def test_classified_error_returns_database_access_denied(self):
        exc = sqlite3.OperationalError("unable to open database file")
        result = read_error_from_exception(exc)
        assert result["success"] is False
        assert result["error"] == "database_access_denied"
        assert os.path.realpath(sys.executable) in result["hint"]
        assert result["interpreter"] == os.path.realpath(sys.executable)

    def test_unclassified_error_falls_back_to_internal_error(self):
        exc = ValueError("something else broke")
        result = read_error_from_exception(exc)
        assert result["success"] is False
        assert result["error"] == "internal_error"
        assert result["message"] == "something else broke"


def _make_server_with_mock_tools(**overrides):
    server = ThingsMCPServer()
    mock_tools = MagicMock()
    mock_tools.tag_validation_service = None
    for method_name, return_value in overrides.items():
        setattr(mock_tools, method_name, AsyncMock(side_effect=return_value))
    server.tools = mock_tools
    return server


class TestDbAccessDeniedEndToEnd:
    """End-to-end: a real things.py call raising a Full-Disk-Access denial
    propagates all the way through the real ReadOperations/ThingsTools/
    ThingsMCPServer stack (no mocked tools layer) and surfaces as a
    structured database_access_denied error instead of an opaque
    internal_error/ToolError.

    Covers both call shapes documented in CLAUDE.md/the bead: the
    raise-then-gate path (get_today, get_todos, get_projects, search_todos -
    the exception propagates up to server.py's except block, which now
    delegates to ThingsMCPServer._handle_read_exception) and the
    return-envelope path (get_tag_usage, get_project_headings - the tools
    layer catches the exception itself and returns the structured error
    directly, never raising into server.py at all).
    """

    @pytest.mark.parametrize(
        "tool_name,tool_args,patch_target",
        [
            ("get_today", {}, "things_mcp.tools_helpers.read_operations.things.today"),
            ("get_todos", {}, "things_mcp.tools_helpers.read_operations.things.todos"),
            ("get_projects", {}, "things_mcp.tools_helpers.read_operations.things.projects"),
            ("search_todos", {"query": "test"}, "things_mcp.tools_helpers.read_operations.things.todos"),
            ("get_tag_usage", {}, "things_mcp.tools_helpers.read_operations.things.tags"),
            ("get_project_headings", {"project_id": "abc123"}, "things_mcp.tools_helpers.read_operations.things.get"),
        ],
    )
    @pytest.mark.asyncio
    async def test_reports_database_access_denied(self, tool_name, tool_args, patch_target):
        server = ThingsMCPServer()

        client = Client(server.mcp)
        with patch(
            patch_target,
            side_effect=sqlite3.OperationalError("unable to open database file"),
        ):
            async with client:
                result = await client.call_tool(tool_name, tool_args)

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "database_access_denied"
        assert os.path.realpath(sys.executable) in sc["hint"]

    @pytest.mark.asyncio
    async def test_get_today_generic_error_still_raises(self):
        """A non-DB-access exception must still surface as a raised
        ToolError (unchanged pre-existing behavior) rather than being
        converted to a structured error."""
        from fastmcp.exceptions import ToolError

        server = _make_server_with_mock_tools(get_today=ValueError("boom"))

        client = Client(server.mcp)
        async with client:
            with pytest.raises(ToolError):
                await client.call_tool("get_today", {})
