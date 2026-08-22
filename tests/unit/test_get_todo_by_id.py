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
from unittest.mock import patch, call

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
        # Headings get a one-hop transitive-trashed check against their own
        # project (hq-wsa.7), so things.get() is called twice: once for the
        # heading itself, once for its project (`item['project']`).
        with patch(GET_PATCH, return_value=dict(HEADING)) as mock_get:
            result = await tools.get_todo_by_id(HEADING["uuid"])

        assert mock_get.call_args_list == [
            call(HEADING["uuid"]),
            call(HEADING["project"]),
        ]
        assert result["type"] == "heading"
        assert result["uuid"] == HEADING["uuid"]
        assert result["projectTitle"] == "Complete Weekly Review"
        assert "trashed" not in result
        assert "trashedViaParent" not in result

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


START_BUCKET_PATCH = (
    "things_mcp.tools_helpers.read_operations.ReadOperations._read_start_bucket"
)


class TestGetTodoByIdEveningField:
    """get_todo_by_id detects This Evening scheduling via a narrow, read-only
    raw-SQL side channel (TMTask.startBucket), since things.py's own SELECT
    never exposes it (hq-wsa.9). `_read_start_bucket` itself is mocked here -
    its own sqlite access is exercised live in tests/regression."""

    @pytest.mark.asyncio
    async def test_start_bucket_one_reports_evening_true(self, tools):
        assert TODO.get("start_date")  # sanity: fixture has a start_date
        with patch(GET_PATCH, return_value=dict(TODO)), \
                patch(START_BUCKET_PATCH, return_value=1) as mock_bucket:
            result = await tools.get_todo_by_id(TODO["uuid"])

        mock_bucket.assert_called_once_with(TODO["uuid"])
        assert result["evening"] is True

    @pytest.mark.asyncio
    async def test_start_bucket_zero_omits_evening_key(self, tools):
        with patch(GET_PATCH, return_value=dict(TODO)), \
                patch(START_BUCKET_PATCH, return_value=0) as mock_bucket:
            result = await tools.get_todo_by_id(TODO["uuid"])

        mock_bucket.assert_called_once_with(TODO["uuid"])
        assert "evening" not in result

    @pytest.mark.asyncio
    async def test_helper_raising_omits_evening_key_but_lookup_succeeds(self, tools):
        with patch(GET_PATCH, return_value=dict(TODO)), \
                patch(START_BUCKET_PATCH, side_effect=RuntimeError("db locked")) as mock_bucket:
            result = await tools.get_todo_by_id(TODO["uuid"])

        mock_bucket.assert_called_once_with(TODO["uuid"])
        assert "evening" not in result
        assert result["uuid"] == TODO["uuid"]

    @pytest.mark.asyncio
    async def test_no_start_date_skips_helper_entirely(self, tools):
        todo_no_start_date = {**TODO, "start_date": None}
        with patch(GET_PATCH, return_value=dict(todo_no_start_date)), \
                patch(START_BUCKET_PATCH) as mock_bucket:
            result = await tools.get_todo_by_id(todo_no_start_date["uuid"])

        mock_bucket.assert_not_called()
        assert "evening" not in result

    @pytest.mark.asyncio
    async def test_project_never_calls_helper(self, tools):
        with patch(GET_PATCH, return_value=dict(PROJECT)), \
                patch(START_BUCKET_PATCH) as mock_bucket:
            result = await tools.get_todo_by_id(PROJECT["uuid"])

        mock_bucket.assert_not_called()
        assert "evening" not in result

    @pytest.mark.asyncio
    async def test_area_never_calls_helper(self, tools):
        with patch(GET_PATCH, return_value=dict(AREA)), \
                patch(START_BUCKET_PATCH) as mock_bucket:
            result = await tools.get_todo_by_id(AREA["uuid"])

        mock_bucket.assert_not_called()
        assert "evening" not in result

    @pytest.mark.asyncio
    async def test_heading_never_calls_helper(self, tools):
        # Headings dispatch through convert_todo but are excluded from the
        # evening check by the item_type == 'to-do' guard.
        with patch(GET_PATCH, return_value=dict(HEADING)), \
                patch(START_BUCKET_PATCH) as mock_bucket:
            result = await tools.get_todo_by_id(HEADING["uuid"])

        mock_bucket.assert_not_called()
        assert "evening" not in result


class TestGetTodoByIdTransitiveTrashed:
    """get_todo_by_id resolves trashed state transitively through a to-do's
    or heading's containing project (hq-wsa.7). Things marks only the
    trashed container itself, so a child of a trashed project carries no
    trashed key of its own - without this hop a consumer would conclude
    the child is live when it's actually unreachable. Direct trash (the
    item's own `trashed` column) still takes precedence and is reported
    without `trashedViaParent`."""

    @pytest.mark.asyncio
    async def test_child_of_trashed_project_reports_trashed_via_parent(self, tools):
        todo = {**TODO, "project": PROJECT["uuid"]}
        trashed_project = {**PROJECT, "trashed": True}

        def fake_get(uuid):
            if uuid == todo["uuid"]:
                return dict(todo)
            if uuid == PROJECT["uuid"]:
                return dict(trashed_project)
            raise AssertionError(f"unexpected things.get({uuid!r})")

        with patch(GET_PATCH, side_effect=fake_get):
            result = await tools.get_todo_by_id(todo["uuid"])

        assert result["trashed"] is True
        assert result["trashedViaParent"] is True

    @pytest.mark.asyncio
    async def test_heading_child_of_trashed_project_reports_trashed_via_parent(self, tools):
        # Two-hop case: to-do -> heading (no project of its own) -> project.
        todo = {**TODO, "heading": HEADING["uuid"], "project": None}
        heading = dict(HEADING)  # HEADING["project"] already points at a project uuid
        trashed_project = {**PROJECT, "uuid": HEADING["project"], "trashed": True}

        def fake_get(uuid):
            if uuid == todo["uuid"]:
                return dict(todo)
            if uuid == HEADING["uuid"]:
                return dict(heading)
            if uuid == HEADING["project"]:
                return dict(trashed_project)
            raise AssertionError(f"unexpected things.get({uuid!r})")

        with patch(GET_PATCH, side_effect=fake_get):
            result = await tools.get_todo_by_id(todo["uuid"])

        assert result["trashed"] is True
        assert result["trashedViaParent"] is True

    @pytest.mark.asyncio
    async def test_child_of_live_project_reports_neither_key(self, tools):
        todo = {**TODO, "project": PROJECT["uuid"]}
        live_project = dict(PROJECT)  # trashed omitted/falsy

        def fake_get(uuid):
            if uuid == todo["uuid"]:
                return dict(todo)
            if uuid == PROJECT["uuid"]:
                return dict(live_project)
            raise AssertionError(f"unexpected things.get({uuid!r})")

        with patch(GET_PATCH, side_effect=fake_get):
            result = await tools.get_todo_by_id(todo["uuid"])

        assert "trashed" not in result
        assert "trashedViaParent" not in result

    @pytest.mark.asyncio
    async def test_direct_trashed_todo_keeps_current_shape_even_with_trashed_parent(self, tools):
        # Direct trash (item's own `trashed` column) is reported without
        # trashedViaParent, and short-circuits before the container hop.
        todo = {**TRASHED_TODO, "project": PROJECT["uuid"]}

        with patch(GET_PATCH, return_value=dict(todo)) as mock_get:
            result = await tools.get_todo_by_id(todo["uuid"])

        mock_get.assert_called_once_with(todo["uuid"])
        assert result["trashed"] is True
        assert "trashedViaParent" not in result

    @pytest.mark.asyncio
    async def test_container_lookup_raises_omits_both_keys_but_lookup_succeeds(self, tools):
        todo = {**TODO, "project": PROJECT["uuid"]}

        def fake_get(uuid):
            if uuid == todo["uuid"]:
                return dict(todo)
            raise RuntimeError("Things database is unreadable")

        with patch(GET_PATCH, side_effect=fake_get):
            result = await tools.get_todo_by_id(todo["uuid"])

        assert result["uuid"] == todo["uuid"]
        assert "trashed" not in result
        assert "trashedViaParent" not in result
