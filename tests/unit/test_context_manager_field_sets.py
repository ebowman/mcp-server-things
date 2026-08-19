"""Tests for hq-f0w.4 step 3: context_manager.py mode field sets after the
convert_todo/convert_project field rewrite.
"""

from things_mcp.context_manager import (
    ContextAwareResponseManager,
    ContextBudget,
    ResponseMode,
)
from things_mcp.tools_helpers.helpers import ToolsHelpers

from fixtures.things_realistic import make_todo, make_project, ANYTIME_PROJECT


SAMPLE_ITEM = {
    'uuid': 'todo-1',
    'title': 'Sample todo',
    'type': 'to-do',
    'status': 'incomplete',
    'notes': 'Some notes',
    'dueDate': None,
    'modificationDate': '2026-08-19 10:00:00',
    'creationDate': '2026-08-01 10:00:00',
    'tags': ['work'],
    'project': 'project-uuid',
    'projectTitle': 'My Project',
    'heading': 'heading-uuid',
    'headingTitle': 'My Heading',
    'start': 'Anytime',
    'startDate': '2026-08-10',
    'inheritedSomeday': True,
    'area': None,  # to-do rows never carry a real area value
    'index': -100,
    'todayIndex': 0,
    'hasChecklist': False,
}


def _engine():
    return ContextAwareResponseManager(ContextBudget())


class TestFieldFilteringByMode:
    def test_minimal_mode_retains_locate_fields(self):
        engine = _engine()
        filtered = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.MINIMAL)[0]

        # MINIMAL must keep at least uuid, title, status, type, start,
        # project so a minimal result can still locate a todo.
        for key in ('uuid', 'title', 'status', 'type', 'start', 'project'):
            assert key in filtered, f"MINIMAL mode dropped required field: {key}"

    def test_standard_mode_includes_new_fields(self):
        engine = _engine()
        filtered = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.STANDARD)[0]

        for key in ('type', 'start', 'projectTitle', 'heading', 'headingTitle'):
            assert key in filtered, f"STANDARD mode missing new field: {key}"

    def test_standard_mode_excludes_area(self):
        """'area' was removed from the todo STANDARD field set - things.py
        to-do rows never carry an area key (only projects do)."""
        engine = _engine()
        filtered = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.STANDARD)[0]

        assert 'area' not in filtered

    def test_summary_mode_unchanged_fields(self):
        engine = _engine()
        filtered = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.SUMMARY)[0]

        assert set(filtered.keys()) <= {'uuid', 'title', 'status', 'tags', 'dueDate'}

    def test_detailed_mode_returns_all_fields(self):
        engine = _engine()
        filtered = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.DETAILED)[0]

        assert filtered == SAMPLE_ITEM

    def test_todo_row_minimal_and_standard_lack_index(self):
        """'index' and 'todoCount' are get_project_headings-specific fields
        (hq-f0w.6) and must never leak into ordinary todo rows, even though
        SAMPLE_ITEM (a todo row) carries an 'index' key from convert_todo."""
        engine = _engine()

        minimal = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.MINIMAL)[0]
        assert 'index' not in minimal
        assert 'todoCount' not in minimal

        standard = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.STANDARD)[0]
        assert 'index' not in standard
        assert 'todoCount' not in standard

    def test_project_headings_minimal_and_standard_keep_index_and_todo_count(self):
        """get_project_headings items use a distinct schema and are
        filtered by method_name rather than the global todo field sets."""
        engine = _engine()
        heading_item = {
            'uuid': 'heading-1',
            'title': 'Research',
            'index': -515,
            'todoCount': 2,
        }

        minimal = engine._apply_field_filtering(
            [heading_item], ResponseMode.MINIMAL, method_name='get_project_headings'
        )[0]
        assert minimal == heading_item

        standard = engine._apply_field_filtering(
            [heading_item], ResponseMode.STANDARD, method_name='get_project_headings'
        )[0]
        assert standard == heading_item


class TestModeFieldSetsReferenceOnlyRealKeys(object):
    """hq-nxu.7: every field named in context_manager's per-mode field sets
    must be a key that convert_todo/convert_project can actually emit, and
    get_optimization_capabilities() must advertise those same sets rather
    than a stale, hand-maintained copy (this is what response_optimizer.py's
    dead ResponseOptimizer class used to drift against undetected)."""

    def _fully_populated_todo_keys(self):
        todo = make_todo(
            "todo-full",
            "Fully populated to-do",
            status="completed",
            notes="Some notes",
            tags=["work", "urgent"],
            project=ANYTIME_PROJECT["uuid"],
            project_title=ANYTIME_PROJECT["title"],
            checklist=True,
            start_date="2026-01-01",
            deadline="2026-02-01",
            stop_date="2026-01-15 10:00:00",
        )
        # inherited_someday is applied post-hoc, not a make_todo() kwarg -
        # convert_todo only emits 'inheritedSomeday' when this raw key is
        # present and truthy (see test_converter_completeness.py).
        todo["inherited_someday"] = True
        return set(ToolsHelpers.convert_todo(todo).keys())

    def _fully_populated_project_keys(self):
        project = make_project(
            "project-full",
            "Fully populated project",
            status="completed",
            notes="Project notes",
            area=ANYTIME_PROJECT["area"],
            area_title=ANYTIME_PROJECT["area_title"],
            start_date="2026-01-01",
            deadline="2026-03-01",
            stop_date="2026-02-15 09:00:00",
        )
        return set(ToolsHelpers.convert_project(project).keys())

    def test_mode_field_sets_are_subset_of_real_converter_output_keys(self):
        """Every non-None field set in TODO_FIELD_SETS must reference only
        keys that convert_todo (or convert_project, for the 'project'-shaped
        subset) actually produces. A stale field like the old 'area' entry
        (removed by hq-f0w.4) or a snake_case leftover would fail here."""
        engine = _engine()
        real_keys = self._fully_populated_todo_keys() | self._fully_populated_project_keys()

        for mode, allowed_fields in engine.TODO_FIELD_SETS.items():
            if allowed_fields is None:  # DETAILED: all fields, nothing to check
                continue
            unknown = allowed_fields - real_keys
            assert not unknown, (
                f"{mode}: field set references keys never produced by "
                f"convert_todo/convert_project: {unknown}"
            )

    def test_get_optimization_capabilities_field_sets_match_TODO_FIELD_SETS(self):
        """get_optimization_capabilities() must derive its advertised
        summary/minimal/standard field lists from the same TODO_FIELD_SETS
        used for actual filtering, not a separately maintained (and
        driftable) copy."""
        engine = _engine()
        capabilities = engine.get_optimization_capabilities()
        advertised = capabilities["features"]["dynamic_field_filtering"]["field_sets"]

        assert advertised["summary"] == sorted(engine.TODO_FIELD_SETS[ResponseMode.SUMMARY])
        assert advertised["minimal"] == sorted(engine.TODO_FIELD_SETS[ResponseMode.MINIMAL])
        assert advertised["standard"] == sorted(engine.TODO_FIELD_SETS[ResponseMode.STANDARD])
