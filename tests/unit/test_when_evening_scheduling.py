"""Unit tests for hq-nxu.10: when='evening'/'tonight' scheduling.

Things 3's AppleScript 'schedule' command has no way to set the "This
Evening" flag (verified against the AppleScript dictionary - 'schedule
... for <date>' only accepts a date object). Only the Things URL scheme
accepts when=evening. This is verified against a real Things 3 install:
a to-do created via `things:///add?when=evening` has startBucket=1 in the
Things sqlite database, vs startBucket=0 for a plain AppleScript
`schedule ... for (current date)` (This Evening vs plain Today), even
though both report the same startDate/'when' timestamp via AppleScript's
_private_experimental_ json property and things.py's start_date field -
startBucket is the only observable signal that distinguishes them.

Covers:
- add_todo(when='evening') routes via the Things URL scheme 'add' action
  (no auth token required for 'add').
- add_todo(when='tonight') is normalized to 'evening' by ParameterValidator
  and behaves identically.
- update_todo(when='evening') routes via the Things URL scheme 'update'
  action and requires the auth token, gated BEFORE any AppleScript write
  (same pattern as heading).
- update_todo(when='evening') without a configured auth token returns a
  structured error with a hint, and does not touch AppleScript at all.
- update_todo(when='evening', title=...) still applies the AppleScript
  field for title while also applying the URL-scheme evening schedule.
- bulk_update_todos(when='evening') requires the auth token upfront
  (checked once, before any AppleScript write across the whole batch) and
  schedules each todo via the URL scheme.
- add_project/update_project reject when='evening' with a structured
  error (Things has no "This Evening" concept for projects).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from things_mcp.scheduling.todo_operations import TodoOperations
from things_mcp.scheduling.strategies import SchedulingStrategies
from things_mcp.tools_helpers.bulk_operations import BulkOperations
from things_mcp.services.applescript_manager import AppleScriptManager, AUTH_TOKEN_HINT


@pytest.fixture(autouse=True)
def fast_url_scheme_polling(monkeypatch):
    """Shrink _add_todo_via_url_scheme's post-create id-lookup poll
    interval/deadline (hq-nxu.12) so tests using the snapshot-then-poll
    execute_applescript side_effect shape run quickly instead of hitting
    the real 3s deadline."""
    monkeypatch.setattr(TodoOperations, "_URL_SCHEME_LOOKUP_POLL_INTERVAL_SECS", 0.01)
    monkeypatch.setattr(TodoOperations, "_URL_SCHEME_LOOKUP_DEADLINE_SECS", 0.05)


def id_lookup_side_effect(new_id):
    """Build an execute_applescript side_effect list for
    _add_todo_via_url_scheme's snapshot-then-poll id lookup (hq-nxu.12):
    the first call is the pre-create snapshot (no existing todo with this
    title), the second is the post-create poll that finds the new id."""
    return [
        {"success": True, "output": ""},
        {"success": True, "output": new_id},
    ]


@pytest.fixture
def mock_applescript_manager():
    """Mock AppleScript manager with a configured auth token."""
    manager = MagicMock(spec=AppleScriptManager)
    manager.auth_token = "test-token-xyz"
    manager.execute_applescript = AsyncMock(return_value={"success": True, "output": "updated"})
    manager.execute_url_scheme = AsyncMock(return_value={
        "success": True,
        "url": "things:///update?id=abc123&when=evening&auth-token=test-token-xyz",
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
    # A real SchedulingStrategies (not a bare Mock()) so when='today' can
    # genuinely take the AppleScript scheduling path in the regression
    # guard test below - schedule_todo_reliable calls back into the same
    # mocked applescript_manager.
    return TodoOperations(mock_applescript_manager, SchedulingStrategies(mock_applescript_manager))


@pytest.fixture
def ops_no_token(mock_applescript_manager_no_token):
    return TodoOperations(mock_applescript_manager_no_token, SchedulingStrategies(mock_applescript_manager_no_token))


class TestAddTodoEvening:
    """add_todo(when='evening') routes via the Things URL scheme 'add' action."""

    @pytest.mark.asyncio
    async def test_add_todo_evening_uses_url_scheme(self, ops, mock_applescript_manager):
        mock_applescript_manager.execute_url_scheme.return_value = {
            "success": True,
            "url": "things:///add?title=evening%20test&when=evening",
        }
        mock_applescript_manager.execute_applescript.side_effect = id_lookup_side_effect("new-todo-id")

        result = await ops.add_todo(title="evening test", when="evening")

        assert result["success"] is True
        assert result["todo_id"] == "new-todo-id"
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        action, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert action == "add"
        assert params["when"] == "evening"

    @pytest.mark.asyncio
    async def test_add_todo_evening_does_not_require_auth_token(self, ops_no_token, mock_applescript_manager_no_token):
        """Unlike update, the URL scheme's 'add' action does not require
        the auth token."""
        mock_applescript_manager_no_token.execute_applescript.side_effect = id_lookup_side_effect("new-todo-id-no-token")

        result = await ops_no_token.add_todo(title="evening test no token", when="evening")

        assert result["success"] is True
        assert result["todo_id"] == "new-todo-id-no-token"
        mock_applescript_manager_no_token.execute_url_scheme.assert_awaited_once()
        action, params = mock_applescript_manager_no_token.execute_url_scheme.await_args.args
        assert action == "add"
        assert params["when"] == "evening"

    @pytest.mark.asyncio
    async def test_add_todo_plain_today_still_uses_applescript(self, ops, mock_applescript_manager):
        """Regression guard: only when='evening' forces the URL-scheme
        route for add_todo - plain 'today' still uses the faster
        AppleScript path."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "new-todo-id",
        }

        result = await ops.add_todo(title="today test", when="today")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()


class TestUpdateTodoEveningWithToken:
    @pytest.mark.asyncio
    async def test_update_todo_evening_only_emits_update_url_with_id_and_when(self, ops, mock_applescript_manager):
        result = await ops.update_todo("abc123", when="evening")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        action, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert action == "update"
        assert params["id"] == "abc123"
        assert params["when"] == "evening"
        # AppleScript write must NOT be issued when when='evening' is the only field.
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_todo_evening_combined_with_title_applies_applescript_field(
        self, ops, mock_applescript_manager
    ):
        result = await ops.update_todo("abc123", when="evening", title="New Title")

        assert result["success"] is True
        mock_applescript_manager.execute_applescript.assert_awaited_once()
        script_arg = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert "New Title" in script_arg
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["when"] == "evening"

    @pytest.mark.asyncio
    async def test_update_todo_evening_combined_with_heading_single_url_call(
        self, ops, mock_applescript_manager
    ):
        """heading and when='evening' together are combined into a single
        things:///update URL rather than two separate calls."""
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "to-do", "project": "PROJECT1"}), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   return_value=[{"title": "Research"}]):
            result = await ops.update_todo("abc123", when="evening", heading="Research")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["when"] == "evening"
        assert params["heading"] == "Research"

    @pytest.mark.asyncio
    async def test_update_todo_tonight_normalizes_and_uses_url_scheme(self, ops, mock_applescript_manager):
        """'tonight' reaches TodoOperations already normalized to 'evening'
        by ParameterValidator (server.py / write_operations.py validate
        upstream) - TodoOperations itself only recognizes the canonical
        'evening' spelling, so this test drives the real normalization
        helper (ParameterValidator.validate_date_format) rather than typing
        'evening' by hand, so it would fail if that normalization ever
        regressed (e.g. server.py discarding the normalized return value -
        see hq-nxu.10 review gap)."""
        from things_mcp.parameter_validator import ParameterValidator

        normalized_when = ParameterValidator.validate_date_format(
            "tonight", "when", allow_relative=True
        )
        assert normalized_when == "evening"

        result = await ops.update_todo("abc123", when=normalized_when)
        assert result["success"] is True
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["when"] == "evening"


class TestUpdateTodoEveningNoToken:
    @pytest.mark.asyncio
    async def test_update_todo_evening_without_token_returns_structured_error(
        self, ops_no_token, mock_applescript_manager_no_token
    ):
        result = await ops_no_token.update_todo("abc123", when="evening")

        assert result["success"] is False
        assert result["error"] == "AUTH_TOKEN_NOT_CONFIGURED"
        assert result["message"] == "Things URL-scheme auth token not configured"
        assert result["hint"] == AUTH_TOKEN_HINT
        # No AppleScript write at all - nothing partially applied.
        mock_applescript_manager_no_token.execute_applescript.assert_not_awaited()
        mock_applescript_manager_no_token.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_todo_evening_with_other_fields_without_token_applies_nothing(
        self, ops_no_token, mock_applescript_manager_no_token
    ):
        """The auth-token gate runs before any write, so title is not
        applied either when when='evening' fails the gate."""
        result = await ops_no_token.update_todo("abc123", when="evening", title="Should not apply")

        assert result["success"] is False
        mock_applescript_manager_no_token.execute_applescript.assert_not_awaited()


class TestUpdateProjectEveningRejected:
    @pytest.mark.asyncio
    async def test_add_project_evening_rejected(self, mock_applescript_manager):
        ops = TodoOperations(mock_applescript_manager, Mock())
        result = await ops.add_project(title="proj", when="evening")

        assert result["success"] is False
        assert result["error"] == "UNSUPPORTED_FOR_PROJECTS"
        assert "not supported for projects" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_project_evening_rejected(self, mock_applescript_manager):
        ops = TodoOperations(mock_applescript_manager, Mock())
        result = await ops.update_project("proj123", when="evening")

        assert result["success"] is False
        assert result["error"] == "UNSUPPORTED_FOR_PROJECTS"
        assert "not supported for projects" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()


class TestBulkUpdateTodosEvening:
    @pytest.fixture
    def bulk_ops(self, mock_applescript_manager):
        return BulkOperations(mock_applescript_manager, Mock())

    @pytest.fixture
    def bulk_ops_no_token(self, mock_applescript_manager_no_token):
        return BulkOperations(mock_applescript_manager_no_token, Mock())

    @pytest.mark.asyncio
    async def test_bulk_update_evening_schedules_each_todo_via_url_scheme(
        self, bulk_ops, mock_applescript_manager
    ):
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "successCount:2, errors:{}",
        }

        result = await bulk_ops.bulk_update_todos(todo_ids=["id1", "id2"], when="evening")

        assert result["success"] is True
        # One URL-scheme 'update' call per todo.
        assert mock_applescript_manager.execute_url_scheme.await_count == 2
        for call in mock_applescript_manager.execute_url_scheme.await_args_list:
            action, params = call.args
            assert action == "update"
            assert params["when"] == "evening"
        assert result["scheduling_info"] == ["id1: scheduled", "id2: scheduled"]

    @pytest.mark.asyncio
    async def test_bulk_update_evening_without_token_returns_structured_error(
        self, bulk_ops_no_token, mock_applescript_manager_no_token
    ):
        result = await bulk_ops_no_token.bulk_update_todos(todo_ids=["id1", "id2"], when="evening")

        assert result["success"] is False
        assert result["error"] == "AUTH_TOKEN_NOT_CONFIGURED"
        assert result["message"] == "Things URL-scheme auth token not configured"
        assert result["hint"] == AUTH_TOKEN_HINT
        # Checked BEFORE any AppleScript write across the whole batch.
        mock_applescript_manager_no_token.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_bulk_update_today_unaffected_uses_scheduler(self, bulk_ops, mock_applescript_manager):
        """Regression guard: plain 'today' still uses schedule_todo_reliable
        (via the injected scheduler mock), not the URL scheme."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "successCount:1, errors:{}",
        }
        scheduler_mock = AsyncMock()
        scheduler_mock.schedule_todo_reliable = AsyncMock(return_value={"success": True})
        bulk_ops.reliable_scheduler = scheduler_mock

        result = await bulk_ops.bulk_update_todos(todo_ids=["id1"], when="today")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()
        scheduler_mock.schedule_todo_reliable.assert_awaited_once_with("id1", "today")
