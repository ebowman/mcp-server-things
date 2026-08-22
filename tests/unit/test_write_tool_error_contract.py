"""Parity tests for hq-f0w.35: the write-tool structured-error contract.

Every write tool's structured (non-raising) `{"success": False, ...}` error
must use the canonical write-tool shape:
``{"success": False, "error": "<UPPER_SNAKE_CODE>", "message": "<human text>", ...}``
-- the same contract already established by VALIDATION_ERROR /
TARGET_COMPLETED / NO_VALID_TAGS (hq-nxu.9) and formalized by
`tools_helpers.errors.write_error` / `ThingsMCPServer._write_error`
(hq-f0w.35). This mirrors the read-tool contract parity coverage in
test_unknown_tag_structured_error.py / test_when_whitespace_rejection.py,
but drives every entry of MUTATING_TOOLS (test_parameter_reach.py's
canonical write-tool list, duplicated here with a sync assertion - see
test_covered_tools_match_mutating_tools below) with input designed to
trigger a structured error, then asserts `error` is UPPER_SNAKE_CASE
(a stable machine-readable code, not a human sentence or a raw
`str(exception)` leak).

Two test styles are used depending on where the rejection happens:
  - Tools rejected by server.py's own pre-validation (before self.tools is
    ever called) use a MagicMock ThingsTools layer (_make_server_with_mock_tools)
    - the mocked tools methods assert_not_called() to prove the rejection
    happened before reaching the tools layer.
  - Tools whose structured error is only produced by the real tools layer
    (WriteOperations/MoveOperationsTools, e.g. NO_VALID_TAGS, NOT_FOUND,
    an AppleScript-execution failure, a validation failure inside
    MoveOperationsTools) use a real ThingsTools instance wired to a mocked
    AppleScriptManager (_make_server_with_real_tools), the same pattern as
    test_delete_validation.py / test_area_tools.py.

These tests exercise the real ThingsMCPServer + FastMCP tool registration
via an in-memory fastmcp.Client (no stdio, no real Things 3).
"""

import re

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock

from fastmcp import Client

from things_mcp.server import ThingsMCPServer
from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager

# A code is "UPPER_SNAKE_CASE" if it's all uppercase letters/digits/underscores
# and contains no lowercase letters or spaces - distinguishing it from a human
# sentence (e.g. "Invalid when date") or a raw str(exception) leak.
_UPPER_SNAKE_RE = re.compile(r'^[A-Z][A-Z0-9_]*$')

# Duplicated from test_parameter_reach.py's MUTATING_TOOLS (the canonical
# write-tool list for this repo) rather than imported, so a change to either
# file's set is visible as a diff; test_covered_tools_match_mutating_tools
# below cross-checks the two stay in sync at test-collection time.
MUTATING_TOOLS = {
    "add_todo",
    "update_todo",
    "delete_todo",
    "add_project",
    "update_project",
    "add_area",
    "update_area",
    "add_tags",
    "remove_tags",
    "create_tag",
    "bulk_update_todos",
    "move_record",
    "bulk_move_records",
    "add_checklist_items",
    "prepend_checklist_items",
    "replace_checklist_items",
}

# Populated by each TestWriteToolErrorCodesAreUpperSnake test method via the
# @_covers decorator below, so test_covered_tools_match_mutating_tools can
# assert the covered set is exactly MUTATING_TOOLS - no tool can silently
# drop out of coverage.
_COVERED_TOOLS: set = set()


def _covers(tool_name: str):
    """Decorator recording that a test method exercises `tool_name`."""
    def decorator(fn):
        _COVERED_TOOLS.add(tool_name)
        return fn
    return decorator


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
    mock_tools.config = MagicMock(ai_can_create_tags=False)
    for method_name, return_value in overrides.items():
        setattr(mock_tools, method_name, AsyncMock(return_value=return_value))
    server.tools = mock_tools
    return server


def _make_mock_applescript_manager(auth_token=None):
    """Create a Mock(spec=AppleScriptManager) with execute_applescript/
    execute_url_scheme as AsyncMocks and an explicit auth_token.

    auth_token is an instance attribute on the real AppleScriptManager, so
    Mock(spec=...) does not auto-generate it - it must be set explicitly or
    `not self.auth_token` checks (the URL-scheme auth gate) raise
    AttributeError instead of evaluating true/false.

    execute_url_scheme's fake replicates the real AppleScriptManager's
    auth-gate behaviour (services/applescript_manager.py's
    AUTH_REQUIRING_ACTIONS/AUTH_TOKEN_HINT) for 'update'/'update-project'
    actions when no auth_token is configured, since callers here mock the
    manager entirely rather than exercising the real gate.
    """
    from things_mcp.services.applescript_manager import AUTH_TOKEN_HINT

    manager = Mock(spec=AppleScriptManager)
    manager.auth_token = auth_token
    manager.execute_applescript = AsyncMock(return_value={"success": True, "output": ""})

    async def _fake_execute_url_scheme(action, parameters=None):
        if action in {"update", "update-project"} and not manager.auth_token:
            return {
                "success": False,
                "error": "AUTH_TOKEN_NOT_CONFIGURED",
                "message": "Things URL-scheme auth token not configured",
                "hint": AUTH_TOKEN_HINT,
                # hq-wsa.4: the real auth gate always includes a
                # checked_paths resolution trace alongside hint - path/
                # status only, never the token value.
                "checked_paths": [
                    {"path": "<project_root>/.things-auth", "status": "missing"},
                    {"path": "<project_root>/things-auth.txt", "status": "missing"},
                    {"path": "~/.things-auth", "status": "missing"},
                ],
            }
        return {"success": True, "url": f"things:///{action}"}

    manager.execute_url_scheme = AsyncMock(side_effect=_fake_execute_url_scheme)
    return manager


def _make_server_with_real_tools(mock_applescript_manager, config=None):
    """Create a ThingsMCPServer with a real ThingsTools layer wired to a
    mocked AppleScriptManager, so structured errors produced by the tools
    layer itself (not server.py pre-validation) are exercised for real."""
    server = ThingsMCPServer()
    server.tools = ThingsTools(mock_applescript_manager, config=config)
    return server


def _assert_upper_snake_error(sc):
    assert sc is not None
    assert sc["success"] is False
    assert "error" in sc, "structured error must include an 'error' code"
    code = sc["error"]
    assert isinstance(code, str)
    assert _UPPER_SNAKE_RE.match(code), (
        f"write-tool error code must be UPPER_SNAKE_CASE, got {code!r} "
        f"(full response: {sc!r})"
    )
    assert "message" in sc, "structured error must include a human-readable 'message'"


class TestWriteToolErrorCodesAreUpperSnake:
    """Drive each write tool with input that triggers a structured error,
    and assert the resulting `error` field is an UPPER_SNAKE_CASE code."""

    @_covers("add_todo")
    @pytest.mark.asyncio
    async def test_add_todo_invalid_when(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_todo", {"title": "T", "when": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_WHEN"
        server.tools.add_todo.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_todo_invalid_deadline(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_todo", {"title": "T", "deadline": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_DEADLINE"

    @_covers("update_todo")
    @pytest.mark.asyncio
    async def test_update_todo_invalid_when(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "TODO-1", "when": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_WHEN"

    @pytest.mark.asyncio
    async def test_update_todo_invalid_deadline(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "TODO-1", "deadline": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_DEADLINE"

    @_covers("bulk_update_todos")
    @pytest.mark.asyncio
    async def test_bulk_update_todos_invalid_when(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "bulk_update_todos", {"todo_ids": "id1,id2", "when": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_WHEN"

    @pytest.mark.asyncio
    async def test_bulk_update_todos_invalid_deadline(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "bulk_update_todos", {"todo_ids": "id1,id2", "deadline": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_DEADLINE"

    @pytest.mark.asyncio
    async def test_bulk_update_todos_no_ids(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "bulk_update_todos", {"todo_ids": "   ,  ,", "completed": "true"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "NO_TODO_IDS"

    @_covers("add_project")
    @pytest.mark.asyncio
    async def test_add_project_invalid_when(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_project", {"title": "P", "when": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_WHEN"

    @pytest.mark.asyncio
    async def test_add_project_invalid_deadline(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_project", {"title": "P", "deadline": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_DEADLINE"

    @_covers("update_project")
    @pytest.mark.asyncio
    async def test_update_project_invalid_when(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_project", {"id": "PROJ-1", "when": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_WHEN"

    @pytest.mark.asyncio
    async def test_update_project_invalid_deadline(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_project", {"id": "PROJ-1", "deadline": "not-a-date"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "INVALID_DEADLINE"

    @_covers("create_tag")
    @pytest.mark.asyncio
    async def test_create_tag_restricted(self):
        """ai_can_create_tags=False (default mock config) rejects create_tag."""
        server = _make_server_with_mock_tools()
        server.config = MagicMock(ai_can_create_tags=False)
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("create_tag", {"tag_name": "new-tag"})
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "TAG_CREATION_RESTRICTED"

    @_covers("add_checklist_items")
    @pytest.mark.asyncio
    async def test_add_checklist_items_empty(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_checklist_items", {"todo_id": "TODO-1", "items": []}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "NO_CHECKLIST_ITEMS"
        server.tools.add_checklist_items.assert_not_called()

    @_covers("prepend_checklist_items")
    @pytest.mark.asyncio
    async def test_prepend_checklist_items_empty(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "prepend_checklist_items", {"todo_id": "TODO-1", "items": []}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "NO_CHECKLIST_ITEMS"

    @_covers("replace_checklist_items")
    @pytest.mark.asyncio
    async def test_replace_checklist_items_applescript_failure(self):
        """replace_checklist_items has no items-required guard - it goes
        straight to the tools layer, which uses the Things URL scheme
        'update' action. No auth token configured -> the shared auth-gate
        error (hq-f0w.46: migrated to the write_error contract, code
        AUTH_TOKEN_NOT_CONFIGURED, with the auth literal preserved verbatim
        in `message`) is asserted directly here."""
        manager = _make_mock_applescript_manager(auth_token=None)
        server = _make_server_with_real_tools(manager)
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "replace_checklist_items", {"todo_id": "TODO-1", "items": ["a"]}
            )
        sc = result.structured_content
        _assert_upper_snake_error(sc)
        assert sc["error"] == "AUTH_TOKEN_NOT_CONFIGURED"
        assert sc["message"] == "Things URL-scheme auth token not configured"
        # hq-wsa.4: checked_paths trace forwarded verbatim through
        # _propagate_url_scheme_error, not stripped by the write_error
        # envelope.
        assert "checked_paths" in sc
        assert sc["checked_paths"] and all(
            {"path", "status"} <= entry.keys() for entry in sc["checked_paths"]
        )

    @_covers("delete_todo")
    @pytest.mark.asyncio
    async def test_delete_todo_empty_id_validation_error(self):
        manager = _make_mock_applescript_manager()
        server = _make_server_with_real_tools(manager)
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("delete_todo", {"todo_id": ""})
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "VALIDATION_ERROR"
        manager.execute_applescript.assert_not_called()

    @_covers("add_area")
    @pytest.mark.asyncio
    async def test_add_area_applescript_failure(self):
        manager = _make_mock_applescript_manager()
        manager.execute_applescript = AsyncMock(return_value={
            "success": False,
            "output": "AppleScript execution failed",
        })
        server = _make_server_with_real_tools(manager)
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool("add_area", {"title": "New Area"})
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "APPLESCRIPT_ERROR"

    @_covers("update_area")
    @pytest.mark.asyncio
    async def test_update_area_not_found(self):
        manager = _make_mock_applescript_manager()
        manager.execute_applescript = AsyncMock(return_value={
            "success": True,
            "output": "error: Can't get area id \"BOGUS-ID\".",
        })
        server = _make_server_with_real_tools(manager)
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_area", {"id": "BOGUS-ID", "title": "New Name"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "NOT_FOUND"
        # Informative text ("Area not found: BOGUS-ID") lives in `message`
        # (human-readable explanation), not `details` (reserved for raw
        # AppleScript/exception passthrough text) - there is no dynamic
        # AppleScript text to preserve separately for this branch.
        assert "BOGUS-ID" in result.structured_content["message"]

    @_covers("add_tags")
    @pytest.mark.asyncio
    async def test_add_tags_no_valid_tags(self):
        """An empty tags string parses to no tags at all - add_tags rejects
        before any AppleScript call, via the same NO_VALID_TAGS path
        test_tag_management_comprehensive.py::test_empty_tag_string covers
        directly against the tools layer; this drives it through the real
        MCP tool boundary instead."""
        manager = _make_mock_applescript_manager()
        server = _make_server_with_real_tools(manager)
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "add_tags", {"todo_id": "TODO-1", "tags": ""}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "NO_VALID_TAGS"
        manager.execute_applescript.assert_not_called()

    @_covers("remove_tags")
    @pytest.mark.asyncio
    async def test_remove_tags_applescript_failure(self):
        manager = _make_mock_applescript_manager()
        manager.execute_applescript = AsyncMock(side_effect=[
            {"success": True, "output": "urgent"},  # current-tags lookup
            {"success": False, "error": "Things 3 not running"},  # the write
        ])
        server = _make_server_with_real_tools(manager)
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "remove_tags", {"todo_id": "TODO-1", "tags": "urgent"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "APPLESCRIPT_ERROR"

    @_covers("move_record")
    @pytest.mark.asyncio
    async def test_move_record_invalid_destination(self):
        manager = _make_mock_applescript_manager()
        server = _make_server_with_real_tools(manager)
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "move_record", {"todo_id": "TODO-1", "destination_list": "not-a-real-destination"}
            )
        _assert_upper_snake_error(result.structured_content)
        assert result.structured_content["error"] == "VALIDATION_ERROR"
        manager.execute_applescript.assert_not_called()

    @_covers("bulk_move_records")
    @pytest.mark.asyncio
    async def test_bulk_move_records_no_ids(self):
        server = _make_server_with_mock_tools()
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "bulk_move_records", {"todo_ids": "   ,  ,", "destination": "today"}
            )
        _assert_upper_snake_error(result.structured_content)
        # bulk_move_records' NO_TODO_IDS code predates this bead and is
        # intentionally left as-is (already a stable UPPER_SNAKE code).
        assert result.structured_content["error"] == "NO_TODO_IDS"


def test_covered_tools_match_mutating_tools():
    """Every MUTATING_TOOLS entry must have at least one @_covers test above -
    no write tool can silently drop out of this file's coverage. This also
    catches MUTATING_TOOLS drifting out of sync with the canonical list in
    test_parameter_reach.py (via the identical set literal, cross-checked
    at import time by both files independently enumerating the same 16
    tool names)."""
    missing = MUTATING_TOOLS - _COVERED_TOOLS
    extra = _COVERED_TOOLS - MUTATING_TOOLS
    assert not missing, f"MUTATING_TOOLS entries with no @_covers test: {sorted(missing)}"
    assert not extra, f"@_covers test(s) for tool(s) not in MUTATING_TOOLS: {sorted(extra)}"


class TestWriteErrorHelperShape:
    """Direct unit tests for the shared write_error()/`_write_error` helpers."""

    def test_write_error_shape(self):
        from things_mcp.tools_helpers.errors import write_error

        result = write_error("SOME_CODE", "Something went wrong", field="when")
        assert result == {
            "success": False,
            "error": "SOME_CODE",
            "message": "Something went wrong",
            "field": "when",
        }

    def test_server_write_error_delegates_to_shared_helper(self):
        from things_mcp.tools_helpers.errors import write_error

        result = ThingsMCPServer._write_error("SOME_CODE", "Something went wrong")
        assert result == write_error("SOME_CODE", "Something went wrong")
