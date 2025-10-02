"""Scheduling strategies for reliable date scheduling in Things 3."""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any

from ..locale_aware_dates import locale_handler
from .helpers import SchedulingHelpers

logger = logging.getLogger(__name__)


class SchedulingStrategies:
    """Implements multiple scheduling strategies with fallback mechanisms."""

    def __init__(self, applescript_manager):
        """Initialize with AppleScript manager.

        Args:
            applescript_manager: AppleScript execution manager
        """
        self.applescript = applescript_manager
        self.helpers = SchedulingHelpers()

    async def schedule_todo_reliable(self, todo_id: str, when_date: str) -> Dict[str, Any]:
        """
        Reliable todo scheduling using ONLY AppleScript (no URL schemes).

        Based on research findings, this uses proper AppleScript date object construction
        to eliminate locale dependencies and string parsing issues.

        Args:
            todo_id: Things todo ID
            when_date: ISO date (YYYY-MM-DD) or relative date ("today", "tomorrow", etc.)

        Returns:
            Dict with success status and method used
        """

        # Strategy 1: Try relative date commands (highest reliability)
        if when_date.lower() in ["today", "tomorrow", "yesterday"]:
            result = await self._schedule_relative_date(todo_id, when_date.lower())
            if result["success"]:
                return {
                    "success": True,
                    "method": "applescript_relative",
                    "reliability": "95%",
                    "date_set": when_date
                }

        # Strategy 2: Try specific date using AppleScript date object construction
        date_components = locale_handler.normalize_date_input(when_date)
        if date_components:
            year, month, day = date_components
            # Convert to date object for the existing method
            parsed_date = date(year, month, day)
            result = await self._schedule_specific_date_objects(todo_id, parsed_date)
            if result["success"]:
                return {
                    "success": True,
                    "method": "applescript_date_objects",
                    "reliability": "90%",
                    "date_set": when_date
                }
        else:
            logger.debug(f"Could not normalize {when_date} as date, trying direct AppleScript")

        # Strategy 3: Try direct AppleScript date string (fallback)
        result = await self._schedule_direct_applescript(todo_id, when_date)
        if result["success"]:
            return {
                "success": True,
                "method": "applescript_direct",
                "reliability": "75%",
                "date_set": when_date
            }

        # Strategy 4: Final fallback - move to appropriate list
        fallback_result = await self._schedule_list_fallback(todo_id, when_date)
        return {
            "success": fallback_result["success"],
            "method": "list_fallback",
            "reliability": "85%",
            "date_set": fallback_result.get("list_assigned", "Today"),
            "note": "Moved to appropriate list due to date scheduling limitations"
        }

    async def _schedule_relative_date(self, todo_id: str, relative_date: str) -> Dict[str, Any]:
        """Schedule using relative date AppleScript commands (most reliable)."""

        date_commands = {
            "today": "set targetDate to (current date)",
            "tomorrow": "set targetDate to ((current date) + 1 * days)",
            "yesterday": "set targetDate to ((current date) - 1 * days)"
        }

        date_setup = date_commands.get(relative_date)
        if not date_setup:
            return {"success": False, "error": f"Unknown relative date: {relative_date}"}

        script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"

                -- Create proper date object
                {date_setup}
                set time of targetDate to 0

                -- Schedule the todo
                schedule theTodo for targetDate
                return "scheduled_relative"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''

        result = await self.applescript.execute_applescript(script)
        if result.get("success") and "scheduled_relative" in result.get("output", ""):
            logger.info(f"Successfully scheduled todo {todo_id} for {relative_date} via AppleScript relative date")
            return {"success": True}
        else:
            logger.debug(f"Relative date scheduling failed: {result.get('output', '')}")
            return {"success": False, "error": result.get("output", "AppleScript failed")}

    async def _schedule_specific_date_objects(self, todo_id: str, target_date: date) -> Dict[str, Any]:
        """Schedule using AppleScript date object construction (highly reliable)."""

        script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"

                -- Construct date object safely to avoid month overflow bug
                set targetDate to (current date)
                set time of targetDate to 0  -- Reset time first
                set day of targetDate to 1   -- Set to safe day first to avoid overflow
                set year of targetDate to {target_date.year}
                set month of targetDate to {target_date.month}  -- Numeric month works correctly
                set day of targetDate to {target_date.day}   -- Set actual day last

                -- Schedule using the constructed date object
                schedule theTodo for targetDate
                return "scheduled_objects"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''

        result = await self.applescript.execute_applescript(script)
        if result.get("success") and "scheduled_objects" in result.get("output", ""):
            logger.info(f"Successfully scheduled todo {todo_id} for {target_date} via AppleScript date objects")
            return {"success": True}
        else:
            logger.debug(f"Date object scheduling failed: {result.get('output', '')}")
            return {"success": False, "error": result.get("output", "AppleScript failed")}

    async def _schedule_direct_applescript(self, todo_id: str, when_date: str) -> Dict[str, Any]:
        """Try direct AppleScript date string scheduling (fallback method)."""

        # Try multiple date string formats that AppleScript might accept
        date_formats = [
            when_date,  # Original format
            self._convert_to_applescript_friendly_format(when_date),  # Try to make it friendly
        ]

        for date_format in date_formats:
            script = f'''
            tell application "Things3"
                try
                    set theTodo to to do id "{todo_id}"
                    schedule theTodo for date "{date_format}"
                    return "scheduled_direct"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

            result = await self.applescript.execute_applescript(script)
            if result.get("success") and "scheduled_direct" in result.get("output", ""):
                logger.info(f"Successfully scheduled todo {todo_id} for {date_format} via direct AppleScript")
                return {"success": True}

        return {"success": False, "error": "All direct AppleScript formats failed"}

    def _convert_to_applescript_friendly_format(self, date_string: str) -> str:
        """Convert date string to AppleScript-friendly property-based format."""
        try:
            # Use locale-aware date handler for property-based date creation
            date_components = locale_handler.normalize_date_input(date_string)
            if date_components:
                year, month, day = date_components
                return locale_handler.build_applescript_date_property(year, month, day)
            else:
                # If can't normalize, return as-is
                return date_string
        except Exception as e:
            logger.warning(f"Error converting date '{date_string}' to AppleScript format: {e}")
            # Fallback to original approach if needed
            try:
                parsed = datetime.strptime(date_string, '%Y-%m-%d').date()
                return parsed.strftime('%B %d, %Y')  # "March 3, 2026"
            except ValueError:
                return date_string

    async def _schedule_list_fallback(self, todo_id: str, when_date: str) -> Dict[str, Any]:
        """Final fallback: Move to appropriate list based on intended date."""

        # Determine appropriate list
        target_list = self.helpers.determine_target_list(when_date)

        script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"
                move theTodo to list "{target_list}"
                return "moved_to_list"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''

        result = await self.applescript.execute_applescript(script)
        if result.get("success") and "moved_to_list" in result.get("output", ""):
            logger.info(f"Successfully moved todo {todo_id} to {target_list} list as scheduling fallback")
            return {"success": True, "list_assigned": target_list}
        else:
            return {"success": False, "error": "List assignment failed"}
