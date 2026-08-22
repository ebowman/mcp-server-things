"""hq-gbl.10: Regression (live) for add_project, update_project,
get_project_headings, add_area, update_area, get_projects, and get_areas,
driven through the real MCP tool boundary.

Every project created here is created inside sandbox.area_id (area_id=) and
tracked via sandbox.tracked_project_ids (never sandbox.track(), which is
for to-dos). Extra areas are tracked via sandbox.track_area(), extended by
this bead onto the Sandbox class in conftest.py.

Error-code notes (confirmed by reading source, not assumed):
  - add_project(when='evening'): scheduling/todo_operations.py's
    add_project() explicitly rejects when='evening'/'tonight' with
    UNSUPPORTED_FOR_PROJECTS ("Things has no 'This Evening' concept for
    projects") - checked BEFORE any AppleScript/URL-scheme write.
    update_project(when='evening') is rejected the same way, same code,
    same pre-write check (scheduling/todo_operations.py update_project()).
  - add_project(todos='##H1' with nothing after): _add_project_via_url_scheme
    (scheduling/todo_operations.py) returns a VALIDATION_ERROR ("Empty
    heading title...", field='todos') BEFORE the URL-scheme call is ever
    issued - nothing is created. Verified against source: the check runs
    inside the items-building loop, ahead of the `execute_url_scheme('json', ...)`
    call.
  - get_project_headings: _get_project_headings_sync (tools_helpers/
    read_operations.py) returns the CANONICAL lower_snake read-tool
    contract via read_error() - {'success': False, 'error': 'not_found'|
    'invalid_type'|'internal_error', 'message': ...} - NOT the
    {'error': true, 'error_type': ...} shape the bead text describes (that
    shape does not appear in the current source; the bead text is stale -
    documented here as observed doc drift, not fixed).
  - update_area: NO_FIELDS_PROVIDED (both title and tags omitted),
    NOT_FOUND (unknown area_id, detected via the AppleScript error-message
    substring match), VALIDATION_ERROR (title='') - all confirmed in
    tools_helpers/write_operations.py's update_area().

bead hq-x9z (fixed): when='today' via the AppleScript scheduler used to
leave start='Someday' with start_date=today rather than start='Anytime'.
Fixed by routing the today-path through `move theTodo to list "Today"`
instead of the `schedule` verb - this applies to update_project's `when`
path too (shared scheduler). See test_when_today_start_is_anytime_not_someday
below and test_update_todo.py's own notes.
"""
import time

import pytest

from regression.helpers import (
    assert_read_error,
    assert_write_error,
    read_back,
    sandbox_title,
    ts,
)

pytestmark = pytest.mark.live


def _new_project(mcp, sandbox, title=None, **kwargs):
    """Create a fresh, tracked project inside the sandbox area and return
    its id. Always created inside sandbox.area_id unless the caller passes
    an explicit area_id/area_title override."""
    title = title or sandbox_title("proj " + ts())
    kwargs.setdefault("area_id", sandbox.area_id)
    result = mcp.call_sync("add_project", title=title, **kwargs)
    assert result.get("success") is True, result
    project_id = result.get("project_id")
    assert project_id
    sandbox.tracked_project_ids.append(project_id)
    return project_id, title, result


def _get_project_item(mcp, project_id):
    """get_todo_by_id resolves projects too (per CLAUDE.md)."""
    result = mcp.call_sync("get_todo_by_id", todo_id=project_id)
    assert "item" in result, result
    return result["item"]


# ---------------------------------------------------------------------------
# 1. add_project
# ---------------------------------------------------------------------------


class TestAddProjectFields:
    def test_title_notes_special_chars(self, mcp, sandbox):
        title = sandbox_title('proj "quoted", back\\slash, comma \U0001F600 ' + ts())
        notes = 'Line one "quoted"\nLine two \\ backslash \U0001F600'
        project_id, _, result = _new_project(mcp, sandbox, title=title, notes=notes)

        record = read_back(project_id, lambda r: r is not None and r.get("title") == title)
        assert record is not None and record.get("title") == title, record
        assert record.get("notes") == notes, record

    def test_tags(self, mcp, sandbox):
        project_id, _, _ = _new_project(mcp, sandbox, tags=sandbox.tag_name)
        record = read_back(
            project_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], record

    @pytest.mark.parametrize("keyword", ["today", "tomorrow", "someday", "anytime"])
    def test_when_keywords(self, mcp, sandbox, keyword):
        project_id, _, result = _new_project(mcp, sandbox, when=keyword)
        assert result.get("success") is True, result
        record = read_back(project_id, lambda r: r is not None)
        assert record is not None, f"{keyword}: project never read back"

    def test_when_evening_rejected(self, mcp, sandbox):
        title = sandbox_title("proj evening reject " + ts())
        result = mcp.call_sync(
            "add_project", title=title, area_id=sandbox.area_id, when="evening"
        )
        assert_write_error(result, "UNSUPPORTED_FOR_PROJECTS")
        assert result.get("field") == "when", result

        # Nothing created: no project with this exact title exists.
        import things

        matches = [
            p for p in things.projects(status=None, trashed=None) or [] if p.get("title") == title
        ]
        assert matches == [], matches

    def test_when_iso_date_with_time_sets_reminder(self, mcp, sandbox, live_server):
        """hq-4gn: unlike when='evening' (UNSUPPORTED_FOR_PROJECTS),
        add_project(when='YYYY-MM-DD@HH:MM') IS supported - routed via the
        Things URL scheme's 'update-project' action after the AppleScript
        create (requires the auth token), which sets the project's reminder
        natively."""
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=13)).strftime("%Y-%m-%d")
        title = sandbox_title("proj when time " + ts())
        result = mcp.call_sync(
            "add_project", title=title, area_id=sandbox.area_id, when=f"{when_date}@10:30"
        )
        assert result.get("success") is True, result
        project_id = result.get("project_id")
        assert project_id
        sandbox.tracked_project_ids.append(project_id)

        record = read_back(
            project_id,
            lambda r: r is not None and r.get("reminder_time") is not None,
        )
        assert record is not None
        assert record.get("reminder_time") == "10:30", record
        assert record.get("start_date") == when_date, record

    def test_deadline_valid(self, mcp, sandbox):
        from datetime import date, timedelta

        deadline = (date.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        project_id, _, result = _new_project(mcp, sandbox, deadline=deadline)
        assert result.get("success") is True, result
        record = read_back(
            project_id, lambda r: r is not None and r.get("deadline") == deadline
        )
        assert record is not None and record.get("deadline") == deadline, record

    def test_deadline_relative_rejected(self, mcp, sandbox):
        title = sandbox_title("proj bad deadline " + ts())
        result = mcp.call_sync(
            "add_project", title=title, area_id=sandbox.area_id, deadline="today"
        )
        assert_write_error(result, "INVALID_DEADLINE")
        assert result.get("field") == "deadline", result

        import things

        matches = [
            p for p in things.projects(status=None, trashed=None) or [] if p.get("title") == title
        ]
        assert matches == [], matches

    def test_area_id_sandbox_area(self, mcp, sandbox):
        project_id, _, _ = _new_project(mcp, sandbox)
        record = read_back(
            project_id, lambda r: r is not None and r.get("area") == sandbox.area_id
        )
        assert record is not None and record.get("area") == sandbox.area_id, record

    def test_area_title_unique(self, mcp, sandbox):
        title = sandbox_title("proj by area title " + ts())
        result = mcp.call_sync(
            "add_project", title=title, area_title=sandbox.area_title
        )
        assert result.get("success") is True, result
        project_id = result.get("project_id")
        sandbox.tracked_project_ids.append(project_id)

        record = read_back(
            project_id, lambda r: r is not None and r.get("area") == sandbox.area_id
        )
        assert record is not None and record.get("area") == sandbox.area_id, record

    def test_area_title_unknown(self, mcp, sandbox):
        """hq-rmh (fixed): add_project pre-resolves area_title via
        things.py BEFORE any AppleScript write
        (TodoOperations._resolve_area). An unresolvable area_title now
        returns a structured NOT_FOUND error and creates nothing - no more
        orphaned, un-areaed project persisting despite a reported failure."""
        title = sandbox_title("proj unknown area " + ts())
        bogus_area = f"hq-gbl-reg-nonexistent-area-{ts()}"
        result = mcp.call_sync("add_project", title=title, area_title=bogus_area)

        # Regardless of reported success, track/clean up any project that
        # actually landed with this exact title - this is the safety net
        # for the previously-observed partial-creation-on-error quirk
        # documented above, so a leaked live object never survives this
        # test either way.
        import things

        def _find_created():
            return [
                p for p in things.projects(status=None, trashed=None) or []
                if p.get("title") == title
            ]

        deadline = time.monotonic() + 10
        matches = _find_created()
        while not matches and time.monotonic() < deadline:
            time.sleep(0.5)
            matches = _find_created()
        for p in matches:
            sandbox.tracked_project_ids.append(p["uuid"])

        assert_write_error(result, "NOT_FOUND")
        assert not matches, (
            "unknown area_title must not create a project; found: "
            f"{[p['uuid'] for p in matches]}"
        )

    def test_area_title_ambiguous(self, mcp, sandbox):
        """hq-rmh: an area_title matching more than one area returns
        AMBIGUOUS_TARGET and creates nothing."""
        dup_title = sandbox_title("proj dup area " + ts())

        area_result_1 = mcp.call_sync("add_area", title=dup_title)
        assert area_result_1.get("success") is True, area_result_1
        area_id_1 = area_result_1.get("area_id")
        sandbox.track_area(area_id_1)

        area_result_2 = mcp.call_sync("add_area", title=dup_title)
        assert area_result_2.get("success") is True, area_result_2
        area_id_2 = area_result_2.get("area_id")
        sandbox.track_area(area_id_2)

        title = sandbox_title("proj via ambiguous area " + ts())
        result = mcp.call_sync("add_project", title=title, area_title=dup_title)

        import things

        matches = [
            p for p in things.projects(status=None, trashed=None) or []
            if p.get("title") == title
        ]
        for p in matches:
            sandbox.tracked_project_ids.append(p["uuid"])

        assert_write_error(result, "AMBIGUOUS_TARGET")
        assert not matches, (
            "ambiguous area_title must not create a project; found: "
            f"{[p['uuid'] for p in matches]}"
        )

    def test_area_id_unknown(self, mcp, sandbox):
        """hq-rmh: an unresolvable area_id returns NOT_FOUND and creates
        nothing."""
        title = sandbox_title("proj unknown area id " + ts())
        bogus_area_id = f"hq-gbl-reg-nonexistent-areaid-{ts()}"
        result = mcp.call_sync("add_project", title=title, area_id=bogus_area_id)

        import things

        matches = [
            p for p in things.projects(status=None, trashed=None) or []
            if p.get("title") == title
        ]
        for p in matches:
            sandbox.tracked_project_ids.append(p["uuid"])

        assert_write_error(result, "NOT_FOUND")
        assert not matches, (
            "unknown area_id must not create a project; found: "
            f"{[p['uuid'] for p in matches]}"
        )


class TestAddProjectTodosPayload:
    def test_three_plain_lines(self, mcp, sandbox):
        import things

        project_id, _, result = _new_project(
            mcp, sandbox, todos="Task one\nTask two\nTask three"
        )
        assert result.get("todos_created") == 3, result

        def _count():
            return len(things.tasks(project=project_id, type="to-do", status=None, trashed=None) or [])

        deadline = time.monotonic() + 20
        count = _count()
        while count < 3 and time.monotonic() < deadline:
            time.sleep(0.25)
            count = _count()
        assert count == 3, f"expected 3 to-dos in project, found {count}"

    def test_headings_and_todos(self, mcp, sandbox):
        project_id, _, result = _new_project(
            mcp, sandbox, todos="##H1\na\n##H2\nb\nc"
        )
        assert result.get("headings_created") == 2, result
        assert result.get("todos_created") == 3, result

        def _headings():
            return mcp.call_sync("get_project_headings", project_id=project_id)

        deadline = time.monotonic() + 20
        headings_result = _headings()
        items = headings_result.get("items") or []
        while len(items) < 2 and time.monotonic() < deadline:
            time.sleep(0.5)
            headings_result = _headings()
            items = headings_result.get("items") or []

        assert len(items) == 2, headings_result
        by_title = {item["title"]: item for item in items}
        assert set(by_title.keys()) == {"H1", "H2"}, by_title
        assert by_title["H1"]["todoCount"] == 1, by_title["H1"]
        assert by_title["H2"]["todoCount"] == 2, by_title["H2"]

    def test_heading_with_nothing_after_rejected_nothing_created(self, mcp, sandbox):
        import things

        title = sandbox_title("proj bad heading " + ts())
        result = mcp.call_sync(
            "add_project", title=title, area_id=sandbox.area_id, todos="##"
        )
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "todos", result

        matches = [
            p for p in things.projects(status=None, trashed=None) or [] if p.get("title") == title
        ]
        if matches:
            # Documented as "nothing created" by source inspection, but if
            # live behavior diverges, track/trash and fail loudly rather
            # than leaking a sandbox object.
            for p in matches:
                sandbox.tracked_project_ids.append(p["uuid"])
            pytest.fail(
                "expected no project to be created for a '##' line with no "
                f"heading title, but found: {matches}"
            )

    def test_blank_and_whitespace_lines_ignored(self, mcp, sandbox):
        import things

        project_id, _, result = _new_project(
            mcp, sandbox, todos="Task A\n\n   \nTask B"
        )
        assert result.get("todos_created") == 2, result

        def _count():
            return len(things.tasks(project=project_id, type="to-do", status=None, trashed=None) or [])

        deadline = time.monotonic() + 20
        count = _count()
        while count < 2 and time.monotonic() < deadline:
            time.sleep(0.25)
            count = _count()
        assert count == 2, f"expected 2 to-dos (blank/whitespace lines ignored), found {count}"

    def test_thirty_todos(self, mcp, sandbox):
        import things

        lines = "\n".join(f"Bulk task {i}" for i in range(30))
        project_id, _, result = _new_project(mcp, sandbox, todos=lines)
        assert result.get("todos_created") == 30, result

        def _count():
            return len(things.tasks(project=project_id, type="to-do", status=None, trashed=None) or [])

        deadline = time.monotonic() + 30
        count = _count()
        while count < 30 and time.monotonic() < deadline:
            time.sleep(0.5)
            count = _count()
        assert count == 30, f"expected 30 to-dos, found {count}"


# ---------------------------------------------------------------------------
# 2. update_project
# ---------------------------------------------------------------------------


class TestUpdateProjectFields:
    def test_title_read_back(self, mcp, sandbox):
        project_id, _, _ = _new_project(mcp, sandbox)
        new_title = sandbox_title("updated proj " + ts())
        result = mcp.call_sync("update_project", id=project_id, title=new_title)
        assert result.get("success") is True, result

        record = read_back(project_id, lambda r: r is not None and r.get("title") == new_title)
        assert record is not None and record.get("title") == new_title, record

    def test_title_empty_rejected(self, mcp, sandbox):
        project_id, original_title, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, title="")
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "title", result

        record = read_back(project_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

    def test_notes_set_and_clear(self, mcp, sandbox):
        project_id, _, _ = _new_project(mcp, sandbox, notes="initial notes")
        record = read_back(project_id, lambda r: r is not None and r.get("notes") == "initial notes")
        assert record is not None and record.get("notes") == "initial notes"

        result = mcp.call_sync("update_project", id=project_id, notes="")
        assert result.get("success") is True, result
        record = read_back(project_id, lambda r: r is not None and (r.get("notes") or "") == "")
        assert record is not None and (record.get("notes") or "") == "", record

    def test_deadline_set_and_clear(self, mcp, sandbox):
        from datetime import date, timedelta

        deadline = (date.today() + timedelta(days=40)).strftime("%Y-%m-%d")
        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, deadline=deadline)
        assert result.get("success") is True, result
        record = read_back(project_id, lambda r: r is not None and r.get("deadline") == deadline)
        assert record is not None and record.get("deadline") == deadline

        clear_result = mcp.call_sync("update_project", id=project_id, deadline="")
        assert clear_result.get("success") is True, clear_result
        record = read_back(project_id, lambda r: r is not None and r.get("deadline") is None)
        assert record is not None and record.get("deadline") is None, record

    def test_tags_set_and_clear(self, mcp, sandbox):
        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, tags=sandbox.tag_name)
        assert result.get("success") is True, result
        record = read_back(
            project_id, lambda r: r is not None and (r.get("tags") or []) == [sandbox.tag_name]
        )
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name]

        clear_result = mcp.call_sync("update_project", id=project_id, tags="")
        assert clear_result.get("success") is True, clear_result
        record = read_back(project_id, lambda r: r is not None and not (r.get("tags") or []))
        assert record is not None and not (record.get("tags") or []), record

    def test_when_evening_rejected(self, mcp, sandbox):
        project_id, original_title, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, when="evening")
        assert_write_error(result, "UNSUPPORTED_FOR_PROJECTS")
        assert result.get("field") == "when", result

        record = read_back(project_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

    def test_when_iso_date_with_time_sets_reminder(self, mcp, sandbox, live_server):
        """hq-4gn: unlike when='evening' (UNSUPPORTED_FOR_PROJECTS),
        update_project(when='YYYY-MM-DD@HH:MM') IS supported - routed via
        the Things URL scheme's 'update-project' action (requires the auth
        token), which sets the project's reminder natively."""
        if not live_server.applescript_manager.auth_token:
            pytest.skip("Things auth token not configured")

        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d")
        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync(
            "update_project", id=project_id, when=f"{when_date}@11:20"
        )
        assert result.get("success") is True, result

        record = read_back(
            project_id,
            lambda r: r is not None and r.get("reminder_time") is not None,
        )
        assert record is not None
        assert record.get("reminder_time") == "11:20", record
        assert record.get("start_date") == when_date, record

    def test_when_time_without_auth_token_shape(self, mcp, sandbox, live_server):
        """hq-4gn: like when='evening', when='YYYY-MM-DD@HH:MM' requires
        the auth token, checked BEFORE any AppleScript write - a title
        passed in the same call must not be applied either."""
        from datetime import date, timedelta

        manager = live_server.applescript_manager
        original_token = manager.auth_token
        project_id, original_title, _ = _new_project(mcp, sandbox)
        when_date = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d")
        try:
            manager.auth_token = None
            should_not_apply = sandbox_title("SHOULD-NOT-APPLY " + ts())
            result = mcp.call_sync(
                "update_project",
                id=project_id,
                when=f"{when_date}@11:20",
                title=should_not_apply,
            )
            assert_write_error(result, "AUTH_TOKEN_NOT_CONFIGURED")
            assert result.get("hint"), result
        finally:
            manager.auth_token = original_token

        record = read_back(project_id, lambda r: r is not None)
        assert record is not None and record.get("title") == original_title, record

    def test_unknown_id(self, mcp, sandbox):
        result = mcp.call_sync(
            "update_project", id="bogus-project-id-does-not-exist", title="new title"
        )
        assert result.get("success") is False, result


class TestUpdateProjectStatus3x3:
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
    def test_status_combination(self, mcp, sandbox, completed, canceled, expected_status):
        project_id, _, _ = _new_project(mcp, sandbox)
        kwargs = {}
        if completed is not None:
            kwargs["completed"] = completed
        if canceled is not None:
            kwargs["canceled"] = canceled

        result = mcp.call_sync("update_project", id=project_id, **kwargs)
        assert result.get("success") is True, result

        record = read_back(
            project_id, lambda r: r is not None and r.get("status") == expected_status
        )
        assert record is not None and record.get("status") == expected_status, record

        item = _get_project_item(mcp, project_id)
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

    def test_reopen_after_complete(self, mcp, sandbox):
        project_id, _, _ = _new_project(mcp, sandbox)
        complete_result = mcp.call_sync("update_project", id=project_id, completed="true")
        assert complete_result.get("success") is True, complete_result
        record = read_back(project_id, lambda r: r is not None and r.get("status") == "completed")
        assert record is not None and record.get("status") == "completed"

        reopen_result = mcp.call_sync("update_project", id=project_id, completed="false")
        assert reopen_result.get("success") is True, reopen_result
        record = read_back(project_id, lambda r: r is not None and r.get("status") == "incomplete")
        assert record is not None and record.get("status") == "incomplete", record


class TestUpdateProjectMoves:
    def test_area_id_move_to_second_area(self, mcp, sandbox):
        second_area_title = sandbox_title("area2 " + ts())
        area_result = mcp.call_sync("add_area", title=second_area_title)
        assert area_result.get("success") is True, area_result
        second_area_id = area_result.get("area_id")
        sandbox.track_area(second_area_id)

        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, area_id=second_area_id)
        assert result.get("success") is True, result

        record = read_back(
            project_id, lambda r: r is not None and r.get("area") == second_area_id
        )
        assert record is not None and record.get("area") == second_area_id, record

    def test_area_title_move(self, mcp, sandbox):
        second_area_title = sandbox_title("area3 " + ts())
        area_result = mcp.call_sync("add_area", title=second_area_title)
        assert area_result.get("success") is True, area_result
        second_area_id = area_result.get("area_id")
        sandbox.track_area(second_area_id)

        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync(
            "update_project", id=project_id, area_title=second_area_title
        )
        assert result.get("success") is True, result

        record = read_back(
            project_id, lambda r: r is not None and r.get("area") == second_area_id
        )
        assert record is not None and record.get("area") == second_area_id, record

    def test_area_title_unknown_no_partial_update(self, mcp, sandbox):
        """hq-rmh: update_project pre-resolves area_title via things.py
        BEFORE the single AppleScript try block that also applies title/
        notes in the same call runs - an unresolvable area_title returns
        NOT_FOUND and none of the other fields in the same call are
        applied either (previously, the area-set line would throw
        mid-script and silently discard the rest of the update while still
        reporting APPLESCRIPT_ERROR)."""
        project_id, _, _ = _new_project(mcp, sandbox)
        bogus_area = f"hq-gbl-reg-nonexistent-area-{ts()}"
        new_title = sandbox_title("proj should not rename " + ts())

        result = mcp.call_sync(
            "update_project",
            id=project_id,
            area_title=bogus_area,
            title=new_title,
        )
        assert_write_error(result, "NOT_FOUND")

        record = read_back(project_id, lambda r: r is not None)
        assert record is not None, record
        assert record.get("title") != new_title, (
            "title must not be updated when area_title resolution fails: "
            f"{record}"
        )

    def test_when_today_start_is_anytime_not_someday(self, mcp, sandbox):
        """hq-x9z fixed: update_project(when='today') shares the
        scheduler's today-path fix with update_todo - it now uses `move
        theTodo to list "Today"` instead of the `schedule` verb, yielding
        start='Anytime' with start_date=today. No longer an xfail."""
        from datetime import date

        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, when="today")
        assert result.get("success") is True, result

        today_str = date.today().strftime("%Y-%m-%d")
        record = read_back(
            project_id, lambda r: r is not None and r.get("start_date") == today_str
        )
        assert record is not None and record.get("start_date") == today_str, record
        assert record.get("start") == "Anytime", record

    def test_when_today_visible_via_get_today_include_projects(self, mcp, sandbox):
        """Not an xfail: things.today()'s own implementation unions in
        'unconfirmed_scheduled_tasks' (start_date in the past/today AND
        start='Someday') - the exact state update_project(when='today')
        produces - so list membership (via get_today(include_projects=true))
        is expected, confirmed live rather than assumed."""
        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, when="today")
        assert result.get("success") is True, result

        read_back(project_id, lambda r: r is not None and r.get("start_date") is not None)

        def _in_today_list():
            today_result = mcp.call_sync(
                "get_today", include_projects=True, mode="detailed"
            )
            items = today_result.get("items") or []
            return any(item.get("uuid") == project_id for item in items)

        deadline = time.monotonic() + 20
        found = _in_today_list()
        while not found and time.monotonic() < deadline:
            time.sleep(0.5)
            found = _in_today_list()
        assert found, "expected project to appear in get_today(include_projects=True)"

    def test_when_anytime_visible_via_get_anytime_include_projects(self, mcp, sandbox):
        """hq-cal.2: on a large enough Anytime list,
        get_anytime(include_projects=True, mode='detailed') can exceed the
        ~80KB response budget and truncate. Truncation is no longer silent
        relevance-ranked dropping (hq-cal.2 fixed context_manager.py to keep
        a deterministic, original-order prefix and surface an explicit
        truncated/truncation_hint envelope signal instead). Two acceptable
        outcomes here:
          - The fresh project fits in the (possibly full, possibly
            truncated-but-still-covering-it) result: pass directly.
          - It doesn't fit: assert the envelope explicitly reports truncation
            (truncated=True, truncation_hint present, count < total) rather
            than silently omitting the item, AND that the project is still
            reachable via a targeted read (get_todo_by_id) - nothing is
            silently unreachable.
        """
        project_id, title, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, when="anytime")
        assert result.get("success") is True, result

        read_back(project_id, lambda r: r is not None)

        def _anytime_result():
            return mcp.call_sync("get_anytime", include_projects=True, mode="detailed")

        deadline = time.monotonic() + 20
        anytime_result = _anytime_result()
        items = anytime_result.get("items") or []
        found = any(item.get("uuid") == project_id for item in items)
        while not found and time.monotonic() < deadline:
            time.sleep(0.5)
            anytime_result = _anytime_result()
            items = anytime_result.get("items") or []
            found = any(item.get("uuid") == project_id for item in items)

        if found:
            return

        # Not found in items: the only acceptable reason is explicit,
        # explicitly-flagged budget truncation - not a silent drop.
        assert anytime_result.get("truncated") is True, (
            "project missing from get_anytime(include_projects=True) items, "
            f"but response was not flagged truncated: {anytime_result}"
        )
        assert anytime_result.get("truncation_hint"), anytime_result
        assert anytime_result.get("count", 0) < anytime_result.get("total", 0), anytime_result

        # Contract: even though it's not in this page, the project
        # must still be reachable via a targeted read.
        project_item = _get_project_item(mcp, project_id)
        assert project_item.get("uuid") == project_id, project_item
        assert project_item.get("title") == title, project_item

    def test_optimize_response_truncation_preserves_order(self, mcp, sandbox):
        """hq-cal.2: when get_anytime(include_projects=True, ...) truncates
        under the response budget, the returned prefix must be an
        order-consistent prefix of the underlying (things.py-produced)
        order - i.e. truncation keeps a deterministic prefix rather than
        reordering by relevance. Compared across two response modes
        (detailed vs. minimal) that produce differently-sized truncated
        prefixes of the *same* underlying list: on this live database both
        may truncate (it is large), but whichever list is shorter must
        still equal a prefix of the longer one, since both traverse the
        same underlying order and only differ in how many items fit under
        their respective per-item size budgets."""
        detailed_result = mcp.call_sync(
            "get_anytime", include_projects=True, mode="detailed"
        )
        minimal_result = mcp.call_sync(
            "get_anytime", include_projects=True, mode="minimal"
        )
        if not detailed_result.get("truncated") and not minimal_result.get("truncated"):
            pytest.skip("get_anytime did not truncate under either mode on this database")

        detailed_uuids = [item["uuid"] for item in detailed_result.get("items") or []]
        minimal_uuids = [item["uuid"] for item in minimal_result.get("items") or []]

        shorter, longer = (
            (detailed_uuids, minimal_uuids)
            if len(detailed_uuids) <= len(minimal_uuids)
            else (minimal_uuids, detailed_uuids)
        )
        assert shorter == longer[: len(shorter)], (
            "truncated get_anytime items are not an order-consistent prefix "
            "across response modes (detailed vs minimal)"
        )

    def test_when_someday_visible_via_get_someday(self, mcp, sandbox):
        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, when="someday")
        assert result.get("success") is True, result

        record = read_back(
            project_id, lambda r: r is not None and r.get("start") == "Someday"
        )
        assert record is not None and record.get("start") == "Someday", record

        def _in_someday_list():
            someday_result = mcp.call_sync(
                "get_someday", include_projects=True, mode="detailed"
            )
            items = someday_result.get("items") or []
            return any(item.get("uuid") == project_id for item in items)

        deadline = time.monotonic() + 20
        found = _in_someday_list()
        while not found and time.monotonic() < deadline:
            time.sleep(0.5)
            found = _in_someday_list()
        assert found, "expected project to appear in get_someday(include_projects=True)"


# ---------------------------------------------------------------------------
# 3. get_project_headings
# ---------------------------------------------------------------------------


class TestGetProjectHeadings:
    def test_sandbox_project_heading_present_todo_count(self, mcp, sandbox):
        assert sandbox.heading_id, "sandbox project must have a seeded heading"

        # Add two more to-dos under the sandbox heading (URL scheme move),
        # bringing todoCount to 1 (seed) + 2 = 3, tracked for teardown.
        added_ids = []
        for i in range(2):
            result = mcp.call_sync(
                "add_todo",
                title=sandbox_title(f"heading todo {i} " + ts()),
                list_id=sandbox.project_id,
                heading=sandbox.heading_title,
            )
            assert result.get("success") is True, result
            todo_id = result.get("todo_id")
            assert todo_id
            sandbox.track(todo_id)
            added_ids.append(todo_id)

        for todo_id in added_ids:
            read_back(todo_id, lambda r: r is not None and r.get("heading") == sandbox.heading_id)

        def _fetch():
            return mcp.call_sync("get_project_headings", project_id=sandbox.project_id)

        deadline = time.monotonic() + 20
        result = _fetch()
        items = result.get("items") or []
        by_uuid = {item["uuid"]: item for item in items}
        while (
            sandbox.heading_id not in by_uuid
            or by_uuid[sandbox.heading_id].get("todoCount", 0) < 3
        ) and time.monotonic() < deadline:
            time.sleep(0.5)
            result = _fetch()
            items = result.get("items") or []
            by_uuid = {item["uuid"]: item for item in items}

        assert sandbox.heading_id in by_uuid, result
        assert by_uuid[sandbox.heading_id]["title"] == sandbox.heading_title, by_uuid
        # Other suite files may also file to-dos under the shared sandbox
        # heading (full-suite order fragility observed in hq-gbl.13's run:
        # hardcoded ==3 saw 4). Compare against things.py's own live count
        # of open to-dos under the heading - the todoCount CONTRACT
        # (open to-dos directly under the heading) - and additionally
        # require >= 3 so the two we just added are provably included.
        import things as _things

        expected = len(
            _things.todos(heading=sandbox.heading_id, status="incomplete") or []
        )
        assert by_uuid[sandbox.heading_id]["todoCount"] == expected, (
            by_uuid[sandbox.heading_id],
            expected,
        )
        assert by_uuid[sandbox.heading_id]["todoCount"] >= 3, by_uuid[sandbox.heading_id]

    def test_empty_project_zero_headings(self, mcp, sandbox):
        project_id, _, _ = _new_project(mcp, sandbox)
        result = mcp.call_sync(
            "get_project_headings", project_id=project_id, mode="standard"
        )
        assert result.get("items") == [], result
        assert result.get("count") == 0, result
        assert result.get("mode") == "standard", result

    def test_area_id_rejected(self, mcp, sandbox):
        result = mcp.call_sync("get_project_headings", project_id=sandbox.area_id)
        assert_read_error(result, "invalid_type")

    def test_todo_id_rejected(self, mcp, sandbox):
        # The sandbox seed to-do is tracked via sandbox.track() during
        # sandbox setup - grab any tracked to-do id.
        assert sandbox.tracked_todo_ids, "sandbox must have at least one to-do"
        todo_id = sandbox.tracked_todo_ids[0]
        result = mcp.call_sync("get_project_headings", project_id=todo_id)
        assert_read_error(result, "invalid_type")

    def test_heading_id_rejected(self, mcp, sandbox):
        assert sandbox.heading_id, "sandbox project must have a seeded heading"
        result = mcp.call_sync("get_project_headings", project_id=sandbox.heading_id)
        assert_read_error(result, "invalid_type")

    def test_unknown_id_rejected(self, mcp, sandbox):
        result = mcp.call_sync(
            "get_project_headings", project_id="bogus-project-id-does-not-exist"
        )
        assert_read_error(result, "not_found")

    @pytest.mark.parametrize("mode", ["auto", "summary", "minimal", "standard", "detailed", "raw"])
    def test_every_mode_value(self, mcp, sandbox, mode):
        result = mcp.call_sync(
            "get_project_headings", project_id=sandbox.project_id, mode=mode
        )
        assert "items" in result, result
        assert result.get("mode") != "auto", result
        if mode != "auto":
            assert result.get("requested_mode") == mode, result

    def test_invalid_mode_rejected(self, mcp, sandbox):
        result = mcp.call_sync(
            "get_project_headings", project_id=sandbox.project_id, mode="bogus-mode"
        )
        assert_read_error(result, "invalid_mode")


# ---------------------------------------------------------------------------
# 4. add_area / update_area / get_areas / get_projects
# ---------------------------------------------------------------------------


class TestAddArea:
    def test_title_special_chars(self, mcp, sandbox):
        import things

        title = sandbox_title('area "quoted", comma \U0001F600 ' + ts())
        result = mcp.call_sync("add_area", title=title)
        assert result.get("success") is True, result
        area_id = result.get("area_id")
        sandbox.track_area(area_id)

        def _fetch():
            return things.get(area_id)

        deadline = time.monotonic() + 20
        record = _fetch()
        while record is None and time.monotonic() < deadline:
            time.sleep(0.5)
            record = _fetch()
        assert record is not None and record.get("title") == title, record

    def test_tags_known(self, mcp, sandbox):
        result = mcp.call_sync("add_area", title=sandbox_title("area tagged " + ts()), tags=sandbox.tag_name)
        assert result.get("success") is True, result
        area_id = result.get("area_id")
        sandbox.track_area(area_id)

        import things

        def _fetch():
            return things.get(area_id)

        deadline = time.monotonic() + 20
        record = _fetch()
        while (record is None or not record.get("tags")) and time.monotonic() < deadline:
            time.sleep(0.5)
            record = _fetch()
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], record

    def test_tags_unknown_silently_filtered(self, mcp, sandbox):
        unknown_tag = f"hq-gbl-reg-nonexistent-area-tag-{ts()}"
        result = mcp.call_sync(
            "add_area", title=sandbox_title("area unknown tag " + ts()), tags=unknown_tag
        )
        assert result.get("success") is True, result
        area_id = result.get("area_id")
        sandbox.track_area(area_id)

        import things

        def _fetch():
            return things.get(area_id)

        deadline = time.monotonic() + 10
        record = _fetch()
        while record is None and time.monotonic() < deadline:
            time.sleep(0.5)
            record = _fetch()
        assert record is not None
        assert (record.get("tags") or []) == [], record


class TestUpdateArea:
    def _new_area(self, mcp, sandbox, **kwargs):
        title = sandbox_title("area upd " + ts())
        result = mcp.call_sync("add_area", title=title, **kwargs)
        assert result.get("success") is True, result
        area_id = result.get("area_id")
        sandbox.track_area(area_id)
        return area_id, title

    def test_title_update(self, mcp, sandbox):
        area_id, _ = self._new_area(mcp, sandbox)
        new_title = sandbox_title("area renamed " + ts())
        result = mcp.call_sync("update_area", id=area_id, title=new_title)
        assert result.get("success") is True, result

        import things

        def _fetch():
            return things.get(area_id)

        deadline = time.monotonic() + 20
        record = _fetch()
        while (record is None or record.get("title") != new_title) and time.monotonic() < deadline:
            time.sleep(0.5)
            record = _fetch()
        assert record is not None and record.get("title") == new_title, record

    def test_tags_set_and_clear(self, mcp, sandbox):
        area_id, _ = self._new_area(mcp, sandbox)
        result = mcp.call_sync("update_area", id=area_id, tags=sandbox.tag_name)
        assert result.get("success") is True, result

        import things

        def _fetch():
            return things.get(area_id)

        deadline = time.monotonic() + 20
        record = _fetch()
        while (record is None or not record.get("tags")) and time.monotonic() < deadline:
            time.sleep(0.5)
            record = _fetch()
        assert record is not None and (record.get("tags") or []) == [sandbox.tag_name], record

        clear_result = mcp.call_sync("update_area", id=area_id, tags="")
        assert clear_result.get("success") is True, clear_result

        record = _fetch()
        deadline = time.monotonic() + 20
        while (record is None or record.get("tags")) and time.monotonic() < deadline:
            time.sleep(0.5)
            record = _fetch()
        assert record is not None and (record.get("tags") or []) == [], record

    def test_no_fields_provided(self, mcp, sandbox):
        area_id, _ = self._new_area(mcp, sandbox)
        result = mcp.call_sync("update_area", id=area_id)
        assert_write_error(result, "NO_FIELDS_PROVIDED")

    def test_unknown_id_not_found(self, mcp, sandbox):
        result = mcp.call_sync(
            "update_area", id="bogus-area-id-does-not-exist", title="new title"
        )
        assert_write_error(result, "NOT_FOUND")

    def test_title_empty_rejected(self, mcp, sandbox):
        area_id, original_title = self._new_area(mcp, sandbox)
        result = mcp.call_sync("update_area", id=area_id, title="")
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "title", result

        import things

        record = things.get(area_id)
        assert record is not None and record.get("title") == original_title, record


class TestGetAreas:
    def test_sandbox_area_visible_with_tags_every_mode(self, mcp, sandbox):
        # Ensure the sandbox area carries a tag so tags-visibility is
        # actually exercised (not merely an empty list matching an empty
        # list). Uses a dedicated tracked area rather than mutating the
        # shared sandbox area.
        area_result = mcp.call_sync(
            "add_area", title=sandbox_title("area getareas " + ts()), tags=sandbox.tag_name
        )
        assert area_result.get("success") is True, area_result
        area_id = area_result.get("area_id")
        sandbox.track_area(area_id)

        import things

        deadline = time.monotonic() + 20
        record = things.get(area_id)
        while (record is None or not record.get("tags")) and time.monotonic() < deadline:
            time.sleep(0.5)
            record = things.get(area_id)
        assert record is not None and record.get("tags"), record

        # 'summary' mode returns only a small preview (not the full list -
        # CLAUDE.md's "Structured Output" section), so a specific item is
        # not guaranteed to be present there; only minimal/standard/
        # detailed return the full list and are checked for presence here.
        for mode in ("minimal", "standard", "detailed"):
            result = mcp.call_sync("get_areas", mode=mode)
            items = result.get("items") or []
            by_uuid = {item["uuid"]: item for item in items}
            assert area_id in by_uuid, f"mode={mode}: area not found in get_areas"
            assert by_uuid[area_id].get("tags") == [sandbox.tag_name], (mode, by_uuid[area_id])

    def test_include_items_nests_sandbox_projects(self, mcp, sandbox):
        result = mcp.call_sync("get_areas", include_items=True, mode="minimal")
        items = result.get("items") or []
        by_uuid = {item["uuid"]: item for item in items}
        assert sandbox.area_id in by_uuid, "sandbox area not found in get_areas(include_items=True)"

        nested_projects = by_uuid[sandbox.area_id].get("projects") or []
        nested_project_ids = {p.get("uuid") for p in nested_projects}
        assert sandbox.project_id in nested_project_ids, (
            f"expected sandbox project {sandbox.project_id!r} nested under area, "
            f"got project ids: {nested_project_ids}"
        )


class TestGetProjects:
    def test_sandbox_projects_present_every_mode_with_area(self, mcp, sandbox):
        # 'summary' mode returns only a small preview (not the full list -
        # CLAUDE.md's "Structured Output" section), so a specific item is
        # not guaranteed to be present there. 'detailed' can also be
        # truncated on this live DB's real project count (>context budget
        # -> _handle_oversized_response), observed live, so only
        # minimal/standard (whose smaller per-item size keeps this
        # environment's full project set under the size budget) are
        # checked for presence here.
        for mode in ("minimal", "standard"):
            result = mcp.call_sync("get_projects", mode=mode)
            items = result.get("items") or []
            by_uuid = {item["uuid"]: item for item in items}
            assert sandbox.project_id in by_uuid, f"mode={mode}: sandbox project not found"
            assert by_uuid[sandbox.project_id].get("area") == sandbox.area_id, (
                mode,
                by_uuid[sandbox.project_id],
            )

    def test_get_projects_summary_active_counts_incomplete(self, mcp, sandbox):
        """hq-wsa.1: _summarize_projects previously counted status=='open'
        for 'active', but things.py/convert_project emit status=='incomplete'
        for open projects - so 'active' was always 0 on a live DB regardless
        of how many open projects existed. The sandbox project (freshly
        created, never completed/canceled) is guaranteed incomplete, so
        'active' must be at least 1 - the robust live-DB assertion, since
        the real database's total open-project count isn't deterministic
        across runs/environments."""
        sc = mcp.call_sync("get_projects", mode="summary")
        assert sc["active"] >= 1, sc
        assert sc["active"] == sc.get("status_breakdown", {}).get("incomplete", 0)
        assert sc["completed"] == sc.get("status_breakdown", {}).get("completed", 0)
        assert sc["canceled"] == sc.get("status_breakdown", {}).get("canceled", 0)

    def test_include_items_nests_todos_scoped_read(self, mcp, sandbox):
        """get_projects(include_items=true) is documented as
        context-dangerous on large DBs - call it but only with a scoped
        read (mode='minimal') and verify only that the sandbox project's
        nested todos are present; never assert against the full DB."""
        result = mcp.call_sync("get_projects", include_items=True, mode="minimal")
        items = result.get("items") or []
        by_uuid = {item["uuid"]: item for item in items}
        assert sandbox.project_id in by_uuid, "sandbox project not found in get_projects(include_items=True)"

        nested_todos = by_uuid[sandbox.project_id].get("todos") or []
        nested_todo_ids = {t.get("uuid") for t in nested_todos}
        assert set(sandbox.tracked_todo_ids) & nested_todo_ids, (
            "expected at least one tracked sandbox to-do nested under the "
            f"sandbox project; nested ids: {nested_todo_ids}"
        )
