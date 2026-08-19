"""Tests for ThingsTools.get_todo_by_id / _get_todo_by_id_sync (hq-nxu.4, hq-f0w.23).

get_todo_by_id used to union things.todos(status=...) (to-do only, excludes
trashed) and linear-search for a matching uuid, so a valid project/heading/
trashed uuid raised ValueError('Todo not found'). It now uses
things.get(uuid), a direct-by-id lookup across all item types (including
trashed), and dispatches conversion by the returned item's `type`.

things.get(uuid) also falls through to areas() and tags() (things.py 1.0.1),
so it resolves area and tag uuids too: area uuids dispatch to convert_area
(type 'area'); tag uuids return a structured invalid_type error, since a tag
is a label, not a retrievable item.

things.get(uuid) internally forces include_items=True for any single-uuid
lookup, so a to-do's `checklist` key (when the to-do has one) is already the
full list of checklist item dicts - no separate things.checklist_items()
re-fetch is needed or performed.

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

# things.get(uuid) on a to-do with a checklist forces include_items=True, so
# 'checklist' is already the full list of checklist-item dicts (each also
# carries uuid/type/created/modified/stop_date, captured live 2026-08-19).
TODO_WITH_CHECKLIST = {
    **TODO,
    "uuid": "Hu8yV5iMwSwfUNV6tFjVek",
    "checklist": [
        {
            "title": "Step 1",
            "status": "completed",
            "stop_date": "2026-07-12",
            "type": "checklist-item",
            "uuid": "ApSmePrdDBFBKXMXuzmESk",
            "created": "2026-07-12 15:33:17",
            "modified": "2026-07-12 15:33:17",
        },
        {
            "title": "Step 2",
            "status": "incomplete",
            "stop_date": None,
            "type": "checklist-item",
            "uuid": "Wvt4DX8Rg5EP1Nb92aCPcU",
            "created": "2026-07-10 18:31:01",
            "modified": "2026-07-10 18:31:01",
        },
    ],
}

AREA = {
    "uuid": "EHLNwkURV152JLuYREfpyp",
    "type": "area",
    "title": "King",
}

TAG = {
    "uuid": "J8kZvzF4zv93W3Eb6c2vRU",
    "type": "tag",
    "title": "\U0001f44e",
    "shortcut": None,
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


class TestGetTodoById:
    """get_todo_by_id dispatches by things.get(uuid)'s `type` field."""

    @pytest.mark.asyncio
    async def test_to_do_without_checklist_dispatches_to_convert_todo(self, tools):
        """get_todo_by_id has always guaranteed a `checklist` list is present
        for to-do results, even when things.py omits the key entirely
        (no checklist) rather than emitting an empty list - see
        docs/UPGRADING.md."""
        with patch(GET_PATCH, return_value=dict(TODO)) as mock_get:
            result = await tools.get_todo_by_id(TODO["uuid"])

        mock_get.assert_called_once_with(TODO["uuid"])
        assert result["type"] == "to-do"
        assert result["uuid"] == TODO["uuid"]
        assert result["checklist"] == []
        assert "trashed" not in result

    @pytest.mark.asyncio
    async def test_to_do_with_checklist_normalizes_title_and_status_only(self, tools):
        """things.get() already embeds full checklist item dicts (include_items=True

        forced internally); get_todo_by_id normalizes each entry down to just
        {'title', 'status'} and does not call things.checklist_items() at all.
        """
        with patch(GET_PATCH, return_value=dict(TODO_WITH_CHECKLIST)) as mock_get, \
                patch("things_mcp.tools_helpers.read_operations.things.checklist_items") as mock_checklist:
            result = await tools.get_todo_by_id(TODO_WITH_CHECKLIST["uuid"])

        mock_get.assert_called_once_with(TODO_WITH_CHECKLIST["uuid"])
        mock_checklist.assert_not_called()
        assert result["type"] == "to-do"
        assert result["checklist"] == [
            {"title": "Step 1", "status": "completed"},
            {"title": "Step 2", "status": "incomplete"},
        ]

    @pytest.mark.asyncio
    async def test_project_dispatches_to_convert_project(self, tools):
        with patch(GET_PATCH, return_value=dict(PROJECT)) as mock_get:
            result = await tools.get_todo_by_id(PROJECT["uuid"])

        mock_get.assert_called_once_with(PROJECT["uuid"])
        assert result["type"] == "project"
        assert result["uuid"] == PROJECT["uuid"]
        assert result["areaTitle"] == "King"
        assert "trashed" not in result

    @pytest.mark.asyncio
    async def test_heading_dispatches_to_convert_todo(self, tools):
        with patch(GET_PATCH, return_value=dict(HEADING)) as mock_get:
            result = await tools.get_todo_by_id(HEADING["uuid"])

        mock_get.assert_called_once_with(HEADING["uuid"])
        assert result["type"] == "heading"
        assert result["uuid"] == HEADING["uuid"]
        assert result["projectTitle"] == "Complete Weekly Review"
        assert "trashed" not in result

    @pytest.mark.asyncio
    async def test_area_dispatches_to_convert_area(self, tools):
        with patch(GET_PATCH, return_value=dict(AREA)) as mock_get:
            result = await tools.get_todo_by_id(AREA["uuid"])

        mock_get.assert_called_once_with(AREA["uuid"])
        assert result["type"] == "area"
        assert result["uuid"] == AREA["uuid"]
        assert result["title"] == "King"
        assert "trashed" not in result

    @pytest.mark.asyncio
    async def test_tag_returns_structured_invalid_type_error(self, tools):
        with patch(GET_PATCH, return_value=dict(TAG)) as mock_get:
            result = await tools.get_todo_by_id(TAG["uuid"])

        mock_get.assert_called_once_with(TAG["uuid"])
        assert result["success"] is False
        assert result["error"] == "invalid_type"
        assert "tag" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_trashed_todo_resolves_with_trashed_flag(self, tools):
        with patch(GET_PATCH, return_value=dict(TRASHED_TODO)):
            result = await tools.get_todo_by_id(TRASHED_TODO["uuid"])

        assert result["type"] == "to-do"
        assert result["trashed"] is True

    @pytest.mark.asyncio
    async def test_unknown_id_raises_value_error(self, tools):
        with patch(GET_PATCH, return_value=None):
            with pytest.raises(ValueError, match="Todo not found"):
                await tools.get_todo_by_id("does-not-exist")
