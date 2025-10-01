"""
State machine-based parser for AppleScript output.

This module replaces the string manipulation approach with a proper state machine
that correctly handles:
- Quoted strings with embedded commas and colons
- Nested lists with braces {}
- Complex date formats with commas
- Tag names with special characters
- Field boundaries and record separators

Format: key1:value1, key2:value2, key3:{list, items}, key1:value3, key2:value4
Records are separated by repeated 'id:' keys.
"""

import re
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ParserState(Enum):
    """Parser states for the state machine."""
    FIELD = "field"           # Reading a field name (before colon)
    VALUE = "value"           # Reading a simple value (after colon)
    QUOTED = "quoted"         # Inside a quoted string
    LIST = "list"             # Inside a list (braces)
    LIST_QUOTED = "list_quoted"  # Inside quoted string within list


class AppleScriptParser:
    """
    State machine parser for AppleScript record output.

    Parses AppleScript output format:
    id:todo1, name:First Todo, notes:Notes 1, status:open, id:todo2, name:Second Todo

    Features:
    - Proper state machine eliminates need for placeholder escaping
    - Handles nested braces and quotes correctly
    - Preserves commas and special characters in values
    - Detects record boundaries by 'id' field repetition
    """

    # Known date fields that require special parsing
    DATE_FIELDS = {
        'creation_date', 'modification_date', 'due_date',
        'start_date', 'completion_date', 'cancellation_date',
        'activation_date'
    }

    # Month names for date parsing
    MONTH_NAMES = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }

    def __init__(self):
        """Initialize the parser."""
        self.reset()

    def reset(self):
        """Reset parser state."""
        self.state = ParserState.FIELD
        self.current_field = ""
        self.current_value = ""
        self.current_record = {}
        self.records = []
        self.brace_depth = 0
        self.in_quotes = False

    def parse(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse AppleScript output into list of records.

        Args:
            output: Raw AppleScript output string

        Returns:
            List of dictionaries, one per record

        Raises:
            ValueError: If output is empty or cannot be parsed
        """
        if not output or not output.strip():
            logger.warning("AppleScript returned empty output")
            return []

        logger.debug(f"Parsing AppleScript output: {output[:200]}...")

        self.reset()

        try:
            # Process character by character through state machine
            for char in output:
                self._process_char(char)

            # Finalize any remaining field and record
            self._finalize_field()
            self._finalize_record()

            logger.debug(f"Successfully parsed {len(self.records)} records")
            return self.records

        except Exception as e:
            logger.error(f"Error parsing AppleScript output: {e}")
            logger.debug(f"Problematic output: {output[:500]}...")

            # Return partial results if we have any
            if self.records:
                logger.warning(f"Returning {len(self.records)} partial records despite error")
                return self.records

            raise ValueError(f"Failed to parse AppleScript output: {e}") from e

    def _process_char(self, char: str):
        """Process a single character through the state machine."""

        if self.state == ParserState.FIELD:
            self._process_field_char(char)
        elif self.state == ParserState.VALUE:
            self._process_value_char(char)
        elif self.state == ParserState.QUOTED:
            self._process_quoted_char(char)
        elif self.state == ParserState.LIST:
            self._process_list_char(char)
        elif self.state == ParserState.LIST_QUOTED:
            self._process_list_quoted_char(char)

    def _process_field_char(self, char: str):
        """Process character in FIELD state."""
        if char == ':':
            # Transition to VALUE state
            self.current_field = self.current_field.strip()
            self.state = ParserState.VALUE
        elif char == ',':
            # Comma without colon - skip (shouldn't happen in well-formed output)
            pass
        else:
            self.current_field += char

    def _process_value_char(self, char: str):
        """Process character in VALUE state."""
        if char == '"':
            # Entering quoted string
            self.in_quotes = True
            self.state = ParserState.QUOTED
            # Don't include the opening quote
        elif char == '{':
            # Entering list
            self.brace_depth = 1
            self.state = ParserState.LIST
            # Don't include the opening brace
        elif char == ',' and not self.in_quotes and self.brace_depth == 0:
            # Check if this might be part of a date value
            # Date fields containing commas should not be split here
            # Date format: "Monday, January 15, 2024 at 2:30:00 PM"
            # We need to be smart: if we see " at " or ", 2" (comma-space-digit)
            # it's likely part of a date
            if self.current_field in self.DATE_FIELDS and self.current_value.strip():
                # Check if this looks like it's still in the middle of a date
                # by looking ahead in the buffer (we can't, so use heuristics)
                # Date pattern: we expect either:
                # 1. ", <number>" for day/year
                # 2. " at " coming soon
                # If we just saw a month name or day name, keep the comma
                value_lower = self.current_value.strip().lower()
                month_names = ['january', 'february', 'march', 'april', 'may', 'june',
                              'july', 'august', 'september', 'october', 'november', 'december']
                day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

                # Check if we just completed a day or month name
                words = value_lower.split()
                if words and (words[-1] in day_names or words[-1] in month_names):
                    # Keep this comma, it's part of the date
                    self.current_value += char
                # Or if the value contains "at" already (we're past the time portion)
                elif ' at ' in value_lower and (':' in value_lower or 'am' in value_lower or 'pm' in value_lower):
                    # We've seen the "at HH:MM" part, next comma ends the field
                    self._finalize_field()
                    self.state = ParserState.FIELD
                else:
                    # Keep the comma, we're still in the date
                    self.current_value += char
            else:
                # End of this field, start of next field
                self._finalize_field()
                self.state = ParserState.FIELD
        else:
            self.current_value += char

    def _process_quoted_char(self, char: str):
        """Process character in QUOTED state."""
        if char == '"' and self.in_quotes:
            # End of quoted string
            self.in_quotes = False
            self.state = ParserState.VALUE
            # Don't include the closing quote
        else:
            # Include everything inside quotes, even commas and colons
            self.current_value += char

    def _process_list_char(self, char: str):
        """Process character in LIST state."""
        if char == '"':
            # Entering quoted string within list
            self.in_quotes = True
            self.state = ParserState.LIST_QUOTED
            self.current_value += char  # Keep quotes in list items
        elif char == '{':
            self.brace_depth += 1
            self.current_value += char
        elif char == '}':
            self.brace_depth -= 1
            if self.brace_depth == 0:
                # End of list
                self.state = ParserState.VALUE
            else:
                self.current_value += char
        else:
            self.current_value += char

    def _process_list_quoted_char(self, char: str):
        """Process character in LIST_QUOTED state."""
        self.current_value += char
        if char == '"' and self.in_quotes:
            # End of quoted string within list
            self.in_quotes = False
            self.state = ParserState.LIST

    def _finalize_field(self):
        """Finalize current field and add to record."""
        if not self.current_field:
            return

        field_name = self.current_field.strip()
        value = self.current_value.strip()

        # Check if this is a new record (repeated 'id' field)
        if field_name == 'id' and 'id' in self.current_record:
            # Save current record and start new one
            self._finalize_record()

        # Parse the value based on field type
        parsed_value = self._parse_value(field_name, value)
        self.current_record[field_name] = parsed_value

        # Reset for next field
        self.current_field = ""
        self.current_value = ""

    def _finalize_record(self):
        """Finalize current record and add to results."""
        if self.current_record:
            self.records.append(self.current_record)
            self.current_record = {}

    def _parse_value(self, field_name: str, value: str) -> Any:
        """
        Parse a value based on its field name.

        Args:
            field_name: Name of the field
            value: Raw string value

        Returns:
            Parsed value (str, list, None, etc.)
        """
        # Handle tag_names field FIRST (before empty check)
        # because empty list {} should return [], not None
        if field_name == 'tag_names':
            tags = self._parse_tags(value)
            return tags

        # Check if value is a list format (contains quotes and commas from LIST state)
        # This handles generic list fields like "tags"
        if value and ('"' in value or (value.count(',') > 0 and not value.strip().replace(',', '').replace(' ', ''))):
            # Looks like a list - parse it
            return self._parse_tags(value)

        # Handle missing value and empty strings
        if value == 'missing value' or value == '':
            return None

        # Handle date fields
        if field_name in self.DATE_FIELDS:
            return self._parse_date(value)

        # Return cleaned string value
        return value

    def _parse_date(self, date_str: str) -> Optional[str]:
        """
        Parse AppleScript date format to ISO string.

        Handles formats like:
        - "Monday, January 1, 2024 at 12:00:00 PM"
        - "Thursday, 4. September 2025 at 00:00:00"
        - "date Monday, January 1, 2024..."

        Args:
            date_str: Raw date string from AppleScript

        Returns:
            ISO format date string or None
        """
        try:
            # Remove 'date' prefix if present
            cleaned = date_str.strip()
            if cleaned.startswith('date'):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]

            if not cleaned or cleaned == 'missing value':
                return None

            # Try different date patterns
            patterns = [
                # European format: "Thursday, 4. September 2025 at 00:00:00"
                (r'^(\w+),\s+(\d+)\.\s+(\w+)\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})$', 'european_24h'),
                # US format with AM/PM: "Monday, January 1, 2024 at 12:00:00 PM"
                (r'^(\w+),\s+(\w+)\s+(\d+),\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)$', 'us_ampm'),
                # Without day of week: "January 1, 2024 at 12:00:00 PM"
                (r'^(\w+)\s+(\d+),\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)$', 'us_ampm_no_dow'),
                # Date only: "January 1, 2024"
                (r'^(\w+)\s+(\d+),\s+(\d{4})$', 'date_only'),
                # ISO format: "2024-01-01 12:00:00" or "2024-01-01"
                (r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}):(\d{2}))?$', 'iso'),
            ]

            for pattern, format_type in patterns:
                match = re.match(pattern, cleaned, re.IGNORECASE)
                if match:
                    groups = match.groups()

                    if format_type == 'european_24h':
                        _, day, month_str, year, hour, minute, second = groups
                        month = self.MONTH_NAMES.get(month_str.lower())
                        if month:
                            dt = datetime(int(year), month, int(day),
                                        int(hour), int(minute), int(second))
                            return dt.isoformat()

                    elif format_type == 'us_ampm':
                        _, month_str, day, year, hour, minute, second, ampm = groups
                        month = self.MONTH_NAMES.get(month_str.lower())
                        if month:
                            hour = int(hour)
                            if ampm.upper() == 'PM' and hour != 12:
                                hour += 12
                            elif ampm.upper() == 'AM' and hour == 12:
                                hour = 0
                            dt = datetime(int(year), month, int(day),
                                        hour, int(minute), int(second))
                            return dt.isoformat()

                    elif format_type == 'us_ampm_no_dow':
                        month_str, day, year, hour, minute, second, ampm = groups
                        month = self.MONTH_NAMES.get(month_str.lower())
                        if month:
                            hour = int(hour)
                            if ampm.upper() == 'PM' and hour != 12:
                                hour += 12
                            elif ampm.upper() == 'AM' and hour == 12:
                                hour = 0
                            dt = datetime(int(year), month, int(day),
                                        hour, int(minute), int(second))
                            return dt.isoformat()

                    elif format_type == 'date_only':
                        month_str, day, year = groups
                        month = self.MONTH_NAMES.get(month_str.lower())
                        if month:
                            dt = datetime(int(year), month, int(day))
                            return dt.date().isoformat()

                    elif format_type == 'iso':
                        if groups[3]:  # Has time component
                            year, month, day, hour, minute, second = groups
                            dt = datetime(int(year), int(month), int(day),
                                        int(hour), int(minute), int(second))
                            return dt.isoformat()
                        else:  # Date only
                            year, month, day = groups[:3]
                            dt = datetime(int(year), int(month), int(day))
                            return dt.date().isoformat()

            # No pattern matched - return as-is
            logger.debug(f"Could not parse date format: '{cleaned}'")
            return cleaned

        except Exception as e:
            logger.warning(f"Error parsing date '{date_str}': {e}")
            return date_str

    def _parse_tags(self, tags_str: str) -> List[str]:
        """
        Parse tag names from AppleScript list format.

        Handles formats like:
        - {"tag1", "tag2", "tag3"}
        - "tag1, tag2, tag3"

        Args:
            tags_str: Raw tags string from AppleScript

        Returns:
            List of tag names
        """
        try:
            if not tags_str or tags_str.strip() in ['{}', 'missing value', '']:
                return []

            # The tags_str at this point still contains quotes and commas
            # Example: '"tag1", "tag2", "tag with, comma"'
            # We need to properly split on commas outside of quotes

            cleaned = tags_str.strip()

            # If it's already been captured as raw list content (which it is in LIST state),
            # it will have quotes preserved. We need to split carefully.
            tags = []
            current_tag = ""
            in_quotes = False

            for char in cleaned:
                if char == '"':
                    in_quotes = not in_quotes
                    # Don't include the quotes themselves
                elif char == ',' and not in_quotes:
                    # End of this tag
                    tag = current_tag.strip()
                    if tag:
                        tags.append(tag)
                    current_tag = ""
                else:
                    current_tag += char

            # Don't forget the last tag
            tag = current_tag.strip()
            if tag:
                tags.append(tag)

            return tags

        except Exception as e:
            logger.warning(f"Error parsing tags '{tags_str}': {e}")
            return []
