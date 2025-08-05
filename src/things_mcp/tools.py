"""Core tools implementation for Things 3 MCP server."""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from .applescript_manager import AppleScriptManager
from .models import Todo, Project, Area, Tag

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
    
    def get_todos(self, project_uuid: Optional[str] = None, include_items: bool = True) -> List[Dict[str, Any]]:
        """Get todos from Things, optionally filtered by project.
        
        Args:
            project_uuid: Optional project UUID to filter by
            include_items: Include checklist items
            
        Returns:
            List of todo dictionaries
        """
        try:
            todos = self.applescript.get_todos(project_uuid)
            
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
    
    def add_todo(self, title: str, notes: Optional[str] = None, tags: Optional[List[str]] = None,
                 when: Optional[str] = None, deadline: Optional[str] = None,
                 list_id: Optional[str] = None, list_title: Optional[str] = None,
                 heading: Optional[str] = None, checklist_items: Optional[List[str]] = None) -> Dict[str, Any]:
        """Create a new todo in Things.
        
        Args:
            title: Todo title
            notes: Optional notes
            tags: Optional list of tags
            when: When to schedule (today, tomorrow, evening, anytime, someday, or YYYY-MM-DD)
            deadline: Deadline date (YYYY-MM-DD)
            list_id: Project or area ID
            list_title: Project or area title
            heading: Heading to add under
            checklist_items: Checklist items to add
            
        Returns:
            Dict with created todo information
        """
        try:
            # Build URL scheme parameters
            params = {"title": title}
            
            if notes:
                params["notes"] = notes
            if tags:
                params["tags"] = ",".join(tags)
            if when:
                params["when"] = when
            if deadline:
                params["deadline"] = deadline
            if list_id:
                params["list-id"] = list_id
            elif list_title:
                params["list"] = list_title
            if heading:
                params["heading"] = heading
            if checklist_items:
                params["checklist-items"] = "\n".join(checklist_items)
            
            result = self.applescript.execute_url_scheme("add", params)
            
            if result.get("success"):
                # Create response with todo information
                todo_data = {
                    "title": title,
                    "notes": notes,
                    "tags": tags or [],
                    "when": when,
                    "deadline": deadline,
                    "list_id": list_id,
                    "list_title": list_title,
                    "heading": heading,
                    "checklist_items": checklist_items or [],
                    "created_at": datetime.now().isoformat(),
                    "url": result.get("url")
                }
                
                logger.info(f"Successfully created todo: {title}")
                return {
                    "success": True,
                    "message": "Todo created successfully",
                    "todo": todo_data
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
    
    def update_todo(self, todo_id: str, title: Optional[str] = None, notes: Optional[str] = None,
                    tags: Optional[List[str]] = None, when: Optional[str] = None,
                    deadline: Optional[str] = None, completed: Optional[bool] = None,
                    canceled: Optional[bool] = None) -> Dict[str, Any]:
        """Update an existing todo in Things.
        
        Args:
            todo_id: ID of the todo to update
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
            # Build URL scheme parameters
            params = {"id": todo_id}
            
            if title is not None:
                params["title"] = title
            if notes is not None:
                params["notes"] = notes
            if tags is not None:
                params["tags"] = ",".join(tags)
            if when is not None:
                params["when"] = when
            if deadline is not None:
                params["deadline"] = deadline
            if completed is not None:
                params["completed"] = "true" if completed else "false"
            if canceled is not None:
                params["canceled"] = "true" if canceled else "false"
            
            result = self.applescript.execute_url_scheme("update", params)
            
            if result.get("success"):
                logger.info(f"Successfully updated todo: {todo_id}")
                return {
                    "success": True,
                    "message": "Todo updated successfully",
                    "todo_id": todo_id,
                    "updated_at": datetime.now().isoformat()
                }
            else:
                logger.error(f"Failed to update todo: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
        
        except Exception as e:
            logger.error(f"Error updating todo: {e}")
            raise
    
    def get_todo_by_id(self, todo_id: str) -> Dict[str, Any]:
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
                return {{id:id of theTodo, name:name of theTodo, notes:notes of theTodo, status:status of theTodo, creation_date:creation date of theTodo, modification_date:modification date of theTodo}}
            end tell
            '''
            
            result = self.applescript.execute_applescript(script, f"todo_{todo_id}")
            
            if result.get("success"):
                # Parse the result (simplified for now)
                todo_data = {
                    "id": todo_id,
                    "uuid": todo_id,
                    "title": "Retrieved Todo",  # TODO: Parse from AppleScript output
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
    
    def delete_todo(self, todo_id: str) -> Dict[str, str]:
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
            
            result = self.applescript.execute_applescript(script)
            
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
    
    def get_projects(self, include_items: bool = False) -> List[Dict[str, Any]]:
        """Get all projects from Things.
        
        Args:
            include_items: Include tasks within projects
            
        Returns:
            List of project dictionaries
        """
        try:
            projects = self.applescript.get_projects()
            
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
    
    def add_project(self, title: str, notes: Optional[str] = None, tags: Optional[List[str]] = None,
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
            # Build URL scheme parameters
            params = {"title": title}
            
            if notes:
                params["notes"] = notes
            if tags:
                params["tags"] = ",".join(tags)
            if when:
                params["when"] = when
            if deadline:
                params["deadline"] = deadline
            if area_id:
                params["area-id"] = area_id
            elif area_title:
                params["area"] = area_title
            if todos:
                params["to-dos"] = "\n".join(todos)
            
            result = self.applescript.execute_url_scheme("add-project", params)
            
            if result.get("success"):
                project_data = {
                    "title": title,
                    "notes": notes,
                    "tags": tags or [],
                    "when": when,
                    "deadline": deadline,
                    "area_id": area_id,
                    "area_title": area_title,
                    "todos": todos or [],
                    "created_at": datetime.now().isoformat()
                }
                
                logger.info(f"Successfully created project: {title}")
                return {
                    "success": True,
                    "message": "Project created successfully",
                    "project": project_data
                }
            else:
                logger.error(f"Failed to create project: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
        
        except Exception as e:
            logger.error(f"Error adding project: {e}")
            raise
    
    def update_project(self, project_id: str, title: Optional[str] = None, notes: Optional[str] = None,
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
            # Build URL scheme parameters
            params = {"id": project_id}
            
            if title is not None:
                params["title"] = title
            if notes is not None:
                params["notes"] = notes
            if tags is not None:
                params["tags"] = ",".join(tags)
            if when is not None:
                params["when"] = when
            if deadline is not None:
                params["deadline"] = deadline
            if completed is not None:
                params["completed"] = "true" if completed else "false"
            if canceled is not None:
                params["canceled"] = "true" if canceled else "false"
            
            result = self.applescript.execute_url_scheme("update", params)
            
            if result.get("success"):
                logger.info(f"Successfully updated project: {project_id}")
                return {
                    "success": True,
                    "message": "Project updated successfully",
                    "project_id": project_id,
                    "updated_at": datetime.now().isoformat()
                }
            else:
                logger.error(f"Failed to update project: {result.get('error')}")
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
        
        except Exception as e:
            logger.error(f"Error updating project: {e}")
            raise
    
    def get_areas(self, include_items: bool = False) -> List[Dict[str, Any]]:
        """Get all areas from Things.
        
        Args:
            include_items: Include projects and tasks within areas
            
        Returns:
            List of area dictionaries
        """
        try:
            areas = self.applescript.get_areas()
            
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
    def get_inbox(self) -> List[Dict[str, Any]]:
        """Get todos from Inbox."""
        return self._get_list_todos("inbox")
    
    def get_today(self) -> List[Dict[str, Any]]:
        """Get todos due today."""
        return self._get_list_todos("today")
    
    def get_upcoming(self) -> List[Dict[str, Any]]:
        """Get upcoming todos."""
        return self._get_list_todos("upcoming")
    
    def get_anytime(self) -> List[Dict[str, Any]]:
        """Get todos from Anytime list."""
        return self._get_list_todos("anytime")
    
    def get_someday(self) -> List[Dict[str, Any]]:
        """Get todos from Someday list."""
        return self._get_list_todos("someday")
    
    def get_logbook(self, limit: int = 50, period: str = "7d") -> List[Dict[str, Any]]:
        """Get completed todos from Logbook.
        
        Args:
            limit: Maximum number of entries
            period: Time period to look back
            
        Returns:
            List of completed todo dictionaries
        """
        return self._get_list_todos("logbook", limit=limit)
    
    def get_trash(self) -> List[Dict[str, Any]]:
        """Get trashed todos."""
        return self._get_list_todos("trash")
    
    def get_tags(self, include_items: bool = False) -> List[Dict[str, Any]]:
        """Get all tags.
        
        Args:
            include_items: Include items tagged with each tag
            
        Returns:
            List of tag dictionaries
        """
        try:
            # This is a placeholder - would need AppleScript implementation
            logger.info("Retrieved tags (placeholder)")
            return []
        
        except Exception as e:
            logger.error(f"Error getting tags: {e}")
            raise
    
    def get_tagged_items(self, tag: str) -> List[Dict[str, Any]]:
        """Get items with a specific tag.
        
        Args:
            tag: Tag title to filter by
            
        Returns:
            List of tagged item dictionaries
        """
        try:
            # This is a placeholder - would need AppleScript implementation
            logger.info(f"Retrieved items with tag: {tag} (placeholder)")
            return []
        
        except Exception as e:
            logger.error(f"Error getting tagged items: {e}")
            raise
    
    def search_todos(self, query: str) -> List[Dict[str, Any]]:
        """Search todos by title or notes.
        
        Args:
            query: Search term
            
        Returns:
            List of matching todo dictionaries
        """
        try:
            # This is a placeholder - would need AppleScript implementation
            logger.info(f"Searched todos for: {query} (placeholder)")
            return []
        
        except Exception as e:
            logger.error(f"Error searching todos: {e}")
            raise
    
    def search_advanced(self, status: Optional[str] = None, type: Optional[str] = None,
                        tag: Optional[str] = None, area: Optional[str] = None,
                        start_date: Optional[str] = None, deadline: Optional[str] = None) -> List[Dict[str, Any]]:
        """Advanced todo search with multiple filters.
        
        Args:
            status: Filter by status
            type: Filter by type
            tag: Filter by tag
            area: Filter by area
            start_date: Filter by start date
            deadline: Filter by deadline
            
        Returns:
            List of matching todo dictionaries
        """
        try:
            # This is a placeholder - would need AppleScript implementation
            filters = {k: v for k, v in locals().items() if v is not None and k != 'self'}
            logger.info(f"Advanced search with filters: {filters} (placeholder)")
            return []
        
        except Exception as e:
            logger.error(f"Error in advanced search: {e}")
            raise
    
    def get_recent(self, period: str) -> List[Dict[str, Any]]:
        """Get recently created items.
        
        Args:
            period: Time period
            
        Returns:
            List of recent item dictionaries
        """
        try:
            # This is a placeholder - would need AppleScript implementation
            logger.info(f"Retrieved recent items for period: {period} (placeholder)")
            return []
        
        except Exception as e:
            logger.error(f"Error getting recent items: {e}")
            raise
    
    def show_item(self, id: str, query: Optional[str] = None, filter_tags: Optional[List[str]] = None) -> Dict[str, str]:
        """Show a specific item or list in Things.
        
        Args:
            id: Item ID or list name
            query: Optional query filter
            filter_tags: Optional tag filters
            
        Returns:
            Dict with show result
        """
        try:
            params = {"id": id}
            if query:
                params["query"] = query
            if filter_tags:
                params["filter"] = ",".join(filter_tags)
            
            result = self.applescript.execute_url_scheme("show", params)
            
            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Successfully showed item: {id}"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
        
        except Exception as e:
            logger.error(f"Error showing item: {e}")
            raise
    
    def search_items(self, query: str) -> Dict[str, str]:
        """Search for items in Things.
        
        Args:
            query: Search query
            
        Returns:
            Dict with search result
        """
        try:
            result = self.applescript.execute_url_scheme("search", {"query": query})
            
            if result.get("success"):
                return {
                    "success": True,
                    "message": f"Successfully searched for: {query}"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error")
                }
        
        except Exception as e:
            logger.error(f"Error searching items: {e}")
            raise
    
    def _get_list_todos(self, list_name: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get todos from a specific list.
        
        Args:
            list_name: Name of the list (inbox, today, etc.)
            limit: Optional limit on number of results
            
        Returns:
            List of todo dictionaries
        """
        try:
            # This is a placeholder - would need specific AppleScript for each list
            logger.info(f"Retrieved todos from {list_name} (placeholder)")
            return []
        
        except Exception as e:
            logger.error(f"Error getting {list_name} todos: {e}")
            raise
