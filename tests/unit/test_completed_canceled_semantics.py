"""Unit tests for hq-f0w.22: align completed/canceled semantics across
update_todo, bulk_update_todos and update_project, and add strict true/false
parsing at the server.py boundary.

Before this bead, `_build_update_script` (the update_todo AppleScript
builder in scheduling/todo_operations.py) treated `canceled=False` alone
(with `completed` omitted) as a silent no-op, while `update_project` (from
hq-f0w.11) already reopened the project in that same case. This file locks
in the now-unified precedence table across all three write tools:

  completed        canceled         -> status statement emitted
  ----------------------------------------------------------------
  (any/omitted)     True             -> canceled   (canceled always wins)
  True              None/omitted     -> completed
  False             None/omitted     -> open
  None/omitted      False            -> open        (was a no-op pre-fix)
  None/omitted      None/omitted     -> (no status statement; unchanged)

It also locks in strict server.py boolean parsing for completed/canceled:
only an actual bool or the strings 'true'/'false' (case-insensitive,
surrounding whitespace stripped - e.g. 'TRUE ' IS accepted) are accepted;
anything else (e.g. 'yes', '1', 'truex') is rejected with a structured
{"success": False, "error": "VALIDATION_ERROR", "field": ...,
"message": ...} response, matching the hq-nxu.9 write-tool error shape.
Before this fix, server.py used `value.lower() == 'true'`, which silently
turned any non-'true' string (including 'yes'/'1') into False and could
reopen an item that was supposed to stay completed/canceled.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock

from fastmcp import Client

from things_mcp.scheduling.todo_operations import TodoOperations
from things_mcp.tools_helpers.bulk_operations import BulkOperations
from things_mcp.server import ThingsMCPServer, _parse_strict_bool, _StrictBoolError


# ---------------------------------------------------------------------------
# update_todo (_build_update_script) status precedence
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_applescript_manager():
    """Mock AppleScript manager that captures the script and reports success."""
    manager = Mock()
    manager.execute_applescript = AsyncMock(return_value={
        "success": True,
        "output": "updated",
    })
    manager.auth_token = None
    return manager


@pytest.fixture
def todo_operations(mock_applescript_manager):
    """TodoOperations instance with a mocked AppleScript manager."""
    return TodoOperations(mock_applescript_manager, Mock())


def _rendered_script(mock_applescript_manager) -> str:
    """Return the AppleScript string passed to execute_applescript."""
    mock_applescript_manager.execute_applescript.assert_called_once()
    args, kwargs = mock_applescript_manager.execute_applescript.call_args
    return args[0] if args else kwargs["script"]


class TestUpdateTodoCanceledFalseAlone:
    """The core regression: canceled=False alone must reopen the todo,
    not be a silent no-op."""

    @pytest.mark.asyncio
    async def test_canceled_false_alone_sets_status_open(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_todo("TODO-1", canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to open" in script

    @pytest.mark.asyncio
    async def test_canceled_true_sets_status_canceled(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_todo("TODO-1", canceled=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to canceled" in script

    @pytest.mark.asyncio
    async def test_completed_true_sets_status_completed(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_todo("TODO-1", completed=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to completed" in script

    @pytest.mark.asyncio
    async def test_completed_false_sets_status_open(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_todo("TODO-1", completed=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to open" in script

    @pytest.mark.asyncio
    async def test_both_none_emits_no_status_statement(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_todo("TODO-1", title="New Title")

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo" not in script


class TestUpdateTodoStatusPrecedence:
    """canceled takes precedence over completed when both are given, matching
    update_project's precedence."""

    @pytest.mark.asyncio
    async def test_canceled_true_wins_over_completed_true(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_todo("TODO-1", completed=True, canceled=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to canceled" in script
        assert script.count("set status of targetTodo to completed") == 0

    @pytest.mark.asyncio
    async def test_canceled_true_wins_over_completed_false(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_todo("TODO-1", completed=False, canceled=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to canceled" in script
        assert script.count("set status of targetTodo to open") == 0

    @pytest.mark.asyncio
    async def test_completed_true_wins_over_canceled_false(self, todo_operations, mock_applescript_manager):
        """completed=True, canceled=False -> completed (canceled=False is only
        the reopen signal when completed is NOT given; here completed decides)."""
        result = await todo_operations.update_todo("TODO-1", completed=True, canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to completed" in script
        assert script.count("set status of targetTodo to open") == 0

    @pytest.mark.asyncio
    async def test_completed_false_and_canceled_false_sets_status_open(self, todo_operations, mock_applescript_manager):
        """completed=False, canceled=False -> open (both agree on reopening)."""
        result = await todo_operations.update_todo("TODO-1", completed=False, canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to open" in script
        assert script.count("set status of targetTodo to canceled") == 0


# ---------------------------------------------------------------------------
# bulk_update_todos (_build_bulk_update_script) status precedence
# ---------------------------------------------------------------------------

@pytest.fixture
def bulk_ops(mock_applescript_manager):
    """BulkOperations instance with a mocked AppleScript manager."""
    return BulkOperations(mock_applescript_manager, Mock())


class TestBulkUpdateTodosCanceledFalseAlone:
    """Regression tests locking in bulk_update_todos's status precedence as
    part of the now-unified three-tool semantics (hq-f0w.22 review gap 1):
    _build_bulk_update_script originally checked `canceled is not None` before
    `completed`, so bulk_update_todos(completed=True, canceled=False) wrongly
    emitted 'open' instead of 'completed' - inconsistent with update_todo/
    update_project, where completed decides whenever canceled is not True.
    Reordered to match: canceled truthy wins outright; otherwise completed
    (if given) decides; otherwise canceled=False alone reopens."""

    @pytest.mark.asyncio
    async def test_canceled_false_alone_sets_status_open(self, bulk_ops, mock_applescript_manager):
        result = await bulk_ops.bulk_update_todos(["TODO-1", "TODO-2"], canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to open" in script

    @pytest.mark.asyncio
    async def test_canceled_true_wins_over_completed_true(self, bulk_ops, mock_applescript_manager):
        result = await bulk_ops.bulk_update_todos(["TODO-1"], completed=True, canceled=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to canceled" in script
        assert script.count("set status of targetTodo to completed") == 0

    @pytest.mark.asyncio
    async def test_completed_false_sets_status_open(self, bulk_ops, mock_applescript_manager):
        result = await bulk_ops.bulk_update_todos(["TODO-1"], completed=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to open" in script

    @pytest.mark.asyncio
    async def test_completed_true_wins_over_canceled_false(self, bulk_ops, mock_applescript_manager):
        """The exact bug from review gap 1: completed=True, canceled=False
        must emit 'completed', not 'open'."""
        result = await bulk_ops.bulk_update_todos(["TODO-1"], completed=True, canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to completed" in script
        assert script.count("set status of targetTodo to open") == 0

    @pytest.mark.asyncio
    async def test_completed_false_and_canceled_false_sets_status_open(self, bulk_ops, mock_applescript_manager):
        """completed=False, canceled=False -> open (both agree on reopening)."""
        result = await bulk_ops.bulk_update_todos(["TODO-1"], completed=False, canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo to open" in script
        assert script.count("set status of targetTodo to canceled") == 0

    @pytest.mark.asyncio
    async def test_both_none_emits_no_status_statement(self, bulk_ops, mock_applescript_manager):
        result = await bulk_ops.bulk_update_todos(["TODO-1"], title="New Title")

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetTodo" not in script


# ---------------------------------------------------------------------------
# server.py strict boolean parsing (_parse_strict_bool)
# ---------------------------------------------------------------------------

class TestParseStrictBoolUnit:
    """Direct unit tests of the _parse_strict_bool helper."""

    def test_none_returns_none(self):
        assert _parse_strict_bool(None, 'completed') is None

    def test_bool_true_passthrough(self):
        assert _parse_strict_bool(True, 'completed') is True

    def test_bool_false_passthrough(self):
        assert _parse_strict_bool(False, 'canceled') is False

    @pytest.mark.parametrize("value", ["true", "True", "TRUE", " true ", "tRuE"])
    def test_true_strings_case_insensitive(self, value):
        assert _parse_strict_bool(value, 'completed') is True

    @pytest.mark.parametrize("value", ["false", "False", "FALSE", " false ", "fAlSe"])
    def test_false_strings_case_insensitive(self, value):
        assert _parse_strict_bool(value, 'canceled') is False

    @pytest.mark.parametrize("value", ["yes", "no", "1", "0", "t", "f", "y", "n", "", "truex"])
    def test_invalid_strings_raise(self, value):
        with pytest.raises(_StrictBoolError) as exc_info:
            _parse_strict_bool(value, 'completed')
        assert exc_info.value.field == 'completed'

    def test_invalid_type_raises(self):
        with pytest.raises(_StrictBoolError):
            _parse_strict_bool(1, 'canceled')


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
    mock_tools.get_todo_by_id = AsyncMock(
        return_value={"uuid": "TODO-1", "type": "to-do", "title": "Receipt todo"}
    )
    for method_name, return_value in overrides.items():
        setattr(mock_tools, method_name, AsyncMock(return_value=return_value))
    server.tools = mock_tools
    return server


class TestUpdateTodoStrictBoolServerLayer:
    """update_todo's MCP tool must reject non-'true'/'false' completed/canceled
    strings with a structured VALIDATION_ERROR, and must never silently treat
    them as False (which previously could reopen a completed/canceled todo)."""

    @pytest.mark.asyncio
    async def test_completed_yes_is_rejected(self):
        server = _make_server_with_mock_tools(
            update_todo={"success": True, "message": "Todo updated successfully"}
        )
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "TODO-1", "completed": "yes"}
            )

        sc = result.structured_content
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "completed"
        server.tools.update_todo.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_canceled_one_is_rejected(self):
        server = _make_server_with_mock_tools(
            update_todo={"success": True, "message": "Todo updated successfully"}
        )
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "TODO-1", "canceled": "1"}
            )

        sc = result.structured_content
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "canceled"
        server.tools.update_todo.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_canceled_false_string_reaches_tools_as_bool_false(self):
        """Regression guard: canceled='false' must reach ThingsTools.update_todo
        as the actual bool False (not silently dropped or coerced to None),
        so the downstream reopen semantics can apply."""
        server = _make_server_with_mock_tools(
            update_todo={"success": True, "message": "Todo updated successfully"}
        )
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_todo", {"id": "TODO-1", "canceled": "false"}
            )

        assert result.structured_content["success"] is True
        server.tools.update_todo.assert_awaited_once()
        _, kwargs = server.tools.update_todo.await_args
        assert kwargs["canceled"] is False


class TestBulkUpdateTodosStrictBoolServerLayer:
    """bulk_update_todos's MCP tool must apply the same strict parsing."""

    @pytest.mark.asyncio
    async def test_completed_yes_is_rejected(self):
        server = _make_server_with_mock_tools(
            bulk_update_todos={"success": True, "updated_count": 2}
        )
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "bulk_update_todos", {"todo_ids": "TODO-1,TODO-2", "completed": "yes"}
            )

        sc = result.structured_content
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "completed"
        assert sc["updated_count"] == 0
        server.tools.bulk_update_todos.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_canceled_false_string_reaches_tools_as_bool_false(self):
        server = _make_server_with_mock_tools(
            bulk_update_todos={"success": True, "updated_count": 2}
        )
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "bulk_update_todos", {"todo_ids": "TODO-1,TODO-2", "canceled": "false"}
            )

        assert result.structured_content["success"] is True
        server.tools.bulk_update_todos.assert_awaited_once()
        _, kwargs = server.tools.bulk_update_todos.await_args
        assert kwargs["canceled"] is False


class TestUpdateProjectStrictBoolServerLayer:
    """update_project's MCP tool must apply the same strict parsing."""

    @pytest.mark.asyncio
    async def test_canceled_one_is_rejected(self):
        server = _make_server_with_mock_tools(
            update_project={"success": True, "message": "Project updated successfully"}
        )
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_project", {"id": "PROJ-1", "canceled": "1"}
            )

        sc = result.structured_content
        assert sc["success"] is False
        assert sc["error"] == "VALIDATION_ERROR"
        assert sc["field"] == "canceled"
        server.tools.update_project.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_canceled_false_string_reaches_tools_as_bool_false(self):
        server = _make_server_with_mock_tools(
            update_project={"success": True, "message": "Project updated successfully"}
        )
        client = Client(server.mcp)
        async with client:
            result = await client.call_tool(
                "update_project", {"id": "PROJ-1", "canceled": "false"}
            )

        assert result.structured_content["success"] is True
        server.tools.update_project.assert_awaited_once()
        _, kwargs = server.tools.update_project.await_args
        assert kwargs["canceled"] is False
