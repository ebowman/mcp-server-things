"""Primary-read failures must not become successful empty results (hq-4yu.2).

Only the source is mocked in the failure/empty matrix: ReadOperations,
ThingsTools, conversion, server registration and FastMCP transport are real.
Required nested-query and date-skip policies are deliberately not changed here.
"""

import os
import sqlite3
import sys
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from things_mcp.server import ThingsMCPServer
from things_mcp.things_import import (
    LazyThingsProxy,
    ScopedHelperAccessError,
    ScopedHelperError,
    ThingsImportTimeoutError,
)
from things_mcp.tools_helpers import read_operations
from things_mcp.tools_helpers.read_operations import (
    ListWithTotal,
    ToolsHelpers,
)

from fixtures.things_realistic import (
    make_area,
    make_project,
    make_tag,
    make_todo,
)


# Public tool, arguments, ReadOperations method, things.py primary source.
CASES = [
    ("get_todos", {}, "get_todos", "todos"),
    ("get_projects", {}, "get_projects", "projects"),
    ("get_areas", {}, "get_areas", "areas"),
    ("get_tags", {}, "get_tags", "tags"),
    ("get_inbox", {}, "get_inbox", "inbox"),
    ("get_today", {}, "get_today", "today"),
    ("get_upcoming", {}, "get_upcoming", "upcoming"),
    ("get_anytime", {}, "get_anytime", "anytime"),
    ("get_someday", {}, "get_someday", "someday"),
    ("get_logbook", {}, "get_logbook", "todos"),
    ("get_trash", {}, "get_trash", "trash"),
    ("get_tagged_items", {"tag": "Work"}, "get_tagged_items", "todos"),
    ("get_due_in_days", {"days": 7}, "get_due_in_days", "todos"),
    ("get_activating_in_days", {"days": 7}, "get_activating_in_days", "todos"),
    ("get_upcoming", {"days": 7}, "get_todos_upcoming_in_days", "todos"),
    ("get_recent", {"period": "7d"}, "get_recent", "tasks"),
]
CASE_IDS = [case[2] for case in CASES]
# These two public tools already return structured generic failures.
STRUCTURED_GENERIC = {"get_due_in_days", "get_activating_in_days"}
ERRORS = [
    (RuntimeError, "synthetic query failure", None),
    (ValueError, "unrelated source value failure", None),
    (sqlite3.OperationalError, "no such table: TMTask", None),
    (sqlite3.OperationalError, "database is locked", None),
    (ScopedHelperError, "query rejected", None),
    (sqlite3.OperationalError, "unable to open database file", "direct"),
    (ScopedHelperAccessError, "bookmark revoked", "scoped"),
]


@pytest.fixture
def stack():
    """No live database, helper, import scan or AppleScript calls."""
    source = MagicMock(spec=[
        "todos", "projects", "areas", "tags", "inbox", "today", "upcoming",
        "anytime", "someday", "trash", "tasks", "get", "checklist_items",
    ])
    for name in source._mock_methods:
        getattr(source, name).return_value = []
    with patch.object(read_operations, "things", source):
        yield ThingsMCPServer(), source


async def assert_public_failure(server, tool, args, message, access=None):
    async with Client(server.mcp) as client:
        if access is None and tool not in STRUCTURED_GENERIC:
            with pytest.raises(ToolError, match=message):
                await client.call_tool(tool, args)
            return
        result = await client.call_tool(tool, args)
    data = result.structured_content
    assert data["success"] is False
    assert data["error"] == (
        "database_access_denied" if access else "internal_error"
    )
    if access == "direct":
        assert "Full Disk Access" in data["hint"]
        assert os.path.realpath(sys.executable) in data["hint"]
    elif access == "scoped":
        assert "select or re-select" in data["hint"]
        assert "Full Disk Access" not in data["hint"]
    else:
        assert message in data["message"]


@pytest.mark.parametrize("tool,args,method,source_name", CASES, ids=CASE_IDS)
@pytest.mark.parametrize(
    "error_type,message,access", ERRORS,
    ids=["runtime", "value", "schema", "locked", "helper-query",
         "direct-access", "helper-access"],
)
async def test_primary_failure_propagates(
    stack, caplog, tool, args, method, source_name, error_type, message, access
):
    server, source = stack
    error = error_type(message)
    getattr(source, source_name).side_effect = error

    # Both direct entry points must raise the original exception, not return
    # a list or a dict that a list consumer could mistake for valid data.
    for owner, name in [(server.tools.read_ops, method), (server.tools, tool)]:
        with pytest.raises(error_type) as raised:
            await getattr(owner, name)(**args)
        assert raised.value is error
    await assert_public_failure(server, tool, args, message, access)
    if access is None:
        assert any(
            record.name == read_operations.__name__ and record.exc_info
            for record in caplog.records
        )


@pytest.mark.parametrize("tool,args,method,source_name", CASES, ids=CASE_IDS)
async def test_genuine_empty_read_preserves_shapes(
    stack, tool, args, method, source_name
):
    server, source = stack
    for owner, name in [(server.tools.read_ops, method), (server.tools, tool)]:
        result = await getattr(owner, name)(**args)
        if tool == "get_trash":
            assert result == {
                "items": [], "total_count": 0, "limit": 50,
                "offset": 0, "has_more": False,
            }
        else:
            assert isinstance(result, list)
            assert result == []
            if tool == "get_logbook":
                assert isinstance(result, ListWithTotal)
                assert result.total_count == 0
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, args)
    data = result.structured_content
    assert data["items"] == []
    assert data["count"] == data["total"] == 0
    assert data.get("success") is not False
    assert "error" not in data
    assert getattr(source, source_name).called


class BrokenTag(dict):
    """Fail primary tag-row conversion, not its nested item/count query."""

    def get(self, *args, **kwargs):
        raise RuntimeError("synthetic conversion failure")


@pytest.mark.parametrize("tool,args,method,source_name", CASES, ids=CASE_IDS)
async def test_conversion_failure_after_valid_row(
    stack, tool, args, method, source_name
):
    server, source = stack
    now = datetime.now()
    row = make_todo(
        "valid", "Valid row", created=now.isoformat(),
        stop_date=now.isoformat(), start_date=now.strftime("%Y-%m-%d"),
        deadline=now.strftime("%Y-%m-%d"),
    )
    converter_name = "convert_todo"
    if tool == "get_projects":
        row = make_project("valid", "Valid project")
        converter_name = "convert_project"
    elif tool == "get_areas":
        row = make_area("valid", "Valid area")
        converter_name = "convert_area"
    elif tool == "get_tags":
        row = make_tag("valid", "Work")

    message = "synthetic conversion failure"
    if tool == "get_tags":
        getattr(source, source_name).return_value = [row, BrokenTag()]
        with pytest.raises(RuntimeError, match=message):
            await server.tools.read_ops.get_tags()
        # The first row got as far as its count before the second failed.
        source.todos.assert_called_once_with(tag="Work")
        await assert_public_failure(server, tool, args, message)
        return

    getattr(source, source_name).return_value = [row, dict(row, uuid="broken")]
    real_converter = getattr(ToolsHelpers, converter_name)
    converted = []

    def convert(raw):
        if raw["uuid"] == "broken":
            raise RuntimeError(message)
        result = real_converter(raw)
        converted.append(result)
        return result

    with patch.object(ToolsHelpers, converter_name, side_effect=convert):
        with pytest.raises(RuntimeError, match=message):
            await getattr(server.tools.read_ops, method)(**args)
        assert len(converted) == 1
        assert converted[0]["uuid"] == "valid"
        await assert_public_failure(server, tool, args, message)
        assert len(converted) == 2


@pytest.mark.parametrize("tool,args,method,source_name", CASES, ids=CASE_IDS)
async def test_lazy_import_timeout_is_not_empty(
    stack, monkeypatch, tool, args, method, source_name
):
    server, _ = stack
    monkeypatch.delenv("THINGS_MCP_SCOPED_HELPER_APP", raising=False)
    monkeypatch.setattr(read_operations, "things", LazyThingsProxy())
    message = "synthetic import timeout"
    with patch(
        "things_mcp.things_import.get_things",
        side_effect=ThingsImportTimeoutError(message),
    ):
        with pytest.raises(ThingsImportTimeoutError, match=message):
            await getattr(server.tools.read_ops, method)(**args)
        await assert_public_failure(server, tool, args, message)


async def test_unknown_tag_source_rejection_retains_suggestions(stack):
    server, source = stack
    source.todos.side_effect = ValueError("Unrecognized tag type: 'WORK'")
    source.tags.return_value = [make_tag("work-id", "Work")]
    direct = await server.tools.read_ops.get_tagged_items("WORK")
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_tagged_items", {"tag": "WORK"})
    assert result.structured_content == direct
    assert direct["success"] is False
    assert direct["error"] == "unknown_tag"
    assert direct["tag"] == "WORK"
    assert direct["suggestions"] == ["Work"]


@pytest.mark.parametrize(
    "message", ["unrelated conversion value", "Unrecognized tag type"]
)
async def test_tag_conversion_value_error_is_not_unknown_tag(stack, message):
    server, source = stack
    source.todos.return_value = [make_todo("valid", "Valid", tags=["Work"])]
    source.tags.return_value = [make_tag("work-id", "Work")]
    with patch.object(
        ToolsHelpers, "convert_todo", side_effect=ValueError(message)
    ):
        with pytest.raises(ValueError, match=message):
            await server.tools.get_tagged_items("Work")
        await assert_public_failure(
            server, "get_tagged_items", {"tag": "Work"}, message
        )
    source.tags.assert_not_called()


async def test_invalid_todo_status_still_short_circuits_source(stack):
    server, source = stack
    direct = await server.tools.get_todos(status="bogus")
    assert direct["error"] == "invalid_status"
    assert direct["success"] is False
    async with Client(server.mcp) as client:
        result = await client.call_tool("get_todos", {"status": "bogus"})
    assert result.structured_content["error"] == "invalid_status"
    source.todos.assert_not_called()
