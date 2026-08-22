"""hq-gbl.8: Regression (live) for update_todo across the full input space,
driven through the real MCP tool boundary.

Every test creates its own tracked to-do via mcp.call_sync('add_todo',
list_id=sandbox.project_id) so each case starts from a clean, known-good
state, then exercises update_todo against it.

bead hq-x9z (fixed): when='today' used to go through the AppleScript
'schedule' verb (used by both add_todo and update_todo), which left
start='Someday' with start_date=today rather than start='Anytime'. Fixed
by routing the today-path through `move theTodo to list "Today"` instead
of `schedule` - update_todo's when='today' now yields start='Anytime',
matching the URL-scheme when='today' path (checklist/heading/evening
adds). See TestUpdateTodoWhen below.

Error-code notes (confirmed by reading scheduling/todo_operations.py):
  - list_id/list_title resolution: NOT_FOUND (unknown), AMBIGUOUS_TARGET
    (list_title matching >1 project/area).
  - list_id/list_title/heading resolving to a completed/canceled project or
    heading: TARGET_COMPLETED, returned BEFORE any AppleScript write - the
    same call's other fields (e.g. title) are never applied.
  - heading='' (or whitespace-only): INVALID_HEADING.
  - heading/when='evening' without the Things auth token configured:
    AUTH_TOKEN_NOT_CONFIGURED, with a 'hint' field - checked before any
    AppleScript write, so no field in the same call is applied.
  - An unknown todo_id is now pre-checked via things.py BEFORE any write
    (hq-wbm) and surfaced as NOT_FOUND, consistent with list_id/list_title
    resolution above. A todo_id that resolves to something other than a
    to-do (e.g. a project id) is rejected with VALIDATION_ERROR instead -
    AppleScript's `to do id "..."` unexpectedly ALSO resolves a project
    uuid (verified live), so without this pre-check a project id passed as
    the primary target would be silently modified rather than erroring.
  - completed/canceled invalid strings ('yes'/'1'): VALIDATION_ERROR with
    field='completed'/'canceled', raised in server.py before ever calling
    self.tools.update_todo.
  - title='': VALIDATION_ERROR (field='title') via
    ParameterValidator.validate_update_params.
  - when='' / when='   ': VALIDATION_ERROR (field='when').
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
    """Create a fresh, tracked to-do in the sandbox project and return its id."""
    title = title or sandbox_title("update target " + ts())
    result = mcp.call_sync(
        "add_todo", title=title, list_id=sandbox.project_id, **kwargs
    )
    assert result.get("success") is True, result
    todo_id = result.get("todo_id")
    assert todo_id
    sandbox.track(todo_id)
    return todo_id, title


def _get_item(mcp, todo_id):
    result = mcp.call_sync("get_todo_by_id", todo_id=todo_id)
    assert "item" in result, result
    return result["item"]


# ---------------------------------------------------------------------------
# 1. Field updates
# ---------------------------------------------------------------------------


class TestUpdateTodoTitle:
    def test_title_special_chars_read_back(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        new_title = sandbox_title('updated "quoted", back\\slash, comma \U0001F600 ' + ts())
        result = mcp.call_sync("update_todo", id=todo_id, title=new_title)
        assert result.get("success") is True, result

        record = read_back(todo_id, lambda r: r is not None and r.get("title") == new_title)
        assert record is not None and record.get("title") == new_title, record

    def test_title_empty_rejected(self, mcp, sandbox):
        todo_id, original_title = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, title="")
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "title"

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record


class TestUpdateTodoNotes:
    def test_notes_multiline_set(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        notes = 'Line one "quoted", comma\n\nLine two \\ backslash\n\nLine three \U0001F600'
        result = mcp.call_sync("update_todo", id=todo_id, notes=notes)
        assert result.get("success") is True, result

        record = read_back(todo_id, lambda r: r is not None and r.get("notes") == notes)
        assert record is not None and record.get("notes") == notes, record.get("notes") if record else None

    def test_notes_empty_string_clears(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, notes="to be cleared")
        record = read_back(todo_id, lambda r: r is not None and r.get("notes") == "to be cleared")
        assert record is not None and record.get("notes") == "to be cleared"

        result = mcp.call_sync("update_todo", id=todo_id, notes="")
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("notes") or "") == ""
        )
        assert record is not None and (record.get("notes") or "") == "", record

    def test_notes_whitespace_only_clears(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, notes="to be cleared by whitespace")
        record = read_back(
            todo_id, lambda r: r is not None and r.get("notes") == "to be cleared by whitespace"
        )
        assert record is not None

        result = mcp.call_sync("update_todo", id=todo_id, notes="   ")
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("notes") or "") == ""
        )
        assert record is not None and (record.get("notes") or "") == "", record


class TestUpdateTodoDeadline:
    def test_deadline_set(self, mcp, sandbox):
        from datetime import date, timedelta

        deadline = (date.today() + timedelta(days=21)).strftime("%Y-%m-%d")
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, deadline=deadline)
        assert result.get("success") is True, result

        record = read_back(todo_id, lambda r: r is not None and r.get("deadline") == deadline)
        assert record is not None and record.get("deadline") == deadline, record

    def test_deadline_empty_clears(self, mcp, sandbox):
        from datetime import date, timedelta

        deadline = (date.today() + timedelta(days=22)).strftime("%Y-%m-%d")
        todo_id, _ = _new_todo(mcp, sandbox, deadline=deadline)
        record = read_back(todo_id, lambda r: r is not None and r.get("deadline") == deadline)
        assert record is not None and record.get("deadline") == deadline

        result = mcp.call_sync("update_todo", id=todo_id, deadline="")
        assert result.get("success") is True, result

        record = read_back(todo_id, lambda r: r is not None and r.get("deadline") is None)
        assert record is not None and record.get("deadline") is None, record


class TestUpdateTodoTags:
    def test_tags_set(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, tags=sandbox.tag_name)
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], record

    def test_tags_empty_clears(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, tags=sandbox.tag_name)
        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name]

        result = mcp.call_sync("update_todo", id=todo_id, tags="")
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and not (r.get("tags") or [])
        )
        assert record is not None and not (record.get("tags") or []), record

    def test_tags_comma_whitespace_clears(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox, tags=sandbox.tag_name)
        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name]

        result = mcp.call_sync("update_todo", id=todo_id, tags=" , ")
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and not (r.get("tags") or [])
        )
        assert record is not None and not (record.get("tags") or []), record

    def test_tags_unknown_only_is_noop(self, mcp, sandbox, live_server):
        """Under FAIL_ON_UNKNOWN (this environment's default), an
        unknown-only tags request should fail with TAG_VALIDATION_FAILED
        rather than silently no-op; under a filtering policy it would be a
        no-op (existing tags unchanged). Assert the behavior implied by the
        active policy, mirroring test_todo_create_delete.py's pattern."""
        from things_mcp.config import TagCreationPolicy

        policy = live_server.config.tag_creation_policy
        todo_id, _ = _new_todo(mcp, sandbox, tags=sandbox.tag_name)
        record = read_back(
            todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None

        unknown_tag = f"hq-gbl-reg-nonexistent-update-{ts()}"
        result = mcp.call_sync("update_todo", id=todo_id, tags=unknown_tag)

        if policy == TagCreationPolicy.FAIL_ON_UNKNOWN:
            assert_write_error(result, "TAG_VALIDATION_FAILED")
            record = read_back(
                todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
            )
            assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], record
        else:
            assert result.get("success") is True, result
            record = read_back(
                todo_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
            )
            assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], (
                "unknown-only tags request should be a no-op (existing tags unchanged), got "
                f"{record}"
            )


class TestUpdateTodoWhen:
    @pytest.mark.parametrize("keyword", ["tomorrow", "someday", "evening", "tonight"])
    def test_when_keyword(self, mcp, sandbox, keyword):
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when=keyword)
        assert result.get("success") is True, result

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None, f"{keyword}: todo never read back"

    def test_when_today_membership(self, mcp, sandbox):
        """hq-x9z fixed: update_todo(when='today') (the AppleScript
        scheduler, shared with add_todo's 'today' seed class) now uses
        `move theTodo to list "Today"` instead of the `schedule` verb, and
        yields start='Anytime' with start_date=today - matching the
        URL-scheme when='today' path. things.today() membership is
        verified separately below (test_when_today_in_things_today_list);
        things.anytime() membership is verified below
        (test_when_today_in_things_anytime_list)."""
        from datetime import date

        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="today")
        assert result.get("success") is True, result

        today_str = date.today().strftime("%Y-%m-%d")
        record = read_back(
            todo_id, lambda r: r is not None and r.get("start_date") == today_str
        )
        assert record is not None and record.get("start_date") == today_str, record
        assert record.get("start") == "Anytime", record

    def test_when_today_in_things_today_list(self, mcp, sandbox):
        """update_todo(when='today') (fixed as of hq-x9z to yield
        start='Anytime', start_date=today) is a member of things.today() -
        confirmed live rather than assumed."""
        import things

        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="today")
        assert result.get("success") is True, result

        read_back(todo_id, lambda r: r is not None and r.get("start_date") is not None)

        def _in_today():
            return any(t["uuid"] == todo_id for t in things.today() or [])

        deadline = time.monotonic() + 20
        found = _in_today()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_today()
        assert found, "expected todo to be a member of things.today()"

    def test_when_today_in_things_anytime_list(self, mcp, sandbox):
        """hq-x9z fixed: update_todo(when='today') now yields
        start='Anytime', so it must also be a member of things.anytime() -
        previously this was the actual hq-x9z bug (absent from
        things.anytime() while present in things.today())."""
        import things

        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="today")
        assert result.get("success") is True, result

        read_back(todo_id, lambda r: r is not None and r.get("start_date") is not None)

        def _in_anytime():
            return any(t["uuid"] == todo_id for t in things.anytime() or [])

        deadline = time.monotonic() + 20
        found = _in_anytime()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_anytime()
        assert found, "expected todo to be a member of things.anytime()"

    def test_when_anytime_in_things_anytime_list(self, mcp, sandbox):
        import things

        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="anytime")
        assert result.get("success") is True, result

        read_back(todo_id, lambda r: r is not None)

        def _in_anytime():
            return any(t["uuid"] == todo_id for t in things.anytime() or [])

        deadline = time.monotonic() + 20
        found = _in_anytime()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_anytime()
        assert found, "expected todo to be a member of things.anytime()"

    def test_when_iso_date(self, mcp, sandbox):
        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=11)).strftime("%Y-%m-%d")
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when=when_date)
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("start_date") == when_date
        )
        assert record is not None and record.get("start_date") == when_date, record

    def test_when_empty_rejected(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="")
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "when"

    def test_when_whitespace_rejected(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="   ")
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "when"

    def test_when_iso_date_with_time_sets_reminder(self, mcp, sandbox, live_server):
        """hq-4gn: update_todo(when='YYYY-MM-DD@HH:MM') is routed via the
        Things URL scheme's 'update' action (same as when='evening'), which
        sets the reminder natively - the AppleScript scheduling path
        (schedule_todo_reliable) used to silently drop the '@HH:MM'
        component. Requires the auth token (same as heading/evening)."""
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when=f"{when_date}@15:45")
        assert result.get("success") is True, result

        record = read_back(
            todo_id,
            lambda r: r is not None and r.get("reminder_time") is not None,
        )
        assert record is not None
        assert record.get("reminder_time") == "15:45", record
        assert record.get("start_date") == when_date, record

    def test_when_iso_date_with_time_invalid_hour_rejected(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="2031-06-15@25:99")
        assert_write_error(result, "INVALID_WHEN")


class TestUpdateTodoWhenTimeNoAuthToken:
    def test_when_time_without_auth_token_shape(self, mcp, sandbox, live_server):
        """hq-4gn: like when='evening', when='YYYY-MM-DD@HH:MM' requires the
        auth token, checked BEFORE any AppleScript write - a title passed in
        the same call must not be applied either."""
        from datetime import date, timedelta

        manager = live_server.applescript_manager
        original_token = manager.auth_token
        todo_id, original_title = _new_todo(mcp, sandbox)
        when_date = (date.today() + timedelta(days=10)).strftime("%Y-%m-%d")
        try:
            manager.auth_token = None
            should_not_apply = f"SHOULD-NOT-APPLY-{ts()}"
            result = mcp.call_sync(
                "update_todo",
                id=todo_id,
                when=f"{when_date}@15:45",
                title=should_not_apply,
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
        finally:
            manager.auth_token = original_token

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record


class TestUpdateTodoUnknownId:
    def test_unknown_id_write_error(self, mcp, sandbox):
        result = mcp.call_sync(
            "update_todo", id="bogus-update-id-does-not-exist", title="new title"
        )
        # hq-wbm: unknown primary target id is now pre-checked via
        # things.py before any write and surfaced as NOT_FOUND, consistent
        # with list_id/list_title resolution (module docstring).
        assert_write_error(result, "NOT_FOUND")

    def test_project_id_as_primary_target_rejected(self, mcp, sandbox):
        """A project id passed as the primary target id must be rejected,
        not silently applied - AppleScript's `to do id "..."` unexpectedly
        also resolves a project uuid (verified live against the real
        Things dictionary), so without this pre-check update_todo would
        rename/modify the caller's project instead of erroring."""
        result = mcp.call_sync(
            "update_todo", id=sandbox.project_id, title="should not be applied"
        )
        assert_write_error(result, "VALIDATION_ERROR")

        # Confirm the sandbox project's title was NOT changed.
        project_record = read_back(sandbox.project_id, lambda r: r is not None)
        assert project_record is not None
        assert project_record.get("title") != "should not be applied", project_record


# ---------------------------------------------------------------------------
# 2. Status 3x3 table
# ---------------------------------------------------------------------------


STATUS_CASES = [
    # (completed, canceled, expected_status)
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


class TestUpdateTodoStatus3x3:
    @pytest.mark.parametrize("completed,canceled,expected_status", STATUS_CASES)
    def test_status_combination(self, mcp, sandbox, completed, canceled, expected_status):
        todo_id, _ = _new_todo(mcp, sandbox)
        kwargs = {}
        if completed is not None:
            kwargs["completed"] = completed
        if canceled is not None:
            kwargs["canceled"] = canceled

        result = mcp.call_sync("update_todo", id=todo_id, **kwargs)
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("status") == expected_status
        )
        assert record is not None and record.get("status") == expected_status, record

        item = _get_item(mcp, todo_id)
        assert item.get("status") == expected_status, item
        if expected_status == "completed":
            assert item.get("completionDate"), item
            assert not item.get("cancellationDate"), item
        elif expected_status == "canceled":
            assert item.get("cancellationDate"), item
            assert not item.get("completionDate"), item
        else:
            assert not item.get("completionDate"), item
            assert not item.get("cancellationDate"), item

    def test_canceled_false_alone_reopens(self, mcp, sandbox):
        """Explicitly documents that canceled='false' alone (completed
        omitted) reopens a completed todo - not a no-op."""
        todo_id, _ = _new_todo(mcp, sandbox)
        complete_result = mcp.call_sync("update_todo", id=todo_id, completed="true")
        assert complete_result.get("success") is True, complete_result
        record = read_back(todo_id, lambda r: r is not None and r.get("status") == "completed")
        assert record is not None and record.get("status") == "completed"

        reopen_result = mcp.call_sync("update_todo", id=todo_id, canceled="false")
        assert reopen_result.get("success") is True, reopen_result
        record = read_back(todo_id, lambda r: r is not None and r.get("status") == "incomplete")
        assert record is not None and record.get("status") == "incomplete", record

    @pytest.mark.parametrize("field", ["completed", "canceled"])
    @pytest.mark.parametrize("bad_value", ["yes", "1"])
    def test_invalid_bool_strings_rejected(self, mcp, sandbox, field, bad_value):
        todo_id, _ = _new_todo(mcp, sandbox)
        kwargs = {field: bad_value}
        result = mcp.call_sync("update_todo", id=todo_id, **kwargs)
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == field, result

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("status") == "incomplete", record


# ---------------------------------------------------------------------------
# 3. Moves
# ---------------------------------------------------------------------------


class TestUpdateTodoMoves:
    def test_move_to_project_b(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, list_id=sandbox.project_b_id)
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
        )
        assert record is not None and record.get("project") == sandbox.project_b_id, record

    def test_move_to_area(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, list_id=sandbox.area_id)
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("area") == sandbox.area_id
        )
        assert record is not None and record.get("area") == sandbox.area_id, record

    def test_move_via_list_title_project_b(self, mcp, sandbox):
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, list_title=sandbox.project_b_title)
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
        )
        assert record is not None and record.get("project") == sandbox.project_b_id, record

    def test_list_title_unknown_rejected_no_partial_update(self, mcp, sandbox):
        todo_id, original_title = _new_todo(mcp, sandbox)
        should_not_apply = f"SHOULD-NOT-APPLY-{ts()}"
        result = mcp.call_sync(
            "update_todo",
            id=todo_id,
            list_title=f"hq-gbl-reg-nonexistent-{ts()}",
            title=should_not_apply,
        )
        assert_write_error(result, "NOT_FOUND")

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

    def test_list_title_ambiguous_rejected_no_partial_update(self, mcp, sandbox):
        """Creates a temporary duplicate-titled project (matching project B's
        title), tracked directly via tracked_project_ids, asserts the
        AMBIGUOUS_TARGET error and that title was NOT applied, then trashes
        the duplicate in-test."""
        dup_result = mcp.call_sync(
            "add_project", title=sandbox.project_b_title, area_id=sandbox.area_id
        )
        assert dup_result.get("success") is True, dup_result
        dup_project_id = dup_result.get("project_id")
        assert dup_project_id
        sandbox.tracked_project_ids.append(dup_project_id)

        todo_id, original_title = _new_todo(mcp, sandbox)
        should_not_apply = f"SHOULD-NOT-APPLY-{ts()}"
        result = mcp.call_sync(
            "update_todo",
            id=todo_id,
            list_title=sandbox.project_b_title,
            title=should_not_apply,
        )
        assert_write_error(result, "AMBIGUOUS_TARGET")
        ids = result.get("ids")
        assert isinstance(ids, list) and len(ids) >= 2, result

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

        delete_result = mcp.call_sync("delete_todo", todo_id=dup_project_id)
        assert delete_result.get("success") is True, delete_result

    def test_list_id_completed_project_rejected_no_partial_update(self, mcp, sandbox):
        todo_id, original_title = _new_todo(mcp, sandbox)
        should_not_apply = f"SHOULD-NOT-APPLY-{ts()}"
        result = mcp.call_sync(
            "update_todo",
            id=todo_id,
            list_id=sandbox.done_project_id,
            title=should_not_apply,
        )
        assert_write_error(result, "TARGET_COMPLETED")

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record
        assert record.get("project") == sandbox.project_id, record

    def test_list_id_precedence_over_list_title(self, mcp, sandbox):
        """When both list_id and list_title are given, list_id wins - here
        list_id points at project B while list_title points at the
        (different) main sandbox project, so a successful move to project B
        proves list_id took precedence."""
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync(
            "update_todo",
            id=todo_id,
            list_id=sandbox.project_b_id,
            list_title=sandbox.project_title,
        )
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
        )
        assert record is not None and record.get("project") == sandbox.project_b_id, record


# ---------------------------------------------------------------------------
# 4. Heading
# ---------------------------------------------------------------------------


class TestUpdateTodoHeading:
    def test_heading_move(self, mcp, sandbox, live_server):
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, heading=sandbox.heading_title)
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("heading") == sandbox.heading_id
        )
        assert record is not None and record.get("heading") == sandbox.heading_id, record

        item = _get_item(mcp, todo_id)
        assert item.get("heading") == sandbox.heading_id, item
        assert item.get("headingTitle") == sandbox.heading_title, item
        assert item.get("project") == sandbox.project_id, item
        assert item.get("projectTitle") == sandbox.project_title, item

    def test_reheading_already_under_heading_is_idempotent(self, mcp, sandbox, live_server):
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        todo_id, _ = _new_todo(mcp, sandbox)
        first = mcp.call_sync("update_todo", id=todo_id, heading=sandbox.heading_title)
        assert first.get("success") is True, first
        record = read_back(
            todo_id, lambda r: r is not None and r.get("heading") == sandbox.heading_id
        )
        assert record is not None and record.get("heading") == sandbox.heading_id

        second = mcp.call_sync("update_todo", id=todo_id, heading=sandbox.heading_title)
        assert second.get("success") is True, second
        record = read_back(
            todo_id, lambda r: r is not None and r.get("heading") == sandbox.heading_id
        )
        assert record is not None and record.get("heading") == sandbox.heading_id, record

    def test_heading_plus_list_id_project_b_missing_heading_warns(self, mcp, sandbox, live_server):
        """Project B has no headings, so moving-and-heading-placing into it
        should warn that the heading could not be confirmed, while the move
        itself still succeeds."""
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync(
            "update_todo",
            id=todo_id,
            heading=sandbox.heading_title,
            list_id=sandbox.project_b_id,
        )
        assert result.get("success") is True, result
        assert result.get("warnings"), result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
        )
        assert record is not None and record.get("project") == sandbox.project_b_id, record

    def test_heading_empty_rejected(self, mcp, sandbox, live_server):
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        todo_id, original_title = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, heading="")
        assert_write_error(result, "INVALID_HEADING")

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

    def test_heading_when_todo_in_area_warns(self, mcp, sandbox, live_server):
        """Move a to-do directly into the area (no project) first, then
        request a heading move with no list_id/list_title - Things' URL
        scheme silently ignores 'heading' for a to-do with no project, and
        update_todo surfaces a warning rather than an error."""
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        todo_id, _ = _new_todo(mcp, sandbox)
        move_result = mcp.call_sync("update_todo", id=todo_id, list_id=sandbox.area_id)
        assert move_result.get("success") is True, move_result
        record = read_back(
            todo_id, lambda r: r is not None and r.get("area") == sandbox.area_id
        )
        assert record is not None and record.get("area") == sandbox.area_id

        result = mcp.call_sync("update_todo", id=todo_id, heading="Some Heading Title")
        assert result.get("success") is True, result
        assert result.get("warnings"), result

    def test_heading_missing_in_target_warns(self, mcp, sandbox, live_server):
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        bogus_heading = f"hq-gbl-reg-nonexistent-heading-{ts()}"
        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, heading=bogus_heading)
        assert result.get("success") is True, result
        assert result.get("warnings"), result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_id
        )
        assert record is not None
        assert record.get("project") == sandbox.project_id, record
        assert record.get("heading") != bogus_heading


class TestUpdateTodoAuthTokenNotConfigured:
    def test_heading_without_auth_token_shape(self, mcp, sandbox, live_server):
        """Monkeypatches the shared live AppleScriptManager's auth_token to
        None for the duration of this test only, restoring it in a finally
        block. The URL-scheme call this triggers must never actually reach
        Things (the auth check runs before any write), so this is safe to
        run even without a real token configured."""
        manager = live_server.applescript_manager
        original_token = manager.auth_token
        todo_id, original_title = _new_todo(mcp, sandbox)
        try:
            manager.auth_token = None
            should_not_apply = f"SHOULD-NOT-APPLY-{ts()}"
            result = mcp.call_sync(
                "update_todo",
                id=todo_id,
                heading=sandbox.heading_title,
                title=should_not_apply,
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
        finally:
            manager.auth_token = original_token

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record


# ---------------------------------------------------------------------------
# 5. Evening
# ---------------------------------------------------------------------------


class TestUpdateTodoEvening:
    def test_evening_read_back(self, mcp, sandbox, live_server):
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        import things
        from datetime import date

        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="evening")
        assert result.get("success") is True, result

        today_str = date.today().strftime("%Y-%m-%d")
        record = read_back(
            todo_id,
            lambda r: r is not None and r.get("start") == "Anytime" and r.get("start_date") == today_str,
        )
        assert record is not None, record
        assert record.get("start") == "Anytime", record
        assert record.get("start_date") == today_str, record

        def _in_today():
            return any(t["uuid"] == todo_id for t in things.today() or [])

        deadline = time.monotonic() + 20
        found = _in_today()
        while not found and time.monotonic() < deadline:
            time.sleep(0.25)
            found = _in_today()
        assert found, "expected evening-scheduled todo to be a member of things.today()"

    def test_evening_read_back_via_get_todo_by_id(self, mcp, sandbox, live_server):
        """hq-wsa.9: get_todo_by_id reports evening:true iff the to-do is
        actually scheduled for This Evening (TMTask.startBucket == 1, read
        via a narrow read-only raw-SQL side channel since things.py itself
        never exposes it), and omits the key once rescheduled away from
        evening."""
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        todo_id, _ = _new_todo(mcp, sandbox)
        result = mcp.call_sync("update_todo", id=todo_id, when="evening")
        assert result.get("success") is True, result

        deadline = time.monotonic() + 20
        item = _get_item(mcp, todo_id)
        while item.get("evening") is not True and time.monotonic() < deadline:
            time.sleep(0.25)
            item = _get_item(mcp, todo_id)
        assert item.get("evening") is True, item

        result = mcp.call_sync("update_todo", id=todo_id, when="today")
        assert result.get("success") is True, result

        deadline = time.monotonic() + 20
        item = _get_item(mcp, todo_id)
        while "evening" in item and time.monotonic() < deadline:
            time.sleep(0.25)
            item = _get_item(mcp, todo_id)
        assert "evening" not in item, item

    def test_evening_plus_list_id_moves_exactly_once(self, mcp, sandbox, live_server):
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        import things

        title = sandbox_title("evening move once " + ts())
        todo_id, _ = _new_todo(mcp, sandbox, title=title)
        result = mcp.call_sync(
            "update_todo", id=todo_id, when="evening", list_id=sandbox.project_b_id
        )
        assert result.get("success") is True, result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_b_id
        )
        assert record is not None and record.get("project") == sandbox.project_b_id, record

        matches = [
            t
            for t in things.tasks(type="to-do", status=None, trashed=None) or []
            if t.get("title") == title
        ]
        assert len(matches) == 1, (
            f"expected exactly one to-do titled {title!r}, found {len(matches)}: {matches}"
        )
        assert matches[0]["uuid"] == todo_id


class TestUpdateTodoEveningNoAuthToken:
    def test_evening_without_auth_token_shape(self, mcp, sandbox, live_server):
        manager = live_server.applescript_manager
        original_token = manager.auth_token
        todo_id, original_title = _new_todo(mcp, sandbox)
        try:
            manager.auth_token = None
            should_not_apply = f"SHOULD-NOT-APPLY-{ts()}"
            result = mcp.call_sync(
                "update_todo", id=todo_id, when="evening", title=should_not_apply
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
        finally:
            manager.auth_token = original_token

        record = read_back(todo_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record


# ---------------------------------------------------------------------------
# 6. Combo call
# ---------------------------------------------------------------------------


class TestUpdateTodoCombo:
    def test_title_notes_tags_deadline_list_id_all_applied(self, mcp, sandbox):
        from datetime import date, timedelta

        todo_id, _ = _new_todo(mcp, sandbox)
        new_title = sandbox_title("combo update " + ts())
        new_notes = "combo notes\nsecond line"
        deadline = (date.today() + timedelta(days=17)).strftime("%Y-%m-%d")

        result = mcp.call_sync(
            "update_todo",
            id=todo_id,
            title=new_title,
            notes=new_notes,
            tags=sandbox.tag_name,
            deadline=deadline,
            list_id=sandbox.project_b_id,
        )
        assert result.get("success") is True, result

        record = read_back(
            todo_id,
            lambda r: r is not None
            and r.get("title") == new_title
            and r.get("project") == sandbox.project_b_id,
        )
        assert record is not None, record
        assert record.get("title") == new_title, record
        assert record.get("notes") == new_notes, record
        assert (record.get("tags") or []) == [sandbox.tag_name], record
        assert record.get("deadline") == deadline, record
        assert record.get("project") == sandbox.project_b_id, record
