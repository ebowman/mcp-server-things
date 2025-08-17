"""
Validation Service for Things 3 MCP Server

Provides validation functionality for todo IDs, project IDs, area IDs,
and other Things 3 entities to ensure data integrity and proper error handling.
"""

import re
from typing import Dict, Any, Optional
import logging

from .applescript_manager import AppleScriptManager

logger = logging.getLogger(__name__)


class ValidationService:
    """Service for validating Things 3 entities and operations."""
    
    def __init__(self, applescript_manager: AppleScriptManager):
        """Initialize validation service with AppleScript manager.
        
        Args:
            applescript_manager: AppleScript manager instance for validation queries
        """
        self.applescript = applescript_manager
    
    async def validate_todo_id(self, todo_id: str) -> Dict[str, Any]:
        """Validate that a todo ID exists and is accessible.
        
        Args:
            todo_id: The todo ID to validate
            
        Returns:
            Dict with validation result and details
        """
        if not todo_id or not isinstance(todo_id, str):
            return {
                "valid": False,
                "error": "INVALID_ID_FORMAT",
                "message": "Todo ID must be a non-empty string"
            }
        
        try:
            # Try to access the todo to verify it exists
            script = f'''
            tell application "Things3"
                try
                    set theTodo to to do id "{self._escape_id(todo_id)}"
                    return "EXISTS"
                on error
                    return "NOT_FOUND"
                end try
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get("success") and result.get("output") == "EXISTS":
                return {
                    "valid": True,
                    "message": "Todo ID is valid"
                }
            else:
                return {
                    "valid": False,
                    "error": "TODO_NOT_FOUND",
                    "message": f"Todo with ID '{todo_id}' does not exist"
                }
        
        except Exception as e:
            logger.error(f"Error validating todo ID {todo_id}: {e}")
            return {
                "valid": False,
                "error": "VALIDATION_EXCEPTION",
                "message": f"Error during validation: {str(e)}"
            }
    
    async def validate_project_id(self, project_id: str) -> Dict[str, Any]:
        """Validate that a project ID exists and is accessible.
        
        Args:
            project_id: The project ID to validate
            
        Returns:
            Dict with validation result and details
        """
        if not project_id or not isinstance(project_id, str):
            return {
                "valid": False,
                "error": "INVALID_ID_FORMAT",
                "message": "Project ID must be a non-empty string"
            }
        
        try:
            script = f'''
            tell application "Things3"
                try
                    set theProject to project id "{self._escape_id(project_id)}"
                    return "EXISTS"
                on error
                    return "NOT_FOUND"
                end try
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get("success") and result.get("output") == "EXISTS":
                return {
                    "valid": True,
                    "message": "Project ID is valid"
                }
            else:
                return {
                    "valid": False,
                    "error": "PROJECT_NOT_FOUND",
                    "message": f"Project with ID '{project_id}' does not exist"
                }
        
        except Exception as e:
            logger.error(f"Error validating project ID {project_id}: {e}")
            return {
                "valid": False,
                "error": "VALIDATION_EXCEPTION",
                "message": f"Error during validation: {str(e)}"
            }
    
    async def validate_area_id(self, area_id: str) -> Dict[str, Any]:
        """Validate that an area ID exists and is accessible.
        
        Args:
            area_id: The area ID to validate
            
        Returns:
            Dict with validation result and details
        """
        if not area_id or not isinstance(area_id, str):
            return {
                "valid": False,
                "error": "INVALID_ID_FORMAT",
                "message": "Area ID must be a non-empty string"
            }
        
        try:
            script = f'''
            tell application "Things3"
                try
                    set theArea to area id "{self._escape_id(area_id)}"
                    return "EXISTS"
                on error
                    return "NOT_FOUND"
                end try
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get("success") and result.get("output") == "EXISTS":
                return {
                    "valid": True,
                    "message": "Area ID is valid"
                }
            else:
                return {
                    "valid": False,
                    "error": "AREA_NOT_FOUND",
                    "message": f"Area with ID '{area_id}' does not exist"
                }
        
        except Exception as e:
            logger.error(f"Error validating area ID {area_id}: {e}")
            return {
                "valid": False,
                "error": "VALIDATION_EXCEPTION",
                "message": f"Error during validation: {str(e)}"
            }
    
    async def validate_list_name(self, list_name: str) -> Dict[str, Any]:
        """Validate that a list name is a valid Things 3 built-in list.
        
        Args:
            list_name: The list name to validate
            
        Returns:
            Dict with validation result and details
        """
        valid_lists = ["inbox", "today", "anytime", "someday", "upcoming", "logbook", "trash"]
        
        if not list_name or not isinstance(list_name, str):
            return {
                "valid": False,
                "error": "INVALID_LIST_NAME",
                "message": "List name must be a non-empty string"
            }
        
        normalized_name = list_name.lower().strip()
        
        if normalized_name in valid_lists:
            return {
                "valid": True,
                "message": f"List name '{list_name}' is valid",
                "normalized_name": normalized_name
            }
        else:
            return {
                "valid": False,
                "error": "INVALID_LIST_NAME",
                "message": f"Invalid list name '{list_name}'. Valid options: {', '.join(valid_lists)}"
            }
    
    def validate_destination_format(self, destination: str) -> Dict[str, Any]:
        """Validate the format of a destination string.
        
        Args:
            destination: Destination string (list name, project:ID, or area:ID)
            
        Returns:
            Dict with validation result and parsed components
        """
        if not destination or not isinstance(destination, str):
            return {
                "valid": False,
                "error": "INVALID_DESTINATION_FORMAT",
                "message": "Destination must be a non-empty string"
            }
        
        destination = destination.strip()
        
        # Check for project format: project:ID
        if destination.startswith("project:"):
            project_id = destination[8:].strip()  # Remove "project:" prefix
            if project_id:
                return {
                    "valid": True,
                    "type": "project",
                    "id": project_id,
                    "message": "Valid project destination format"
                }
            else:
                return {
                    "valid": False,
                    "error": "EMPTY_PROJECT_ID",
                    "message": "Project ID cannot be empty in 'project:ID' format"
                }
        
        # Check for area format: area:ID
        elif destination.startswith("area:"):
            area_id = destination[5:].strip()  # Remove "area:" prefix
            if area_id:
                return {
                    "valid": True,
                    "type": "area", 
                    "id": area_id,
                    "message": "Valid area destination format"
                }
            else:
                return {
                    "valid": False,
                    "error": "EMPTY_AREA_ID",
                    "message": "Area ID cannot be empty in 'area:ID' format"
                }
        
        # Check for list name (synchronous validation using the same logic)
        else:
            valid_lists = ["inbox", "today", "anytime", "someday", "upcoming", "logbook", "trash"]
            normalized_name = destination.lower().strip()
            
            if normalized_name in valid_lists:
                return {
                    "valid": True,
                    "type": "list",
                    "name": normalized_name,
                    "message": "Valid list destination format"
                }
            else:
                return {
                    "valid": False,
                    "error": "INVALID_DESTINATION",
                    "message": f"Invalid destination '{destination}'. Use list name, 'project:ID', or 'area:ID' format"
                }
    
    def _escape_id(self, id_string: str) -> str:
        """Escape an ID string for safe use in AppleScript.
        
        Args:
            id_string: The ID string to escape
            
        Returns:
            Escaped ID string
        """
        if not id_string:
            return ""
        
        # Escape quotes and backslashes for AppleScript safety
        return id_string.replace('\\', '\\\\').replace('"', '\\"')
    
    def validate_bulk_operation_limits(self, item_count: int, operation_type: str = "move") -> Dict[str, Any]:
        """Validate bulk operation limits to prevent system overload.
        
        Args:
            item_count: Number of items in bulk operation
            operation_type: Type of operation (for different limits)
            
        Returns:
            Dict with validation result and recommended limits
        """
        # Set reasonable limits for different operations
        limits = {
            "move": 100,
            "update": 50,
            "delete": 25,
            "create": 50
        }
        
        max_limit = limits.get(operation_type, 50)
        
        if item_count <= 0:
            return {
                "valid": False,
                "error": "INVALID_COUNT",
                "message": "Item count must be greater than 0"
            }
        
        if item_count > max_limit:
            return {
                "valid": False,
                "error": "EXCEEDS_LIMIT",
                "message": f"Bulk {operation_type} operation limited to {max_limit} items. Requested: {item_count}",
                "max_allowed": max_limit,
                "recommended_batch_size": max_limit // 2
            }
        
        return {
            "valid": True,
            "message": f"Bulk operation count {item_count} is within limits",
            "max_allowed": max_limit
        }