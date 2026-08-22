"""hq-gbl.9: Regression (live) for bulk_update_todos, move_record, and
bulk_move_records across destinations and multi-field updates, driven
through the real MCP tool boundary.

Every test creates its own tracked to-do(s) via
mcp.call_sync('add_todo', list_id=sandbox.project_id) so each case starts
from a clean, known-good state.

Error-code notes (confirmed by reading tools_helpers/bulk_operations.py,
move_operations.py, and server.py's bulk_update_todos/move_record/
bulk_move_records wrappers):
  - bulk_update_todos: todo_ids='' or ',,' -> NO_TODO_IDS (parsed in
    server.py before self.tools.bulk_update_todos is ever called).
  - bulk_update_todos: invalid completed/canceled string ('yes'/'1') ->
    VALIDATION_ERROR with field='completed'|'canceled' and
    updated_count=0, raised in server.py before any AppleScript write.
  - bulk_update_todos: when='evening' without the Things auth token ->
    AUTH_TOKEN_NOT_CONFIGURED with updated_count=0 and a 'hint' field,
    checked in BulkOperations.bulk_update_todos BEFORE the AppleScript
    script for the other fields is ever built/executed - so nothing in
    the batch is touched (verified below by reading every todo back
    unchanged).
  - bulk_update_todos: an unknown id inside an otherwise-valid todo_ids
    list IS now pre-checked via things.py BEFORE the AppleScript script is
    built (hq-wbm) - unresolvable ids (unknown, or resolving to something
    other than a to-do, e.g. a project) are excluded from the script and
    reported in a 'not_found' list field, while known ids still go through
    the existing per-id try/on-error AppleScript block and succeed.
    updated_count/failed_count/total_requested still reflect the full
    ORIGINAL request (pre-check rejections count as failures). There is
    still no per-id result list for AppleScript-level failures (a
    known-good id whose AppleScript write itself errors) - only the
    pre-check's 'not_found' list is itemized by id.
  - move_record: destination is not one of the fixed valid_lists /
    'project:'-or-'area:'-prefixed forms -> VALIDATION_ERROR (from
    MoveOperationsTools._validate_move_inputs/_validate_destination,
    returned by move_record's own dict, not the write_error() helper -
    this predates that shared helper and was not migrated by this bead).
  - move_record: 'project:' (empty id after the prefix) -> VALIDATION_ERROR
    ("Project ID cannot be empty").
  - move_record: unknown project id embedded in 'project:<id>' -> the
    destination-string shape itself is valid (non-empty suffix), so
    _validate_destination passes; the actual AppleScript `project id
    "<id>"` lookup fails inside _execute_move, surfaced as
    APPLESCRIPT_ERROR.
  - move_record: unknown todo_id -> TODO_NOT_FOUND (from
    move_record's own _get_todo_info pre-check, which fails to resolve
    `to do id "<id>"` and short-circuits before any destination handling).
  - bulk_move_records: todo_ids='' or ',,' -> NO_TODO_IDS (parsed in
    server.py's bulk_move_records wrapper itself, NOT the
    NO_TODOS_SPECIFIED code MoveOperationsTools.bulk_move would use for an
    empty list - server.py never lets an empty list reach bulk_move since
    it pre-filters and short-circuits first).
  - bulk_move_records: invalid destination -> INVALID_DESTINATION,
    validated once up front (MoveOperationsTools.bulk_move's own
    _validate_destination call) before any per-todo move is attempted -
    verified below that none of the batch's to-dos moved.
  - bulk_move_records: max_concurrent is declared `ge=1, le=10` on the
    MCP tool Field - out-of-range values are rejected by pydantic before
    the tool body ever runs (a FastMCP ToolError, surfaced by the `mcp`
    helper as {"tool_error": ...}, not a structured error dict).

bead hq-x9z (fixed): when='today' via the AppleScript scheduler
(bulk_update_todos' reliable_scheduler.schedule_todo_reliable, same
underlying path as add_todo/update_todo's 'today' case) used to leave
start='Someday' with start_date=today rather than start='Anytime'. Fixed
by routing the today-path through `move theTodo to list "Today"` instead
of the `schedule` verb - see test_when_today_start_date below, which now
asserts start='Anytime' directly.

move_record destination='today' was never affected by hq-x9z - it always
used Things' own `move ... to list "today"` verb (not the `schedule`
scheduler path), producing the same 'unconfirmed_scheduled'-turned-Anytime
state confirmed live for the scheduler fix above; membership in
things.today() is asserted directly (see test_move_to_today below).

preserve_scheduling: CLAUDE.md documents a `preserve_scheduling` flag on
bulk_move_records ("preserve_scheduling=true"), but neither the
bulk_move_records MCP tool signature (server.py) nor
MoveOperationsTools.bulk_move/move_record (move_operations.py) accept or
reference any such parameter anywhere in the current codebase - it is
pure documentation drift, not a real, functioning flag. Filed as
Discovered work rather than fixed here (out of scope). This suite instead
directly observes what bulk_move_records actually does to when/deadline
on move to a project (the only destination where "preserving" scheduling
is even meaningful) and documents it in
TestBulkMoveRecordsSchedulingObserved's docstring/test.
"""
import time

import pytest

from regression.helpers import (
    assert_write_error,
    read_back,
    sandbox_title,
    ts,
)

pytestmark = pytest.mark.live


def _new_todo(mcp, sandbox, title=None, **kwargs):
    """Create a fresh, tracked to-do in the sandbox project and return its id.

    Defaults to when='someday' rather than Things' own create-time default
    (Anytime) unless the caller passes an explicit `when` (including
    `when=None` to force the create-time default). This keeps this file's
    scratch to-dos - which linger, untracked-by-teardown-until-session-end,
    for the full remainder of the live regression session - out of the
    real database's Anytime list. That list is large enough on this live
    database (1172+ items measured) that test_seed_oracle.py's
    get_anytime check (an unpaged, limit=500 fetch) can silently truncate
    a seed item out of its returned window if enough Anytime-state to-dos
    accumulate before it runs later in the same session - confirmed by a
    live before/after comparison during hq-gbl.9 development (496 passed/
    6 xfailed with this file absent; get_anytime-only failures appeared
    with it present at the Anytime default). Tests that care about
    Anytime-state behavior pass when='anytime'/'today' explicitly (or move
    the to-do into Anytime afterward via update_todo/move_record), so
    defaulting creation to Someday does not weaken any test's actual
    assertions - see module docstring 'Discovered' notes for the
    unpaged-fetch issue itself, which is out of scope to fix here.
    """
    title = title or sandbox_title("bulk/move target " + ts())
    if "when" not in kwargs:
        kwargs["when"] = "someday"
    elif kwargs["when"] is None:
        kwargs.pop("when")
    result = mcp.call_sync(
        "add_todo", title=title, list_id=sandbox.project_id, **kwargs
    )
    assert result.get("success") is True, result
    todo_id = result.get("todo_id")
    assert todo_id
    sandbox.track(todo_id)
    return todo_id, title


def _new_todos(mcp, sandbox, count, prefix="bulk batch"):
    ids = []
    titles = []
    for i in range(count):
        todo_id, title = _new_todo(mcp, sandbox, title=sandbox_title(f"{prefix} {i} {ts()}"))
        ids.append(todo_id)
        titles.append(title)
    return ids, titles


def _bulk_move_tolerating_concurrency_race(mcp, todo_ids, destination, max_concurrent=None, retries=3):
    """Call bulk_move_records, retrying only todo ids that failed with the
    specific transient concurrency-race signature (see below) - any other
    failure is a real bug and is NOT retried, so it surfaces immediately as
    a failed_moves entry in the returned result for the caller's own
    assertions to catch.

    Originally observed live (hq-gbl.9, no prior bead): MoveOperationsTools.
    bulk_move fans out concurrent AppleScript calls via asyncio.gather
    (bounded by max_concurrent, default 5). Under that concurrency,
    individual per-todo moves intermittently failed ("N successful, M
    failed" with M > 0) even though every id/destination was valid.

    hq-c7a root-caused and partially fixed the underlying defect: the
    AppleScript executor (services/applescript/executor.py) now retries
    rc=0 results whose stdout carries the in-script "ERROR:"-prefixed
    convention, which used to bypass retry entirely (only rc!=0 triggered
    retry before). AppleScriptManager._applescript_lock (services/
    applescript_manager.py) - a duplicate, dead lock that was never
    acquired anywhere - was also removed; the real serialization has
    always lived in AppleScriptExecutor's executor-level lock (per-event-loop via _get_lock() since hq-yxu), which IS held
    around every osascript call.

    Re-measured live post-hq-c7a (two full 59-test live runs, plus a
    targeted third run of just the destination/max_concurrent tests): the
    executor fix does NOT fully eliminate the race. A distinct residual
    failure mode remains at the higher layer - move_record's own
    _get_todo_info pre-check (move_operations.py) intermittently fails to
    resolve a just-created, genuinely-valid todo's `to do id "<id>"` under
    concurrent AppleScript bursts, which move_record reports as
    error='TODO_NOT_FOUND', message="Todo with ID '<id>' not found". Across
    all three post-fix live runs, TODO_NOT_FOUND was the ONLY error
    signature ever observed on a retried-and-then-succeeding id (8 total
    occurrences, spanning destination='area:...'/'today'/'trash'/
    'project:...' and max_concurrent=5/10) - this is narrower than "any
    failure" and is what this helper now matches on specifically. Retrying
    only ids that failed with exactly this signature (typically 0-2 of N)
    reliably converges within a couple of attempts. Any id that fails with
    a different error code is left in failed_moves and NOT retried, so a
    real regression (e.g. a genuinely invalid id, or a new failure mode)
    still fails the calling test's assertions instead of being silently
    masked. Filed under Discovered rather than fixed at the move_record
    layer (out of scope for hq-c7a: that pre-check would need its own
    retry/backoff treatment, tracked separately)."""
    RETRYABLE_ERROR = "TODO_NOT_FOUND"
    remaining = list(todo_ids)
    last_result = None
    for _ in range(retries):
        kwargs = {"todo_ids": ",".join(remaining), "destination": destination}
        if max_concurrent is not None:
            kwargs["max_concurrent"] = max_concurrent
        last_result = mcp.call_sync("bulk_move_records", **kwargs)
        failed_moves = last_result.get("failed_moves") or []
        if not failed_moves:
            return last_result
        non_retryable = [m for m in failed_moves if m.get("error") != RETRYABLE_ERROR]
        if non_retryable:
            # A different failure signature - not the known transient race.
            # Stop retrying immediately and return as-is so the caller's
            # assertions see (and fail on) the real problem.
            return last_result
        remaining = [m["id"] for m in failed_moves]
        time.sleep(1)
    return last_result


# ---------------------------------------------------------------------------
# 1. bulk_update_todos
# ---------------------------------------------------------------------------


class TestBulkUpdateMultiField:
    def test_multi_field_all_read_back_on_every_todo(self, mcp, sandbox):
        from datetime import date, timedelta

        todo_ids, _ = _new_todos(mcp, sandbox, 3, prefix="bulk multi")
        new_title = sandbox_title("bulk multi title " + ts())
        new_notes = "bulk multi notes\nsecond line"
        deadline = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")

        result = mcp.call_sync(
            "bulk_update_todos",
            todo_ids=",".join(todo_ids),
            title=new_title,
            notes=new_notes,
            tags=sandbox.tag_name,
            when="tomorrow",
            deadline=deadline,
        )
        assert result.get("success") is True, result
        assert result.get("updated_count") == 3, result

        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("title") == new_title
            )
            assert record is not None, record
            assert record.get("title") == new_title, record
            assert record.get("notes") == new_notes, record
            assert (record.get("tags") or []) == [sandbox.tag_name], record
            assert record.get("deadline") == deadline, record
            assert record.get("start_date") is not None, record


class TestBulkUpdateSingleField:
    def test_title_only(self, mcp, sandbox):
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk title only")
        new_title = sandbox_title("bulk single title " + ts())
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), title=new_title
        )
        assert result.get("success") is True, result
        assert result.get("updated_count") == 2, result
        for todo_id in todo_ids:
            record = read_back(todo_id, lambda r: r is not None and r.get("title") == new_title)
            assert record is not None and record.get("title") == new_title, record

    def test_notes_only(self, mcp, sandbox):
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk notes only")
        notes = "bulk single notes " + ts()
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), notes=notes
        )
        assert result.get("success") is True, result
        for todo_id in todo_ids:
            record = read_back(todo_id, lambda r: r is not None and r.get("notes") == notes)
            assert record is not None and record.get("notes") == notes, record

    def test_tags_only(self, mcp, sandbox):
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk tags only")
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), tags=sandbox.tag_name
        )
        assert result.get("success") is True, result
        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
            )
            assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], record

    def test_deadline_only(self, mcp, sandbox):
        from datetime import date, timedelta

        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk deadline only")
        deadline = (date.today() + timedelta(days=25)).strftime("%Y-%m-%d")
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), deadline=deadline
        )
        assert result.get("success") is True, result
        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("deadline") == deadline
            )
            assert record is not None and record.get("deadline") == deadline, record

    def test_when_today_start_date(self, mcp, sandbox):
        """hq-x9z fixed: bulk_update_todos(when='today') now yields
        start='Anytime' with start_date=today (previously start='Someday'
        due to the AppleScript `schedule` verb quirk)."""
        from datetime import date

        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk when today")
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), when="today"
        )
        assert result.get("success") is True, result
        today_str = date.today().strftime("%Y-%m-%d")
        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("start_date") == today_str
            )
            assert record is not None and record.get("start_date") == today_str, record
            assert record.get("start") == "Anytime", record

    def test_when_anytime_lands_anytime(self, mcp, sandbox):
        todo_ids, _ = _new_todos(mcp, sandbox, 1, prefix="bulk when anytime")
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), when="anytime"
        )
        assert result.get("success") is True, result
        record = read_back(todo_ids[0], lambda r: r is not None and r.get("start") is not None)
        assert record is not None and record.get("start") == "Anytime", record


class TestBulkUpdateClears:
    def test_notes_empty_clears(self, mcp, sandbox):
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk clear notes")
        for todo_id in todo_ids:
            r = mcp.call_sync("update_todo", id=todo_id, notes="to be cleared")
            assert r.get("success") is True, r
        for todo_id in todo_ids:
            read_back(todo_id, lambda r: r is not None and r.get("notes") == "to be cleared")

        result = mcp.call_sync("bulk_update_todos", todo_ids=",".join(todo_ids), notes="")
        assert result.get("success") is True, result
        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and (r.get("notes") or "") == ""
            )
            assert record is not None and (record.get("notes") or "") == "", record

    def test_deadline_empty_clears(self, mcp, sandbox):
        from datetime import date, timedelta

        deadline = (date.today() + timedelta(days=28)).strftime("%Y-%m-%d")
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk clear deadline")
        for todo_id in todo_ids:
            r = mcp.call_sync("update_todo", id=todo_id, deadline=deadline)
            assert r.get("success") is True, r
        for todo_id in todo_ids:
            read_back(todo_id, lambda r: r is not None and r.get("deadline") == deadline)

        result = mcp.call_sync("bulk_update_todos", todo_ids=",".join(todo_ids), deadline="")
        assert result.get("success") is True, result
        for todo_id in todo_ids:
            record = read_back(todo_id, lambda r: r is not None and r.get("deadline") is None)
            assert record is not None and record.get("deadline") is None, record

    def test_tags_empty_clears(self, mcp, sandbox):
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk clear tags")
        for todo_id in todo_ids:
            r = mcp.call_sync("update_todo", id=todo_id, tags=sandbox.tag_name)
            assert r.get("success") is True, r
        for todo_id in todo_ids:
            read_back(
                todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
            )

        result = mcp.call_sync("bulk_update_todos", todo_ids=",".join(todo_ids), tags="")
        assert result.get("success") is True, result
        for todo_id in todo_ids:
            record = read_back(todo_id, lambda r: r is not None and not (r.get("tags") or []))
            assert record is not None and not (record.get("tags") or []), record


class TestBulkUpdateStatus3x3:
    STATUS_CASES = [
        ("true", "true", "canceled"),
        ("true", "false", "completed"),
        ("true", None, "completed"),
        ("false", "true", "canceled"),
        ("false", "false", "incomplete"),
        ("false", None, "incomplete"),
        (None, "true", "canceled"),
        (None, "false", "incomplete"),
        (None, None, "incomplete"),
    ]

    @pytest.mark.parametrize("completed,canceled,expected_status", STATUS_CASES)
    def test_status_combination_on_batch(self, mcp, sandbox, completed, canceled, expected_status):
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk status")
        kwargs = {}
        if completed is not None:
            kwargs["completed"] = completed
        if canceled is not None:
            kwargs["canceled"] = canceled

        result = mcp.call_sync("bulk_update_todos", todo_ids=",".join(todo_ids), **kwargs)
        assert result.get("success") is True, result
        assert result.get("updated_count") == 2, result

        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("status") == expected_status
            )
            assert record is not None and record.get("status") == expected_status, record


class TestBulkUpdateInvalidBool:
    @pytest.mark.parametrize("field", ["completed", "canceled"])
    @pytest.mark.parametrize("bad_value", ["yes", "1"])
    def test_invalid_bool_rejected_updated_count_zero(self, mcp, sandbox, field, bad_value):
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk invalid bool")
        kwargs = {field: bad_value}
        result = mcp.call_sync("bulk_update_todos", todo_ids=",".join(todo_ids), **kwargs)
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == field, result
        assert result.get("updated_count") == 0, result

        for todo_id in todo_ids:
            record = read_back(todo_id, lambda r: r is not None)
            assert record is not None and record.get("status") == "incomplete", record


class TestBulkUpdateNoTodoIds:
    @pytest.mark.parametrize("todo_ids_str", ["", ",,"])
    def test_empty_or_commas_only_no_todo_ids(self, mcp, sandbox, todo_ids_str):
        result = mcp.call_sync("bulk_update_todos", todo_ids=todo_ids_str, title="ignored")
        assert_write_error(result, "NO_TODO_IDS")
        assert result.get("updated_count") == 0, result


class TestBulkUpdateMixedValidUnknown:
    def test_mixed_valid_and_unknown_ids(self, mcp, sandbox):
        """hq-wbm: unknown ids are now pre-checked via things.py and
        reported in a 'not_found' list field (see module docstring), while
        the valid id is still updated via AppleScript as before. There is
        still no per-id AppleScript-failure breakdown ('results'/'per_id'
        keys), only the pre-check's itemized 'not_found' list."""
        todo_id, _ = _new_todo(mcp, sandbox, title=sandbox_title("bulk mixed valid " + ts()))
        unknown_id = "bogus-bulk-update-id-does-not-exist"
        new_title = sandbox_title("bulk mixed applied " + ts())

        result = mcp.call_sync(
            "bulk_update_todos",
            todo_ids=f"{todo_id},{unknown_id}",
            title=new_title,
        )
        # Partial success: at least one id succeeded, so overall success is
        # True (BulkOperations._parse_bulk_results: success = success_count > 0).
        assert result.get("success") is True, result
        assert result.get("total_requested") == 2, result
        assert result.get("updated_count") == 1, result
        assert result.get("failed_count") == 1, result
        assert result.get("not_found") == [unknown_id], result
        # No per-id AppleScript-failure breakdown field exists in the response.
        assert "results" not in result, result
        assert "per_id" not in result, result

        record = read_back(todo_id, lambda r: r is not None and r.get("title") == new_title)
        assert record is not None and record.get("title") == new_title, record

    def test_all_unknown_ids_not_found(self, mcp, sandbox):
        """When every id fails the pre-check, bulk_update_todos returns a
        structured NOT_FOUND error without ever building/running the
        AppleScript script."""
        unknown_ids = [
            "bogus-bulk-update-id-does-not-exist-1",
            "bogus-bulk-update-id-does-not-exist-2",
        ]
        result = mcp.call_sync(
            "bulk_update_todos",
            todo_ids=",".join(unknown_ids),
            title="should not be applied",
        )
        assert_write_error(result, "NOT_FOUND")
        assert result.get("updated_count") == 0, result
        assert result.get("failed_count") == 2, result
        assert result.get("total_requested") == 2, result
        assert result.get("not_found") == unknown_ids, result


class TestBulkUpdateEvening:
    def test_evening_with_token(self, mcp, sandbox, live_server):
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        import things
        from datetime import date

        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk evening")
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), when="evening"
        )
        assert result.get("success") is True, result

        today_str = date.today().strftime("%Y-%m-%d")
        for todo_id in todo_ids:
            record = read_back(
                todo_id,
                lambda r: r is not None
                and r.get("start") == "Anytime"
                and r.get("start_date") == today_str,
            )
            assert record is not None, record
            assert record.get("start") == "Anytime", record
            assert record.get("start_date") == today_str, record

        def _all_in_today():
            today_ids = {t["uuid"] for t in things.today() or []}
            return all(tid in today_ids for tid in todo_ids)

        deadline = time.monotonic() + 20
        found = _all_in_today()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _all_in_today()
        assert found, "expected all evening-scheduled todos to be members of things.today()"

    def test_evening_without_token_nothing_touched(self, mcp, sandbox, live_server):
        """Monkeypatches the shared live AppleScriptManager's auth_token to
        None for the duration of this test only, restoring it in a finally
        block. Todos are created BEFORE the patch is applied.

        hq-wsa.4: the auth gate now reloads the token from disk
        (reload_auth_token_if_missing()) whenever none is currently loaded,
        so that a token file added after startup works without a restart.
        The live environment has a real .things-auth on disk, so simply
        clearing auth_token here is no longer sufficient to keep the gate
        tripped for the duration of the call - reload_auth_token_if_missing
        is also stubbed out to a no-op for the same window, restored
        alongside the token in the same finally block."""
        manager = live_server.applescript_manager
        original_token = manager.auth_token
        original_reload = manager.reload_auth_token_if_missing
        todo_ids, original_titles = _new_todos(mcp, sandbox, 2, prefix="bulk evening no token")
        try:
            manager.auth_token = None
            manager.reload_auth_token_if_missing = lambda: manager.auth_token
            should_not_apply = sandbox_title("SHOULD-NOT-APPLY " + ts())
            result = mcp.call_sync(
                "bulk_update_todos",
                todo_ids=",".join(todo_ids),
                when="evening",
                title=should_not_apply,
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
            assert result.get("updated_count") == 0, result
        finally:
            manager.auth_token = original_token
            manager.reload_auth_token_if_missing = original_reload

        for todo_id, original_title in zip(todo_ids, original_titles):
            record = read_back(todo_id, lambda r: r is not None)
            assert record is not None and record.get("title") == original_title, record
            assert record.get("start") != "Anytime" or record.get("start_date") is None, record


class TestBulkUpdateWhenWithTime:
    """hq-4gn: bulk_update_todos(when='YYYY-MM-DD@HH:MM') is routed via the
    Things URL scheme's per-todo 'update' action (same pattern as
    when='evening'), which sets each todo's reminder natively - the
    AppleScript scheduling path used to silently drop the '@HH:MM'
    component."""

    def test_when_time_with_token_sets_reminder(self, mcp, sandbox, live_server):
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=12)).strftime("%Y-%m-%d")
        todo_ids, _ = _new_todos(mcp, sandbox, 2, prefix="bulk when time")
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), when=f"{when_date}@13:15"
        )
        assert result.get("success") is True, result

        for todo_id in todo_ids:
            record = read_back(
                todo_id,
                lambda r: r is not None and r.get("reminder_time") is not None,
            )
            assert record is not None
            assert record.get("reminder_time") == "13:15", record
            assert record.get("start_date") == when_date, record

    def test_when_time_without_token_nothing_touched(self, mcp, sandbox, live_server):
        """Monkeypatches the shared live AppleScriptManager's auth_token to
        None for the duration of this test only, restoring it in a finally
        block. Todos are created BEFORE the patch is applied.

        hq-wsa.4: the auth gate now reloads the token from disk
        (reload_auth_token_if_missing()) whenever none is currently loaded,
        so that a token file added after startup works without a restart.
        The live environment has a real .things-auth on disk, so simply
        clearing auth_token here is no longer sufficient to keep the gate
        tripped for the duration of the call - reload_auth_token_if_missing
        is also stubbed out to a no-op for the same window, restored
        alongside the token in the same finally block."""
        from datetime import date, timedelta

        manager = live_server.applescript_manager
        original_token = manager.auth_token
        original_reload = manager.reload_auth_token_if_missing
        todo_ids, original_titles = _new_todos(mcp, sandbox, 2, prefix="bulk when time no token")
        when_date = (date.today() + timedelta(days=12)).strftime("%Y-%m-%d")
        try:
            manager.auth_token = None
            manager.reload_auth_token_if_missing = lambda: manager.auth_token
            should_not_apply = sandbox_title("SHOULD-NOT-APPLY " + ts())
            result = mcp.call_sync(
                "bulk_update_todos",
                todo_ids=",".join(todo_ids),
                when=f"{when_date}@13:15",
                title=should_not_apply,
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
            assert result.get("updated_count") == 0, result
        finally:
            manager.auth_token = original_token
            manager.reload_auth_token_if_missing = original_reload

        for todo_id, original_title in zip(todo_ids, original_titles):
            record = read_back(todo_id, lambda r: r is not None)
            assert record is not None and record.get("title") == original_title, record
            assert record.get("reminder_time") is None, record


class TestBulkUpdateTiming:
    def test_25_id_batch_timing(self, mcp, sandbox):
        """25-id batch timing, recorded for reference only - no assertion
        on wall-clock time. Observed: ~4.5s for a single-field (title)
        AppleScript-only bulk_update_todos across 25 todos (one AppleScript
        invocation covering all 25 ids in a single script - see
        BulkOperations._build_bulk_update_script)."""
        todo_ids, _ = _new_todos(mcp, sandbox, 25, prefix="bulk timing")
        new_title = sandbox_title("bulk timing applied " + ts())

        start = time.monotonic()
        result = mcp.call_sync(
            "bulk_update_todos", todo_ids=",".join(todo_ids), title=new_title
        )
        elapsed = time.monotonic() - start
        # elapsed observed locally around 4-6s for 25 ids; not asserted.

        assert result.get("success") is True, result
        assert result.get("updated_count") == 25, result


# ---------------------------------------------------------------------------
# 2. move_record
# ---------------------------------------------------------------------------


class TestMoveRecordDestinations:
    def test_move_to_inbox(self, mcp, sandbox):
        """hq-wsa.6: project -> inbox. _new_todo files the to-do in
        sandbox.project_id, so the pre-move origin must be reported as
        exactly 'project:<sandbox.project_id>' (no 'current_list:' prefix
        from the old positional AppleScript parser), and the success
        message must carry the bare title (no 'name:' prefix)."""
        import things

        title = sandbox_title("move inbox " + ts())
        todo_id, _ = _new_todo(mcp, sandbox, title=title)
        result = mcp.call_sync("move_record", todo_id=todo_id, destination_list="inbox")
        assert result.get("success") is True, result
        assert result.get("message") == f"Todo '{title}' moved to inbox successfully", result
        assert "name:" not in result.get("message", ""), result
        assert result.get("original_location") == f"project:{sandbox.project_id}", result
        assert "current_list:" not in str(result.get("original_location")), result

        def _in_inbox():
            return any(t["uuid"] == todo_id for t in things.inbox() or [])

        deadline = time.monotonic() + 20
        found = _in_inbox()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_inbox()
        assert found, "expected todo to be a member of things.inbox()"

    def test_move_from_inbox_to_project(self, mcp, sandbox):
        """hq-wsa.6: inbox -> project. A to-do created with no list_id
        lands in the Inbox (things.py start == 'Inbox'), so the pre-move
        origin must be reported as exactly 'inbox', and moving it into
        sandbox.project_id must read back with the exact project id (no
        'current_list:inbox' hardcoded-stub leak regardless of true
        origin - the historic bug this bead fixes)."""
        import things

        title = sandbox_title("move from inbox " + ts())
        # No list_id/when: Things' create-time default with neither
        # given is the Inbox (things.py start == 'Inbox') - unlike
        # _new_todo's own when='someday' default (see that helper's
        # docstring), this test needs a genuine Inbox-origin todo.
        add_result = mcp.call_sync("add_todo", title=title)
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("start") == "Inbox")
        assert record is not None and record.get("start") == "Inbox", record

        result = mcp.call_sync(
            "move_record", todo_id=todo_id, destination_list=f"project:{sandbox.project_id}"
        )
        assert result.get("success") is True, result
        assert result.get("message") == f"Todo '{title}' moved to project:{sandbox.project_id} successfully", result
        assert "name:" not in result.get("message", ""), result
        assert result.get("original_location") == "inbox", result
        assert "current_list:" not in str(result.get("original_location")), result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_id
        )
        assert record is not None and record.get("project") == sandbox.project_id, record

    def test_move_to_today(self, mcp, sandbox):
        """move_record's `move ... to list "today"` verb was never
        affected by the hq-x9z `schedule`-verb quirk (it doesn't use
        `schedule` at all) - it yields start='Anytime', start_date=today,
        same as the scheduler's now-fixed when='today' path. Membership in
        things.today() is asserted directly."""
        import things

        todo_id, _ = _new_todo(mcp, sandbox, title=sandbox_title("move today " + ts()))
        result = mcp.call_sync("move_record", todo_id=todo_id, destination_list="today")
        assert result.get("success") is True, result

        def _in_today():
            return any(t["uuid"] == todo_id for t in things.today() or [])

        deadline = time.monotonic() + 20
        found = _in_today()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_today()
        assert found, "expected todo to be a member of things.today()"

    def test_move_to_upcoming(self, mcp, sandbox):
        """'upcoming' is not a valid move destination (bead hq-cag): Things
        has no direct Upcoming move target - an item is Upcoming by having
        a future start date, and Things' AppleScript move verb itself
        rejects `move ... to list "upcoming"`. move_record now rejects it
        at validation with a structured error steering callers to
        update_todo(when=<date>) instead of guessing an arbitrary future
        date. The to-do must remain untouched (still in its original
        project)."""
        todo_id, original_title = _new_todo(mcp, sandbox, title=sandbox_title("move upcoming " + ts()))
        result = mcp.call_sync("move_record", todo_id=todo_id, destination_list="upcoming")
        assert_write_error(result, "VALIDATION_ERROR")
        message = result.get("message", "")
        assert "when=" in message or "update_todo" in message, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_id
        )
        assert record is not None, record
        assert record.get("title") == original_title, record
        assert record.get("project") == sandbox.project_id, record

    def test_move_to_anytime(self, mcp, sandbox):
        import things

        todo_id, _ = _new_todo(mcp, sandbox, title=sandbox_title("move anytime " + ts()))
        result = mcp.call_sync("move_record", todo_id=todo_id, destination_list="anytime")
        assert result.get("success") is True, result

        def _in_anytime():
            return any(t["uuid"] == todo_id for t in things.anytime() or [])

        deadline = time.monotonic() + 20
        found = _in_anytime()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_anytime()
        assert found, "expected todo to be a member of things.anytime()"

    def test_move_to_someday(self, mcp, sandbox):
        import things

        todo_id, _ = _new_todo(mcp, sandbox, title=sandbox_title("move someday " + ts()))
        result = mcp.call_sync("move_record", todo_id=todo_id, destination_list="someday")
        assert result.get("success") is True, result

        def _in_someday():
            return any(t["uuid"] == todo_id for t in things.someday() or [])

        deadline = time.monotonic() + 20
        found = _in_someday()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_someday()
        assert found, "expected todo to be a member of things.someday()"

    def test_move_to_logbook(self, mcp, sandbox):
        """Moving to 'logbook' changes status/trashed - read back via
        things.get(uuid, trashed=None) and things.logbook() membership."""
        import things

        todo_id, _ = _new_todo(mcp, sandbox, title=sandbox_title("move logbook " + ts()))
        result = mcp.call_sync("move_record", todo_id=todo_id, destination_list="logbook")
        assert result.get("success") is True, result

        def _in_logbook():
            return any(t["uuid"] == todo_id for t in things.logbook() or [])

        deadline = time.monotonic() + 20
        found = _in_logbook()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_logbook()
        assert found, "expected todo to be a member of things.logbook()"

        record = things.get(todo_id, trashed=None)
        assert record is not None and record.get("status") in ("completed", "canceled"), record

    def test_move_to_trash(self, mcp, sandbox):
        """Moving to 'trash' sets trashed=True - read back via
        things.get(uuid, trashed=None). Already tracked (via _new_todo
        before the move), so teardown will trash it again idempotently."""
        import things

        todo_id, _ = _new_todo(mcp, sandbox, title=sandbox_title("move trash " + ts()))
        result = mcp.call_sync("move_record", todo_id=todo_id, destination_list="trash")
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("trashed") is True,
            timeout=20,
        )
        # things.get(..., trashed=None) surfaces trashed items too.
        record = things.get(todo_id, trashed=None)
        assert record is not None and record.get("trashed") is True, record

    def test_move_to_project_b(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, title=sandbox_title("move project b " + ts()))
        result = mcp.call_sync(
            "move_record", todo_id=todo_id, destination_list=f"project:{sandbox.project_b_id}"
        )
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
        )
        assert record is not None and record.get("project") == sandbox.project_b_id, record

    def test_move_to_area(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, title=sandbox_title("move area " + ts()))
        result = mcp.call_sync(
            "move_record", todo_id=todo_id, destination_list=f"area:{sandbox.area_id}"
        )
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("area") == sandbox.area_id
        )
        assert record is not None and record.get("area") == sandbox.area_id, record


class TestMoveRecordErrors:
    def test_invalid_destination(self, mcp, sandbox):
        todo_id, original_title = _new_todo(mcp, sandbox, title=sandbox_title("move bad dest " + ts()))
        result = mcp.call_sync(
            "move_record", todo_id=todo_id, destination_list="not-a-real-destination"
        )
        assert_write_error(result, "VALIDATION_ERROR")

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

    def test_project_prefix_empty_id(self, mcp, sandbox):
        todo_id, original_title = _new_todo(mcp, sandbox, title=sandbox_title("move empty proj " + ts()))
        result = mcp.call_sync("move_record", todo_id=todo_id, destination_list="project:")
        assert_write_error(result, "VALIDATION_ERROR")

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

    def test_unknown_project_id(self, mcp, sandbox):
        todo_id, original_title = _new_todo(mcp, sandbox, title=sandbox_title("move unknown proj " + ts()))
        result = mcp.call_sync(
            "move_record",
            todo_id=todo_id,
            destination_list=f"project:bogus-project-{ts()}",
        )
        assert_write_error(result, "APPLESCRIPT_ERROR")

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

    def test_unknown_todo_id(self, mcp, sandbox):
        result = mcp.call_sync(
            "move_record",
            todo_id="bogus-move-todo-id-does-not-exist",
            destination_list="today",
        )
        assert_write_error(result, "TODO_NOT_FOUND")

    def test_whitespace_only_todo_id(self, mcp, sandbox):
        """hq-a5j: move_record's todo_id validation now rejects a
        whitespace-only id the same as an empty one (previously only a
        falsy/empty string was rejected; '   ' passed _validate_move_inputs
        and proceeded to the AppleScript move against a literal `to do id
        "   "`)."""
        result = mcp.call_sync(
            "move_record", todo_id="   ", destination_list="today"
        )
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "todo_id", result


# ---------------------------------------------------------------------------
# 3. bulk_move_records
# ---------------------------------------------------------------------------


class TestBulkMoveRecordsDestinations:
    def test_to_project_b(self, mcp, sandbox):
        todo_ids, _ = _new_todos(mcp, sandbox, 3, prefix="bulk move project b")
        result = mcp.call_sync(
            "bulk_move_records",
            todo_ids=",".join(todo_ids),
            destination=f"project:{sandbox.project_b_id}",
        )
        assert result.get("success") is True, result
        assert result.get("total_successful") == 3, result
        assert result.get("total_failed") == 0, result

        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
            )
            assert record is not None and record.get("project") == sandbox.project_b_id, record

    def test_to_area(self, mcp, sandbox):
        """Uses _bulk_move_tolerating_concurrency_race - see its docstring
        and module docstring for the observed unserialized-AppleScript-call
        race in MoveOperationsTools.bulk_move (Discovered, not fixed here).
        """
        todo_ids, _ = _new_todos(mcp, sandbox, 3, prefix="bulk move area")
        result = _bulk_move_tolerating_concurrency_race(
            mcp, todo_ids, f"area:{sandbox.area_id}"
        )
        assert not (result.get("failed_moves") or []), result

        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("area") == sandbox.area_id
            )
            assert record is not None and record.get("area") == sandbox.area_id, record

    def test_to_today(self, mcp, sandbox):
        """Uses _bulk_move_tolerating_concurrency_race - see its docstring
        and module docstring for the observed unserialized-AppleScript-call
        race in MoveOperationsTools.bulk_move (Discovered, not fixed here).
        """
        import things

        todo_ids, _ = _new_todos(mcp, sandbox, 3, prefix="bulk move today")
        result = _bulk_move_tolerating_concurrency_race(mcp, todo_ids, "today")
        assert not (result.get("failed_moves") or []), result

        def _all_in_today():
            today_ids = {t["uuid"] for t in things.today() or []}
            return all(tid in today_ids for tid in todo_ids)

        deadline = time.monotonic() + 20
        found = _all_in_today()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _all_in_today()
        assert found, "expected all todos to be members of things.today()"

    def test_to_trash(self, mcp, sandbox):
        """Uses _bulk_move_tolerating_concurrency_race - see its docstring
        and module docstring for the observed unserialized-AppleScript-call
        race in MoveOperationsTools.bulk_move (Discovered, not fixed here;
        the docstring explicitly names 'trash' as one of the destinations
        this race was reproduced against).
        """
        import things

        todo_ids, _ = _new_todos(mcp, sandbox, 3, prefix="bulk move trash")
        result = _bulk_move_tolerating_concurrency_race(mcp, todo_ids, "trash")
        assert not (result.get("failed_moves") or []), result

        def _all_trashed():
            for todo_id in todo_ids:
                record = things.get(todo_id, trashed=None)
                if record is None or not record.get("trashed"):
                    return False
            return True

        deadline = time.monotonic() + 20
        found = _all_trashed()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _all_trashed()
        assert found, "expected all todos to be trashed"


class TestBulkMoveRecordsSchedulingObserved:
    def test_move_to_project_preserves_when_and_deadline(self, mcp, sandbox):
        """Observed: moving to a project via bulk_move_records (AppleScript
        `set project of theTodo to targetProject`, move_operations.py's
        _build_project_move_script) does NOT touch when/deadline at all -
        both a pre-set start_date (+5d) and deadline survive the move
        unchanged. There is no preserve_scheduling flag in the actual code
        (see module docstring) - this is simply what the project-move
        AppleScript does (it only reassigns the `project` property)."""
        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        deadline = (date.today() + timedelta(days=40)).strftime("%Y-%m-%d")

        todo_id, _ = _new_todo(
            mcp,
            sandbox,
            title=sandbox_title("bulk move preserve " + ts()),
            when=when_date,
            deadline=deadline,
        )
        record = read_back(
            todo_id, lambda r: r is not None and r.get("start_date") == when_date
        )
        assert record is not None and record.get("start_date") == when_date, record
        assert record.get("deadline") == deadline, record

        result = mcp.call_sync(
            "bulk_move_records",
            todo_ids=todo_id,
            destination=f"project:{sandbox.project_b_id}",
        )
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
        )
        assert record is not None and record.get("project") == sandbox.project_b_id, record
        # Observed: when/deadline are unaffected by a project move.
        assert record.get("start_date") == when_date, record
        assert record.get("deadline") == deadline, record

    def test_move_to_today_list_clears_prior_start_date(self, mcp, sandbox):
        """Observed: moving to the built-in 'today' list via
        bulk_move_records (AppleScript `move theTodo to list "today"`)
        re-schedules the todo for today - overwriting any prior future
        start_date rather than preserving it. Deadline is untouched."""
        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        deadline = (date.today() + timedelta(days=40)).strftime("%Y-%m-%d")

        todo_id, _ = _new_todo(
            mcp,
            sandbox,
            title=sandbox_title("bulk move today preserve " + ts()),
            when=when_date,
            deadline=deadline,
        )
        record = read_back(
            todo_id, lambda r: r is not None and r.get("start_date") == when_date
        )
        assert record is not None and record.get("start_date") == when_date, record

        result = mcp.call_sync(
            "bulk_move_records", todo_ids=todo_id, destination="today"
        )
        assert result.get("success") is True, result

        import things

        def _in_today():
            return any(t["uuid"] == todo_id for t in things.today() or [])

        deadline_t = time.monotonic() + 20
        found = _in_today()
        while not found and time.monotonic() < deadline_t:
            time.sleep(0.25)
            found = _in_today()
        assert found, "expected todo to be a member of things.today()"

        record = things.get(todo_id, trashed=None)
        assert record.get("start_date") != when_date, record
        assert record.get("deadline") == deadline, record


class TestBulkMoveRecordsMaxConcurrent:
    def test_max_concurrent_1(self, mcp, sandbox):
        todo_ids, _ = _new_todos(mcp, sandbox, 3, prefix="bulk move maxc1")
        result = mcp.call_sync(
            "bulk_move_records",
            todo_ids=",".join(todo_ids),
            destination=f"project:{sandbox.project_b_id}",
            max_concurrent=1,
        )
        assert result.get("success") is True, result
        assert result.get("total_successful") == 3, result

        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
            )
            assert record is not None and record.get("project") == sandbox.project_b_id, record

    def test_max_concurrent_10(self, mcp, sandbox):
        """Uses _bulk_move_tolerating_concurrency_race - at max_concurrent=10
        the observed unserialized-AppleScript-call race (module docstring,
        Discovered) is most pronounced; retries converge on full success."""
        todo_ids, _ = _new_todos(mcp, sandbox, 3, prefix="bulk move maxc10")
        result = _bulk_move_tolerating_concurrency_race(
            mcp, todo_ids, f"project:{sandbox.project_b_id}", max_concurrent=10
        )
        assert not (result.get("failed_moves") or []), result

        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
            )
            assert record is not None and record.get("project") == sandbox.project_b_id, record

    @pytest.mark.parametrize("bad_value", [0, 11])
    def test_max_concurrent_boundary_rejected(self, mcp, sandbox, bad_value):
        """max_concurrent is declared ge=1, le=10 on the MCP tool Field -
        an out-of-range value is rejected by pydantic before the tool body
        runs, surfaced by the `mcp` call_sync helper as a tool_error dict
        rather than a structured {"success": False, ...} response."""
        todo_id, original_title = _new_todo(
            mcp, sandbox, title=sandbox_title("bulk move maxc boundary " + ts())
        )
        result = mcp.call_sync(
            "bulk_move_records",
            todo_ids=todo_id,
            destination=f"project:{sandbox.project_b_id}",
            max_concurrent=bad_value,
        )
        assert "tool_error" in result, result

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record
        assert record.get("project") == sandbox.project_id, record


class TestBulkMoveRecordsNoTodoIds:
    @pytest.mark.parametrize("todo_ids_str", ["", ",,"])
    def test_empty_or_commas_only_no_todo_ids(self, mcp, sandbox, todo_ids_str):
        result = mcp.call_sync(
            "bulk_move_records", todo_ids=todo_ids_str, destination="today"
        )
        assert_write_error(result, "NO_TODO_IDS")
        assert result.get("total_requested") == 0, result


class TestBulkMoveRecordsInvalidDestination:
    def test_invalid_destination_nothing_moved(self, mcp, sandbox):
        todo_ids, original_titles = _new_todos(
            mcp, sandbox, 2, prefix="bulk move bad dest"
        )
        result = mcp.call_sync(
            "bulk_move_records",
            todo_ids=",".join(todo_ids),
            destination="not-a-real-destination",
        )
        assert_write_error(result, "INVALID_DESTINATION")
        assert result.get("total_requested") == 2, result

        for todo_id in todo_ids:
            record = read_back(
                todo_id, lambda r: r is not None and r.get("project") == sandbox.project_id
            )
            assert record is not None and record.get("project") == sandbox.project_id, record
