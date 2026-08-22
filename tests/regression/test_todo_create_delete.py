"""hq-gbl.7: Regression (live) for add_todo + delete_todo + get_todo_by_id
across the full input space, driven through the real MCP tool boundary.

Every test creates its own tracked to-do(s) via mcp.call_sync('add_todo',
...) with titles prefixed via sandbox_title(...); every returned id is
tracked via sandbox.track() (the response key is 'todo_id' - confirmed
against scheduling/todo_operations.py's add_todo return shape and the
existing seed.py/test_harness_smoke.py usage). list_id=sandbox.project_id
is used by default so the sandbox's own per-project child sweep is a
second safety net beyond explicit tracking; anything created in the
area/inbox is explicitly tracked since it lives outside that sweep.

Error-code notes (see CLAUDE.md's write-tool error contract):
  - add_todo's list_id/list_title resolution errors are NOT literally
    named in CLAUDE.md (it says "structured error" generically) - the
    actual codes, confirmed by reading scheduling/todo_operations.py, are
    NOT_FOUND (unknown list_id/list_title) and AMBIGUOUS_TARGET (list_title
    matching >1 project/area). Asserted here as observed fact and listed
    under Discovered (CLAUDE.md could be more specific, not a bug).
  - "heading without list" -> VALIDATION_ERROR (not a bespoke code).
  - Unknown tag under the active tag_creation_policy: this environment's
    default policy is FAIL_ON_UNKNOWN (ai_can_create_tags=False), which
    add_todo surfaces as TAG_VALIDATION_FAILED - NOT the filtered/silent
    behavior CLAUDE.md's tag section describes for filter_silent/
    filter_warn. The test reads live_server.config.tag_creation_policy and
    asserts the behavior that policy actually implies, rather than assuming
    one policy.
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


# ---------------------------------------------------------------------------
# 1. add_todo
# ---------------------------------------------------------------------------


class TestAddTodoTitles:
    def test_title_with_quotes_backslash_commas_emoji(self, mcp, sandbox):
        title = sandbox_title('title "quoted", back\\slash, comma \U0001F600 ' + ts())
        result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("title") == title)
        assert record is not None and record.get("title") == title, record

    def test_title_2000_chars(self, mcp, sandbox):
        prefix = sandbox_title("long ")
        # Pad to exactly 2000 chars total.
        title = prefix + ("x" * (2000 - len(prefix)))
        assert len(title) == 2000
        result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("title") == title)
        assert record is not None and record.get("title") == title
        assert len(record.get("title")) == 2000


class TestAddTodoNotes:
    def test_multiline_notes_preserved_exactly(self, mcp, sandbox):
        notes = 'Line one "quoted", comma\n\nLine two \\ backslash\n\nLine three \U0001F600'
        title = sandbox_title("multiline notes")
        result = mcp.call_sync(
            "add_todo", title=title, notes=notes, list_id=sandbox.project_id
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("notes") == notes)
        assert record is not None and record.get("notes") == notes, record.get("notes") if record else None


class TestAddTodoTags:
    def test_tags_policy_behavior(self, mcp, sandbox, live_server):
        """Adds a known sandbox tag plus an unknown tag and asserts the
        outcome implied by the ACTIVE tag_creation_policy, rather than
        assuming filter_silent/filter_warn - this environment's default is
        FAIL_ON_UNKNOWN (see module docstring)."""
        from things_mcp.config import TagCreationPolicy

        policy = live_server.config.tag_creation_policy
        unknown_tag = f"hq-gbl-reg-nonexistent-tag-{ts()}"
        title = sandbox_title("tags policy")
        result = mcp.call_sync(
            "add_todo",
            title=title,
            tags=f"{sandbox.tag_name},{unknown_tag}",
            list_id=sandbox.project_id,
        )

        if policy == TagCreationPolicy.FAIL_ON_UNKNOWN:
            assert_write_error(result, "TAG_VALIDATION_FAILED")
            assert result.get("message")
            return

        # ALLOW_ALL / FILTER_SILENT / FILTER_WARN: operation proceeds.
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("title") == title)
        assert record is not None
        applied_tags = record.get("tags") or []
        if policy == TagCreationPolicy.ALLOW_ALL:
            assert sandbox.tag_name in applied_tags
            assert unknown_tag in applied_tags
        else:
            # FILTER_SILENT / FILTER_WARN: only the known sandbox tag lands.
            assert applied_tags == [sandbox.tag_name], applied_tags
            if policy == TagCreationPolicy.FILTER_WARN:
                assert result.get("tag_warnings") or "tag_info" in result, result


class TestAddTodoWhen:
    @pytest.mark.parametrize(
        "keyword", ["today", "tomorrow", "yesterday", "someday", "anytime", "evening", "tonight"]
    )
    def test_when_keyword(self, mcp, sandbox, keyword):
        title = sandbox_title(f"when {keyword}")
        result = mcp.call_sync(
            "add_todo", title=title, when=keyword, list_id=sandbox.project_id
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("title") == title)
        assert record is not None, f"{keyword}: todo never read back"

    def test_when_iso_date(self, mcp, sandbox):
        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=9)).strftime("%Y-%m-%d")
        title = sandbox_title("when iso date")
        result = mcp.call_sync(
            "add_todo", title=title, when=when_date, list_id=sandbox.project_id
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(
            todo_id,
            lambda r: r is not None and r.get("start_date") == when_date,
        )
        assert record is not None and record.get("start_date") == when_date, record

    def test_when_iso_date_with_time_sets_reminder(self, mcp, sandbox):
        from datetime import date, timedelta

        when_date = (date.today() + timedelta(days=9)).strftime("%Y-%m-%d")
        title = sandbox_title("when iso date+time")
        result = mcp.call_sync(
            "add_todo",
            title=title,
            when=f"{when_date}@14:30",
            list_id=sandbox.project_id,
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(
            todo_id,
            lambda r: r is not None and r.get("reminder_time") is not None,
        )
        assert record is not None
        assert record.get("reminder_time") == "14:30", record
        assert record.get("start_date") == when_date, record

    def test_when_invalid(self, mcp, sandbox):
        title = sandbox_title("when invalid")
        result = mcp.call_sync(
            "add_todo", title=title, when="not-a-date", list_id=sandbox.project_id
        )
        assert_write_error(result, "INVALID_WHEN")

    def test_when_whitespace(self, mcp, sandbox):
        title = sandbox_title("when whitespace")
        result = mcp.call_sync(
            "add_todo", title=title, when="   ", list_id=sandbox.project_id
        )
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "when"


class TestAddTodoDeadline:
    def test_deadline_valid(self, mcp, sandbox):
        from datetime import date, timedelta

        deadline = (date.today() + timedelta(days=14)).strftime("%Y-%m-%d")
        title = sandbox_title("deadline valid")
        result = mcp.call_sync(
            "add_todo", title=title, deadline=deadline, list_id=sandbox.project_id
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(
            todo_id, lambda r: r is not None and r.get("deadline") == deadline
        )
        assert record is not None and record.get("deadline") == deadline, record

    def test_deadline_relative_rejected(self, mcp, sandbox):
        title = sandbox_title("deadline relative")
        result = mcp.call_sync(
            "add_todo", title=title, deadline="today", list_id=sandbox.project_id
        )
        assert_write_error(result, "INVALID_DEADLINE")

    def test_deadline_invalid(self, mcp, sandbox):
        title = sandbox_title("deadline invalid")
        result = mcp.call_sync(
            "add_todo", title=title, deadline="not-a-date", list_id=sandbox.project_id
        )
        assert_write_error(result, "INVALID_DEADLINE")


class TestAddTodoListId:
    def test_list_id_project(self, mcp, sandbox):
        title = sandbox_title("list_id project")
        result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("project") == sandbox.project_id)
        assert record is not None and record.get("project") == sandbox.project_id, record

    def test_list_id_area(self, mcp, sandbox):
        title = sandbox_title("list_id area")
        result = mcp.call_sync("add_todo", title=title, list_id=sandbox.area_id)
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("area") == sandbox.area_id)
        assert record is not None and record.get("area") == sandbox.area_id, record

    def test_list_id_unknown(self, mcp, sandbox):
        title = sandbox_title("list_id unknown")
        result = mcp.call_sync(
            "add_todo", title=title, list_id="bogus-list-id-does-not-exist", list_title=None
        )
        # Observed: the actual code is NOT_FOUND (see module docstring).
        assert_write_error(result, "NOT_FOUND")


class TestAddTodoListTitle:
    def test_list_title_unique(self, mcp, sandbox):
        title = sandbox_title("list_title unique")
        result = mcp.call_sync("add_todo", title=title, list_title=sandbox.project_title)
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("project") == sandbox.project_id)
        assert record is not None and record.get("project") == sandbox.project_id, record

    def test_list_title_unknown(self, mcp, sandbox):
        title = sandbox_title("list_title unknown")
        result = mcp.call_sync(
            "add_todo", title=title, list_title=f"hq-gbl-reg-nonexistent-{ts()}"
        )
        assert_write_error(result, "NOT_FOUND")

    def test_list_title_ambiguous(self, mcp, sandbox):
        """Creates a temporary second project with the exact same title as
        project B to force ambiguity, tracked via sandbox.tracked_project_ids
        directly (Sandbox.track() only appends to tracked_todo_ids - see
        conftest.py's Sandbox class - so a project id must be appended to
        tracked_project_ids explicitly for the session teardown's
        per-project child sweep / project-delete loop to find it)."""
        dup_result = mcp.call_sync(
            "add_project", title=sandbox.project_b_title, area_id=sandbox.area_id
        )
        assert dup_result.get("success") is True, dup_result
        dup_project_id = dup_result.get("project_id")
        assert dup_project_id
        sandbox.tracked_project_ids.append(dup_project_id)

        title = sandbox_title("list_title ambiguous")
        result = mcp.call_sync("add_todo", title=title, list_title=sandbox.project_b_title)
        assert_write_error(result, "AMBIGUOUS_TARGET")
        ids = result.get("ids")
        assert isinstance(ids, list) and len(ids) >= 2, result

        # Trash the temporary duplicate project in this same test, per the
        # brief - session teardown is still a second safety net.
        delete_result = mcp.call_sync("delete_todo", todo_id=dup_project_id)
        assert delete_result.get("success") is True, delete_result


class TestAddTodoHeading:
    def test_heading_existing(self, mcp, sandbox):
        title = sandbox_title("heading existing")
        result = mcp.call_sync(
            "add_todo",
            title=title,
            list_id=sandbox.project_id,
            heading=sandbox.heading_title,
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(
            todo_id, lambda r: r is not None and r.get("heading") == sandbox.heading_id
        )
        assert record is not None and record.get("heading") == sandbox.heading_id, record

    def test_heading_missing_warns_and_still_files_in_project(self, mcp, sandbox):
        bogus_heading = f"hq-gbl-reg-nonexistent-heading-{ts()}"
        title = sandbox_title("heading missing")
        result = mcp.call_sync(
            "add_todo",
            title=title,
            list_id=sandbox.project_id,
            heading=bogus_heading,
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)
        assert result.get("warnings"), result

        record = read_back(
            todo_id, lambda r: r is not None and r.get("project") == sandbox.project_id
        )
        assert record is not None
        assert record.get("project") == sandbox.project_id, record
        assert record.get("heading") != bogus_heading

    def test_heading_without_list_rejected_and_nothing_created(self, mcp, sandbox):
        import things

        title = sandbox_title("heading without list")
        before = {
            t["uuid"]
            for t in things.tasks(
                project=sandbox.project_id, type="to-do", status=None
            )
            or []
        }

        result = mcp.call_sync("add_todo", title=title, heading="Some Heading")
        assert_write_error(result, "VALIDATION_ERROR")
        assert result.get("field") == "heading"

        # Give any (unexpected) async write a moment before re-checking.
        time.sleep(1)
        after = {
            t["uuid"]
            for t in things.tasks(
                project=sandbox.project_id, type="to-do", status=None
            )
            or []
        }
        assert after == before, "heading-without-list must not create a to-do anywhere"

        # Also confirm nothing with this exact title exists anywhere.
        matches = [
            t
            for t in things.tasks(type="to-do", status=None, trashed=None) or []
            if t.get("title") == title
        ]
        assert matches == [], matches


class TestAddTodoChecklist:
    @pytest.mark.parametrize("count", [1, 3, 100])
    def test_checklist_items_count(self, mcp, sandbox, count):
        items = [f"item {i}" for i in range(count)]
        title = sandbox_title(f"checklist {count}")
        result = mcp.call_sync(
            "add_todo", title=title, checklist_items=items, list_id=sandbox.project_id
        )
        assert result.get("success") is True, result
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(
            todo_id,
            lambda r: r is not None and r.get("title") == title,
        )
        assert record is not None, f"checklist({count}) todo never read back"

        import things

        checklist = things.checklist_items(todo_id) or []
        assert len(checklist) == count, (
            f"expected {count} checklist items, got {len(checklist)}"
        )

    def test_checklist_items_101_rejected_and_nothing_created(self, mcp, sandbox):
        """hq-exe: the documented 100-item checklist cap is enforced with
        TOO_MANY_CHECKLIST_ITEMS before any Things URL-scheme write."""
        import things

        items = [f"item {i}" for i in range(101)]
        title = sandbox_title("checklist 101")
        before = {
            t["uuid"]
            for t in things.tasks(
                project=sandbox.project_id, type="to-do", status=None
            )
            or []
        }

        result = mcp.call_sync(
            "add_todo", title=title, checklist_items=items, list_id=sandbox.project_id
        )
        assert result.get("success") is False, result
        assert result.get("error") == "TOO_MANY_CHECKLIST_ITEMS", result
        assert result.get("field") == "checklist_items", result
        if result.get("success") is True and result.get("todo_id"):
            sandbox.track(result["todo_id"])

        time.sleep(1)
        after = {
            t["uuid"]
            for t in things.tasks(
                project=sandbox.project_id, type="to-do", status=None
            )
            or []
        }
        assert after == before, "101 checklist items must not create a to-do"


class TestAddTodoTargetCompleted:
    def test_list_id_completed_project_rejected_and_nothing_created(self, mcp, sandbox):
        import things

        title = sandbox_title("target completed")
        before = {
            t["uuid"]
            for t in things.tasks(
                project=sandbox.done_project_id, type="to-do", status=None
            )
            or []
        }

        result = mcp.call_sync(
            "add_todo", title=title, list_id=sandbox.done_project_id
        )
        assert_write_error(result, "TARGET_COMPLETED")

        time.sleep(1)
        after = {
            t["uuid"]
            for t in things.tasks(
                project=sandbox.done_project_id, type="to-do", status=None
            )
            or []
        }
        assert after == before, "TARGET_COMPLETED must not create a to-do"

        done_record = things.get(sandbox.done_project_id)
        assert done_record is not None
        assert done_record.get("status") == "completed", done_record


class TestAddTodoSameTitleTwice:
    def test_same_title_twice_within_1s_resolve_distinct_ids(self, mcp, sandbox):
        title = sandbox_title("same title twice " + ts())

        result_a = mcp.call_sync(
            "add_todo", title=title, checklist_items=["only item"], list_id=sandbox.project_id
        )
        assert result_a.get("success") is True, result_a
        todo_id_a = result_a.get("todo_id")
        assert todo_id_a
        sandbox.track(todo_id_a)

        result_b = mcp.call_sync(
            "add_todo", title=title, checklist_items=["only item"], list_id=sandbox.project_id
        )
        assert result_b.get("success") is True, result_b
        todo_id_b = result_b.get("todo_id")
        assert todo_id_b
        sandbox.track(todo_id_b)

        assert todo_id_a != todo_id_b, "same-title creates resolved to the same id"

        record_a = read_back(todo_id_a, lambda r: r is not None and r.get("title") == title)
        record_b = read_back(todo_id_b, lambda r: r is not None and r.get("title") == title)
        assert record_a is not None and record_a.get("title") == title
        assert record_b is not None and record_b.get("title") == title


# ---------------------------------------------------------------------------
# 2. delete_todo
# ---------------------------------------------------------------------------


class TestDeleteTodo:
    def test_delete_todo_trashes_it(self, mcp, sandbox):
        title = sandbox_title("delete todo")
        add_result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        delete_result = mcp.call_sync("delete_todo", todo_id=todo_id)
        assert delete_result.get("success") is True, delete_result

        get_result = mcp.call_sync("get_todo_by_id", todo_id=todo_id)
        assert "item" in get_result, get_result
        assert get_result["item"].get("trashed") is True, get_result

    def test_delete_project_trashes_it(self, mcp, sandbox):
        proj_title = sandbox_title("delete project")
        add_result = mcp.call_sync(
            "add_project", title=proj_title, area_id=sandbox.area_id
        )
        assert add_result.get("success") is True, add_result
        project_id = add_result.get("project_id")
        assert project_id
        sandbox.tracked_project_ids.append(project_id)

        delete_result = mcp.call_sync("delete_todo", todo_id=project_id)
        assert delete_result.get("success") is True, delete_result

        get_result = mcp.call_sync("get_todo_by_id", todo_id=project_id)
        assert "item" in get_result, get_result
        assert get_result["item"].get("type") == "project"
        assert get_result["item"].get("trashed") is True, get_result

    def test_delete_heading_not_deletable(self, mcp, sandbox):
        result = mcp.call_sync("delete_todo", todo_id=sandbox.heading_id)
        assert_read_error(result, "not_deletable")

    def test_delete_area_not_deletable(self, mcp, sandbox):
        result = mcp.call_sync("delete_todo", todo_id=sandbox.area_id)
        assert_read_error(result, "not_deletable")

    def test_delete_tag_not_deletable(self, mcp, sandbox):
        result = mcp.call_sync("delete_todo", todo_id=sandbox.tag_id)
        assert_read_error(result, "not_deletable")

    def test_delete_unknown_id_not_found(self, mcp, sandbox):
        result = mcp.call_sync("delete_todo", todo_id="bogus-id-does-not-exist")
        assert_read_error(result, "not_found")

    def test_delete_already_trashed_todo(self, mcp, sandbox):
        """Documents the OBSERVED behavior of deleting an already-trashed
        to-do: things.get() still resolves it (type 'to-do', trashed=True),
        so delete_todo's type-resolution treats it exactly like any other
        to-do and retries the AppleScript `delete (to do id ...)` / trash
        move - Things either accepts the no-op delete of an already-trashed
        item, or the underlying AppleScript errors (in which case the
        move-to-Trash fallback still succeeds since the item is already
        there). Either way this test asserts what was actually observed,
        not a guess."""
        title = sandbox_title("delete already trashed")
        add_result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        first_delete = mcp.call_sync("delete_todo", todo_id=todo_id)
        assert first_delete.get("success") is True, first_delete

        second_delete = mcp.call_sync("delete_todo", todo_id=todo_id)
        # Observed: delete_todo on an already-trashed to-do still reports
        # success (idempotent from the caller's point of view) rather than
        # a not_found/already-trashed error.
        assert second_delete.get("success") is True, second_delete

        get_result = mcp.call_sync("get_todo_by_id", todo_id=todo_id)
        assert "item" in get_result, get_result
        assert get_result["item"].get("trashed") is True, get_result

    def test_delete_project_cascades_trashed_to_child_todo(self, mcp, sandbox):
        """hq-wsa.7: a to-do filed under a project reports no `trashed` key
        of its own when only its parent project is trashed - things.py
        marks the trashed container, not each descendant. get_todo_by_id
        now resolves this transitively: the child reports both
        `trashed: True` and `trashedViaParent: True`, while the project
        itself (directly trashed) reports `trashed: True` with no
        `trashedViaParent` key."""
        proj_title = sandbox_title("cascade delete project")
        add_project_result = mcp.call_sync(
            "add_project", title=proj_title, area_id=sandbox.area_id
        )
        assert add_project_result.get("success") is True, add_project_result
        project_id = add_project_result.get("project_id")
        assert project_id
        sandbox.tracked_project_ids.append(project_id)

        child_title = sandbox_title("cascade delete child todo")
        add_todo_result = mcp.call_sync(
            "add_todo", title=child_title, list_id=project_id
        )
        assert add_todo_result.get("success") is True, add_todo_result
        child_id = add_todo_result.get("todo_id")
        assert child_id
        sandbox.track(child_id)

        record = read_back(
            child_id, lambda r: r is not None and r.get("title") == child_title
        )
        assert record is not None

        delete_result = mcp.call_sync("delete_todo", todo_id=project_id)
        assert delete_result.get("success") is True, delete_result

        # Poll: delete_todo's Things-side trash move can lag a subsequent
        # things.py-backed read (same URL-scheme/AppleScript async lag
        # documented in CLAUDE.md), so retry get_todo_by_id on the child
        # until it reports the transitive trashed state, rather than
        # asserting on the first read.
        deadline = time.monotonic() + 20.0
        child_result = None
        while time.monotonic() < deadline:
            child_result = mcp.call_sync("get_todo_by_id", todo_id=child_id)
            if child_result.get("item", {}).get("trashedViaParent") is True:
                break
            time.sleep(0.25)

        assert "item" in child_result, child_result
        assert child_result["item"].get("trashed") is True, child_result
        assert child_result["item"].get("trashedViaParent") is True, child_result

        project_result = mcp.call_sync("get_todo_by_id", todo_id=project_id)
        assert "item" in project_result, project_result
        assert project_result["item"].get("trashed") is True, project_result
        assert "trashedViaParent" not in project_result["item"], project_result


# ---------------------------------------------------------------------------
# 3. get_todo_by_id
# ---------------------------------------------------------------------------


class TestGetTodoById:
    def test_todo_type(self, mcp, sandbox):
        title = sandbox_title("get_todo_by_id todo")
        add_result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert add_result.get("success") is True, add_result
        todo_id = add_result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        record = read_back(todo_id, lambda r: r is not None and r.get("title") == title)
        assert record is not None

        result = mcp.call_sync("get_todo_by_id", todo_id=todo_id)
        assert "item" in result, result
        assert result["item"]["type"] == "to-do"
        assert result["item"]["uuid"] == todo_id

    def test_project_type(self, mcp, sandbox):
        result = mcp.call_sync("get_todo_by_id", todo_id=sandbox.project_id)
        assert "item" in result, result
        assert result["item"]["type"] == "project"
        assert result["item"]["uuid"] == sandbox.project_id

    def test_heading_type(self, mcp, sandbox):
        result = mcp.call_sync("get_todo_by_id", todo_id=sandbox.heading_id)
        assert "item" in result, result
        assert result["item"]["type"] == "heading"
        assert result["item"]["uuid"] == sandbox.heading_id

    def test_area_type(self, mcp, sandbox):
        result = mcp.call_sync("get_todo_by_id", todo_id=sandbox.area_id)
        assert "item" in result, result
        assert result["item"]["type"] == "area"
        assert result["item"]["uuid"] == sandbox.area_id

    def test_tag_id_invalid_type(self, mcp, sandbox):
        result = mcp.call_sync("get_todo_by_id", todo_id=sandbox.tag_id)
        assert_read_error(result, "invalid_type")

    def test_unknown_id_raises_tool_error(self, mcp, sandbox):
        result = mcp.call_sync("get_todo_by_id", todo_id="bogus-id-does-not-exist-at-all")
        assert "tool_error" in result, result
        assert isinstance(result["tool_error"], str) and result["tool_error"], result
