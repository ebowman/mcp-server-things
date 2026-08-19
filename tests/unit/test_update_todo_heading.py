"""Unit tests for hq-f0w.7: update_todo(heading=...) moves an existing
to-do under a heading via the Things URL scheme (things:///update).

Covers:
- heading=... with auth token configured emits a things:///update URL
  with id + heading + auth-token, and reports success.
- heading=... with no auth token configured -> structured error (with
  hint), no AppleScript write is issued (fields not partially applied).
- heading combined with title/notes still applies the AppleScript fields
  (in addition to the URL-scheme heading move).
- heading='' is rejected outright with a structured error.
- heading + list_id includes 'list-id' in the URL params.
- heading not found in the target project surfaces a warning.
- to-do with no project and no list_id surfaces a warning.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from things_mcp.scheduling.todo_operations import TodoOperations
from things_mcp.services.applescript_manager import AppleScriptManager, AUTH_TOKEN_HINT


@pytest.fixture
def mock_applescript_manager():
    """Mock AppleScript manager with a configured auth token."""
    manager = MagicMock(spec=AppleScriptManager)
    manager.auth_token = "test-token-xyz"
    manager.execute_applescript = AsyncMock(return_value={"success": True, "output": "updated"})
    manager.execute_url_scheme = AsyncMock(return_value={
        "success": True,
        "url": "things:///update?id=abc123&heading=Research&auth-token=test-token-xyz",
        "message": "Successfully executed update action",
    })
    return manager


@pytest.fixture
def mock_applescript_manager_no_token():
    """Mock AppleScript manager with no auth token configured - mimics the
    real AppleScriptManager.execute_url_scheme auth-gate behaviour."""
    manager = MagicMock(spec=AppleScriptManager)
    manager.auth_token = None
    manager.execute_applescript = AsyncMock(return_value={"success": True, "output": "updated"})

    async def fake_execute_url_scheme(action, parameters=None):
        if action in {"update", "update-project"}:
            return {
                "success": False,
                "error": "AUTH_TOKEN_NOT_CONFIGURED",
                "message": "Things URL-scheme auth token not configured",
                "hint": AUTH_TOKEN_HINT,
            }
        return {"success": True, "url": f"things:///{action}"}

    manager.execute_url_scheme = AsyncMock(side_effect=fake_execute_url_scheme)
    return manager


@pytest.fixture
def ops(mock_applescript_manager):
    return TodoOperations(mock_applescript_manager, Mock())


@pytest.fixture
def ops_no_token(mock_applescript_manager_no_token):
    return TodoOperations(mock_applescript_manager_no_token, Mock())


class TestHeadingWithToken:
    @pytest.mark.asyncio
    async def test_heading_only_emits_update_url_with_id_and_heading(self, ops, mock_applescript_manager):
        def fake_get(record_id):
            if record_id == "abc123":
                return {"type": "to-do", "project": "PROJECT1"}
            return {"type": "project"}

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   return_value=[{"title": "Research"}]):
            result = await ops.update_todo("abc123", heading="Research")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        action, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert action == "update"
        assert params["id"] == "abc123"
        assert params["heading"] == "Research"
        # AppleScript write must NOT be issued when heading is the only field.
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heading_combined_with_title_notes_applies_applescript_fields(
        self, ops, mock_applescript_manager
    ):
        def fake_get(record_id):
            if record_id == "abc123":
                return {"type": "to-do", "project": "PROJECT1"}
            return {"type": "project"}

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   return_value=[{"title": "Research"}]):
            result = await ops.update_todo(
                "abc123", heading="Research", title="New Title", notes="New notes"
            )

        assert result["success"] is True
        # AppleScript write happens for title/notes ...
        mock_applescript_manager.execute_applescript.assert_awaited_once()
        script_arg = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert "New Title" in script_arg
        assert "New notes" in script_arg
        # ... and the URL-scheme heading move also happens.
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["heading"] == "Research"

    @pytest.mark.asyncio
    async def test_heading_with_list_id_includes_list_id_in_url(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project"}), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   return_value=[{"title": "Phase 1"}]):
            result = await ops.update_todo("abc123", heading="Phase 1", list_id="PROJECT99")

        assert result["success"] is True
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["list-id"] == "PROJECT99"
        assert params["heading"] == "Phase 1"

    @pytest.mark.asyncio
    async def test_heading_not_found_in_project_adds_warning(self, ops, mock_applescript_manager):
        def fake_get(record_id):
            if record_id == "abc123":
                return {"type": "to-do", "project": "PROJECT1"}
            return {"type": "project"}

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   return_value=[{"title": "Other Heading"}]):
            result = await ops.update_todo("abc123", heading="Nonexistent")

        assert result["success"] is True
        assert "warnings" in result
        assert any("Nonexistent" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_todo_with_no_project_and_no_list_id_adds_warning(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "to-do", "project": None}):
            result = await ops.update_todo("abc123", heading="Research")

        assert result["success"] is True
        assert "warnings" in result
        assert any("does not appear to belong to a project" in w for w in result["warnings"])


class TestHeadingEmptyStringRejected:
    @pytest.mark.asyncio
    async def test_heading_empty_string_returns_structured_error(self, ops, mock_applescript_manager):
        result = await ops.update_todo("abc123", heading="")

        assert result["success"] is False
        assert result["error"] == "INVALID_HEADING"
        assert "heading cannot be empty" in result["message"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heading_whitespace_only_returns_structured_error(self, ops, mock_applescript_manager):
        result = await ops.update_todo("abc123", heading="   ")

        assert result["success"] is False
        assert result["error"] == "INVALID_HEADING"
        assert "heading cannot be empty" in result["message"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()
        mock_applescript_manager.execute_applescript.assert_not_awaited()


class TestHeadingChildProjectResolution:
    """A to-do whose current parent is itself a heading reports
    project=None from things.py (things/database.py joins PROJECT on
    TASK.project, which is NULL for heading children) - the project only
    appears on the heading record. update_todo must fall back to the
    to-do's heading record's project instead of wrongly warning that the
    to-do doesn't belong to a project."""

    @pytest.mark.asyncio
    async def test_heading_child_resolves_project_via_heading_record(self, ops, mock_applescript_manager):
        def fake_get(record_id):
            if record_id == "abc123":
                return {"type": "to-do", "project": None, "heading": "H1"}
            if record_id == "H1":
                return {"type": "heading", "project": "P1"}
            raise AssertionError(f"unexpected things.get call: {record_id}")

        tasks_calls = []

        def fake_tasks(type=None, project=None, status=None):
            tasks_calls.append((type, project))
            return [{"title": "Other"}]

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get),              patch("things_mcp.scheduling.todo_operations.things.tasks", side_effect=fake_tasks):
            result = await ops.update_todo("abc123", heading="Other")

        assert result["success"] is True
        assert not any(
            "does not appear to belong to a project" in w for w in result.get("warnings", [])
        )
        # _check_heading_exists must have been consulted against the
        # heading record's resolved project (P1), not None.
        assert ("heading", "P1") in tasks_calls

    @pytest.mark.asyncio
    async def test_heading_child_with_headingless_project_still_warns(self, ops, mock_applescript_manager):
        """If the heading record itself also has no resolvable project,
        the "does not appear to belong to a project" warning is still
        correct and must be kept."""
        def fake_get(record_id):
            if record_id == "abc123":
                return {"type": "to-do", "project": None, "heading": "H1"}
            if record_id == "H1":
                return {"type": "heading", "project": None}
            raise AssertionError(f"unexpected things.get call: {record_id}")

        with patch("things_mcp.scheduling.todo_operations.things.get", side_effect=fake_get):
            result = await ops.update_todo("abc123", heading="Other")

        assert result["success"] is True
        assert any("does not appear to belong to a project" in w for w in result["warnings"])


class TestHeadingListIdResolvesToArea:
    @pytest.mark.asyncio
    async def test_list_id_resolving_to_area_adds_warning(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "area"}):
            result = await ops.update_todo("abc123", heading="Research", list_id="AREA1")

        assert result["success"] is True
        assert "warnings" in result
        assert any("resolves to an area" in w for w in result["warnings"])
        # The URL-scheme call still proceeds with list-id + heading -
        # Things itself decides what to do with an area target.
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["list-id"] == "AREA1"
        assert params["heading"] == "Research"


class TestHeadingNoAuthToken:
    @pytest.mark.asyncio
    async def test_heading_without_token_returns_structured_error_with_hint(
        self, ops_no_token, mock_applescript_manager_no_token
    ):
        result = await ops_no_token.update_todo("abc123", heading="Research")

        assert result["success"] is False
        assert result["error"] == "AUTH_TOKEN_NOT_CONFIGURED"
        assert result["message"] == "Things URL-scheme auth token not configured"
        assert "hint" in result and result["hint"]
        mock_applescript_manager_no_token.execute_applescript.assert_not_awaited()
        mock_applescript_manager_no_token.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heading_without_token_does_not_partially_apply_other_fields(
        self, ops_no_token, mock_applescript_manager_no_token
    ):
        """Even when title/notes are provided alongside heading, the auth
        check must happen BEFORE any AppleScript write - nothing should be
        partially applied when the token is missing."""
        result = await ops_no_token.update_todo(
            "abc123", heading="Research", title="New Title", notes="New notes"
        )

        assert result["success"] is False
        mock_applescript_manager_no_token.execute_applescript.assert_not_awaited()


class TestHeadingUrlSchemeFailurePropagatesHint:
    @pytest.mark.asyncio
    async def test_url_scheme_failure_propagates_hint_when_present(self, ops, mock_applescript_manager):
        mock_applescript_manager.execute_url_scheme.return_value = {
            "success": False,
            "error": "AUTH_TOKEN_NOT_CONFIGURED",
            "message": "Things URL-scheme auth token not configured",
            "hint": AUTH_TOKEN_HINT,
        }
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "to-do", "project": "PROJECT1"}), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   return_value=[]):
            result = await ops.update_todo("abc123", heading="Research")

        assert result["success"] is False
        assert result["error"] == "AUTH_TOKEN_NOT_CONFIGURED"
        assert result["hint"] == AUTH_TOKEN_HINT


class TestUpdateTodoWithoutHeadingUnaffected:
    """Regular update_todo calls (no heading) must behave exactly as before -
    single AppleScript write, no URL-scheme call."""

    @pytest.mark.asyncio
    async def test_no_heading_only_uses_applescript(self, ops, mock_applescript_manager):
        result = await ops.update_todo("abc123", title="New Title")

        assert result["success"] is True
        mock_applescript_manager.execute_applescript.assert_awaited_once()
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()
