"""Helper functions for Things 3 tools - conversion and utility methods."""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

from ..utils.applescript_utils import AppleScriptTemplates

logger = logging.getLogger(__name__)


class ToolsHelpers:
    """Helper methods for data conversion and utilities."""

    @staticmethod
    def escape_applescript_string(text: str) -> str:
        """Escape special characters in AppleScript strings.

        Delegates to `AppleScriptTemplates.escape_string()` (the single
        source of truth for AppleScript string escaping) so this and the
        AppleScriptTemplates escaper stay in sync. Newlines/carriage
        returns/tabs are escaped to their AppleScript literal escape
        sequences (\\n, \\r, \\t), not collapsed to spaces or dropped.

        Args:
            text: String to escape

        Returns:
            Escaped string safe for AppleScript, wrapped in double quotes
            (a complete AppleScript string literal). Callers that need to
            embed the escaped text inside a larger literal instead of
            using it as a standalone literal should call
            `AppleScriptTemplates.escape_string_inner()` directly rather
            than stripping the quotes from this return value.
        """
        return AppleScriptTemplates.escape_string(text)

    @staticmethod
    def convert_to_boolean(value: Any) -> Optional[bool]:
        """Convert various input formats to boolean.

        Args:
            value: Input value (bool, str, int, etc.)

        Returns:
            Boolean value or None

        Raises:
            ValueError: If value cannot be converted
        """
        if value is None or value == "":
            return None

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ['true', '1', 'yes', 'y']:
                return True
            elif value_lower in ['false', '0', 'no', 'n']:
                return False
            else:
                raise ValueError(f"Cannot convert '{value}' to boolean")

        if isinstance(value, (int, float)):
            return bool(value)

        raise ValueError(f"Cannot convert {type(value).__name__} to boolean")

    @staticmethod
    def convert_iso_to_applescript_date(iso_date: str) -> str:
        """Convert ISO date string to AppleScript-compatible format.

        Args:
            iso_date: ISO format date string (YYYY-MM-DD)

        Returns:
            AppleScript date string

        Raises:
            ValueError: If date format is invalid
        """
        try:
            # Parse ISO date
            dt = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
            # Format for AppleScript
            return dt.strftime('%B %d, %Y')
        except Exception as e:
            raise ValueError(f"Invalid ISO date format '{iso_date}': {e}")

    @staticmethod
    def convert_applescript_todo(todo: Dict) -> Dict:
        """Convert AppleScript todo format to MCP API format.

        Args:
            todo: Todo dict from AppleScript

        Returns:
            Converted todo dict in MCP format
        """
        # Map AppleScript 'open' status to 'incomplete'
        status = todo.get('status', 'open').lower()
        if status == 'open':
            status = 'incomplete'

        return {
            'uuid': todo.get('id'),
            'title': todo.get('name'),
            'notes': todo.get('notes'),
            'status': status,
            'tags': todo.get('tags', []),
            'creationDate': todo.get('creation_date'),
            'modificationDate': todo.get('modification_date'),
            'activationDate': todo.get('activation_date'),
            'dueDate': todo.get('due_date'),
            'hasReminder': todo.get('has_reminder', False),
            'reminderTime': todo.get('reminder_time')
        }

    @staticmethod
    def convert_todo(todo: Dict) -> Dict:
        """Convert things.py todo format to MCP API format.

        things.py's real to-do key set (captured live, 2026-08-19) is:
        uuid, type, title, status, notes, start, start_date, deadline,
        stop_date, created, modified, index, today_index, tags, project,
        project_title, heading, heading_title, checklist, reminder_time
        (optional - present on a small subset of rows, live: 8/1699 todos).
        Notably there is NO 'completion_date'/'cancellation_date'/'area' key
        on to-do rows - `stop_date` carries both, disambiguated by `status`.
        `checklist` (when present) is a bool "has a checklist" flag, not a
        list of items.

        Args:
            todo: Todo dict from things.py (uses snake_case field names). Also
                accepts pre-converted/mocked rows that already use MCP
                camelCase keys (e.g. some unit test fixtures) as a fallback.

        Returns:
            Converted todo dict in MCP format (uses camelCase field names).
            `heading`/`headingTitle` are always present (None when the todo
            isn't under a heading). `checklist` is only present as a list
            when real checklist items were fetched and merged in by the
            caller (e.g. read_operations include_items path) - convert_todo
            itself never emits a `checklist` list, only `hasChecklist` (bool).
        """
        status = todo.get('status')

        stop_date = todo.get('stop_date')
        completion_date = todo.get('completion_date', stop_date if status == 'completed' else None)
        cancellation_date = todo.get('cancellation_date', stop_date if status == 'canceled' else None)

        # 'checklist' from things.py is a bool "has checklist" flag. Some
        # callers (read_operations include_items path, and a few older test
        # mocks) pass a pre-fetched list of checklist item dicts instead -
        # preserve that as the `checklist` key rather than misreading it as
        # a bool via hasChecklist.
        raw_checklist = todo.get('checklist')
        checklist_items = raw_checklist if isinstance(raw_checklist, list) else None
        has_checklist = bool(raw_checklist)

        # things.py returns snake_case fields, we convert to camelCase
        converted = {
            'uuid': todo.get('uuid'),
            'title': todo.get('title'),
            'type': todo.get('type', 'to-do'),
            'notes': todo.get('notes'),
            'status': status,
            'tags': todo.get('tags', []),
            'start': todo.get('start'),  # Inbox | Anytime | Someday
            'creationDate': todo.get('created'),  # things.py: 'created'
            'modificationDate': todo.get('modified'),  # things.py: 'modified'
            'completionDate': completion_date,
            'cancellationDate': cancellation_date,
            'dueDate': todo.get('deadline'),  # things.py: 'deadline'
            'startDate': todo.get('start_date'),  # things.py: 'start_date'
            'project': todo.get('project'),
            'projectTitle': todo.get('project_title'),
            'heading': todo.get('heading'),
            'headingTitle': todo.get('heading_title'),
            'hasChecklist': has_checklist,
            'index': todo.get('index'),
            'todayIndex': todo.get('today_index'),
            'reminderTime': todo.get('reminder_time'),
        }
        if checklist_items is not None:
            converted['checklist'] = checklist_items

        # Marker added by Someday-project filtering: a task that things.py
        # reports as Anytime/other but that actually belongs to a Someday
        # project (see get_someday()). Only included when truthy.
        if todo.get('inherited_someday'):
            converted['inheritedSomeday'] = True

        # Remove None values, but keep heading/headingTitle/project/
        # projectTitle/start explicit (as None) so callers can rely on the
        # keys being present even for todos without a heading/project.
        always_present = {'heading', 'headingTitle', 'project', 'projectTitle', 'start'}
        return {
            k: v for k, v in converted.items()
            if v is not None or k in always_present
        }

    @staticmethod
    def convert_project(project: Dict) -> Dict:
        """Convert things.py project format to MCP API format.

        things.py project rows carry `stop_date` (not separate
        completion_date/cancellation_date keys), same as to-do rows -
        disambiguated by `status`. `area`/`area_title` are only present when
        the project actually belongs to an area. `reminderTime` is emitted
        the same way as on to-dos (things.py's `reminder_time`, present on a
        small subset of rows - live: 8/67 projects). `start`/`startDate`/
        `index`/`todayIndex` are emitted the same way convert_todo emits
        them for to-dos.

        Args:
            project: Project dict from things.py (uses snake_case field names)

        Returns:
            Converted project dict in MCP format (uses camelCase field names).
            `start` is always present (None when things.py doesn't supply
            it), matching convert_todo's always_present handling of the
            same field.
        """
        status = project.get('status')
        stop_date = project.get('stop_date')
        completion_date = project.get('completion_date', stop_date if status == 'completed' else None)
        cancellation_date = project.get('cancellation_date', stop_date if status == 'canceled' else None)

        # things.py returns snake_case fields, we convert to camelCase
        converted = {
            'uuid': project.get('uuid'),
            'title': project.get('title'),
            'type': project.get('type', 'project'),
            'notes': project.get('notes'),
            'status': status,
            'tags': project.get('tags', []),
            'area': project.get('area'),
            'areaTitle': project.get('area_title'),
            'start': project.get('start'),  # Inbox | Anytime | Someday
            'creationDate': project.get('created'),  # things.py: 'created'
            'modificationDate': project.get('modified'),  # things.py: 'modified'
            'completionDate': completion_date,
            'cancellationDate': cancellation_date,
            'dueDate': project.get('deadline'),  # things.py: 'deadline'
            'startDate': project.get('start_date'),  # things.py: 'start_date'
            'index': project.get('index'),
            'todayIndex': project.get('today_index'),
            'reminderTime': project.get('reminder_time'),
        }

        # Remove None values, but keep 'start' explicit (as None) so callers
        # can rely on the key being present, matching convert_todo's
        # always_present handling of the same field.
        always_present = {'start'}
        return {
            k: v for k, v in converted.items()
            if v is not None or k in always_present
        }

    @staticmethod
    def convert_area(area: Dict) -> Dict:
        """Convert things.py area format to MCP API format.

        Live things.py area rows never carry a `tags` key - verified against
        4/4 real areas, including with `things.areas(include_items=True)`
        (which adds an unrelated `items` key, not `tags`). So this lookup is
        currently always a no-op default (`[]`) on the read side, even though
        areas *can* be tagged via `add_area(tags=...)`/`update_area(tags=...)`
        (write side, via AppleScript) - things.py just doesn't expose area
        tags back out. Kept (rather than dropped) so the `tags` key stays
        present and callers get `[]` instead of a missing key; revisit if
        things.py ever starts returning area tags.

        Args:
            area: Area dict from things.py

        Returns:
            Converted area dict in MCP format
        """
        return {
            'uuid': area.get('uuid'),
            'title': area.get('title'),
            'type': area.get('type', 'area'),
            'tags': area.get('tags', [])
        }

    @staticmethod
    def parse_period_to_days(period: str) -> int:
        """Parse period string (e.g., '7d', '2w') to number of days.

        Args:
            period: Period string like '3d', '1w', '2m', '1y'

        Returns:
            Number of days

        Raises:
            ValueError: If period format is invalid
        """
        if not period or len(period) < 2:
            raise ValueError(f"Invalid period format: '{period}'")

        unit = period[-1].lower()
        try:
            value = int(period[:-1])
        except ValueError:
            raise ValueError(f"Invalid period value: '{period}'")

        if unit == 'd':
            return value
        elif unit == 'w':
            return value * 7
        elif unit == 'm':
            return value * 30  # Approximate
        elif unit == 'y':
            return value * 365  # Approximate
        else:
            raise ValueError(f"Invalid period unit: '{unit}' (use d/w/m/y)")
