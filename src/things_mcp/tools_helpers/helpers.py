"""Helper functions for Things 3 tools - conversion and utility methods."""

import logging
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ToolsHelpers:
    """Helper methods for data conversion and utilities."""

    @staticmethod
    def escape_applescript_string(text: str) -> str:
        """Escape special characters in AppleScript strings.

        Args:
            text: String to escape

        Returns:
            Escaped string safe for AppleScript
        """
        # Escape backslashes first
        text = text.replace('\\', '\\\\')
        # Escape quotes
        text = text.replace('"', '\\"')
        # Return wrapped in quotes
        return f'"{text}"'

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

        Args:
            todo: Todo dict from things.py (uses snake_case field names)

        Returns:
            Converted todo dict in MCP format (uses camelCase field names)
        """
        # things.py returns snake_case fields, we convert to camelCase
        converted = {
            'uuid': todo.get('uuid'),
            'title': todo.get('title'),
            'notes': todo.get('notes'),
            'status': todo.get('status'),
            'tags': todo.get('tags', []),
            'creationDate': todo.get('created'),  # things.py: 'created'
            'modificationDate': todo.get('modified'),  # things.py: 'modified'
            'completionDate': todo.get('completion_date'),  # things.py: 'completion_date'
            'cancellationDate': todo.get('cancellation_date'),  # things.py: 'cancellation_date'
            'dueDate': todo.get('deadline'),  # things.py: 'deadline'
            'startDate': todo.get('start_date'),  # things.py: 'start_date'
            'project': todo.get('project'),
            'area': todo.get('area'),
            'checklist': todo.get('checklist', []) if 'checklist' in todo else None
        }

        # Remove None values to keep response clean
        return {k: v for k, v in converted.items() if v is not None}

    @staticmethod
    def convert_project(project: Dict) -> Dict:
        """Convert things.py project format to MCP API format.

        Args:
            project: Project dict from things.py (uses snake_case field names)

        Returns:
            Converted project dict in MCP format (uses camelCase field names)
        """
        # things.py returns snake_case fields, we convert to camelCase
        converted = {
            'uuid': project.get('uuid'),
            'title': project.get('title'),
            'notes': project.get('notes'),
            'status': project.get('status'),
            'tags': project.get('tags', []),
            'area': project.get('area'),
            'creationDate': project.get('created'),  # things.py: 'created'
            'modificationDate': project.get('modified'),  # things.py: 'modified'
            'completionDate': project.get('completion_date'),  # things.py: 'completion_date'
            'cancellationDate': project.get('cancellation_date'),  # things.py: 'cancellation_date'
            'dueDate': project.get('deadline')  # things.py: 'deadline'
        }

        # Remove None values
        return {k: v for k, v in converted.items() if v is not None}

    @staticmethod
    def convert_area(area: Dict) -> Dict:
        """Convert things.py area format to MCP API format.

        Args:
            area: Area dict from things.py

        Returns:
            Converted area dict in MCP format
        """
        return {
            'uuid': area.get('uuid'),
            'title': area.get('title'),
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
