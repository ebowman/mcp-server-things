"""
Move Operations Tools

Implements functionality for moving todos and projects between different lists,
projects, and areas in Things 3. Provides both single and bulk move operations
with comprehensive error handling and validation.
"""

from typing import Optional, List, Dict, Any, Union
from datetime import datetime, date
import asyncio
import logging
import time

from .services.applescript_manager import AppleScriptManager
from .services.validation_service import ValidationService
from .things_import import LazyThingsProxy

logger = logging.getLogger(__name__)

# Lazily-importing proxy for things.py -- avoids the module-level,
# unbounded glob.iglob() scan that a plain `import things` would perform
# at server boot time. See things_import.LazyThingsProxy docstring; this
# also preserves the existing test-patching convention used elsewhere
# (things_mcp.tools_helpers.write_operations.things, etc.) - here the
# patch target is things_mcp.move_operations.things.
things = LazyThingsProxy()

# hq-wsa.6: bounded retry for the pre-move things.py existence/location
# pre-check, tolerating the documented ~1-2s async lag between a
# URL-scheme write (things:///add, things:///update - used for headings,
# checklists, evening scheduling) and things.py's SQLite-backed read
# (CLAUDE.md point 6). Two 250ms re-checks (500ms total) is the same
# bounded-retry order of magnitude already used elsewhere for this lag
# (see scheduling/todo_operations.py's
# _URL_SCHEME_LOOKUP_POLL_INTERVAL_SECS), so a todo created moments ago via
# the URL scheme and immediately moved doesn't spuriously read back as
# not-found any more often than before this change.
_TODO_INFO_LOOKUP_RETRIES = 2
_TODO_INFO_LOOKUP_RETRY_INTERVAL_SECS = 0.25


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
        destination: str
    ) -> Dict[str, Any]:
        """
        Move a todo to a different list, project, or area.

        The move operation handles scheduling automatically based on the destination:
        - Moving to 'today' sets activation date to today
        - Moving to 'anytime'/'someday' clears activation date
        - Moving to 'inbox' clears activation date

        Args:
            todo_id: ID of the todo to move
            destination: Destination list/project/area
                        Valid values: inbox, today, anytime, someday, logbook, trash,
                        project:[project-id], area:[area-id]

        Returns:
            Dict with move operation result
        """
        try:
            # Validate inputs
            validation_result = await self._validate_move_inputs(todo_id, destination)
            if not validation_result["valid"]:
                error_response = {
                    "success": False,
                    "error": "VALIDATION_ERROR",
                    "message": validation_result["message"],
                    "todo_id": todo_id,
                    "destination": destination
                }
                if "field" in validation_result:
                    error_response["field"] = validation_result["field"]
                return error_response
            
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
                current_todo["todo"]
            )

            if move_result["success"]:
                response = {
                    "success": True,
                    "message": f"Todo '{current_todo['todo']['title']}' moved to {destination} successfully",
                    "todo_id": todo_id,
                    "destination": destination,
                    "moved_at": datetime.now().isoformat()
                }
                # original_location is omitted entirely (not present as
                # null) when the pre-move things.py lookup itself raised
                # (DB unreadable) - see _get_todo_info's DB-raise fallback,
                # item 3 of hq-wsa.6.
                original_location = current_todo["todo"].get("current_list")
                if original_location is not None:
                    response["original_location"] = original_location
                return response
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
        max_concurrent: int = 5
    ) -> Dict[str, Any]:
        """
        Move multiple todos to the same destination.

        Args:
            todo_ids: List of todo IDs to move
            destination: Destination for all todos
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
                    return await self.move_record(todo_id, destination)
            
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
        if not todo_id or not isinstance(todo_id, str) or not todo_id.strip():
            return {
                "valid": False,
                "message": "Todo ID must be a non-empty string",
                "field": "todo_id"
            }
        
        if not destination or not isinstance(destination, str):
            return {
                "valid": False,
                "message": "Destination must be a non-empty string"
            }
        
        return await self._validate_destination(destination)
    
    async def _validate_destination(self, destination: str) -> Dict[str, Any]:
        """Validate destination string."""
        valid_lists = ["inbox", "today", "anytime", "someday", "logbook", "trash"]

        # 'upcoming' is intentionally rejected, not a valid destination.
        # Things has no direct 'Upcoming' move target - an item is Upcoming
        # by having a future start date, and Things' AppleScript move verb
        # itself rejects `move ... to list "upcoming"` ('Cannot move
        # to-do'). Rather than guessing an arbitrary future date, steer
        # callers to update_todo(when=<date>) instead (bead hq-cag).
        if destination == "upcoming":
            return {
                "valid": False,
                "message": (
                    "'upcoming' is not a valid move destination - Things has no "
                    "direct Upcoming move target (an item is Upcoming by having "
                    "a future start date). Use update_todo(id=..., "
                    "when='<YYYY-MM-DD>') (or when='tomorrow') to schedule the "
                    "to-do for a future date instead."
                ),
            }

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
        """Get information about a todo before moving it, via things.py.

        Replaces the historic AppleScript round-trip (a stub
        ``getCurrentLocation`` helper that always returned "inbox", parsed
        via a positionally-fragile ``output.split(", ")``) with a direct
        ``things.get(todo_id)`` read - see hq-wsa.6. This fixes two bugs:
        every ``original_location`` reporting the hardcoded
        'current_list:inbox' regardless of true origin, and the returned
        title carrying a stray 'name:' label from the parsed record.

        The actual work (including the bounded retry's blocking sleep) runs
        in a worker thread via ``loop.run_in_executor`` rather than inline
        on the event loop. move_record()/_get_todo_info() is called
        concurrently (via asyncio.gather, fanned out by bulk_move) for
        multi-todo moves that run alongside AppleScriptExecutor's own
        locked, awaited subprocess calls on the SAME event loop - a
        synchronous things.get()/time.sleep() called directly here would
        block that loop for the duration, perturbing the interleaving of
        those concurrent AppleScript calls (observed live: this previously
        surfaced as AppleScriptExecutor._applescript_lock's underlying
        asyncio.Lock picking up a second genuine waiter it otherwise
        wouldn't have, then tripping "bound to a different event loop" on
        a later, separate asyncio.run() call in the same process - a
        real, event-loop-timing-sensitive interaction, not a pre-existing
        defect independent of this change). Executor scheduling avoids
        that interaction entirely, matching the existing
        loop.run_in_executor convention used throughout
        tools_helpers/read_operations.py for things.py reads on the async
        path.

        Returns:
            On success: {"success": True, "todo": {"id", "title", "notes",
            "status", "current_list"}} - "current_list" is the derived
            pre-move origin string (see _derive_original_location), or
            omitted (None) when things.get() itself raised and the id
            could not be pre-verified (DB-unreadable fallback, item 3).
            On the id not resolving to a todo at all (existence check
            failed after the bounded race-tolerance retry): {"success":
            False, "error": ...} - the TODO_NOT_FOUND contract in
            move_record() is unchanged.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_todo_info_sync, todo_id)

    def _get_todo_info_sync(self, todo_id: str) -> Dict[str, Any]:
        """Synchronous implementation of _get_todo_info - see that method's
        docstring for why this runs off the event loop via run_in_executor."""
        try:
            record = None
            lookup_raised = False
            attempts = _TODO_INFO_LOOKUP_RETRIES + 1
            for attempt in range(attempts):
                try:
                    record = things.get(todo_id)
                except Exception as e:
                    # things.get() itself raised (DB unreadable / Full Disk
                    # Access missing) - fall back to proceeding with the
                    # move rather than refusing it, same convention as
                    # add_todo's list_id resolution fallback. Not
                    # retryable (a raise here is an environment problem,
                    # not a transient race), so stop immediately.
                    logger.warning(
                        f"things.py lookup failed for todo {todo_id} "
                        f"(falling back to proceeding with the move, "
                        f"original_location omitted): {e}"
                    )
                    lookup_raised = True
                    break

                if record is not None:
                    break

                # things.get() resolved cleanly but found nothing. This is
                # ambiguous between "id genuinely unknown" and "todo was
                # just created via the async Things URL scheme and hasn't
                # landed in the SQLite DB yet" (~1-2s documented lag,
                # CLAUDE.md point 6) - bounded retry before declaring
                # TODO_NOT_FOUND, so the existing hq-c7a concurrency-race
                # tolerance is not worsened by this things.py-based
                # pre-check replacing the old AppleScript one.
                if attempt < attempts - 1:
                    time.sleep(_TODO_INFO_LOOKUP_RETRY_INTERVAL_SECS)

            if lookup_raised:
                return {
                    "success": True,
                    "todo": {
                        "id": todo_id,
                        "title": todo_id,
                        "notes": "",
                        "status": "open",
                        "current_list": None,
                    },
                }

            if record is None:
                return {
                    "success": False,
                    "error": f"Todo with ID '{todo_id}' not found",
                }

            if record.get("type") != "to-do":
                # Mirrors the existing "not a to-do" guard used elsewhere
                # (update_todo's primary-id pre-check) - a project/area/
                # heading id resolving here would otherwise be silently
                # treated as a todo by the move logic downstream.
                return {
                    "success": False,
                    "error": (
                        f"Todo with ID '{todo_id}' not found "
                        f"(resolved to a {record.get('type')}, not a to-do)"
                    ),
                }

            original_location = self._derive_original_location(record)

            return {
                "success": True,
                "todo": {
                    "id": record.get("uuid", todo_id),
                    "title": record.get("title", ""),
                    "notes": record.get("notes", ""),
                    "status": record.get("status", "open"),
                    "current_list": original_location,
                },
            }

        except Exception as e:
            logger.error(f"Error getting todo info for {todo_id}: {e}")
            return {
                "success": False,
                "error": f"Exception getting todo info: {str(e)}"
            }

    def _derive_original_location(self, record: Dict[str, Any]) -> str:
        """Derive the true pre-move origin of a todo from its things.py record.

        Rules (in priority order), matching hq-wsa.6:
        - Filed in a project directly: 'project:<project_uuid>'.
        - Filed under a heading: resolve the heading's own record (things.py
          denormalizes 'project' onto the heading row, not onto the
          heading-child todo row - see read_operations._fill_project_from_heading
          for the identical pattern used on the read side) and report
          'project:<project_uuid>' the same as a direct project todo. If the
          heading record itself can't be resolved (unexpected/edge case),
          falls through to the start-based rules below.
        - start == 'Inbox': 'inbox'.
        - start == 'Someday': 'someday'.
        - start == 'Anytime' with a start_date on or before today: 'today'
          (matches Things' own Today-list membership rule - an Anytime todo
          with a past-or-present start date shows in Today, not just one
          dated exactly today).
        - start == 'Anytime' with a start_date in the future: the literal
          ISO date string itself (e.g. '2026-09-01') rather than a generic
          'upcoming' token - this is the most precise, unambiguous
          representation of "this todo's true prior schedule was a future
          date", and avoids inventing a destination-style token that
          move_record's own destination validation would reject as invalid
          input if ever round-tripped.
        - start == 'Anytime' with no start_date: 'anytime'.
        - Anything else (unexpected/unknown start value): 'anytime' as a
          conservative fallback.

        Area-filed todos: things.py to-do rows never carry an 'area' key
        directly (only project rows do - CLAUDE.md, Tag Management section),
        so a todo filed directly in an area with no project/heading falls
        through to the start-based rules above (typically 'anytime' or
        'someday') rather than reporting 'area:<id>' - the area itself is
        not derivable from the todo row alone.
        """
        project_id = record.get("project")
        if project_id:
            return f"project:{project_id}"

        heading_id = record.get("heading")
        if heading_id:
            try:
                heading_record = things.get(heading_id)
            except Exception as e:
                logger.warning(
                    f"things.py lookup failed resolving heading {heading_id} "
                    f"for original_location (falling back to start-based "
                    f"derivation): {e}"
                )
                heading_record = None
            if heading_record and heading_record.get("project"):
                return f"project:{heading_record['project']}"

        start = record.get("start")
        if start == "Inbox":
            return "inbox"
        if start == "Someday":
            return "someday"
        if start == "Anytime":
            start_date = record.get("start_date")
            if start_date:
                try:
                    parsed_date = date.fromisoformat(str(start_date))
                    if parsed_date <= date.today():
                        return "today"
                    return start_date
                except (TypeError, ValueError):
                    return "anytime"
            return "anytime"

        return "anytime"
    
    async def _execute_move(
        self,
        todo_id: str,
        destination: str,
        current_todo: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the actual move operation using AppleScript."""
        try:
            # Build the move script based on destination type
            # ('upcoming' is rejected at _validate_destination and never
            # reaches here - see bead hq-cag)
            if destination in ["inbox", "today", "anytime", "someday", "trash"]:
                # Moving to a built-in list (including Trash - same `move ... to
                # list` verb Things exposes for Trash as for the other lists)
                script = await self._build_list_move_script(todo_id, destination)
            elif destination == "logbook":
                # Things has no `move ... to list "logbook"` target - the only
                # documented way an item reaches the Logbook is completion.
                script = await self._build_complete_move_script(todo_id)
            elif destination.startswith("project:"):
                # Moving to a project
                project_id = destination[8:]  # Remove "project:" prefix
                script = await self._build_project_move_script(todo_id, project_id)
            elif destination.startswith("area:"):
                # Moving to an area
                area_id = destination[5:]  # Remove "area:" prefix
                script = await self._build_area_move_script(todo_id, area_id)
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
        list_name: str
    ) -> str:
        """Build AppleScript for moving to a built-in list.

        The move command handles scheduling automatically:
        - Moving to 'today' sets activation date to today
        - Moving to 'anytime'/'someday' clears activation date
        - Moving to 'inbox' clears activation date
        """

        lines = [
            "tell application \"Things3\"",
            "    try",
            f"        set theTodo to to do id \"{todo_id}\"",
            f"        move theTodo to list \"{list_name}\"",
            f"        return \"MOVED to {list_name}\"",
            "    on error errMsg",
            "        return \"ERROR: \" & errMsg",
            "    end try",
            "end tell"
        ]

        return "\n".join(lines)

    async def _build_complete_move_script(
        self,
        todo_id: str
    ) -> str:
        """Build AppleScript for moving a todo to the Logbook.

        Things has no `move ... to list "logbook"` target - the only
        documented way an item reaches the Logbook is completion (Things
        moves completed to-dos there automatically). This sets the to-do's
        status to completed, which is what actually produces Logbook
        membership; it is not a true "move" but is exposed as the
        'logbook' destination for symmetry with the other built-in lists.
        """

        lines = [
            "tell application \"Things3\"",
            "    try",
            f"        set theTodo to to do id \"{todo_id}\"",
            "        set status of theTodo to completed",
            "        return \"MOVED to logbook\"",
            "    on error errMsg",
            "        return \"ERROR: \" & errMsg",
            "    end try",
            "end tell"
        ]

        return "\n".join(lines)
    
    async def _build_project_move_script(
        self,
        todo_id: str,
        project_id: str
    ) -> str:
        """Build AppleScript for moving to a project."""
        script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"
                set targetProject to project id "{project_id}"
                
                -- Set the project property instead of using move command
                -- The move command doesn't work for projects in Things 3
                set project of theTodo to targetProject
                
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
        area_id: str
    ) -> str:
        """Build AppleScript for moving to an area."""
        script = f'''
        tell application "Things3"
            try
                set theTodo to to do id "{todo_id}"
                set targetArea to area id "{area_id}"
                
                -- Set the area property instead of using move command
                -- The move command doesn't work for areas in Things 3
                set area of theTodo to targetArea
                
                return "MOVED to area {area_id}"
            on error errMsg
                return "ERROR: " & errMsg
            end try
        end tell
        '''
        
        return script