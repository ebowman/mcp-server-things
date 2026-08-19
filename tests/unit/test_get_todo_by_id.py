"""Tests for ThingsTools.get_todo_by_id / _get_todo_by_id_sync (hq-nxu.4).

get_todo_by_id used to union things.todos(status=...) (to-do only, excludes
trashed) and linear-search for a matching uuid, so a valid project/heading/
trashed uuid raised ValueError('Todo not found'). It now uses
things.get(uuid), a direct-by-id lookup across all item types (including
trashed), and dispatches conversion by the returned item's `type`.

Fixtures are anonymised copies of rows captured live via things.py on
2026-08-19, in the same style as test_converters.py.
"""

import pytest
from unittest.mock import patch

from things_mcp.tools import ThingsTools


TODO = {
    "uuid": "LSGhTn44NpEsZphcNuMQcM",
    "type": "to-do",
    "title": "Send a doc to advisors",
    "status": "incomplete",
    "notes": "Some notes",
    "tags": ["work-tag"],
    "start": "Someday",
    "start_date": "2026-08-08",
    "deadline": None,
    "stop_date": None,
    "created": "2026-08-08 21:31:35",
    "modified": "2026-08-08 21:31:35",
    "index": -2764421,
    "today_index": -898,
}

PROJECT = {
    "uuid": "HpXrCLPoB4nJwr2Uikjto8",
    "type": "project",
    "title": "Project Template",
    "status": "incomplete",
    "area": "EHLNwkURV152JLuYREfpyp",
    "area_title": "King",
    "notes": "Some archived project notes",
    "start": "Someday",
    "start_date": None,
    "deadline": None,
    "stop_date": None,
    "created": "2024-03-19 21:07:43",
    "modified": "2025-08-05 09:27:49",
    "index": -99972,
    "today_index": 0,
}

HEADING = {
    "uuid": "6PsfVfwwHh8vD3jNXcwgsJ",
    "type": "heading",
    "title": "Review Calendar",
    "status": "incomplete",
    "project": "9r4F1446LXfRcj6a9fmpRD",
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

TRASHED_TODO = {
    "uuid": "XngAY1ro8HE97LaggXMhFX",
    "type": "to-do",
    "trashed": True,
    "title": "Triple_203756",
    "status": "incomplete",
    "notes": "Three field update",
    "start": "Anytime",
    "start_date": "2026-08-18",
    "deadline": None,
    "stop_date": None,
    "created": "2026-08-18 20:37:53",
    "modified": "2026-08-18 20:37:59",
    "index": -2766227,
    "today_index": -2145,
}


@pytest.fixture
def tools(mock_applescript_manager):
    """ThingsTools instance with a mocked AppleScript manager (unused here)."""
    return ThingsTools(mock_applescript_manager)


GET_PATCH = "things_mcp.tools_helpers.read_operations.things.get"
CHECKLIST_PATCH = "things_mcp.tools_helpers.read_operations.things.checklist_items"


class TestGetTodoById:
    """get_todo_by_id dispatches by things.get(uuid)'s `type` field."""

    @pytest.mark.asyncio
    async def test_to_do_dispatches_to_convert_todo_and_fetches_checklist(self, tools):
        with patch(GET_PATCH, return_value=dict(TODO)) as mock_get, \
                patch(CHECKLIST_PATCH, return_value=[{"title": "Step 1", "status": "incomplete"}]) as mock_checklist:
            result = await tools.get_todo_by_id(TODO["uuid"])

        mock_get.assert_called_once_with(TODO["uuid"])
        mock_checklist.assert_called_once_with(TODO["uuid"])
        assert result["type"] == "to-do"
        assert result["uuid"] == TODO["uuid"]
        assert result["checklist"] == [{"title": "Step 1", "status": "incomplete"}]
        assert "trashed" not in result

    @pytest.mark.asyncio
    async def test_to_do_checklist_fetch_failure_is_non_fatal(self, tools):
        """A checklist fetch error (KeyError/TypeError) shouldn't fail the whole lookup."""
        with patch(GET_PATCH, return_value=dict(TODO)), \
                patch(CHECKLIST_PATCH, side_effect=KeyError("boom")):
            result = await tools.get_todo_by_id(TODO["uuid"])

        assert result["type"] == "to-do"
        assert "checklist" not in result

    @pytest.mark.asyncio
    async def test_project_dispatches_to_convert_project_no_checklist_fetch(self, tools):
        with patch(GET_PATCH, return_value=dict(PROJECT)) as mock_get, \
                patch(CHECKLIST_PATCH) as mock_checklist:
            result = await tools.get_todo_by_id(PROJECT["uuid"])

        mock_get.assert_called_once_with(PROJECT["uuid"])
        mock_checklist.assert_not_called()
        assert result["type"] == "project"
        assert result["uuid"] == PROJECT["uuid"]
        assert result["areaTitle"] == "King"
        assert "trashed" not in result

    @pytest.mark.asyncio
    async def test_heading_dispatches_to_convert_todo_no_checklist_fetch(self, tools):
        with patch(GET_PATCH, return_value=dict(HEADING)) as mock_get, \
                patch(CHECKLIST_PATCH) as mock_checklist:
            result = await tools.get_todo_by_id(HEADING["uuid"])

        mock_get.assert_called_once_with(HEADING["uuid"])
        mock_checklist.assert_not_called()
        assert result["type"] == "heading"
        assert result["uuid"] == HEADING["uuid"]
        assert result["projectTitle"] == "Complete Weekly Review"
        assert "trashed" not in result

    @pytest.mark.asyncio
    async def test_trashed_todo_resolves_with_trashed_flag(self, tools):
        with patch(GET_PATCH, return_value=dict(TRASHED_TODO)), \
                patch(CHECKLIST_PATCH, return_value=[]):
            result = await tools.get_todo_by_id(TRASHED_TODO["uuid"])

        assert result["type"] == "to-do"
        assert result["trashed"] is True

    @pytest.mark.asyncio
    async def test_unknown_id_raises_value_error(self, tools):
        with patch(GET_PATCH, return_value=None):
            with pytest.raises(ValueError, match="Todo not found"):
                await tools.get_todo_by_id("does-not-exist")
