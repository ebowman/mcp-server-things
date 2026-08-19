"""Converter field-completeness tests (hq-f0w.10).

Two independent checks against ToolsHelpers.convert_todo/convert_project/
convert_area (tools_helpers/helpers.py), driven by realistic things.py rows
(tests/fixtures/things_realistic.py):

1. The converted output key set for a realistic, "everything populated"
   input covers an explicit EXPECTED_KEYS set per entity (documents the
   full camelCase key vocabulary each converter can emit, post hq-f0w.4).
   Any key the converter emits that isn't in EXPECTED_KEYS, or any expected
   key it fails to emit, fails the test - this pins the contract so a
   future edit that silently drops a field is caught immediately.

2. Every field name response_optimizer.py's ResponseOptimizer.optimize_*
   methods reference (via the internal _add_if_present/_add_relationship/
   _add_array_if_not_empty/_add_date_field helpers, discovered by parsing
   the optimizer source with `ast` rather than hand-copying the list - so
   this test can't silently drift from the real source) must either:
     a) appear in the converter's actual output key set for a realistic,
        fully-populated row, or
     b) be listed in that entity's DROPPED allowlist with a reason.
   This is what catches dead-code branches like
   response_optimizer.py:66 (`_add_if_present(optimized, todo, 'heading')`)
   going unnoticed: convert_todo *does* emit 'heading', so that particular
   reference isn't dead - but nearly every other field name
   ResponseOptimizer.optimize_todo/optimize_project/optimize_area
   references (name/when/tag_names/completed/created/modified/...) is
   snake_case and simply does not exist anywhere in convert_todo's
   camelCase output (title/dueDate/tags/status/creationDate/...). That
   mismatch means ResponseOptimizer.optimize_todo/optimize_project/
   optimize_area are effectively dead code against the real converter
   output shape - documented via the DROPPED allowlists below rather than
   fixed (out of scope for this fixtures/tests-only bead; tracked as
   follow-up work in bead hq-nxu.7).

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
"""

import ast
import inspect
import textwrap

import pytest

from things_mcp import response_optimizer as ro
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


# ---------------------------------------------------------------------------
# Check 2: every field response_optimizer.py's optimize_* methods reference
# must be produced by the matching converter, or be in an explicit,
# reasoned DROPPED allowlist.
# ---------------------------------------------------------------------------

_OPTIMIZER_HELPER_METHODS = {
    "_add_if_present",
    "_add_relationship",
    "_add_array_if_not_empty",
    "_add_date_field",
}


def _referenced_fields(method_name: str) -> set:
    """Parse ResponseOptimizer.<method_name> source via `ast` and return the
    set of field-name string literals passed as the 3rd positional arg to
    any of the _add_*/_add_relationship helper calls, plus any field
    accessed via a direct `<param>.get('field'...)` / `<param>['field']`
    call/subscript on the method's data parameter (covers fields read
    without going through a helper, e.g. optimize_tag's `tag.get('name')`).

    Parsing the live source (rather than hand-copying a list) means this
    test cannot silently drift from response_optimizer.py.
    """
    method = getattr(ro.ResponseOptimizer, method_name)
    source = textwrap.dedent(inspect.getsource(method))
    tree = ast.parse(source)
    func_node = tree.body[0]
    assert isinstance(func_node, ast.FunctionDef)

    # The data parameter is the 2nd positional arg (after self).
    data_param = func_node.args.args[1].arg

    fields = set()
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _OPTIMIZER_HELPER_METHODS and len(node.args) >= 3:
                arg = node.args[2]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    fields.add(arg.value)
            elif node.func.attr == "get" and isinstance(node.func.value, ast.Name):
                if node.func.value.id == data_param and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        fields.add(arg.value)
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id == data_param:
                sl = node.slice
                if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                    fields.add(sl.value)
    return fields


# DROPPED allowlists: field names response_optimizer.py references for this
# entity that the corresponding ToolsHelpers.convert_* function does not
# produce, each with a reason. response_optimizer.py's ResponseOptimizer
# class operates on a different (older, snake_case: name/when/tag_names/
# completed/id/...) field schema than ToolsHelpers.convert_todo/
# convert_project/convert_area's real camelCase output (title/dueDate/tags/
# status/uuid/...) - per the module docstrings in tools_helpers/helpers.py,
# ResponseOptimizer.optimize_todo/optimize_project/optimize_area are not
# actually wired into the read_operations.py list-tool call paths (nothing
# under src/things_mcp ever calls self.response_optimizer.optimize_todo/
# optimize_project/optimize_area/optimize_tag - grep confirms only the
# ResponseOptimizer instance itself, and its private _add_if_present-style
# helpers indirectly, are referenced). Because the whole optimize_* family
# is dead code against the real converter schema, every field it references
# that isn't a same-named literal match is allowlisted below with that one
# shared reason rather than repeated per field.

_DEAD_OPTIMIZER_REASON = (
    "ResponseOptimizer.optimize_todo/optimize_project/optimize_area are not "
    "called anywhere in the read path (grep: no call site invokes "
    "self.response_optimizer.optimize_*); they operate on a snake_case "
    "field schema (name/when/tag_names/completed/id/...) left over from "
    "before convert_todo/convert_project/convert_area were rewritten to "
    "the real things.py key set (hq-f0w.4) and now emit camelCase "
    "(title/dueDate/tags/status/uuid/...). Fixing the mismatch is out of "
    "scope for this fixtures/tests-only bead (hq-f0w.10); tracked as "
    "follow-up work in bead hq-nxu.7."
)

DROPPED_TODO = {
    "id": _DEAD_OPTIMIZER_REASON + " (convert_todo's identifier key is 'uuid', never 'id').",
    "name": _DEAD_OPTIMIZER_REASON + " (convert_todo's title key is 'title', never 'name').",
    "when": _DEAD_OPTIMIZER_REASON + " (convert_todo's equivalent is 'start'/'startDate').",
    "deadline": _DEAD_OPTIMIZER_REASON + " (convert_todo's equivalent is 'dueDate').",
    "completed": _DEAD_OPTIMIZER_REASON + " (convert_todo's equivalent is 'completionDate').",
    "tag_names": _DEAD_OPTIMIZER_REASON + " (convert_todo's equivalent is 'tags').",
    "checklist": (
        "optimize_todo reads a raw list-shaped 'checklist' field, but "
        "convert_todo only emits a 'checklist' list key when the caller "
        "pre-fetches real checklist items (read_operations.py include_items "
        "path); this fully-populated fixture uses checklist=True (the "
        "normal things.py bool 'has a checklist' flag), which convert_todo "
        "correctly turns into 'hasChecklist' instead. " + _DEAD_OPTIMIZER_REASON
    ),
    "has_reminder": (
        "things.py does not expose a boolean 'has_reminder' field (only "
        "'reminder_time' itself, e.g. '09:00', on the small subset of rows "
        "that have a reminder - live: 8/1699 todos); convert_todo has no "
        "'has_reminder' equivalent to emit. " + _DEAD_OPTIMIZER_REASON
    ),
    "reminder_time": (
        "things.py does emit reminder_time; convert_todo currently drops "
        "it - tracked in bead hq-f0w.29."
    ),
    "activation_date": _DEAD_OPTIMIZER_REASON + " (convert_todo's equivalent is 'startDate').",
    "created": _DEAD_OPTIMIZER_REASON + " (convert_todo's equivalent is 'creationDate').",
    "modified": _DEAD_OPTIMIZER_REASON + " (convert_todo's equivalent is 'modificationDate').",
    "area": (
        "things.py to-do rows never carry an 'area' key (only projects/"
        "headings can belong to an area); convert_todo correctly never "
        "emits one. " + _DEAD_OPTIMIZER_REASON
    ),
}

DROPPED_PROJECT = {
    "id": _DEAD_OPTIMIZER_REASON + " (convert_project's identifier key is 'uuid', never 'id').",
    "name": _DEAD_OPTIMIZER_REASON + " (convert_project's title key is 'title', never 'name').",
    "when": _DEAD_OPTIMIZER_REASON + " (convert_project's equivalent is 'start'/'startDate').",
    "deadline": _DEAD_OPTIMIZER_REASON + " (convert_project's equivalent is 'dueDate').",
    "completed": _DEAD_OPTIMIZER_REASON + " (convert_project's equivalent is 'completionDate').",
    "tag_names": _DEAD_OPTIMIZER_REASON + " (convert_project's equivalent is 'tags').",
    "created": _DEAD_OPTIMIZER_REASON + " (convert_project's equivalent is 'creationDate').",
    "modified": _DEAD_OPTIMIZER_REASON + " (convert_project's equivalent is 'modificationDate').",
    "item_count": (
        "convert_project never emits an item/child count - counting "
        "project items is not part of the converter's job. " + _DEAD_OPTIMIZER_REASON
    ),
}

DROPPED_AREA = {
    "id": _DEAD_OPTIMIZER_REASON + " (convert_area's identifier key is 'uuid', never 'id').",
    "name": _DEAD_OPTIMIZER_REASON + " (convert_area's title key is 'title', never 'name').",
    "notes": (
        "things.py area rows carry no 'notes' field and convert_area "
        "never emits one (only uuid/title/type/tags). " + _DEAD_OPTIMIZER_REASON
    ),
    "tag_names": _DEAD_OPTIMIZER_REASON + " (convert_area's equivalent is 'tags').",
    "created": (
        "things.py area rows carry no creation-date field and "
        "convert_area never emits one. " + _DEAD_OPTIMIZER_REASON
    ),
    "modified": (
        "things.py area rows carry no modification-date field and "
        "convert_area never emits one. " + _DEAD_OPTIMIZER_REASON
    ),
    "item_count": (
        "convert_area never emits an item/child count - counting area "
        "items is not part of the converter's job. " + _DEAD_OPTIMIZER_REASON
    ),
}


class TestOptimizerFieldsCoveredByConverterOrAllowlisted:
    """Every field response_optimizer.py's optimize_todo/optimize_project/
    optimize_area reads must appear in the matching converter's realistic
    output, or be explicitly allowlisted with a reason above."""

    def test_optimize_todo_fields_covered_or_dropped(self):
        referenced = _referenced_fields("optimize_todo")
        converted_keys = ToolsHelpers.convert_todo(FULLY_POPULATED_TODO).keys()

        uncovered = referenced - converted_keys - DROPPED_TODO.keys()
        assert not uncovered, (
            f"response_optimizer.optimize_todo references fields not produced "
            f"by convert_todo and not allowlisted in DROPPED_TODO: {uncovered}"
        )
        for field in DROPPED_TODO:
            assert field in referenced, (
                f"DROPPED_TODO allowlist entry '{field}' is no longer "
                f"referenced by optimize_todo - remove the stale entry"
            )

    def test_optimize_project_fields_covered_or_dropped(self):
        referenced = _referenced_fields("optimize_project")
        converted_keys = ToolsHelpers.convert_project(FULLY_POPULATED_PROJECT).keys()

        uncovered = referenced - converted_keys - DROPPED_PROJECT.keys()
        assert not uncovered, (
            f"response_optimizer.optimize_project references fields not "
            f"produced by convert_project and not allowlisted in "
            f"DROPPED_PROJECT: {uncovered}"
        )
        for field in DROPPED_PROJECT:
            assert field in referenced, (
                f"DROPPED_PROJECT allowlist entry '{field}' is no longer "
                f"referenced by optimize_project - remove the stale entry"
            )

    def test_optimize_area_fields_covered_or_dropped(self):
        referenced = _referenced_fields("optimize_area")
        converted_keys = ToolsHelpers.convert_area(FULLY_POPULATED_AREA).keys()

        uncovered = referenced - converted_keys - DROPPED_AREA.keys()
        assert not uncovered, (
            f"response_optimizer.optimize_area references fields not "
            f"produced by convert_area and not allowlisted in "
            f"DROPPED_AREA: {uncovered}"
        )
        for field in DROPPED_AREA:
            assert field in referenced, (
                f"DROPPED_AREA allowlist entry '{field}' is no longer "
                f"referenced by optimize_area - remove the stale entry"
            )

    def test_notes_field_is_covered_directly_no_allowlist_needed(self):
        """Sanity check: 'notes' is a genuine same-name match across both
        schemas, proving the covered/dropped split above is meaningful and
        not just allowlisting everything."""
        assert "notes" in _referenced_fields("optimize_todo")
        assert "notes" in ToolsHelpers.convert_todo(FULLY_POPULATED_TODO)
