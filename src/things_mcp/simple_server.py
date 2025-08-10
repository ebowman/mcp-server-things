"""Simple FastMCP 2.0 server implementation for Things 3 integration."""

import asyncio
import atexit
import logging
import signal
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Optional dotenv support
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not available, continue without it
    pass

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from .applescript_manager import AppleScriptManager
from .tools import ThingsTools
from .operation_queue import shutdown_operation_queue, get_operation_queue
from .config import ThingsMCPConfig, load_config_from_env

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
        self._register_tools()
        self._register_shutdown_handlers()
        logger.info("Things MCP Server initialized with tag validation support")

    def _register_shutdown_handlers(self):
        """Register shutdown handlers for graceful cleanup."""
        def shutdown_handler():
            """Handle server shutdown."""
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # If we're in an async context, schedule the shutdown
                    loop.create_task(shutdown_operation_queue())
                else:
                    # If not, run it directly
                    loop.run_until_complete(shutdown_operation_queue())
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")
        
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
            project_uuid: Optional[str] = Field(None, description="Optional UUID of a specific project to get todos from"),
            include_items: bool = Field(True, description="Include checklist items")
        ) -> List[Dict[str, Any]]:
            """Get todos from Things, optionally filtered by project."""
            try:
                return await self.tools.get_todos(project_uuid=project_uuid, include_items=include_items)
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
            when: Optional[str] = Field(None, description="When to schedule the todo (today, tomorrow, evening, anytime, someday, or YYYY-MM-DD)"),
            deadline: Optional[str] = Field(None, description="Deadline for the todo (YYYY-MM-DD)"),
            list_id: Optional[str] = Field(None, description="ID of project/area to add to"),
            list_title: Optional[str] = Field(None, description="Title of project/area to add to"),
            heading: Optional[str] = Field(None, description="Heading to add under"),
            checklist_items: Optional[str] = Field(None, description="Newline-separated checklist items to add")
        ) -> Dict[str, Any]:
            """Create a new todo in Things."""
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
            when: Optional[str] = Field(None, description="New schedule"),
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
            when: Optional[str] = Field(None, description="When to schedule the project"),
            deadline: Optional[str] = Field(None, description="Deadline for the project"),
            area_id: Optional[str] = Field(None, description="ID of area to add to"),
            area_title: Optional[str] = Field(None, description="Title of area to add to"),
            todos: Optional[str] = Field(None, description="Newline-separated initial todos to create in the project")
        ) -> Dict[str, Any]:
            """Create a new project in Things."""
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
            when: Optional[str] = Field(None, description="New schedule"),
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
        logger.info("Stopping Things MCP Server...")
        try:
            # Shutdown operation queue
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(shutdown_operation_queue())
            else:
                loop.run_until_complete(shutdown_operation_queue())
        except Exception as e:
            logger.error(f"Error stopping operation queue: {e}")
        logger.info("Things MCP Server stopped")


def main():
    """Main entry point for the simple server."""
    # Check for config path in environment or command line
    import os
    config_path = os.getenv('THINGS_MCP_CONFIG_PATH')
    server = ThingsMCPServer(config_path=config_path)
    server.run()


if __name__ == "__main__":
    main()