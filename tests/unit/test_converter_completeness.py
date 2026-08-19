"""Converter field-completeness tests (hq-f0w.10).

A single check against ToolsHelpers.convert_todo/convert_project/
convert_area (tools_helpers/helpers.py), driven by realistic things.py rows
(tests/fixtures/things_realistic.py):

The converted output key set for a realistic, "everything populated"
input covers an explicit EXPECTED_KEYS set per entity (documents the
full camelCase key vocabulary each converter can emit, post hq-f0w.4).
Any key the converter emits that isn't in EXPECTED_KEYS, or any expected
key it fails to emit, fails the test - this pins the contract so a
future edit that silently drops a field is caught immediately.

Ambiguity flagged (not resolved here): the bead brief for hq-f0w.10 asks for
"convert_tag" coverage alongside convert_todo/convert_project/convert_area,
but no such function exists on ToolsHelpers (or anywhere in
tools_helpers/helpers.py) - grep confirms only convert_to_boolean,
convert_iso_to_applescript_date, convert_applescript_todo, convert_todo,
convert_project, and convert_area are defined. Tag conversion is inlined
directly in read_operations.py's _get_tags_sync (title/shortcut/count/
todos), not routed through a ToolsHelpers.convert_tag. This test file
therefore covers convert_todo/convert_project/convert_area only; tag-field
completeness is out of scope pending clarification of where a convert_tag
would live (see "Discovered" note filed alongside this bead).

Note (hq-nxu.7): this file previously also contained a second check that
parsed response_optimizer.py's ResponseOptimizer.optimize_* methods via
`ast` and asserted every field they referenced was either produced by the
matching converter or listed in a DROPPED allowlist with a reason.
response_optimizer.py had zero callers anywhere in src/ or tests/ (dead
code left over from before convert_todo/convert_project/convert_area were
rewritten to the real things.py key set in hq-f0w.4) and was deleted in
hq-nxu.7, so that check and its DROPPED_TODO/DROPPED_PROJECT/DROPPED_AREA
allowlists were removed along with it. The EXPECTED_KEYS contracts below
(Check 1) are unaffected and remain the coverage mechanism for this file.
"""

import pytest

from things_mcp.tools_helpers.helpers import ToolsHelpers

from fixtures.things_realistic import (
    make_todo,
    make_project,
    make_area,
    ANYTIME_PROJECT,
)


# ---------------------------------------------------------------------------
# Fully-populated realistic rows: every optional key things.py can emit for
# that entity is present, so the converter's full output key set is exposed.
# ---------------------------------------------------------------------------

# completionDate/cancellationDate are mutually exclusive (derived from the
# same 'stop_date' field, disambiguated by 'status') - a single row can
# never carry both, so the full EXPECTED_TODO_KEYS/EXPECTED_PROJECT_KEYS
# contract is only fully exposed by the *union* of a completed row and a
# canceled row.
#
# NOTE: this is a documented SYNTHETIC SUPERSET row, not a copy of any one
# realistic canned fixture: real things.py rows never carry both
# 'heading'/'heading_title' AND 'project'/'project_title' together (a
# heading-child's project is only reachable via its heading - live: 0/40
# heading-children have a project key; tracked as hq-f0w.24). To still
# exercise every *independent* optional key convert_todo can emit in one
# place, this row is project-attached (not heading-attached) - i.e. it
# models a to-do that's a direct child of a project, which realistically
# does carry project/project_title without heading/heading_title.
def _fully_populated_todo(status: str, stop_date: str) -> dict:
    return make_todo(
        f"todo-full-{status}",
        "Fully populated to-do",
        status=status,
        notes="Some notes\n\nwith a blank line",
        tags=["work", "urgent"],
        project=ANYTIME_PROJECT["uuid"],
        project_title=ANYTIME_PROJECT["title"],
        checklist=True,
        start_date="2026-01-01",
        deadline="2026-02-01",
        stop_date=stop_date,
        reminder_time="09:00",
    )


FULLY_POPULATED_TODO = _fully_populated_todo("completed", "2026-01-15 10:00:00")
FULLY_POPULATED_TODO_CANCELED = _fully_populated_todo("canceled", "2026-01-20 11:00:00")

# Also exercise inherited_someday marker + a pre-fetched checklist item list,
# both of which convert_todo conditionally emits.
FULLY_POPULATED_TODO_WITH_EXTRAS = dict(FULLY_POPULATED_TODO)
FULLY_POPULATED_TODO_WITH_EXTRAS["inherited_someday"] = True
FULLY_POPULATED_TODO_WITH_EXTRAS["checklist"] = [
    {"title": "Item 1", "status": "incomplete"},
]


def _fully_populated_project(status: str, stop_date: str) -> dict:
    return make_project(
        f"project-full-{status}",
        "Fully populated project",
        status=status,
        notes="Project notes",
        area=ANYTIME_PROJECT["area"],
        area_title=ANYTIME_PROJECT["area_title"],
        start_date="2026-01-01",
        deadline="2026-03-01",
        stop_date=stop_date,
    )


FULLY_POPULATED_PROJECT = _fully_populated_project("completed", "2026-02-15 09:00:00")
FULLY_POPULATED_PROJECT_CANCELED = _fully_populated_project("canceled", "2026-02-20 09:00:00")

FULLY_POPULATED_AREA = make_area("area-full-1", "Fully populated area")


# ---------------------------------------------------------------------------
# Check 1: explicit EXPECTED_KEYS contract per converter.
# ---------------------------------------------------------------------------

EXPECTED_TODO_KEYS = {
    "uuid", "title", "type", "notes", "status", "tags", "start",
    "creationDate", "modificationDate", "completionDate", "cancellationDate",
    "dueDate", "startDate", "project", "projectTitle", "heading",
    "headingTitle", "hasChecklist", "index", "todayIndex",
}

EXPECTED_PROJECT_KEYS = {
    "uuid", "title", "type", "notes", "status", "tags", "area", "areaTitle",
    "creationDate", "modificationDate", "completionDate", "cancellationDate",
    "dueDate",
}

EXPECTED_AREA_KEYS = {"uuid", "title", "type", "tags"}


class TestConvertTodoKeyCompleteness:
    def test_fully_populated_todo_union_matches_expected_keys_exactly(self):
        """completionDate/cancellationDate are mutually exclusive per row
        (both derive from 'stop_date', disambiguated by 'status'), so the
        full contract is only exposed by unioning a completed + canceled
        row's output keys."""
        completed_keys = ToolsHelpers.convert_todo(FULLY_POPULATED_TODO).keys()
        canceled_keys = ToolsHelpers.convert_todo(FULLY_POPULATED_TODO_CANCELED).keys()
        assert completed_keys | canceled_keys == EXPECTED_TODO_KEYS
        assert "completionDate" in completed_keys and "cancellationDate" not in completed_keys
        assert "cancellationDate" in canceled_keys and "completionDate" not in canceled_keys

    def test_inherited_someday_and_checklist_list_add_exactly_those_keys(self):
        """FULLY_POPULATED_TODO_WITH_EXTRAS is status='completed', so it never
        carries cancellationDate - compare against EXPECTED_TODO_KEYS minus
        that one status-exclusive key, plus the two extras this test adds."""
        converted = ToolsHelpers.convert_todo(FULLY_POPULATED_TODO_WITH_EXTRAS)
        expected = (EXPECTED_TODO_KEYS - {"cancellationDate"}) | {"inheritedSomeday", "checklist"}
        assert converted.keys() == expected

    @pytest.mark.xfail(strict=True, reason="hq-f0w.29")
    def test_reminder_time_is_emitted_as_reminderTime(self):
        """things.py does emit 'reminder_time' on rows that have a reminder
        (live: 8/1699 todos, e.g. '09:00') but convert_todo currently drops
        it entirely - no 'reminderTime' key is emitted. Tracked in
        hq-f0w.29; this pins the gap so the fix is visible when landed
        (this test will start passing and must be un-xfailed then)."""
        converted = ToolsHelpers.convert_todo(FULLY_POPULATED_TODO)
        assert converted.get("reminderTime") == "09:00"


class TestConvertProjectKeyCompleteness:
    def test_fully_populated_project_union_matches_expected_keys_exactly(self):
        completed_keys = ToolsHelpers.convert_project(FULLY_POPULATED_PROJECT).keys()
        canceled_keys = ToolsHelpers.convert_project(FULLY_POPULATED_PROJECT_CANCELED).keys()
        assert completed_keys | canceled_keys == EXPECTED_PROJECT_KEYS
        assert "completionDate" in completed_keys and "cancellationDate" not in completed_keys
        assert "cancellationDate" in canceled_keys and "completionDate" not in canceled_keys


class TestConvertAreaKeyCompleteness:
    def test_fully_populated_area_matches_expected_keys_exactly(self):
        converted = ToolsHelpers.convert_area(FULLY_POPULATED_AREA)
        assert converted.keys() == EXPECTED_AREA_KEYS
