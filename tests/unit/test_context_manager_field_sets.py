"""Tests for hq-f0w.4 step 3: context_manager.py mode field sets after the
convert_todo/convert_project field rewrite.
"""

from things_mcp.context_manager import (
    ContextAwareResponseManager,
    ContextBudget,
    ResponseMode,
)


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
