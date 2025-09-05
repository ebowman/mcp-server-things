"""Simple FastMCP 2.0 server implementation for Things 3 integration."""

import asyncio
import atexit
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Optional dotenv support
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, continue without it
    pass

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .services.applescript_manager import AppleScriptManager
from .tools import ThingsTools
from .operation_queue import shutdown_operation_queue, get_operation_queue
from .config import ThingsMCPConfig, load_config_from_env
from .context_manager import ContextAwareResponseManager, ResponseMode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ThingsMCPServer:
    """Simple MCP server for Things 3 integration."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the Things MCP server.
        
        Args:
            config_path: Optional path to configuration file
        """
        self.mcp = FastMCP("things-mcp")
        
        # Load configuration
        if config_path and Path(config_path).exists():
            try:
                self.config = ThingsMCPConfig.from_file(Path(config_path))
                logger.info(f"Loaded configuration from {config_path}")
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}. Using environment/defaults.")
                self.config = load_config_from_env()
        else:
            self.config = load_config_from_env()
        
        self.applescript_manager = AppleScriptManager()
        self.tools = ThingsTools(self.applescript_manager, self.config)
        self.context_manager = ContextAwareResponseManager()
        self._register_tools()
        self._register_shutdown_handlers()
        logger.info("Things MCP Server initialized with context-aware response management and tag validation support")

    def _register_shutdown_handlers(self):
        """Register shutdown handlers for graceful cleanup."""
        def shutdown_handler():
            """Handle server shutdown."""
            try:
                import sys
                # Skip shutdown during pytest to prevent stream conflicts
                if hasattr(sys, '_called_from_test') or 'pytest' in sys.modules:
                    return
                    
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're in an async context, schedule the shutdown
                    loop.create_task(shutdown_operation_queue())
                else:
                    # If not, run it directly
                    loop.run_until_complete(shutdown_operation_queue())
            except Exception as e:
                # Use safe logging during shutdown
                try:
                    logger.error(f"Error during shutdown: {e}")
                except (ValueError, OSError):
                    # Streams already closed, ignore
                    pass
        
        # Register cleanup for normal exit
        atexit.register(shutdown_handler)
        
        # Register signal handlers for graceful shutdown
        if sys.platform != 'win32':
            signal.signal(signal.SIGTERM, lambda s, f: shutdown_handler())
            signal.signal(signal.SIGINT, lambda s, f: shutdown_handler())
    
    def _register_tools(self) -> None:
        """Register all MCP tools with the server."""
        
        # Todo management tools
        @self.mcp.tool()
        async def get_todos(
            project_uuid: Optional[str] = None,
            include_items: Optional[bool] = None,
            mode: Optional[str] = None,
            limit: Any = None
        ) -> Dict[str, Any]:
            """🔍 CONTEXT-OPTIMIZED todo retrieval with INTELLIGENT response management.

            🎯 SMART FEATURES:
            - Auto-selects optimal response size to prevent context exhaustion  
            - 5 progressive disclosure modes (auto/summary/minimal/standard/detailed/raw)
            - Relevance-based ranking prioritizes today's and overdue items
            - Built-in pagination for large datasets

            📊 PERFORMANCE OPTIMIZED:
            - Handles 1000+ items efficiently with smart defaults
            - Dynamic field filtering reduces response size by 60-80%
            - Estimated response size tracking prevents context overflow

            🔄 WORKFLOW EXAMPLES:
            1. Daily Review: mode='standard', limit=20
            2. Project Analysis: mode='summary' → mode='detailed' for specifics  
            3. Bulk Operations: mode='minimal', limit=100

            ⚡ AI ASSISTANT GUIDANCE:
            - START: Use mode='auto' for unknown datasets
            - LARGE DATA: Use mode='summary' first, then drill down
            - BULK OPS: Use mode='minimal' to get IDs and essential fields
            - DETAILED VIEW: Only request when you need full field data

            CONTEXT BUDGET: ~1KB per item (standard), ~50 bytes per item (summary)
            """
            try:
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return {
                        "success": False,
                        "error": "Invalid mode",
                        "message": f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}"
                    }
                
                # Convert and validate limit parameter
                actual_limit = None
                if limit is not None:
                    try:
                        # Handle various input types
                        if isinstance(limit, str):
                            actual_limit = int(limit)
                        elif isinstance(limit, (int, float)):
                            actual_limit = int(limit)
                        else:
                            actual_limit = int(str(limit))
                        
                        # Validate range
                        if actual_limit < 1 or actual_limit > 500:
                            return {
                                "success": False,
                                "error": "Invalid limit value",
                                "message": f"Limit must be between 1 and 500, got {actual_limit}"
                            }
                    except (ValueError, TypeError) as e:
                        return {
                            "success": False,
                            "error": "Invalid limit parameter",
                            "message": f"Limit must be a number between 1 and 500, got '{limit}'"
                        }
                
                # Prepare request parameters
                request_params = {
                    'project_uuid': project_uuid,
                    'include_items': include_items,
                    'mode': mode,
                    'limit': actual_limit
                }
                
                # Apply smart defaults and optimization
                optimized_params, was_modified = self.context_manager.optimize_request('get_todos', request_params)
                
                # Extract optimized parameters
                final_include_items = optimized_params.get('include_items', False)
                final_limit = optimized_params.get('limit')
                response_mode = ResponseMode(optimized_params.get('mode', 'standard'))
                
                # Get raw data from tools layer
                raw_data = await self.tools.get_todos(
                    project_uuid=project_uuid, 
                    include_items=final_include_items
                )
                
                # Apply limit if specified
                if final_limit and len(raw_data) > final_limit:
                    raw_data = raw_data[:final_limit]
                
                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'get_todos', response_mode, optimized_params
                )
                
                # Add optimization metadata for transparency
                if was_modified:
                    optimized_response['optimization_applied'] = {
                        'smart_defaults_used': True,
                        'original_params': request_params,
                        'optimized_params': optimized_params
                    }
                
                return optimized_response
                
            except Exception as e:
                logger.error(f"Error getting todos: {e}")
                raise
        
        @self.mcp.tool()
        async def create_tag(
            tag_name: str = Field(..., description="Name of the tag to create")
        ) -> Dict[str, Any]:
            """Create a new tag in Things 3.
            
            IMPORTANT: This tool is for HUMAN USE ONLY. AI assistants should not create tags
            automatically. Tags should be intentionally created by users to maintain a clean
            and organized tag structure. If you need to use a tag that doesn't exist, please
            inform the user and ask if they'd like to create it.
            """
            # Check if AI can create tags based on configuration
            if not self.config.ai_can_create_tags:
                # Provide informative response for AI guidance
                return {
                    "success": False,
                    "error": "Tag creation is restricted to human users only",
                    "message": "This system is configured to require manual tag creation by users. This helps maintain a clean and intentional tag structure.",
                    "user_action": f"Please ask the user if they would like to create the tag '{tag_name}'",
                    "existing_tags_hint": "You can use get_tags to show the user existing tags they can use instead."
                }
            
            # If AI can create tags, proceed
            try:
                if self.tools.tag_validation_service:
                    result = await self.tools.tag_validation_service.create_tags([tag_name])
                    if result['created']:
                        return {
                            "success": True,
                            "message": f"Tag '{tag_name}' created successfully",
                            "tag": tag_name
                        }
                    else:
                        errors = result.get('errors', [])
                        return {
                            "success": False,
                            "error": errors[0] if errors else f"Failed to create tag '{tag_name}'",
                            "message": "Tag creation failed"
                        }
                else:
                    # Fallback if no validation service
                    return {
                        "success": False,
                        "error": "Tag validation service not available",
                        "message": "Cannot create tags without validation service"
                    }
            except Exception as e:
                logger.error(f"Error creating tag: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "message": "An error occurred while creating the tag"
                }
        
        @self.mcp.tool()
        async def add_todo(
            title: str = Field(..., description="Title of the todo"),
            notes: Optional[str] = Field(None, description="Notes for the todo"),
            tags: Optional[str] = Field(None, description="Comma-separated tags. NOTE: Only existing tags will be applied. New tags must be created separately by the user."),
            when: Optional[str] = Field(None, description="When to schedule the todo. Supports: 'today', 'tomorrow', 'evening', 'anytime', 'someday', 'YYYY-MM-DD' for dates, or 'today@HH:MM', 'tomorrow@HH:MM', 'YYYY-MM-DD@HH:MM' for specific time reminders (e.g. 'today@18:00', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="Deadline for the todo (YYYY-MM-DD)"),
            list_id: Optional[str] = Field(None, description="ID of project/area to add to"),
            list_title: Optional[str] = Field(None, description="Title of project/area to add to"),
            heading: Optional[str] = Field(None, description="Heading to add under"),
            checklist_items: Optional[str] = Field(None, description="Newline-separated checklist items to add")
        ) -> Dict[str, Any]:
            """Create a new todo in Things. 
            
            REMINDER SUPPORT: Use 'when' parameter with @HH:MM format for specific time reminders:
            - 'today@18:00' creates a reminder today at 6 PM
            - 'tomorrow@09:30' creates a reminder tomorrow at 9:30 AM  
            - '2024-12-25@14:30' creates a reminder on Christmas at 2:30 PM
            """
            try:
                # Convert comma-separated tags to list
                tag_list = [t.strip() for t in tags.split(",")] if tags else None
                result = await self.tools.add_todo(
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    list_id=list_id,
                    list_title=list_title,
                    heading=heading,
                    checklist_items=[item.strip() for item in checklist_items.split("\n")] if checklist_items else None
                )
                
                # Enhance response with tag validation feedback if available
                if (tag_list and self.tools.tag_validation_service and 
                    hasattr(result, 'get') and result.get('success')):
                    # Get tag validation info from the result
                    if 'tag_info' in result:
                        tag_info = result['tag_info']
                        if tag_info.get('created_tags'):
                            result['message'] = result.get('message', '') + f" Created new tags: {', '.join(tag_info['created_tags'])}"
                        if tag_info.get('filtered_tags'):
                            result['message'] = result.get('message', '') + f" Filtered tags: {', '.join(tag_info['filtered_tags'])}"
                        if tag_info.get('warnings'):
                            result['tag_warnings'] = tag_info['warnings']
                
                return result
            except Exception as e:
                logger.error(f"Error adding todo: {e}")
                raise
        
        @self.mcp.tool()
        async def update_todo(
            id: str = Field(..., description="ID of the todo to update"),
            title: Optional[str] = Field(None, description="New title"),
            notes: Optional[str] = Field(None, description="New notes"),
            tags: Optional[str] = Field(None, description="Comma-separated new tags"),
            when: Optional[str] = Field(None, description="New schedule. Supports: 'today', 'tomorrow', 'evening', 'anytime', 'someday', 'YYYY-MM-DD' for dates, or 'today@HH:MM', 'tomorrow@HH:MM', 'YYYY-MM-DD@HH:MM' for specific time reminders (e.g. 'today@18:00', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="New deadline"),
            completed: Optional[str] = Field(None, description="Mark as completed (true/false)"),
            canceled: Optional[str] = Field(None, description="Mark as canceled (true/false)")
        ) -> Dict[str, Any]:
            """Update an existing todo in Things."""
            try:
                # Convert comma-separated tags to list  
                tag_list = [t.strip() for t in tags.split(",")] if tags else None
                
                # Convert string booleans to actual booleans
                completed_bool = None
                if completed is not None:
                    completed_bool = completed.lower() == 'true' if isinstance(completed, str) else completed
                    
                canceled_bool = None
                if canceled is not None:
                    canceled_bool = canceled.lower() == 'true' if isinstance(canceled, str) else canceled
                
                result = await self.tools.update_todo(
                    todo_id=id,
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    completed=completed_bool,
                    canceled=canceled_bool
                )
                
                # Enhance response with tag validation feedback if available
                if (tag_list and self.tools.tag_validation_service and 
                    hasattr(result, 'get') and result.get('success')):
                    # Get tag validation info from the result
                    if 'tag_info' in result:
                        tag_info = result['tag_info']
                        if tag_info.get('created_tags'):
                            result['message'] = result.get('message', '') + f" Created new tags: {', '.join(tag_info['created_tags'])}"
                        if tag_info.get('filtered_tags'):
                            result['message'] = result.get('message', '') + f" Filtered tags: {', '.join(tag_info['filtered_tags'])}"
                        if tag_info.get('warnings'):
                            result['tag_warnings'] = tag_info['warnings']
                
                return result
            except Exception as e:
                logger.error(f"Error updating todo: {e}")
                raise
        
        @self.mcp.tool()
        async def get_todo_by_id(
            todo_id: str = Field(..., description="ID of the todo to retrieve")
        ) -> Dict[str, Any]:
            """Get a specific todo by its ID."""
            try:
                return await self.tools.get_todo_by_id(todo_id)
            except Exception as e:
                logger.error(f"Error getting todo by ID: {e}")
                raise
        
        @self.mcp.tool()
        async def delete_todo(
            todo_id: str = Field(..., description="ID of the todo to delete")
        ) -> Dict[str, Any]:
            """Delete a todo from Things."""
            try:
                return await self.tools.delete_todo(todo_id)
            except Exception as e:
                logger.error(f"Error deleting todo: {e}")
                raise
        
        @self.mcp.tool()
        async def move_record(
            todo_id: str = Field(..., description="ID of the todo to move"),
            destination_list: str = Field(..., description="Destination: list name (inbox, today, anytime, someday, upcoming, logbook), project:ID, or area:ID")
        ) -> Dict[str, Any]:
            """Move a todo to a different list, project, or area in Things."""
            try:
                return await self.tools.move_record(todo_id=todo_id, destination_list=destination_list)
            except Exception as e:
                logger.error(f"Error moving todo: {e}")
                raise
        
        @self.mcp.tool()
        async def bulk_move_records(
            todo_ids: str = Field(..., description="Comma-separated list of todo IDs to move"),
            destination: str = Field(..., description="Destination: list name (inbox, today, anytime, someday, upcoming, logbook), project:ID, or area:ID"),
            preserve_scheduling: bool = Field(True, description="Whether to preserve existing scheduling when moving"),
            max_concurrent: int = Field(5, description="Maximum concurrent operations (1-10)", ge=1, le=10)
        ) -> Dict[str, Any]:
            """Move multiple todos to the same destination efficiently."""
            try:
                # Parse the comma-separated todo IDs
                todo_id_list = [tid.strip() for tid in todo_ids.split(",") if tid.strip()]
                if not todo_id_list:
                    return {
                        "success": False,
                        "error": "NO_TODO_IDS",
                        "message": "No valid todo IDs provided",
                        "total_requested": 0
                    }
                
                # Use the advanced bulk move functionality
                result = await self.tools.move_operations.bulk_move(
                    todo_ids=todo_id_list,
                    destination=destination,
                    preserve_scheduling=preserve_scheduling,
                    max_concurrent=max_concurrent
                )
                
                return result
            except Exception as e:
                logger.error(f"Error in bulk move operation: {e}")
                raise
        
        # Project management tools
        @self.mcp.tool()
        async def get_projects(
            include_items: bool = Field(False, description="Include tasks within projects")
        ) -> List[Dict[str, Any]]:
            """Get all projects from Things."""
            try:
                return await self.tools.get_projects(include_items=include_items)
            except Exception as e:
                logger.error(f"Error getting projects: {e}")
                raise
        
        @self.mcp.tool()
        async def add_project(
            title: str = Field(..., description="Title of the project"),
            notes: Optional[str] = Field(None, description="Notes for the project"),
            tags: Optional[str] = Field(None, description="Comma-separated tags to apply to the project"),
            when: Optional[str] = Field(None, description="When to schedule the project. Supports: 'today', 'tomorrow', 'evening', 'anytime', 'someday', 'YYYY-MM-DD' for dates, or 'today@HH:MM', 'tomorrow@HH:MM', 'YYYY-MM-DD@HH:MM' for specific time reminders (e.g. 'today@18:00', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="Deadline for the project"),
            area_id: Optional[str] = Field(None, description="ID of area to add to"),
            area_title: Optional[str] = Field(None, description="Title of area to add to"),
            todos: Optional[str] = Field(None, description="Newline-separated initial todos to create in the project")
        ) -> Dict[str, Any]:
            """Create a new project in Things.
            
            REMINDER SUPPORT: Use 'when' parameter with @HH:MM format for specific time reminders:
            - 'today@18:00' creates a reminder today at 6 PM
            - 'tomorrow@09:30' creates a reminder tomorrow at 9:30 AM  
            - '2024-12-25@14:30' creates a reminder on Christmas at 2:30 PM
            """
            try:
                # Convert comma-separated tags to list
                tag_list = [t.strip() for t in tags.split(",")] if tags else None
                return await self.tools.add_project(
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    area_id=area_id,
                    area_title=area_title,
                    todos=[todo.strip() for todo in todos.split("\n")] if todos else None
                )
            except Exception as e:
                logger.error(f"Error adding project: {e}")
                raise
        
        @self.mcp.tool()
        async def update_project(
            id: str = Field(..., description="ID of the project to update"),
            title: Optional[str] = Field(None, description="New title"),
            notes: Optional[str] = Field(None, description="New notes"),
            tags: Optional[str] = Field(None, description="Comma-separated new tags"),
            when: Optional[str] = Field(None, description="New schedule. Supports: 'today', 'tomorrow', 'evening', 'anytime', 'someday', 'YYYY-MM-DD' for dates, or 'today@HH:MM', 'tomorrow@HH:MM', 'YYYY-MM-DD@HH:MM' for specific time reminders (e.g. 'today@18:00', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="New deadline"),
            completed: Optional[str] = Field(None, description="Mark as completed (true/false)"),
            canceled: Optional[str] = Field(None, description="Mark as canceled (true/false)")
        ) -> Dict[str, Any]:
            """Update an existing project in Things."""
            try:
                # Convert comma-separated tags to list
                tag_list = [t.strip() for t in tags.split(",")] if tags else None
                
                # Convert string booleans to actual booleans
                completed_bool = None
                if completed is not None:
                    completed_bool = completed.lower() == 'true' if isinstance(completed, str) else completed
                    
                canceled_bool = None
                if canceled is not None:
                    canceled_bool = canceled.lower() == 'true' if isinstance(canceled, str) else canceled
                
                return await self.tools.update_project(
                    project_id=id,
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    completed=completed_bool,
                    canceled=canceled_bool
                )
            except Exception as e:
                logger.error(f"Error updating project: {e}")
                raise
        
        # Area management tools
        @self.mcp.tool()
        async def get_areas(
            include_items: bool = Field(False, description="Include projects and tasks within areas")
        ) -> List[Dict[str, Any]]:
            """Get all areas from Things."""
            try:
                return await self.tools.get_areas(include_items=include_items)
            except Exception as e:
                logger.error(f"Error getting areas: {e}")
                raise
        
        # List-based tools
        @self.mcp.tool()
        async def get_inbox() -> List[Dict[str, Any]]:
            """Get todos from Inbox."""
            try:
                return await self.tools.get_inbox()
            except Exception as e:
                logger.error(f"Error getting inbox: {e}")
                raise
        
        @self.mcp.tool()
        async def get_today() -> List[Dict[str, Any]]:
            """Get todos due today."""
            try:
                return await self.tools.get_today()
            except Exception as e:
                logger.error(f"Error getting today's todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_upcoming() -> List[Dict[str, Any]]:
            """Get upcoming todos."""
            try:
                return await self.tools.get_upcoming()
            except Exception as e:
                logger.error(f"Error getting upcoming todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_anytime() -> List[Dict[str, Any]]:
            """Get todos from Anytime list."""
            try:
                return await self.tools.get_anytime()
            except Exception as e:
                logger.error(f"Error getting anytime todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_someday() -> List[Dict[str, Any]]:
            """Get todos from Someday list."""
            try:
                return await self.tools.get_someday()
            except Exception as e:
                logger.error(f"Error getting someday todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_logbook(
            limit: int = Field(50, description="Maximum number of entries to return. Defaults to 50", ge=1, le=100),
            period: str = Field("7d", description="Time period to look back (e.g., '3d', '1w', '2m', '1y'). Defaults to '7d'", pattern=r"^\d+[dwmy]$")
        ) -> List[Dict[str, Any]]:
            """Get completed todos from Logbook, defaults to last 7 days."""
            try:
                return await self.tools.get_logbook(limit=limit, period=period)
            except Exception as e:
                logger.error(f"Error getting logbook: {e}")
                raise
        
        @self.mcp.tool()
        async def get_trash() -> List[Dict[str, Any]]:
            """Get trashed todos."""
            try:
                return await self.tools.get_trash()
            except Exception as e:
                logger.error(f"Error getting trash: {e}")
                raise
        
        # Tag management tools
        @self.mcp.tool()
        async def get_tags(
            include_items: bool = Field(False, description="Include items tagged with each tag")
        ) -> List[Dict[str, Any]]:
            """Get all tags."""
            try:
                return await self.tools.get_tags(include_items=include_items)
            except Exception as e:
                logger.error(f"Error getting tags: {e}")
                raise
        
        @self.mcp.tool()
        async def get_tagged_items(
            tag: str = Field(..., description="Tag title to filter by")
        ) -> List[Dict[str, Any]]:
            """Get items with a specific tag."""
            try:
                return await self.tools.get_tagged_items(tag=tag)
            except Exception as e:
                logger.error(f"Error getting tagged items: {e}")
                raise
        
        # Search tools
        @self.mcp.tool()
        async def search_todos(
            query: str = Field(..., description="Search term to look for in todo titles and notes")
        ) -> List[Dict[str, Any]]:
            """Search todos by title or notes."""
            try:
                return await self.tools.search_todos(query=query)
            except Exception as e:
                logger.error(f"Error searching todos: {e}")
                raise
        
        @self.mcp.tool()
        async def search_advanced(
            status: Optional[str] = Field(None, description="Filter by todo status", pattern="^(incomplete|completed|canceled)$"),
            type: Optional[str] = Field(None, description="Filter by item type", pattern="^(to-do|project|heading)$"),
            tag: Optional[str] = Field(None, description="Filter by tag"),
            area: Optional[str] = Field(None, description="Filter by area UUID"),
            start_date: Optional[str] = Field(None, description="Filter by start date (YYYY-MM-DD)"),
            deadline: Optional[str] = Field(None, description="Filter by deadline (YYYY-MM-DD)"),
            limit: int = Field(50, description="Maximum number of results to return (1-500)", ge=1, le=500)
        ) -> List[Dict[str, Any]]:
            """Advanced todo search with multiple filters."""
            try:
                return await self.tools.search_advanced(
                    status=status,
                    type=type,
                    tag=tag,
                    area=area,
                    start_date=start_date,
                    deadline=deadline,
                    limit=limit
                )
            except Exception as e:
                logger.error(f"Error in advanced search: {e}")
                raise
        
        @self.mcp.tool()
        async def get_recent(
            period: str = Field(..., description="Time period (e.g., '3d', '1w', '2m', '1y')", pattern=r"^\d+[dwmy]$")
        ) -> List[Dict[str, Any]]:
            """Get recently created items."""
            try:
                return await self.tools.get_recent(period=period)
            except Exception as e:
                logger.error(f"Error getting recent items: {e}")
                raise
        
        # Navigation tools
        @self.mcp.tool()
        async def add_tags(
            todo_id: str = Field(..., description="ID of the todo"),
            tags: str = Field(..., description="Comma-separated tags to add")
        ) -> Dict[str, Any]:
            """Add tags to a todo."""
            try:
                # Convert comma-separated tags to list
                tag_list = [t.strip() for t in tags.split(",")] if tags else []
                result = await self.tools.add_tags(todo_id=todo_id, tags=tag_list)
                
                # Enhance response with tag policy feedback
                if (self.tools.tag_validation_service and 
                    hasattr(result, 'get') and result.get('success')):
                    policy = self.tools.config.tag_creation_policy if self.tools.config else 'allow_all'
                    
                    # Add policy information to response
                    result['tag_policy'] = {
                        'policy': policy.value if hasattr(policy, 'value') else str(policy),
                        'description': self._get_policy_description(policy)
                    }
                    
                    # Get tag validation info from the result
                    if 'tag_info' in result:
                        tag_info = result['tag_info']
                        if tag_info.get('created_tags'):
                            result['message'] = result.get('message', 'Tags added successfully.') + f" Created new tags: {', '.join(tag_info['created_tags'])}"
                        if tag_info.get('filtered_tags'):
                            result['message'] = result.get('message', 'Tags added successfully.') + f" Filtered tags per policy: {', '.join(tag_info['filtered_tags'])}"
                        if tag_info.get('warnings'):
                            result['tag_warnings'] = tag_info['warnings']
                
                return result
            except Exception as e:
                logger.error(f"Error adding tags: {e}")
                raise
        
        @self.mcp.tool()
        async def remove_tags(
            todo_id: str = Field(..., description="ID of the todo"),
            tags: str = Field(..., description="Comma-separated tags to remove")
        ) -> Dict[str, Any]:
            """Remove tags from a todo."""
            try:
                # Convert comma-separated tags to list
                tag_list = [t.strip() for t in tags.split(",")] if tags else []
                return await self.tools.remove_tags(todo_id=todo_id, tags=tag_list)
            except Exception as e:
                logger.error(f"Error removing tags: {e}")
                raise
        
        # Removed show_item and search_items as they trigger UI changes
        # which are not appropriate for MCP server operations
        
        # Health check tool
        @self.mcp.tool()
        async def health_check() -> Dict[str, Any]:
            """Check server health and Things 3 connectivity."""
            try:
                is_running = await self.applescript_manager.is_things_running()
                return {
                    "server_status": "healthy",
                    "things_running": is_running,
                    "applescript_available": True,
                    "timestamp": self.applescript_manager._get_current_timestamp()
                }
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return {
                    "server_status": "unhealthy",
                    "error": str(e),
                    "timestamp": self.applescript_manager._get_current_timestamp()
                }

        @self.mcp.tool()
        async def queue_status() -> Dict[str, Any]:
            """Get operation queue status and statistics."""
            try:
                queue = await get_operation_queue()
                status = queue.get_queue_status()
                active_ops = queue.get_active_operations()
                return {
                    "queue_status": status,
                    "active_operations": active_ops,
                    "timestamp": self.applescript_manager._get_current_timestamp()
                }
            except Exception as e:
                logger.error(f"Queue status check failed: {e}")
                return {
                    "error": str(e),
                    "timestamp": self.applescript_manager._get_current_timestamp()
                }
        
        @self.mcp.tool()
        async def context_stats() -> Dict[str, Any]:
            """Get context usage statistics and optimization insights."""
            try:
                stats = self.context_manager.get_context_usage_stats()
                
                # Add current optimization status
                stats['optimization_status'] = {
                    'auto_mode_enabled': True,
                    'smart_defaults_active': True,
                    'context_aware_responses': True,
                    'dynamic_field_filtering': True
                }
                
                # Add usage recommendations
                stats['recommendations'] = [
                    "Use 'mode=auto' for intelligent response optimization",
                    "Use 'mode=summary' for large datasets to get counts and insights",
                    "Use 'mode=minimal' when you only need basic todo information",
                    "Use 'limit' parameter to control response size"
                ]
                
                return stats
            except Exception as e:
                logger.error(f"Error getting context stats: {e}")
                return {
                    "error": str(e),
                    "context_management": "Context awareness is active but stats unavailable"
                }

        @self.mcp.tool()
        async def get_server_capabilities() -> Dict[str, Any]:
            """🎯 Get comprehensive server capabilities and feature discovery information.
            
            🔍 CONTEXT-OPTIMIZED: Returns structured capability information
            📊 INTELLIGENT: Provides feature matrix and usage recommendations
            ⚡ PERFORMANCE: Lightweight response for quick feature discovery
            
            Returns complete information about:
            - Available features and their badges
            - Context optimization settings  
            - API coverage statistics
            - Performance characteristics
            - Usage recommendations
            
            Perfect for AI assistants to understand server capabilities and optimize their interactions.
            """
            try:
                capabilities = {
                    "server_info": {
                        "name": "Things 3 MCP Server",
                        "version": "2.0",
                        "platform": "macOS",
                        "framework": "FastMCP 2.0",
                        "total_tools": 27  # Updated count including new tools
                    },
                    "features": {
                        "context_optimization": {
                            "enabled": True,
                            "badge": "🔍 Context-Optimized",
                            "modes": ["auto", "summary", "minimal", "standard", "detailed", "raw"],
                            "smart_defaults": True,
                            "progressive_disclosure": True,
                            "budget_management": True,
                            "relevance_ranking": True
                        },
                        "reminder_system": {
                            "enabled": True,
                            "badge": "📅 Reminder-Capable",
                            "formats": ["today@14:30", "tomorrow@09:30", "YYYY-MM-DD@HH:MM"],
                            "url_scheme_support": True,
                            "notification_integration": True,
                            "timezone_aware": True
                        },
                        "bulk_operations": {
                            "enabled": True,
                            "badge": "🔄 Bulk-Capable", 
                            "max_concurrent": 10,
                            "operations": ["move", "tag_management", "status_updates"],
                            "queue_management": True,
                            "progress_tracking": True
                        },
                        "tag_management": {
                            "enabled": True,
                            "badge": "🏷️ Tag-Aware",
                            "validation_policies": ["allow_all", "filter_unknown", "warn_unknown", "reject_unknown"],
                            "ai_creation_restricted": not self.config.ai_can_create_tags,
                            "policy_enforcement": True,
                            "intelligent_suggestions": True
                        },
                        "performance_optimization": {
                            "enabled": True,
                            "badge": "⚡ Performance-Tuned",
                            "async_operations": True,
                            "connection_pooling": True,
                            "response_caching": False,  # AppleScript doesn't benefit from caching
                            "smart_pagination": True
                        },
                        "analytics": {
                            "enabled": True,
                            "badge": "📊 Analytics-Enabled",
                            "usage_tracking": True,
                            "performance_monitoring": True,
                            "context_usage_stats": True,
                            "queue_status_reporting": True
                        }
                    },
                    "api_coverage": {
                        "total_tools": 27,
                        "applescript_coverage_percentage": 45,
                        "workflow_operations": ["create", "read", "update", "delete", "move", "search"],
                        "list_operations": ["inbox", "today", "upcoming", "anytime", "someday", "logbook", "trash"],
                        "organization": ["projects", "areas", "tags", "headings"],
                        "advanced_features": ["reminders", "bulk_ops", "context_optimization"]
                    },
                    "performance_characteristics": {
                        "context_budget_kb": round(self.context_manager.context_budget.total_budget / 1024, 1),
                        "max_response_size_kb": round(self.context_manager.context_budget.max_response_size / 1024, 1),
                        "warning_threshold_kb": round(self.context_manager.context_budget.warning_threshold / 1024, 1),
                        "pagination_support": True,
                        "relevance_ranking": True,
                        "field_level_filtering": True,
                        "estimated_items_per_kb": {"summary": 20, "minimal": 5, "standard": 1, "detailed": 0.8}
                    },
                    "usage_recommendations": {
                        "daily_workflow": {
                            "morning_review": "get_today()",
                            "quick_capture": "add_todo() with minimal fields",
                            "project_overview": "get_projects(mode='summary')",
                            "bulk_organization": "bulk_move_records() with mode='minimal'"
                        },
                        "optimization_tips": [
                            "Start with mode='auto' for unknown datasets",
                            "Use mode='summary' for large collections to get insights first",
                            "Use mode='minimal' for bulk operations to get essential data only",
                            "Request mode='detailed' only when you need complete field information",
                            "Use limit parameter to control response sizes"
                        ],
                        "error_recovery": [
                            "Check get_tags() before creating new tags",
                            "Use health_check() to verify Things 3 connectivity",
                            "Monitor queue_status() during bulk operations",
                            "Check context_stats() if responses seem truncated"
                        ]
                    },
                    "compatibility": {
                        "things_version": "3.0+",
                        "macos_version": "12.0+",
                        "python_version": "3.8+",
                        "mcp_version": "1.0+",
                        "applescript_support": True,
                        "url_scheme_support": True
                    }
                }
                
                # Add dynamic information
                is_things_running = await self.applescript_manager.is_things_running()
                queue = await get_operation_queue()
                queue_status = queue.get_queue_status()
                
                capabilities["current_status"] = {
                    "things_running": is_things_running,
                    "server_healthy": True,
                    "queue_active": queue_status.get('active_operations', 0) > 0,
                    "applescript_available": True,
                    "timestamp": self.applescript_manager._get_current_timestamp()
                }
                
                return capabilities
            except Exception as e:
                logger.error(f"Error getting server capabilities: {e}")
                return {
                    "error": str(e),
                    "fallback_info": {
                        "server_name": "Things 3 MCP Server",
                        "basic_functionality": "Available", 
                        "capabilities_discovery": "Failed - using fallback mode"
                    }
                }

        @self.mcp.tool()
        async def get_usage_recommendations(
            operation: Optional[str] = Field(None, description="Specific operation to get recommendations for (e.g., 'get_todos', 'bulk_move')")
        ) -> Dict[str, Any]:
            """📊 Get personalized usage recommendations based on current state and operation.
            
            🎯 INTELLIGENT: Analyzes current data size and provides optimal parameters
            ⚡ PERFORMANCE: Suggests best practices for efficient operations
            🔍 CONTEXT-AWARE: Considers current context budget and usage patterns
            
            Args:
                operation: Specific operation to get recommendations for
                
            Returns:
                - Recommended parameters for operations
                - Optimal workflow suggestions
                - Performance tips tailored to current state
                - Context usage estimates
                - Error prevention guidance
            """
            try:
                recommendations = {
                    "timestamp": self.applescript_manager._get_current_timestamp(),
                    "context_status": self.context_manager.get_context_usage_stats()
                }
                
                # Get current system state
                is_things_running = await self.applescript_manager.is_things_running()
                
                if operation:
                    # Provide operation-specific recommendations
                    if operation == "get_todos":
                        # Sample data to make intelligent recommendations
                        try:
                            sample_todos = await self.tools.get_todos(None, False)  # Small sample
                            todo_count = len(sample_todos)
                            
                            if todo_count == 0:
                                recommendations[operation] = {
                                    "suggested_mode": "standard",
                                    "reason": "No todos found - standard mode provides complete view",
                                    "next_actions": ["Check get_inbox()", "Try get_projects()"],
                                    "estimated_response_size_kb": 0.1
                                }
                            elif todo_count <= 10:
                                recommendations[operation] = {
                                    "suggested_mode": "detailed",
                                    "suggested_limit": None,
                                    "reason": "Small dataset - detailed mode is safe",
                                    "estimated_response_size_kb": todo_count * 1.2,
                                    "include_items": "optional"
                                }
                            elif todo_count <= 50:
                                recommendations[operation] = {
                                    "suggested_mode": "standard", 
                                    "suggested_limit": 30,
                                    "reason": "Medium dataset - standard mode with limit",
                                    "estimated_response_size_kb": 30,
                                    "include_items": False
                                }
                            else:
                                recommendations[operation] = {
                                    "suggested_mode": "summary",
                                    "suggested_limit": None,
                                    "reason": "Large dataset detected - start with summary",
                                    "estimated_response_size_kb": 2,
                                    "next_steps": "Use summary insights to decide on detailed queries",
                                    "include_items": False
                                }
                        except Exception as e:
                            recommendations[operation] = {
                                "suggested_mode": "auto",
                                "reason": "Unable to analyze current data - auto mode will adapt",
                                "fallback": True,
                                "error": str(e)
                            }
                    
                    elif operation == "bulk_move_records":
                        recommendations[operation] = {
                            "max_concurrent": min(5, max(1, int(10))),  # Conservative default
                            "preserve_scheduling": True,
                            "pre_check": "Use get_todos(mode='minimal') to verify IDs",
                            "progress_monitoring": "Check queue_status() during operation",
                            "estimated_time_per_item": "0.5-1 seconds"
                        }
                    
                    elif operation == "add_todo":
                        existing_tags = []
                        try:
                            existing_tags = await self.tools.get_tags(False)
                            tag_count = len(existing_tags)
                        except:
                            tag_count = 0
                        
                        recommendations[operation] = {
                            "tag_strategy": "Use existing tags only" if not self.config.ai_can_create_tags else "Can create new tags",
                            "available_tags_count": tag_count,
                            "reminder_format": "Use 'today@14:30' format for timed reminders",
                            "suggested_workflow": [
                                "Check existing tags with get_tags()",
                                "Create todo with existing tags",
                                "Verify creation success"
                            ]
                        }
                else:
                    # General recommendations
                    recommendations["general"] = {
                        "discovery_workflow": [
                            "1. Start with get_server_capabilities() to understand features",
                            "2. Use get_today() for current priorities",
                            "3. Use get_projects(mode='summary') for project overview",
                            "4. Use context-aware modes for large datasets"
                        ],
                        "performance_tips": [
                            "Use mode='auto' as default - it adapts to data size",
                            "Use mode='summary' for initial exploration of large datasets",
                            "Use specific limits to control response size",
                            "Monitor context_stats() to track usage"
                        ],
                        "error_prevention": [
                            "Check health_check() before bulk operations",
                            "Use get_tags() before creating todos with new tags",
                            "Monitor queue_status() during concurrent operations"
                        ]
                    }
                
                # Add context-specific recommendations
                current_stats = self.context_manager.get_context_usage_stats()
                recommendations["context_guidance"] = {
                    "budget_remaining_kb": current_stats["available_for_response_kb"],
                    "suggested_max_items": {
                        "summary_mode": int(current_stats["available_for_response_kb"] * 20),
                        "minimal_mode": int(current_stats["available_for_response_kb"] * 5),
                        "standard_mode": int(current_stats["available_for_response_kb"] * 1),
                        "detailed_mode": int(current_stats["available_for_response_kb"] * 0.8)
                    }
                }
                
                # Add system status
                recommendations["system_status"] = {
                    "things_running": is_things_running,
                    "ready_for_operations": is_things_running,
                    "recommended_checks": [] if is_things_running else ["Start Things 3 application", "Check system permissions"]
                }
                
                return recommendations
            except Exception as e:
                logger.error(f"Error getting usage recommendations: {e}")
                return {
                    "error": str(e),
                    "fallback_recommendations": {
                        "safe_defaults": {
                            "mode": "auto",
                            "limit": 25,
                            "include_items": False
                        },
                        "guidance": "Use conservative parameters when server analysis is unavailable"
                    }
                }

        logger.info("All MCP tools registered successfully")
    
    def _get_policy_description(self, policy) -> str:
        """Get human-readable description of tag creation policy.
        
        Args:
            policy: Tag creation policy
            
        Returns:
            Description string
        """
        policy_descriptions = {
            'allow_all': 'New tags will be created automatically',
            'filter_unknown': 'Unknown tags will be filtered out',
            'warn_unknown': 'Unknown tags allowed with warnings',
            'reject_unknown': 'Operations with unknown tags will be rejected'
        }
        
        policy_str = policy.value if hasattr(policy, 'value') else str(policy)
        return policy_descriptions.get(policy_str, 'Custom policy')
    
    def run(self) -> None:
        """Run the MCP server."""
        try:
            logger.info("Starting Things MCP Server...")
            self.mcp.run()
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server error: {e}")
            raise
    
    def stop(self) -> None:
        """Stop the MCP server gracefully."""
        try:
            logger.info("Stopping Things MCP Server...")
        except (ValueError, OSError):
            # Streams may be closed during shutdown
            pass
            
        try:
            # Shutdown operation queue
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(shutdown_operation_queue())
            else:
                loop.run_until_complete(shutdown_operation_queue())
        except Exception as e:
            try:
                logger.error(f"Error stopping operation queue: {e}")
            except (ValueError, OSError):
                # Streams already closed, ignore
                pass
                
        try:
            logger.info("Things MCP Server stopped")
        except (ValueError, OSError):
            # Streams may be closed during shutdown
            pass


def main():
    """Main entry point for the simple server."""
    # Check for config path in environment or command line
    import os
    config_path = os.getenv('THINGS_MCP_CONFIG_PATH')
    server = ThingsMCPServer(config_path=config_path)
    server.run()


if __name__ == "__main__":
    main()