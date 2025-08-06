"""Core tools implementation for Things 3 MCP server."""

import asyncio
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from .applescript_manager import AppleScriptManager

logger = logging.getLogger(__name__)


class ThingsTools:
    """Core tools for Things 3 operations."""
    
    def __init__(self, applescript_manager: AppleScriptManager):
        """Initialize with AppleScript manager.
        
        Args:
            applescript_manager: AppleScript manager instance
        """
        self.applescript = applescript_manager
        logger.info("Things tools initialized")
    
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
        """Convert ISO date (YYYY-MM-DD) to AppleScript-compatible DD/MM/YYYY format.
        
        Args:
            iso_date: Date in YYYY-MM-DD format
            
        Returns:
            Date in DD/MM/YYYY format (European) or original string if parsing fails
        """
        try:
            parsed = datetime.strptime(iso_date, '%Y-%m-%d').date()
            return parsed.strftime('%d/%m/%Y')  # DD/MM/YYYY for European locale
        except ValueError:
            # Return original if not in expected format
            return iso_date
    
    def _parse_relative_date(self, date_input: str) -> str:
        """Parse relative date input like 'tomorrow', 'Friday', etc. to YYYY-MM-DD format.
        
        Args:
            date_input: User input date string
            
        Returns:
            Formatted date string or original input if not recognized
        """
        if not date_input:
            return date_input
            
        input_lower = date_input.lower().strip()
        today = datetime.now().date()
        
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
    
    async def add_todo(self, title: str, notes: Optional[str] = None, tags: Optional[List[str]] = None,
                 when: Optional[str] = None, deadline: Optional[str] = None,
                 list_id: Optional[str] = None, list_title: Optional[str] = None,
                 heading: Optional[str] = None, checklist_items: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new todo in Things.
        
        Args:
            title: Todo title
            notes: Optional notes
            tags: Optional list of tags (will be created if they don't exist)
            when: When to schedule (today, tomorrow, evening, anytime, someday, or YYYY-MM-DD)
            deadline: Deadline date (YYYY-MM-DD)
            list_id: Project or area ID
            list_title: Project or area title
            heading: Heading to add under
            checklist_items: Checklist items to add
            
        Returns:
            Dict with created todo information including the ID of created todo
        """
        try:
            created_tags = []
            existing_tags = []
            
            # Check and create missing tags if needed
            if tags:
                # Get existing tags
                existing_tag_names = []
                try:
                    current_tags = await self.get_tags(include_items=False)
                    existing_tag_names = [tag.get('name', '').lower() for tag in current_tags]
                except Exception as e:
                    logger.warning(f"Could not fetch existing tags: {e}")
                
                # Check each requested tag
                for tag in tags:
                    tag_lower = tag.lower()
                    if tag_lower not in existing_tag_names:
                        # Tag doesn't exist, create it
                        escaped_tag = self._escape_applescript_string(tag)
                        create_script = f'''
                        tell application "Things3"
                            try
                                make new tag with properties {{name:{escaped_tag}}}
                                return "created"
                            on error errMsg
                                return "error: " & errMsg
                            end try
                        end tell
                        '''
                        
                        create_result = await self.applescript.execute_applescript(create_script, cache_key=None)
                        if create_result.get("success") and "created" in create_result.get("output", ""):
                            created_tags.append(tag)
                            logger.info(f"Created new tag: {tag}")
                        else:
                            logger.warning(f"Could not create tag '{tag}': {create_result.get('output', '')}")
                    else:
                        existing_tags.append(tag)
            
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
                    # For specific dates, try to use the schedule command
                    # Convert various formats to what AppleScript accepts
                    if when_lower == "yesterday":
                        schedule_command = "schedule newTodo for (current date) - 1 * days"
                    elif "/" in when or "-" in when:
                        # Specific date format - convert to AppleScript-compatible format
                        try:
                            # Convert ISO date to MM/DD/YYYY format for AppleScript
                            applescript_date = self._convert_iso_to_applescript_date(parsed_when)
                            schedule_command = f'schedule newTodo for date "{applescript_date}"'
                        except:
                            # Fallback: put in Today list without scheduling
                            target_list = "Today"
                    else:
                        # Other formats - try as-is
                        schedule_command = f'schedule newTodo for date "{when}"'

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
                    # For specific dates, use the due date property during creation
                    if "/" in deadline or "-" in deadline:
                        # Convert ISO date to MM/DD/YYYY format for AppleScript
                        applescript_date = self._convert_iso_to_applescript_date(parsed_deadline)
                        due_date_property = f'due date:date "{applescript_date}"'
                    else:
                        # Try as-is
                        due_date_property = f'due date:date "{deadline}"'

            # Add checklist items to notes if specified  
            # Note: Things 3 doesn't support checklist items via AppleScript properties
            if checklist_items:
                checklist_text = "Checklist:\n" + "\n".join([f"- [ ] {item}" for item in checklist_items])
                if notes:
                    notes = notes + "\n\n" + checklist_text
                else:
                    notes = checklist_text
            
            # Prepare properties for the new todo
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
            
            # Add tags if specified
            if tags:
                for tag in tags:
                    escaped_tag = self._escape_applescript_string(tag)
                    script_parts.append(f'        try')
                    script_parts.append(f'            set targetTag to first tag whose name is {escaped_tag}')
                    script_parts.append(f'            set tag names of newTodo to (tag names of newTodo) & {{targetTag}}')
                    script_parts.append(f'        on error')
                    script_parts.append(f'            -- Tag might not exist, skip')
                    script_parts.append(f'        end try')
            
            
            # Apply scheduling if specified
            if schedule_command:
                script_parts.append(f'        {schedule_command}')
            
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
            
            if result.get("success"):
                output = result.get("output", "").strip()
                
                if output.startswith("error:"):
                    logger.error(f"Failed to create todo: {output}")
                    return {
                        "success": False,
                        "error": output
                    }
                
                # The output should be the todo ID
                todo_id = output
                
                # Create response with todo information
                todo_data = {
                    "id": todo_id,
                    "uuid": todo_id,
                    "title": title,
                    "notes": notes,
                    "tags": tags or [],
                    "when": when,
                    "deadline": deadline,
                    "list_id": list_id,
                    "list_title": list_title,
                    "heading": heading,
                    "checklist_items": checklist_items or [],
                    "created_at": datetime.now().isoformat()
                }
                
                # Build informative message
                message_parts = ["Todo created successfully"]
                if created_tags:
                    message_parts.append(f"Created new tag(s): {', '.join(created_tags)}")
                if existing_tags:
                    message_parts.append(f"Applied existing tag(s): {', '.join(existing_tags)}")
                
                logger.info(f"Successfully created todo with ID {todo_id}: {title}")
                return {
                    "success": True,
                    "message": ". ".join(message_parts),
                    "todo": todo_data,
                    "tags_created": created_tags,
                    "tags_existing": existing_tags
                }
            else:
                logger.error(f"Failed to create todo: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
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
        try:
            created_tags = []
            existing_tags = []
            
            # Check and create missing tags if needed
            if tags is not None:
                # Get existing tags
                existing_tag_names = []
                try:
                    current_tags = await self.get_tags(include_items=False)
                    existing_tag_names = [tag.get('name', '').lower() for tag in current_tags]
                except Exception as e:
                    logger.warning(f"Could not fetch existing tags: {e}")
                
                # Check each requested tag
                for tag in tags:
                    tag_lower = tag.lower()
                    if tag_lower not in existing_tag_names:
                        # Tag doesn't exist, create it
                        escaped_tag = self._escape_applescript_string(tag)
                        create_script = f'''
                        tell application "Things3"
                            try
                                make new tag with properties {{name:{escaped_tag}}}
                                return "created"
                            on error errMsg
                                return "error: " & errMsg
                            end try
                        end tell
                        '''
                        
                        create_result = await self.applescript.execute_applescript(create_script, cache_key=None)
                        if create_result.get("success") and "created" in create_result.get("output", ""):
                            created_tags.append(tag)
                            logger.info(f"Created new tag: {tag}")
                        else:
                            logger.warning(f"Could not create tag '{tag}': {create_result.get('output', '')}")
                    else:
                        existing_tags.append(tag)
            
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
            
            # Handle scheduling (when) - use schedule command for dates
            if when is not None:
                parsed_when = self._parse_relative_date(when)
                when_lower = parsed_when.lower() if parsed_when else ""
                # Handle relative dates with AppleScript date arithmetic or direct commands
                if when_lower == "today":
                    script_parts.append('        schedule theTodo for (current date)')
                elif when_lower == "tomorrow":
                    script_parts.append('        schedule theTodo for ((current date) + 1 * days)')
                elif when_lower in ['anytime', 'someday']:
                    # These are special Things states - move to appropriate list
                    script_parts.append(f'        move theTodo to list "{when_lower.title()}"')
                elif "/" in when or "-" in when:
                    # For specific dates, convert to AppleScript-compatible format
                    try:
                        applescript_date = self._convert_iso_to_applescript_date(parsed_when)
                        script_parts.append(f'        schedule theTodo for date "{applescript_date}"')
                    except:
                        # Fallback: clear scheduling
                        logger.warning(f"Could not parse date: {when}")
                else:
                    # Try as-is for other formats
                    script_parts.append(f'        schedule theTodo for date "{when}"')
            
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
                        # For specific dates, set the due date directly
                        if "/" in deadline or "-" in deadline:
                            # Convert ISO date to MM/DD/YYYY format for AppleScript
                            applescript_date = self._convert_iso_to_applescript_date(parsed_deadline)
                            script_parts.append(f'        set due date of theTodo to date "{applescript_date}"')
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
            
            script = '\n'.join(script_parts)
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get("success"):
                output = result.get("output", "")
                if "updated" in output:
                    # Build informative message
                    message_parts = ["Todo updated successfully"]
                    if created_tags:
                        message_parts.append(f"Created new tag(s): {', '.join(created_tags)}")
                    if existing_tags:
                        message_parts.append(f"Applied existing tag(s): {', '.join(existing_tags)}")
                    
                    logger.info(f"Successfully updated todo: {todo_id}")
                    return {
                        "success": True,
                        "message": ". ".join(message_parts),
                        "todo_id": todo_id,
                        "updated_at": datetime.now().isoformat(),
                        "tags_created": created_tags,
                        "tags_existing": existing_tags
                    }
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
                    "error": result.get("error", "AppleScript execution failed")
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
                return {{id:id of theTodo, name:name of theTodo, notes:notes of theTodo, status:status of theTodo, tag_names:tag names of theTodo, creation_date:creation date of theTodo, modification_date:modification date of theTodo}}
            end tell
            '''
            
            # Don't cache individual todo fetches as they can change frequently
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get("success"):
                # Parse the result using our AppleScript parser
                raw_records = self.applescript._parse_applescript_list(result.get("output", ""))
                
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
    
    async def delete_todo(self, todo_id: str) -> Dict[str, str]:
        """Delete a todo from Things.
        
        Args:
            todo_id: ID of the todo to delete
            
        Returns:
            Dict with deletion result
        """
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
            
            if result.get("success"):
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
                    "error": result.get("error", "Unknown error")
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
            
            # Convert to standardized format
            result = []
            for project in projects:
                project_dict = {
                    "id": project.get("id"),
                    "uuid": project.get("id"),
                    "title": project.get("name", ""),
                    "notes": project.get("notes", ""),
                    "status": project.get("status", "open"),
                    "creation_date": project.get("creation_date"),
                    "modification_date": project.get("modification_date"),
                    "tags": [],  # TODO: Extract tags
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
        try:
            created_tags = []
            existing_tags = []
            
            # Check and create missing tags if needed
            if tags:
                # Get existing tags
                existing_tag_names = []
                try:
                    current_tags = await self.get_tags(include_items=False)
                    existing_tag_names = [tag.get('name', '').lower() for tag in current_tags]
                except Exception as e:
                    logger.warning(f"Could not fetch existing tags: {e}")
                
                # Check each requested tag
                for tag in tags:
                    tag_lower = tag.lower()
                    if tag_lower not in existing_tag_names:
                        # Tag doesn't exist, create it
                        escaped_tag = self._escape_applescript_string(tag)
                        create_script = f'''
                        tell application "Things3"
                            try
                                make new tag with properties {{name:{escaped_tag}}}
                                return "created"
                            on error errMsg
                                return "error: " & errMsg
                            end try
                        end tell
                        '''
                        
                        create_result = await self.applescript.execute_applescript(create_script, cache_key=None)
                        if create_result.get("success") and "created" in create_result.get("output", ""):
                            created_tags.append(tag)
                            logger.info(f"Created new tag: {tag}")
                        else:
                            logger.warning(f"Could not create tag '{tag}': {create_result.get('output', '')}")
                    else:
                        existing_tags.append(tag)
            
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
            
            if result.get("success") and not result.get("output", "").startswith("error:"):
                # Parse the project info
                output = result.get("output", "")
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
                            todo_result = await self.add_todo(
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
                error_msg = result.get("output", "Unknown error")
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
            
            if result.get("success"):
                logger.info(f"Successfully updated project: {project_id}")
                return {
                    "success": True,
                    "message": "Project updated successfully",
                    "project_id": project_id,
                    "updated_at": datetime.now().isoformat()
                }
            else:
                error_msg = result.get("error", "Unknown error")
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
        """Get completed todos from Logbook.
        
        Args:
            limit: Maximum number of entries
            period: Time period to look back
            
        Returns:
            List of completed todo dictionaries
        """
        return await self._get_list_todos("logbook", limit=limit)
    
    async def get_trash(self) -> List[Dict[str, Any]]:
        """Get trashed todos."""
        return await self._get_list_todos("trash")
    
    async def get_tags(self, include_items: bool = False) -> List[Dict[str, Any]]:
        """Get all tags.
        
        Args:
            include_items: Include items tagged with each tag
            
        Returns:
            List of tag dictionaries
        """
        try:
            # Build AppleScript to get all tags with IDs and names
            script = '''
            tell application "Things3"
                set tagNames to name of every tag
                set tagIds to id of every tag
                set tagList to {}
                
                repeat with i from 1 to count of tagNames
                    set tagList to tagList & {item i of tagIds & "|" & item i of tagNames}
                end repeat
                
                return tagList
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, "tags_all")
            
            if result.get("success"):
                output = result.get("output", "")
                tags = []
                
                if output and output.strip():
                    # Parse the output which is now in format: tag1id|tag1name, tag2id|tag2name, ...
                    tag_entries = output.strip().split(', ')
                    
                    for entry in tag_entries:
                        entry = entry.strip()
                        if entry and "|" in entry:
                            # Parse id and name from "tagid|tagname"
                            parts = entry.split('|', 1)
                            if len(parts) == 2:
                                tag_id = parts[0].strip()
                                tag_name = parts[1].strip()
                            
                                if tag_id and tag_name:
                                    tag_dict = {
                                        "id": tag_id,
                                        "uuid": tag_id,
                                        "name": tag_name,
                                        "shortcut": "",  # Skip shortcut for performance
                                        "items": []
                                    }
                                    
                                    # If include_items is requested, get items with this tag
                                    if include_items and tag_name:
                                        try:
                                            tag_dict["items"] = await self.get_tagged_items(tag_name)
                                        except Exception as e:
                                            logger.warning(f"Failed to get items for tag '{tag_name}': {e}")
                                    
                                    tags.append(tag_dict)
                
                logger.info(f"Retrieved {len(tags)} tags with IDs")
                return tags
            else:
                logger.error(f"Failed to get tags: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting tags: {e}")
            raise
    
    async def get_tagged_items(self, tag: str) -> List[Dict[str, Any]]:
        """Get items with a specific tag.
        
        Args:
            tag: Tag title to filter by
            
        Returns:
            List of tagged item dictionaries
        """
        try:
            # Build AppleScript to get items with specific tag using 'whose' clause
            escaped_tag = self._escape_applescript_string(tag)
            script = f'''
            tell application "Things3"
                set matchingItems to {{}}
                
                try
                    -- Get all todos with this tag using whose clause (most reliable)
                    set taggedTodos to (to dos whose tag names contains {escaped_tag})
                    set itemCount to count of taggedTodos
                    
                    repeat with theTodo in taggedTodos
                        try
                            set todoID to id of theTodo
                            set todoName to name of theTodo
                            set todoNotes to notes of theTodo
                            set todoStatus to status of theTodo
                            
                            -- Replace newlines in notes with space to avoid parsing issues
                            set AppleScript's text item delimiters to return
                            set notesParts to text items of todoNotes
                            set AppleScript's text item delimiters to " "
                            set todoNotes to notesParts as text
                            set AppleScript's text item delimiters to ""
                            
                            -- Use a unique delimiter that won't appear in text
                            set delimiter to "§§§"
                            
                            -- Create delimited format for easier parsing
                            set itemRecord to todoID & delimiter & todoName & delimiter & todoNotes & delimiter & todoStatus
                            set matchingItems to matchingItems & {{itemRecord}}
                        on error
                            -- Skip if can't access this todo
                        end try
                    end repeat
                on error errMsg
                    -- Return empty if tag doesn't exist or error occurs
                    return {{}}
                end try
                
                return matchingItems
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, f"tagged_items_{tag}")
            
            if result.get("success"):
                output = result.get("output", "")
                items = []
                
                if output and output.strip():
                    # Parse AppleScript list output with custom delimiter
                    # Format: "id§§§name§§§notes§§§status", "id§§§name§§§notes§§§status"
                    entries = output.strip().split(', ')
                    
                    for entry in entries:
                        entry = entry.strip()
                        if entry and "§§§" in entry:
                            # Parse the delimited format: id§§§name§§§notes§§§status
                            parts = entry.split("§§§")
                            if len(parts) >= 2:  # At minimum need ID and name
                                item_id = parts[0].strip()
                                item_name = parts[1].strip() if len(parts) > 1 else ""
                                item_notes = parts[2].strip() if len(parts) > 2 else ""
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
                
                logger.info(f"Retrieved {len(items)} items with tag: {tag}")
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
                todos = self._parse_applescript_todos(result.get("output", ""))
                
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
            
            # Date filters (if provided)
            if deadline:
                # Convert YYYY-MM-DD to AppleScript date comparison
                conditions.append(f'due date is not missing value')
                # Note: More complex date comparisons would need date parsing
            
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
            
            if result.get("success"):
                # Parse using existing parser
                todos = self._parse_applescript_todos(result.get("output", ""))
                
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
        """Get recently created items.
        
        Args:
            period: Time period (e.g., '3d', '1w', '2m', '1y')
            
        Returns:
            List of recent item dictionaries
        """
        try:
            # Parse the period to get number of days
            days = self._parse_period_to_days(period)
            
            # Build AppleScript to get recent items
            script = f'''
            tell application "Things3"
                set recentItems to {{}}
                set cutoffDate to (current date) - ({days} * days)
                
                -- Get recent todos
                repeat with theTodo in to dos
                    try
                        set todoCreationDate to creation date of theTodo
                        if todoCreationDate > cutoffDate then
                            set itemRecord to {{}}
                            set itemRecord to itemRecord & {{id:(id of theTodo)}}
                            set itemRecord to itemRecord & {{name:(name of theTodo)}}
                            set itemRecord to itemRecord & {{notes:(notes of theTodo)}}
                            set itemRecord to itemRecord & {{status:(status of theTodo)}}
                            set itemRecord to itemRecord & {{tag_names:(tag names of theTodo)}}
                            set itemRecord to itemRecord & {{creation_date:todoCreationDate}}
                            set itemRecord to itemRecord & {{modification_date:(modification date of theTodo)}}
                            set itemRecord to itemRecord & {{item_type:"todo"}}
                            
                            try
                                set todoProject to project of theTodo
                                if todoProject is not missing value then
                                    set itemRecord to itemRecord & {{project_id:(id of todoProject)}}
                                end if
                            on error
                                -- Todo has no project
                            end try
                            
                            set recentItems to recentItems & {{itemRecord}}
                        end if
                    on error
                        -- Skip todos that can't be accessed
                    end try
                end repeat
                
                -- Get recent projects
                repeat with theProject in projects
                    try
                        set projectCreationDate to creation date of theProject
                        if projectCreationDate > cutoffDate then
                            set itemRecord to {{}}
                            set itemRecord to itemRecord & {{id:(id of theProject)}}
                            set itemRecord to itemRecord & {{name:(name of theProject)}}
                            set itemRecord to itemRecord & {{notes:(notes of theProject)}}
                            set itemRecord to itemRecord & {{status:(status of theProject)}}
                            set itemRecord to itemRecord & {{tag_names:(tag names of theProject)}}
                            set itemRecord to itemRecord & {{creation_date:projectCreationDate}}
                            set itemRecord to itemRecord & {{modification_date:(modification date of theProject)}}
                            set itemRecord to itemRecord & {{item_type:"project"}}
                            
                            try
                                set projectArea to area of theProject
                                if projectArea is not missing value then
                                    set itemRecord to itemRecord & {{area_id:(id of projectArea)}}
                                end if
                            on error
                                -- Project has no area
                            end try
                            
                            set recentItems to recentItems & {{itemRecord}}
                        end if
                    on error
                        -- Skip projects that can't be accessed
                    end try
                end repeat
                
                return recentItems
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, f"recent_items_{period}")
            
            if result.get("success"):
                # Parse the AppleScript output
                raw_records = self.applescript._parse_applescript_list(result.get("output", ""))
                
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
        """Move a todo to a different list in Things using AppleScript 'move' command.
        
        This function moves a todo to one of Things' standard lists. Note that some moves may
        fail if the todo doesn't meet the requirements for the destination list (e.g., moving
        to 'upcoming' requires the todo to have a start date set).
        
        Args:
            todo_id: ID of the todo to move
            destination_list: Name of the destination list. Valid options are:
                - inbox: Inbox list (default location for new todos)
                - today: Today list (scheduled for today)
                - anytime: Anytime list (todos without specific schedule)
                - someday: Someday list (todos for someday/maybe)
                - upcoming: Upcoming list (todos with future start dates)
                - logbook: Logbook list (completed todos)
            
        Returns:
            Dict with move operation result containing:
                - success: Boolean indicating if move succeeded
                - message: Success/error message
                - todo_id: ID of the todo that was moved
                - destination_list: Target list name
                - moved_at: Timestamp of successful move (only on success)
                - error: Error details (only on failure)
        """
        try:
            # Validate destination list
            valid_lists = ["inbox", "today", "anytime", "someday", "upcoming", "logbook"]
            if destination_list.lower() not in valid_lists:
                raise ValueError(f"Invalid destination list: {destination_list}. Valid options are: {', '.join(valid_lists)}")
            
            # Normalize the destination list name
            normalized_destination = destination_list.lower()
            
            # Build AppleScript to move the todo
            escaped_todo_id = self._escape_applescript_string(todo_id)
            
            # Use Things' native 'move' command with proper list reference
            script = f'''
            tell application "Things3"
                try
                    set theTodo to to do id {escaped_todo_id}
                    set targetList to list "{normalized_destination}"
                    move theTodo to targetList
                    return "moved"
                on error errMsg
                    return "error: " & errMsg
                end try
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get("success"):
                output = result.get("output", "").strip()
                
                if "moved" in output:
                    logger.info(f"Successfully moved todo {todo_id} to {destination_list}")
                    return {
                        "success": True,
                        "message": f"Todo moved to {destination_list} successfully",
                        "todo_id": todo_id,
                        "destination_list": destination_list,
                        "moved_at": datetime.now().isoformat()
                    }
                elif output.startswith("error:"):
                    error_msg = output.replace("error: ", "")
                    logger.error(f"AppleScript error moving todo {todo_id}: {error_msg}")
                    
                    # Provide more helpful error messages for common issues
                    if "Cannot move" in error_msg and normalized_destination == "upcoming":
                        friendly_error = "Cannot move to Upcoming list. The todo may need a start date set to appear in Upcoming."
                    elif "Cannot move" in error_msg and normalized_destination == "logbook":
                        friendly_error = "Cannot move to Logbook. Only completed todos can be moved to Logbook."
                    else:
                        friendly_error = f"Failed to move todo: {error_msg}"
                    
                    return {
                        "success": False,
                        "error": friendly_error,
                        "todo_id": todo_id,
                        "destination_list": destination_list
                    }
                else:
                    logger.error(f"Unexpected AppleScript output: {output}")
                    return {
                        "success": False,
                        "error": f"Unexpected response: {output}",
                        "todo_id": todo_id,
                        "destination_list": destination_list
                    }
            else:
                error_msg = result.get("error", "AppleScript execution failed")
                logger.error(f"Failed to execute move AppleScript: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "todo_id": todo_id,
                    "destination_list": destination_list
                }
        
        except Exception as e:
            logger.error(f"Error moving todo: {e}")
            raise
    
    # Removed show_item and search_items methods as they trigger UI changes
    # which are not appropriate for MCP server operations
    
    async def _get_list_todos(self, list_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get todos from a specific list.
        
        Args:
            list_name: Name of the list (inbox, today, etc.)
            limit: Optional limit on number of results
            
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
            
            # Build AppleScript to get todos from the specified list with proper limiting
            limit_clause = ""
            if limit:
                limit_clause = f"""
                set allTodos to to dos of listRef
                set itemCount to count of allTodos
                set maxItems to {limit}
                
                if itemCount > 0 then
                    if itemCount > maxItems then
                        set itemsToProcess to maxItems
                    else
                        set itemsToProcess to itemCount
                    end if
                    
                    repeat with i from 1 to itemsToProcess
                        set theTodo to item i of allTodos
                        set todoRecord to {{}}
                        try
                            set todoRecord to todoRecord & {{id:id of theTodo}}
                            set todoRecord to todoRecord & {{name:name of theTodo}}
                            set todoRecord to todoRecord & {{notes:notes of theTodo}}
                            set todoRecord to todoRecord & {{status:status of theTodo}}
                            set todoRecord to todoRecord & {{tag_names:tag names of theTodo}}
                            set todoRecord to todoRecord & {{creation_date:creation date of theTodo}}
                            set todoRecord to todoRecord & {{modification_date:modification date of theTodo}}
                            set todoList to todoList & {{todoRecord}}
                        end try
                    end repeat
                end if"""
            else:
                limit_clause = """
                repeat with theTodo in to dos of listRef
                    set todoRecord to {{}}
                    try
                        set todoRecord to todoRecord & {{id:id of theTodo}}
                        set todoRecord to todoRecord & {{name:name of theTodo}}
                        set todoRecord to todoRecord & {{notes:notes of theTodo}}
                        set todoRecord to todoRecord & {{status:status of theTodo}}
                        set todoRecord to todoRecord & {{tag_names:tag names of theTodo}}
                        set todoRecord to todoRecord & {{creation_date:creation date of theTodo}}
                        set todoRecord to todoRecord & {{modification_date:modification date of theTodo}}
                        set todoList to todoList & {{todoRecord}}
                    end try
                end repeat"""
            
            script = f'''
            tell application "Things3"
                set todoList to {{}}
                set listRef to list "{list_mapping[list_name]}"
                {limit_clause}
                return todoList
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, f"list_{list_name}")
            
            if result.get("success"):
                # Parse the AppleScript output
                todos = self._parse_applescript_todos(result.get("output", ""))
                
                # Limit is already applied in AppleScript, so no need for post-processing
                logger.info(f"Retrieved {len(todos)} todos from {list_name}")
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
                    "start_date": record.get("start_date")
                }
                todos.append(todo)
                
            logger.debug(f"Parsed {len(todos)} todos from AppleScript output")
            
        except Exception as e:
            logger.error(f"Error parsing AppleScript output: {e}")
        
        return todos
    
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
