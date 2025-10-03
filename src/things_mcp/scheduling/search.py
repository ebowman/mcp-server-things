"""Search and query operations for Things 3."""

import logging
from typing import Dict, Any, List, Optional

from .helpers import SchedulingHelpers
from ..utils.applescript_utils import AppleScriptTemplates

logger = logging.getLogger(__name__)


class SearchOperations:
    """Handles search and query operations."""

    def __init__(self, applescript_manager):
        """Initialize with AppleScript manager.

        Args:
            applescript_manager: AppleScript execution manager
        """
        self.applescript = applescript_manager
        self.helpers = SchedulingHelpers()

    def _build_list_selection_script(self, list_name: str, status: Optional[str]) -> str:
        """Build AppleScript for selecting which lists to search.

        Args:
            list_name: Specific list name to search, or empty for all lists
            status: Status filter ('completed', 'canceled', etc.)

        Returns:
            AppleScript code for list selection
        """
        if list_name:
            return f'set allTodos to to dos of list "{list_name}"\n'

        # Include active lists
        script = '''
                    set allTodos to allTodos & (to dos of list "Today")
                    set allTodos to allTodos & (to dos of list "Upcoming")
                    set allTodos to allTodos & (to dos of list "Anytime")
                    set allTodos to allTodos & (to dos of list "Someday")
                    set allTodos to allTodos & (to dos of list "Inbox")
                '''

        # Include Logbook if searching for completed or canceled todos
        if status and status.lower() in ['completed', 'canceled']:
            script += '''
                    set allTodos to allTodos & (to dos of list "Logbook")
                    '''

        return script

    def _build_search_filters_script(self, query: str, tags: List[str], area: str,
                                     project: str, status: Optional[str]) -> str:
        """Build AppleScript filter conditions for advanced search.

        Args:
            query: Search query for title/notes
            tags: List of tags to filter by
            area: Area name to filter by
            project: Project name to filter by
            status: Status filter ('incomplete', 'completed', 'canceled')

        Returns:
            AppleScript code for filter conditions
        """
        script = ''

        # Add query filter
        if query:
            escaped_query = AppleScriptTemplates.escape_string(query.lower()).strip('"')
            script += f'''
                        -- Check if query matches title or notes
                        set titleMatch to false
                        set notesMatch to false
                        try
                            if (name of aTodo as string) contains "{escaped_query}" then
                                set titleMatch to true
                            end if
                        end try
                        try
                            if (notes of aTodo as string) contains "{escaped_query}" then
                                set notesMatch to true
                            end if
                        end try
                        if not (titleMatch or notesMatch) then
                            set todoMatches to false
                        end if
                '''

        # Add tag filter
        if tags:
            for tag in tags:
                escaped_tag = AppleScriptTemplates.escape_string(tag).strip('"')
                script += f'''
                        -- Check if todo has the specified tag
                        try
                            set todoTags to tag names of aTodo
                            if not (todoTags contains "{escaped_tag}") then
                                set todoMatches to false
                            end if
                        on error
                            -- No tags, doesn't match
                            set todoMatches to false
                        end try
                    '''

        # Add area filter
        if area:
            escaped_area = AppleScriptTemplates.escape_string(area).strip('"')
            script += f'''
                        try
                            if (area of aTodo as string) is not equal to "{escaped_area}" then
                                set todoMatches to false
                            end if
                        on error
                            set todoMatches to false
                        end try
                '''

        # Add project filter
        if project:
            escaped_project = AppleScriptTemplates.escape_string(project).strip('"')
            script += f'''
                        try
                            if (project of aTodo as string) is not equal to "{escaped_project}" then
                                set todoMatches to false
                            end if
                        on error
                            set todoMatches to false
                        end try
                '''

        # Add status filter
        if status is not None:
            if status.lower() in ['incomplete', 'open']:
                script += '''
                        if status of aTodo is not equal to open then
                            set todoMatches to false
                        end if
                    '''
            elif status.lower() == 'completed':
                script += '''
                        if status of aTodo is not equal to completed then
                            set todoMatches to false
                        end if
                    '''
            elif status.lower() == 'canceled':
                script += '''
                        if status of aTodo is not equal to canceled then
                            set todoMatches to false
                        end if
                    '''

        return script

    def _parse_todo_info(self, info_string: str) -> Dict[str, Any]:
        """Parse the todo info string returned from AppleScript."""
        todo_dict = {
            'id': '',
            'uuid': '',
            'title': '',
            'notes': '',
            'tags': [],
            'status': 'open',  # Default status
            'deadline': '',
            'activation_date': '',
            'completion_date': '',
            'creation_date': ''
        }

        # Split by | and parse each part
        parts = info_string.split('|')
        for part in parts:
            if ':' in part:
                key, value = part.split(':', 1)
                if key == 'ID':
                    todo_dict['id'] = value
                    todo_dict['uuid'] = value
                elif key == 'TITLE':
                    todo_dict['title'] = value
                elif key == 'NOTES':
                    todo_dict['notes'] = value
                elif key == 'TAGS':
                    # Parse tags from string representation
                    if value and value != '{}':
                        tag_string = value.strip('{}')
                        todo_dict['tags'] = [tag.strip() for tag in tag_string.split(',') if tag.strip()]
                elif key == 'STATUS':
                    # AppleScript returns status as 'open', 'completed', or 'canceled'
                    # Store it as-is for now
                    todo_dict['status'] = value.lower()
                elif key == 'DEADLINE':
                    todo_dict['deadline'] = value
                elif key == 'ACTIVATION':
                    todo_dict['activation_date'] = value
                elif key == 'COMPLETED':
                    todo_dict['completion_date'] = value
                elif key == 'CREATED':
                    todo_dict['creation_date'] = value

        return todo_dict

    def _parse_search_results(self, output: Any) -> List[Dict[str, Any]]:
        """Parse search results from AppleScript output.

        Args:
            output: Raw output from AppleScript execution

        Returns:
            List of todo dictionaries
        """
        todos = []

        # Handle both list and string output formats
        if isinstance(output, list):
            for item in output:
                if isinstance(item, str) and item.startswith("ID:"):
                    todo_dict = self._parse_todo_info(item)
                    todos.append(todo_dict)
        elif isinstance(output, str) and output:
            # Split by ID: to separate todos
            if "ID:" in output:
                # Split by ', ID:' for comma-separated format
                if ", ID:" in output:
                    parts = output.split(", ID:")
                    # First part already has ID:, others need it added back
                    for i, part in enumerate(parts):
                        if i > 0:
                            part = "ID:" + part
                        todo_dict = self._parse_todo_info(part.strip())
                        todos.append(todo_dict)
                else:
                    # Single todo
                    todo_dict = self._parse_todo_info(output.strip())
                    todos.append(todo_dict)

        return todos

    async def search_advanced(self, **filters) -> List[Dict[str, Any]]:
        """Advanced search using AppleScript with multiple filters and limit support."""
        try:
            # Extract filter parameters
            query = filters.get('query', '')
            tags = filters.get('tags', [])
            area = filters.get('area', '')
            project = filters.get('project', '')
            list_name = filters.get('list', '')
            status = filters.get('status', None)
            limit = filters.get('limit', None)

            # Build AppleScript to search todos
            script = '''
            tell application "Things3"
                try
                    set matchingTodos to {}
                    set allTodos to {}
            '''

            # Add list selection
            script += self._build_list_selection_script(list_name, status)

            # Start results collection
            script += '''
                    set resultList to {}
                    set resultCount to 0

                    repeat with aTodo in allTodos
                        set todoMatches to true
            '''

            # Add search filters
            script += self._build_search_filters_script(query, tags, area, project, status)

            # Collect matching todos
            limit_value = limit if limit and limit > 0 else 999999
            script += f'''
                        if todoMatches then
                            if resultCount < {limit_value} then
                                set todoInfo to "ID:" & (id of aTodo) & "|TITLE:" & (name of aTodo)
                                try
                                    set todoInfo to todoInfo & "|NOTES:" & (notes of aTodo)
                                end try
                                try
                                    set todoInfo to todoInfo & "|TAGS:" & (tag names of aTodo as string)
                                end try
                                try
                                    set todoInfo to todoInfo & "|STATUS:" & (status of aTodo as string)
                                end try
                                set resultList to resultList & todoInfo
                                set resultCount to resultCount + 1
                            end if
                        end if
                    end repeat
                '''

            script += '''
                    return resultList
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

            result = await self.applescript.execute_applescript(script)
            if result.get("success"):
                output = result.get("output", "")
                logger.debug(f"search_advanced raw output: {output[:500] if output else 'empty'}")
                return self._parse_search_results(output)
            else:
                logger.error(f"Failed to perform advanced search: {result.get('output', 'Unknown error')}")
                return []

        except Exception as e:
            logger.error(f"Error in advanced search: {e}")
            return []

    async def get_recent(self, period: str) -> List[Dict[str, Any]]:
        """Get recently created items using AppleScript.

        This function searches ALL todos (not just completed ones) and filters
        by creation date to find items created within the specified time period.

        Args:
            period: Time period string (e.g., '1d', '3d', '1w', '2m', '1y')

        Returns:
            List of recently created todos with their details
        """
        try:
            # Parse period string to days
            days = self.helpers.parse_period_to_days(period)

            script = f'''
            tell application "Things3"
                try
                    set currentDate to (current date)
                    set pastDate to currentDate - ({days} * days)
                    set maxResults to 50

                    set resultList to {{}}
                    set resultCount to 0

                    -- Search only Inbox for now to avoid timeout
                    repeat with aTodo in (to dos of list "Inbox")
                        if creation date of aTodo is not missing value then
                            if creation date of aTodo >= pastDate then
                                -- Build the info string directly
                                set todoInfo to "ID:" & (id of aTodo) & "|TITLE:" & (name of aTodo)
                                set todoInfo to todoInfo & "|CREATED:" & (creation date of aTodo as string)
                                if status of aTodo is not missing value then
                                    set todoInfo to todoInfo & "|STATUS:" & (status of aTodo as string)
                                end if
                                -- Append string to list (not todo object)
                                set end of resultList to todoInfo
                                set resultCount to resultCount + 1

                                -- Limit results to prevent timeouts
                                if resultCount >= maxResults then exit repeat
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
                logger.error(f"Failed to get recent items: {result.get('output', 'Unknown error')}")
                return []

            output = result.get("output", "")

            # Handle both string (single item) and list (multiple items) outputs
            # AppleScript returns single-item lists as strings
            items = []
            if isinstance(output, str):
                # Single item returned as string
                if output and output.startswith("ID:"):
                    items = [output]
                else:
                    return []
            elif isinstance(output, list):
                items = output
            else:
                logger.warning(f"Unexpected output type: {type(output)}")
                return []

            if not items:
                return []

            # Parse the items
            todos = []
            for item in items:
                if isinstance(item, str) and item.startswith("ID:"):
                    try:
                        todo_dict = self._parse_todo_info(item)
                        todos.append(todo_dict)
                    except Exception as e:
                        logger.error(f"Error parsing todo info: {e}")
                        continue

            logger.info(f"Found {len(todos)} recent items within {period}")
            return todos

        except Exception as e:
            logger.error(f"Error getting recent items: {e}")
            return []
