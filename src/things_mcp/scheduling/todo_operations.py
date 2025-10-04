"""Todo and project creation/update operations."""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from ..locale_aware_dates import locale_handler
from ..utils.applescript_utils import AppleScriptTemplates

logger = logging.getLogger(__name__)


class TodoOperations:
    """Handles todo and project creation/update operations."""

    def __init__(self, applescript_manager, scheduler):
        """Initialize with AppleScript manager and scheduler.

        Args:
            applescript_manager: AppleScript execution manager
            scheduler: Scheduling strategies instance
        """
        self.applescript = applescript_manager
        self.scheduler = scheduler

    def _convert_to_boolean(self, value: Any) -> Optional[bool]:
        """
        Convert various input formats to boolean.

        Handles:
        - Boolean values: True, False
        - String values: "true", "True", "TRUE", "false", "False", "FALSE"
        - None and empty strings return None

        Args:
            value: The value to convert

        Returns:
            True, False, or None if value is None/empty

        Raises:
            ValueError: If value cannot be converted to boolean
        """
        if value is None or value == '':
            return None

        # Already a boolean
        if isinstance(value, bool):
            return value

        # String conversion
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower == 'true':
                return True
            elif value_lower == 'false':
                return False
            else:
                raise ValueError(f"Invalid boolean string: '{value}'. Must be 'true' or 'false'")

        # Fallback for any other type - use Python's truthiness
        return bool(value)

    def _build_create_todo_script(self, title: str, notes: str, tags: List[str],
                                  deadline: str, area: str, project: str,
                                  checklist: List[str]) -> str:
        """Build AppleScript for creating a new todo.

        Args:
            title: Todo title
            notes: Todo notes
            tags: Tags list
            deadline: Deadline date
            area: Area name or ID
            project: Project ID
            checklist: Checklist items

        Returns:
            AppleScript code
        """
        escaped_title = AppleScriptTemplates.escape_string(title)
        escaped_notes = AppleScriptTemplates.escape_string(notes)

        script = f'''
            tell application "Things3"
                try
                    set newTodo to make new to do with properties {{name:{escaped_title}}}
            '''

        if notes:
            script += f'set notes of newTodo to {escaped_notes}\n                    '

        if area:
            escaped_area = AppleScriptTemplates.escape_string(area)
            script += f'set area of newTodo to area {escaped_area}\n                    '

        if project:
            script += f'set project of newTodo to project id "{project}"\n                    '

        if tags:
            tags_string = ', '.join(tags)
            escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
            script += f'set tag names of newTodo to {escaped_tags_string}\n                    '

        # NOTE: Checklist items are NOT supported via AppleScript (Things 3 API limitation)
        # The checklist parameter is accepted but we don't generate AppleScript for it
        # A warning is added in the response instead
        # if checklist:
        #     for item in checklist:
        #         escaped_item = AppleScriptTemplates.escape_string(item)
        #         script += f'make new checklist item in newTodo with properties {{name:{escaped_item}}}\n                    '

        if deadline:
            date_components = locale_handler.normalize_date_input(deadline)
            if date_components:
                year, month, day = date_components
                script += f'''
                    set deadlineDate to (current date)
                    set time of deadlineDate to 0
                    set day of deadlineDate to 1
                    set year of deadlineDate to {year}
                    set month of deadlineDate to {month}
                    set day of deadlineDate to {day}
                    set due date of newTodo to deadlineDate
                    '''

        script += '''
                    return id of newTodo
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

        return script

    async def add_todo(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new todo using AppleScript, or URL scheme if checklist items are provided."""
        try:
            # Extract parameters
            notes = kwargs.get('notes', '')
            tags = kwargs.get('tags', [])
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', '')
            area = kwargs.get('area', '')
            project = kwargs.get('project', '') or kwargs.get('list_id', '')
            checklist = kwargs.get('checklist_items') or []
            heading = kwargs.get('heading', '')
            list_title = kwargs.get('list_title', '')

            # If checklist items are provided, use Things URL scheme (only way to create checklists)
            if checklist:
                return await self._add_todo_with_checklist(
                    title=title,
                    notes=notes,
                    tags=tags,
                    when=when,
                    deadline=deadline,
                    list_id=project,
                    list_title=list_title,
                    heading=heading,
                    checklist_items=checklist
                )

            # Otherwise use AppleScript (faster, more reliable for non-checklist todos)
            script = self._build_create_todo_script(title, notes, tags, deadline,
                                                    area, project, checklist)
            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                todo_id = result.get("output", "").strip()
                if todo_id and not todo_id.startswith("error:"):
                    # Build response
                    response = {
                        "success": True,
                        "todo_id": todo_id
                    }

                    # Schedule if when date provided
                    if when:
                        schedule_result = await self.scheduler.schedule_todo_reliable(todo_id, when)
                        response["message"] = "Todo created and scheduled successfully"
                        response["scheduling"] = schedule_result
                    else:
                        response["message"] = "Todo created successfully"

                    return response
                return {
                    "success": False,
                    "error": todo_id,
                    "message": "Failed to create todo"
                }
            return {
                "success": False,
                "error": result.get("output", "AppleScript execution failed"),
                "message": "Failed to create todo"
            }

        except Exception as e:
            logger.error(f"Error adding todo: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add todo"
            }

    async def _add_todo_with_checklist(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a todo with checklist items using Things URL scheme.

        This is the only way to create checklist items, as AppleScript doesn't support them.

        Args:
            title: Todo title
            notes: Optional notes
            tags: Optional tag list
            when: Optional scheduling date
            deadline: Optional deadline date
            list_id: Optional project/area ID
            list_title: Optional project/area title
            heading: Optional heading within project
            checklist_items: List of checklist item titles

        Returns:
            Dict with success status and todo information
        """
        try:
            import time
            from urllib.parse import quote

            # Build URL parameters
            params = {
                'title': title
            }

            # Add optional parameters
            if kwargs.get('notes'):
                params['notes'] = kwargs['notes']

            if kwargs.get('tags'):
                # Tags are comma-separated in URL scheme
                params['tags'] = ','.join(kwargs['tags'])

            if kwargs.get('when'):
                params['when'] = kwargs['when']

            if kwargs.get('deadline'):
                params['deadline'] = kwargs['deadline']

            if kwargs.get('list_id'):
                params['list'] = kwargs['list_id']
            elif kwargs.get('list_title'):
                params['list'] = kwargs['list_title']

            if kwargs.get('heading'):
                params['heading'] = kwargs['heading']

            # Add checklist items (newline-separated, URL-encoded)
            if kwargs.get('checklist_items'):
                items = kwargs['checklist_items']
                logger.debug(f"Checklist items received: type={type(items)}, value={repr(items)}")

                # Handle both string and list inputs
                if isinstance(items, str):
                    # If it's already a newline-separated string, use it as-is
                    # If it's a single item, it will work too
                    params['checklist-items'] = items
                elif isinstance(items, list):
                    # Convert list to newline-separated string
                    params['checklist-items'] = '\n'.join(items)
                    logger.debug(f"Joined list to string: {repr(params['checklist-items'])}")
                else:
                    # Fallback: convert to string
                    params['checklist-items'] = str(items)

                logger.debug(f"Final checklist-items param: {repr(params['checklist-items'])}")

            # Execute URL scheme
            logger.debug(f"Creating todo with checklist via URL scheme: {params}")
            result = await self.applescript.execute_url_scheme('add', params)

            if not result.get('success'):
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "message": "Failed to create todo via URL scheme"
                }

            # URL scheme doesn't return the todo ID, so we need to find it
            # Wait a moment for Things to process the URL
            await asyncio.sleep(0.5)

            # Search for the newly created todo by title
            # Use AppleScript to find it
            search_script = f'''
            tell application "Things3"
                try
                    set foundTodos to to dos whose name is {AppleScriptTemplates.escape_string(title)}
                    if (count of foundTodos) > 0 then
                        -- Get the most recently created one
                        set newestTodo to item 1 of foundTodos
                        set newestDate to creation date of newestTodo
                        repeat with aTodo in foundTodos
                            if creation date of aTodo > newestDate then
                                set newestTodo to aTodo
                                set newestDate to creation date of aTodo
                            end if
                        end repeat
                        return id of newestTodo
                    else
                        return "error: Todo not found after creation"
                    end if
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

            search_result = await self.applescript.execute_applescript(search_script)

            # Calculate checklist count correctly
            checklist_items = kwargs.get('checklist_items', [])
            if isinstance(checklist_items, str):
                item_count = len([item.strip() for item in checklist_items.split('\n') if item.strip()])
            elif isinstance(checklist_items, list):
                item_count = len(checklist_items)
            else:
                item_count = 0

            if search_result.get('success'):
                todo_id = search_result.get('output', '').strip()
                if todo_id and not todo_id.startswith('error:'):
                    return {
                        "success": True,
                        "todo_id": todo_id,
                        "message": f"Todo created with {item_count} checklist items",
                        "checklist_count": item_count
                    }
                else:
                    # Todo was created but we couldn't find it
                    return {
                        "success": True,
                        "message": "Todo created with checklist but ID could not be retrieved",
                        "warning": "Todo ID not available",
                        "checklist_count": item_count
                    }
            else:
                # Todo was likely created but we couldn't find it
                return {
                    "success": True,
                    "message": "Todo created with checklist but ID could not be retrieved",
                    "warning": "Todo ID not available",
                    "checklist_count": item_count
                }

        except Exception as e:
            logger.error(f"Error adding todo with checklist: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add todo with checklist"
            }

    async def add_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Add checklist items to an existing todo using Things URL scheme.

        Args:
            todo_id: ID of the todo to add checklist items to
            items: List of checklist item titles to add

        Returns:
            Dict with success status and operation details
        """
        try:
            if not items:
                return {
                    "success": False,
                    "error": "No checklist items provided",
                    "message": "At least one checklist item is required"
                }

            # Build URL parameters for appending checklist items
            params = {
                'id': todo_id,
                'append-checklist-items': '\n'.join(items)
            }

            logger.debug(f"Adding {len(items)} checklist items to todo {todo_id}")
            result = await self.applescript.execute_url_scheme('update', params)

            if result.get('success'):
                return {
                    "success": True,
                    "message": f"Added {len(items)} checklist items",
                    "items_added": len(items)
                }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "message": "Failed to add checklist items"
                }

        except Exception as e:
            logger.error(f"Error adding checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add checklist items"
            }

    async def prepend_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Prepend checklist items to an existing todo using Things URL scheme.

        Args:
            todo_id: ID of the todo to prepend checklist items to
            items: List of checklist item titles to prepend

        Returns:
            Dict with success status and operation details
        """
        try:
            if not items:
                return {
                    "success": False,
                    "error": "No checklist items provided",
                    "message": "At least one checklist item is required"
                }

            # Build URL parameters for prepending checklist items
            params = {
                'id': todo_id,
                'prepend-checklist-items': '\n'.join(items)
            }

            logger.debug(f"Prepending {len(items)} checklist items to todo {todo_id}")
            result = await self.applescript.execute_url_scheme('update', params)

            if result.get('success'):
                return {
                    "success": True,
                    "message": f"Prepended {len(items)} checklist items",
                    "items_added": len(items)
                }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "message": "Failed to prepend checklist items"
                }

        except Exception as e:
            logger.error(f"Error prepending checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to prepend checklist items"
            }

    async def replace_checklist_items(self, todo_id: str, items: List[str]) -> Dict[str, Any]:
        """Replace all checklist items in a todo using Things URL scheme.

        Args:
            todo_id: ID of the todo to replace checklist items in
            items: List of checklist item titles to replace with

        Returns:
            Dict with success status and operation details
        """
        try:
            # Build URL parameters for replacing checklist items
            params = {
                'id': todo_id,
                'checklist-items': '\n'.join(items) if items else ''
            }

            logger.debug(f"Replacing checklist items in todo {todo_id} with {len(items)} new items")
            result = await self.applescript.execute_url_scheme('update', params)

            if result.get('success'):
                return {
                    "success": True,
                    "message": f"Replaced checklist with {len(items)} items",
                    "items_count": len(items)
                }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error'),
                    "message": "Failed to replace checklist items"
                }

        except Exception as e:
            logger.error(f"Error replacing checklist items: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to replace checklist items"
            }

    def _build_update_script(self, todo_id: str, title: str, notes: str, tags: List[str],
                            deadline: str, area: str, project: str,
                            completed: Optional[bool], canceled: Optional[bool]) -> str:
        """Build AppleScript for updating a todo.

        Args:
            todo_id: Todo ID to update
            title: New title (or empty)
            notes: New notes (or empty)
            tags: New tags list
            deadline: New deadline date
            area: New area
            project: New project
            completed: Completion status
            canceled: Canceled status

        Returns:
            AppleScript code
        """
        script = f'''
            tell application "Things3"
                try
                    set targetTodo to to do id "{todo_id}"
            '''

        # Update title if provided
        if title:
            escaped_title = AppleScriptTemplates.escape_string(title)
            script += f'set name of targetTodo to {escaped_title}\n                    '

        # Update notes if provided
        if notes:
            escaped_notes = AppleScriptTemplates.escape_string(notes)
            script += f'set notes of targetTodo to {escaped_notes}\n                    '

        # Update area if provided
        if area:
            escaped_area = AppleScriptTemplates.escape_string(area)
            script += f'set area of targetTodo to area {escaped_area}\n                    '

        # Update project if provided
        if project:
            escaped_project = AppleScriptTemplates.escape_string(project)
            script += f'set project of targetTodo to project {escaped_project}\n                    '

        # Update tags if provided
        if tags:
            tags_string = ', '.join(tags)
            escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
            script += f'set tag names of targetTodo to {escaped_tags_string}\n                    '

        # Update deadline if provided
        if deadline:
            date_components = locale_handler.normalize_date_input(deadline)
            if date_components:
                year, month, day = date_components
                script += f'''
                    set deadlineDate to (current date)
                    set time of deadlineDate to 0
                    set day of deadlineDate to 1
                    set year of deadlineDate to {year}
                    set month of deadlineDate to {month}
                    set day of deadlineDate to {day}
                    set due date of targetTodo to deadlineDate
                    '''

        # Update status
        if canceled is not None and canceled:
            script += 'set status of targetTodo to canceled\n                    '
        elif completed is not None:
            if completed:
                script += 'set status of targetTodo to completed\n                    '
            else:
                script += 'set status of targetTodo to open\n                    '

        script += '''
                    return "updated"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

        return script

    async def update_todo(self, todo_id: str, **kwargs) -> Dict[str, Any]:
        """Update an existing todo using AppleScript."""
        try:
            # Extract parameters
            title = kwargs.get('title', '')
            notes = kwargs.get('notes', '')
            tags = kwargs.get('tags', [])
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', '')
            area = kwargs.get('area', '')
            project = kwargs.get('project', '')

            # Convert status parameters
            completed = kwargs.get('completed', None)
            canceled = kwargs.get('canceled', None)

            try:
                if completed is not None:
                    completed = self._convert_to_boolean(completed)
                if canceled is not None:
                    canceled = self._convert_to_boolean(canceled)
            except ValueError as e:
                return {
                    "success": False,
                    "error": str(e),
                    "message": "Invalid boolean value for status parameter"
                }

            # Build and execute script
            script = self._build_update_script(todo_id, title, notes, tags, deadline,
                                              area, project, completed, canceled)
            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                output = result.get("output", "").strip()
                if output == "updated":
                    # Schedule if when date provided
                    if when:
                        schedule_result = await self.scheduler.schedule_todo_reliable(todo_id, when)
                        return {
                            "success": True,
                            "message": "Todo updated and scheduled successfully",
                            "scheduling": schedule_result
                        }
                    return {
                        "success": True,
                        "message": "Todo updated successfully"
                    }
                return {
                    "success": False,
                    "error": output,
                    "message": "Failed to update todo"
                }
            return {
                "success": False,
                "error": result.get("output", "AppleScript execution failed"),
                "message": "Failed to update todo"
            }

        except Exception as e:
            logger.error(f"Error updating todo: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update todo"
            }

    def _build_create_project_script(self, title: str, notes: str, tags: List[str],
                                     deadline: str, area_id: str, area_title: str, todos: List[str]) -> str:
        """Build AppleScript for creating a new project.

        Args:
            title: Project title
            notes: Project notes
            tags: Tags list
            deadline: Deadline date
            area_id: Area UUID (takes precedence if provided)
            area_title: Area name
            todos: Initial todos to create in project

        Returns:
            AppleScript code
        """
        escaped_title = AppleScriptTemplates.escape_string(title)
        escaped_notes = AppleScriptTemplates.escape_string(notes)

        script = f'''
            tell application "Things3"
                try
                    set newProject to make new project with properties {{name:{escaped_title}}}
            '''

        if notes:
            script += f'set notes of newProject to {escaped_notes}\n                    '

        # Set area: prefer area_id (UUID) over area_title (name)
        if area_id:
            escaped_area_id = AppleScriptTemplates.escape_string(area_id)
            script += f'set area of newProject to area id {escaped_area_id}\n                    '
        elif area_title:
            escaped_area_title = AppleScriptTemplates.escape_string(area_title)
            script += f'set area of newProject to area {escaped_area_title}\n                    '

        if tags:
            tags_string = ', '.join(tags)
            escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
            script += f'set tag names of newProject to {escaped_tags_string}\n                    '

        if deadline:
            date_components = locale_handler.normalize_date_input(deadline)
            if date_components:
                year, month, day = date_components
                script += f'''
                    set deadlineDate to (current date)
                    set time of deadlineDate to 0
                    set day of deadlineDate to 1
                    set year of deadlineDate to {year}
                    set month of deadlineDate to {month}
                    set day of deadlineDate to {day}
                    set due date of newProject to deadlineDate
                    '''

        if todos:
            for todo_title in todos:
                if todo_title.strip():
                    escaped_todo = AppleScriptTemplates.escape_string(todo_title.strip())
                    script += f'''
                    set newTodoInProject to make new to do in newProject with properties {{name:{escaped_todo}}}
                        '''

        script += '''
                    return id of newProject
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

        return script

    async def add_project(self, title: str, **kwargs) -> Dict[str, Any]:
        """Add a new project using AppleScript."""
        try:
            # Extract parameters
            notes = kwargs.get('notes', '')
            tags = kwargs.get('tags', [])
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', '')

            # Separate area_id (UUID) and area_title (name) for proper AppleScript syntax
            area_id = kwargs.get('area_id', '')
            area_title = kwargs.get('area_title', '') or kwargs.get('area', '')  # 'area' param is treated as title

            # Handle todos parameter - can be string (newline-separated) or list
            todos_param = kwargs.get('todos', [])
            if isinstance(todos_param, str):
                # Split by newlines and filter out empty strings
                todos = [t.strip() for t in todos_param.split('\n') if t.strip()]
            elif isinstance(todos_param, list):
                todos = todos_param
            else:
                todos = []

            # Build and execute script
            script = self._build_create_project_script(title, notes, tags, deadline, area_id, area_title, todos)
            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                project_id = result.get("output", "").strip()
                if project_id and not project_id.startswith("error:"):
                    # Schedule if when date provided
                    if when:
                        schedule_result = await self.scheduler.schedule_todo_reliable(project_id, when)
                        return {
                            "success": True,
                            "project_id": project_id,
                            "message": "Project created and scheduled successfully",
                            "scheduling": schedule_result
                        }
                    return {
                        "success": True,
                        "project_id": project_id,
                        "message": "Project created successfully"
                    }
                return {
                    "success": False,
                    "error": project_id,
                    "message": "Failed to create project"
                }
            return {
                "success": False,
                "error": result.get("output", "AppleScript execution failed"),
                "message": "Failed to create project"
            }

        except Exception as e:
            logger.error(f"Error adding project: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add project"
            }

    async def update_project(self, project_id: str, **kwargs) -> Dict[str, Any]:
        """Update an existing project using AppleScript."""
        try:
            # Extract parameters
            title = kwargs.get('title', '')
            notes = kwargs.get('notes', '')
            tags = kwargs.get('tags', [])
            when = kwargs.get('when', '')
            deadline = kwargs.get('deadline', '')

            # Separate area_id (UUID) and area_title (name) for proper AppleScript syntax
            area_id = kwargs.get('area_id', '')
            area_title = kwargs.get('area_title', '') or kwargs.get('area', '')  # 'area' param is treated as title

            completed = kwargs.get('completed', None)

            # Start building the AppleScript
            script = f'''
            tell application "Things3"
                try
                    set targetProject to project id "{project_id}"
            '''

            # Update title if provided
            if title:
                escaped_title = AppleScriptTemplates.escape_string(title)
                script += f'set name of targetProject to {escaped_title}\n                    '

            # Update notes if provided
            if notes:
                escaped_notes = AppleScriptTemplates.escape_string(notes)
                script += f'set notes of targetProject to {escaped_notes}\n                    '

            # Update area if provided: prefer area_id (UUID) over area_title (name)
            if area_id:
                escaped_area_id = AppleScriptTemplates.escape_string(area_id)
                script += f'set area of targetProject to area id {escaped_area_id}\n                    '
            elif area_title:
                escaped_area_title = AppleScriptTemplates.escape_string(area_title)
                script += f'set area of targetProject to area {escaped_area_title}\n                    '

            # Update tags if provided
            if tags:
                # Things 3 expects tags as comma-separated string, not AppleScript list
                tags_string = ', '.join(tags)
                escaped_tags_string = AppleScriptTemplates.escape_string(tags_string)
                script += f'set tag names of targetProject to {escaped_tags_string}\n                    '

            # Update deadline if provided
            if deadline:
                date_components = locale_handler.normalize_date_input(deadline)
                if date_components:
                    year, month, day = date_components
                    script += f'''
                    set deadlineDate to (current date)
                    set time of deadlineDate to 0
                    set day of deadlineDate to 1
                    set year of deadlineDate to {year}
                    set month of deadlineDate to {month}
                    set day of deadlineDate to {day}
                    set due date of targetProject to deadlineDate
                    '''

            # Update completion status if provided
            if completed is not None:
                if completed:
                    script += 'set completion date of targetProject to (current date)\n                    '
                else:
                    script += 'set completion date of targetProject to missing value\n                    '

            script += '''
                    return "updated"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''

            result = await self.applescript.execute_applescript(script)

            if result.get("success"):
                output = result.get("output", "").strip()
                if output == "updated":
                    # Schedule the project if when date is provided
                    if when:
                        schedule_result = await self.scheduler.schedule_todo_reliable(project_id, when)
                        return {
                            "success": True,
                            "message": "Project updated and scheduled successfully",
                            "scheduling": schedule_result
                        }
                    else:
                        return {
                            "success": True,
                            "message": "Project updated successfully"
                        }
                else:
                    return {
                        "success": False,
                        "error": output,
                        "message": "Failed to update project"
                    }
            else:
                return {
                    "success": False,
                    "error": result.get("output", "AppleScript execution failed"),
                    "message": "Failed to update project"
                }

        except Exception as e:
            logger.error(f"Error updating project: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to update project"
            }
