"""
Unit tests for hq-nxu.12: URL-scheme post-create id lookup for
TodoOperations._add_todo_via_url_scheme.

The URL scheme (things:///add) does not return the id of the todo it
creates, so _add_todo_via_url_scheme snapshots the set of existing todo
ids with the requested title *before* issuing the URL-scheme call, then
polls (up to a deadline) for a new id (after - before) afterward. This
avoids picking the wrong todo when two todos share a title and are
created within the same 1s AppleScript creation-date granularity, and
avoids silently reporting success without an id.

Covers:
  - Immediate hit: the new id is already present on the first poll.
  - Delayed hit: the new id only appears after a couple of polls.
  - Duplicate titles: more than one new id appears (e.g. a concurrent
    create with the same title) - the newest one is returned, with a
    warning.
  - Timeout: no new id appears before the deadline - success:false with
    an explanatory error, not a silent "Todo ID not available" success.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from things_mcp.scheduling.todo_operations import TodoOperations


def make_applescript_manager(execute_applescript_side_effect, url_scheme_result=None):
    manager = Mock()
    manager.execute_url_scheme = AsyncMock(
        return_value=url_scheme_result or {"success": True, "url": "things:///add", "message": "ok"}
    )
    manager.execute_applescript = AsyncMock(side_effect=execute_applescript_side_effect)
    return manager


def ids_result(ids):
    """Build the execute_applescript-shaped result for a set of ids."""
    return {"success": True, "output": "\n".join(ids)}


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    """Shrink the poll interval/deadline so timeout tests run quickly."""
    monkeypatch.setattr(TodoOperations, "_URL_SCHEME_LOOKUP_POLL_INTERVAL_SECS", 0.01)
    monkeypatch.setattr(TodoOperations, "_URL_SCHEME_LOOKUP_DEADLINE_SECS", 0.05)


class TestImmediateHit:
    @pytest.mark.asyncio
    async def test_new_id_present_on_first_poll(self):
        manager = make_applescript_manager([
            ids_result([]),            # pre-create snapshot: no existing todos
            ids_result(["new-id-1"]),  # first poll: the new todo is already there
        ])
        ops = TodoOperations(manager, Mock())

        result = await ops._add_todo_via_url_scheme("Immediate Hit Todo")

        assert result["success"] is True
        assert result["todo_id"] == "new-id-1"
        assert "warning" not in result
        assert "warnings" not in result


class TestDelayedHit:
    @pytest.mark.asyncio
    async def test_new_id_appears_after_a_few_polls(self):
        manager = make_applescript_manager([
            ids_result([]),            # pre-create snapshot
            ids_result([]),            # poll 1: not there yet
            ids_result([]),            # poll 2: not there yet
            ids_result(["new-id-2"]),  # poll 3: appears
        ])
        ops = TodoOperations(manager, Mock())

        result = await ops._add_todo_via_url_scheme("Delayed Hit Todo")

        assert result["success"] is True
        assert result["todo_id"] == "new-id-2"


class TestDuplicateTitles:
    @pytest.mark.asyncio
    async def test_multiple_new_ids_returns_newest_with_warning(self):
        # Pre-existing todo "existing-id" with the same title is present
        # before the create and must be excluded from the "new" set even
        # though it still shows up in the post-create listing.
        manager = make_applescript_manager([
            ids_result(["existing-id"]),                          # snapshot
            ids_result(["existing-id", "new-id-a", "new-id-b"]),  # poll: two new ids
            {"success": True, "output": "new-id-b"},               # newest-id lookup
        ])
        ops = TodoOperations(manager, Mock())

        result = await ops._add_todo_via_url_scheme("Duplicate Title Todo")

        assert result["success"] is True
        assert result["todo_id"] == "new-id-b"
        assert any("multiple" in w.lower() for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_newest_id_lookup_falls_back_to_last_candidate_on_error(self):
        manager = make_applescript_manager([
            ids_result([]),
            ids_result(["new-id-a", "new-id-b"]),
            {"success": False, "error": "boom"},  # newest-id lookup fails
        ])
        ops = TodoOperations(manager, Mock())

        result = await ops._add_todo_via_url_scheme("Duplicate Title Todo 2")

        assert result["success"] is True
        assert result["todo_id"] == "new-id-b"  # falls back to last candidate
        assert any("multiple" in w.lower() for w in result["warnings"])


class TestTimeout:
    @pytest.mark.asyncio
    async def test_no_new_id_within_deadline_returns_failure(self):
        # Every call (snapshot + every poll) reports the same, unchanged
        # set of ids - the new todo never shows up before the deadline.
        manager = make_applescript_manager(lambda *args, **kwargs: ids_result([]))
        ops = TodoOperations(manager, Mock())

        result = await ops._add_todo_via_url_scheme("Timeout Todo")

        assert result["success"] is False
        assert result["error"] == "CREATE_UNCONFIRMED"
        assert "may still have been created" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_url_scheme_failure_short_circuits_before_lookup(self):
        manager = make_applescript_manager(
            [ids_result([])],
            url_scheme_result={"success": False, "error": "things not running"},
        )
        ops = TodoOperations(manager, Mock())

        result = await ops._add_todo_via_url_scheme("Unreachable Todo")

        assert result["success"] is False
        assert result["error"] == "APPLESCRIPT_ERROR"
        assert result["details"] == "things not running"
        # Only the pre-create snapshot call should have happened - no
        # polling after a failed URL-scheme call.
        assert manager.execute_applescript.await_count == 1
