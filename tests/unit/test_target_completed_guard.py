"""Unit tests for hq-f0w.36: writes into a completed/canceled heading or
project are rejected with a structured TARGET_COMPLETED error before any
write happens, instead of silently reopening the target in Things.

Covers:
- add_todo(heading=..., list_id=...) targeting a completed heading ->
  structured error, no AppleScript/URL-scheme write issued.
- update_todo(heading=..., list_id=...) targeting a completed heading ->
  structured error, no AppleScript/URL-scheme write issued.
- add_todo(list_id=...) targeting a completed project (no heading) ->
  structured error, no AppleScript write issued.
- update_todo(list_id=...) targeting a completed project (no heading) ->
  structured error, no AppleScript write issued.
- add_todo(list_id=<completed project>, checklist_items=[...]) (no heading,
  URL-scheme path taken for a reason unrelated to the project target) ->
  structured error, no URL-scheme call issued.
- add_todo(list_id=<completed project>, when='evening') (no heading, same
  URL-scheme path) -> structured error, no URL-scheme call issued.
- Open (incomplete) targets are unaffected - existing heading/list_id
  behavior continues to work.

_check_heading_status's things.tasks() call (unrelated fix, same bead):
things.tasks() defaults to status='incomplete', so a completed heading used
to be invisible there and produced a false "heading not found" warning -
status=None fixes it. The completed-heading tests below use a status-aware
fake_tasks (rather than a flat return_value) so they would fail again if
status=None regressed back to the default - a flat return_value/mock would
silently keep "seeing" the completed heading row even without status=None,
masking exactly the regression this bead fixed.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from things_mcp.scheduling.todo_operations import TodoOperations
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    manager = MagicMock(spec=AppleScriptManager)
    manager.auth_token = "test-token-xyz"
    manager.execute_applescript = AsyncMock(return_value={"success": True, "output": "updated"})
    manager.execute_url_scheme = AsyncMock(return_value={
        "success": True,
        "url": "things:///update?id=abc123",
        "message": "Successfully executed update action",
    })
    return manager


@pytest.fixture
def ops(mock_applescript_manager):
    return TodoOperations(mock_applescript_manager, Mock())


def status_aware_heading_tasks(heading_row):
    """Build a things.tasks() side_effect that only returns `heading_row`
    when called with status=None (things.py's own default is
    status='incomplete', which would hide a completed/canceled heading row)
    - any other status value sees an empty result, same as a real
    status='incomplete' query would for a completed heading. This makes the
    test fail if the production code stops passing status=None explicitly,
    unlike a flat return_value which can't distinguish the two calls."""
    def fake_tasks(type=None, project=None, status='incomplete'):
        if status is None:
            return [heading_row]
        return []
    return fake_tasks


class TestAddTodoCompletedHeading:
    @pytest.mark.asyncio
    async def test_add_todo_heading_completed_returns_structured_error(self, ops, mock_applescript_manager):
        def fake_get(record_id):
            if record_id == "PROJECT1":
                return {"type": "project", "status": "incomplete"}
            raise AssertionError(f"unexpected things.get call: {record_id}")

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   side_effect=status_aware_heading_tasks({"title": "Johan", "status": "completed"})):
            result = await ops.add_todo(title="New task", list_id="PROJECT1", heading="Johan")

        assert result["success"] is False
        assert result["error"] == "TARGET_COMPLETED"
        assert "Johan" in result["message"]
        assert "completed" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_todo_heading_open_is_unaffected(self, ops, mock_applescript_manager):
        """An open (incomplete) heading in an open project must still work
        exactly as before - no TARGET_COMPLETED error, URL-scheme create
        proceeds normally."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {"success": True, "output": ""},
            {"success": True, "output": "new-todo-id"},
        ]

        def fake_get(record_id):
            if record_id == "PROJECT1":
                return {"type": "project", "status": "incomplete"}
            raise AssertionError(f"unexpected things.get call: {record_id}")

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   side_effect=status_aware_heading_tasks({"title": "Johan", "status": "incomplete"})):
            result = await ops.add_todo(title="New task", list_id="PROJECT1", heading="Johan")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_todo_heading_check_queries_things_tasks_with_status_none(
        self, ops, mock_applescript_manager
    ):
        """Explicit call-shape assertion: the heading lookup must pass
        status=None, not rely on things.tasks()'s own status='incomplete'
        default - this is the direct regression test for the
        _check_heading_status fix."""
        calls = []

        def fake_get(record_id):
            if record_id == "PROJECT1":
                return {"type": "project", "status": "incomplete"}
            raise AssertionError(f"unexpected things.get call: {record_id}")

        def fake_tasks(type=None, project=None, status='incomplete'):
            calls.append({"type": type, "project": project, "status": status})
            return [{"title": "Johan", "status": "incomplete"}]

        mock_applescript_manager.execute_applescript.side_effect = [
            {"success": True, "output": ""},
            {"success": True, "output": "new-todo-id"},
        ]

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get), \
             patch("things_mcp.scheduling.todo_operations.things.tasks", side_effect=fake_tasks):
            await ops.add_todo(title="New task", list_id="PROJECT1", heading="Johan")

        assert calls, "things.tasks() was never called for the heading check"
        assert any(c["status"] is None for c in calls), (
            f"expected a things.tasks(..., status=None) call, got: {calls}"
        )


class TestUpdateTodoCompletedHeading:
    @pytest.mark.asyncio
    async def test_update_todo_heading_completed_returns_structured_error(self, ops, mock_applescript_manager):
        def fake_get(record_id):
            if record_id == "abc123":
                return {"type": "to-do", "project": "PROJECT1"}
            if record_id == "PROJECT1":
                return {"type": "project", "status": "incomplete"}
            raise AssertionError(f"unexpected things.get call: {record_id}")

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   side_effect=status_aware_heading_tasks({"title": "Johan", "status": "canceled"})):
            result = await ops.update_todo("abc123", heading="Johan")

        assert result["success"] is False
        assert result["error"] == "TARGET_COMPLETED"
        assert "Johan" in result["message"]
        assert "canceled" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_todo_heading_open_is_unaffected(self, ops, mock_applescript_manager):
        def fake_get(record_id):
            if record_id == "abc123":
                return {"type": "to-do", "project": "PROJECT1"}
            if record_id == "PROJECT1":
                return {"type": "project", "status": "incomplete"}
            raise AssertionError(f"unexpected things.get call: {record_id}")

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   side_effect=status_aware_heading_tasks({"title": "Johan", "status": "incomplete"})):
            result = await ops.update_todo("abc123", heading="Johan")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()


class TestAddTodoCompletedProjectNoHeading:
    @pytest.mark.asyncio
    async def test_add_todo_list_id_completed_project_returns_structured_error(
        self, ops, mock_applescript_manager
    ):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "status": "completed"}):
            result = await ops.add_todo(title="New task", list_id="PROJECT1")

        assert result["success"] is False
        assert result["error"] == "TARGET_COMPLETED"
        assert "completed" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_todo_list_id_open_project_is_unaffected(self, ops, mock_applescript_manager):
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True, "output": "todo-1"
        }
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "status": "incomplete"}):
            result = await ops.add_todo(title="New task", list_id="PROJECT1")

        assert result["success"] is True
        mock_applescript_manager.execute_applescript.assert_awaited_once()


class TestAddTodoCompletedProjectUrlSchemePathNoHeading:
    """GAP 1 (review): add_todo takes the URL-scheme path (not AppleScript)
    whenever checklist_items or when='evening' is given, even with no
    heading. Without a completed-project pre-check specifically on that
    branch, a completed/canceled list_id target would reach
    execute_url_scheme('add') unchecked."""

    @pytest.mark.asyncio
    async def test_add_todo_list_id_completed_project_with_checklist_returns_error(
        self, ops, mock_applescript_manager
    ):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "status": "completed"}):
            result = await ops.add_todo(
                title="New task", list_id="PROJECT1", checklist_items=["Step 1", "Step 2"]
            )

        assert result["success"] is False
        assert result["error"] == "TARGET_COMPLETED"
        assert "completed" in result["message"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_todo_list_id_completed_project_with_evening_returns_error(
        self, ops, mock_applescript_manager
    ):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "status": "completed"}):
            result = await ops.add_todo(title="New task", list_id="PROJECT1", when="evening")

        assert result["success"] is False
        assert result["error"] == "TARGET_COMPLETED"
        assert "completed" in result["message"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_todo_list_id_open_project_with_checklist_is_unaffected(
        self, ops, mock_applescript_manager
    ):
        mock_applescript_manager.execute_applescript.side_effect = [
            {"success": True, "output": ""},
            {"success": True, "output": "new-todo-id"},
        ]
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "status": "incomplete"}):
            result = await ops.add_todo(
                title="New task", list_id="PROJECT1", checklist_items=["Step 1"]
            )

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_todo_list_id_area_with_checklist_is_unaffected(self, ops, mock_applescript_manager):
        """Areas have no completed/canceled status in Things - a list_id
        resolving to an area must never trip TARGET_COMPLETED even on the
        URL-scheme (checklist/evening) path."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {"success": True, "output": ""},
            {"success": True, "output": "new-todo-id"},
        ]
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "area"}):
            result = await ops.add_todo(
                title="New task", list_id="AREA1", checklist_items=["Step 1"]
            )

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()


class TestUpdateTodoCompletedProjectNoHeading:
    @pytest.mark.asyncio
    async def test_update_todo_list_id_completed_project_returns_structured_error(
        self, ops, mock_applescript_manager
    ):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "status": "completed"}):
            result = await ops.update_todo("abc123", list_id="PROJECT1")

        assert result["success"] is False
        assert result["error"] == "TARGET_COMPLETED"
        assert "completed" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_todo_list_id_open_project_is_unaffected(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project", "status": "incomplete"}):
            result = await ops.update_todo("abc123", list_id="PROJECT1")

        assert result["success"] is True
        mock_applescript_manager.execute_applescript.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_todo_list_id_area_is_unaffected(self, ops, mock_applescript_manager):
        """Areas have no completed/canceled status in Things - a list_id
        resolving to an area must never trip TARGET_COMPLETED."""
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "area"}):
            result = await ops.update_todo("abc123", list_id="AREA1")

        assert result["success"] is True
        mock_applescript_manager.execute_applescript.assert_awaited_once()
