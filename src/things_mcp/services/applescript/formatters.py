"""AppleScript data formatters for dates, tags, and URLs."""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


class AppleScriptFormatters:
    """Handles formatting and parsing of AppleScript data types."""

    def build_things_url(self, action: str, parameters: Dict[str, Any], auth_token: Optional[str] = None) -> str:
        """Build a Things URL scheme string.

        Args:
            action: Things URL action (add, update, show, etc.)
            parameters: Optional parameters for the action
            auth_token: Optional auth token to include

        Returns:
            Formatted Things URL
        """
        url = f"things:///{action}"

        # Add auth token if available and not already in parameters
        if auth_token and 'auth-token' not in parameters:
            parameters = parameters.copy() if parameters else {}
            parameters['auth-token'] = auth_token

        if parameters:
            # URL encode parameters
            param_strings = []
            for key, value in parameters.items():
                if value is not None:
                    if isinstance(value, list):
                        value = ",".join(str(v) for v in value)

                    # URL encode all values (including newlines as %0A)
                    encoded_value = quote(str(value))

                    # Debug logging for checklist parameters
                    if key in ('checklist-items', 'append-checklist-items', 'prepend-checklist-items'):
                        logger.debug(f"Checklist parameter '{key}': raw={repr(value)}, encoded={encoded_value}")

                    param_strings.append(f"{key}={encoded_value}")

            if param_strings:
                url += "?" + "&".join(param_strings)

        # Debug log for checklist URLs
        if 'checklist-items' in str(parameters):
            logger.debug(f"Generated Things URL: {url[:200]}...")  # Truncate for readability

        return url

    def parse_applescript_date(self, date_str: str) -> Optional[str]:
        """Parse AppleScript date format to ISO string.

        Args:
            date_str: AppleScript date string

        Returns:
            ISO formatted date string or None if parsing fails
        """
        try:
            # AppleScript dates typically come as: date "Monday, January 1, 2024 at 12:00:00 PM"
            # Remove 'date' prefix and quotes if present
            cleaned = date_str.strip()
            if cleaned.startswith('date'):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]

            if not cleaned or cleaned == 'missing value':
                return None

            # Restore protected commas if any
            if '§COMMA§' in cleaned:
                cleaned = cleaned.replace('§COMMA§', ',')

            # Try to parse various AppleScript date formats
            date_patterns = [
                # European format: "Thursday, 4. September 2025 at 00:00:00" (24-hour)
                r'^(\w+),\s+(\d+)\.\s+(\w+)\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})$',
                # "Monday, January 1, 2024 at 12:00:00 PM"
                r'^(\w+),\s+(\w+)\s+(\d+),\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)$',
                # "January 1, 2024 at 12:00:00 PM"
                r'^(\w+)\s+(\d+),\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)$',
                # "January 1, 2024"
                r'^(\w+)\s+(\d+),\s+(\d{4})$',
                # "2024-01-01 12:00:00"
                r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}):(\d{2}))?$'
            ]

            month_names = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }

            for pattern in date_patterns:
                match = re.match(pattern, cleaned, re.IGNORECASE)
                if match:
                    groups = match.groups()

                    if pattern.startswith(r'^(\w+),\s+'):
                        if len(groups) == 7 and r'\.' in pattern:
                            # European format: "Thursday, 4. September 2025 at 00:00:00" (24-hour)
                            _, day, month_str, year, hour, minute, second = groups
                            month = month_names.get(month_str.lower())
                            if not month:
                                continue
                            dt = datetime(int(year), month, int(day), int(hour), int(minute), int(second))
                            return dt.isoformat()
                        elif len(groups) == 8:
                            # US format with AM/PM: "Monday, January 1, 2024 at 12:00:00 PM"
                            _, month_str, day, year, hour, minute, second, ampm = groups
                            month = month_names.get(month_str.lower())
                            if not month:
                                continue

                            hour = int(hour)
                            if ampm.upper() == 'PM' and hour != 12:
                                hour += 12
                            elif ampm.upper() == 'AM' and hour == 12:
                                hour = 0

                            dt = datetime(int(year), month, int(day), hour, int(minute), int(second))
                            return dt.isoformat()

                    elif pattern.startswith(r'^(\w+)\s+'):
                        # Month day, year format
                        if len(groups) == 7:  # With time
                            month_str, day, year, hour, minute, second, ampm = groups
                            month = month_names.get(month_str.lower())
                            if not month:
                                continue

                            hour = int(hour)
                            if ampm.upper() == 'PM' and hour != 12:
                                hour += 12
                            elif ampm.upper() == 'AM' and hour == 12:
                                hour = 0

                            dt = datetime(int(year), month, int(day), hour, int(minute), int(second))
                            return dt.isoformat()
                        else:  # Date only
                            month_str, day, year = groups
                            month = month_names.get(month_str.lower())
                            if not month:
                                continue
                            dt = datetime(int(year), month, int(day))
                            return dt.date().isoformat()

                    elif pattern.startswith(r'^(\d{4})'):
                        # ISO format
                        if len(groups) == 6 and groups[3]:  # With time
                            year, month, day, hour, minute, second = groups
                            dt = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
                            return dt.isoformat()
                        else:  # Date only
                            year, month, day = groups[:3]
                            dt = datetime(int(year), int(month), int(day))
                            return dt.date().isoformat()

            # If no pattern matches, return the cleaned string
            logger.debug(f"Could not parse date format, returning raw: '{cleaned}'")
            return cleaned

        except Exception as e:
            logger.warning(f"Could not parse date '{date_str}': {e}")
            return date_str  # Return original on error

    def format_applescript_date_to_iso(self, date_str: str) -> Optional[str]:
        """Convert AppleScript date string to ISO format YYYY-MM-DD HH:MM:SS.

        This method handles AppleScript's native date format and converts it
        to the standardized ISO format expected by the MCP API.

        Args:
            date_str: AppleScript date string (e.g., "date Friday, 15. August 2025 at 17:01:55")

        Returns:
            ISO formatted date string or None if missing/invalid
        """
        try:
            # Handle missing values
            if not date_str or date_str.strip() in ['missing value', '{}', '']:
                return None

            # Clean the string
            cleaned = date_str.strip()
            if cleaned.startswith('date'):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]

            # Enhanced pattern matching for AppleScript date formats
            patterns = [
                # "Friday, 15. August 2025 at 17:01:55"
                r'^(\w+),\s+(\d+)\.\s+(\w+)\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})$',
                # "Friday, August 15, 2025 at 5:01:55 PM"
                r'^(\w+),\s+(\w+)\s+(\d+),\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)$',
                # Already ISO-ish: "2025-08-15 17:01:55"
                r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})$'
            ]

            month_names = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }

            for pattern in patterns:
                match = re.match(pattern, cleaned, re.IGNORECASE)
                if match:
                    groups = match.groups()

                    if pattern.startswith(r'^(\w+),\s+(\d+)\.'):
                        # "Friday, 15. August 2025 at 17:01:55"
                        weekday, day, month_str, year, hour, minute, second = groups
                        month_num = month_names.get(month_str.lower())
                        if month_num:
                            return f"{year}-{month_num:02d}-{int(day):02d} {int(hour):02d}:{minute}:{second}"

                    elif pattern.startswith(r'^(\w+),\s+(\w+)\s+'):
                        # "Friday, August 15, 2025 at 5:01:55 PM"
                        weekday, month_str, day, year, hour, minute, second, ampm = groups
                        month_num = month_names.get(month_str.lower())
                        if month_num:
                            hour_24 = int(hour)
                            if ampm.upper() == 'PM' and hour_24 != 12:
                                hour_24 += 12
                            elif ampm.upper() == 'AM' and hour_24 == 12:
                                hour_24 = 0
                            return f"{year}-{month_num:02d}-{int(day):02d} {hour_24:02d}:{minute}:{second}"

                    elif pattern.startswith(r'^(\d{4})'):
                        # Already ISO format
                        return cleaned

            # If no pattern matches, try the existing parser
            existing_result = self.parse_applescript_date(date_str)
            if existing_result and existing_result != date_str:
                # Convert date-only to datetime format
                if len(existing_result) == 10:  # YYYY-MM-DD
                    return f"{existing_result} 00:00:00"
                return existing_result

            logger.debug(f"Could not parse AppleScript date format: '{cleaned}'")
            return None

        except Exception as e:
            logger.warning(f"Error formatting AppleScript date '{date_str}': {e}")
            return None

    def parse_applescript_tags(self, tags_str: str) -> List[str]:
        """Parse AppleScript tag names list.

        Args:
            tags_str: AppleScript tags string (e.g., '{"tag1", "tag2"}')

        Returns:
            List of tag names
        """
        try:
            # Tags might come as a list like: {"tag1", "tag2", "tag3"}
            # or as a simple comma-separated string like: "tag1, tag2, tag3"
            if not tags_str or tags_str.strip() in ['{}', 'missing value', '']:
                return []

            # Remove braces if present (for list format)
            cleaned = tags_str.strip()
            if cleaned.startswith('{') and cleaned.endswith('}'):
                cleaned = cleaned[1:-1]

            # Split by commas and clean up each tag
            tags = []
            for tag in cleaned.split(','):
                tag = tag.strip()
                # Remove quotes if present
                if tag.startswith('"') and tag.endswith('"'):
                    tag = tag[1:-1]
                if tag:
                    tags.append(tag)

            return tags
        except Exception as e:
            logger.warning(f"Could not parse tags '{tags_str}': {e}")
            return []

    def get_applescript_date_formatter(self, date_property: str, fallback_value: str = "missing value") -> str:
        """Generate AppleScript code to format a date property as YYYY-MM-DD HH:MM:SS.

        Args:
            date_property: The AppleScript date property (e.g., "creation date of theTodo")
            fallback_value: Value to return if date is missing (default: "missing value")

        Returns:
            AppleScript code that formats the date or returns fallback
        """
        return f'''
        try
            set dateValue to {date_property}
            if dateValue is missing value then
                "{fallback_value}"
            else
                set yyyy to (year of dateValue) as string
                set mm to (month of dateValue as integer) as string
                if length of mm = 1 then set mm to "0" & mm
                set dd to (day of dateValue) as string
                if length of dd = 1 then set dd to "0" & dd
                set timeStr to time string of dateValue
                yyyy & "-" & mm & "-" & dd & " " & timeStr
            end if
        on error
            "{fallback_value}"
        end try
        '''
