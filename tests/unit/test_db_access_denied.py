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

    def test_permission_error(self):
        exc = PermissionError("Operation not permitted")
        assert is_db_access_error(exc) is True

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


class TestGetTodayDbAccessDenied:
    """End-to-end: a real things.py call raising a Full-Disk-Access denial
    propagates all the way through the real ReadOperations/ThingsTools/
    ThingsMCPServer stack (no mocked tools layer) and surfaces as a
    structured database_access_denied error instead of an opaque
    internal_error/ToolError."""

    @pytest.mark.asyncio
    async def test_get_today_reports_database_access_denied(self):
        server = ThingsMCPServer()

        client = Client(server.mcp)
        with patch(
            "things_mcp.tools_helpers.read_operations.things.today",
            side_effect=sqlite3.OperationalError("unable to open database file"),
        ):
            async with client:
                result = await client.call_tool("get_today", {})

        sc = result.structured_content
        assert sc is not None
        assert sc["success"] is False
        assert sc["error"] == "database_access_denied"
        assert os.path.realpath(sys.executable) in sc["hint"]

    @pytest.mark.asyncio
    async def test_get_todos_reports_database_access_denied(self):
        """Same end-to-end check via get_todos (things.todos), since
        get_today and get_todos read through different things.py entry
        points but must classify identically."""
        server = ThingsMCPServer()

        client = Client(server.mcp)
        with patch(
            "things_mcp.tools_helpers.read_operations.things.todos",
            side_effect=sqlite3.OperationalError("unable to open database file"),
        ):
            async with client:
                result = await client.call_tool("get_todos", {})

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
