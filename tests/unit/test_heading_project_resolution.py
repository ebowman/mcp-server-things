"""Tests for hq-f0w.24: heading-children backfill project/projectTitle.

things.py to-do rows parented under a heading carry heading/heading_title but
leave project/project_title None (things.py only denormalizes project onto
the heading row itself, live-confirmed 2026-08-19: 0/40 heading-children have
a populated project field). ReadOperations._fill_project_from_heading() is a
post-conversion pass, applied at every convert_todo() call site in
read_operations.py, that backfills project/projectTitle for such items by
batch-resolving via a single things.tasks(type='heading') call (cached per
request/list) or, for get_todo_by_id's single-item lookup, a direct
things.get() call on the heading.
"""

import pytest
from unittest.mock import patch

from things_mcp.tools import ThingsTools


TASKS_PATCH = "things_mcp.tools_helpers.read_operations.things.tasks"
TODOS_PATCH = "things_mcp.tools_helpers.read_operations.things.todos"
TODAY_PATCH = "things_mcp.tools_helpers.read_operations.things.today"
GET_PATCH = "things_mcp.tools_helpers.read_operations.things.get"
CHECKLIST_PATCH = "things_mcp.tools_helpers.read_operations.things.checklist_items"


HEADING_ROW = {
    "uuid": "heading-1",
    "type": "heading",
    "title": "Review Calendar",
    "status": "incomplete",
    "project": "proj-1",
    "project_title": "Complete Weekly Review",
    "notes": "",
    "start": "Anytime",
    "start_date": None,
    "deadline": None,
    "stop_date": None,
    "created": "2017-09-03 21:38:20",
    "modified": "2017-09-03 21:38:20",
    "index": -515,
    "today_index": 0,
}

TODO_UNDER_HEADING = {
    "uuid": "todo-under-heading-1",
    "type": "to-do",
    "title": "Look at Calendar for the past 2 weeks",
    "status": "incomplete",
    "heading": "heading-1",
    "heading_title": "Review Calendar",
    "notes": "",
    "start": "Anytime",
    "start_date": None,
    "deadline": None,
    "stop_date": None,
    "created": "2017-09-03 21:38:20",
    "modified": "2017-09-03 21:38:20",
    "index": -417,
    "today_index": 0,
    # No 'project'/'project_title' key - matches real things.py rows.
}

TODO_STANDALONE = {
    "uuid": "todo-standalone-1",
    "type": "to-do",
    "title": "Buy milk",
    "status": "incomplete",
    "notes": "",
    "start": "Anytime",
    "start_date": None,
    "deadline": None,
    "stop_date": None,
    "created": "2026-01-01 09:00:00",
    "modified": "2026-01-01 09:00:00",
    "index": 0,
    "today_index": 0,
}

TODO_DIRECT_PROJECT = {
    "uuid": "todo-direct-project-1",
    "type": "to-do",
    "title": "Top-level project task",
    "status": "incomplete",
    "project": "proj-2",
    "project_title": "Other Project",
    "notes": "",
    "start": "Anytime",
    "start_date": None,
    "deadline": None,
    "stop_date": None,
    "created": "2026-01-01 09:00:00",
    "modified": "2026-01-01 09:00:00",
    "index": 0,
    "today_index": 0,
}


@pytest.fixture
def tools(mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


class TestGetTodosBackfillsHeadingProject:
    """get_todos()/get_today() fill project/projectTitle for heading-children."""

    @pytest.mark.asyncio
    async def test_get_todos_fills_project_for_heading_child(self, tools):
        with patch(TODOS_PATCH, return_value=[dict(TODO_UNDER_HEADING)]), \
                patch(TASKS_PATCH, return_value=[dict(HEADING_ROW)]) as mock_tasks:
            result = await tools.get_todos()

        assert len(result) == 1
        item = result[0]
        assert item["project"] == "proj-1"
        assert item["projectTitle"] == "Complete Weekly Review"
        assert item["heading"] == "heading-1"
        mock_tasks.assert_called_once_with(type="heading", status=None)

    @pytest.mark.asyncio
    async def test_get_today_fills_project_for_heading_child(self, tools):
        with patch(TODAY_PATCH, return_value=[dict(TODO_UNDER_HEADING)]), \
                patch(
                    "things_mcp.tools_helpers.read_operations.things.projects",
                    return_value=[],
                ), \
                patch(TASKS_PATCH, return_value=[dict(HEADING_ROW)]):
            result = await tools.get_today()

        assert len(result) == 1
        assert result[0]["project"] == "proj-1"
        assert result[0]["projectTitle"] == "Complete Weekly Review"

    @pytest.mark.asyncio
    async def test_standalone_todo_is_untouched(self, tools):
        """A todo with no heading is never passed to the heading map lookup,
        and things.tasks() is not called at all (lazy - no work to do)."""
        with patch(TODOS_PATCH, return_value=[dict(TODO_STANDALONE)]), \
                patch(TASKS_PATCH) as mock_tasks:
            result = await tools.get_todos()

        assert result[0]["project"] is None
        assert result[0]["projectTitle"] is None
        mock_tasks.assert_not_called()

    @pytest.mark.asyncio
    async def test_todo_with_own_project_is_not_overwritten(self, tools):
        """A todo directly in a project (no heading) already has project set by
        things.py - the backfill must never overwrite an existing value."""
        with patch(TODOS_PATCH, return_value=[dict(TODO_DIRECT_PROJECT)]), \
                patch(TASKS_PATCH) as mock_tasks:
            result = await tools.get_todos()

        assert result[0]["project"] == "proj-2"
        assert result[0]["projectTitle"] == "Other Project"
        mock_tasks.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_heading_leaves_project_none(self, tools):
        """If the heading can't be resolved (e.g. deleted/missing from the
        things.tasks(type='heading') result), project/projectTitle stay None
        rather than raising."""
        with patch(TODOS_PATCH, return_value=[dict(TODO_UNDER_HEADING)]), \
                patch(TASKS_PATCH, return_value=[]):
            result = await tools.get_todos()

        assert result[0]["project"] is None
        assert result[0]["projectTitle"] is None

    @pytest.mark.asyncio
    async def test_things_tasks_error_is_defensive(self, tools):
        """An error while building the heading->project map must not fail the
        whole request - project/projectTitle simply stay None."""
        with patch(TODOS_PATCH, return_value=[dict(TODO_UNDER_HEADING)]), \
                patch(TASKS_PATCH, side_effect=RuntimeError("boom")):
            result = await tools.get_todos()

        assert len(result) == 1
        assert result[0]["project"] is None
        assert result[0]["projectTitle"] is None

    @pytest.mark.asyncio
    async def test_mixed_batch_resolves_only_heading_children(self, tools):
        """A batch with both a heading-child and a standalone/direct-project
        todo only enriches the heading-child; things.tasks() is called once
        for the whole batch (not once per item)."""
        with patch(
            TODOS_PATCH,
            return_value=[dict(TODO_UNDER_HEADING), dict(TODO_STANDALONE), dict(TODO_DIRECT_PROJECT)],
        ), patch(TASKS_PATCH, return_value=[dict(HEADING_ROW)]) as mock_tasks:
            result = await tools.get_todos()

        by_uuid = {item["uuid"]: item for item in result}
        assert by_uuid["todo-under-heading-1"]["project"] == "proj-1"
        assert by_uuid["todo-under-heading-1"]["projectTitle"] == "Complete Weekly Review"
        assert by_uuid["todo-standalone-1"]["project"] is None
        assert by_uuid["todo-direct-project-1"]["project"] == "proj-2"
        mock_tasks.assert_called_once_with(type="heading", status=None)


class TestCompletedHeadingsAreResolved:
    """things.tasks()'s own default status filter is 'incomplete', which only
    covers headings belonging to open projects (live: 30/674 headings). The
    heading map must be built with status=None so headings under
    completed/canceled projects (completed projects, finished repeating-project
    instances) are included too - otherwise their to-do children's
    project/projectTitle stay unresolved even though the fix "works" for
    headings under open projects."""

    COMPLETED_HEADING_ROW = {
        "uuid": "heading-completed-1",
        "type": "heading",
        "title": "Archived Section",
        "status": "completed",
        "project": "proj-completed-1",
        "project_title": "Finished Project",
        "notes": "",
        "start": "Anytime",
        "start_date": None,
        "deadline": None,
        "stop_date": "2026-01-01 09:00:00",
        "created": "2026-01-01 09:00:00",
        "modified": "2026-01-01 09:00:00",
        "index": 0,
        "today_index": 0,
    }

    COMPLETED_TODO_UNDER_COMPLETED_HEADING = {
        "uuid": "todo-completed-under-heading-1",
        "type": "to-do",
        "title": "Finished subtask",
        "status": "completed",
        "heading": "heading-completed-1",
        "heading_title": "Archived Section",
        "notes": "",
        "start": "Anytime",
        "start_date": None,
        "deadline": None,
        "stop_date": "2026-01-01 09:00:00",
        "created": "2026-01-01 09:00:00",
        "modified": "2026-01-01 09:00:00",
        "index": 0,
        "today_index": 0,
        # No 'project'/'project_title' key - matches real things.py rows.
    }

    @pytest.mark.asyncio
    async def test_get_todos_status_completed_resolves_heading_under_completed_project(self, tools):
        """get_todos(status='completed') must resolve project/projectTitle for a
        completed to-do filed under a heading whose own status is 'completed' -
        the heading map has to include non-incomplete headings, not just open
        ones, or this whole class of item is silently left unresolved."""
        with patch(TODOS_PATCH, return_value=[dict(self.COMPLETED_TODO_UNDER_COMPLETED_HEADING)]), \
                patch(TASKS_PATCH, return_value=[dict(self.COMPLETED_HEADING_ROW)]) as mock_tasks:
            result = await tools.get_todos(status='completed')

        assert len(result) == 1
        item = result[0]
        assert item["project"] == "proj-completed-1"
        assert item["projectTitle"] == "Finished Project"
        mock_tasks.assert_called_once_with(type="heading", status=None)

    @pytest.mark.asyncio
    async def test_get_logbook_resolves_heading_under_completed_project(self, tools):
        """get_logbook (completed-only by construction) must likewise resolve
        project/projectTitle for a completed heading-child."""
        def todos_side_effect(status=None, **kwargs):
            if status == 'completed':
                return [dict(self.COMPLETED_TODO_UNDER_COMPLETED_HEADING)]
            return []

        with patch(TODOS_PATCH, side_effect=todos_side_effect), \
                patch(TASKS_PATCH, return_value=[dict(self.COMPLETED_HEADING_ROW)]):
            result = await tools.get_logbook(period="365d")

        assert len(result) == 1
        item = result[0]
        assert item["project"] == "proj-completed-1"
        assert item["projectTitle"] == "Finished Project"


class TestGetTodoByIdBackfillsHeadingProject:
    """get_todo_by_id() resolves a single heading-child via a direct things.get()
    call rather than fetching the whole heading list."""

    @pytest.mark.asyncio
    async def test_heading_child_resolved_via_single_get_call(self, tools):
        def get_side_effect(uuid):
            if uuid == TODO_UNDER_HEADING["uuid"]:
                return dict(TODO_UNDER_HEADING)
            if uuid == "heading-1":
                return dict(HEADING_ROW)
            return None

        with patch(GET_PATCH, side_effect=get_side_effect) as mock_get, \
                patch(CHECKLIST_PATCH, return_value=[]), \
                patch(TASKS_PATCH) as mock_tasks:
            result = await tools.get_todo_by_id(TODO_UNDER_HEADING["uuid"])

        assert result["project"] == "proj-1"
        assert result["projectTitle"] == "Complete Weekly Review"
        # Single-item path must not call the batch things.tasks(type='heading').
        mock_tasks.assert_not_called()
        assert mock_get.call_count == 2

    @pytest.mark.asyncio
    async def test_standalone_todo_by_id_untouched(self, tools):
        with patch(GET_PATCH, return_value=dict(TODO_STANDALONE)) as mock_get, \
                patch(CHECKLIST_PATCH, return_value=[]):
            result = await tools.get_todo_by_id(TODO_STANDALONE["uuid"])

        assert result["project"] is None
        assert result["projectTitle"] is None
        # No heading key on the item, so only the original lookup happens.
        mock_get.assert_called_once_with(TODO_STANDALONE["uuid"])

    @pytest.mark.asyncio
    async def test_heading_child_missing_heading_row_is_defensive(self, tools):
        """If things.get(heading_uuid) returns None (deleted heading), the
        lookup doesn't raise and project/projectTitle stay None."""
        def get_side_effect(uuid):
            if uuid == TODO_UNDER_HEADING["uuid"]:
                return dict(TODO_UNDER_HEADING)
            return None

        with patch(GET_PATCH, side_effect=get_side_effect), \
                patch(CHECKLIST_PATCH, return_value=[]):
            result = await tools.get_todo_by_id(TODO_UNDER_HEADING["uuid"])

        assert result["project"] is None
        assert result["projectTitle"] is None
