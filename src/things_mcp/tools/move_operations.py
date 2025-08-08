"""
Move Operations Tools

Implements functionality for moving todos and projects between different lists,
projects, and areas in Things 3. Provides both single and bulk move operations
with comprehensive error handling and validation.
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime
import logging

from ..services.applescript_manager import AppleScriptManager
from ..services.validation_service import ValidationService
from ..models.response_models import OperationResult

logger = logging.getLogger(__name__)


class MoveOperationsTools:
    """Tools for moving todos and projects between containers."""
    
    def __init__(
        self, 
        applescript_manager: AppleScriptManager,
        validation_service: ValidationService
    ):
        self.applescript = applescript_manager
        self.validator = validation_service
    
    async def move_record(
        self, 
        todo_id: str, 
        destination: str,
        preserve_scheduling: bool = True
    ) -> Dict[str, Any]:
        """
        Move a todo to a different list, project, or area.
        
        Args:
            todo_id: ID of the todo to move
            destination: Destination list/project/area
                        Valid values: inbox, today, upcoming, anytime, someday,
                        project:[project-id], area:[area-id]
            preserve_scheduling: Whether to preserve existing scheduling when moving
            
        Returns:
            Dict with move operation result
        """
        try:
            # Validate inputs
            validation_result = await self._validate_move_inputs(todo_id, destination)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": "VALIDATION_ERROR",
                    "message": validation_result["message"],
                    "todo_id": todo_id,
                    "destination": destination
                }
            
            # Get current todo information before moving
            current_todo = await self._get_todo_info(todo_id)
            if not current_todo["success"]:
                return {
                    "success": False,
                    "error": "TODO_NOT_FOUND",
                    "message": f"Todo with ID '{todo_id}' not found",
                    "todo_id": todo_id,
                    "destination": destination
                }
            
            # Execute the move operation
            move_result = await self._execute_move(
                todo_id, 
                destination, 
                current_todo["todo"], 
                preserve_scheduling
            )
            
            if move_result["success"]:
                return {
                    "success": True,
                    "message": f"Todo '{current_todo['todo']['title']}' moved to {destination} successfully",
                    "todo_id": todo_id,
                    "destination": destination,
                    "original_location": current_todo["todo"].get("current_list"),
                    "moved_at": datetime.now().isoformat(),
                    "preserved_scheduling": preserve_scheduling
                }
            else:
                return {
                    "success": False,
                    "error": move_result.get("error", "MOVE_FAILED"),
                    "message": move_result.get("message", "Failed to move todo"),
                    "todo_id": todo_id,
                    "destination": destination
                }
        
        except Exception as e:
            logger.error(f"Error moving todo {todo_id} to {destination}: {e}")
            return {
                "success": False,
                "error": "UNEXPECTED_ERROR",
                "message": f"Unexpected error during move operation: {str(e)}",
                "todo_id": todo_id,
                "destination": destination
            }
    
    async def bulk_move(
        self,
        todo_ids: List[str],
        destination: str,
        preserve_scheduling: bool = True,
        max_concurrent: int = 5
    ) -> Dict[str, Any]:
        """
        Move multiple todos to the same destination.
        
        Args:
            todo_ids: List of todo IDs to move
            destination: Destination for all todos
            preserve_scheduling: Whether to preserve scheduling
            max_concurrent: Maximum concurrent move operations
            
        Returns:
            Dict with bulk move results
        """
        try:
            if not todo_ids:
                return {
                    "success": False,
                    "error": "NO_TODOS_SPECIFIED",
                    "message": "No todo IDs provided for bulk move",
                    "total_requested": 0
                }
            
            # Validate destination once for all moves
            dest_validation = await self._validate_destination(destination)
            if not dest_validation["valid"]:
                return {
                    "success": False,
                    "error": "INVALID_DESTINATION",
                    "message": dest_validation["message"],
                    "total_requested": len(todo_ids)
                }
            
            successful_moves = []
            failed_moves = []
            
            # Process todos in batches to avoid overwhelming the system
            import asyncio
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def move_single_todo(todo_id: str) -> Dict[str, Any]:
                async with semaphore:
                    return await self.move_record(todo_id, destination, preserve_scheduling)
            
            # Execute all moves concurrently
            tasks = [move_single_todo(todo_id) for todo_id in todo_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                todo_id = todo_ids[i]
                
                if isinstance(result, Exception):
                    failed_moves.append({
                        "id": todo_id,
                        "error": "EXCEPTION",
                        "message": str(result)
                    })
                elif result.get("success"):
                    successful_moves.append({
                        "id": todo_id,
                        "destination": destination,
                        "moved_at": result.get("moved_at")
                    })
                else:
                    failed_moves.append({
                        "id": todo_id,
                        "error": result.get("error", "UNKNOWN"),
                        "message": result.get("message", "Move operation failed")
                    })
            
            return {
                "success": len(failed_moves) == 0,
                "message": f"Bulk move completed: {len(successful_moves)} successful, {len(failed_moves)} failed",
                "destination": destination,
                "total_requested": len(todo_ids),
                "total_successful": len(successful_moves),
                "total_failed": len(failed_moves),
                "successful_moves": successful_moves,
                "failed_moves": failed_moves,
                "preserve_scheduling": preserve_scheduling,
                "completed_at": datetime.now().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error during bulk move operation: {e}")
            return {
                "success": False,
                "error": "BULK_MOVE_ERROR",
                "message": f"Bulk move operation failed: {str(e)}",
                "total_requested": len(todo_ids),
                "total_successful": 0,
                "total_failed": len(todo_ids)
            }
    
    async def move_to_project(
        self,
        todo_id: str,
        project_id: str,
        heading: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Move a todo to a specific project, optionally under a heading.
        
        Args:
            todo_id: ID of the todo to move
            project_id: ID of the target project
            heading: Optional heading within the project
            
        Returns:
            Dict with move result
        """
        destination = f"project:{project_id}"
        if heading:
            destination += f":{heading}"
        
        return await self.move_record(todo_id, destination)
    
    async def move_to_area(
        self,
        todo_id: str,
        area_id: str
    ) -> Dict[str, Any]:
        """
        Move a todo to a specific area.
        
        Args:
            todo_id: ID of the todo to move
            area_id: ID of the target area
            
        Returns:
            Dict with move result
        """
        destination = f"area:{area_id}"
        return await self.move_record(todo_id, destination)
    
    async def _validate_move_inputs(self, todo_id: str, destination: str) -> Dict[str, Any]:
        """Validate move operation inputs."""
        if not todo_id or not isinstance(todo_id, str):
            return {
                "valid": False,
                "message": "Todo ID must be a non-empty string"
            }
        
        if not destination or not isinstance(destination, str):
            return {
                "valid": False,
                "message": "Destination must be a non-empty string"
            }
        
        return await self._validate_destination(destination)
    
    async def _validate_destination(self, destination: str) -> Dict[str, Any]:
        """Validate destination string."""
        valid_lists = ["inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash"]
        
        # Check for simple list destinations
        if destination in valid_lists:
            return {"valid": True, "message": "Valid list destination"}
        
        # Check for project destinations
        if destination.startswith("project:"):
            project_part = destination[8:]  # Remove "project:" prefix
            if project_part:
                return {"valid": True, "message": "Valid project destination"}
            else:
                return {"valid": False, "message": "Project ID cannot be empty"}
        
        # Check for area destinations
        if destination.startswith("area:"):
            area_part = destination[5:]  # Remove "area:" prefix
            if area_part:
                return {"valid": True, "message": "Valid area destination"}
            else:
                return {"valid": False, "message": "Area ID cannot be empty"}
        
        return {
            "valid": False,
            "message": f"Invalid destination '{destination}'. Must be a list name, project:ID, or area:ID"
        }
    
    async def _get_todo_info(self, todo_id: str) -> Dict[str, Any]:
        """Get information about a todo before moving it."""
        try:
            script = f'''
            -- Helper function to efficiently determine todo location using native properties
            on getCurrentLocation(theTodo)
                tell application "Things3"
                    try
                        -- Use scheduled date and completion date to determine list location
                        set todoScheduledDate to scheduled date of theTodo
                        set todoCompletionDate to completion date of theTodo
                        set todoStatus to status of theTodo
                        
                        -- Check if completed (in logbook)
                        if todoStatus is completed then
                            return "logbook"
                        end if
                        
                        -- Check if in trash
                        if todoStatus is canceled then
                            return "trash"
                        end if
                        
                        -- For open todos, check scheduling properties
                        if todoScheduledDate is not missing value then
                            set currentDate to current date
                            set startOfToday to date (short date string of currentDate)
                            set startOfTomorrow to startOfToday + 1 * days
                            
                            -- Today: scheduled for today
                            if todoScheduledDate ≥ startOfToday and todoScheduledDate < startOfTomorrow then
                                return "today"
                            -- Upcoming: scheduled for future dates
                            else if todoScheduledDate ≥ startOfTomorrow then
                                return "upcoming"
                            -- Anytime: scheduled for past dates (overdue but not in Today)
                            else
                                return "anytime"
                            end if
                        else
                            -- No scheduled date - check if it has specific list placement
                            -- Use a more efficient method: check the todo's container properties
                            try
                                -- Try to access the todo through different lists to find where it belongs
                                set foundInSomeday to false
                                set foundInAnytime to false
                                set foundInInbox to false
                                
                                -- Check someday list efficiently
                                try
                                    set somedayList to list "someday"
                                    tell somedayList to set somedayTodos to to dos whose id is (id of theTodo)
                                    if (count of somedayTodos) > 0 then set foundInSomeday to true
                                end try
                                
                                if foundInSomeday then return "someday"
                                
                                -- Check anytime list efficiently  
                                try
                                    set anytimeList to list "anytime"
                                    tell anytimeList to set anytimeTodos to to dos whose id is (id of theTodo)
                                    if (count of anytimeTodos) > 0 then set foundInAnytime to true
                                end try
                                
                                if foundInAnytime then return "anytime"
                                
                                -- Check inbox as fallback
                                try
                                    set inboxList to list "inbox"
                                    tell inboxList to set inboxTodos to to dos whose id is (id of theTodo)
                                    if (count of inboxTodos) > 0 then set foundInInbox to true
                                end try
                                
                                if foundInInbox then return "inbox"
                                
                                -- Default fallback
                                return "inbox"
                                
                            on error
                                return "unknown"
                            end try
                        end if
                    on error
                        return "unknown"
                    end try
                end tell
            end getCurrentLocation
            
            tell application "Things3"
                try
                    set theTodo to to do id "{todo_id}"
                    set todoInfo to {{}}
                    set todoInfo to todoInfo & {{id:id of theTodo}}
                    set todoInfo to todoInfo & {{name:name of theTodo}}
                    set todoInfo to todoInfo & {{notes:notes of theTodo}}
                    set todoInfo to todoInfo & {{status:status of theTodo}}
                    
                    -- Try to get current list information
                    try
                        set currentList to ""
                        if (project of theTodo) is not missing value then
                            set currentList to "project:" & (id of project of theTodo)
                        else if (area of theTodo) is not missing value then
                            set currentList to "area:" & (id of area of theTodo)
                        else
                            -- Use native AppleScript properties to efficiently determine location
                            set currentList to my getCurrentLocation(theTodo)
                        end if
                        set todoInfo to todoInfo & {{current_list:currentList}}
                    on error
                        set todoInfo to todoInfo & {{current_list:"unknown"}}
                    end try
                    
                    return todoInfo
                on error errMsg
                    return "ERROR:" & errMsg
                end try
            end tell
            '''
            
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get("success"):
                output = result.get("output", "")
                if output.startswith("ERROR:"):
                    return {
                        "success": False,
                        "error": output[6:]  # Remove "ERROR:" prefix
                    }
                
                # Parse the todo information
                todo_info = self.applescript._parse_applescript_record(output)
                return {
                    "success": True,
                    "todo": {
                        "id": todo_info.get("id"),
                        "title": todo_info.get("name", ""),
                        "notes": todo_info.get("notes", ""),
                        "status": todo_info.get("status", "open"),
                        "current_list": todo_info.get("current_list", "unknown")
                    }
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Failed to get todo information")
                }
        
        except Exception as e:
            logger.error(f"Error getting todo info for {todo_id}: {e}")
            return {
                "success": False,
                "error": f"Exception getting todo info: {str(e)}"
            }
    
    async def _execute_move(
        self,
        todo_id: str,
        destination: str,
        current_todo: Dict[str, Any],
        preserve_scheduling: bool
    ) -> Dict[str, Any]:
        """Execute the actual move operation using AppleScript."""
        try:
            # Build the move script based on destination type
            if destination in ["inbox", "today", "upcoming", "anytime", "someday"]:
                # Moving to a built-in list
                script = await self._build_list_move_script(todo_id, destination, preserve_scheduling)
            elif destination.startswith("project:"):
                # Moving to a project
                project_id = destination[8:]  # Remove "project:" prefix
                script = await self._build_project_move_script(todo_id, project_id, preserve_scheduling)
            elif destination.startswith("area:"):
                # Moving to an area
                area_id = destination[5:]  # Remove "area:" prefix
                script = await self._build_area_move_script(todo_id, area_id, preserve_scheduling)
            else:
                return {
                    "success": False,
                    "error": "INVALID_DESTINATION",
                    "message": f"Unknown destination type: {destination}"
                }
            
            # Execute the move script
            result = await self.applescript.execute_applescript(script, cache_key=None)
            
            if result.get("success"):
                output = result.get("output", "")
                if "ERROR:" in output:
                    return {
                        "success": False,
                        "error": "APPLESCRIPT_ERROR",
                        "message": output
                    }
                elif "MOVED" in output or "moved" in output.lower():
                    return {"success": True}
                else:
                    return {
                        "success": False,
                        "error": "UNEXPECTED_OUTPUT",
                        "message": f"Unexpected script output: {output}"
                    }
            else:
                return {
                    "success": False,
                    "error": "SCRIPT_EXECUTION_FAILED",
                    "message": result.get("error", "AppleScript execution failed")
                }
        
        except Exception as e:
            logger.error(f"Error executing move for {todo_id}: {e}")
            return {
                "success": False,
                "error": "EXECUTION_EXCEPTION",
                "message": str(e)
            }
    
    async def _build_list_move_script(
        self,
        todo_id: str,
        list_name: str,
        preserve_scheduling: bool
    ) -> str:
        """Build AppleScript for moving to a built-in list."""
        scheduling_part = ""
        if not preserve_scheduling:
            # Clear scheduling when moving to different lists
            if list_name == "today":
                scheduling_part = "\n        set scheduled date of theTodo to current date"
            elif list_name == "upcoming":
                scheduling_part = "\n        set scheduled date of theTodo to (current date + 1 * days)"
            elif list_name in ["anytime", "someday"]:
                scheduling_part = f"\n        set scheduled date of theTodo to missing value"
        
        script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"
                
                -- Move to the specified list
                if "{list_name}" is "inbox" then
                    move theTodo to list "inbox"
                else if "{list_name}" is "today" then
                    move theTodo to list "today"
                else if "{list_name}" is "upcoming" then
                    move theTodo to list "upcoming"
                else if "{list_name}" is "anytime" then
                    move theTodo to list "anytime"
                else if "{list_name}" is "someday" then
                    move theTodo to list "someday"
                end if
                {scheduling_part}
                
                return "MOVED to {list_name}"
            on error errMsg
                return "ERROR: " & errMsg
            end try
        end tell
        '''
        
        return script
    
    async def _build_project_move_script(
        self,
        todo_id: str,
        project_id: str,
        preserve_scheduling: bool
    ) -> str:
        """Build AppleScript for moving to a project."""
        script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"
                set targetProject to project id "{project_id}"
                
                -- Move todo to the project
                move theTodo to targetProject
                
                return "MOVED to project {project_id}"
            on error errMsg
                return "ERROR: " & errMsg
            end try
        end tell
        '''
        
        return script
    
    async def _build_area_move_script(
        self,
        todo_id: str,
        area_id: str,
        preserve_scheduling: bool
    ) -> str:
        """Build AppleScript for moving to an area."""
        script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"
                set targetArea to area id "{area_id}"
                
                -- Move todo to the area
                move theTodo to targetArea
                
                return "MOVED to area {area_id}"
            on error errMsg
                return "ERROR: " & errMsg
            end try
        end tell
        '''
        
        return script