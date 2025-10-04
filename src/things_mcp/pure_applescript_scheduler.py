#!/usr/bin/env python3
"""
Pure AppleScript Date Scheduling Implementation

This implementation primarily uses AppleScript for todo/project operations, focusing on making
AppleScript date scheduling 100% reliable using proper date object construction and the research
findings from the claude-flow hive-mind investigation.

**Exception: Checklist Operations**
The Things URL scheme is used ONLY for checklist item management (add/prepend/replace) because
the Things 3 AppleScript API does not support checklist items. This is the only way to create
and manage checklists programmatically.

Key Research Insights Applied:
1. Use AppleScript date objects, not string parsing
2. Construct dates using current date + offset for reliability
3. Use proper AppleScript date arithmetic patterns
4. Handle locale dependencies through date object construction

This class now acts as a facade, delegating to specialized scheduling modules.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from .scheduling import SchedulingHelpers, SchedulingStrategies, TodoOperations, SearchOperations

logger = logging.getLogger(__name__)


class PureAppleScriptScheduler:
    """100% AppleScript-based reliable scheduler for Things 3 date scheduling.

    This class acts as a facade, delegating to specialized modules:
    - SchedulingStrategies: Date scheduling strategies
    - TodoOperations: Todo and project creation/update
    - SearchOperations: Search and query operations
    - SchedulingHelpers: Utility methods
    """

    def __init__(self, applescript_manager):
        """Initialize with AppleScript manager and operation modules.

        Args:
            applescript_manager: AppleScript execution manager
        """
        self.applescript = applescript_manager

        # Initialize operation modules (Facade Pattern)
        self.strategies = SchedulingStrategies(applescript_manager)
        self.todo_ops = TodoOperations(applescript_manager, self.strategies)
        self.search_ops = SearchOperations(applescript_manager)
        self.helpers = SchedulingHelpers()

    # ========== SCHEDULING OPERATIONS (delegate to SchedulingStrategies) ==========

    async def schedule_todo_reliable(self, todo_id: str, when_date: str) -> Dict[str, Any]:
        """
        Reliable todo scheduling using ONLY AppleScript (no URL schemes).

        Args:
            todo_id: Things todo ID
            when_date: ISO date (YYYY-MM-DD) or relative date ("today", "tomorrow", etc.)

        Returns:
            Dict with success status and method used
        """
        return await self.strategies.schedule_todo_reliable(todo_id, when_date)

    # ========== TODO/PROJECT OPERATIONS (delegate to TodoOperations) ==========

    async def add_todo(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new todo using AppleScript."""
        return await self.todo_ops.add_todo(title, **kwargs)

    async def update_todo(self, todo_id: str, **kwargs) -> Dict[str, Any]:
        """Update an existing todo using AppleScript."""
        return await self.todo_ops.update_todo(todo_id, **kwargs)

    async def add_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Add checklist items to an existing todo."""
        return await self.todo_ops.add_checklist_items(todo_id, items)

    async def prepend_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Prepend checklist items to an existing todo."""
        return await self.todo_ops.prepend_checklist_items(todo_id, items)

    async def replace_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Replace all checklist items in a todo."""
        return await self.todo_ops.replace_checklist_items(todo_id, items)

    async def add_project(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new project using AppleScript."""
        return await self.todo_ops.add_project(title, **kwargs)

    async def update_project(self, project_id: str, **kwargs) -> Dict[str, Any]:
        """Update an existing project using AppleScript."""
        return await self.todo_ops.update_project(project_id, **kwargs)

    # ========== SEARCH OPERATIONS (delegate to SearchOperations) ==========

    async def search_advanced(self, **filters) -> List[Dict[str, Any]]:
        """Advanced search using AppleScript with multiple filters and limit support."""
        return await self.search_ops.search_advanced(**filters)

    async def get_recent(self, period: str) -> List[Dict[str, Any]]:
        """Get recently created items using AppleScript.

        Args:
            period: Time period string (e.g., '1d', '3d', '1w', '2m', '1y')

        Returns:
            List of recently created todos with their details
        """
        return await self.search_ops.get_recent(period)

    # ========== DATE QUERY OPERATIONS (currently in pure_applescript_scheduler.py) ==========
    # These methods are not yet extracted but could be moved to a DateQueryOperations module

    async def get_todos_due_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos due within specified days using AppleScript.

        Args:
            days: Number of days to look ahead

        Returns:
            List of todos due within the specified timeframe
        """
        try:
            # Calculate target date
            target_date = datetime.now() + timedelta(days=days)
            year, month, day = target_date.year, target_date.month, target_date.day

            script = f'''
            tell application "Things3"
                try
                    set targetDate to (current date)
                    set time of targetDate to 0
                    set day of targetDate to 1
                    set year of targetDate to {year}
                    set month of targetDate to {month}
                    set day of targetDate to {day}

                    set resultList to {{}}

                    repeat with aTodo in (to dos of list "Today")
                        if due date of aTodo is not missing value then
                            if due date of aTodo <= targetDate then
                                set todoInfo to "ID:" & (id of aTodo) & "|TITLE:" & (name of aTodo)
                                try
                                    set todoInfo to todoInfo & "|DEADLINE:" & (due date of aTodo as string)
                                end try
                                try
                                    set todoInfo to todoInfo & "|STATUS:" & (status of aTodo as string)
                                end try
                                set end of resultList to todoInfo
                            end if
                        end if
                    end repeat

                    repeat with aTodo in (to dos of list "Upcoming")
                        if due date of aTodo is not missing value then
                            if due date of aTodo <= targetDate then
                                set todoInfo to "ID:" & (id of aTodo) & "|TITLE:" & (name of aTodo)
                                try
                                    set todoInfo to todoInfo & "|DEADLINE:" & (due date of aTodo as string)
                                end try
                                try
                                    set todoInfo to todoInfo & "|STATUS:" & (status of aTodo as string)
                                end try
                                set end of resultList to todoInfo
                            end if
                        end if
                    end repeat

                    return resultList
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

            result = await self.applescript.execute_applescript(script)

            if not result.get("success"):
                logger.error(f"Failed to get due todos: {result.get('output', 'Unknown error')}")
                return []

            output = result.get("output", "")
            return self.search_ops._parse_search_results(output)

        except Exception as e:
            logger.error(f"Error getting due todos: {e}")
            return []

    async def get_todos_activating_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos activating within specified days using AppleScript.

        Args:
            days: Number of days to look ahead

        Returns:
            List of todos activating within the specified timeframe
        """
        try:
            # Calculate target date
            target_date = datetime.now() + timedelta(days=days)
            year, month, day = target_date.year, target_date.month, target_date.day

            script = f'''
            tell application "Things3"
                try
                    set targetDate to (current date)
                    set time of targetDate to 0
                    set day of targetDate to 1
                    set year of targetDate to {year}
                    set month of targetDate to {month}
                    set day of targetDate to {day}

                    set resultList to {{}}

                    repeat with aTodo in (to dos of list "Upcoming")
                        if activation date of aTodo is not missing value then
                            if activation date of aTodo <= targetDate then
                                set todoInfo to "ID:" & (id of aTodo) & "|TITLE:" & (name of aTodo)
                                try
                                    set todoInfo to todoInfo & "|ACTIVATION:" & (activation date of aTodo as string)
                                end try
                                try
                                    set todoInfo to todoInfo & "|STATUS:" & (status of aTodo as string)
                                end try
                                set end of resultList to todoInfo
                            end if
                        end if
                    end repeat

                    return resultList
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

            result = await self.applescript.execute_applescript(script)

            if not result.get("success"):
                logger.error(f"Failed to get activating todos: {result.get('output', 'Unknown error')}")
                return []

            output = result.get("output", "")
            return self.search_ops._parse_search_results(output)

        except Exception as e:
            logger.error(f"Error getting activating todos: {e}")
            return []

    async def get_todos_upcoming_in_days(self, days: int) -> List[Dict[str, Any]]:
        """Get todos upcoming (due or activating) within specified days.

        Args:
            days: Number of days to look ahead

        Returns:
            List of todos upcoming within the specified timeframe
        """
        try:
            due_todos = await self.get_todos_due_in_days(days)
            activating_todos = await self.get_todos_activating_in_days(days)

            # Combine and deduplicate by ID
            all_todos = {}
            for todo in due_todos + activating_todos:
                todo_id = todo.get('id') or todo.get('uuid')
                if todo_id and todo_id not in all_todos:
                    all_todos[todo_id] = todo

            return list(all_todos.values())

        except Exception as e:
            logger.error(f"Error getting upcoming todos: {e}")
            return []
