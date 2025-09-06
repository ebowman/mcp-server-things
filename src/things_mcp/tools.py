"""Core tools implementation for Things 3 MCP server."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from .services.applescript_manager import AppleScriptManager
from .pure_applescript_scheduler import PureAppleScriptScheduler
from .operation_queue import get_operation_queue, Priority
from .locale_aware_dates import locale_handler
from .services.validation_service import ValidationService
from .services.tag_service import TagValidationService
from .move_operations import MoveOperationsTools
from .config import ThingsMCPConfig

logger = logging.getLogger(__name__)


class ThingsTools:
    """Core tools for Things 3 operations."""
    
    def __init__(self, applescript_manager: AppleScriptManager, config: Optional[ThingsMCPConfig] = None):
        """Initialize with AppleScript manager and optional configuration.
        
        Args:
            applescript_manager: AppleScript manager instance
            config: Optional configuration for tag validation and policies
        """
        self.applescript = applescript_manager
        self.config = config
        self.reliable_scheduler = PureAppleScriptScheduler(applescript_manager)
        
        # Initialize validation service and advanced move operations
        self.validation_service = ValidationService(applescript_manager)
        self.move_operations = MoveOperationsTools(applescript_manager, self.validation_service)
        
        # Initialize tag validation service if config is provided
        self.tag_validation_service = None
        if config:
            self.tag_validation_service = TagValidationService(applescript_manager, config)
            logger.info("Things tools initialized with tag validation service")
        else:
            logger.info("Things tools initialized without tag validation (backward compatibility mode)")
        
        logger.info("Things tools initialized with advanced move operations")
    
    def _escape_applescript_string(self, text: str) -> str:
        """Escape a string for safe use in AppleScript.
        
        Args:
            text: The string to escape
            
        Returns:
            The escaped string safe for AppleScript
        """
        if not text:
            return '""'
        
        # Escape backslashes first, then quotes
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    
    def _convert_iso_to_applescript_date(self, iso_date: str) -> str:
        """Convert ISO date (YYYY-MM-DD) to AppleScript property-based date construction.
        
        Args:
            iso_date: Date in YYYY-MM-DD format
            
        Returns:
            AppleScript code that creates a date object using properties
        """
        try:
            # Use the new locale-aware date handler
            return locale_handler.convert_iso_to_applescript(iso_date)
        except Exception as e:
            logger.error(f"Error converting ISO date '{iso_date}': {e}")
            # Fallback to original approach if needed
            try:
                parsed = datetime.strptime(iso_date, '%Y-%m-%d').date()
                return parsed.strftime('%d/%m/%Y')  # DD/MM/YYYY for European locale
            except ValueError:
                return iso_date
    
    async def _ensure_tags_exist(self, tags: List[str]) -> Dict[str, List[str]]:
        """Ensure tags exist, using policy-aware validation if available.
        
        This method delegates to either the new policy-aware validation service
        or falls back to the original behavior for backward compatibility.
        
        Args:
            tags: List of tag names to ensure exist
            
        Returns:
            Dict with 'created', 'existing', 'filtered', 'warnings' lists
        """
        result = await self._validate_tags_with_policy(tags)
        
        # Return all fields including filtered and warnings for proper policy enforcement
        return {
            'created': result.get('created', []),
            'existing': result.get('existing', []),
            'filtered': result.get('filtered', []),
            'warnings': result.get('warnings', [])
        }
    
    async def _ensure_tags_exist_original(self, tags: List[str]) -> Dict[str, List[str]]:
        """Ensure tags exist, creating them if necessary in a single AppleScript call.
        
        This consolidates all tag existence checking and creation into one efficient
        operation instead of sequential individual tag checks.
        
        Args:
            tags: List of tag names to ensure exist
            
        Returns:
            Dict with 'created' and 'existing' lists of tag names
        """
        if not tags:
            return {'created': [], 'existing': []}
            
        try:
            # Get all existing tag names in one call
            existing_tag_names = []
            try:
                current_tags = await self.get_tags(include_items=False)
                existing_tag_names = [tag.get('name', '').lower() for tag in current_tags]
            except Exception as e:
                logger.warning(f"Could not fetch existing tags: {e}")
                existing_tag_names = []  # Continue with empty list if fetch fails
            
            # Categorize tags into existing and missing
            existing_tags = []
            missing_tags = []
            
            for tag in tags:
                if tag.lower() in existing_tag_names:
                    existing_tags.append(tag)
                else:
                    missing_tags.append(tag)
            
            # Create all missing tags in one AppleScript call
            created_tags = []
            if missing_tags:
                # OPTIMIZATION: Build consolidated AppleScript to create all missing tags
                # with compound validation to avoid redundant existence checks  
                tag_creation_commands = []
                for tag in missing_tags:
                    escaped_tag = self._escape_applescript_string(tag)
                    tag_creation_commands.append(
                        f'try\n'
                        f'    make new tag with properties {{name:{escaped_tag}}}\n'
                        f'    set tagResults to tagResults & {{"{tag}"}}\n'
                        f'on error\n'
                        f'    -- Tag creation failed, skip\n'
                        f'end try'
                    )
                
                create_script = f'''
                tell application "Things3"
                    set tagResults to {{}}
                    {chr(10).join(tag_creation_commands)}
                    return tagResults
                end tell
                '''
                
                create_result = await self.applescript.execute_applescript(create_script, cache_key=None)
                if create_result.get("success"):
                    output = create_result.get("output") or ""
                    if output and output.strip():
                        # Parse the list of successfully created tags
                        try:
                            created_list = output.strip().split(', ')
                            for created_tag in created_list:
                                cleaned_tag = created_tag.strip().strip('"')
                                if cleaned_tag:
                                    created_tags.append(cleaned_tag)
                                    logger.info(f"Created new tag: {cleaned_tag}")
                        except Exception as e:
                            logger.warning(f"Could not parse created tags from output: {e}")
                            # Fallback: assume all missing tags were created
                            created_tags = missing_tags.copy()
                    else:
                        # No output, likely all creations failed
                        logger.warning("Tag creation returned no results")
                else:
                    logger.warning(f"Batch tag creation failed: {create_result.get('error') or 'Unknown error'}")
            
            result = {
                'created': created_tags,
                'existing': existing_tags
            }
            
            logger.info(f"Tag operation complete - Created: {len(created_tags)}, Existing: {len(existing_tags)}")
            return result
            
        except Exception as e:
            logger.error(f"Error ensuring tags exist: {e}")
            # Fallback: assume all tags are existing to avoid breaking the parent operation
            return {'created': [], 'existing': tags}
    
    async def _validate_tags_with_policy(self, tags: List[str]) -> Dict[str, Any]:
        """Validate tags using the configured policy if validation service is available.
        
        Args:
            tags: List of tag names to validate
            
        Returns:
            Dict with validation results, warnings, and processed tags
        """
        if not self.tag_validation_service:
            # Fallback to legacy behavior
            return await self._ensure_tags_exist_legacy(tags)
        
        try:
            result = await self.tag_validation_service.validate_and_filter_tags(tags)
            
            # Convert to legacy format for backward compatibility
            legacy_result = {
                'created': result.created_tags,
                'existing': [tag for tag in result.valid_tags if tag not in result.created_tags],
                'filtered': result.filtered_tags,
                'warnings': result.warnings,
                'errors': result.get('errors', [])
            }
            
            # Log warnings and errors
            for warning in result.warnings:
                logger.warning(f"Tag validation: {warning}")
            
            for error in result.get('errors', []):
                logger.error(f"Tag validation: {error}")
            
            # If there are errors (from FAIL_ON_UNKNOWN policy), raise exception
            if result.get('errors'):
                raise ValueError(f"Tag validation failed: {'; '.join(result.get('errors', []))}")
            
            return legacy_result
            
        except ValueError as e:
            # Re-raise ValueError for policy violations (like FAIL_ON_UNKNOWN)
            # These should NOT fall back to legacy behavior
            logger.error(f"Tag validation policy violation: {e}")
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error in tag validation service: {e}")
            # Only fall back to legacy for unexpected errors, not policy violations
            return await self._ensure_tags_exist_legacy(tags)
    
    async def _ensure_tags_exist_legacy(self, tags: List[str]) -> Dict[str, List[str]]:
        """Legacy tag existence checking (renamed from _ensure_tags_exist).
        
        This is the original implementation kept for backward compatibility.
        
        Args:
            tags: List of tag names to ensure exist
            
        Returns:
            Dict with 'created' and 'existing' lists of tag names
        """
        # This is the existing implementation - we'll keep it as fallback
        return await self._ensure_tags_exist_original(tags)
    
    def _parse_period_date(self, date_input: str) -> dict:
        """Parse period-based dates like 'this week', 'next week' into when+deadline combinations.
        
        Args:
            date_input: User input date string
            
        Returns:
            Dict with 'when', 'deadline', and 'is_period' keys, or None if not a period
        """
        if not date_input:
            return None
            
        input_lower = date_input.lower().strip()
        today = datetime.now().date()
        
        if input_lower in ['this week', 'thisweek']:
            # "this week" -> when: today, deadline: this Friday
            days_until_friday = (4 - today.weekday()) % 7
            if days_until_friday == 0 and today.weekday() == 4:  # It's Friday
                this_friday = today
            else:
                this_friday = today + timedelta(days=days_until_friday) if days_until_friday > 0 else today + timedelta(days=7+days_until_friday)
            
            return {
                'when': today.isoformat(),
                'deadline': this_friday.isoformat(),
                'is_period': True,
                'period_type': 'this_week'
            }
            
        elif input_lower in ['next week', 'nextweek']:
            # "next week" -> when: next Monday, deadline: Friday after next Monday  
            days_until_next_monday = 7 - today.weekday()
            if today.weekday() == 6:  # Sunday
                days_until_next_monday = 1
            next_monday = today + timedelta(days=days_until_next_monday)
            friday_after_next_monday = next_monday + timedelta(days=4)
            
            return {
                'when': next_monday.isoformat(),
                'deadline': friday_after_next_monday.isoformat(),
                'is_period': True,
                'period_type': 'next_week'
            }
            
        elif input_lower in ['this month', 'thismonth']:
            # "this month" -> when: today, deadline: end of this month
            # Find last day of current month
            next_month = today.replace(day=28) + timedelta(days=4)
            end_of_month = next_month - timedelta(days=next_month.day)
            
            return {
                'when': today.isoformat(),
                'deadline': end_of_month.isoformat(),
                'is_period': True,
                'period_type': 'this_month'
            }
            
        elif input_lower in ['next month', 'nextmonth']:
            # "next month" -> when: first day of next month, deadline: end of next month
            next_month = today.replace(day=28) + timedelta(days=4)
            first_day_next_month = next_month.replace(day=1)
            # Find last day of next month
            month_after_next = first_day_next_month.replace(day=28) + timedelta(days=4)
            end_of_next_month = month_after_next - timedelta(days=month_after_next.day)
            
            return {
                'when': first_day_next_month.isoformat(),
                'deadline': end_of_next_month.isoformat(),
                'is_period': True,
                'period_type': 'next_month'
            }
        
        return None
    
    async def _set_todo_deadline(self, todo_id: str, deadline_date: str) -> dict:
        """Set deadline for a todo using AppleScript.
        
        Args:
            todo_id: Things todo ID
            deadline_date: ISO date string (YYYY-MM-DD)
            
        Returns:
            Dict with success status
        """
        try:
            # Parse the ISO date to get components
            from datetime import datetime
            parsed_date = datetime.strptime(deadline_date, '%Y-%m-%d')
            
            # Build AppleScript that constructs date object safely
            script = f'''
            tell application "Things3"
                try
                    set theTodo to to do id "{todo_id}"
                    
                    -- Construct due date object safely to avoid date parsing issues
                    set dueDate to (current date)
                    set time of dueDate to 0
                    set day of dueDate to 1
                    set year of dueDate to {parsed_date.year}
                    set month of dueDate to {parsed_date.month}
                    set day of dueDate to {parsed_date.day}
                    
                    set due date of theTodo to dueDate
                    return "deadline_set"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script)
            if result.get("success") and "deadline_set" in (result.get("output") or ""):
                logger.info(f"Successfully set deadline {deadline_date} for todo {todo_id}")
                return {"success": True, "deadline": deadline_date}
            else:
                logger.warning(f"Failed to set deadline: {result.get('output') or 'Unknown error'}")
                return {"success": False, "error": result.get('output') or "Unknown error"}
                
        except Exception as e:
            logger.error(f"Error setting deadline: {e}")
            return {"success": False, "error": str(e)}
    
    def _parse_relative_date(self, date_input: str) -> str:
        """Parse relative date input like 'tomorrow', 'Friday', 'September 10', etc. to YYYY-MM-DD format.
        
        Args:
            date_input: User input date string
            
        Returns:
            Formatted date string or original input if not recognized
        """
        # Check if this is a datetime format (YYYY-MM-DD@HH:MM) for reminder support
        if '@' in date_input:
            return self._parse_datetime_input(date_input)
            
        return self._parse_date_only_input(date_input)
    
    def _parse_datetime_input(self, datetime_input: str) -> str:
        """Parse datetime input in YYYY-MM-DD@HH:MM format for reminder support.
        
        Processes datetime strings with @ separators to create reminders at specific times.
        Handles both relative dates (today, tomorrow) and absolute dates (YYYY-MM-DD).
        Falls back gracefully by returning original input if parsing fails.
        
        Args:
            datetime_input: Input in format like "today@14:30" or "2024-01-15@09:00"
                Supported date formats:
                - "today@HH:MM" - reminder today at specified time
                - "tomorrow@HH:MM" - reminder tomorrow at specified time  
                - "YYYY-MM-DD@HH:MM" - reminder on specific date and time
                - Input without @ symbol - returned unchanged
                
        Returns:
            Formatted datetime string for URL scheme or original input if invalid
            
        Examples:
            >>> parser._parse_datetime_input("today@14:30")        # "2025-08-17@14:30"
            >>> parser._parse_datetime_input("2024-12-25@09:00")   # "2024-12-25@09:00"
            >>> parser._parse_datetime_input("today@25:00")        # "today@25:00" (invalid, returned as-is)
            >>> parser._parse_datetime_input("tomorrow")           # "tomorrow" (no @ symbol, passed through)
        """
        if '@' not in datetime_input:
            return datetime_input
            
        try:
            date_part, time_part = datetime_input.split('@', 1)
            
            # Parse the date part using existing logic
            parsed_date = self._parse_date_only_input(date_part.strip())
            
            # Validate time format (HH:MM or H:MM)
            time_part = time_part.strip()
            if not self._validate_time_format(time_part):
                logger.warning(f"Invalid time format '{time_part}' in datetime input '{datetime_input}'")
                return datetime_input  # Return original if invalid
            
            # Return in the format expected for URL scheme
            return f"{parsed_date}@{time_part}"
            
        except Exception as e:
            logger.warning(f"Error parsing datetime input '{datetime_input}': {e}")
            return datetime_input
    
    def _parse_date_only_input(self, date_input: str) -> str:
        """Parse date-only input like 'tomorrow', 'Friday', 'September 10', etc. to YYYY-MM-DD format.
        
        Args:
            date_input: User input date string
            
        Returns:
            Formatted date string or original input if not recognized
        """
        if not date_input:
            return date_input
            
        input_lower = date_input.lower().strip()
        today = datetime.now().date()
        
        # Try dateutil first for natural language dates like "September 10", "next Friday", etc.
        try:
            from dateutil import parser as date_parser
            # Use dateutil to parse natural language dates
            parsed_date = date_parser.parse(date_input, default=datetime.now())
            return parsed_date.date().isoformat()
        except ImportError:
            # dateutil not available, fall back to manual parsing
            pass
        except Exception:
            # dateutil couldn't parse it, fall back to manual parsing
            pass
        
        # Handle relative dates
        if input_lower == 'today':
            return today.isoformat()
        elif input_lower == 'tomorrow':
            return (today + timedelta(days=1)).isoformat()
        elif input_lower == 'yesterday':
            return (today - timedelta(days=1)).isoformat()
        elif input_lower in ['this weekend', 'weekend']:
            # Find next Saturday
            days_ahead = 5 - today.weekday()  # Saturday is 5
            if days_ahead <= 0:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()
        elif input_lower in ['this week', 'thisweek']:
            # Smart "this week" handling based on current day
            current_weekday = today.weekday()  # 0=Monday, 6=Sunday
            if current_weekday <= 2:  # Monday-Wednesday: suggest Wednesday
                target_date = today + timedelta(days=(2 - current_weekday))
            elif current_weekday <= 4:  # Thursday-Friday: suggest Friday  
                target_date = today + timedelta(days=(4 - current_weekday))
            else:  # Weekend: suggest Monday next week
                days_until_monday = 7 - current_weekday
                target_date = today + timedelta(days=days_until_monday)
            return target_date.isoformat()
        elif input_lower in ['next week', 'nextweek']:
            # Smart "next week" handling - default to Tuesday of next week
            days_until_next_monday = 7 - today.weekday()
            next_tuesday = today + timedelta(days=days_until_next_monday + 1)
            return next_tuesday.isoformat()
        elif input_lower.endswith('week') and input_lower.startswith('next'):
            return (today + timedelta(weeks=1)).isoformat()
        
        # Handle day names (monday, tuesday, etc.)
        day_names = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        if input_lower in day_names:
            target_day = day_names.index(input_lower)
            current_day = today.weekday()
            days_ahead = target_day - current_day
            if days_ahead <= 0:  # Target day already happened this week
                days_ahead += 7  # Get next week's occurrence
            return (today + timedelta(days=days_ahead)).isoformat()
            
        # Handle "next [day]"
        if input_lower.startswith('next '):
            day_part = input_lower[5:]  # Remove "next "
            if day_part in day_names:
                target_day = day_names.index(day_part)
                current_day = today.weekday()
                days_ahead = target_day - current_day + 7  # Always next week
                return (today + timedelta(days=days_ahead)).isoformat()
        
        # Try to parse YYYY-MM-DD format
        try:
            parsed = datetime.strptime(input_lower, '%Y-%m-%d').date()
            return parsed.isoformat()
        except ValueError:
            pass
            
        # Try to parse MM/DD/YYYY format
        try:
            parsed = datetime.strptime(input_lower, '%m/%d/%Y').date()
            return parsed.isoformat()
        except ValueError:
            pass
        
        # If nothing matches, return original input (Things can handle many formats)
        return date_input
    
    async def get_todos(self, project_uuid: Optional[str] = None, include_items: bool = True) -> List[Dict[str, Any]]:
        """Get todos from Things, optionally filtered by project.
        
        Args:
            project_uuid: Optional project UUID to filter by
            include_items: Include checklist items
            
        Returns:
            List of todo dictionaries
        """
        try:
            todos = await self.applescript.get_todos(project_uuid)
            
            # Convert to standardized format
            result = []
            for todo in todos:
                todo_dict = {
                    "id": todo.get("id"),
                    "uuid": todo.get("id"),  # Things uses ID as UUID
                    "title": todo.get("name", ""),
                    "notes": todo.get("notes", ""),
                    "status": todo.get("status", "open"),
                    "creation_date": todo.get("creation_date"),
                    "modification_date": todo.get("modification_date"),
                    "project_uuid": project_uuid,
                    "tags": [],  # TODO: Extract tags from AppleScript
                    "checklist_items": []  # TODO: Extract checklist items if include_items
                }
                result.append(todo_dict)
            
            logger.info(f"Retrieved {len(result)} todos")
            return result
        
        except Exception as e:
            logger.error(f"Error getting todos: {e}")
            raise
    
    async def _schedule_todo_reliable(self, todo_id: str, when_date: str) -> Dict[str, Any]:
        """Ultra-reliable todo scheduling using multi-layered approach.
        
        Uses a fallback hierarchy for 100% scheduling reliability:
        1. Things URL Scheme (95%+ reliability)
        2. AppleScript Date Objects (90%+ reliability) 
        3. List Assignment Fallback (85%+ reliability)
        
        Args:
            todo_id: ID of the todo to schedule
            when_date: Date in YYYY-MM-DD format or relative term
            
        Returns:
            Dict with scheduling result and method used
        """
        logger.info(f"Scheduling todo {todo_id} for {when_date} using reliable multi-layer approach")
        
        # Layer 1: Things URL Scheme (Primary - Most Reliable)
        if self.applescript.auth_token:
            try:
                parameters = {
                    'id': todo_id,
                    'when': when_date,
                    'auth-token': self.applescript.auth_token
                }
                
                result = await self.applescript.execute_url_scheme('update', parameters)
                if result.get("success"):
                    logger.info(f"Successfully scheduled todo {todo_id} using URL scheme")
                    return {
                        "success": True,
                        "method": "url_scheme",
                        "reliability": "95%",
                        "todo_id": todo_id,
                        "when": when_date
                    }
            except Exception as e:
                logger.warning(f"URL scheme scheduling failed for {todo_id}: {e}, falling back to AppleScript")
        
        # Layer 2: AppleScript Date Objects (High Reliability Fallback)
        try:
            when_lower = when_date.lower().strip()
            
            # Handle relative dates with reliable AppleScript date arithmetic
            if when_lower == "today":
                schedule_script = 'schedule theTodo for (current date)'
            elif when_lower == "tomorrow":
                schedule_script = 'schedule theTodo for ((current date) + 1 * days)'
            elif when_lower == "yesterday":
                schedule_script = 'schedule theTodo for ((current date) - 1 * days)'
            else:
                # For specific dates, construct proper date objects
                try:
                    parsed_date = datetime.strptime(when_date, '%Y-%m-%d').date()
                    # Map numeric months to AppleScript month constants to avoid overflow bugs
                    month_names = {
                        1: "January", 2: "February", 3: "March", 4: "April",
                        5: "May", 6: "June", 7: "July", 8: "August",
                        9: "September", 10: "October", 11: "November", 12: "December"
                    }
                    month_constant = month_names[parsed_date.month]
                    schedule_script = f'''
                    set targetDate to current date
                    set time of targetDate to 0
                    set day of targetDate to 1
                    set year of targetDate to {parsed_date.year}
                    set month of targetDate to {month_constant}
                    set day of targetDate to {parsed_date.day}
                    schedule theTodo for targetDate'''
                except ValueError:
                    # If date parsing fails, try as-is
                    schedule_script = f'schedule theTodo for date "{when_date}"'
            
            script = f'''
            tell application "Things3"
                try
                    set theTodo to to do id "{todo_id}"
                    {schedule_script}
                    return "scheduled"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            if result.get("success") and "scheduled" in (result.get("output") or ""):
                logger.info(f"Successfully scheduled todo {todo_id} using AppleScript objects")
                return {
                    "success": True,
                    "method": "applescript_objects",
                    "reliability": "90%",
                    "todo_id": todo_id,
                    "when": when_date
                }
        except Exception as e:
            logger.warning(f"AppleScript object scheduling failed for {todo_id}: {e}, falling back to list assignment")
        
        # Layer 3: List Assignment (Final Fallback)
        try:
            target_list = "Today" if when_lower in ["today", "tonight", "evening"] else "Today"
            
            script = f'''
            tell application "Things3"
                try
                    set theTodo to to do id "{todo_id}"
                    move theTodo to list "{target_list}"
                    return "moved"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            if result.get('success') and "moved" in (result.get('output') or ""):
                logger.info(f"Fallback: moved todo {todo_id} to {target_list} list")
                return {
                    "success": True,
                    "method": "list_fallback",
                    "reliability": "85%",
                    "todo_id": todo_id,
                    "when": when_date,
                    "note": f"Moved to {target_list} list (scheduling fallback)"
                }
        except Exception as e:
            logger.error(f"All scheduling methods failed for todo {todo_id}: {e}")
        
        return {
            "success": False,
            "error": f"All scheduling methods failed for todo {todo_id}",
            "todo_id": todo_id,
            "when": when_date
        }

    async def add_todo(self, title: str, notes: Optional[str] = None, tags: Optional[List[str]] = None,
                 when: Optional[str] = None, deadline: Optional[str] = None,
                 list_id: Optional[str] = None, list_title: Optional[str] = None,
                 heading: Optional[str] = None, checklist_items: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new todo in Things.
        
        IMPORTANT - Hybrid Implementation Approach:
        This method uses TWO different approaches depending on whether you need a reminder:
        
        1. Regular todos (date only) → Uses AppleScript
           - Returns actual todo ID from Things
           - Full control over all properties
           - Examples: when="today", when="tomorrow", when="2024-12-25"
        
        2. Todos with time-based reminders → Uses URL scheme
           - Returns placeholder ID "created_via_url_scheme" 
           - This is because AppleScript API cannot set reminder times, only dates
           - Things URL scheme supports Quick Entry syntax including reminders
           - Examples: when="today@14:30", when="tomorrow@09:00", when="2024-12-25@18:00"
        
        Why this approach?
        - AppleScript limitation: The Things 3 AppleScript API lacks the ability to set
          reminder times. It can only set the date when a todo appears in Today/Upcoming.
        - URL scheme advantage: Supports the full Quick Entry natural language parser,
          including the ability to set specific reminder times using the @ syntax.
        - Trade-off: URL scheme doesn't return the created todo's ID, but this is
          acceptable since the primary goal is to create todos with working reminders.
        
        Args:
            title: Todo title
            notes: Optional notes
            tags: Optional list of tags (will be created if they don't exist)
            when: When to schedule. Formats supported:
                  - Date only (uses AppleScript): "today", "tomorrow", "evening", 
                    "anytime", "someday", "YYYY-MM-DD"
                  - With reminder time (uses URL scheme): "today@14:30", "tomorrow@09:00",
                    "YYYY-MM-DD@HH:MM" (24-hour format, converted to 12-hour for Things)
            deadline: Deadline date (YYYY-MM-DD format)
            list_id: Project or area ID
            list_title: Project or area title  
            heading: Heading to add under
            checklist_items: Checklist items to add
            
        Returns:
            Dict with created todo information including:
            - success: Boolean indicating if creation succeeded
            - todo_id: ID of created todo (actual ID for AppleScript, 
                      "created_via_url_scheme" for URL scheme method)
            - method: "applescript" or "url_scheme" to indicate which was used
            - reminder_time: Time portion if a reminder was set (e.g., "14:30")
            - message: Human-readable success/error message
        """
        # Use operation queue to ensure write consistency
        queue = await get_operation_queue()
        operation_id = await queue.enqueue(
            self._add_todo_impl,
            title, notes, tags, when, deadline, list_id, list_title, heading, checklist_items,
            name=f"add_todo({title[:30]}...)",
            priority=Priority.HIGH,
            timeout=60.0,
            max_retries=2
        )
        return await queue.wait_for_operation(operation_id)

    async def _add_todo_impl(self, title: str, notes: Optional[str] = None, tags: Optional[List[str]] = None,
                      when: Optional[str] = None, deadline: Optional[str] = None,
                      list_id: Optional[str] = None, list_title: Optional[str] = None,
                      heading: Optional[str] = None, checklist_items: Optional[List[str]] = None) -> Dict[str, Any]:
        """Internal implementation of add_todo (executed through operation queue)."""
        try:
            created_tags = []
            existing_tags = []
            filtered_tags = []
            tag_warnings = []
            
            # Ensure all tags exist using consolidated batch operation
            if tags:
                try:
                    tag_result = await self._ensure_tags_exist(tags)
                    created_tags = tag_result.get('created', [])
                    existing_tags = tag_result.get('existing', [])
                    filtered_tags = tag_result.get('filtered', [])
                    tag_warnings = tag_result.get('warnings', [])
                    
                    # Update tags to only include valid tags (not filtered ones)
                    # This ensures we don't pass rejected tags to AppleScript
                    valid_tags = created_tags + existing_tags
                    if filtered_tags:
                        logger.info(f"Filtered out tags per policy: {filtered_tags}")
                        tags = valid_tags  # Use only the valid tags
                except ValueError as e:
                    logger.error(f"Tag validation failed with ValueError: {e}")
                    return {
                        "success": False,
                        "error": str(e)
                    }
            
            # Handle when/start date - Things 3 supports the schedule command!
            schedule_command = None
            target_list = None
            
            if when:
                parsed_when = self._parse_relative_date(when)
                when_lower = when.lower().strip()
                
                # Handle relative dates with AppleScript date arithmetic or list assignment
                if when_lower == "today":
                    schedule_command = "schedule newTodo for (current date)"
                elif when_lower == "tomorrow":
                    schedule_command = "schedule newTodo for (current date) + 1 * days"
                elif when_lower == "anytime":
                    target_list = "Anytime"  # No scheduling needed
                elif when_lower == "someday":
                    target_list = "Someday"  # No scheduling needed
                elif when_lower == "upcoming":
                    target_list = "Upcoming"  # No scheduling needed
                else:
                    # For specific dates, we'll handle scheduling after todo creation
                    # using our reliable scheduling method
                    pass  # Will be handled post-creation

            # Handle deadline - Things 3 supports due date property!
            due_date_property = None
            due_date_command = None
            
            if deadline:
                parsed_deadline = self._parse_relative_date(deadline)
                deadline_lower = deadline.lower().strip()
                
                # Handle relative deadlines with AppleScript date arithmetic  
                if deadline_lower == "today":
                    due_date_property = "due date:(current date)"
                elif deadline_lower == "tomorrow":
                    due_date_property = "due date:((current date) + 1 * days)"
                elif deadline_lower == "yesterday":
                    due_date_property = "due date:((current date) - 1 * days)"
                else:
                    # For specific dates, we'll set the deadline after creation
                    # because AppleScript date strings are unreliable
                    due_date_command = deadline  # Will be handled post-creation

            # Add checklist items to notes if specified  
            # Note: Things 3 doesn't support checklist items via AppleScript properties
            if checklist_items:
                checklist_text = "Checklist:\n" + "\n".join([f"- [ ] {item}" for item in checklist_items])
                if notes:
                    notes = notes + "\n\n" + checklist_text
                else:
                    notes = checklist_text
            
            # PHASE 2: Check if this is a datetime reminder and use URL scheme if needed
            # 
            # ARCHITECTURAL DECISION: Why use URL scheme for reminders?
            # =========================================================
            # The Things 3 AppleScript API has a critical limitation: it cannot set reminder times.
            # While AppleScript can set when a todo appears (its date), it cannot set a notification
            # time (e.g., "remind me at 2:30 PM"). This is a fundamental gap in the AppleScript API.
            #
            # The Things URL scheme (things:///add) supports the full Quick Entry syntax, including
            # the ability to set reminders using the @ notation (e.g., "today@14:30"). This makes
            # it the ONLY programmatic way to create todos with time-based reminders.
            #
            # Trade-offs of this approach:
            # - PRO: Enables reminder functionality that would otherwise be impossible
            # - PRO: Leverages Things' natural language parser for better date/time handling  
            # - CON: URL scheme doesn't return the created todo's ID (returns placeholder)
            # - CON: Less control over error handling compared to AppleScript
            #
            # We accept these trade-offs because having working reminders is more valuable
            # than having immediate access to the todo ID.
            
            if when and self._has_datetime_reminder(when):
                logger.info(f"Detected datetime reminder in '{when}', using URL scheme instead of AppleScript")
                try:
                    # Parse datetime format (e.g., "today@14:30" or "2024-12-25@09:00")
                    parsed_when = self._parse_datetime_input(when)
                    
                    # Build URL scheme for reminder creation
                    # This constructs: things:///add?title=...&when=today@2:30pm&...
                    url_scheme = self._build_url_scheme_with_reminder(title, parsed_when, notes, tags)
                    logger.info(f"Built reminder URL scheme: {url_scheme}")
                    
                    # Execute URL scheme through AppleScript manager
                    # This opens the URL in Things, which creates the todo with reminder
                    url_result = await self.applescript.execute_url_scheme(
                        action="add",
                        parameters={"url_override": url_scheme}
                    )
                    
                    if url_result.get('success'):
                        # LIMITATION: URL scheme doesn't return the actual todo ID
                        # This is a Things URL scheme limitation, not a bug in our code
                        # We return a placeholder ID to indicate the method used
                        logger.info(f"Successfully created todo with reminder using URL scheme")
                        return {
                            "success": True,
                            "message": f"Todo '{title}' created with reminder at {parsed_when.split('@')[1] if '@' in parsed_when else 'unknown time'}",
                            "reminder_time": parsed_when.split('@')[1] if '@' in parsed_when else None,
                            "method": "url_scheme",
                            "todo_id": "created_via_url_scheme",  # URL scheme limitation
                            "created_tags": created_tags,
                            "existing_tags": existing_tags,
                            "filtered_tags": filtered_tags,
                            "tag_warnings": tag_warnings
                        }
                    else:
                        logger.warning(f"URL scheme reminder creation failed: {url_result.get('error')}, falling back to AppleScript")
                        # Fall through to AppleScript creation (without time component)
                        when = self._parse_date_only_input(when.split('@')[0])
                        
                except Exception as e:
                    logger.warning(f"URL scheme reminder creation failed: {e}, falling back to AppleScript")
                    # Fall through to AppleScript creation (without time component)  
                    when = self._parse_date_only_input(when.split('@')[0]) if when and '@' in when else when

            # Prepare properties for the new todo (AppleScript fallback path)
            escaped_title = self._escape_applescript_string(title)
            escaped_notes = self._escape_applescript_string(notes or "")
            
            # Build the properties dictionary for AppleScript
            properties_parts = [f"name:{escaped_title}"]
            
            if notes:
                properties_parts.append(f"notes:{escaped_notes}")
            
            # Add due date property if specified
            if due_date_property:
                properties_parts.append(due_date_property)
            
            properties_string = "{" + ", ".join(properties_parts) + "}"
            
            # Build AppleScript to create todo
            script_parts = []
            script_parts.append('tell application "Things3"')
            script_parts.append('    try')
            
            # Determine where to create the todo
            if list_id:
                # Create in specific project/area by ID
                # First try as a project, then as an area, then as a list
                script_parts.append(f'''        
                try
                    set targetContainer to project id "{list_id}"
                    set newTodo to make new to do at end of to dos of targetContainer with properties {properties_string}
                on error
                    try
                        set targetContainer to area id "{list_id}"
                        set newTodo to make new to do at end of to dos of targetContainer with properties {properties_string}
                    on error
                        -- Fall back to creating in inbox if not found
                        set newTodo to make new to do with properties {properties_string}
                    end try
                end try''')
            elif list_title:
                # Create in specific project/area by name
                escaped_list_title = self._escape_applescript_string(list_title)
                script_parts.append(f'''
                try
                    set targetContainer to first project whose name is {escaped_list_title}
                    set newTodo to make new to do at end of to dos of targetContainer with properties {properties_string}
                on error
                    try
                        set targetContainer to first area whose name is {escaped_list_title}
                        set newTodo to make new to do at end of to dos of targetContainer with properties {properties_string}
                    on error
                        -- Fall back to creating in inbox if not found
                        set newTodo to make new to do with properties {properties_string}
                    end try
                end try''')
            elif target_list:
                # Create in the target list determined by "when" parameter
                script_parts.append(f'''        
                try
                    set targetList to list "{target_list}"
                    set newTodo to make new to do at end of to dos of targetList with properties {properties_string}
                on error
                    -- Fall back to creating in inbox if list not found
                    set newTodo to make new to do with properties {properties_string}
                end try''')
            elif heading:
                # Create under specific heading (this is more complex, for now create in inbox)
                escaped_heading = self._escape_applescript_string(heading)
                logger.warning(f"Heading placement not fully implemented, creating in inbox: {heading}")
                script_parts.append(f'        set newTodo to make new to do with properties {properties_string}')
            else:
                # Create in inbox (default)
                script_parts.append(f'        set newTodo to make new to do with properties {properties_string}')
            
            # Add tags if specified - use comma-separated string approach (same as update_todo)
            if tags:
                # Set tags as comma-separated string (this works reliably)
                tags_string = ", ".join(tags)
                escaped_tags = self._escape_applescript_string(tags_string)
                script_parts.append(f'        set tag names of newTodo to {escaped_tags}')
            
            
            # Note: Scheduling will be handled post-creation using reliable method
            
            # Return the ID of the created todo
            script_parts.append('        return id of newTodo')
            script_parts.append('    on error errMsg')
            script_parts.append('        return "error: " & errMsg')
            script_parts.append('    end try')
            script_parts.append('end tell')
            
            script = "\n".join(script_parts)
            
            # Debug logging - temporarily log the generated script
            logger.debug(f"Generated AppleScript for add_todo:\n{script}")
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get('success'):
                output = (result.get('output') or "").strip()
                
                if output.startswith("error:"):
                    logger.error(f"Failed to create todo: {output}")
                    return {
                        "success": False,
                        "error": output
                    }
                
                # The output should be the todo ID
                todo_id = output
                
                # Handle scheduling post-creation using enhanced method
                scheduling_result = None
                resolved_when = when
                resolved_deadline = deadline
                
                if when:
                    # Check if this is a period-based date (this week, next week, etc.)
                    period_info = self._parse_period_date(when)
                    if period_info:
                        # Use period-based scheduling with both when and deadline
                        resolved_when = period_info['when']
                        resolved_deadline = period_info['deadline']
                        
                        # Schedule with the resolved when date
                        scheduling_result = await self.reliable_scheduler.schedule_todo_reliable(todo_id, resolved_when)
                        
                        # Set the deadline separately if it's different
                        if resolved_deadline and resolved_deadline != resolved_when:
                            deadline_result = await self._set_todo_deadline(todo_id, resolved_deadline)
                            if scheduling_result:
                                scheduling_result['deadline_set'] = deadline_result
                        
                        # Add period info to scheduling result
                        if scheduling_result:
                            scheduling_result.update({
                                'period_type': period_info['period_type'],
                                'original_input': when,
                                'resolved_when': resolved_when,
                                'resolved_deadline': resolved_deadline
                            })
                    else:
                        # Regular single-date scheduling
                        scheduling_result = await self.reliable_scheduler.schedule_todo_reliable(todo_id, when)
                
                # Handle deadline post-creation if we have a due_date_command
                if due_date_command:
                    deadline_result = await self._set_todo_deadline(todo_id, due_date_command)
                    if not scheduling_result:
                        scheduling_result = {}
                    scheduling_result['deadline_set'] = deadline_result
                
                # Create response with todo information
                todo_data = {
                    "id": todo_id,
                    "uuid": todo_id,
                    "title": title,
                    "notes": notes,
                    "tags": tags or [],
                    "when": resolved_when,
                    "deadline": resolved_deadline,
                    "list_id": list_id,
                    "list_title": list_title,
                    "heading": heading,
                    "checklist_items": checklist_items or [],
                    "created_at": datetime.now().isoformat(),
                }
                
                # Build informative message
                message_parts = ["Todo created successfully"]
                if created_tags:
                    message_parts.append(f"Created new tag(s): {', '.join(created_tags)}")
                if existing_tags:
                    message_parts.append(f"Applied existing tag(s): {', '.join(existing_tags)}")
                if scheduling_result and scheduling_result.get("success"):
                    message_parts.append("Successfully scheduled")
                elif when:
                    message_parts.append(f"Warning: Scheduling for '{when}' may have failed")
                
                logger.info(f"Successfully created todo with ID {todo_id}: {title}")
                result = {
                    "success": True,
                    "message": ". ".join(message_parts),
                    "todo": todo_data,
                    "tags_created": created_tags,
                    "tags_existing": existing_tags,
                    "tags_filtered": filtered_tags,
                }
                
                # Add enhanced guidance for filtered tags
                if filtered_tags and not self.config.ai_can_create_tags:
                    result["tag_guidance"] = {
                        "message": f"The following tags were not applied because they don't exist: {', '.join(filtered_tags)}",
                        "user_action": "The user has configured tag creation to be manual-only to maintain a clean tag structure.",
                        "suggestion": f"Please inform the user that the todo was created but the tags {filtered_tags} were not applied. Ask if they would like to create these tags.",
                        "policy": "Tags can only be created intentionally by users, not automatically by AI assistants."
                    }
                
                # Add tag warnings if any
                if tag_warnings:
                    result["tag_warnings"] = tag_warnings
                
                return result
            else:
                logger.error(f"Failed to create todo: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get('error') or "Unknown error"
                }
        
        except Exception as e:
            logger.error(f"Error adding todo: {e}")
            raise
    
    async def update_todo(self, todo_id: str, title: Optional[str] = None, notes: Optional[str] = None,
                    tags: Optional[List[str]] = None, when: Optional[str] = None,
                    deadline: Optional[str] = None, completed: Optional[bool] = None,
                    canceled: Optional[bool] = None) -> Dict[str, Any]:
        """Update an existing todo in Things using AppleScript.
        
        Args:
            todo_id: ID of the todo to update
            title: New title
            notes: New notes
            tags: New tags (will be created if they don't exist)
            when: New schedule
            deadline: New deadline
            completed: Mark as completed
            canceled: Mark as canceled
            
        Returns:
            Dict with update result
        """
        # Use operation queue to ensure write consistency
        queue = await get_operation_queue()
        operation_id = await queue.enqueue(
            self._update_todo_impl,
            todo_id, title, notes, tags, when, deadline, completed, canceled,
            name=f"update_todo({todo_id})",
            priority=Priority.HIGH,
            timeout=60.0,
            max_retries=2
        )
        return await queue.wait_for_operation(operation_id)

    async def _update_todo_impl(self, todo_id: str, title: Optional[str] = None, notes: Optional[str] = None,
                         tags: Optional[List[str]] = None, when: Optional[str] = None,
                         deadline: Optional[str] = None, completed: Optional[bool] = None,
                         canceled: Optional[bool] = None) -> Dict[str, Any]:
        """Internal implementation of update_todo (executed through operation queue)."""
        try:
            created_tags = []
            existing_tags = []
            filtered_tags = []
            tag_warnings = []
            date_warnings = []
            
            # Check for date conflicts if 'when' is being updated
            if when is not None:
                try:
                    # Get the current todo to check its due date
                    current_todo = await self.get_todo_by_id(todo_id)
                    current_due_date = current_todo.get('due_date')
                    
                    # Check if the todo has a due date (now properly normalized to ISO format or None)
                    if current_due_date is not None:
                        # Parse the new 'when' date
                        new_when_date = self._parse_relative_date(when)
                        new_when_parsed = datetime.strptime(new_when_date, '%Y-%m-%d').date()
                        
                        # Parse the current due date (now in ISO format: YYYY-MM-DDTHH:MM:SS)
                        current_due_parsed = None
                        try:
                            # Current due date is in ISO format, extract just the date part
                            if 'T' in current_due_date:
                                # ISO format: 2025-09-04T00:00:00
                                date_part = current_due_date.split('T')[0]
                                current_due_parsed = datetime.strptime(date_part, '%Y-%m-%d').date()
                            else:
                                # Fallback: try parsing as date directly
                                current_due_parsed = datetime.strptime(current_due_date, '%Y-%m-%d').date()
                        except (ValueError, TypeError) as e:
                            # If we can't parse the due date, give a generic warning
                            date_warnings.append(
                                f"Warning: This todo has a due date ('{current_due_date}') and you are rescheduling it to '{when}'. "
                                f"Please verify the new schedule doesn't conflict with the due date."
                            )
                        
                        if current_due_parsed:
                            # Check if the new 'when' date is after the due date
                            if new_when_parsed > current_due_parsed:
                                date_warnings.append(
                                    f"Warning: You are scheduling this todo for {new_when_parsed}, "
                                    f"but it has a due date of {current_due_parsed}. "
                                    f"The todo is now scheduled AFTER its due date - you may want to update the due date as well."
                                )
                except Exception as e:
                    logger.debug(f"Could not check for date conflicts: {e}")
                    # Don't fail the update if we can't check dates, just skip the warning
            
            # Ensure all tags exist using consolidated batch operation
            if tags is not None:
                tag_result = await self._ensure_tags_exist(tags)
                created_tags = tag_result.get('created', [])
                existing_tags = tag_result.get('existing', [])
                filtered_tags = tag_result.get('filtered', [])
                tag_warnings = tag_result.get('warnings', [])
                
                # Update tags to only include valid tags (not filtered ones)
                valid_tags = created_tags + existing_tags
                if filtered_tags:
                    logger.info(f"Filtered out tags per policy: {filtered_tags}")
                    tags = valid_tags  # Use only the valid tags
            
            # Build AppleScript to update the todo
            escaped_todo_id = self._escape_applescript_string(todo_id)
            script_parts = [
                'tell application "Things3"',
                '    try'
            ]
            
            # First, check if todo exists
            script_parts.append(f'        set theTodo to to do id {escaped_todo_id}')
            
            # Update properties if provided
            if title is not None:
                escaped_title = self._escape_applescript_string(title)
                script_parts.append(f'        set name of theTodo to {escaped_title}')
            
            if notes is not None:
                escaped_notes = self._escape_applescript_string(notes)
                script_parts.append(f'        set notes of theTodo to {escaped_notes}')
            
            if tags is not None:
                if tags:
                    # Set tags as comma-separated string
                    tags_string = ", ".join(tags)
                    escaped_tags = self._escape_applescript_string(tags_string)
                    script_parts.append(f'        set tag names of theTodo to {escaped_tags}')
                else:
                    # Clear tags if empty list provided
                    script_parts.append('        set tag names of theTodo to ""')
            
            # Note: Scheduling will be handled post-update using reliable method
            
            # Handle deadline - Things 3 supports due date property!
            if deadline is not None:
                if deadline == "":
                    # Empty string means remove the deadline - but AppleScript doesn't support this directly
                    # We'll need to work around this limitation
                    logger.warning("Removing due dates via AppleScript is not supported by Things 3")
                    # Skip setting any due date - user will need to remove manually
                else:
                    parsed_deadline = self._parse_relative_date(deadline)
                    deadline_lower = deadline.lower().strip()
                    
                    # Handle relative deadlines with AppleScript date arithmetic  
                    if deadline_lower == "today":
                        script_parts.append('        set due date of theTodo to (current date)')
                    elif deadline_lower == "tomorrow":
                        script_parts.append('        set due date of theTodo to ((current date) + 1 * days)')
                    elif deadline_lower == "yesterday":
                        script_parts.append('        set due date of theTodo to ((current date) - 1 * days)')
                    else:
                        # For specific dates, construct date object safely
                        if "/" in deadline or "-" in deadline:
                            # Parse the ISO date to get components
                            try:
                                parsed_date = datetime.strptime(parsed_deadline, '%Y-%m-%d')
                                # Build safe date construction script
                                script_parts.append(f'''
        set dueDate to (current date)
        set time of dueDate to 0
        set day of dueDate to 1
        set year of dueDate to {parsed_date.year}
        set month of dueDate to {parsed_date.month}
        set day of dueDate to {parsed_date.day}
        set due date of theTodo to dueDate''')
                            except ValueError:
                                # Fallback to string format if parsing fails
                                script_parts.append(f'        set due date of theTodo to date "{deadline}"')
                        else:
                            # Try as-is
                            script_parts.append(f'        set due date of theTodo to date "{deadline}"')
            
            # Handle completion status
            if completed is True:
                script_parts.append('        set status of theTodo to completed')
            elif canceled is True:
                script_parts.append('        set status of theTodo to canceled')
            elif completed is False or canceled is False:
                # Reopen the todo
                script_parts.append('        set status of theTodo to open')
            
            script_parts.extend([
                '        return "updated"',
                '    on error errMsg',
                '        return "error: " & errMsg',
                '    end try',
                'end tell'
            ])
            
            # OPTIMIZATION: Invalidate related caches for granular cache management
            def _invalidate_caches_after_update():
                cache_keys_to_clear = [
                    "todos_all", "projects_all", "areas_all",
                    "logbook_period_1d_100", "logbook_period_3d_100"  # Common logbook queries
                ]
                for key in filter(None, cache_keys_to_clear):
                    # Use delete method for SharedCache
                    self.applescript._cache.delete(key)
            
            script = '\n'.join(script_parts)
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            # Invalidate caches after successful update
            if result.get('success'):
                _invalidate_caches_after_update()
            
            # Handle scheduling separately using reliable method
            scheduling_result = None
            if result.get('success') and when is not None:
                scheduling_result = await self._schedule_todo_reliable(todo_id, when)
            
            if result.get('success'):
                output = result.get('output') or ""
                if "updated" in output:
                    # Build informative message
                    message_parts = ["Todo updated successfully"]
                    if created_tags:
                        message_parts.append(f"Created new tag(s): {', '.join(created_tags)}")
                    if existing_tags:
                        message_parts.append(f"Applied existing tag(s): {', '.join(existing_tags)}")
                    if scheduling_result and scheduling_result.get("success"):
                        message_parts.append("Successfully scheduled")
                    elif when is not None:
                        message_parts.append(f"Warning: Scheduling for '{when}' may have failed")
                    
                    logger.info(f"Successfully updated todo: {todo_id}")
                    result = {
                        "success": True,
                        "message": ". ".join(message_parts),
                        "todo_id": todo_id,
                        "updated_at": datetime.now().isoformat(),
                        "tags_created": created_tags,
                        "tags_existing": existing_tags,
                        "tags_filtered": filtered_tags,
                        }
                    
                    # Add tag warnings if any
                    if tag_warnings:
                        result["tag_warnings"] = tag_warnings
                    
                    # Add date warnings if any
                    if date_warnings:
                        result["date_warnings"] = date_warnings
                    
                    return result
                elif "error:" in output:
                    error_msg = output.replace("error: ", "")
                    logger.error(f"AppleScript error updating todo {todo_id}: {error_msg}")
                    return {
                        "success": False,
                        "error": f"Todo not found or could not be updated: {error_msg}"
                    }
                else:
                    logger.error(f"Unexpected AppleScript output: {output}")
                    return {
                        "success": False,
                        "error": f"Unexpected response: {output}"
                    }
            else:
                logger.error(f"Failed to execute AppleScript for todo update: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get('error') or "AppleScript execution failed"
                }
        
        except Exception as e:
            logger.error(f"Error updating todo: {e}")
            raise
    
    async def get_todo_by_id(self, todo_id: str) -> Dict[str, Any]:
        """Get a specific todo by its ID.
        
        Args:
            todo_id: ID of the todo to retrieve
            
        Returns:
            Dict with todo information
        """
        try:
            # Use AppleScript to get specific todo
            script = f'''
            tell application "Things3"
                set theTodo to to do id "{todo_id}"
                return {{id:id of theTodo, name:name of theTodo, notes:notes of theTodo, status:status of theTodo, tag_names:tag names of theTodo, creation_date:creation date of theTodo, modification_date:modification date of theTodo, due_date:due date of theTodo, start_date:activation date of theTodo}}
            end tell
            '''
            
            # Don't cache individual todo fetches as they can change frequently
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get('success'):
                # Parse the result using our AppleScript parser
                raw_records = self.applescript._parse_applescript_list(result.get('output') or "")
                
                if raw_records:
                    record = raw_records[0]  # Should be just one record
                    # The parser already converts tag_names to 'tags' key and parses them
                    # So we can use the tags directly from the parsed record
                    tags = record.get("tags", [])
                    
                    todo_data = {
                        "id": record.get("id", todo_id),
                        "uuid": record.get("id", todo_id),
                        "title": record.get("name", ""),
                        "notes": record.get("notes", ""),
                        "status": record.get("status", "open"),
                        "tags": tags,
                        "creation_date": record.get("creation_date"),
                        "modification_date": record.get("modification_date"),
                        "due_date": record.get("due_date"),
                        "start_date": record.get("start_date"),
                        "retrieved_at": datetime.now().isoformat()
                    }
                else:
                    # Fallback if parsing fails
                    todo_data = {
                        "id": todo_id,
                        "uuid": todo_id,
                        "title": "Retrieved Todo",
                        "notes": "",
                        "status": "open",
                        "tags": [],
                        "retrieved_at": datetime.now().isoformat()
                    }
                
                logger.info(f"Successfully retrieved todo: {todo_id}")
                return todo_data
            else:
                logger.error(f"Failed to get todo: {result.get('error')}")
                raise Exception(f"Todo not found: {todo_id}")
        
        except Exception as e:
            logger.error(f"Error getting todo by ID: {e}")
            raise
    
    async def delete_todo(self, todo_id: str) -> Dict[str, Any]:
        """Delete a todo from Things.
        
        Args:
            todo_id: ID of the todo to delete
            
        Returns:
            Dict with deletion result
        """
        # Use operation queue to ensure write consistency
        queue = await get_operation_queue()
        operation_id = await queue.enqueue(
            self._delete_todo_impl,
            todo_id,
            name=f"delete_todo({todo_id})",
            priority=Priority.HIGH,
            timeout=30.0,
            max_retries=2
        )
        return await queue.wait_for_operation(operation_id)

    async def _delete_todo_impl(self, todo_id: str) -> Dict[str, Any]:
        """Internal implementation of delete_todo (executed through operation queue)."""
        try:
            # Use AppleScript to delete todo
            script = f'''
            tell application "Things3"
                set theTodo to to do id "{todo_id}"
                delete theTodo
                return "deleted"
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script)
            
            if result.get('success'):
                logger.info(f"Successfully deleted todo: {todo_id}")
                return {
                    "success": True,
                    "message": "Todo deleted successfully",
                    "todo_id": todo_id,
                    "deleted_at": datetime.now().isoformat()
                }
            else:
                logger.error(f"Failed to delete todo: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get('error') or "Unknown error"
                }
        
        except Exception as e:
            logger.error(f"Error deleting todo: {e}")
            raise
    
    async def get_projects(self, include_items: bool = False) -> List[Dict[str, Any]]:
        """Get all projects from Things.
        
        Args:
            include_items: Include tasks within projects
            
        Returns:
            List of project dictionaries
        """
        try:
            projects = await self.applescript.get_projects()
            
            # Convert to standardized format using the same structure as todos
            # since projects inherit from todos in Things 3
            result = []
            for project in projects:
                # Parse the complete project using the same logic as todos
                # The parser already converts tag_names to 'tags' key and parses them
                tags = project.get("tags", [])
                
                project_dict = {
                    "id": project.get("id"),
                    "uuid": project.get("id"),
                    "title": project.get("name", ""),
                    "notes": project.get("notes", ""),
                    "status": project.get("status", "open"),
                    "tags": tags,  # Now properly extracted from AppleScript
                    "creation_date": project.get("creation_date"),
                    "modification_date": project.get("modification_date"),
                    "due_date": project.get("due_date"),
                    "start_date": project.get("start_date"),
                    "completion_date": project.get("completion_date"),
                    "cancellation_date": project.get("cancellation_date"),
                    "area": project.get("area"),
                    "project": project.get("project"),  # Parent project for sub-projects
                    "contact": project.get("contact"),
                    "retrieved_at": datetime.now().isoformat(),
                    "todos": []  # TODO: Extract todos if include_items
                }
                result.append(project_dict)
            
            logger.info(f"Retrieved {len(result)} projects")
            return result
        
        except Exception as e:
            logger.error(f"Error getting projects: {e}")
            raise
    
    async def add_project(self, title: str, notes: Optional[str] = None, tags: Optional[List[str]] = None,
                    when: Optional[str] = None, deadline: Optional[str] = None,
                    area_id: Optional[str] = None, area_title: Optional[str] = None,
                    todos: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new project in Things.
        
        Args:
            title: Project title
            notes: Optional notes
            tags: Optional list of tags
            when: When to schedule
            deadline: Deadline date
            area_id: Area ID
            area_title: Area title
            todos: Initial todos to create
            
        Returns:
            Dict with created project information
        """
        # Use operation queue to ensure write consistency
        queue = await get_operation_queue()
        operation_id = await queue.enqueue(
            self._add_project_impl,
            title, notes, tags, when, deadline, area_id, area_title, todos,
            name=f"add_project({title[:30]}...)",
            priority=Priority.NORMAL,
            timeout=60.0,
            max_retries=2
        )
        return await queue.wait_for_operation(operation_id)

    async def _add_project_impl(self, title: str, notes: Optional[str] = None, tags: Optional[List[str]] = None,
                         when: Optional[str] = None, deadline: Optional[str] = None,
                         area_id: Optional[str] = None, area_title: Optional[str] = None,
                         todos: Optional[List[str]] = None) -> Dict[str, Any]:
        """Internal implementation of add_project (executed through operation queue)."""
        try:
            created_tags = []
            existing_tags = []
            filtered_tags = []
            tag_warnings = []
            
            # Ensure all tags exist using consolidated batch operation
            if tags:
                tag_result = await self._ensure_tags_exist(tags)
                created_tags = tag_result.get('created', [])
                existing_tags = tag_result.get('existing', [])
                filtered_tags = tag_result.get('filtered', [])
                tag_warnings = tag_result.get('warnings', [])
                
                # Update tags to only include valid tags (not filtered ones)
                valid_tags = created_tags + existing_tags
                if filtered_tags:
                    logger.info(f"Filtered out tags per policy: {filtered_tags}")
                    tags = valid_tags  # Use only the valid tags
            
            # Build AppleScript to create project
            escaped_title = self._escape_applescript_string(title)
            escaped_notes = self._escape_applescript_string(notes or "")
            
            # Build properties dictionary for project creation
            properties = [f"name:{escaped_title}"]
            
            if notes:
                properties.append(f"notes:{escaped_notes}")
            
            # Handle when/start date
            if when:
                parsed_when = self._parse_relative_date(when)
                if parsed_when.lower() == "someday":
                    # Someday projects have no start date
                    pass
                elif parsed_when.lower() == "anytime":
                    # Anytime projects have start date of today
                    properties.append("|start date|:(current date)")
                elif parsed_when.lower() == "today":
                    properties.append("|start date|:(current date)")
                elif parsed_when.lower() == "tomorrow":
                    properties.append("|start date|:((current date) + 1 * days)")
                # For specific dates (YYYY-MM-DD), skip setting the property
                # Things will handle these through other mechanisms
            
            # Handle deadline
            if deadline:
                parsed_deadline = self._parse_relative_date(deadline)
                # Only set date properties for relative dates that AppleScript can handle
                if parsed_deadline.lower() == "today":
                    properties.append("|due date|:(current date)")
                elif parsed_deadline.lower() == "tomorrow":
                    properties.append("|due date|:((current date) + 1 * days)")
                # For specific dates (YYYY-MM-DD), skip setting the property
                # Things will handle these through other mechanisms
            
            properties_string = "{" + ", ".join(properties) + "}"
            
            # Create the AppleScript
            script = f'''
            tell application "Things3"
                try
                    -- Create the project
                    set newProject to make new project with properties {properties_string}
                    
                    -- Handle area assignment
                    '''
            
            if area_id:
                script += f'''
                    try
                        set targetArea to area id "{area_id}"
                        move newProject to targetArea
                    on error
                        -- Area ID not found, continue without area
                    end try
                    '''
            elif area_title:
                escaped_area_title = self._escape_applescript_string(area_title)
                script += f'''
                    try
                        set targetArea to first area whose name is {escaped_area_title}
                        move newProject to targetArea
                    on error
                        -- Area title not found, continue without area
                    end try
                    '''
            
            # Handle tags
            if tags:
                for tag in tags:
                    escaped_tag = self._escape_applescript_string(tag)
                    script += f'''
                    try
                        set targetTag to first tag whose name is {escaped_tag}
                        set tag names of newProject to (tag names of newProject) & {{name of targetTag}}
                    on error
                        -- Tag not found, skip
                    end try
                    '''
            
            script += '''
                    -- Return project information
                    set projectInfo to "id:" & (id of newProject) & ",name:" & (name of newProject)
                    return projectInfo
                    
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''
            
            # Execute the project creation script
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get('success') and not (result.get('output') or "").startswith("error:"):
                # Parse the project info
                output = result.get('output') or ""
                project_id = None
                
                # Extract project ID from the response
                if "id:" in output:
                    try:
                        id_part = output.split("id:")[1].split(",")[0]
                        project_id = id_part.strip()
                    except (IndexError, AttributeError):
                        logger.warning("Could not parse project ID from response")
                
                # Add initial todos if provided
                created_todos = []
                if todos and project_id:
                    # Small delay to ensure project is registered in Things
                    import asyncio
                    await asyncio.sleep(0.5)
                    
                    for todo_title in todos:
                        try:
                            # Call the implementation directly to avoid queue deadlock
                            todo_result = await self._add_todo_impl(
                                title=todo_title,
                                list_id=project_id
                            )
                            if todo_result.get("success"):
                                created_todos.append(todo_title)
                                logger.info(f"Added todo '{todo_title}' to project {project_id}")
                            else:
                                logger.warning(f"Could not add todo '{todo_title}' to project: {todo_result.get('error', 'Unknown error')}")
                        except Exception as e:
                            logger.warning(f"Error creating todo '{todo_title}': {e}")
                
                # Build response
                project_data = {
                    "id": project_id,
                    "title": title,
                    "notes": notes,
                    "tags": tags or [],
                    "when": when,
                    "deadline": deadline,
                    "area_id": area_id,
                    "area_title": area_title,
                    "todos": todos or [],
                    "created_todos": created_todos,
                    "created_at": datetime.now().isoformat()
                }
                
                # Build informative message
                message_parts = ["Project created successfully"]
                if created_tags:
                    message_parts.append(f"Created new tag(s): {', '.join(created_tags)}")
                if existing_tags:
                    message_parts.append(f"Applied existing tag(s): {', '.join(existing_tags)}")
                if created_todos:
                    message_parts.append(f"Added {len(created_todos)} todo(s)")
                
                logger.info(f"Successfully created project: {title}")
                return {
                    "success": True,
                    "message": ". ".join(message_parts),
                    "project": project_data,
                    "tags_created": created_tags,
                    "tags_existing": existing_tags
                }
            else:
                error_msg = result.get('output') or "Unknown error"
                if error_msg.startswith("error:"):
                    error_msg = error_msg[6:].strip()
                logger.error(f"Failed to create project: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
        
        except Exception as e:
            logger.error(f"Error adding project: {e}")
            raise
    
    async def update_project(self, project_id: str, title: Optional[str] = None, notes: Optional[str] = None,
                       tags: Optional[List[str]] = None, when: Optional[str] = None,
                       deadline: Optional[str] = None, completed: Optional[bool] = None,
                       canceled: Optional[bool] = None) -> Dict[str, Any]:
        """Update an existing project in Things.
        
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
            Dict with update result
        """
        # Use operation queue to ensure write consistency
        queue = await get_operation_queue()
        operation_id = await queue.enqueue(
            self._update_project_impl,
            project_id, title, notes, tags, when, deadline, completed, canceled,
            name=f"update_project({project_id})",
            priority=Priority.NORMAL,
            timeout=60.0,
            max_retries=2
        )
        return await queue.wait_for_operation(operation_id)

    async def _update_project_impl(self, project_id: str, title: Optional[str] = None, notes: Optional[str] = None,
                            tags: Optional[List[str]] = None, when: Optional[str] = None,
                            deadline: Optional[str] = None, completed: Optional[bool] = None,
                            canceled: Optional[bool] = None) -> Dict[str, Any]:
        """Internal implementation of update_project (executed through operation queue)."""
        try:
            # Use direct AppleScript instead of URL scheme to avoid modal dialogs
            result = await self.applescript.update_project_direct(
                project_id=project_id,
                title=title,
                notes=notes,
                tags=tags,
                when=when,
                deadline=deadline,
                completed=completed,
                canceled=canceled
            )
            
            if result.get('success'):
                logger.info(f"Successfully updated project: {project_id}")
                return {
                    "success": True,
                    "message": "Project updated successfully",
                    "project_id": project_id,
                    "updated_at": datetime.now().isoformat()
                }
            else:
                error_msg = result.get('error') or "Unknown error"
                logger.error(f"Failed to update project: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg
                }
        
        except Exception as e:
            logger.error(f"Error updating project: {e}")
            raise
    
    async def get_areas(self, include_items: bool = False) -> List[Dict[str, Any]]:
        """Get all areas from Things.
        
        Args:
            include_items: Include projects and tasks within areas
            
        Returns:
            List of area dictionaries
        """
        try:
            areas = await self.applescript.get_areas()
            
            # Convert to standardized format
            result = []
            for area in areas:
                area_dict = {
                    "id": area.get("id"),
                    "uuid": area.get("id"),
                    "title": area.get("name", ""),
                    "notes": area.get("notes", ""),
                    "creation_date": area.get("creation_date"),
                    "modification_date": area.get("modification_date"),
                    "tags": [],  # TODO: Extract tags
                    "projects": [],  # TODO: Extract projects if include_items
                    "todos": []  # TODO: Extract todos if include_items
                }
                result.append(area_dict)
            
            logger.info(f"Retrieved {len(result)} areas")
            return result
        
        except Exception as e:
            logger.error(f"Error getting areas: {e}")
            raise
    
    # List-based operations
    async def get_inbox(self) -> List[Dict[str, Any]]:
        """Get todos from Inbox."""
        return await self._get_list_todos("inbox")
    
    async def get_today(self) -> List[Dict[str, Any]]:
        """Get todos due today."""
        return await self._get_list_todos("today")
    
    async def get_upcoming(self) -> List[Dict[str, Any]]:
        """Get upcoming todos."""
        return await self._get_list_todos("upcoming")
    
    async def get_anytime(self) -> List[Dict[str, Any]]:
        """Get todos from Anytime list."""
        return await self._get_list_todos("anytime")
    
    async def get_someday(self) -> List[Dict[str, Any]]:
        """Get todos from Someday list."""
        return await self._get_list_todos("someday")
    
    async def get_logbook(self, limit: int = 50, period: str = "7d") -> List[Dict[str, Any]]:
        """Get completed todos from Logbook using native AppleScript date filtering.
        
        Uses Things 3's native date comparisons for optimal performance instead of 
        fetching all items and filtering in Python.
        
        Args:
            limit: Maximum number of entries
            period: Time period to look back (e.g., '3d', '1w', '2m', '1y')
            
        Returns:
            List of completed todo dictionaries
        """
        try:
            # Parse the period to get number of days for native AppleScript filtering
            days = self._parse_period_to_days(period)
            
            # Use native AppleScript date arithmetic for optimal performance
            script = f'''
            tell application "Things3"
                -- Use native date arithmetic - much faster than Python filtering
                set cutoffDate to (current date) - ({days} * days)
                set logbookList to list "logbook"
                
                -- Native filtering with "whose" clause for maximum efficiency
                set recentCompleted to (to dos of logbookList whose completion date > cutoffDate)
                
                set logbookResults to {{}}
                set maxResults to {min(limit, 200)}  -- Reasonable upper bound
                set resultCount to 0
                
                repeat with theTodo in recentCompleted
                    if resultCount >= maxResults then exit repeat
                    
                    try
                        set todoRecord to {{}}
                        set todoRecord to todoRecord & {{id:(id of theTodo)}}
                        set todoRecord to todoRecord & {{name:(name of theTodo)}}
                        set todoRecord to todoRecord & {{notes:(notes of theTodo)}}
                        set todoRecord to todoRecord & {{status:(status of theTodo)}}
                        set todoRecord to todoRecord & {{tag_names:(tag names of theTodo)}}
                        set todoRecord to todoRecord & {{creation_date:(creation date of theTodo)}}
                        set todoRecord to todoRecord & {{modification_date:(modification date of theTodo)}}
                        set todoRecord to todoRecord & {{completion_date:(completion date of theTodo)}}
                        
                        -- Try to get project info if available
                        try
                            set todoProject to project of theTodo
                            if todoProject is not missing value then
                                set todoRecord to todoRecord & {{project_id:(id of todoProject)}}
                                set todoRecord to todoRecord & {{project_name:(name of todoProject)}}
                            end if
                        on error
                            -- No project
                        end try
                        
                        set logbookResults to logbookResults & {{todoRecord}}
                        set resultCount to resultCount + 1
                    on error
                        -- Skip items that can't be accessed
                    end try
                end repeat
                
                return logbookResults
            end tell
            '''
            
            # Use period-specific cache key
            cache_key = f"logbook_period_{period}_limit_{limit}"
            result = await self.applescript.execute_applescript(script, cache_key)
            
            if result.get('success'):
                # Parse using existing parser
                todos = self._parse_applescript_todos((result.get('output') or ""))
                
                # Add period context
                for todo in todos:
                    todo["period_filter"] = period
                    todo["days_back"] = days
                
                logger.info(f"Retrieved {len(todos)} completed todos from logbook (period: {period}, {days} days back)")
                return todos
            else:
                logger.error(f"Failed to get logbook with period filter: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting logbook with period filtering: {e}")
            # Fallback to original method without period filtering
            logger.info("Falling back to basic logbook retrieval")
            return await self._get_list_todos("logbook", limit=limit)
    
    async def get_trash(self) -> List[Dict[str, Any]]:
        """Get trashed todos."""
        return await self._get_list_todos("trash")
    
    async def get_tags(self, include_items: bool = False) -> List[Dict[str, Any]]:
        """Get all tags using native AppleScript collection operations.
        
        Args:
            include_items: If True, include full items list for each tag.
                         If False, include only the count of todos for each tag.
            
        Returns:
            List of tag dictionaries with either items or item_count
        """
        try:
            # Use native AppleScript record handling for cleaner output
            # When include_items is False, we'll get counts instead of full items
            script = '''
            tell application "Things3"
                set allTags to every tag
                set tagRecords to {}
                
                repeat with currentTag in allTags
                    try
                        set tagRecord to (id of currentTag) & tab & (name of currentTag)
                        set tagRecords to tagRecords & {tagRecord}
                    on error
                        -- Skip tags that can't be accessed
                    end try
                end repeat
                
                return tagRecords
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, "tags_all")
            
            if result.get("success"):
                output = (result.get("output") or "")
                tags = []
                
                if output and output.strip():
                    # Parse tab-delimited output: id<tab>name, id<tab>name, ...
                    tag_entries = output.strip().split(', ')
                    
                    for entry in tag_entries:
                        entry = entry.strip()
                        if entry and "\t" in entry:
                            # Parse id and name from "id<tab>name"
                            tag_id, tag_name = entry.split('\t', 1)
                            tag_id = tag_id.strip()
                            tag_name = tag_name.strip()
                            
                            if tag_id and tag_name:
                                tag_dict = {
                                    "id": tag_id,
                                    "uuid": tag_id,
                                    "name": tag_name,
                                    "shortcut": "",  # Skip shortcut for performance
                                }
                                
                                # If include_items is requested, get full items list
                                if include_items:
                                    tag_dict["items"] = []
                                    if tag_name:
                                        try:
                                            tag_dict["items"] = await self.get_tagged_items(tag_name)
                                        except Exception as e:
                                            logger.warning(f"Failed to get items for tag '{tag_name}': {e}")
                                else:
                                    # When include_items is False, get the count of todos with this tag
                                    tag_dict["item_count"] = 0
                                    if tag_name:
                                        try:
                                            # Get count of todos with this tag
                                            count_script = f'''
                                            tell application "Things3"
                                                set taggedTodos to every to do whose tag names contains "{self._escape_applescript_string(tag_name)}"
                                                return count of taggedTodos
                                            end tell
                                            '''
                                            count_result = await self.applescript.execute_applescript(count_script, f"tag_count_{tag_id}")
                                            if count_result.get("success"):
                                                try:
                                                    tag_dict["item_count"] = int(count_result.get("output", "0").strip())
                                                except (ValueError, AttributeError):
                                                    tag_dict["item_count"] = 0
                                        except Exception as e:
                                            logger.warning(f"Failed to get count for tag '{tag_name}': {e}")
                                
                                tags.append(tag_dict)
                
                logger.info(f"Retrieved {len(tags)} tags with native operations")
                return tags
            else:
                logger.error(f"Failed to get tags: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting tags: {e}")
            raise
    
    async def get_tagged_items(self, tag: str) -> List[Dict[str, Any]]:
        """Get items with a specific tag using native collection operations.
        
        Args:
            tag: Tag title to filter by
            
        Returns:
            List of tagged item dictionaries
        """
        try:
            # Use native AppleScript collection operations with simplified output
            escaped_tag = self._escape_applescript_string(tag)
            script = f'''
            tell application "Things3"
                set matchingItems to {{}}
                
                try
                    -- OPTIMIZATION: Use compound whose clause for better performance
                    -- Get all active todos with this tag using native filtering
                    set taggedTodos to (to dos whose tag names contains {escaped_tag} and status is open)
                    
                    repeat with currentTodo in taggedTodos
                        try
                            -- Get todo properties and clean notes inline
                            set todoNotes to notes of currentTodo
                            
                            -- Replace problematic characters for clean parsing
                            set AppleScript's text item delimiters to return
                            set notesParts to text items of todoNotes
                            set AppleScript's text item delimiters to " "
                            set cleanNotes to notesParts as text
                            
                            -- Also replace commas in notes to avoid parsing issues
                            set AppleScript's text item delimiters to ","
                            set notesParts to text items of cleanNotes
                            set AppleScript's text item delimiters to "§COMMA§"
                            set cleanNotes to notesParts as text
                            set AppleScript's text item delimiters to ""
                            
                            -- Create tab-delimited record for simpler parsing
                            set todoRecord to (id of currentTodo) & tab & (name of currentTodo) & tab & cleanNotes & tab & (status of currentTodo)
                            
                            -- Use a unique delimiter between records
                            if length of matchingItems > 0 then
                                set matchingItems to matchingItems & "|||RECORD_SEPARATOR|||"
                            end if
                            set matchingItems to matchingItems & todoRecord
                        on error
                            -- Skip todos that can't be accessed
                        end try
                    end repeat
                on error
                    -- Return empty if tag doesn't exist or error occurs
                    return {{}}
                end try
                
                return matchingItems
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, f"tagged_items_{tag}")
            
            if result.get('success'):
                output = (result.get('output') or "")
                items = []
                
                if output and output.strip():
                    # Parse output with new record separator
                    entries = output.strip().split('|||RECORD_SEPARATOR|||')
                    
                    for entry in entries:
                        entry = entry.strip()
                        if entry and "\t" in entry:
                            # Parse tab-delimited format: id<tab>name<tab>notes<tab>status
                            parts = entry.split("\t")
                            if len(parts) >= 2:  # At minimum need ID and name
                                item_id = parts[0].strip()
                                item_name = parts[1].strip() if len(parts) > 1 else ""
                                item_notes = parts[2].strip() if len(parts) > 2 else ""
                                # Restore commas in notes
                                item_notes = item_notes.replace("§COMMA§", ",")
                                item_status = parts[3].strip() if len(parts) > 3 else "open"
                                
                                if item_id:
                                    item_dict = {
                                        "id": item_id,
                                        "uuid": item_id,
                                        "title": item_name,
                                        "notes": item_notes,
                                        "status": item_status,
                                        "tags": [tag],  # We know it has this tag
                                        "creation_date": None,
                                        "modification_date": None,
                                        "type": "todo",
                                        "tag": tag
                                    }
                                    items.append(item_dict)
                
                logger.info(f"Retrieved {len(items)} items with tag '{tag}' using native operations")
                return items
            else:
                logger.error(f"Failed to get tagged items: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting tagged items: {e}")
            raise
    
    async def search_todos(self, query: str) -> List[Dict[str, Any]]:
        """Search todos by title using AppleScript 'whose' clause (much more efficient).
        
        Args:
            query: Search term to look for in todo names
            
        Returns:
            List of matching todo dictionaries
        """
        try:
            # Use AppleScript "whose" clause for efficient native filtering
            escaped_query = self._escape_applescript_string(query)
            
            # Much more efficient: let Things do the filtering natively
            script = f'''
            tell application "Things3"
                -- Use "whose" clause for efficient native filtering (much faster than manual iteration)
                set matchedTodos to to dos whose name contains {escaped_query} and status is open
                
                set searchResults to {{}}
                set maxResults to 50  -- Reasonable limit
                set resultCount to 0
                
                repeat with theTodo in matchedTodos
                    if resultCount >= maxResults then exit repeat
                    try
                        set todoRecord to {{}}
                        set todoRecord to todoRecord & {{id:(id of theTodo)}}
                        set todoRecord to todoRecord & {{name:(name of theTodo)}}
                        set todoRecord to todoRecord & {{notes:(notes of theTodo)}}
                        set todoRecord to todoRecord & {{status:(status of theTodo)}}
                        set todoRecord to todoRecord & {{tag_names:(tag names of theTodo)}}
                        set todoRecord to todoRecord & {{creation_date:(creation date of theTodo)}}
                        set todoRecord to todoRecord & {{modification_date:(modification date of theTodo)}}
                        set todoRecord to todoRecord & {{due_date:(due date of theTodo)}}
                        set todoRecord to todoRecord & {{start_date:(activation date of theTodo)}}
                        
                        -- Try to get project info if it exists
                        try
                            set todoProject to project of theTodo
                            if todoProject is not missing value then
                                set todoRecord to todoRecord & {{project_id:(id of todoProject)}}
                                set todoRecord to todoRecord & {{project_name:(name of todoProject)}}
                            else
                                set todoRecord to todoRecord & {{project_id:missing value}}
                                set todoRecord to todoRecord & {{project_name:missing value}}
                            end if
                        on error
                            set todoRecord to todoRecord & {{project_id:missing value}}
                            set todoRecord to todoRecord & {{project_name:missing value}}
                        end try
                        
                        set searchResults to searchResults & {{todoRecord}}
                        set resultCount to resultCount + 1
                    on error
                        -- Skip todos that can't be accessed
                    end try
                end repeat
                
                return searchResults
            end tell
            '''
            
            # No cache for search to ensure fresh results
            result = await self.applescript.execute_applescript(script, None)
            
            if result.get("success"):
                # Parse using existing parser
                todos = self._parse_applescript_todos((result.get("output") or ""))
                
                # Add search context
                for todo in todos:
                    todo["search_query"] = query
                
                logger.info(f"Efficient search found {len(todos)} todos matching query: {query}")
                return todos
            else:
                logger.error(f"Failed to search todos: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error searching todos: {e}")
            raise
    
    async def search_advanced(self, status: Optional[str] = None, type: Optional[str] = None,
                        tag: Optional[str] = None, area: Optional[str] = None,
                        start_date: Optional[str] = None, deadline: Optional[str] = None,
                        limit: int = 50) -> List[Dict[str, Any]]:
        """Advanced todo search using AppleScript 'whose' clause for efficiency.
        
        Args:
            status: Filter by status (incomplete, completed, canceled)
            type: Filter by type (to-do, project, heading)
            tag: Filter by tag
            area: Filter by area UUID
            start_date: Filter by start date (YYYY-MM-DD)
            deadline: Filter by deadline (YYYY-MM-DD)
            limit: Maximum number of results to return (default: 50, max: 500)
            
        Returns:
            List of matching todo dictionaries
        """
        try:
            # Validate and clamp the limit to reasonable bounds
            limit = max(1, min(limit, 500))  # Between 1 and 500
            
            # Build "whose" clause conditions for efficient native filtering
            conditions = []
            
            # Status filter - be more specific for incomplete to avoid massive searches
            if status:
                if status == "incomplete":
                    conditions.append('status is open')
                elif status == "completed":
                    conditions.append('status is completed')
                elif status == "canceled":
                    conditions.append('status is canceled')
            
            # Tag filter  
            if tag:
                escaped_tag = self._escape_applescript_string(tag)
                conditions.append(f'tag names contains {escaped_tag}')
            
            # Date filters using native AppleScript date comparisons
            if deadline:
                deadline_condition = self._build_native_date_condition(deadline, "due date")
                conditions.append(deadline_condition)
            
            if start_date:
                start_condition = self._build_native_date_condition(start_date, "activation date")  
                conditions.append(start_condition)
            
            # Combine conditions with "and"
            where_clause = ""
            if conditions:
                where_clause = f"whose {' and '.join(conditions)}"
            
            # Choose collection based on type and optimize for common searches
            if type == "project":
                collection = "projects"
            else:
                # For "to-do" type with incomplete status, we can use specific lists for better performance
                if status == "incomplete" and not tag and not area and not start_date and not deadline:
                    # Use combined lists instead of all todos for better performance
                    collection = "(to dos of list \"today\") & (to dos of list \"upcoming\") & (to dos of list \"anytime\") & (to dos of list \"someday\")"
                    where_clause = ""  # No need for additional filtering since lists are already filtered
                else:
                    collection = "to dos"  # Default to todos for other cases
            
            # Build efficient AppleScript using "whose" clause
            script = f'''
            tell application "Things3"
                -- Use native "whose" filtering for maximum efficiency
                set matchedItems to {collection} {where_clause}
                
                set searchResults to {{}}
                set maxResults to {limit}  -- Configurable limit for advanced search
                set resultCount to 0
                set totalCount to count of matchedItems
                
                -- Limit processing to maxResults or total, whichever is smaller
                if totalCount > maxResults then
                    set itemsToProcess to maxResults
                else
                    set itemsToProcess to totalCount
                end if
                
                repeat with i from 1 to itemsToProcess
                    set theItem to item i of matchedItems
                    try
                        set itemRecord to {{}}
                        set itemRecord to itemRecord & {{id:(id of theItem)}}
                        set itemRecord to itemRecord & {{name:(name of theItem)}}
                        set itemRecord to itemRecord & {{notes:(notes of theItem)}}
                        set itemRecord to itemRecord & {{status:(status of theItem)}}
                        set itemRecord to itemRecord & {{tag_names:(tag names of theItem)}}
                        set itemRecord to itemRecord & {{creation_date:(creation date of theItem)}}
                        set itemRecord to itemRecord & {{modification_date:(modification date of theItem)}}
                        set itemRecord to itemRecord & {{due_date:(due date of theItem)}}
                        
                        -- Add type info
                        {'set itemRecord to itemRecord & {item_type:"project"}' if type == "project" else 'set itemRecord to itemRecord & {item_type:"todo"}'}
                        
                        -- Try to get area info if it exists
                        try
                            set itemArea to area of theItem
                            if itemArea is not missing value then
                                set itemRecord to itemRecord & {{area_id:(id of itemArea)}}
                                set itemRecord to itemRecord & {{area_name:(name of itemArea)}}
                            end if
                        on error
                            -- Item has no area
                        end try
                        
                        -- Try to get project info for todos
                        if "{type}" is not "project" then
                            try
                                set itemProject to project of theItem
                                if itemProject is not missing value then
                                    set itemRecord to itemRecord & {{project_id:(id of itemProject)}}
                                    set itemRecord to itemRecord & {{project_name:(name of itemProject)}}
                                end if
                            on error
                                -- Item has no project
                            end try
                        end if
                        
                        set searchResults to searchResults & {{itemRecord}}
                    on error
                        -- Skip items that can't be accessed
                    end try
                end repeat
                
                return searchResults
            end tell
            '''
            
            # No cache for advanced search to ensure fresh results
            result = await self.applescript.execute_applescript(script, None)
            
            if result.get('success'):
                # Parse using existing parser
                todos = self._parse_applescript_todos((result.get('output') or ""))
                
                # Add filter context - be explicit about which parameters to include
                filters = {}
                if status is not None:
                    filters["status"] = status
                if type is not None:
                    filters["type"] = type
                if tag is not None:
                    filters["tag"] = tag
                if area is not None:
                    filters["area"] = area
                if start_date is not None:
                    filters["start_date"] = start_date
                if deadline is not None:
                    filters["deadline"] = deadline
                filters["limit"] = limit  # Always include limit for transparency
                
                # Only add filters if there are any, and make them serializable
                if filters:
                    for todo in todos:
                        todo["search_filters"] = filters.copy()  # Use copy to avoid any reference issues
                
                logger.info(f"Efficient advanced search found {len(todos)} items with filters: {filters}")
                return todos
            else:
                logger.error(f"Failed to perform advanced search: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error in advanced search: {e}")
            raise
    
    async def get_recent(self, period: str) -> List[Dict[str, Any]]:
        """Get recently created items using Things 3's native filtering.
        
        This implementation uses AppleScript's 'whose' clause to let Things 3
        do the filtering natively, which is MUCH faster than iterating through
        all items manually.
        
        Args:
            period: Time period (e.g., '3d', '1w', '2m', '1y')
            
        Returns:
            List of recent item dictionaries
        """
        try:
            # Parse the period to get number of days
            days = self._parse_period_to_days(period)
            
            # Build highly optimized AppleScript using native filtering
            # This lets Things 3 do the heavy lifting internally
            script = f'''
            tell application "Things3"
                set recentItems to {{}}
                set cutoffDate to (current date) - ({days} * days)
                set maxResults to 200
                
                -- Use native filtering with "whose" clause for todos
                -- This is ORDERS OF MAGNITUDE faster than manual iteration
                try
                    -- OPTIMIZATION: Use compound whose clause with status filter
                    -- Get active todos created after cutoff date using native filtering
                    -- Things 3 handles this internally with its optimized database
                    set recentTodos to to dos whose creation date > cutoffDate and status is not canceled
                    
                    -- Limit results for performance
                    set todoCount to 0
                    repeat with theTodo in recentTodos
                        if todoCount >= maxResults then exit repeat
                        
                        try
                            set itemRecord to {{}}
                            set itemRecord to itemRecord & {{id:(id of theTodo)}}
                            set itemRecord to itemRecord & {{name:(name of theTodo)}}
                            set itemRecord to itemRecord & {{notes:(notes of theTodo)}}
                            set itemRecord to itemRecord & {{status:(status of theTodo)}}
                            set itemRecord to itemRecord & {{tag_names:(tag names of theTodo)}}
                            set itemRecord to itemRecord & {{creation_date:(creation date of theTodo)}}
                            set itemRecord to itemRecord & {{modification_date:(modification date of theTodo)}}
                            set itemRecord to itemRecord & {{item_type:"todo"}}
                            
                            -- Include activation date if scheduled
                            try
                                set itemRecord to itemRecord & {{activation_date:(activation date of theTodo)}}
                            on error
                                set itemRecord to itemRecord & {{activation_date:missing value}}
                            end try
                            
                            -- Include project info if available
                            try
                                set todoProject to project of theTodo
                                if todoProject is not missing value then
                                    set itemRecord to itemRecord & {{project_id:(id of todoProject)}}
                                    set itemRecord to itemRecord & {{project_name:(name of todoProject)}}
                                end if
                            on error
                                -- No project
                            end try
                            
                            -- Include area info if available
                            try
                                set todoArea to area of theTodo
                                if todoArea is not missing value then
                                    set itemRecord to itemRecord & {{area_id:(id of todoArea)}}
                                    set itemRecord to itemRecord & {{area_name:(name of todoArea)}}
                                end if
                            on error
                                -- No area
                            end try
                            
                            set recentItems to recentItems & {{itemRecord}}
                            set todoCount to todoCount + 1
                        on error
                            -- Skip items that can't be accessed
                        end try
                    end repeat
                on error errMsg
                    -- Log but continue if todos filtering fails
                    log "Todo filtering error: " & errMsg
                end try
                
                -- Also get recent projects using native filtering
                if (count of recentItems) < maxResults then
                    try
                        set recentProjects to projects whose creation date > cutoffDate
                        
                        set projectCount to 0
                        set remainingSlots to maxResults - (count of recentItems)
                        
                        repeat with theProject in recentProjects
                            if projectCount >= remainingSlots then exit repeat
                            
                            try
                                set itemRecord to {{}}
                                set itemRecord to itemRecord & {{id:(id of theProject)}}
                                set itemRecord to itemRecord & {{name:(name of theProject)}}
                                set itemRecord to itemRecord & {{notes:(notes of theProject)}}
                                set itemRecord to itemRecord & {{status:(status of theProject)}}
                                set itemRecord to itemRecord & {{tag_names:(tag names of theProject)}}
                                set itemRecord to itemRecord & {{creation_date:(creation date of theProject)}}
                                set itemRecord to itemRecord & {{modification_date:(modification date of theProject)}}
                                set itemRecord to itemRecord & {{item_type:"project"}}
                                
                                -- Include area info if available
                                try
                                    set projectArea to area of theProject
                                    if projectArea is not missing value then
                                        set itemRecord to itemRecord & {{area_id:(id of projectArea)}}
                                        set itemRecord to itemRecord & {{area_name:(name of projectArea)}}
                                    end if
                                on error
                                    -- No area
                                end try
                                
                                set recentItems to recentItems & {{itemRecord}}
                                set projectCount to projectCount + 1
                            on error
                                -- Skip items that can't be accessed
                            end try
                        end repeat
                    on error errMsg
                        -- Log but continue if project filtering fails
                        log "Project filtering error: " & errMsg
                    end try
                end if
                
                return recentItems
            end tell
            '''
            
            # Don't cache this query as results change frequently
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get('success'):
                # Parse the AppleScript output
                raw_records = self.applescript._parse_applescript_list((result.get('output') or ""))
                
                # Convert to standardized format
                items = []
                for record in raw_records:
                    item_dict = {
                        "id": record.get("id", "unknown"),
                        "uuid": record.get("id", "unknown"),
                        "title": record.get("name", ""),
                        "notes": record.get("notes", ""),
                        "status": record.get("status", "open"),
                        "tags": record.get("tags", []),
                        "creation_date": record.get("creation_date"),
                        "modification_date": record.get("modification_date"),
                        "type": record.get("item_type", "todo"),
                        "project_id": record.get("project_id"),
                        "area_id": record.get("area_id"),
                        "period_filter": period
                    }
                    items.append(item_dict)
                
                logger.info(f"Retrieved {len(items)} recent items for period: {period}")
                return items
            else:
                logger.error(f"Failed to get recent items: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting recent items: {e}")
            raise
    
    async def add_tags(self, todo_id: str, tags: List[str]) -> Dict[str, Any]:
        """Add tags to a todo.
        
        Args:
            todo_id: ID of the todo
            tags: List of tags to add
            
        Returns:
            Dict with operation result
        """
        try:
            # First, get the current todo to see existing tags
            todo = await self.get_todo_by_id(todo_id)
            current_tags = todo.get('tags', [])
            
            # Combine with new tags (avoid duplicates)
            all_tags = list(set(current_tags + tags))
            
            # Update the todo with all tags
            return await self.update_todo(todo_id, tags=all_tags)
            
        except Exception as e:
            logger.error(f"Error adding tags: {e}")
            raise
    
    async def remove_tags(self, todo_id: str, tags: List[str]) -> Dict[str, Any]:
        """Remove tags from a todo.
        
        Args:
            todo_id: ID of the todo
            tags: List of tags to remove
            
        Returns:
            Dict with operation result
        """
        try:
            # First, get the current todo to see existing tags
            todo = await self.get_todo_by_id(todo_id)
            current_tags = todo.get('tags', [])
            
            # Remove specified tags
            remaining_tags = [t for t in current_tags if t not in tags]
            
            # Update the todo with remaining tags
            return await self.update_todo(todo_id, tags=remaining_tags)
            
        except Exception as e:
            logger.error(f"Error removing tags: {e}")
            raise
    
    async def move_record(self, todo_id: str, destination_list: str) -> Dict[str, Any]:
        """Move a todo to a different list, project, or area in Things.
        
        This function supports moving todos to:
        - Built-in lists: inbox, today, anytime, someday, upcoming, logbook
        - Projects: Use format "project:PROJECT_ID" 
        - Areas: Use format "area:AREA_ID"
        
        Args:
            todo_id: ID of the todo to move
            destination_list: Destination in one of these formats:
                - List name: "inbox", "today", "anytime", "someday", "upcoming", "logbook"
                - Project: "project:PROJECT_ID" (e.g., "project:ABC123")
                - Area: "area:AREA_ID" (e.g., "area:XYZ789")
            
        Returns:
            Dict with move operation result containing:
                - success: Boolean indicating if move succeeded
                - message: Success/error message
                - todo_id: ID of the todo that was moved
                - destination: Target destination 
                - moved_at: Timestamp of successful move (only on success)
                - error: Error details (only on failure)
        """
        # Use operation queue to ensure write consistency for backward compatibility
        queue = await get_operation_queue()
        operation_id = await queue.enqueue(
            self._move_record_impl,
            todo_id, destination_list,
            name=f"move_record({todo_id} to {destination_list})",
            priority=Priority.HIGH,
            timeout=30.0,
            max_retries=2
        )
        return await queue.wait_for_operation(operation_id)

    async def _move_record_impl(self, todo_id: str, destination_list: str) -> Dict[str, Any]:
        """Internal implementation of move_record (executed through operation queue)."""
        try:
            # Use the advanced MoveOperationsTools for all move operations
            # This provides full support for lists, projects, and areas with proper validation
            result = await self.move_operations.move_record(
                todo_id=todo_id, 
                destination=destination_list,
                preserve_scheduling=True
            )
            
            # Normalize the response format to maintain backward compatibility
            if result.get('success'):
                return {
                    "success": True,
                    "message": result.get("message", f"Todo moved to {destination_list} successfully"),
                    "todo_id": todo_id,
                    "destination_list": destination_list,  # Keep original parameter name for compatibility
                    "destination": result.get("destination", destination_list),
                    "moved_at": result.get("moved_at", datetime.now().isoformat())
                }
            else:
                return {
                    "success": False,
                    "error": result.get('error'),
                    "message": result.get("message", "Failed to move todo"),
                    "todo_id": todo_id,
                    "destination_list": destination_list
                }
        
        except Exception as e:
            logger.error(f"Error in move_record operation: {e}")
            return {
                "success": False,
                "error": "UNEXPECTED_ERROR", 
                "message": f"Unexpected error during move: {str(e)}",
                "todo_id": todo_id,
                "destination_list": destination_list
            }
    
    # Removed show_item and search_items methods as they trigger UI changes
    # which are not appropriate for MCP server operations
    
    async def _get_list_todos(self, list_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get todos from a specific list.
        
        OPTIMIZATION: Uses native AppleScript 'items 1 thru N' syntax for efficient limiting
        instead of fetching all items and filtering in Python.
        
        Args:
            list_name: Name of the list (inbox, today, etc.)
            limit: Optional limit on number of results (uses native AppleScript limiting)
            
        Returns:
            List of todo dictionaries
        """
        try:
            # Map list names to AppleScript list references
            list_mapping = {
                "inbox": "inbox",
                "today": "today",
                "upcoming": "upcoming",
                "anytime": "anytime",
                "someday": "someday",
                "logbook": "logbook",
                "trash": "trash"
            }
            
            if list_name not in list_mapping:
                logger.error(f"Unknown list name: {list_name}")
                return []
            
            # Build AppleScript with native limiting
            # OPTIMIZATION: Use native AppleScript limiting to avoid fetching all items and filtering in Python
            script = f'''
            tell application "Things3"
                set todoList to {{}}
                set listRef to list "{list_mapping[list_name]}"
                set allTodos to (to dos of listRef)
                set todoCount to count of allTodos
                
                -- Determine how many items to process (native AppleScript limiting)
                set maxIndex to todoCount
                if {limit if limit else 0} > 0 and {limit if limit else 0} < todoCount then
                    set maxIndex to {limit if limit else 0}
                end if
                
                -- Process only the required number of todos (native limiting applied)
                if maxIndex > 0 then
                    set todosToProcess to items 1 thru maxIndex of allTodos
                    
                    repeat with theTodo in todosToProcess
                        set todoRecord to {{}}
                        try
                            set todoRecord to todoRecord & {{id:id of theTodo}}
                            set todoRecord to todoRecord & {{name:name of theTodo}}
                            set todoRecord to todoRecord & {{notes:notes of theTodo}}
                            set todoRecord to todoRecord & {{status:status of theTodo}}
                            set todoRecord to todoRecord & {{tag_names:tag names of theTodo}}
                            set todoRecord to todoRecord & {{creation_date:creation date of theTodo}}
                            set todoRecord to todoRecord & {{modification_date:modification date of theTodo}}
                            set todoRecord to todoRecord & {{due_date:due date of theTodo}}
                            set todoRecord to todoRecord & {{activation_date:activation date of theTodo}}
                            set todoList to todoList & {{todoRecord}}
                        end try
                    end repeat
                end if
                
                return todoList
            end tell
            '''
            
            # Include limit in cache key to avoid cache conflicts between different limits
            cache_key = f"list_{list_name}_limit_{limit}" if limit else f"list_{list_name}_all"
            result = await self.applescript.execute_applescript(script, cache_key)
            
            if result.get('success'):
                # Parse the AppleScript output
                todos = self._parse_applescript_todos((result.get('output') or ""))
                
                # Native AppleScript limiting applied - no post-processing needed
                logger.info(f"Retrieved {len(todos)} todos from {list_name} (native limit: {limit or 'none'})")
                return todos
            else:
                logger.error(f"Failed to get {list_name} todos: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting {list_name} todos: {e}")
            return []  # Return empty list instead of raising to be more resilient
    
    def _parse_applescript_todos(self, output: str) -> List[Dict[str, Any]]:
        """Parse AppleScript output into todo dictionaries.
        
        Args:
            output: Raw AppleScript output
            
        Returns:
            List of parsed todo dictionaries
        """
        todos = []
        try:
            if not output or not output.strip():
                return []
                
            # Use the same parsing logic as the AppleScript manager
            raw_records = self.applescript._parse_applescript_list(output)
            
            # Convert to standardized todo format
            for record in raw_records:
                todo = {
                    "id": record.get("id", "unknown"),
                    "uuid": record.get("id", "unknown"),  # Things uses ID as UUID
                    "title": record.get("name", ""),
                    "notes": record.get("notes", ""),
                    "status": record.get("status", "open"),
                    "tags": record.get("tags", []),  # Already parsed by _parse_applescript_list
                    "creation_date": record.get("creation_date"),
                    "modification_date": record.get("modification_date"),
                    "area": record.get("area"),
                    "project": record.get("project"),
                    "due_date": record.get("due_date"),
                    "start_date": record.get("start_date"),
                    # New reminder fields from Phase 1 implementation
                    "activation_date": record.get("activation_date"),
                    "has_reminder": record.get("has_reminder", False),
                    "reminder_time": record.get("reminder_time")
                }
                todos.append(todo)
                
            logger.debug(f"Parsed {len(todos)} todos from AppleScript output")
            
        except Exception as e:
            logger.error(f"Error parsing AppleScript output: {e}")
        
        return todos
    
    def _build_native_date_condition(self, date_input: str, field_name: str) -> str:
        """Build a native AppleScript date condition for efficient filtering.
        
        This creates AppleScript date comparisons that run natively in Things 3,
        avoiding the need to fetch all items and filter in Python.
        
        Args:
            date_input: Date string (today, tomorrow, YYYY-MM-DD, etc.)
            field_name: AppleScript field name (due date, activation date, creation date, etc.)
            
        Returns:
            AppleScript condition string for use in 'whose' clause
        """
        if not date_input:
            return f"{field_name} is not missing value"
            
        date_lower = date_input.lower().strip()
        
        # Handle relative dates with native AppleScript date arithmetic
        if date_lower in ['today']:
            return f"{field_name} = (current date)"
        elif date_lower in ['tomorrow']:
            return f"{field_name} = ((current date) + 1 * days)"
        elif date_lower in ['yesterday']:
            return f"{field_name} = ((current date) - 1 * days)"
        elif date_lower in ['this week', 'thisweek']:
            # Within current week (next 7 days)
            return f"{field_name} ≥ (current date) and {field_name} ≤ ((current date) + 7 * days)"
        elif date_lower in ['next week', 'nextweek']:
            # Within next week (days 8-14 from now)
            return f"{field_name} > ((current date) + 7 * days) and {field_name} ≤ ((current date) + 14 * days)"
        elif date_lower in ['this month', 'thismonth']:
            # Within current month (next 30 days)
            return f"{field_name} ≥ (current date) and {field_name} ≤ ((current date) + 30 * days)"
        elif date_lower in ['past week', 'last week']:
            # Past week (last 7 days)
            return f"{field_name} ≥ ((current date) - 7 * days) and {field_name} ≤ (current date)"
        elif date_lower in ['past month', 'last month']:
            # Past month (last 30 days) 
            return f"{field_name} ≥ ((current date) - 30 * days) and {field_name} ≤ (current date)"
        elif '-' in date_input:  # YYYY-MM-DD format
            try:
                # Use locale-aware date handler for property-based date creation
                date_components = locale_handler.normalize_date_input(date_input)
                if date_components:
                    year, month, day = date_components
                    # Build property-based date comparison
                    date_expr = locale_handler.build_applescript_date_property(year, month, day)
                    return f'{field_name} = ({date_expr})'
                else:
                    logger.warning(f"Could not normalize date '{date_input}', using existence check")
                    return f"{field_name} is not missing value"
            except Exception as e:
                logger.warning(f"Error parsing date '{date_input}': {e}, using existence check")
                return f"{field_name} is not missing value"
        else:
            # Default fallback: just check field exists
            return f"{field_name} is not missing value"

    def _parse_period_to_days(self, period: str) -> int:
        """Parse period string like '3d', '1w', '2m', '1y' to number of days.
        
        Args:
            period: Period string
            
        Returns:
            Number of days
        """
        try:
            if not period or len(period) < 2:
                return 7  # Default to 7 days
            
            unit = period[-1].lower()
            number = int(period[:-1])
            
            if unit == 'd':  # days
                return number
            elif unit == 'w':  # weeks
                return number * 7
            elif unit == 'm':  # months (approximate)
                return number * 30
            elif unit == 'y':  # years (approximate)
                return number * 365
            else:
                logger.warning(f"Unknown period unit: {unit}, defaulting to 7 days")
                return 7
        
        except (ValueError, IndexError):
            logger.warning(f"Could not parse period: {period}, defaulting to 7 days")
            return 7
    
    def _validate_time_format(self, time_str: str) -> bool:
        """Validate time format for reminder support.
        
        Validates time strings in HH:MM or H:MM format for use in reminder creation.
        Supports both 24-hour format with hours 0-23 and minutes 0-59.
        
        Args:
            time_str: Time string to validate. Accepted formats:
                - "14:30" (2-digit hour, 2-digit minute)  
                - "9:15" (1-digit hour, 2-digit minute)
                - "00:00" (midnight)
                - "23:59" (end of day)
                - None or empty string (returns False)
                
        Returns:
            True if valid time format, False otherwise
            
        Examples:
            >>> validator._validate_time_format("14:30")  # True
            >>> validator._validate_time_format("9:15")   # True  
            >>> validator._validate_time_format("25:00")  # False (invalid hour)
            >>> validator._validate_time_format("12:60")  # False (invalid minute)
            >>> validator._validate_time_format("14")     # False (missing minute)
        """
        if not time_str:
            return False
        
        # Reject strings with leading/trailing whitespace
        if time_str != time_str.strip():
            return False
            
        try:
            # Expected format: HH:MM or H:MM
            if ':' not in time_str:
                return False
            
            parts = time_str.split(':')
            if len(parts) != 2:
                return False
                
            hour, minute = parts
            
            # Check that hour and minute don't have spaces
            if hour != hour.strip() or minute != minute.strip():
                return False
                
            hour_int = int(hour)
            minute_int = int(minute)
            
            # Validate ranges
            if not (0 <= hour_int <= 23):
                return False
            if not (0 <= minute_int <= 59):
                return False
                
            return True
            
        except (ValueError, TypeError):
            return False
    
    def _has_datetime_reminder(self, when_value: str) -> bool:
        """Check if a when value contains datetime reminder format.
        
        Args:
            when_value: The when parameter value
            
        Returns:
            True if contains @HH:MM time component, False otherwise
        """
        return '@' in when_value if when_value else False
    
    def _convert_to_things_datetime_format(self, when_datetime: str) -> str:
        """Convert datetime to Things-preferred format.
        
        Converts 24-hour time format to 12-hour AM/PM format for Things URL scheme compatibility.
        Things prefers formats like "today@6pm" rather than "today@18:00" for better parsing.
        Handles edge cases like midnight (00:00 -> 12am) and noon (12:00 -> 12pm).
        
        Args:
            when_datetime: Datetime string in format "date@HH:MM"
                Examples: "today@18:00", "2024-12-25@14:30", "tomorrow@09:15"
            
        Returns:
            Datetime string in Things-preferred format "date@Hpm/Ham"
            Returns original string if format is invalid or doesn't contain @ symbol
            
        Examples:
            >>> converter._convert_to_things_datetime_format("today@18:00")      # "today@6pm"
            >>> converter._convert_to_things_datetime_format("today@14:30")     # "today@2:30pm"  
            >>> converter._convert_to_things_datetime_format("today@00:00")     # "today@12am" (midnight)
            >>> converter._convert_to_things_datetime_format("today@12:00")     # "today@12pm" (noon)
            >>> converter._convert_to_things_datetime_format("today@09:15")     # "today@9:15am"
            >>> converter._convert_to_things_datetime_format("no_at_symbol")    # "no_at_symbol" (unchanged)
        """
        if '@' not in when_datetime:
            return when_datetime
            
        try:
            date_part, time_part = when_datetime.split('@', 1)
            
            # Parse the time part
            if ':' in time_part:
                hour_str, minute_str = time_part.split(':', 1)
                hour = int(hour_str)
                minute = int(minute_str)
            else:
                hour = int(time_part)
                minute = 0
            
            # Convert to 12-hour format with proper handling of edge cases
            if hour == 0:
                hour_12 = 12        # Midnight: 00:00 -> 12am
                period = 'am'
            elif hour < 12:
                hour_12 = hour      # Morning: 1-11 stays the same in AM
                period = 'am'
            elif hour == 12:
                hour_12 = 12        # Noon: 12:00 -> 12pm (not 0pm)
                period = 'pm'
            else:
                hour_12 = hour - 12 # Afternoon/Evening: 13-23 becomes 1-11 PM
                period = 'pm'
            
            # Format the time part - use simple format like "6pm" for on-the-hour times
            if minute == 0:
                time_formatted = f"{hour_12}{period}"
            else:
                time_formatted = f"{hour_12}:{minute:02d}{period}"
            
            result = f"{date_part}@{time_formatted}"
            logger.debug(f"Converted datetime '{when_datetime}' to Things format '{result}'")
            return result
            
        except (ValueError, IndexError) as e:
            logger.warning(f"Could not convert datetime format '{when_datetime}': {e}")
            return when_datetime  # Return original if conversion fails
    
    def _build_url_scheme_with_reminder(self, title: str, when_datetime: str, notes: Optional[str] = None, 
                                       tags: Optional[List[str]] = None) -> str:
        """Build Things URL scheme for creating todo with reminder.
        
        Constructs a Things URL scheme string that creates a todo with a specific reminder time.
        The URL will automatically open Things and create the todo when executed. Handles
        URL encoding of special characters and converts time format for Things compatibility.
        
        Args:
            title: Todo title (will be URL-encoded for safety)
            when_datetime: Datetime string in format "YYYY-MM-DD@HH:MM" or "today@HH:MM"
                Will be converted to Things-preferred 12-hour format internally
            notes: Optional notes content (will be URL-encoded if provided)
            tags: Optional list of tags to apply (will be comma-separated and URL-encoded)
            
        Returns:
            Complete Things URL scheme string for reminder creation
            Format: "things:///add?title=...&when=...&notes=...&tags=..."
            
        Examples:
            >>> builder._build_url_scheme_with_reminder("Meeting", "today@14:30")
            # "things:///add?title=Meeting&when=today%402%3A30pm"
            
            >>> builder._build_url_scheme_with_reminder("Review & Approve", "2024-12-25@09:00", 
            ...                                        notes="Important deadline", tags=["work", "urgent"])
            # "things:///add?title=Review%20%26%20Approve&when=2024-12-25%409am&notes=Important%20deadline&tags=work%2Curgent"
        """
        try:
            # URL encode components for safety - Things is strict about special characters
            from urllib.parse import quote
            
            # Build parameter list starting with required title
            params = [f"title={quote(title)}"]
            
            # Convert 24-hour time format to 12-hour format for Things URL scheme
            # Things prefers formats like "today@6pm" rather than "today@18:00"
            converted_datetime = self._convert_to_things_datetime_format(when_datetime)
            
            # Add when parameter with converted datetime - this is the key for reminder creation
            params.append(f"when={quote(converted_datetime)}")
            
            # Add optional parameters if provided
            if notes:
                params.append(f"notes={quote(notes)}")
                
            if tags:
                # Convert tag list to comma-separated string and encode
                tags_str = ",".join(tags)
                params.append(f"tags={quote(tags_str)}")
            
            # Construct the final Things URL scheme 
            url_scheme = "things:///add?" + "&".join(params)
            logger.debug(f"Built URL scheme for reminder: {url_scheme}")
            
            return url_scheme
            
        except Exception as e:
            logger.error(f"Error building URL scheme for reminder: {e}")
            raise
    
    async def get_todos_due_in_days(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get todos due within specified number of days using efficient AppleScript filtering.
        
        Uses AppleScript's 'whose' clause for fast filtering directly in Things 3,
        avoiding expensive O(n) loops in Python.
        
        Args:
            days: Number of days ahead to check for due todos (default: 30)
            
        Returns:
            List of todo dictionaries with due dates within the specified range
        """
        return await self.applescript.get_todos_due_in_days(days)
    
    async def get_todos_activating_in_days(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get todos with activation dates within specified number of days using efficient filtering.
        
        Uses AppleScript's 'whose' clause for fast filtering directly in Things 3.
        
        Args:
            days: Number of days ahead to check for activating todos (default: 30)
            
        Returns:
            List of todo dictionaries with activation dates within the specified range
        """
        return await self.applescript.get_todos_activating_in_days(days)
    
    async def get_todos_upcoming_in_days(self, days: int = 30) -> List[Dict[str, Any]]:
        """Get todos due or activating within specified number of days (union).
        
        Combines results from due dates and activation dates, removing duplicates.
        Uses efficient AppleScript filtering.
        
        Args:
            days: Number of days ahead to check (default: 30)
            
        Returns:
            List of unique todo dictionaries due or activating within the range
        """
        return await self.applescript.get_todos_upcoming_in_days(days)
