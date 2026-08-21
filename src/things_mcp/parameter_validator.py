"""
Parameter Validation Module for Things 3 MCP Server

Provides centralized validation for all parameter types to prevent bugs
like the recent tag concatenation issue and ensure consistent error handling.
"""

import re
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for parameter validation failures."""

    def __init__(self, field: str, message: str, value: Any = None):
        self.field = field
        self.message = message
        self.value = value
        super().__init__(f"{field}: {message}")


class ParameterValidator:
    """
    Centralized parameter validation for Things 3 MCP operations.

    Provides validation for:
    - Integer ranges (limit, offset, days)
    - Boolean conversion (completed, canceled, include_items)
    - Date formats (deadline, when, start_date)
    - String sanitization
    - Tag lists
    - ID formats
    """

    # Valid mode values for response optimization
    VALID_MODES = ["auto", "summary", "minimal", "standard", "detailed", "raw"]

    # Valid list names in Things 3
    VALID_LISTS = ["inbox", "today", "anytime", "someday", "upcoming", "logbook", "trash"]

    # Valid status values
    VALID_STATUSES = ["incomplete", "completed", "canceled", "open"]

    # Valid item types
    VALID_TYPES = ["to-do", "project", "heading"]

    @staticmethod
    def validate_limit(limit: Any, min_val: int = 1, max_val: int = 500,
                       field_name: str = "limit", allow_zero: bool = True) -> Optional[int]:
        """
        Validate and convert limit parameter.

        Args:
            limit: The limit value to validate (can be int, str, float, or None)
            min_val: Minimum allowed value (default: 1)
            max_val: Maximum allowed value (default: 500)
            field_name: Name of the field for error messages
            allow_zero: If True, allow limit=0 (returns empty results). Default: True

        Returns:
            Validated integer limit or None if input was None

        Raises:
            ValidationError: If limit is invalid
        """
        if limit is None:
            return None

        try:
            # Handle various input types
            if isinstance(limit, str):
                limit_int = int(limit)
            elif isinstance(limit, (int, float)):
                limit_int = int(limit)
            else:
                limit_int = int(str(limit))

            # Special case: allow limit=0 if configured (returns empty results)
            if allow_zero and limit_int == 0:
                return 0

            # Validate range
            if limit_int < min_val or limit_int > max_val:
                raise ValidationError(
                    field_name,
                    f"must be between {min_val} and {max_val}, got {limit_int}",
                    limit_int
                )

            return limit_int

        except (ValueError, TypeError) as e:
            raise ValidationError(
                field_name,
                f"must be a number between {min_val} and {max_val}",
                limit
            )

    @staticmethod
    def validate_offset(offset: Any, min_val: int = 0,
                       field_name: str = "offset") -> int:
        """
        Validate and convert offset parameter.

        Args:
            offset: The offset value to validate (can be int, str, float, or None)
            min_val: Minimum allowed value (default: 0)
            field_name: Name of the field for error messages

        Returns:
            Validated integer offset (defaults to 0 if None)

        Raises:
            ValidationError: If offset is invalid
        """
        if offset is None:
            return 0

        try:
            # Handle various input types
            if isinstance(offset, str):
                offset_int = int(offset)
            elif isinstance(offset, (int, float)):
                offset_int = int(offset)
            else:
                offset_int = int(str(offset))

            # Validate minimum
            if offset_int < min_val:
                raise ValidationError(
                    field_name,
                    f"must be >= {min_val}, got {offset_int}",
                    offset_int
                )

            return offset_int

        except (ValueError, TypeError) as e:
            raise ValidationError(
                field_name,
                f"must be a non-negative integer",
                offset
            )

    @staticmethod
    def validate_days(days: Any, min_val: int = 1, max_val: int = 365,
                     field_name: str = "days") -> int:
        """
        Validate days parameter for date range queries.

        Args:
            days: The days value to validate
            min_val: Minimum allowed value (default: 1)
            max_val: Maximum allowed value (default: 365)
            field_name: Name of the field for error messages

        Returns:
            Validated integer days

        Raises:
            ValidationError: If days is invalid
        """
        if days is None:
            raise ValidationError(field_name, "is required", None)

        try:
            # Handle various input types
            if isinstance(days, str):
                days_int = int(days)
            elif isinstance(days, (int, float)):
                days_int = int(days)
            else:
                days_int = int(str(days))

            # Validate range
            if days_int < min_val or days_int > max_val:
                raise ValidationError(
                    field_name,
                    f"must be between {min_val} and {max_val}, got {days_int}",
                    days_int
                )

            return days_int

        except (ValueError, TypeError) as e:
            raise ValidationError(
                field_name,
                f"must be a number between {min_val} and {max_val}",
                days
            )

    @staticmethod
    def validate_boolean(value: Any, field_name: str = "boolean") -> Optional[bool]:
        """
        Validate and convert boolean parameter.

        Handles string representations like "true", "false", "yes", "no", "1", "0"
        as well as actual boolean and numeric values.

        Args:
            value: The value to convert to boolean (can be bool, str, int, or None)
            field_name: Name of the field for error messages

        Returns:
            Boolean value or None if input was None

        Raises:
            ValidationError: If value cannot be converted to boolean
        """
        if value is None:
            return None

        # Already a boolean
        if isinstance(value, bool):
            return value

        # Handle string representations
        if isinstance(value, str):
            lower_val = value.lower().strip()
            if lower_val in ('true', 'yes', '1', 't', 'y'):
                return True
            elif lower_val in ('false', 'no', '0', 'f', 'n'):
                return False
            else:
                raise ValidationError(
                    field_name,
                    f"must be a boolean value (true/false), got '{value}'",
                    value
                )

        # Handle numeric values
        if isinstance(value, (int, float)):
            return bool(value)

        raise ValidationError(
            field_name,
            f"must be a boolean value (true/false), got '{value}'",
            value
        )

    @staticmethod
    def validate_strict_iso_date(date_str: Any, field_name: str = "date") -> Optional[str]:
        """
        Validate strict ISO 8601 date format (YYYY-MM-DD only) with range checking.

        This is stricter than validate_date_format() - only ISO 8601 format allowed,
        no relative dates. Validates that the date is actually valid (no month 13, day 45, etc).

        Args:
            date_str: The date string to validate
            field_name: Name of the field for error messages

        Returns:
            Validated date string or None if input was None

        Raises:
            ValidationError: If date format is invalid or date is out of range
        """
        if date_str is None:
            return None

        if not isinstance(date_str, str):
            raise ValidationError(
                field_name,
                f"must be a string, got {type(date_str).__name__}",
                date_str
            )

        date_str = date_str.strip()

        if not date_str:
            return None

        # Check ISO 8601 format (YYYY-MM-DD)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            raise ValidationError(
                field_name,
                f"must be ISO 8601 format (YYYY-MM-DD), got: {date_str}",
                date_str
            )

        # Validate the date is actually valid
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError as e:
            raise ValidationError(
                field_name,
                f"invalid date: {date_str} - {str(e)}",
                date_str
            )

    @staticmethod
    def validate_date_format(date_str: Any, field_name: str = "date",
                            allow_relative: bool = True) -> Optional[str]:
        """
        Validate date format (YYYY-MM-DD or relative like "today", "tomorrow").

        Args:
            date_str: The date string to validate
            field_name: Name of the field for error messages
            allow_relative: Whether to allow relative dates like "today"

        Returns:
            Validated date string or None if input was None

        Raises:
            ValidationError: If date format is invalid
        """
        if date_str is None:
            return None

        if not isinstance(date_str, str):
            raise ValidationError(
                field_name,
                f"must be a string, got {type(date_str).__name__}",
                date_str
            )

        date_str = date_str.strip()

        if not date_str:
            return None

        # Allow relative dates if enabled
        if allow_relative:
            relative_dates = ["today", "tomorrow", "yesterday", "someday", "anytime", "evening"]
            lowered = date_str.lower()
            # 'tonight' is a user-facing alias for Things' 'evening' scheduling
            # keyword (This Evening) - normalize to the canonical 'evening' so
            # downstream code (URL-scheme routing, etc.) only has to handle one
            # spelling.
            if lowered == "tonight":
                return "evening"
            if lowered in relative_dates:
                return lowered

        # Validate YYYY-MM-DD format
        iso_date_pattern = r'^\d{4}-\d{2}-\d{2}$'
        if re.match(iso_date_pattern, date_str):
            try:
                # Verify it's a valid date
                datetime.strptime(date_str, '%Y-%m-%d')
                return date_str
            except ValueError as e:
                raise ValidationError(
                    field_name,
                    f"is not a valid date: {str(e)}",
                    date_str
                )

        # Check for datetime format with time component (YYYY-MM-DD@HH:MM).
        # The date portion is validated the same way as the plain
        # YYYY-MM-DD case above (real calendar date, via strptime), and the
        # time portion's hour/minute ranges are validated explicitly -
        # datetime.strptime with '%H:%M' already rejects out-of-range
        # values (e.g. '25:99'), which a bare regex does not.
        datetime_pattern = r'^(\d{4}-\d{2}-\d{2})@(\d{1,2}:\d{2})$'
        datetime_match = re.match(datetime_pattern, date_str)
        if datetime_match:
            date_part, time_part = datetime_match.groups()
            try:
                datetime.strptime(date_part, '%Y-%m-%d')
                datetime.strptime(time_part, '%H:%M')
                return date_str  # Valid datetime format
            except ValueError as e:
                raise ValidationError(
                    field_name,
                    f"is not a valid date/time: {str(e)}",
                    date_str
                )

        if allow_relative:
            message = f"must be in YYYY-MM-DD format or a relative date (today, tomorrow, etc.), got '{date_str}'"
        else:
            message = f"must be in YYYY-MM-DD format, got '{date_str}'"

        raise ValidationError(
            field_name,
            message,
            date_str
        )

    @staticmethod
    def validate_period_format(period: str, field_name: str = "period") -> str:
        """
        Validate period format (e.g., "7d", "1w", "2m", "1y").

        Args:
            period: The period string to validate
            field_name: Name of the field for error messages

        Returns:
            Validated period string

        Raises:
            ValidationError: If period format is invalid
        """
        if period is None:
            raise ValidationError(field_name, "is required", None)

        if not isinstance(period, str):
            raise ValidationError(
                field_name,
                f"must be a string, got {type(period).__name__}",
                period
            )

        period = period.strip()

        # Match pattern: digits followed by d/w/m/y
        pattern = r'^\d+[dwmy]$'
        if not re.match(pattern, period):
            raise ValidationError(
                field_name,
                f"must match pattern like '7d', '1w', '2m', '1y', got '{period}'",
                period
            )

        return period

    @staticmethod
    def validate_mode(mode: Optional[str], field_name: str = "mode") -> Optional[str]:
        """
        Validate response mode parameter.

        Args:
            mode: The mode to validate
            field_name: Name of the field for error messages

        Returns:
            Validated mode string or None if input was None

        Raises:
            ValidationError: If mode is invalid
        """
        if mode is None:
            return None

        if not isinstance(mode, str):
            raise ValidationError(
                field_name,
                f"must be a string, got {type(mode).__name__}",
                mode
            )

        mode = mode.strip().lower()

        if mode not in ParameterValidator.VALID_MODES:
            raise ValidationError(
                field_name,
                f"must be one of {', '.join(ParameterValidator.VALID_MODES)}, got '{mode}'",
                mode
            )

        return mode

    @staticmethod
    def validate_status(status: Optional[str], field_name: str = "status") -> Optional[str]:
        """
        Validate status parameter.

        Args:
            status: The status to validate
            field_name: Name of the field for error messages

        Returns:
            Validated status string or None if input was None

        Raises:
            ValidationError: If status is invalid
        """
        if status is None:
            return None

        if not isinstance(status, str):
            raise ValidationError(
                field_name,
                f"must be a string, got {type(status).__name__}",
                status
            )

        status = status.strip().lower()

        if status not in ParameterValidator.VALID_STATUSES:
            raise ValidationError(
                field_name,
                f"must be one of {', '.join(ParameterValidator.VALID_STATUSES)}, got '{status}'",
                status
            )

        return status

    @staticmethod
    def validate_item_type(item_type: Optional[str], field_name: str = "type") -> Optional[str]:
        """
        Validate item type parameter.

        Args:
            item_type: The type to validate
            field_name: Name of the field for error messages

        Returns:
            Validated type string or None if input was None

        Raises:
            ValidationError: If type is invalid
        """
        if item_type is None:
            return None

        if not isinstance(item_type, str):
            raise ValidationError(
                field_name,
                f"must be a string, got {type(item_type).__name__}",
                item_type
            )

        item_type = item_type.strip().lower()

        if item_type not in ParameterValidator.VALID_TYPES:
            raise ValidationError(
                field_name,
                f"must be one of {', '.join(ParameterValidator.VALID_TYPES)}, got '{item_type}'",
                item_type
            )

        return item_type

    @staticmethod
    def validate_non_empty_string(value: Any, field_name: str = "string") -> str:
        """
        Validate that a value is a non-empty string.

        Args:
            value: The value to validate
            field_name: Name of the field for error messages

        Returns:
            Validated trimmed string

        Raises:
            ValidationError: If value is not a non-empty string
        """
        if value is None:
            raise ValidationError(field_name, "is required", None)

        if not isinstance(value, str):
            raise ValidationError(
                field_name,
                f"must be a string, got {type(value).__name__}",
                value
            )

        value = value.strip()

        if not value:
            raise ValidationError(field_name, "cannot be empty", "")

        return value

    @staticmethod
    def validate_tag_list(tags: Union[str, List[str], None],
                         field_name: str = "tags") -> Optional[List[str]]:
        """
        Validate and normalize tag list.

        Handles both comma-separated strings and lists.
        Filters out empty tags and trims whitespace.

        Individual tag names containing a literal comma are rejected: Things'
        AppleScript tag API represents a todo's tags as a single comma-joined
        string (`tag names of targetTodo`), so a tag name containing a comma
        is indistinguishable from two separate tags and cannot round-trip
        through that API. This can only happen via list input (e.g.
        `["home, office"]`) - comma-separated string input already splits on
        `,` before this check runs, so a string-typed tag name can never
        contain a comma by the time it reaches this branch.

        Args:
            tags: Tags as string (comma-separated), list, or None
            field_name: Name of the field for error messages

        Returns:
            List of validated tag strings or None if input was None

        Raises:
            ValidationError: If tags format is invalid, or if any individual
                tag name contains a comma
        """
        if tags is None:
            return None

        # Handle string input (comma-separated)
        if isinstance(tags, str):
            tags = tags.strip()
            if not tags:
                return None
            tag_list = [t.strip() for t in tags.split(",") if t.strip()]

        # Handle list input
        elif isinstance(tags, list):
            tag_list = [str(t).strip() for t in tags if str(t).strip()]

        else:
            raise ValidationError(
                field_name,
                f"must be a string or list, got {type(tags).__name__}",
                tags
            )

        if not tag_list:
            return None

        for tag in tag_list:
            if "," in tag:
                raise ValidationError(
                    field_name,
                    f"tag name {tag!r} contains a comma, which Things' "
                    "comma-joined AppleScript tag API cannot represent - "
                    "rename the tag or remove the comma",
                    tag
                )

        return tag_list

    @staticmethod
    def validate_id_list(ids: Union[str, List[str]],
                        field_name: str = "ids") -> List[str]:
        """
        Validate and normalize ID list.

        Handles both comma-separated strings and lists.
        Filters out empty IDs and trims whitespace.

        Args:
            ids: IDs as string (comma-separated) or list
            field_name: Name of the field for error messages

        Returns:
            List of validated ID strings

        Raises:
            ValidationError: If ids format is invalid or empty
        """
        if ids is None:
            raise ValidationError(field_name, "is required", None)

        # Handle string input (comma-separated)
        if isinstance(ids, str):
            ids = ids.strip()
            if not ids:
                raise ValidationError(field_name, "cannot be empty", "")
            id_list = [i.strip() for i in ids.split(",") if i.strip()]

        # Handle list input
        elif isinstance(ids, list):
            id_list = [str(i).strip() for i in ids if str(i).strip()]

        else:
            raise ValidationError(
                field_name,
                f"must be a string or list, got {type(ids).__name__}",
                ids
            )

        if not id_list:
            raise ValidationError(field_name, "cannot be empty after parsing", ids)

        return id_list

    @staticmethod
    def sanitize_string(value: Optional[str], max_length: Optional[int] = None) -> Optional[str]:
        """
        Sanitize a string by trimming whitespace and optionally limiting length.

        Args:
            value: The string to sanitize
            max_length: Optional maximum length

        Returns:
            Sanitized string or None if input was None/empty
        """
        if value is None:
            return None

        if not isinstance(value, str):
            value = str(value)

        value = value.strip()

        if not value:
            return None

        if max_length and len(value) > max_length:
            logger.warning(f"String truncated from {len(value)} to {max_length} characters")
            value = value[:max_length]

        return value

    @classmethod
    def validate_search_params(cls, query: str, limit: Optional[int] = None,
                               mode: Optional[str] = None) -> Dict[str, Any]:
        """
        Validate search_todos parameters.

        Args:
            query: Search query string
            limit: Optional result limit
            mode: Optional response mode

        Returns:
            Dict with validated parameters

        Raises:
            ValidationError: If any parameter is invalid
        """
        return {
            'query': cls.validate_non_empty_string(query, 'query'),
            'limit': cls.validate_limit(limit, min_val=1, max_val=500, field_name='limit'),
            'mode': cls.validate_mode(mode)
        }

    @classmethod
    def validate_update_params(cls, **kwargs) -> Dict[str, Any]:
        """
        Validate update_todo/update_project/update_area/bulk_update_todos parameters.

        Clear-field contract (applies to partial updates only - a parameter that
        is omitted, or explicitly passed as ``None``, leaves the existing field
        unchanged):

        - ``notes=''`` and ``deadline=''`` are valid "clear this field" requests
          and are passed through as the literal empty string ``''`` so callers
          can distinguish "clear" from "leave unchanged" (``None``).
        - ``tags=''`` is also a valid "clear all tags" request and is passed
          through as ``[]`` (an explicit empty list, distinct from ``None``).
        - ``title=''`` (or whitespace-only) is rejected with a ValidationError -
          titles cannot be cleared.
        - ``when=''`` is rejected with a ValidationError directing callers to
          use ``when='anytime'`` or ``when='someday'`` to unschedule instead -
          there is no "clear" semantics for ``when``.
        - ``when`` accepts the relative keywords ``today``/``tomorrow``/
          ``yesterday``/``someday``/``anytime``/``evening`` (``tonight`` is
          accepted as an alias and normalized to ``evening``), in addition to
          ``YYYY-MM-DD`` (and ``YYYY-MM-DD@HH:MM``).
        - ``deadline`` (when non-empty) must be ``YYYY-MM-DD`` -
          relative keywords like ``today`` are rejected with a
          ValidationError, identically to the pre-validation server.py
          already performs for add_todo/update_todo/bulk_update_todos.

        Args:
            **kwargs: Update parameters

        Returns:
            Dict with validated parameters

        Raises:
            ValidationError: If any parameter is invalid
        """
        validated = {}

        if 'title' in kwargs and kwargs['title'] is not None:
            sanitized_title = cls.sanitize_string(kwargs['title'])
            if sanitized_title is None:
                raise ValidationError('title', 'title cannot be empty', kwargs['title'])
            validated['title'] = sanitized_title

        if 'notes' in kwargs and kwargs['notes'] is not None:
            if isinstance(kwargs['notes'], str) and kwargs['notes'].strip() == '':
                # Explicit clear request - preserve as '' rather than sanitizing
                # away to None, so downstream update paths can distinguish
                # "clear notes" from "notes not provided".
                validated['notes'] = ''
            else:
                sanitized_notes = cls.sanitize_string(kwargs['notes'])
                if sanitized_notes is not None:
                    validated['notes'] = sanitized_notes

        if 'tags' in kwargs and kwargs['tags'] is not None:
            raw_tags = kwargs['tags']
            is_explicit_clear = (isinstance(raw_tags, str) and raw_tags.strip() == '') or \
                (isinstance(raw_tags, list) and len(raw_tags) == 0)
            if is_explicit_clear:
                # Explicit clear request - preserve as [] rather than the
                # normal validate_tag_list() None-on-empty behaviour, so
                # downstream update paths can distinguish "clear tags" from
                # "tags not provided".
                validated['tags'] = []
            else:
                validated['tags'] = cls.validate_tag_list(raw_tags)

        if 'when' in kwargs and kwargs['when'] is not None:
            if isinstance(kwargs['when'], str) and kwargs['when'].strip() == '':
                raise ValidationError(
                    'when',
                    "use when='anytime' or when='someday' to unschedule",
                    kwargs['when']
                )
            validated['when'] = cls.validate_date_format(kwargs['when'], 'when', allow_relative=True)

        if 'deadline' in kwargs and kwargs['deadline'] is not None:
            if isinstance(kwargs['deadline'], str) and kwargs['deadline'].strip() == '':
                # Explicit clear request - preserve as '' rather than the
                # normal validate_date_format() None-on-empty behaviour, so
                # downstream update paths can distinguish "clear deadline"
                # from "deadline not provided".
                validated['deadline'] = ''
            else:
                # allow_relative=False: deadline must be YYYY-MM-DD - this
                # matches the pre-validation server.py already performs for
                # add_todo/update_todo/bulk_update_todos (allow_relative=False),
                # so a relative keyword like 'today' is rejected identically
                # at both layers instead of silently reaching AppleScript/URL
                # scheme code that has no relative-date handling for deadline.
                validated['deadline'] = cls.validate_date_format(kwargs['deadline'], 'deadline', allow_relative=False)

        if 'completed' in kwargs and kwargs['completed'] is not None:
            validated['completed'] = cls.validate_boolean(kwargs['completed'], 'completed')

        if 'canceled' in kwargs and kwargs['canceled'] is not None:
            validated['canceled'] = cls.validate_boolean(kwargs['canceled'], 'canceled')

        return validated

    @classmethod
    def validate_advanced_search_params(cls, **kwargs) -> Dict[str, Any]:
        """
        Validate search_advanced parameters.

        Args:
            **kwargs: Search filter parameters

        Returns:
            Dict with validated parameters

        Raises:
            ValidationError: If any parameter is invalid
        """
        validated = {}

        if 'status' in kwargs and kwargs['status'] is not None:
            validated['status'] = cls.validate_status(kwargs['status'])

        if 'type' in kwargs and kwargs['type'] is not None:
            validated['type'] = cls.validate_item_type(kwargs['type'])

        if 'tag' in kwargs and kwargs['tag'] is not None:
            validated['tag'] = cls.sanitize_string(kwargs['tag'])

        if 'area' in kwargs and kwargs['area'] is not None:
            validated['area'] = cls.sanitize_string(kwargs['area'])

        if 'start_date' in kwargs and kwargs['start_date'] is not None:
            validated['start_date'] = cls.validate_date_format(kwargs['start_date'], 'start_date', allow_relative=False)

        if 'deadline' in kwargs and kwargs['deadline'] is not None:
            validated['deadline'] = cls.validate_date_format(kwargs['deadline'], 'deadline', allow_relative=False)

        if 'limit' in kwargs and kwargs['limit'] is not None:
            validated['limit'] = cls.validate_limit(kwargs['limit'], min_val=1, max_val=500)

        if 'mode' in kwargs and kwargs['mode'] is not None:
            validated['mode'] = cls.validate_mode(kwargs['mode'])

        return validated


def create_validation_error_response(error: ValidationError) -> Dict[str, Any]:
    """
    Create a standardized error response for validation failures.

    Args:
        error: The ValidationError to convert

    Returns:
        Dict with error details suitable for API response
    """
    return {
        "success": False,
        "error": "VALIDATION_ERROR",
        "field": error.field,
        "message": error.message,
        "invalid_value": error.value
    }