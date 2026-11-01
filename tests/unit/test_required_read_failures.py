"""Required secondary reads fail the request; optional metadata does not.

Only source calls are mocked: conversion, ReadOperations, ThingsTools and
the in-process MCP boundary are real. No live database or Things writes.
"""

import os
import sqlite3
import sys
from datetime import date
from unittest.mock import MagicMock, call, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from fixtures.things_realistic import (
    make_area,
    make_heading,
    make_project,
    make_tag,
    make_todo,
)
from things_mcp.server import ThingsMCPServer
from things_mcp.things_import import ScopedHelperAccessError
from things_mcp.tools_helpers import read_operations


ERRORS = [
    (RuntimeError, "required query failed", None),
    (sqlite3.OperationalError, "unable to open database file", "direct"),
    (ScopedHelperAccessError, "bookmark revoked", "scoped"),
]
CONTENTS = [
    ("get_todos", True, "todos", make_todo, "checklist_items", "checklist"),
    ("get_projects", True, "projects", make_project, "todos", "todos"),
    ("get_areas", True, "areas", make_area, "projects", "projects"),
    ("get_areas", True, "areas", make_area, "todos", "todos"),
    ("get_tags", True, "tags", make_tag, "todos", "todos"),
    ("get_tags", False, "tags", make_tag, "todos", "count"),
]
CONTENT_IDS = [
    "checklist", "project-todos", "area-projects", "area-todos",
    "tag-items-count", "tag-count-only",
]
MEMBERSHIP = [
    ("get_today", {}, "get_today", "today"),
    ("get_anytime", {}, "get_anytime", "anytime"),
    ("get_upcoming", {}, "get_upcoming", "upcoming"),
    ("get_due_in_days", {"days": 7}, "get_due_in_days", "todos"),
    ("get_activating_in_days", {"days": 7}, "get_activating_in_days", "todos"),
    ("get_upcoming", {"days": 7}, "get_todos_upcoming_in_days", "todos"),
    ("get_someday", {"include_project_tasks": True}, "get_someday", "todos"),
]


@pytest.fixture
def stack():
    source = MagicMock(spec=[
        "todos", "projects", "areas", "tags", "today", "anytime", "upcoming",
        "someday", "tasks", "get", "checklist_items",
    ])
    for name in source._mock_methods:
        getattr(source, name).return_value = []
    source.get.return_value = None
    with patch.object(read_operations, "things", source):
        yield ThingsMCPServer(), source


async def assert_failure(server, tool, args, error, access, method=None):
    """Verify original exceptions internally and existing public envelopes."""
    for owner, name in [
        (server.tools.read_ops, method or tool), (server.tools, tool),
    ]:
        with pytest.raises(type(error)) as raised:
            await getattr(owner, name)(**args)
        assert raised.value is error

    async with Client(server.mcp) as client:
        # These two tools already use structured generic errors.
        if access is None and tool not in {
            "get_due_in_days", "get_activating_in_days",
        }:
            with pytest.raises(ToolError, match=str(error)):
                await client.call_tool(tool, args)
            return
        result = await client.call_tool(tool, args)
    data = result.structured_content
    assert data["success"] is False
    assert data["error"] == (
        "database_access_denied" if access else "internal_error"
    )
    if tool not in {"get_due_in_days", "get_activating_in_days"}:
        assert "items" not in data
    if access == "direct":
        assert "Full Disk Access" in data["hint"]
        assert os.path.realpath(sys.executable) in data["hint"]
    elif access == "scoped":
        assert "select or re-select" in data["hint"]
        assert "Full Disk Access" not in data["hint"]
    else:
        assert str(error) in data["message"]


@pytest.mark.parametrize(
    "tool,include,primary,factory,nested,field", CONTENTS, ids=CONTENT_IDS,
)
@pytest.mark.parametrize("later", [False, True], ids=["first", "later"])
@pytest.mark.parametrize("error_type,message,access", ERRORS)
async def test_required_contents_and_counts_fail(
    stack, tool, include, primary, factory, nested, field,
    later, error_type, message, access,
):
    server, source = stack
    getattr(source, primary).return_value = [
        factory("first", "First"), factory("second", "Second"),
    ]
    error = error_type(message)
    successful = []

    def query(*args, **kwargs):
        container = args[0] if args else next(iter(kwargs.values()))
        if later and container in ("first", "First"):
            successful.append(container)
            if nested == "checklist_items":
                return [{"title": "Checked", "status": "completed"}]
            return [make_todo("child", "Child")]
        raise error

    getattr(source, nested).side_effect = query
    if tool == "get_areas" and nested == "todos":
        source.projects.return_value = [make_project("project", "Project")]
    await assert_failure(
        server, tool, {"include_items": include}, error, access,
    )
    assert len(successful) == (3 if later else 0)
    if tool == "get_areas" and nested == "todos":
        # Even the first todo failure occurs after a successful project query.
        assert source.projects.call_args_list[0] == call(area="first")


@pytest.mark.parametrize(
    "tool,include,primary,factory,nested,field", CONTENTS, ids=CONTENT_IDS,
)
async def test_successful_empty_nested_contents(
    stack, tool, include, primary, factory, nested, field,
):
    server, source = stack
    getattr(source, primary).return_value = [factory("parent", "Parent")]
    args = {"include_items": include}
    direct = await getattr(server.tools, tool)(**args)
    assert direct[0][field] == (0 if field == "count" else [])
    if tool == "get_tags":
        assert direct[0]["count"] == 0
        assert ("todos" in direct[0]) is include
    if tool == "get_areas":
        assert direct[0]["projects"] == direct[0]["todos"] == []
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, args)
    assert result.structured_content["items"][0][field] == direct[0][field]
    assert result.structured_content["total"] == 1


@pytest.mark.parametrize("tool,primary,factory", [
    ("get_todos", "todos", make_todo),
    ("get_projects", "projects", make_project),
    ("get_areas", "areas", make_area),
    ("get_tags", "tags", make_tag),
])
async def test_include_items_false_requests_only_primary_and_tag_counts(
    stack, tool, primary, factory,
):
    server, source = stack
    getattr(source, primary).return_value = [factory("parent", "Parent")]
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, {"include_items": False})
    assert len(result.structured_content["items"]) == 1
    expected = (
        [call.todos(status="incomplete")] if tool == "get_todos"
        else [getattr(call, primary)()]
    )
    if tool == "get_tags":
        expected.append(call.todos(tag="Parent"))
    assert source.mock_calls == expected


def membership_rows(source):
    today = date.today().isoformat()
    rows = [
        make_todo("standalone", "Standalone",
                  start_date=today, deadline=today),
        make_todo("direct", "Direct", project="someday",
                  start_date=today, deadline=today),
        make_todo("heading-child", "Heading child", heading="heading",
                  start_date=today, deadline=today),
    ]
    source.projects.return_value = [
        make_project("someday", "Someday", start="Someday"),
    ]
    source.get.return_value = make_heading(
        "heading", "Heading", project="someday", project_title="Someday",
    )
    source.someday.return_value = [make_todo("native", "Native")]
    return rows


@pytest.mark.parametrize("tool,args,method,primary", MEMBERSHIP)
@pytest.mark.parametrize("lookup", ["projects", "get"])
@pytest.mark.parametrize("error_type,message,access", ERRORS)
async def test_required_membership_failure(
    stack, tool, args, method, primary, lookup, error_type, message, access,
):
    server, source = stack
    getattr(source, primary).return_value = membership_rows(source)
    error = error_type(message)
    getattr(source, lookup).side_effect = error
    await assert_failure(server, tool, args, error, access, method)
    source.projects.assert_called_with(start="Someday")
    if lookup == "get":
        # Direct membership was successfully determined before heading failed.
        source.get.assert_called_with("heading")


@pytest.mark.parametrize("error_type,message,access", ERRORS)
async def test_requested_inherited_todos_failure(
    stack, error_type, message, access,
):
    server, source = stack
    membership_rows(source)
    error = error_type(message)
    source.todos.side_effect = error
    await assert_failure(
        server, "get_someday", {"include_project_tasks": True}, error, access,
    )
    source.todos.assert_called_with(status="incomplete")


@pytest.mark.parametrize("tool,args,method,primary", MEMBERSHIP)
async def test_direct_and_heading_someday_membership(
    stack, tool, args, method, primary,
):
    server, source = stack
    getattr(source, primary).return_value = membership_rows(source)
    async with Client(server.mcp) as client:
        result = await client.call_tool(tool, args)
    items = result.structured_content["items"]
    if tool == "get_someday":
        assert {item["uuid"] for item in items} == {
            "native", "direct", "heading-child",
        }
        assert all(item["inheritedSomeday"] for item in items[1:])
    else:
        assert [item["uuid"] for item in items] == ["standalone"]
    source.get.assert_called_once_with("heading")


@pytest.mark.parametrize("tool,args,method,primary", MEMBERSHIP)
@pytest.mark.parametrize("empty", [[], None])
async def test_no_someday_projects_is_a_noop(
    stack, tool, args, method, primary, empty,
):
    server, source = stack
    getattr(source, primary).return_value = membership_rows(source)
    source.projects.return_value = empty
    result = await getattr(server.tools, tool)(**args)
    assert len(result) == (1 if tool == "get_someday" else 3)
    source.get.assert_not_called()
    if tool == "get_someday":
        source.todos.assert_not_called()


@pytest.mark.parametrize("heading", [None, {}, {"uuid": "heading"}])
@pytest.mark.parametrize("tool", ["get_today", "get_someday"])
async def test_successfully_missing_heading_retains_absence(
    stack, heading, tool,
):
    server, source = stack
    rows = membership_rows(source)
    source.get.return_value = heading
    source.today.return_value = rows
    source.todos.return_value = rows
    args = {"include_project_tasks": True} if tool == "get_someday" else {}
    result = await getattr(server.tools, tool)(**args)
    assert {item["uuid"] for item in result} == (
        {"native", "direct"} if tool == "get_someday"
        else {"standalone", "heading-child"}
    )


@pytest.mark.parametrize("empty", [[], None])
async def test_successfully_empty_inherited_todos(stack, empty):
    server, source = stack
    membership_rows(source)
    source.todos.return_value = empty
    result = await server.tools.get_someday(include_project_tasks=True)
    assert [item["uuid"] for item in result] == ["native"]
    source.get.assert_not_called()


async def test_inherited_tasks_opt_out_skips_membership_and_todos(stack):
    server, source = stack
    membership_rows(source)
    result = await server.tools.get_someday(include_project_tasks=False)
    assert [item["uuid"] for item in result] == ["native"]
    source.projects.assert_not_called()
    source.todos.assert_not_called()
    source.get.assert_not_called()


@pytest.mark.parametrize("error_type,message,access", ERRORS)
async def test_optional_heading_failure_keeps_requested_children(
    stack, error_type, message, access,
):
    server, source = stack
    source.projects.return_value = [make_project("parent", "Parent")]
    source.todos.return_value = [
        make_todo("child", "Child", heading="heading"),
    ]
    source.tasks.side_effect = error_type(message)
    async with Client(server.mcp) as client:
        result = await client.call_tool(
            "get_projects", {"include_items": True},
        )
    child = result.structured_content["items"][0]["todos"][0]
    assert child["uuid"] == "child"
    assert child["project"] is None
    source.tasks.assert_called_once_with(type="heading", status=None)


@pytest.mark.parametrize("error_type,message,access", ERRORS)
async def test_optional_single_item_failures_keep_item(
    stack, error_type, message, access,
):
    server, source = stack
    row = make_todo(
        "child", "Child", project="parent",
        start_date=date.today().isoformat(),
    )
    error = error_type(message)

    def get(uuid):
        if uuid == "child":
            return row
        raise error

    source.get.side_effect = get
    with patch.object(
        read_operations.ReadOperations, "_read_start_bucket",
        side_effect=error,
    ) as bucket:
        result = await server.tools.get_todo_by_id("child")
    assert result["uuid"] == "child"
    assert result["checklist"] == []
    assert "evening" not in result
    assert "trashedViaParent" not in result
    source.get.assert_has_calls([call("child"), call("parent")])
    bucket.assert_called_once_with("child")
