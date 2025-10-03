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

from . import __version__
from .services.applescript_manager import AppleScriptManager
from .tools import ThingsTools
from .operation_queue import shutdown_operation_queue, get_operation_queue
from .config import ThingsMCPConfig, load_config_from_env
from .context_manager import ContextAwareResponseManager, ResponseMode
# from .query_engine import NaturalLanguageQueryEngine  # Removed - too complex

logger = logging.getLogger(__name__)


class ThingsMCPServer:
    """Simple MCP server for Things 3 integration."""
    
    def __init__(self, env_file: Optional[str] = None):
        """Initialize the Things MCP server.
        
        Args:
            env_file: Optional path to .env file
        """
        self.mcp = FastMCP("things-mcp")
        
        # Load configuration from environment and optional .env file
        if env_file:
            try:
                self.config = load_config_from_env(Path(env_file))
                logger.info(f"Loaded configuration from {env_file}")
            except FileNotFoundError as e:
                logger.error(f"Configuration file not found: {env_file}")
                raise
            except Exception as e:
                logger.warning(f"Failed to load config from {env_file}: {e}. Using environment/defaults.")
                self.config = load_config_from_env()
        else:
            self.config = load_config_from_env()
        
        # Configure logging based on config
        self._configure_logging()
        
        self.applescript_manager = AppleScriptManager()
        self.tools = ThingsTools(self.applescript_manager, self.config)
        self.context_manager = ContextAwareResponseManager()
        # self.query_engine = NaturalLanguageQueryEngine(self.tools)  # Removed - too complex
        self._register_tools()
        self._register_shutdown_handlers()
        logger.info("Things MCP Server initialized with context-aware response management and tag validation support")
    
    def _configure_logging(self):
        """Configure logging based on configuration settings."""
        # Get root logger
        root_logger = logging.getLogger()
        
        # Set log level from config
        root_logger.setLevel(self.config.log_level.value)
        
        # Clear any existing handlers to avoid duplicates
        root_logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Add file handler if configured
        if self.config.log_file_path:
            try:
                # Ensure log directory exists
                self.config.log_file_path.parent.mkdir(parents=True, exist_ok=True)
                
                file_handler = logging.FileHandler(self.config.log_file_path)
                file_handler.setFormatter(formatter)
                root_logger.addHandler(file_handler)
                logger.info(f"Logging to file: {self.config.log_file_path}")
            except Exception as e:
                logger.warning(f"Failed to setup file logging: {e}")
                # Fall back to console logging
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                root_logger.addHandler(console_handler)
        else:
            # Console handler for stdout
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)

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
            limit: Any = None,
            status: Optional[str] = 'incomplete'
        ) -> Dict[str, Any]:
            """Get todos with context-aware response optimization. Supports mode parameter (auto/summary/minimal/standard/detailed/raw) and optional project filtering. Use mode='auto' for adaptive responses.

            Args:
                project_uuid: Optional project UUID to filter by
                include_items: Include checklist items
                mode: Response mode (auto/summary/minimal/standard/detailed/raw)
                limit: Maximum number of results to return (1-500)
                status: Filter by status - 'incomplete' (default), 'completed', 'canceled', or None for all
            """
            try:
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return {
                        "success": False,
                        "error": "Invalid mode",
                        "message": f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}"
                    }

                # Normalize status parameter (MCP may pass string "None")
                if status == "None" or status == "null":
                    status = None

                # Validate status parameter
                if status is not None and status not in ["incomplete", "completed", "canceled"]:
                    return {
                        "success": False,
                        "error": "Invalid status",
                        "message": f"Status must be one of: 'incomplete', 'completed', 'canceled', or None for all. Got: {status}"
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
                    'limit': actual_limit,
                    'status': status
                }

                # Apply smart defaults and optimization
                optimized_params, was_modified = self.context_manager.optimize_request('get_todos', request_params)

                # Extract optimized parameters
                final_include_items = optimized_params.get('include_items', False)
                final_limit = optimized_params.get('limit')
                final_status = optimized_params.get('status', 'incomplete')
                response_mode = ResponseMode(optimized_params.get('mode', 'standard'))

                # Get raw data from tools layer
                raw_data = await self.tools.get_todos(
                    project_uuid=project_uuid,
                    include_items=final_include_items,
                    status=final_status
                )
                
                # Apply limit if specified
                if final_limit and len(raw_data) > final_limit:
                    raw_data = raw_data[:final_limit]
                
                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'get_todos', response_mode, optimized_params
                )
                
                # Add minimal optimization metadata
                if was_modified:
                    optimized_response['optimized'] = True
                
                return optimized_response
                
            except Exception as e:
                logger.error(f"Error getting todos: {e}")
                raise
        
        @self.mcp.tool()
        async def create_tag(
            tag_name: str = Field(..., description="Name of the tag to create")
        ) -> Dict[str, Any]:
            """Create a new tag. Note: For human use only, AI should ask users to create tags."""
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
            title: str = Field(..., min_length=1, description="Title of the todo"),
            notes: Optional[str] = Field(None, description="Notes for the todo"),
            tags: Optional[str] = Field(None, description="Comma-separated tags (only existing tags applied)"),
            when: Optional[str] = Field(None, description="Schedule date/time (e.g., 'today', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="Deadline for the todo (YYYY-MM-DD)"),
            list_id: Optional[str] = Field(None, description="ID of project/area to add to"),
            list_title: Optional[str] = Field(None, description="Title of project/area to add to"),
            heading: Optional[str] = Field(None, description="Heading to add under"),
            checklist_items: Optional[str] = Field(None, description="Newline-separated checklist items to add")
        ) -> Dict[str, Any]:
            """Create a new todo. Supports scheduling (when='today', 'tomorrow', 'YYYY-MM-DD'), tags, projects, deadlines, and notes."""
            try:
                # Validate date parameters
                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid when date",
                            "message": str(e)
                        }

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid deadline date",
                            "message": str(e)
                        }

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
            when: Optional[str] = Field(None, description="Schedule date/time (e.g., 'today', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="New deadline"),
            completed: Optional[str] = Field(None, description="Mark as completed (true/false)"),
            canceled: Optional[str] = Field(None, description="Mark as canceled (true/false)")
        ) -> Dict[str, Any]:
            """Update an existing todo. Supports partial updates to any field including status, scheduling, tags, and content."""
            try:
                # Validate date parameters
                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid when date",
                            "message": str(e)
                        }

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid deadline date",
                            "message": str(e)
                        }

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
        async def bulk_update_todos(
            todo_ids: str = Field(..., description="Comma-separated list of todo IDs to update"),
            title: Optional[str] = Field(None, description="New title for all todos"),
            notes: Optional[str] = Field(None, description="New notes for all todos"),
            tags: Optional[str] = Field(None, description="Comma-separated tags to apply to all todos"),
            when: Optional[str] = Field(None, description="Schedule date (e.g., 'today', '2024-12-25')"),
            deadline: Optional[str] = Field(None, description="New deadline for all todos (YYYY-MM-DD)"),
            completed: Optional[str] = Field(None, description="Mark all as completed (true/false)"),
            canceled: Optional[str] = Field(None, description="Mark all as canceled (true/false)")
        ) -> Dict[str, Any]:
            """Update multiple todos with the same changes in a single operation."""
            try:
                # Validate date parameters
                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid when date",
                            "message": str(e)
                        }

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid deadline date",
                            "message": str(e)
                        }

                # Parse comma-separated IDs
                id_list = [id.strip() for id in todo_ids.split(",") if id.strip()]

                if not id_list:
                    return {
                        "success": False,
                        "error": "No valid todo IDs provided",
                        "updated_count": 0
                    }

                # Convert comma-separated tags to list
                tag_list = [t.strip() for t in tags.split(",")] if tags else None

                # Convert string booleans to actual booleans
                completed_bool = None
                if completed is not None:
                    completed_bool = completed.lower() == 'true' if isinstance(completed, str) else completed

                canceled_bool = None
                if canceled is not None:
                    canceled_bool = canceled.lower() == 'true' if isinstance(canceled, str) else canceled

                result = await self.tools.bulk_update_todos(
                    todo_ids=id_list,
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    completed=completed_bool,
                    canceled=canceled_bool
                )

                # Enhance response with tag validation feedback if available
                if (tag_list and result.get('success') and 'tag_info' in result):
                    tag_info = result['tag_info']
                    if tag_info:
                        if tag_info.get('created'):
                            result['message'] = result.get('message', '') + f" Created new tags: {', '.join(tag_info['created'])}"
                        if tag_info.get('filtered'):
                            result['message'] = result.get('message', '') + f" Filtered tags: {', '.join(tag_info['filtered'])}"
                        if tag_info.get('warnings'):
                            result['tag_warnings'] = tag_info['warnings']

                return result
            except Exception as e:
                logger.error(f"Error in bulk update: {e}")
                return {
                    "success": False,
                    "error": str(e),
                    "updated_count": 0
                }

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
            """Delete a todo by ID."""
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
            """Move a todo to a different list, project, or area."""
            try:
                return await self.tools.move_record(todo_id=todo_id, destination_list=destination_list)
            except Exception as e:
                logger.error(f"Error moving todo: {e}")
                raise
        
        @self.mcp.tool()
        async def bulk_move_records(
            todo_ids: str = Field(..., description="Comma-separated list of todo IDs to move"),
            destination: str = Field(..., description="Destination: list name (inbox, today, anytime, someday, upcoming, logbook), project:ID, or area:ID"),
            max_concurrent: int = Field(5, description="Maximum concurrent operations (1-10)", ge=1, le=10)
        ) -> Dict[str, Any]:
            """Move multiple todos to the same destination efficiently. The move operation handles scheduling automatically based on the destination."""
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
                    max_concurrent=max_concurrent
                )
                
                return result
            except Exception as e:
                logger.error(f"Error in bulk move operation: {e}")
                raise
        
        # Project management tools
        @self.mcp.tool()
        async def get_projects(
            include_items: bool = Field(False, description="Include tasks within projects"),
            mode: Optional[str] = Field(None, description="Response mode (auto/summary/minimal/standard/detailed/raw)")
        ) -> Dict[str, Any]:
            """Get all projects with optional task inclusion. Supports include_items and response optimization via mode parameter."""
            try:
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return {
                        "success": False,
                        "error": "Invalid mode",
                        "message": f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}"
                    }

                # Prepare request parameters
                request_params = {
                    'include_items': include_items,
                    'mode': mode
                }

                # Apply smart defaults and optimization
                optimized_params, was_modified = self.context_manager.optimize_request('get_projects', request_params)

                # Extract optimized parameters
                final_include_items = optimized_params.get('include_items', False)
                response_mode = ResponseMode(optimized_params.get('mode', 'standard'))

                # Get raw data from tools layer
                raw_data = await self.tools.get_projects(include_items=final_include_items)

                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'get_projects', response_mode, optimized_params
                )

                return optimized_response
            except Exception as e:
                logger.error(f"Error getting projects: {e}")
                raise
        
        @self.mcp.tool()
        async def add_project(
            title: str = Field(..., min_length=1, description="Title of the project"),
            notes: Optional[str] = Field(None, description="Notes for the project"),
            tags: Optional[str] = Field(None, description="Comma-separated tags to apply to the project"),
            when: Optional[str] = Field(None, description="Schedule date/time (e.g., 'today', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="Deadline for the project"),
            area_id: Optional[str] = Field(None, description="ID of area to add to"),
            area_title: Optional[str] = Field(None, description="Title of area to add to"),
            todos: Optional[str] = Field(None, description="Newline-separated initial todos to create in the project")
        ) -> Dict[str, Any]:
            """Create a new project. Supports areas, deadlines, tags, initial todos, and scheduling."""
            try:
                # Validate date parameters
                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid when date",
                            "message": str(e)
                        }

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid deadline date",
                            "message": str(e)
                        }

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
            when: Optional[str] = Field(None, description="Schedule date/time (e.g., 'today', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="New deadline"),
            completed: Optional[str] = Field(None, description="Mark as completed (true/false)"),
            canceled: Optional[str] = Field(None, description="Mark as canceled (true/false)")
        ) -> Dict[str, Any]:
            """Update an existing project. Supports partial updates to any field including status, scheduling, tags, and content."""
            try:
                # Validate date parameters
                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid when date",
                            "message": str(e)
                        }

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return {
                            "success": False,
                            "error": "Invalid deadline date",
                            "message": str(e)
                        }

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
            include_items: bool = Field(False, description="Include projects and tasks within areas"),
            mode: Optional[str] = Field(None, description="Response mode (auto/summary/minimal/standard/detailed/raw)")
        ) -> Dict[str, Any]:
            """Get all areas with optional project/task inclusion. Supports include_items and response optimization via mode parameter."""
            try:
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return {
                        "success": False,
                        "error": "Invalid mode",
                        "message": f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}"
                    }

                # Prepare request parameters
                request_params = {
                    'include_items': include_items,
                    'mode': mode
                }

                # Apply smart defaults and optimization
                optimized_params, was_modified = self.context_manager.optimize_request('get_areas', request_params)

                # Extract optimized parameters
                final_include_items = optimized_params.get('include_items', False)
                response_mode = ResponseMode(optimized_params.get('mode', 'standard'))

                # Get raw data from tools layer
                raw_data = await self.tools.get_areas(include_items=final_include_items)

                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'get_areas', response_mode, optimized_params
                )

                return optimized_response
            except Exception as e:
                logger.error(f"Error getting areas: {e}")
                raise
        
        # List-based tools
        @self.mcp.tool()
        async def get_inbox(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500)
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Get todos from Inbox. Supports response optimization via mode parameter and limit."""
            try:
                # Get raw data with optional limit
                raw_data = await self.tools.get_inbox(limit=limit)

                # Apply context-aware optimization if mode is specified
                if mode:
                    request_params = {'mode': mode, 'limit': limit}
                    optimized_params, _ = self.context_manager.optimize_request('get_inbox', request_params)
                    response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                    return self.context_manager.optimize_response(raw_data, 'get_inbox', response_mode, optimized_params)

                return raw_data
            except Exception as e:
                logger.error(f"Error getting inbox: {e}")
                raise
        
        @self.mcp.tool()
        async def get_today(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500)
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Get todos due today. Supports response optimization via mode parameter and limit."""
            try:
                # Get raw data with optional limit
                raw_data = await self.tools.get_today(limit=limit)

                # Apply context-aware optimization if mode is specified
                if mode:
                    request_params = {'mode': mode, 'limit': limit}
                    optimized_params, _ = self.context_manager.optimize_request('get_today', request_params)
                    response_mode = ResponseMode(optimized_params.get('mode', 'standard'))  # Default to standard for Today
                    return self.context_manager.optimize_response(raw_data, 'get_today', response_mode, optimized_params)

                return raw_data
            except Exception as e:
                logger.error(f"Error getting today's todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_upcoming(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500)
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Get upcoming todos. Supports response optimization via mode parameter and limit."""
            try:
                # Get raw data with optional limit
                raw_data = await self.tools.get_upcoming(limit=limit)

                # Apply context-aware optimization if mode is specified
                if mode:
                    request_params = {'mode': mode, 'limit': limit}
                    optimized_params, _ = self.context_manager.optimize_request('get_upcoming', request_params)
                    response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                    return self.context_manager.optimize_response(raw_data, 'get_upcoming', response_mode, optimized_params)

                return raw_data
            except Exception as e:
                logger.error(f"Error getting upcoming todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_anytime(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500)
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Get todos from Anytime list. Supports response optimization via mode parameter and limit."""
            try:
                # Get raw data with optional limit
                raw_data = await self.tools.get_anytime(limit=limit)

                # Apply context-aware optimization if mode is specified
                if mode:
                    request_params = {'mode': mode, 'limit': limit}
                    optimized_params, _ = self.context_manager.optimize_request('get_anytime', request_params)
                    response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                    return self.context_manager.optimize_response(raw_data, 'get_anytime', response_mode, optimized_params)

                return raw_data
            except Exception as e:
                logger.error(f"Error getting anytime todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_someday(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500)
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Get todos from Someday list. Supports response optimization via mode parameter and limit."""
            try:
                # Get raw data with optional limit
                raw_data = await self.tools.get_someday(limit=limit)

                # Apply context-aware optimization if mode is specified
                if mode:
                    request_params = {'mode': mode, 'limit': limit}
                    optimized_params, _ = self.context_manager.optimize_request('get_someday', request_params)
                    response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                    return self.context_manager.optimize_response(raw_data, 'get_someday', response_mode, optimized_params)

                return raw_data
            except Exception as e:
                logger.error(f"Error getting someday todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_logbook(
            limit: int = Field(50, description="Maximum number of entries to return. Defaults to 50", ge=1, le=100),
            period: str = Field("7d", description="Time period to look back (e.g., '3d', '1w', '2m', '1y'). Defaults to '7d'", pattern=r"^\d+[dwmy]$")
        ) -> List[Dict[str, Any]]:
            """Get completed todos from Logbook. Supports limit (max 100) and period filters (e.g., '7d', '1w')."""
            try:
                return await self.tools.get_logbook(limit=limit, period=period)
            except Exception as e:
                logger.error(f"Error getting logbook: {e}")
                raise
        
        @self.mcp.tool()
        async def get_trash(
            limit: int = Field(50, description="Maximum number of items to return (default: 50, max: 100)", ge=1, le=100),
            offset: int = Field(0, description="Number of items to skip (default: 0)", ge=0)
        ) -> Dict[str, Any]:
            """Get trashed todos with pagination support.

            Returns a dictionary containing:
            - items: List of trashed todos
            - total_count: Total number of items in trash
            - limit: Applied limit value
            - offset: Applied offset value
            - has_more: Boolean indicating if more items are available

            Examples:
            - get_trash() - Get first 50 items
            - get_trash(limit=20) - Get first 20 items
            - get_trash(limit=50, offset=50) - Get items 51-100
            - get_trash(limit=100, offset=200) - Get items 201-300
            """
            try:
                return await self.tools.get_trash(limit=limit, offset=offset)
            except Exception as e:
                logger.error(f"Error getting trash: {e}")
                raise
        
        # Efficient date-range query tools using AppleScript 'whose' clause
        @self.mcp.tool()
        async def get_due_in_days(
            days: int = Field(30, description="Number of days ahead to check for due todos", ge=1, le=365)
        ) -> List[Dict[str, Any]]:
            """Get todos due within specified days (1-365). Uses efficient AppleScript filtering."""
            try:
                return await self.tools.get_todos_due_in_days(days)
            except Exception as e:
                logger.error(f"Error getting todos due in {days} days: {e}")
                return {"error": str(e), "todos": []}
        
        @self.mcp.tool()
        async def get_activating_in_days(
            days: int = Field(30, description="Number of days ahead to check for activating todos", ge=1, le=365)
        ) -> List[Dict[str, Any]]:
            """Get todos activating within specified days (1-365)."""
            try:
                return await self.tools.get_todos_activating_in_days(days)
            except Exception as e:
                logger.error(f"Error getting todos activating in {days} days: {e}")
                return {"error": str(e), "todos": []}
        
        @self.mcp.tool()
        async def get_upcoming_in_days(
            days: int = Field(30, description="Number of days ahead to check for upcoming todos", ge=1, le=365),
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw")
        ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
            """Get todos due or activating within specified days (1-365). Supports response modes."""
            try:
                logger.info(f"Getting todos upcoming in {days} days")
                todos = await self.tools.get_todos_upcoming_in_days(days)
                
                # Always return a properly formatted response
                if mode:
                    request_params = {'mode': mode}
                    optimized_params, _ = self.context_manager.optimize_request('get_upcoming_in_days', request_params)
                    response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                    return self.context_manager.optimize_response(todos, 'get_upcoming_in_days', response_mode, optimized_params)
                else:
                    # Return structured response even without mode
                    return {
                        "data": todos,
                        "meta": {
                            "count": len(todos),
                            "days": days
                        }
                    }
            except Exception as e:
                logger.error(f"Error getting upcoming todos in {days} days: {e}")
                # Return structured error response
                return {
                    "data": [],
                    "meta": {
                        "count": 0,
                        "days": days,
                        "error": str(e)
                    }
                }
        
        # Tag management tools
        @self.mcp.tool()
        async def get_tags(
            include_items: bool = Field(False, description="Include items list (True) or just counts (False)")
        ) -> List[Dict[str, Any]]:
            """Get all tags with item counts or full items. Use include_items=true for full item lists."""
            try:
                return await self.tools.get_tags(include_items=include_items)
            except Exception as e:
                logger.error(f"Error getting tags: {e}")
                raise
        
        @self.mcp.tool()
        async def get_tagged_items(
            tag: str = Field(..., description="Tag title to filter by")
        ) -> List[Dict[str, Any]]:
            """Get todos with a specific tag."""
            try:
                return await self.tools.get_tagged_items(tag=tag)
            except Exception as e:
                logger.error(f"Error getting tagged items: {e}")
                raise
        
        # Search tools
        @self.mcp.tool()
        async def search_todos(
            query: str = Field(..., description="Search term to look for in todo titles and notes"),
            limit: int = Field(50, description="Maximum number of results to return (1-500)", ge=1, le=500),
            mode: Optional[str] = None
        ) -> Dict[str, Any]:
            """Search todos by query term. Supports limit (1-500) and response modes for context optimization."""
            try:
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return {
                        "success": False,
                        "error": "Invalid mode",
                        "message": f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}"
                    }
                
                # Prepare request parameters
                request_params = {
                    'query': query,
                    'limit': limit,
                    'mode': mode
                }
                
                # Apply smart defaults and optimization
                optimized_params, was_modified = self.context_manager.optimize_request('search_todos', request_params)
                
                # Extract optimized parameters
                final_limit = optimized_params.get('limit', 50)
                response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                
                # Get raw data from tools layer
                raw_data = await self.tools.search_todos(query=query, limit=final_limit)
                
                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'search_todos', response_mode, optimized_params
                )
                
                # Add minimal optimization metadata
                if was_modified:
                    optimized_response['optimized'] = True
                
                return optimized_response
                
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
            limit: int = Field(50, description="Maximum number of results to return (1-500)", ge=1, le=500),
            mode: Optional[str] = None
        ) -> Dict[str, Any]:
            """Advanced search with multiple filters: status, type, tag, area, start_date, deadline. Supports response modes and limit (1-500) for efficient retrieval."""
            try:
                # Import datetime for validation
                from datetime import datetime
                
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return {
                        "success": False,
                        "error": "Invalid mode",
                        "message": f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}",
                        "valid_modes": ["auto", "summary", "minimal", "standard", "detailed", "raw"]
                    }
                
                # Validate date formats
                if start_date:
                    try:
                        datetime.strptime(start_date, '%Y-%m-%d')
                    except ValueError:
                        return {
                            "success": False,
                            "error": "Invalid start_date format",
                            "message": f"start_date must be in YYYY-MM-DD format. Got: {start_date}",
                            "example": "2024-12-25"
                        }
                
                if deadline:
                    try:
                        datetime.strptime(deadline, '%Y-%m-%d')
                    except ValueError:
                        return {
                            "success": False,
                            "error": "Invalid deadline format",
                            "message": f"deadline must be in YYYY-MM-DD format. Got: {deadline}",
                            "example": "2024-12-31"
                        }
                
                # Prepare request parameters
                request_params = {
                    'status': status,
                    'type': type,
                    'tag': tag,
                    'area': area,
                    'start_date': start_date,
                    'deadline': deadline,
                    'limit': limit,
                    'mode': mode
                }
                
                # Apply smart defaults and optimization
                optimized_params, was_modified = self.context_manager.optimize_request('search_advanced', request_params)
                
                # Extract optimized parameters
                final_limit = optimized_params.get('limit', 50)
                response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                
                # Get raw data from tools layer
                raw_data = await self.tools.search_advanced(
                    status=status,
                    type=type,
                    tag=tag,
                    area=area,
                    start_date=start_date,
                    deadline=deadline,
                    limit=final_limit
                )
                
                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'search_advanced', response_mode, optimized_params
                )
                
                # Add minimal optimization metadata
                if was_modified:
                    optimized_response['optimized'] = True
                
                return optimized_response
                
            except Exception as e:
                logger.error(f"Error in advanced search: {e}")
                raise
        
        @self.mcp.tool()
        async def get_recent(
            period: str = Field(..., description="Time period (e.g., '3d', '1w', '2m', '1y')", pattern=r"^\d+[dwmy]$")
        ) -> List[Dict[str, Any]]:
            """Get recently created items within a time period (e.g., '3d', '1w')."""
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
            """Add tags to a todo. Only existing tags can be applied."""
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
        # Empty request model for compatibility
        class HealthCheckRequest(BaseModel):
            """Empty request model - health_check takes no parameters."""
            pass

        @self.mcp.tool()
        async def health_check(request: Optional[HealthCheckRequest] = None) -> Dict[str, Any]:
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

        # Queue status tool
        class QueueStatusRequest(BaseModel):
            """Empty request model - queue_status takes no parameters."""
            pass

        @self.mcp.tool()
        async def queue_status(request: Optional[QueueStatusRequest] = None) -> Dict[str, Any]:
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
        
        # Context stats tool
        class ContextStatsRequest(BaseModel):
            """Empty request model - context_stats takes no parameters."""
            pass

        @self.mcp.tool()
        async def context_stats(request: Optional[ContextStatsRequest] = None) -> Dict[str, Any]:
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

        # Server capabilities tool
        class ServerCapabilitiesRequest(BaseModel):
            """Empty request model - get_server_capabilities takes no parameters."""
            pass

        @self.mcp.tool()
        async def get_server_capabilities(request: Optional[ServerCapabilitiesRequest] = None) -> Dict[str, Any]:
            """Get server capabilities, features, API coverage, and optimization settings. Returns structured information about available tools, response modes, and performance characteristics."""
            try:
                capabilities = {
                    "server_info": {
                        "name": "Things 3 MCP Server",
                        "version": __version__,
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
                        "advanced_features": ["bulk_ops", "context_optimization"]
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
            """Get usage recommendations for efficient MCP operations. Optionally specify an operation name for targeted guidance."""
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
                            "pre_check": "Use get_todos(mode='minimal') to verify IDs",
                            "progress_monitoring": "Check queue_status() during operation",
                            "estimated_time_per_item": "0.5-1 seconds",
                            "note": "Scheduling handled automatically based on destination"
                        }
                    
                    elif operation == "add_todo":
                        existing_tags = []
                        try:
                            existing_tags = await self.tools.get_tags(False)
                            tag_count = len(existing_tags)
                        except Exception as e:
                            logger.warning(f"Failed to retrieve existing tags for recommendations: {e}")
                            tag_count = 0
                        
                        recommendations[operation] = {
                            "tag_strategy": "Use existing tags only" if not self.config.ai_can_create_tags else "Can create new tags",
                            "available_tags_count": tag_count,
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
        
        # NOTE: Natural language query tools removed - too complex to implement reliably
        # The Things API doesn't provide proper date fields for most todos,
        # making date-based queries unreliable. Consider using get_today(), 
        # get_upcoming(), get_logbook() instead for specific time-based queries.

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
    server = ThingsMCPServer(env_file=config_path)
    server.run()


if __name__ == "__main__":
    main()