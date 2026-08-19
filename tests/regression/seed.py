"""Deterministic seed set for the list/status/date-class regression oracle
(hq-gbl.6).

`SEED_CLASSES` defines one to-do per "class" of Things state (inbox,
today, evening, deadline windows, overdue, completed, canceled, trashed,
tagged, checklist, multiline-notes, under-heading, in-area, in-project-B,
activating window, ...). `create_seed_set()` creates every one of them
through the real MCP tool boundary (never AppleScript/things.py directly
for the creation step itself - only for read-back verification), tracks
every id on the sandbox (including ones created outside the sandbox
project - inbox, area, project B - so the sandbox's own child-sweep in
conftest.py, which only walks `tracked_project_ids`, still finds and
tears them down via `sandbox.track()`), and returns a `SeedSet` with the
per-class todo id, title, and any relevant dates.

This module intentionally does not import pytest - it is plain seeding
logic invoked from a fixture.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from regression.helpers import read_back, sandbox_title

# Multiline/notes torture string: quotes, commas, backslash, newline, emoji.
# Exercises the AppleScript string escaper (CLAUDE.md "Multi-line notes
# preserved" note) - must round-trip through add_todo's AppleScript path
# without corrupting the note or breaking the script.
MULTILINE_NOTES = 'Line one "quoted", with a comma\nLine two \\ backslash\nLine three \U0001F600 emoji'

CHECKLIST_ITEMS = ["Checklist item 1", "Checklist item 2", "Checklist item 3"]

# All class names, in creation order. Kept as a plain list (not just dict
# keys) so test_seed_oracle.py can assert every class was actually seeded.
CLASS_NAMES: List[str] = [
    "inbox",
    "today",
    "evening",
    "tomorrow",
    "plus5d",
    "plus40d",
    "someday",
    "anytime_in_project",
    "under_heading",
    "deadline_today",
    "deadline_plus3d",
    "deadline_plus20d",
    "deadline_plus60d",
    "overdue",
    "with_tag",
    "with_checklist",
    "with_multiline_notes",
    "completed",
    "canceled",
    "trashed",
    "activating_plus10d",
    "in_area",
    "in_project_b",
]


@dataclass
class SeedSet:
    """Resolved seed data: per-class todo id/title, plus the dates used so
    tests can compute expected windows without recomputing "today" (which
    could roll over across midnight during a long session)."""

    today: date
    ids: Dict[str, Optional[str]] = field(default_factory=dict)
    titles: Dict[str, str] = field(default_factory=dict)
    dates: Dict[str, Any] = field(default_factory=dict)
    notes: Dict[str, Optional[str]] = field(default_factory=dict)
    skipped: Dict[str, str] = field(default_factory=dict)
    overdue_set_via: Optional[str] = None  # 'add_todo' or 'update_todo'

    def uuid(self, class_name: str) -> Optional[str]:
        return self.ids.get(class_name)


def _iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def create_seed_set(mcp, sandbox) -> SeedSet:
    """Create one to-do per class in CLASS_NAMES via the MCP tool boundary,
    tracking every created id on `sandbox` (so the session teardown finds
    and cleans them up regardless of where they live), and return a
    populated SeedSet.

    `mcp` is the tests/regression `_MCPCallHelper` (mcp.call_sync(...)).
    `sandbox` is the session Sandbox from conftest.py.
    """
    today = date.today()
    seed = SeedSet(today=today)
    seed.dates["today"] = today
    seed.dates["tomorrow"] = today + timedelta(days=1)
    seed.dates["plus5d"] = today + timedelta(days=5)
    seed.dates["plus40d"] = today + timedelta(days=40)
    seed.dates["deadline_today"] = today
    seed.dates["deadline_plus3d"] = today + timedelta(days=3)
    seed.dates["deadline_plus20d"] = today + timedelta(days=20)
    seed.dates["deadline_plus60d"] = today + timedelta(days=60)
    seed.dates["overdue_deadline"] = today - timedelta(days=2)
    seed.dates["activating_when"] = today + timedelta(days=10)
    seed.dates["activating_deadline"] = today + timedelta(days=12)

    def _title(class_name: str) -> str:
        t = sandbox_title(f"seed {class_name}")
        seed.titles[class_name] = t
        return t

    def _create(class_name: str, **kwargs) -> Optional[str]:
        title = _title(class_name)
        result = mcp.call_sync("add_todo", title=title, **kwargs)
        assert result.get("success"), (
            f"seed class {class_name!r}: add_todo failed: {result}"
        )
        todo_id = result.get("todo_id")
        assert todo_id, f"seed class {class_name!r}: add_todo missing todo_id: {result}"
        sandbox.track(todo_id)
        seed.ids[class_name] = todo_id
        return todo_id

    # -- plain list-state classes -----------------------------------------
    _create("inbox")
    _create("today", when="today", list_id=sandbox.project_id)
    _create("evening", when="evening", list_id=sandbox.project_id)
    _create("tomorrow", when="tomorrow", list_id=sandbox.project_id)
    _create("plus5d", when=_iso(seed.dates["plus5d"]), list_id=sandbox.project_id)
    _create("plus40d", when=_iso(seed.dates["plus40d"]), list_id=sandbox.project_id)
    _create("someday", when="someday")
    _create("anytime_in_project", when="anytime", list_id=sandbox.project_id)

    # -- under-heading (URL scheme; heading must already exist) -----------
    if sandbox.heading_title:
        _create(
            "under_heading",
            list_id=sandbox.project_id,
            heading=sandbox.heading_title,
        )
        # Poll read-back to confirm the URL-scheme write landed under the
        # heading before any oracle test reads it.
        heading_id = seed.ids["under_heading"]
        record = read_back(
            heading_id,
            lambda r: r is not None and r.get("title") == seed.titles["under_heading"],
        )
        assert record is not None, (
            f"under_heading seed {heading_id} never read back via things.py"
        )
    else:
        seed.ids["under_heading"] = None
        seed.skipped["under_heading"] = "sandbox.heading_title is None (heading not confirmed)"

    # -- deadline classes ---------------------------------------------------
    _create("deadline_today", deadline=_iso(seed.dates["deadline_today"]), list_id=sandbox.project_id)
    _create("deadline_plus3d", deadline=_iso(seed.dates["deadline_plus3d"]), list_id=sandbox.project_id)
    _create("deadline_plus20d", deadline=_iso(seed.dates["deadline_plus20d"]), list_id=sandbox.project_id)
    _create("deadline_plus60d", deadline=_iso(seed.dates["deadline_plus60d"]), list_id=sandbox.project_id)

    # -- overdue: try add_todo(deadline=<-2d>) first; verify it actually
    #    landed with that deadline; fall back to update_todo if not.
    overdue_deadline_iso = _iso(seed.dates["overdue_deadline"])
    overdue_title = _title("overdue")
    add_result = mcp.call_sync(
        "add_todo", title=overdue_title, deadline=overdue_deadline_iso,
        list_id=sandbox.project_id,
    )
    if add_result.get("success") and add_result.get("todo_id"):
        overdue_id = add_result["todo_id"]
        sandbox.track(overdue_id)
        record = read_back(
            overdue_id,
            lambda r: r is not None and r.get("deadline") is not None,
        )
        if record is not None and record.get("deadline") == overdue_deadline_iso:
            seed.ids["overdue"] = overdue_id
            seed.overdue_set_via = "add_todo"
        else:
            # add_todo accepted the call but the past deadline didn't
            # stick (or came back different) - set it via update_todo
            # instead, on the same todo id.
            update_result = mcp.call_sync(
                "update_todo", id=overdue_id, deadline=overdue_deadline_iso
            )
            assert update_result.get("success"), (
                f"overdue seed: update_todo(deadline={overdue_deadline_iso!r}) "
                f"failed after add_todo landed without it: {update_result}"
            )
            record2 = read_back(
                overdue_id,
                lambda r: r is not None and r.get("deadline") == overdue_deadline_iso,
            )
            assert record2 is not None and record2.get("deadline") == overdue_deadline_iso, (
                f"overdue seed: deadline still not {overdue_deadline_iso!r} after "
                f"update_todo read-back: {record2}"
            )
            seed.ids["overdue"] = overdue_id
            seed.overdue_set_via = "update_todo"
    else:
        # add_todo rejected the past deadline outright - create without a
        # deadline, then set it via update_todo.
        create_result = mcp.call_sync(
            "add_todo", title=overdue_title, list_id=sandbox.project_id,
        )
        assert create_result.get("success"), (
            f"overdue seed: fallback add_todo (no deadline) failed: {create_result}"
        )
        overdue_id = create_result["todo_id"]
        sandbox.track(overdue_id)
        update_result = mcp.call_sync(
            "update_todo", id=overdue_id, deadline=overdue_deadline_iso
        )
        assert update_result.get("success"), (
            f"overdue seed: update_todo(deadline={overdue_deadline_iso!r}) failed: "
            f"{update_result}"
        )
        record = read_back(
            overdue_id,
            lambda r: r is not None and r.get("deadline") == overdue_deadline_iso,
        )
        assert record is not None and record.get("deadline") == overdue_deadline_iso, (
            f"overdue seed: deadline still not {overdue_deadline_iso!r} after "
            f"update_todo read-back: {record}"
        )
        seed.ids["overdue"] = overdue_id
        seed.overdue_set_via = "update_todo (add_todo rejected past deadline)"

    # -- tagged ---------------------------------------------------------
    _create("with_tag", tags=sandbox.tag_name, list_id=sandbox.project_id)

    # -- checklist (URL scheme; poll read-back for checklist presence) --
    checklist_id = _create("with_checklist", checklist_items=list(CHECKLIST_ITEMS), list_id=sandbox.project_id)
    record = read_back(
        checklist_id,
        lambda r: r is not None and r.get("title") == seed.titles["with_checklist"],
    )
    assert record is not None, (
        f"with_checklist seed {checklist_id} never read back via things.py"
    )

    # -- multiline / special-character notes -----------------------------
    notes_id = _create("with_multiline_notes", notes=MULTILINE_NOTES, list_id=sandbox.project_id)
    seed.notes["with_multiline_notes"] = MULTILINE_NOTES
    record = read_back(
        notes_id,
        lambda r: r is not None and r.get("notes") == MULTILINE_NOTES,
    )
    assert record is not None and record.get("notes") == MULTILINE_NOTES, (
        f"with_multiline_notes seed {notes_id}: notes did not round-trip: "
        f"{record.get('notes') if record else None!r}"
    )

    # -- status classes: create, then flip status via update_todo --------
    completed_id = _create("completed", list_id=sandbox.project_id)
    complete_result = mcp.call_sync("update_todo", id=completed_id, completed="true")
    assert complete_result.get("success"), (
        f"completed seed: update_todo(completed='true') failed: {complete_result}"
    )

    canceled_id = _create("canceled", list_id=sandbox.project_id)
    cancel_result = mcp.call_sync("update_todo", id=canceled_id, canceled="true")
    assert cancel_result.get("success"), (
        f"canceled seed: update_todo(canceled='true') failed: {cancel_result}"
    )

    trashed_id = _create("trashed", list_id=sandbox.project_id)
    delete_result = mcp.call_sync("delete_todo", todo_id=trashed_id)
    assert delete_result.get("success"), (
        f"trashed seed: delete_todo failed: {delete_result}"
    )

    # -- activating window: when=+10d AND deadline=+12d -------------------
    _create(
        "activating_plus10d",
        when=_iso(seed.dates["activating_when"]),
        deadline=_iso(seed.dates["activating_deadline"]),
        list_id=sandbox.project_id,
    )

    # -- location classes: area / project B --------------------------------
    _create("in_area", list_id=sandbox.area_id)
    _create("in_project_b", list_id=sandbox.project_b_id)

    return seed
