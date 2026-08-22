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
    'reminderTime': '09:00',
}

# A project row as produced by ToolsHelpers.convert_project - distinct from
# SAMPLE_ITEM (a todo row) because projects carry area/areaTitle instead of
# project/projectTitle/heading/headingTitle (hq-f0w.32).
SAMPLE_PROJECT_ITEM = {
    'uuid': 'project-1',
    'title': 'Sample project',
    'type': 'project',
    'status': 'open',
    'notes': 'Project notes',
    'tags': ['work'],
    'area': 'area-uuid',
    'areaTitle': 'My Area',
    'start': 'Anytime',
    'creationDate': '2026-08-01 10:00:00',
    'modificationDate': '2026-08-19 10:00:00',
    'dueDate': '2026-09-01',
    'startDate': '2026-08-10',
    'index': -100,
    'todayIndex': 0,
    'reminderTime': '09:00',
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

    def test_standard_mode_includes_reminderTime(self):
        """reminderTime (hq-f0w.29) is included in STANDARD, matching the
        other schedule-related fields (start/startDate)."""
        engine = _engine()
        filtered = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.STANDARD)[0]

        assert filtered.get('reminderTime') == '09:00'

    def test_summary_mode_excludes_reminderTime(self):
        engine = _engine()
        filtered = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.SUMMARY)[0]

        assert 'reminderTime' not in filtered

    def test_minimal_mode_excludes_reminderTime(self):
        engine = _engine()
        filtered = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.MINIMAL)[0]

        assert 'reminderTime' not in filtered

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

    def test_project_rows_standard_and_minimal_keep_area_fields(self):
        """hq-f0w.32: get_projects(mode='standard'/'minimal') must keep a
        project's area, not just detailed/raw - project rows are filtered
        against PROJECT_FIELD_SETS (not the todo-shaped TODO_FIELD_SETS)
        when method_name == 'get_projects'."""
        engine = _engine()

        minimal = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.MINIMAL, method_name='get_projects'
        )[0]
        assert minimal.get('area') == 'area-uuid'

        standard = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.STANDARD, method_name='get_projects'
        )[0]
        assert standard.get('area') == 'area-uuid'
        assert standard.get('areaTitle') == 'My Area'

    def test_project_rows_minimal_lacks_areaTitle_but_keeps_type_and_status(self):
        engine = _engine()
        minimal = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.MINIMAL, method_name='get_projects'
        )[0]
        for key in ('uuid', 'title', 'status', 'type', 'area'):
            assert key in minimal, f"MINIMAL project mode dropped required field: {key}"

    def test_project_rows_summary_mode_unchanged_fields(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.SUMMARY, method_name='get_projects'
        )[0]
        assert set(filtered.keys()) <= {'uuid', 'title', 'status', 'tags', 'dueDate'}

    def test_project_rows_detailed_mode_returns_all_fields(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.DETAILED, method_name='get_projects'
        )[0]
        assert filtered == SAMPLE_PROJECT_ITEM

    def test_todo_rows_unaffected_by_get_projects_field_sets(self):
        """A todo row filtered without method_name='get_projects' must keep
        using TODO_FIELD_SETS, not accidentally pick up PROJECT_FIELD_SETS."""
        engine = _engine()
        minimal = engine._apply_field_filtering([SAMPLE_ITEM], ResponseMode.MINIMAL)[0]
        assert minimal == engine._apply_field_filtering(
            [SAMPLE_ITEM], ResponseMode.MINIMAL, method_name='get_today'
        )[0]
        # 'project'/'projectTitle' (todo-shaped) survive; 'area' does not,
        # matching the pre-existing todo STANDARD/MINIMAL behavior.
        assert 'project' in minimal
        assert 'area' not in minimal

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
            reminder_time="09:00",
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
            reminder_time="09:00",
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

    def test_project_field_sets_are_subset_of_real_converter_output_keys(self):
        """Every non-None field set in PROJECT_FIELD_SETS (hq-f0w.32) must
        reference only keys that convert_project actually produces."""
        engine = _engine()
        real_keys = self._fully_populated_project_keys()

        for mode, allowed_fields in engine.PROJECT_FIELD_SETS.items():
            if allowed_fields is None:  # DETAILED: all fields, nothing to check
                continue
            unknown = allowed_fields - real_keys
            assert not unknown, (
                f"{mode}: PROJECT_FIELD_SETS references keys never produced "
                f"by convert_project: {unknown}"
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

    def test_get_optimization_capabilities_project_field_sets_match_PROJECT_FIELD_SETS(self):
        """get_optimization_capabilities() must also advertise the project
        field sets (hq-f0w.32), derived from PROJECT_FIELD_SETS."""
        engine = _engine()
        capabilities = engine.get_optimization_capabilities()
        advertised = capabilities["features"]["dynamic_field_filtering"]["project_field_sets"]

        assert advertised["summary"] == sorted(engine.PROJECT_FIELD_SETS[ResponseMode.SUMMARY])
        assert advertised["minimal"] == sorted(engine.PROJECT_FIELD_SETS[ResponseMode.MINIMAL])
        assert advertised["standard"] == sorted(engine.PROJECT_FIELD_SETS[ResponseMode.STANDARD])

    def test_get_optimization_capabilities_area_field_sets_match_AREA_FIELD_SETS(self):
        """get_optimization_capabilities() must also advertise the area
        field sets (hq-f0w.45), derived from AREA_FIELD_SETS - previously
        missing from the advertised capabilities (hq-f0w.37 review note)."""
        engine = _engine()
        capabilities = engine.get_optimization_capabilities()
        advertised = capabilities["features"]["dynamic_field_filtering"]["area_field_sets"]

        assert advertised["summary"] == sorted(engine.AREA_FIELD_SETS[ResponseMode.SUMMARY])
        assert advertised["minimal"] == sorted(engine.AREA_FIELD_SETS[ResponseMode.MINIMAL])
        assert advertised["standard"] == sorted(engine.AREA_FIELD_SETS[ResponseMode.STANDARD])


# A converted area row (ToolsHelpers.convert_area's fixed 4-key output).
SAMPLE_AREA_ITEM = {
    'uuid': 'area-1',
    'title': 'Sample area',
    'type': 'area',
    'tags': ['work'],
}


class TestAreaFieldSets:
    """hq-f0w.37: get_areas(mode='minimal') was silently dropping an area's
    tags because it fell through to TODO_FIELD_SETS' MINIMAL set (which
    lacks 'tags'). AREA_FIELD_SETS is used instead when
    method_name == 'get_areas', and - unlike TODO_FIELD_SETS/
    PROJECT_FIELD_SETS - is identical across summary/minimal/standard
    because convert_area's output schema is a fixed 4 keys."""

    def test_area_minimal_mode_keeps_tags(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_AREA_ITEM], ResponseMode.MINIMAL, method_name='get_areas'
        )[0]
        assert filtered.get('tags') == ['work']

    def test_area_summary_mode_keeps_tags(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_AREA_ITEM], ResponseMode.SUMMARY, method_name='get_areas'
        )[0]
        assert filtered.get('tags') == ['work']

    def test_area_standard_mode_matches_all_area_keys(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_AREA_ITEM], ResponseMode.STANDARD, method_name='get_areas'
        )[0]
        assert filtered == SAMPLE_AREA_ITEM

    def test_area_detailed_mode_returns_all_fields(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_AREA_ITEM], ResponseMode.DETAILED, method_name='get_areas'
        )[0]
        assert filtered == SAMPLE_AREA_ITEM

    def test_area_field_sets_are_subset_of_real_converter_output_keys(self):
        """Every field named in AREA_FIELD_SETS must be a key convert_area
        actually produces."""
        engine = _engine()
        real_keys = set(ToolsHelpers.convert_area({'uuid': 'x', 'title': 'y'}).keys())
        for mode, allowed_fields in engine.AREA_FIELD_SETS.items():
            if allowed_fields is None:
                continue
            unknown = allowed_fields - real_keys
            assert not unknown, (
                f"{mode}: AREA_FIELD_SETS references keys never produced by convert_area: {unknown}"
            )


class TestIncludeItemsNestedKeysSurvive:
    """hq-f0w.37: get_areas(include_items=True) and
    get_projects(include_items=True) build nested 'projects'/'todos' lists
    directly in read_operations.py, independent of response mode. Before
    this fix, MINIMAL/STANDARD field sets never listed 'projects'/'todos',
    so _apply_field_filtering silently dropped them - only DETAILED/RAW
    (which skip filtering entirely) kept them."""

    def test_get_areas_minimal_keeps_nested_projects_key(self):
        engine = _engine()
        area_with_projects = dict(SAMPLE_AREA_ITEM, projects=[{'uuid': 'p1', 'title': 'P1'}])
        filtered = engine._apply_field_filtering(
            [area_with_projects], ResponseMode.MINIMAL, method_name='get_areas'
        )[0]
        assert filtered.get('projects') == [{'uuid': 'p1', 'title': 'P1'}]

    def test_get_areas_standard_keeps_nested_todos_key(self):
        engine = _engine()
        area_with_todos = dict(SAMPLE_AREA_ITEM, todos=[{'uuid': 't1', 'title': 'T1'}])
        filtered = engine._apply_field_filtering(
            [area_with_todos], ResponseMode.STANDARD, method_name='get_areas'
        )[0]
        assert filtered.get('todos') == [{'uuid': 't1', 'title': 'T1'}]

    def test_get_projects_minimal_keeps_nested_todos_key(self):
        engine = _engine()
        project_with_todos = dict(SAMPLE_PROJECT_ITEM, todos=[{'uuid': 't1', 'title': 'T1'}])
        filtered = engine._apply_field_filtering(
            [project_with_todos], ResponseMode.MINIMAL, method_name='get_projects'
        )[0]
        assert filtered.get('todos') == [{'uuid': 't1', 'title': 'T1'}]

    def test_get_projects_standard_keeps_nested_todos_key(self):
        engine = _engine()
        project_with_todos = dict(SAMPLE_PROJECT_ITEM, todos=[{'uuid': 't1', 'title': 'T1'}])
        filtered = engine._apply_field_filtering(
            [project_with_todos], ResponseMode.STANDARD, method_name='get_projects'
        )[0]
        assert filtered.get('todos') == [{'uuid': 't1', 'title': 'T1'}]

    def test_nested_keys_not_added_when_absent(self):
        """A row without 'projects'/'todos' keys must not spontaneously
        gain them."""
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_AREA_ITEM], ResponseMode.MINIMAL, method_name='get_areas'
        )[0]
        assert 'projects' not in filtered
        assert 'todos' not in filtered

    def test_nested_keys_not_leaked_into_unrelated_methods(self):
        """The nested-key preservation is scoped to method_name in
        {'get_areas', 'get_projects'} - a todo row from get_today carrying a
        stray 'todos' key (shouldn't happen, but guard against it) must not
        have that key preserved by this mechanism."""
        engine = _engine()
        todo_with_stray_key = dict(SAMPLE_ITEM, todos=[{'uuid': 'x'}])
        filtered = engine._apply_field_filtering(
            [todo_with_stray_key], ResponseMode.MINIMAL, method_name='get_today'
        )[0]
        assert 'todos' not in filtered


class TestMixedListProjectRowDispatch:
    """hq-f0w.37: rows with type == 'project' inside nominally todo-shaped
    lists (get_today/get_anytime/get_upcoming/get_someday with
    include_projects=True, search_advanced) must be filtered against
    PROJECT_FIELD_SETS (carrying area/areaTitle), not TODO_FIELD_SETS,
    regardless of method_name."""

    def test_project_row_in_get_today_list_keeps_area(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.STANDARD, method_name='get_today'
        )[0]
        assert filtered.get('area') == 'area-uuid'
        assert filtered.get('areaTitle') == 'My Area'

    def test_project_row_in_get_today_list_keeps_area_under_minimal(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.MINIMAL, method_name='get_today'
        )[0]
        assert filtered.get('area') == 'area-uuid'

    def test_todo_row_in_same_list_still_uses_todo_field_set(self):
        """A mixed list containing both a todo row and a project row must
        filter each according to its own type, not a single method-wide
        choice."""
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_ITEM, SAMPLE_PROJECT_ITEM], ResponseMode.STANDARD, method_name='get_today'
        )
        todo_row, project_row = filtered
        assert 'area' not in todo_row
        assert 'project' in todo_row
        assert project_row.get('area') == 'area-uuid'

    def test_project_row_in_search_advanced_keeps_area(self):
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.STANDARD, method_name='search_advanced'
        )[0]
        assert filtered.get('area') == 'area-uuid'

    def test_project_row_in_get_projects_list_unaffected(self):
        """Sanity check: method_name == 'get_projects' with a project row
        still resolves to PROJECT_FIELD_SETS as before (no regression from
        adding the per-row dispatch)."""
        engine = _engine()
        filtered = engine._apply_field_filtering(
            [SAMPLE_PROJECT_ITEM], ResponseMode.MINIMAL, method_name='get_projects'
        )[0]
        assert filtered.get('area') == 'area-uuid'


class TestSummaryPreviewRowShape:
    """hq-9tm: summary-mode preview rows (ProgressiveDisclosureEngine's
    _summarize_todos/_summarize_projects/_summarize_search_results) must emit
    the documented SUMMARY field set {uuid, title, status, tags, dueDate}
    from CLAUDE.md's 'Todo field lists per mode', not a hand-built
    {id, name} shape. Previously the preview rows carried entirely different
    key names than the rest of the SUMMARY contract."""

    SUMMARY_KEYS = {'uuid', 'title', 'status', 'tags', 'dueDate'}

    def test_summarize_todos_preview_row_exact_keys(self):
        engine = _engine()
        summary = engine.progressive_engine._summarize_todos([SAMPLE_ITEM])
        preview = summary['recent_preview']
        assert len(preview) == 1
        row = preview[0]
        assert set(row.keys()) == self.SUMMARY_KEYS
        assert 'id' not in row
        assert 'name' not in row
        assert row['uuid'] == 'todo-1'
        assert row['title'] == 'Sample todo'
        assert row['status'] == 'incomplete'
        assert row['tags'] == ['work']
        assert row['dueDate'] is None

    def test_summarize_projects_preview_row_exact_keys(self):
        engine = _engine()
        summary = engine.progressive_engine._summarize_projects([SAMPLE_PROJECT_ITEM])
        preview = summary['recent_projects']
        assert len(preview) == 1
        row = preview[0]
        assert set(row.keys()) == self.SUMMARY_KEYS
        assert 'id' not in row
        assert 'name' not in row
        assert row['uuid'] == 'project-1'
        assert row['title'] == 'Sample project'
        assert row['status'] == 'open'
        assert row['tags'] == ['work']
        assert row['dueDate'] == '2026-09-01'
        # hq-wsa.1: SAMPLE_PROJECT_ITEM's fixture status ('open') does not
        # match the real things.py/convert_project status value
        # ('incomplete') - so this single-item, status='open' case
        # necessarily reports active=0 here. See
        # test_summarize_projects_active_counts_incomplete_status below for
        # the real-shape ('incomplete') case that hq-wsa.1 actually fixes.
        assert summary['active'] == 0
        assert summary['completed'] == 0
        assert summary['canceled'] == 0
        assert summary['status_breakdown'] == {'open': 1}

    def test_summarize_projects_active_counts_incomplete_status(self):
        """hq-wsa.1: things.py/convert_project emit status == 'incomplete'
        for open projects, never 'open' - active must count 'incomplete'
        rows, not a literal 'open' string that live data never produces."""
        engine = _engine()
        incomplete_project = dict(SAMPLE_PROJECT_ITEM, uuid='project-2', status='incomplete')
        summary = engine.progressive_engine._summarize_projects([incomplete_project])
        assert summary['active'] == 1
        assert summary['completed'] == 0
        assert summary['canceled'] == 0
        assert summary['status_breakdown'] == {'incomplete': 1}

    def test_summarize_projects_mixed_status_breakdown(self):
        """Mixed incomplete/completed/canceled set -> correct per-status
        counts and a dynamic status_breakdown reflecting all three."""
        engine = _engine()
        rows = [
            dict(SAMPLE_PROJECT_ITEM, uuid='p-incomplete-1', status='incomplete'),
            dict(SAMPLE_PROJECT_ITEM, uuid='p-incomplete-2', status='incomplete'),
            dict(SAMPLE_PROJECT_ITEM, uuid='p-completed-1', status='completed'),
            dict(SAMPLE_PROJECT_ITEM, uuid='p-canceled-1', status='canceled'),
        ]
        engine_summary = engine.progressive_engine._summarize_projects(rows)
        assert engine_summary['active'] == 2
        assert engine_summary['completed'] == 1
        assert engine_summary['canceled'] == 1
        assert engine_summary['status_breakdown'] == {
            'incomplete': 2,
            'completed': 1,
            'canceled': 1,
        }

    def test_summarize_search_results_preview_row_exact_keys(self):
        """Search preview rows mix todo and project rows depending on the
        underlying result's own 'type' - a to-do row here must resolve
        against TODO_FIELD_SETS, matching _apply_field_filtering's per-row
        dispatch used by non-preview list responses."""
        engine = _engine()
        summary = engine.progressive_engine._summarize_search_results([SAMPLE_ITEM])
        preview = summary['result_preview']
        assert len(preview) == 1
        row = preview[0]
        assert set(row.keys()) == self.SUMMARY_KEYS
        assert 'id' not in row
        assert 'name' not in row
        assert row['uuid'] == 'todo-1'
        assert row['title'] == 'Sample todo'

    def test_summarize_search_results_no_total_matches_key(self):
        """hq-wsa.5: _summarize_search_results must not emit 'total_matches'.
        The data it receives is already limit/offset-truncated by the time it
        gets here (server.py passes the final window down), so
        'total_matches': len(results) was always a post-limit count masquerading
        as a total - misleading whenever limit was in play. The envelope's
        separately-injected 'total' is the authoritative pre-limit count and is
        not touched by this function at all. Uses a truncated single-item
        window (as if limit=1 had been applied upstream) to make the point
        concrete: len(results) here is 1, which is exactly the wrong number to
        expose as any kind of 'total'."""
        engine = _engine()
        truncated_window = [SAMPLE_ITEM]  # stands in for a limit=1-truncated window
        summary = engine.progressive_engine._summarize_search_results(truncated_window)
        assert 'total_matches' not in summary
        # window-scoped keys describing the returned window are fine to keep
        assert 'search_results_breakdown' in summary
        assert 'result_preview' in summary

    def test_summarize_todos_preview_omits_null_fields(self):
        """Field-filtering never invents keys - a preview row for an item
        missing a SUMMARY field (e.g. no dueDate key at all) simply omits
        it, same convention as non-preview field filtering."""
        engine = _engine()
        sparse_todo = {'uuid': 'todo-2', 'title': 'No due date', 'status': 'open'}
        summary = engine.progressive_engine._summarize_todos([sparse_todo])
        row = summary['recent_preview'][0]
        assert set(row.keys()) == {'uuid', 'title', 'status'}
        assert 'dueDate' not in row
        assert 'tags' not in row
