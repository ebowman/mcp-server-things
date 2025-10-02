"""AppleScript manager for Things 3 integration.

This module serves as a facade that delegates to specialized modules:
- executor: AppleScript execution with locking and retry
- formatters: Date/tag/URL formatting
- queries: AppleScript query builders
- parser: State machine parser for AppleScript output
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..locale_aware_dates import locale_handler
from ..config import ThingsMCPConfig
from .applescript import (
    AppleScriptParser,
    AppleScriptExecutor,
    AppleScriptFormatters,
    AppleScriptQueries,
)

logger = logging.getLogger(__name__)


class AppleScriptManager:
    """Manages AppleScript execution and Things URL schemes.

    This class acts as a facade that delegates to specialized modules for
    execution, formatting, queries, and parsing. It maintains backwards
    compatibility with the original interface.
    """

    # Class-level lock shared across all instances (delegated to executor)
    _applescript_lock = asyncio.Lock()

    def __init__(self, timeout: int = 45, retry_count: int = 3, config: Optional[ThingsMCPConfig] = None):
        """Initialize the AppleScript manager.

        Args:
            timeout: Command timeout in seconds
            retry_count: Number of retries for failed commands
            config: Optional configuration object for feature flags
        """
        self.timeout = timeout
        self.retry_count = retry_count
        self.config = config or ThingsMCPConfig()
        self.auth_token = self._load_auth_token()

        # Initialize specialized modules
        self.executor = AppleScriptExecutor(timeout=timeout, retry_count=retry_count)
        self.formatters = AppleScriptFormatters()
        self.queries = AppleScriptQueries()

        # Initialize parser based on config
        if self.config.use_new_applescript_parser:
            self.parser = AppleScriptParser()
            logger.info("AppleScript manager initialized with NEW state machine parser")
        else:
            self.parser = None
            logger.warning(
                "DEPRECATED: Using LEGACY string manipulation parser. "
                "The legacy parser has known bugs with completion_date and cancellation_date fields. "
                "Set use_new_applescript_parser=True to use the new state machine parser. "
                "Legacy parser will be removed in v2.0.0."
            )

        logger.info("AppleScript manager initialized - cache removed for hybrid implementation")

    def _load_auth_token(self) -> Optional[str]:
        """Load Things auth token from file if it exists."""
        auth_files = [
            Path(__file__).parent.parent.parent / '.things-auth',
            Path(__file__).parent.parent.parent / 'things-auth.txt',
            Path.home() / '.things-auth'
        ]

        for auth_file in auth_files:
            if auth_file.exists():
                try:
                    token = auth_file.read_text().strip()
                    # Handle format: THINGS_AUTH_TOKEN=xxx or just xxx
                    if '=' in token:
                        token = token.split('=', 1)[1].strip()
                    logger.info(f"Loaded Things auth token from {auth_file}")
                    return token
                except Exception as e:
                    logger.warning(f"Failed to read auth token from {auth_file}: {e}")

        logger.debug("No Things auth token found - will use direct AppleScript execution")
        return None

    async def is_things_running(self) -> bool:
        """Check if Things 3 is currently running."""
        return await self.executor.is_things_running()

    async def execute_applescript(self, script: str, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """Execute an AppleScript command.

        Args:
            script: AppleScript code to execute
            cache_key: Ignored - caching removed for hybrid implementation

        Returns:
            Dict with success status, output, and error information
        """
        return await self.executor.execute_script(script)

    async def execute_url_scheme(self, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a Things URL scheme command.

        Args:
            action: Things URL action (add, update, show, etc.)
            parameters: Optional parameters for the action

        Returns:
            Dict with success status and result information
        """
        try:
            # Handle url_override for complete URLs (for reminder functionality)
            if parameters and "url_override" in parameters:
                url = parameters["url_override"]
            else:
                url = self.formatters.build_things_url(action, parameters or {}, self.auth_token)

            # Use do shell script with open -g to avoid bringing Things to foreground
            script = f'''do shell script "open -g '{url}'"'''

            result = await self.executor.execute_script(script)

            # For URL schemes, success is usually indicated by no error
            if result.get("success"):
                return {
                    "success": True,
                    "url": url,
                    "message": f"Successfully executed {action} action"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "url": url
                }

        except Exception as e:
            logger.error(f"Error executing URL scheme: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    async def get_todos(self, project_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get todos from Things 3 using optimized batch property retrieval.

        Args:
            project_uuid: Optional project UUID to filter by

        Returns:
            List of todo dictionaries
        """
        try:
            script = self.queries.build_get_todos_script(project_uuid)
            result = await self.execute_applescript(script)

            if result.get("success"):
                try:
                    return self._parse_applescript_list(result.get("output", ""))
                except ValueError as e:
                    logger.error(f"Failed to parse todos: {e}")
                    raise
            else:
                error_msg = f"AppleScript failed to get todos: {result.get('error')}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Error getting todos: {e}")
            raise

    async def get_projects(self) -> List[Dict[str, Any]]:
        """Get all projects from Things 3 using optimized batch property retrieval.

        Projects in Things 3 inherit from todos and have identical properties.
        This method now fetches all inherited fields to maintain proper inheritance.
        """
        try:
            script = self.queries.build_get_projects_script()
            result = await self.execute_applescript(script, "projects_all")

            if result.get("success"):
                try:
                    return self._parse_applescript_list(result.get("output", ""))
                except ValueError as e:
                    logger.error(f"Failed to parse projects: {e}")
                    raise
            else:
                error_msg = f"AppleScript failed to get projects: {result.get('error')}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Error getting projects: {e}")
            raise

    async def get_areas(self) -> List[Dict[str, Any]]:
        """Get all areas from Things 3 using optimized batch property retrieval.

        Note: Areas in Things 3 only have 'id' and 'name' properties.
        """
        try:
            script = self.queries.build_get_areas_script()
            result = await self.execute_applescript(script, "areas_all")

            if result.get("success"):
                try:
                    return self._parse_applescript_list(result.get("output", ""))
                except ValueError as e:
                    logger.error(f"Failed to parse areas: {e}")
                    raise
            else:
                error_msg = f"AppleScript failed to get areas: {result.get('error')}"
                logger.error(error_msg)
                raise Exception(error_msg)

        except Exception as e:
            logger.error(f"Error getting areas: {e}")
            raise

    def _parse_applescript_list(self, output: str) -> List[Dict[str, Any]]:
        """Parse AppleScript list output into Python dictionaries.

        Parses AppleScript record format like:
        id:todo1, name:First Todo, notes:Notes 1, status:open, id:todo2, name:Second Todo, notes:Notes 2, status:completed

        Uses either the new state machine parser (if enabled) or the legacy string manipulation parser.

        Raises:
            ValueError: If the output is empty or cannot be parsed
            Exception: For other parsing errors
        """
        if not output or not output.strip():
            logger.warning("AppleScript returned empty output")
            return []  # Return empty list for empty output, don't raise error

        logger.debug(f"AppleScript output to parse: {output}")

        # Use new parser if configured
        if self.parser is not None:
            try:
                logger.debug("Using NEW state machine parser")
                records = self.parser.parse(output)

                # Convert tag_names to tags for compatibility
                for record in records:
                    if 'tag_names' in record:
                        record['tags'] = record.pop('tag_names')

                # Add reminder detection fields to all records
                for record in records:
                    self.formatters.enhance_record_with_reminder_info(record)

                logger.debug(f"Parsed {len(records)} records using new parser")
                return records
            except Exception as e:
                logger.error(f"New parser failed: {e}. Falling back to legacy parser.")
                # Fall through to legacy parser

        # Legacy parser implementation follows
        logger.warning(
            "DEPRECATED: Using legacy parser for this operation. "
            "Consider enabling use_new_applescript_parser=True. "
            "Legacy parser has known bugs with completion_date and cancellation_date fields."
        )

        try:
            # Parse the output - special handling for tag_names which can contain commas
            records = []
            current_record = {}

            # First, let's handle tag_names specially since it can contain commas
            # Strategy: find tag_names: and extract value until we hit another known field
            temp_output = output.strip()

            # Known field names that can follow tag_names (added activation_date for reminder support)
            known_fields = ['creation_date:', 'modification_date:', 'due_date:', 'status:',
                          'notes:', 'id:', 'name:', 'area:', 'project:', 'start_date:',
                          'completion_date:', 'cancellation_date:', 'contact:', 'activation_date:']

            # Find tag_names and protect its commas
            if 'tag_names:' in temp_output:
                start_idx = temp_output.find('tag_names:') + len('tag_names:')

                # Find the next field after tag_names
                end_idx = len(temp_output)  # Default to end of string
                for field in known_fields:
                    field_idx = temp_output.find(field, start_idx)
                    if field_idx != -1 and field_idx < end_idx:
                        # Found a field that comes after tag_names
                        # Back up to the comma before this field
                        comma_idx = temp_output.rfind(',', start_idx, field_idx)
                        if comma_idx != -1:
                            end_idx = comma_idx
                        else:
                            end_idx = field_idx

                # Extract and protect the tag value
                tag_value = temp_output[start_idx:end_idx].strip()
                if tag_value:
                    protected_value = tag_value.replace(',', '§COMMA§')
                    temp_output = temp_output[:start_idx] + protected_value + temp_output[end_idx:]

            # Also protect commas in date fields which contain "date Thursday, 4. September 2025 at 00:00:00"
            for date_field in ['creation_date:', 'modification_date:', 'due_date:', 'start_date:', 'completion_date:', 'cancellation_date:', 'activation_date:']:
                if date_field in temp_output:
                    # Find all instances of this date field
                    field_start = 0
                    while True:
                        field_idx = temp_output.find(date_field, field_start)
                        if field_idx == -1:
                            break

                        start_idx = field_idx + len(date_field)

                        # Find the next field or end of this date value
                        end_idx = len(temp_output)
                        for field in known_fields:
                            next_field_idx = temp_output.find(field, start_idx)
                            if next_field_idx != -1 and next_field_idx < end_idx:
                                # Back up to the comma before this field
                                comma_idx = temp_output.rfind(',', start_idx, next_field_idx)
                                if comma_idx != -1:
                                    end_idx = comma_idx
                                else:
                                    end_idx = next_field_idx

                        # Extract the date value and protect its commas
                        date_value = temp_output[start_idx:end_idx].strip()
                        if date_value and date_value != 'missing value':
                            protected_value = date_value.replace(',', '§COMMA§')
                            temp_output = temp_output[:start_idx] + protected_value + temp_output[end_idx:]
                            # Adjust field_start to continue searching after the replaced text
                            field_start = start_idx + len(protected_value)
                        else:
                            field_start = start_idx

            # Now split by commas safely
            parts = self.formatters.split_applescript_output(temp_output)

            if not parts:
                logger.warning("No parts found in AppleScript output after splitting")
                return []

            for part in parts:
                part = part.strip()
                if not part:
                    continue

                if ':' in part:
                    key, value = part.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    # If we encounter an 'id' key and already have a record, save it
                    if key == 'id' and current_record:
                        records.append(current_record)
                        current_record = {}

                    # Parse different value types
                    if key in ['creation_date', 'modification_date', 'due_date', 'start_date', 'activation_date']:
                        # Restore both commas and colons that were escaped
                        if '§COMMA§' in value:
                            value = value.replace('§COMMA§', ',')
                        if '§COLON§' in value:
                            value = value.replace('§COLON§', ':')
                        # Handle date parsing
                        if value and value != 'missing value':
                            current_record[key] = self.formatters.parse_applescript_date(value)
                        else:
                            current_record[key] = None
                    elif key == 'tag_names':
                        # Restore commas in tag names and parse
                        value = value.replace('§COMMA§', ',')
                        current_record['tags'] = self.formatters.parse_applescript_tags(value)
                    else:
                        # Handle string values, removing quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]

                        # Handle AppleScript "missing value"
                        if value == 'missing value':
                            value = None

                        current_record[key] = value
                else:
                    # Handle AppleScript list items that don't have colons (like tag names)
                    part_stripped = part.strip()

                    # Skip empty parts
                    if not part_stripped:
                        continue

                    # If we're in the middle of parsing a record, this might be a tag name
                    # that got split from an AppleScript list
                    if current_record:
                        # Initialize tags list if we don't have it yet
                        if 'tags' not in current_record:
                            current_record['tags'] = []

                        # If this looks like a tag name (no colon, reasonable length, alphanumeric+spaces)
                        if (part_stripped and
                            len(part_stripped) < 100 and
                            not any(char in part_stripped for char in [':', '{', '}', '(', ')']) and
                            part_stripped.replace(' ', '').replace('-', '').replace('_', '').isalnum()):
                            current_record['tags'].append(part_stripped)
                            logger.debug(f"Recovered tag name: '{part_stripped}'")
                        else:
                            logger.debug(f"Skipping unparseable part: '{part_stripped}'")
                    else:
                        logger.debug(f"Orphaned part (no current record): '{part_stripped}'")

            # Don't forget the last record
            if current_record:
                # Add reminder detection fields to all records before finalizing
                self.formatters.enhance_record_with_reminder_info(current_record)
                records.append(current_record)

            # Also enhance any previously added records with reminder info
            for record in records:
                self.formatters.enhance_record_with_reminder_info(record)

            logger.debug(f"Parsed {len(records)} records from AppleScript output")

            # If we expected records but got none, that might indicate a problem
            if not records and output.strip():
                logger.warning(f"Failed to parse any records from non-empty output: {output[:100]}...")

            return records

        except Exception as e:
            logger.error(f"Error parsing AppleScript output: {e}")
            logger.debug(f"Problematic output was: {output[:500]}...")

            # In production, we should try to continue with partial data rather than failing completely
            if records:
                logger.warning(f"Partial parsing successful - returning {len(records)} records despite error")
                return records
            else:
                # Only fail completely if we got no usable data at all
                raise ValueError(f"Failed to parse AppleScript output: {e}") from e

    # Delegate formatting methods to formatters module
    def _parse_applescript_date(self, date_str: str) -> Optional[str]:
        """Parse AppleScript date format to ISO string (delegates to formatters)."""
        return self.formatters.parse_applescript_date(date_str)

    def get_applescript_date_formatter(self, date_property: str, fallback_value: str = "missing value") -> str:
        """Generate AppleScript code to format a date property (delegates to formatters)."""
        return self.formatters.get_applescript_date_formatter(date_property, fallback_value)

    def format_applescript_date_to_iso(self, date_str: str) -> Optional[str]:
        """Convert AppleScript date string to ISO format (delegates to formatters)."""
        return self.formatters.format_applescript_date_to_iso(date_str)

    def _parse_applescript_tags(self, tags_str: str) -> List[str]:
        """Parse AppleScript tag names list (delegates to formatters)."""
        return self.formatters.parse_applescript_tags(tags_str)

    def _build_things_url(self, action: str, parameters: Dict[str, Any]) -> str:
        """Build a Things URL scheme string (delegates to formatters)."""
        return self.formatters.build_things_url(action, parameters, self.auth_token)

    def _split_applescript_output(self, output: str) -> List[str]:
        """Split AppleScript output (delegates to formatters)."""
        return self.formatters.split_applescript_output(output)

    def _has_reminder_time(self, activation_date_str: Optional[str]) -> bool:
        """Detect if an activation_date indicates a reminder (delegates to formatters)."""
        return self.formatters.has_reminder_time(activation_date_str)

    def _extract_reminder_time(self, activation_date_str: Optional[str]) -> Optional[str]:
        """Extract reminder time from activation_date (delegates to formatters)."""
        return self.formatters.extract_reminder_time(activation_date_str)

    def _enhance_record_with_reminder_info(self, record: Dict[str, Any]) -> None:
        """Enhance a record with reminder detection fields (delegates to formatters)."""
        return self.formatters.enhance_record_with_reminder_info(record)

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    async def update_project_direct(self, project_id: str, title: Optional[str] = None,
                                   notes: Optional[str] = None, tags: Optional[List[str]] = None,
                                   when: Optional[str] = None, deadline: Optional[str] = None,
                                   completed: Optional[bool] = None, canceled: Optional[bool] = None) -> Dict[str, Any]:
        """Update a project directly using AppleScript (no URL scheme).

        Args:
            project_id: ID of the project to update
            title: New title
            notes: New notes
            tags: New tags
            when: New schedule
            deadline: New deadline
            completed: Mark as completed
            canceled: Mark as canceled

        Returns:
            Dict with success status and result information
        """
        try:
            # Build the AppleScript to update the project
            script_parts = [
                'tell application "Things3"',
                '    try'
            ]

            # First check if project exists
            script_parts.extend([
                f'        set theProject to project id "{project_id}"',
                '        -- Project exists, proceed with updates'
            ])

            # Update title if provided
            if title is not None:
                escaped_title = title.replace('"', '\\"')
                script_parts.append(f'        set name of theProject to "{escaped_title}"')

            # Update notes if provided
            if notes is not None:
                escaped_notes = notes.replace('"', '\\"').replace('\n', '\\n')
                script_parts.append(f'        set notes of theProject to "{escaped_notes}"')

            # Handle status changes
            if completed is not None:
                if completed:
                    script_parts.append('        set status of theProject to completed')
                elif canceled is not None and canceled:
                    script_parts.append('        set status of theProject to canceled')
                else:
                    script_parts.append('        set status of theProject to open')
            elif canceled is not None:
                if canceled:
                    script_parts.append('        set status of theProject to canceled')
                else:
                    script_parts.append('        set status of theProject to open')

            # Handle tags if provided
            if tags is not None:
                # First clear existing tags, then add new ones
                script_parts.append('        set tag names of theProject to {}')
                if tags:
                    for tag in tags:
                        escaped_tag = tag.replace('"', '\\"')
                        script_parts.extend([
                            '        try',
                            f'            set theTag to tag named "{escaped_tag}"',
                            '        on error',
                            f'            set theTag to make new tag with properties {{name:"{escaped_tag}"}}',
                            '        end try',
                            '        set tag names of theProject to tag names of theProject & {theTag}'
                        ])

            # Handle scheduling if provided
            if when is not None:
                when_lower = when.lower()
                if when_lower == "today":
                    script_parts.append('        set start date of theProject to current date')
                elif when_lower == "tomorrow":
                    script_parts.append('        set start date of theProject to (current date) + 1 * days')
                elif when_lower == "evening":
                    script_parts.append('        set start date of theProject to current date')
                elif when_lower in ["anytime", "someday"]:
                    script_parts.append('        set start date of theProject to missing value')
                else:
                    # Try to parse as date string (YYYY-MM-DD) using locale-aware handler
                    try:
                        date_components = locale_handler.normalize_date_input(when)
                        if date_components:
                            year, month, day = date_components
                            date_expr = locale_handler.build_applescript_date_property(year, month, day)
                            script_parts.append(f'        set start date of theProject to ({date_expr})')
                        else:
                            logger.warning(f"Could not normalize when date: {when}")
                    except Exception as e:
                        logger.warning(f"Error parsing when date '{when}': {e}")

            # Handle deadline if provided
            if deadline is not None:
                try:
                    date_components = locale_handler.normalize_date_input(deadline)
                    if date_components:
                        year, month, day = date_components
                        date_expr = locale_handler.build_applescript_date_property(year, month, day)
                        script_parts.append(f'        set due date of theProject to ({date_expr})')
                    else:
                        logger.warning(f"Could not normalize deadline date: {deadline}")
                except Exception as e:
                    logger.warning(f"Error parsing deadline date '{deadline}': {e}")

            # Close the try block and handle errors
            script_parts.extend([
                '        return "success"',
                '    on error errMsg',
                '        if errMsg contains "Can\'t get project id" then',
                '            return "error:Project not found"',
                '        else',
                '            return "error:" & errMsg',
                '        end if',
                '    end try',
                'end tell'
            ])

            script = '\n'.join(script_parts)
            logger.debug(f"Executing project update script for project {project_id}")

            result = await self.executor.execute_script(script)

            if result.get("success"):
                output = result.get("output", "").strip()
                if output == "success":
                    return {
                        "success": True,
                        "message": "Project updated successfully",
                        "project_id": project_id
                    }
                elif output.startswith("error:"):
                    error_msg = output[6:]  # Remove "error:" prefix
                    return {
                        "success": False,
                        "error": error_msg
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Unexpected output: {output}"
                    }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown AppleScript error")
                }

        except Exception as e:
            logger.error(f"Error updating project {project_id}: {e}")
            return {
                "success": False,
                "error": f"Exception during update: {str(e)}"
            }

    def clear_cache(self) -> None:
        """Clear all cached results - no-op in hybrid implementation."""
        logger.info("Cache clearing requested but caching is disabled in hybrid implementation")

    async def get_todos_due_in_days(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get todos due within specified number of days using efficient 'whose' clause.

        Uses AppleScript's native 'whose' clause for efficient filtering at the database level.

        Args:
            days: Number of days ahead to check for due todos (default: 30)

        Returns:
            List of todo dictionaries with due dates within the specified range
        """
        try:
            # Build AppleScript that uses 'whose' clause for efficient filtering
            script = f'''
            tell application "Things3"
                set nowDate to (current date)
                set cutoffDate to nowDate + ({days} * days)

                -- Use 'whose' clause for efficient filtering at the database level
                -- This is MUCH faster than iterating through all todos
                -- Note: We can't use "is not missing value" in a whose clause, so we just check the date range
                -- AppleScript will automatically skip todos without due dates
                try
                    set matchingTodos to (to dos whose status is open and due date ≥ nowDate and due date ≤ cutoffDate)
                on error
                    set matchingTodos to {{}}
                end try

                set todoRecords to {{}}

                repeat with t in matchingTodos
                    try
                        set todoRecord to {{}}
                        set todoRecord to todoRecord & {{id:(id of t)}}
                        set todoRecord to todoRecord & {{name:(name of t)}}

                        -- Get due date
                        set d to due date of t
                        if d is not missing value then
                            set todoRecord to todoRecord & {{due_date:(d as string)}}
                        end if

                        -- Get status
                        set todoRecord to todoRecord & {{status:(status of t as string)}}

                        -- Get notes if present
                        try
                            set n to notes of t
                            if n is not missing value then
                                set todoRecord to todoRecord & {{notes:n}}
                            end if
                        end try

                        -- Get tags
                        try
                            set todoRecord to todoRecord & {{tag_names:(tag names of t)}}
                        end try

                        -- Get creation and modification dates
                        try
                            set todoRecord to todoRecord & {{creation_date:(creation date of t as string)}}
                            set todoRecord to todoRecord & {{modification_date:(modification date of t as string)}}
                        end try

                        -- Get activation date if present
                        try
                            set a to activation date of t
                            if a is not missing value then
                                set todoRecord to todoRecord & {{activation_date:(a as string)}}
                                -- Check for reminder time
                                set h to hours of a
                                set m to minutes of a
                                if h > 0 or m > 0 then
                                    set todoRecord to todoRecord & {{has_reminder:true}}
                                    set reminderTime to ""
                                    if h < 10 then set reminderTime to "0"
                                    set reminderTime to reminderTime & h & ":"
                                    if m < 10 then set reminderTime to reminderTime & "0"
                                    set reminderTime to reminderTime & m
                                    set todoRecord to todoRecord & {{reminder_time:reminderTime}}
                                else
                                    set todoRecord to todoRecord & {{has_reminder:false}}
                                end if
                            end if
                        end try

                        -- Get project info if available
                        try
                            set p to project of t
                            if p is not missing value then
                                set todoRecord to todoRecord & {{project_id:(id of p)}}
                                set todoRecord to todoRecord & {{project_name:(name of p)}}
                            end if
                        end try

                        -- Get area info if available
                        try
                            set ar to area of t
                            if ar is not missing value then
                                set todoRecord to todoRecord & {{area_id:(id of ar)}}
                                set todoRecord to todoRecord & {{area_name:(name of ar)}}
                            end if
                        end try

                        set end of todoRecords to todoRecord
                    on error errMsg
                        -- Skip problematic todos
                    end try
                end repeat

                return todoRecords
            end tell
            '''

            result = await self.executor.execute_script(script)

            if result.get("success"):
                todos = self._parse_applescript_list(result.get("output", ""))
                logger.info(f"Found {len(todos)} todos due within {days} days")
                return todos
            else:
                logger.error(f"AppleScript error getting todos due in {days} days: {result.get('error')}")
                return []

        except Exception as e:
            logger.error(f"Error getting todos due in {days} days: {e}")
            return []

    async def get_todos_activating_in_days(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get todos with activation dates within specified number of days using efficient 'whose' clause.

        Uses AppleScript's native 'whose' clause for efficient filtering at the database level.

        Args:
            days: Number of days ahead to check for activating todos (default: 30)

        Returns:
            List of todo dictionaries with activation dates within the specified range
        """
        try:
            # Build AppleScript that uses 'whose' clause for efficient filtering
            script = f'''
            tell application "Things3"
                set nowDate to (current date)
                set cutoffDate to nowDate + ({days} * days)

                -- Use 'whose' clause for efficient filtering at the database level
                -- This is MUCH faster than iterating through all todos
                -- Note: We can't use "is not missing value" in a whose clause, so we just check the date range
                -- AppleScript will automatically skip todos without activation dates
                try
                    set matchingTodos to (to dos whose status is open and activation date ≥ nowDate and activation date ≤ cutoffDate)
                on error
                    set matchingTodos to {{}}
                end try

                set todoRecords to {{}}

                repeat with t in matchingTodos
                    try
                        set todoRecord to {{}}
                        set todoRecord to todoRecord & {{id:(id of t)}}
                        set todoRecord to todoRecord & {{name:(name of t)}}

                        -- Get activation date with time info for reminders
                        set a to activation date of t
                        if a is not missing value then
                            set todoRecord to todoRecord & {{activation_date:(a as string)}}
                            -- Check for reminder time
                            set h to hours of a
                            set m to minutes of a
                            if h > 0 or m > 0 then
                                set todoRecord to todoRecord & {{has_reminder:true}}
                                set reminderTime to ""
                                if h < 10 then set reminderTime to "0"
                                set reminderTime to reminderTime & h & ":"
                                if m < 10 then set reminderTime to reminderTime & "0"
                                set reminderTime to reminderTime & m
                                set todoRecord to todoRecord & {{reminder_time:reminderTime}}
                            else
                                set todoRecord to todoRecord & {{has_reminder:false}}
                            end if
                        end if

                        -- Get status
                        set todoRecord to todoRecord & {{status:(status of t as string)}}

                        -- Get due date if present
                        try
                            set d to due date of t
                            if d is not missing value then
                                set todoRecord to todoRecord & {{due_date:(d as string)}}
                            end if
                        end try

                        -- Get notes if present
                        try
                            set n to notes of t
                            if n is not missing value then
                                set todoRecord to todoRecord & {{notes:n}}
                            end if
                        end try

                        -- Get tags
                        try
                            set todoRecord to todoRecord & {{tag_names:(tag names of t)}}
                        end try

                        -- Get creation and modification dates
                        try
                            set todoRecord to todoRecord & {{creation_date:(creation date of t as string)}}
                            set todoRecord to todoRecord & {{modification_date:(modification date of t as string)}}
                        end try

                        -- Get project info if available
                        try
                            set p to project of t
                            if p is not missing value then
                                set todoRecord to todoRecord & {{project_id:(id of p)}}
                                set todoRecord to todoRecord & {{project_name:(name of p)}}
                            end if
                        end try

                        -- Get area info if available
                        try
                            set ar to area of t
                            if ar is not missing value then
                                set todoRecord to todoRecord & {{area_id:(id of ar)}}
                                set todoRecord to todoRecord & {{area_name:(name of ar)}}
                            end if
                        end try

                        set end of todoRecords to todoRecord
                    on error errMsg
                        -- Skip problematic todos
                    end try
                end repeat

                return todoRecords
            end tell
            '''

            result = await self.executor.execute_script(script)

            if result.get("success"):
                todos = self._parse_applescript_list(result.get("output", ""))
                logger.info(f"Found {len(todos)} todos activating within {days} days")
                return todos
            else:
                logger.error(f"AppleScript error getting todos activating in {days} days: {result.get('error')}")
                return []

        except Exception as e:
            logger.error(f"Error getting todos activating in {days} days: {e}")
            return []

    async def get_todos_upcoming_in_days(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get todos due or activating within specified number of days (union).

        Combines results from due dates and activation dates, removing duplicates.

        Args:
            days: Number of days ahead to check (default: 30)

        Returns:
            List of unique todo dictionaries due or activating within the range
        """
        try:
            # Get todos with due dates
            due_todos = await self.get_todos_due_in_days(days)

            # Get todos with activation dates
            activating_todos = await self.get_todos_activating_in_days(days)

            # Combine and de-duplicate by ID
            seen_ids = set()
            combined_todos = []

            # Add all due todos
            for todo in due_todos:
                todo_id = todo.get('id')
                if todo_id:
                    seen_ids.add(todo_id)
                    combined_todos.append(todo)

            # Add activating todos that aren't already in the list
            for todo in activating_todos:
                todo_id = todo.get('id')
                if todo_id and todo_id not in seen_ids:
                    combined_todos.append(todo)

            return combined_todos

        except Exception as e:
            logger.error(f"Error getting upcoming todos in {days} days: {e}")
            return []
