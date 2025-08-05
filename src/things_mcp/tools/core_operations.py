"""
Core Operations Tools

Implements the fundamental CRUD operations for Things 3 objects:
- Create todos, projects, areas
- Read/retrieve items
- Update existing items
- Delete items
"""

from typing import Optional, List, Dict, Any
from fastmcp import FastMCP

from ..models.things_models import Todo, Project, Area, Tag, TodoResult
from ..models.response_models import OperationResult
from ..services.applescript_manager import AppleScriptManager
from ..services.validation_service import ValidationService
from ..utils.date_utils import parse_natural_date


class CoreOperationsTools:
    """Core CRUD operations for Things 3 objects"""
    
    def __init__(
        self, 
        mcp: FastMCP,
        applescript_manager: AppleScriptManager,
        validation_service: ValidationService
    ):
        self.mcp = mcp
        self.applescript = applescript_manager
        self.validator = validation_service
        self._register_tools()
    
    def _register_tools(self):
        """Register all core operation tools with FastMCP"""
        
        @self.mcp.tool
        async def add_todo(
            title: str,
            notes: Optional[str] = None,
            project: Optional[str] = None,
            area: Optional[str] = None,
            tags: Optional[List[str]] = None,
            when: Optional[str] = None,
            deadline: Optional[str] = None,
            checklist_items: Optional[List[str]] = None
        ) -> TodoResult:
            """
            Add a new todo to Things 3
            
            Args:
                title: The todo title (required)
                notes: Optional notes for the todo
                project: Project name to add todo to
                area: Area name to add todo to  
                tags: List of tags to apply
                when: When to schedule (today, tomorrow, evening, anytime, someday, or YYYY-MM-DD)
                deadline: Deadline date (YYYY-MM-DD or natural language)
                checklist_items: List of checklist items to add
                
            Returns:
                TodoResult with success status and todo details
                
            Examples:
                - add_todo("Buy groceries", when="today", tags=["errands"])
                - add_todo("Review proposal", project="Work", deadline="2024-01-15")
                - add_todo("Plan vacation", area="Personal", when="someday")
            """
            try:
                # Validate required parameters
                validation_result = await self.validator.validate_todo_creation(
                    title=title,
                    project=project,
                    area=area,
                    when=when,
                    deadline=deadline
                )
                
                if not validation_result.is_valid:
                    return TodoResult(
                        success=False,
                        error="VALIDATION_ERROR",
                        message=validation_result.error_message,
                        details=validation_result.errors
                    )
                
                # Parse dates
                parsed_when = parse_natural_date(when) if when else None
                parsed_deadline = parse_natural_date(deadline) if deadline else None
                
                # Build URL scheme parameters
                url_params = {"title": title}
                
                if notes:
                    url_params["notes"] = notes
                if parsed_when:
                    url_params["when"] = parsed_when
                if parsed_deadline:
                    url_params["deadline"] = parsed_deadline
                if tags:
                    url_params["tags"] = ",".join(tags)
                if project:
                    url_params["list"] = project
                elif area:
                    url_params["list"] = area
                if checklist_items:
                    url_params["checklist-items"] = "\n".join(checklist_items)
                
                # Execute via URL scheme (primary method)
                result = await self.applescript.execute_url_scheme(
                    action="add",
                    parameters=url_params,
                    cache_key=None  # Don't cache creation operations
                )
                
                if result.success:
                    return TodoResult(
                        success=True,
                        message=f"Todo '{title}' created successfully",
                        todo=Todo(
                            name=title,
                            notes=notes,
                            project_name=project,
                            area_name=area,
                            tag_names=tags or [],
                            scheduled_date=parsed_when,
                            due_date=parsed_deadline
                        )
                    )
                else:
                    return TodoResult(
                        success=False,
                        error="EXECUTION_ERROR",
                        message=f"Failed to create todo: {result.error}",
                        details={"applescript_error": result.error}
                    )
                    
            except Exception as e:
                return TodoResult(
                    success=False,
                    error="UNEXPECTED_ERROR",
                    message=f"Unexpected error: {str(e)}"
                )
        
        @self.mcp.tool
        async def get_todos(
            list_name: Optional[str] = None,
            include_completed: bool = False,
            include_canceled: bool = False,
            tag_filter: Optional[List[str]] = None,
            limit: Optional[int] = 50
        ) -> OperationResult:
            """
            Retrieve todos from Things 3
            
            Args:
                list_name: Specific list name (Inbox, Today, Upcoming, Anytime, Someday, or project/area name)
                include_completed: Include completed todos
                include_canceled: Include canceled todos  
                tag_filter: Filter by specific tags
                limit: Maximum number of todos to return
                
            Returns:
                OperationResult with list of todos
                
            Examples:
                - get_todos("Today")
                - get_todos("Work Project", include_completed=True)
                - get_todos(tag_filter=["urgent", "work"])
            """
            try:
                # Build AppleScript query
                script_parts = ['tell application "Things3"']
                
                # Determine target list
                if list_name:
                    if list_name.lower() in ["inbox", "today", "upcoming", "anytime", "someday"]:
                        script_parts.append(f'set targetList to list "{list_name}"')
                    else:
                        # Try as project first, then area
                        script_parts.append(f'try')
                        script_parts.append(f'  set targetList to project "{list_name}"')
                        script_parts.append(f'on error')
                        script_parts.append(f'  set targetList to area "{list_name}"')
                        script_parts.append(f'end try')
                else:
                    script_parts.append('set targetList to application "Things3"')
                
                # Build todo query with filters
                query_conditions = []
                if not include_completed:
                    query_conditions.append('status is not completed')
                if not include_canceled:
                    query_conditions.append('status is not canceled')
                
                if query_conditions:
                    where_clause = ' and '.join(query_conditions)
                    script_parts.append(f'set todoList to (to dos of targetList whose {where_clause})')
                else:
                    script_parts.append('set todoList to (to dos of targetList)')
                
                # Limit results
                if limit:
                    script_parts.append(f'if length of todoList > {limit} then')
                    script_parts.append(f'  set todoList to items 1 thru {limit} of todoList')
                    script_parts.append('end if')
                
                # Extract todo data
                script_parts.append('set results to {}')
                script_parts.append('repeat with aTodo in todoList')
                script_parts.append('  set todoData to {')
                script_parts.append('    name:(name of aTodo),')
                script_parts.append('    notes:(notes of aTodo),')
                script_parts.append('    id:(id of aTodo),')
                script_parts.append('    status:(status of aTodo as string),')
                script_parts.append('    creation_date:(creation date of aTodo),')
                script_parts.append('    due_date:(due date of aTodo),')
                script_parts.append('    tag_names:(tag names of aTodo)}')
                script_parts.append('  set end of results to todoData')
                script_parts.append('end repeat')
                script_parts.append('return results')
                script_parts.append('end tell')
                
                script = '\n'.join(script_parts)
                
                # Execute AppleScript
                cache_key = f"get_todos_{list_name}_{include_completed}_{include_canceled}_{tag_filter}_{limit}"
                result = await self.applescript.execute_applescript(
                    script=script,
                    script_name="get_todos",
                    cache_key=cache_key
                )
                
                if result.success:
                    # Parse AppleScript output into Todo objects
                    todos = self._parse_todos_from_applescript(result.output)
                    
                    # Apply tag filter if specified
                    if tag_filter:
                        todos = [
                            todo for todo in todos 
                            if any(tag in todo.tag_names for tag in tag_filter)
                        ]
                    
                    return OperationResult(
                        success=True,
                        data={
                            "todos": [todo.dict() for todo in todos],
                            "count": len(todos),
                            "list_name": list_name,
                            "filters": {
                                "include_completed": include_completed,
                                "include_canceled": include_canceled,
                                "tag_filter": tag_filter
                            }
                        },
                        message=f"Retrieved {len(todos)} todos"
                    )
                else:
                    return OperationResult(
                        success=False,
                        error="EXECUTION_ERROR",
                        message=f"Failed to retrieve todos: {result.error}"
                    )
                    
            except Exception as e:
                return OperationResult(
                    success=False,
                    error="UNEXPECTED_ERROR",
                    message=f"Unexpected error: {str(e)}"
                )
        
        @self.mcp.tool
        async def update_todo(
            todo_id: str,
            title: Optional[str] = None,
            notes: Optional[str] = None,
            project: Optional[str] = None,
            area: Optional[str] = None,
            tags: Optional[List[str]] = None,
            when: Optional[str] = None,
            deadline: Optional[str] = None,
            status: Optional[str] = None
        ) -> TodoResult:
            """
            Update an existing todo in Things 3
            
            Args:
                todo_id: Unique identifier of the todo to update
                title: New title for the todo
                notes: New notes for the todo
                project: Move to project
                area: Move to area
                tags: Replace tags (comma-separated)
                when: Reschedule todo
                deadline: Update deadline
                status: Update status (open, completed, canceled)
                
            Returns:
                TodoResult with update status
                
            Examples:
                - update_todo("ABC123", title="Updated title")
                - update_todo("ABC123", status="completed")
                - update_todo("ABC123", project="New Project", when="tomorrow")
            """
            try:
                # Validate todo_id
                if not todo_id:
                    return TodoResult(
                        success=False,
                        error="VALIDATION_ERROR",
                        message="todo_id is required"
                    )
                
                # Build update script
                script_parts = ['tell application "Things3"']
                script_parts.append(f'set targetTodo to to do id "{todo_id}"')
                
                # Update properties
                if title:
                    script_parts.append(f'set name of targetTodo to "{title}"')
                if notes is not None:  # Allow empty string
                    script_parts.append(f'set notes of targetTodo to "{notes}"')
                if when:
                    parsed_when = parse_natural_date(when)
                    if parsed_when:
                        script_parts.append(f'set scheduled date of targetTodo to date "{parsed_when}"')
                if deadline:
                    parsed_deadline = parse_natural_date(deadline)
                    if parsed_deadline:
                        script_parts.append(f'set due date of targetTodo to date "{parsed_deadline}"')
                if status:
                    if status.lower() == "completed":
                        script_parts.append('set status of targetTodo to completed')
                    elif status.lower() == "canceled":
                        script_parts.append('set status of targetTodo to canceled')
                    elif status.lower() == "open":
                        script_parts.append('set status of targetTodo to open')
                
                # Handle tags
                if tags is not None:
                    tag_list = '", "'.join(tags) if tags else ""
                    script_parts.append(f'set tag names of targetTodo to {{"{tag_list}"}}')
                
                # Handle list movement
                if project:
                    script_parts.append(f'move targetTodo to project "{project}"')
                elif area:
                    script_parts.append(f'move targetTodo to area "{area}"')
                
                script_parts.append('return "Updated successfully"')
                script_parts.append('end tell')
                
                script = '\n'.join(script_parts)
                
                # Execute update
                result = await self.applescript.execute_applescript(
                    script=script,
                    script_name="update_todo"
                )
                
                if result.success:
                    return TodoResult(
                        success=True,
                        message=f"Todo {todo_id} updated successfully",
                        todo_id=todo_id
                    )
                else:
                    return TodoResult(
                        success=False,
                        error="EXECUTION_ERROR",
                        message=f"Failed to update todo: {result.error}"
                    )
                    
            except Exception as e:
                return TodoResult(
                    success=False,
                    error="UNEXPECTED_ERROR",
                    message=f"Unexpected error: {str(e)}"
                )
        
        @self.mcp.tool
        async def delete_todo(todo_id: str) -> OperationResult:
            """
            Delete a todo from Things 3
            
            Args:
                todo_id: Unique identifier of the todo to delete
                
            Returns:
                OperationResult with deletion status
                
            Examples:
                - delete_todo("ABC123")
            """
            try:
                if not todo_id:
                    return OperationResult(
                        success=False,
                        error="VALIDATION_ERROR",
                        message="todo_id is required"
                    )
                
                script = f'''
                tell application "Things3"
                    delete to do id "{todo_id}"
                    return "Deleted successfully"
                end tell
                '''
                
                result = await self.applescript.execute_applescript(
                    script=script,
                    script_name="delete_todo"
                )
                
                if result.success:
                    return OperationResult(
                        success=True,
                        message=f"Todo {todo_id} deleted successfully",
                        data={"todo_id": todo_id}
                    )
                else:
                    return OperationResult(
                        success=False,
                        error="EXECUTION_ERROR",
                        message=f"Failed to delete todo: {result.error}"
                    )
                    
            except Exception as e:
                return OperationResult(
                    success=False,
                    error="UNEXPECTED_ERROR",
                    message=f"Unexpected error: {str(e)}"
                )
    
    def _parse_todos_from_applescript(self, applescript_output: str) -> List[Todo]:
        """
        Parse AppleScript output into Todo objects.
        
        This is a simplified parser - in production, you'd want more robust
        parsing of AppleScript record syntax.
        """
        todos = []
        # Implementation would parse the AppleScript record format
        # For now, return empty list as placeholder
        return todos