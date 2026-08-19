"""Tests for ToolsHelpers.convert_todo / convert_project / convert_area against
the real things.py key set (hq-f0w.4).

Fixtures below are anonymised copies of rows captured live via things.py on
2026-08-19 (`things.todos()`, `things.todos(status='completed')`,
`things.todos(status='canceled')`, `things.projects()`, `things.areas()`,
`things.tags()`, `things.tasks(type='heading')`, plus rows with 'heading',
'project', and 'checklist' keys found by scanning things.todos()). Real
things.py to-do rows never carry 'completion_date'/'cancellation_date'/'area'
keys - only 'stop_date', disambiguated by 'status'. 'checklist' (when
present) is a bool "has a checklist" flag, not a list of items. Areas never
carry a 'tags' key.
"""

import pytest

from things_mcp.tools_helpers.helpers import ToolsHelpers


# --- Fixtures captured from a real things.py database (2026-08-19) ---------

INCOMPLETE_TODO_SOMEDAY = {
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

COMPLETED_TODO = {
    "uuid": "3LAF1Qg21rUfPkCVg356Ts",
    "type": "to-do",
    "title": "Setup time with someone",
    "status": "completed",
    "notes": "",
    "tags": ["Alexis", "Todd"],
    "start": "Anytime",
    "start_date": "2026-06-11",
    "deadline": None,
    "stop_date": "2026-07-25 18:38:32",
    "created": "2026-06-11 11:46:11",
    "modified": "2026-07-25 18:38:32",
    "index": -2758935,
    "today_index": 0,
}

CANCELED_TODO = {
    "uuid": "SeXraakXboAhuNDHVQ3MNd",
    "type": "to-do",
    "title": "REGRESSION_TEST: Project Todo 2",
    "status": "canceled",
    "notes": "Second project todo",
    "start": "Inbox",
    "start_date": None,
    "deadline": None,
    "stop_date": "2025-10-04 22:24:04",
    "created": "2025-10-04 21:09:48",
    "modified": "2025-10-04 22:24:04",
    "index": -2724269,
    "today_index": 0,
    # Note: no 'tags' key at all when a todo has no tags.
}

TODO_WITH_HEADING = {
    "uuid": "WMVVPmqvWnmbMXsZ8GPdER",
    "type": "to-do",
    "title": "Look at Calendar for the past 2 weeks",
    "status": "incomplete",
    "heading": "6PsfVfwwHh8vD3jNXcwgsJ",
    "heading_title": "Review Calendar",
    "notes": "",
    "tags": ["Short Dashes"],
    "start": "Anytime",
    "start_date": None,
    "deadline": None,
    "stop_date": None,
    "created": "2017-09-03 21:38:20",
    "modified": "2017-09-03 21:38:20",
    "index": -417,
    "today_index": 0,
}

TODO_WITH_PROJECT_AND_CHECKLIST = {
    "uuid": "DVMkWtfMd4MMxCByJ7go9z",
    "type": "to-do",
    "title": "Activate a marketing campaign",
    "status": "incomplete",
    "project": "NoTumK4NCMpx25j5gDSkY1",
    "project_title": "Marketing",
    "notes": "Some steps here",
    "start": "Anytime",
    "checklist": True,
    "start_date": "2026-03-22",
    "deadline": None,
    "stop_date": None,
    "created": "2026-03-22 10:20:28",
    "modified": "2026-03-22 10:22:43",
    "index": -2758333,
    "today_index": -428,
}

PROJECT_WITH_AREA = {
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

COMPLETED_PROJECT = {
    "uuid": "K69SjpxeBgdBx7P69xwEJH",
    "type": "project",
    "title": "Keel",
    "status": "completed",
    "notes": "",
    "start": "Anytime",
    "start_date": None,
    "deadline": None,
    "stop_date": "2026-06-01 12:00:00",
    "created": "2026-05-03 20:24:23",
    "modified": "2026-06-01 12:00:00",
    "index": -127790,
    "today_index": 0,
}

AREA = {
    "uuid": "EHLNwkURV152JLuYREfpyp",
    "type": "area",
    "title": "King",
    # No 'tags' key - real things.py areas never carry one, even with
    # things.areas(include_items=True) (verified live, 4/4 areas).
}

TAG = {
    "uuid": "J8kZvzF4zv93W3Eb6c2vRU",
    "type": "tag",
    "title": "some-tag",
    "shortcut": None,
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


class TestConvertTodo:
    """convert_todo against realistic things.py rows."""

    def test_incomplete_someday_todo_has_required_keys(self):
        converted = ToolsHelpers.convert_todo(INCOMPLETE_TODO_SOMEDAY)

        assert converted["uuid"] == "LSGhTn44NpEsZphcNuMQcM"
        assert converted["title"] == "Send a doc to advisors"
        assert converted["type"] == "to-do"
        assert converted["status"] == "incomplete"
        assert converted["start"] == "Someday"
        assert converted["startDate"] == "2026-08-08"
        assert converted["tags"] == ["work-tag"]
        assert converted["hasChecklist"] is False
        assert converted["index"] == -2764421
        assert converted["todayIndex"] == -898
        # No stop_date -> no completion/cancellation date.
        assert "completionDate" not in converted
        assert "cancellationDate" not in converted
        # heading/headingTitle/project/projectTitle keys always present,
        # even when None, for todos not under a heading/project.
        assert converted["heading"] is None
        assert converted["headingTitle"] is None
        assert converted["project"] is None
        assert converted["projectTitle"] is None

    def test_completed_todo_derives_completion_date_from_stop_date(self):
        converted = ToolsHelpers.convert_todo(COMPLETED_TODO)

        assert converted["status"] == "completed"
        assert converted["completionDate"] == "2026-07-25 18:38:32"
        assert "cancellationDate" not in converted
        assert converted["tags"] == ["Alexis", "Todd"]

    def test_canceled_todo_derives_cancellation_date_from_stop_date(self):
        converted = ToolsHelpers.convert_todo(CANCELED_TODO)

        assert converted["status"] == "canceled"
        assert converted["cancellationDate"] == "2025-10-04 22:24:04"
        assert "completionDate" not in converted
        # No 'tags' key on the input row -> defaults to empty list, then
        # stripped by the None-filter (empty list is falsy but not None,
        # so it stays as []).
        assert converted["tags"] == []

    def test_todo_under_heading_carries_heading_title(self):
        converted = ToolsHelpers.convert_todo(TODO_WITH_HEADING)

        assert converted["heading"] == "6PsfVfwwHh8vD3jNXcwgsJ"
        assert converted["headingTitle"] == "Review Calendar"
        assert converted["project"] is None
        assert converted["projectTitle"] is None

    def test_todo_with_project_and_checklist_flag(self):
        converted = ToolsHelpers.convert_todo(TODO_WITH_PROJECT_AND_CHECKLIST)

        assert converted["project"] == "NoTumK4NCMpx25j5gDSkY1"
        assert converted["projectTitle"] == "Marketing"
        # things.py 'checklist': True -> hasChecklist bool, no 'checklist'
        # list key (no real items were fetched).
        assert converted["hasChecklist"] is True
        assert "checklist" not in converted

    def test_checklist_items_list_preserved_when_pre_fetched(self):
        """Callers (e.g. read_operations include_items path) merge in a real
        checklist item list after convert_todo runs, but convert_todo itself
        must not clobber/misinterpret an already-list-shaped 'checklist'
        input (defensive - also covers legacy test mocks)."""
        row = dict(TODO_WITH_PROJECT_AND_CHECKLIST)
        row["checklist"] = [
            {"title": "Item 1", "status": "incomplete"},
            {"title": "Item 2", "status": "completed"},
        ]

        converted = ToolsHelpers.convert_todo(row)

        assert converted["checklist"] == row["checklist"]
        assert converted["hasChecklist"] is True

    def test_rows_missing_start_default_to_none(self):
        """Rows lacking 'start' (e.g. minimal unit test mocks) -> None,
        but the key is still present."""
        converted = ToolsHelpers.convert_todo({"uuid": "x", "title": "t"})

        assert converted["start"] is None
        assert converted["type"] == "to-do"
        assert converted["hasChecklist"] is False

    def test_project_row_passed_through_convert_todo_keeps_type_project(self):
        """When include_projects=True (hq-f0w.3), projects flow through
        convert_todo alongside to-dos in list results - type must be
        preserved as 'project' so callers can distinguish them."""
        converted = ToolsHelpers.convert_todo(PROJECT_WITH_AREA)

        assert converted["type"] == "project"
        assert converted["uuid"] == "HpXrCLPoB4nJwr2Uikjto8"

    def test_inherited_someday_marker_preserved(self):
        row = dict(INCOMPLETE_TODO_SOMEDAY)
        row["inherited_someday"] = True

        converted = ToolsHelpers.convert_todo(row)

        assert converted["inheritedSomeday"] is True


class TestConvertProject:
    """convert_project against realistic things.py rows."""

    def test_project_with_area(self):
        converted = ToolsHelpers.convert_project(PROJECT_WITH_AREA)

        assert converted["uuid"] == "HpXrCLPoB4nJwr2Uikjto8"
        assert converted["type"] == "project"
        assert converted["area"] == "EHLNwkURV152JLuYREfpyp"
        assert converted["areaTitle"] == "King"
        assert converted["status"] == "incomplete"
        assert "completionDate" not in converted
        assert "cancellationDate" not in converted

    def test_project_emits_start_startDate_index_todayIndex(self):
        """convert_project emits start/startDate/index/todayIndex the same
        way convert_todo emits them for to-dos (hq-f0w.29)."""
        converted = ToolsHelpers.convert_project(PROJECT_WITH_AREA)

        assert converted["start"] == "Someday"
        assert "startDate" not in converted  # PROJECT_WITH_AREA's start_date is None
        assert converted["index"] == -99972
        assert converted["todayIndex"] == 0

        row_with_start_date = dict(PROJECT_WITH_AREA)
        row_with_start_date["start_date"] = "2026-01-01"
        converted_with_start_date = ToolsHelpers.convert_project(row_with_start_date)
        assert converted_with_start_date["startDate"] == "2026-01-01"

    def test_project_reminder_time_is_emitted_as_reminderTime(self):
        """things.py emits 'reminder_time' on a small subset of project rows
        (live: 8/67 projects, e.g. '09:00') and convert_project surfaces it
        as 'reminderTime' (hq-f0w.29)."""
        row = dict(PROJECT_WITH_AREA)
        row["reminder_time"] = "09:00"

        converted = ToolsHelpers.convert_project(row)

        assert converted["reminderTime"] == "09:00"

    def test_project_missing_start_defaults_to_none_but_key_present(self):
        """Rows lacking 'start' -> None, but the key is still present,
        matching convert_todo's always_present handling of 'start'."""
        converted = ToolsHelpers.convert_project({"uuid": "x", "title": "t"})

        assert converted["start"] is None
        assert "reminderTime" not in converted

    def test_completed_project_derives_completion_date(self):
        converted = ToolsHelpers.convert_project(COMPLETED_PROJECT)

        assert converted["status"] == "completed"
        assert converted["completionDate"] == "2026-06-01 12:00:00"
        assert "cancellationDate" not in converted
        # No area on this project -> key omitted (None stripped).
        assert "area" not in converted
        assert "areaTitle" not in converted


class TestConvertArea:
    """convert_area against realistic things.py rows."""

    def test_area_basic_fields(self):
        converted = ToolsHelpers.convert_area(AREA)

        assert converted["uuid"] == "EHLNwkURV152JLuYREfpyp"
        assert converted["title"] == "King"
        assert converted["type"] == "area"
        # tags key stays present, defaulting to [] - things.py never
        # supplies area tags on the read side (verified live).
        assert converted["tags"] == []
