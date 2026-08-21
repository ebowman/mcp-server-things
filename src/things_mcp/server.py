"""Simple FastMCP 3.x server implementation for Things 3 integration."""

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
from .boot_trace import boot_marker
from .services.applescript_manager import AppleScriptManager
from .tools import ThingsTools
from .tools_helpers.read_operations import read_error as _tools_read_error
from .tools_helpers.errors import write_error as _tools_write_error
from .operation_queue import shutdown_operation_queue, get_operation_queue
from .config import ThingsMCPConfig, load_config_from_env
from .context_manager import ContextAwareResponseManager, ResponseMode
# from .query_engine import NaturalLanguageQueryEngine  # Removed - too complex

logger = logging.getLogger(__name__)


def _parse_tag_list(tags: Optional[str]) -> Optional[List[str]]:
    """Parse a comma-separated tag string into a list of non-empty, stripped tag names.

    Args:
        tags: Comma-separated tag names (e.g. "work,urgent" or "a, ,b").

    Returns:
        A list of non-empty, stripped tag names, or None if `tags` is falsy or
        contains no non-empty entries after stripping (e.g. None, "", " , ").
    """
    if not tags:
        return None
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    return tag_list or None


class _StrictBoolError(ValueError):
    """Raised by `_parse_strict_bool` when a value is not 'true'/'false'.

    Carries `field` and `message` so callers can build a structured
    VALIDATION_ERROR response matching
    `parameter_validator.create_validation_error_response`'s shape.
    """

    def __init__(self, field: str, value: Any):
        self.field = field
        self.value = value
        self.message = (
            f"must be 'true' or 'false' (case-insensitive), got '{value}'"
        )
        super().__init__(f"{field}: {self.message}")


def _parse_strict_bool(value: Optional[Union[str, bool]], field_name: str) -> Optional[bool]:
    """Strictly parse a completed/canceled parameter to bool or None.

    Unlike the historical `value.lower() == 'true'` pattern (which silently
    turns any non-'true' string - including typos like 'yes'/'1' - into
    False and can unintentionally reopen a completed/canceled item), this
    only accepts an actual bool, or the strings 'true'/'false'
    (case-insensitive, surrounding whitespace stripped). Anything else
    raises `_StrictBoolError` so the caller can return a structured
    VALIDATION_ERROR instead of guessing.

    Args:
        value: None (leave unchanged), a bool, or a 'true'/'false' string.
        field_name: Name of the field, used in the raised error.

    Returns:
        True, False, or None if `value` is None.

    Raises:
        _StrictBoolError: If `value` is a non-bool, non-'true'/'false' string,
            or any other type (e.g. int).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == 'true':
            return True
        if lowered == 'false':
            return False
    raise _StrictBoolError(field_name, value)


def _parse_tag_list_for_update(tags: Optional[str]) -> Optional[List[str]]:
    """Parse a comma-separated tag string for update_todo/update_project/update_area/
    bulk_update_todos, preserving the "clear all tags" signal.

    Unlike `_parse_tag_list`, an explicit empty string (or a string that is
    only commas/whitespace, e.g. " , ") is treated as a request to clear all
    tags and returns `[]` rather than `None`. `None` (the field omitted
    entirely) still means "leave tags unchanged".

    Args:
        tags: Comma-separated tag names, "" to clear, or None to leave unchanged.

    Returns:
        A list of non-empty, stripped tag names; `[]` if `tags` was an
        explicit (post-strip) empty string; or `None` if `tags` was `None`.
    """
    if tags is None:
        return None
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    return tag_list


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
        boot_marker("config-loaded")

        # Configure logging based on config
        self._configure_logging()
        boot_marker("logging-configured")

        # Advisory, best-effort tip for legacy launch paths (console-script
        # alias / src-layout PYTHONPATH checkout) pointing at the upgrade
        # guide. Emitted here (once, at INFO) rather than earlier because it
        # must only run on the actual server-start path (not doctor/config/
        # --version) and only after logging is configured. Deferred import
        # to avoid a circular import with main.py (which imports this module).
        try:
            from .main import _legacy_launch_notice
            notice = _legacy_launch_notice()
            if notice:
                logger.info(notice)
        except Exception:
            # Must never affect server startup.
            pass

        self.applescript_manager = AppleScriptManager()
        boot_marker("applescript-manager-ready")
        self.tools = ThingsTools(self.applescript_manager, self.config)
        self.context_manager = ContextAwareResponseManager()
        # self.query_engine = NaturalLanguageQueryEngine(self.tools)  # Removed - too complex
        self._register_tools()
        boot_marker("tools-registered")
        self._register_shutdown_handlers()
        logger.info("Things MCP Server initialized with context-aware response management and tag validation support")

    def _process_checklist_items(self, checklist_items_str: str) -> list:
        """Process checklist items string, handling escape sequences from MCP protocol.

        Args:
            checklist_items_str: String with newline-separated items (may contain \\n escape sequences)

        Returns:
            List of individual checklist item strings
        """
        logger.debug(f"Processing checklist input: {repr(checklist_items_str)}")
        logger.debug(f"Raw bytes: {checklist_items_str.encode('unicode_escape').decode('ascii')}")

        # Replace escaped newlines with actual newlines
        processed = checklist_items_str.replace('\\n', '\n')
        logger.debug(f"After replace: {repr(processed)}")

        # Split on newlines
        items = [item.strip() for item in processed.split('\n') if item.strip()]
        logger.debug(f"Split into {len(items)} items: {items}")

        return items

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
    
    async def _registered_tool_count(self) -> int:
        """Return the number of tools currently registered with the MCP server.

        Computed at runtime from the FastMCP tool registry so this value never
        drifts from the actual set of registered tools. Falls back defensively
        if the registry call fails for any reason.
        """
        try:
            tools = await self.mcp.list_tools()
            return len(tools)
        except Exception as e:
            logger.debug(f"Failed to compute registered tool count from FastMCP registry: {e}")
            return 0

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
                    return self._read_error(
                        "invalid_mode",
                        f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}",
                    )

                # Normalize status parameter (MCP may pass string "None")
                if status == "None" or status == "null":
                    status = None

                # Validate status parameter
                if status is not None and status not in ["incomplete", "completed", "canceled"]:
                    return self._read_error(
                        "invalid_status",
                        f"Status must be one of: 'incomplete', 'completed', 'canceled', or None for all. Got: {status}",
                    )

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
                            return self._read_error(
                                "invalid_limit",
                                f"Limit must be between 1 and 500, got {actual_limit}",
                            )
                    except (ValueError, TypeError) as e:
                        return self._read_error(
                            "invalid_limit",
                            f"Limit must be a number between 1 and 500, got '{limit}'",
                        )

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

                # Defense in depth: _get_todos_sync also validates status and
                # returns a structured error dict for values that somehow slip
                # past the pre-validation above (e.g. a direct/non-MCP caller
                # of the tools layer). Surface it as-is, same pattern as
                # search_todos's "Invalid status" short-circuit.
                if isinstance(raw_data, dict):
                    return raw_data

                # Track pre-limit total, then apply limit if specified
                pre_limit_total = len(raw_data)
                if final_limit and len(raw_data) > final_limit:
                    raw_data = raw_data[:final_limit]

                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'get_todos', response_mode, optimized_params
                )

                # Add minimal optimization metadata
                if was_modified:
                    optimized_response['optimized'] = True

                return self._read_result(
                    optimized_response,
                    mode=response_mode.value,
                    limit=final_limit,
                    total=pre_limit_total,
                )

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
                return self._write_error(
                    "TAG_CREATION_RESTRICTED",
                    "This system is configured to require manual tag creation by users. This helps maintain a clean and intentional tag structure.",
                    user_action=f"Please ask the user if they would like to create the tag '{tag_name}'",
                    existing_tags_hint="You can use get_tags to show the user existing tags they can use instead."
                )

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
                        return self._write_error(
                            "TAG_CREATION_FAILED",
                            "Tag creation failed",
                            details=errors[0] if errors else f"Failed to create tag '{tag_name}'"
                        )
                else:
                    # Fallback if no validation service
                    return self._write_error(
                        "TAG_VALIDATION_SERVICE_UNAVAILABLE",
                        "Cannot create tags without validation service"
                    )
            except Exception as e:
                logger.error(f"Error creating tag: {e}")
                return self._write_error(
                    "APPLESCRIPT_ERROR",
                    "An error occurred while creating the tag",
                    details=str(e)
                )

        @self.mcp.tool()
        async def add_todo(
            title: str = Field(..., min_length=1, description="Title of the todo"),
            notes: Optional[str] = Field(None, description="Notes for the todo"),
            tags: Optional[str] = Field(None, description="Comma-separated tags (only existing tags applied)"),
            when: Optional[str] = Field(None, description="Schedule date/time: 'today', 'tomorrow', 'evening' (alias 'tonight', schedules for This Evening), 'someday', 'anytime', or a date (e.g., '2024-12-25', '2024-12-25@14:30')"),
            deadline: Optional[str] = Field(None, description="Deadline for the todo. Must be YYYY-MM-DD - relative keywords like 'today' are rejected"),
            list_id: Optional[str] = Field(None, description="ID of project/area to add to"),
            list_title: Optional[str] = Field(None, description="Title of project/area to add to"),
            heading: Optional[str] = Field(None, description="Heading to add under"),
            checklist_items: Optional[List[str]] = Field(None, description="List of checklist items to add")
        ) -> Dict[str, Any]:
            """Create a new todo. Supports scheduling (when='today', 'tomorrow', 'YYYY-MM-DD'), tags, projects, deadlines, and notes."""
            try:
                # Validate date parameters. Whitespace-only when (e.g. '   ')
                # must be rejected explicitly here: validate_date_format()
                # strips and returns None for it, which would otherwise be
                # silently treated as "no schedule requested" instead of a
                # rejection (hq-f0w.34).
                if isinstance(when, str) and when.strip() == '' and when != '':
                    return {
                        "success": False,
                        "error": "VALIDATION_ERROR",
                        "field": "when",
                        "message": "use when='anytime' or when='someday' to unschedule",
                        "invalid_value": when
                    }

                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        when = ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return self._write_error("INVALID_WHEN", str(e), field="when")

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return self._write_error("INVALID_DEADLINE", str(e), field="deadline")

                # Convert comma-separated tags to list
                tag_list = _parse_tag_list(tags)
                result = await self.tools.add_todo(
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    list_id=list_id,
                    list_title=list_title,
                    heading=heading,
                    checklist_items=checklist_items
                )
                
                # Enhance response with tag validation feedback if available
                if (tag_list and self.tools.tag_validation_service and 
                    hasattr(result, 'get') and result.get('success')):
                    # Get tag validation info from the result
                    if 'tag_info' in result:
                        tag_info = result['tag_info']
                        if tag_info.get('created'):
                            result['message'] = result.get('message', '') + f" Created new tags: {', '.join(tag_info['created'])}"
                        if tag_info.get('filtered'):
                            result['message'] = result.get('message', '') + f" Filtered tags: {', '.join(tag_info['filtered'])}"
                        if tag_info.get('warnings'):
                            result['tag_warnings'] = tag_info['warnings']
                
                return result
            except Exception as e:
                logger.error(f"Error adding todo: {e}")
                raise
        
        @self.mcp.tool()
        async def update_todo(
            id: str = Field(..., description="ID of the todo to update"),
            title: Optional[str] = Field(None, description="New title. Omit to leave unchanged; '' is rejected (titles cannot be cleared)"),
            notes: Optional[str] = Field(None, description="New notes. Omit to leave unchanged; pass '' to clear existing notes"),
            tags: Optional[str] = Field(None, description="Comma-separated new tags (replaces existing tags). Omit to leave unchanged; pass '' to clear all tags"),
            when: Optional[str] = Field(None, description="Schedule date/time: 'today', 'tomorrow', 'evening' (alias 'tonight', schedules for This Evening; requires the Things URL-scheme auth token, see hint below), 'someday', 'anytime', or a date (e.g., '2024-12-25@14:30'). Omit to leave unchanged; '' is rejected - use 'anytime' or 'someday' to unschedule"),
            deadline: Optional[str] = Field(None, description="New deadline. Must be YYYY-MM-DD - relative keywords like 'today' are rejected. Omit to leave unchanged; pass '' to clear the existing deadline"),
            completed: Optional[str] = Field(None, description="Mark as completed (true/false)"),
            canceled: Optional[str] = Field(None, description="Mark as canceled (true/false)"),
            heading: Optional[str] = Field(None, description="Move the to-do under this heading (within its current project, or list_id's/list_title's project if also given). Requires the Things URL-scheme auth token (see README/CLAUDE.md 'Things URL-scheme auth token') - fails fast with a structured error and hint if not configured. Cannot be cleared with ''; '' is rejected"),
            list_id: Optional[str] = Field(None, description="Project or area ID to move the to-do into. Combined with heading, moves + places under that heading in one call via the Things URL scheme. Without heading, moves the to-do directly into that project/area via AppleScript ('project id'/'area id') - cannot target inbox/today/anytime/someday (use move_record for those). Takes precedence over list_title if both are given"),
            list_title: Optional[str] = Field(None, description="Project or area title to move the to-do into (resolved to an id the same way as add_todo's list_title). Only consulted when list_id is not given. Works the same whether or not heading is also given - resolved and used as the move target either way. Errors if the title matches zero or more than one project/area")
        ) -> Dict[str, Any]:
            """Update an existing todo. Supports partial updates to any field including status, scheduling, tags, and content.

            A successful response includes ``todo_id`` and ``verified``.
            When verified is true, ``item`` is the final state returned by
            ``get_todo_by_id``. If readback fails after the write, success
            remains true, verified is false, and ``verification_error`` plus
            a warning explain that callers must not retry automatically.

            Status semantics for completed/canceled (identical across update_todo,
            bulk_update_todos, and update_project - see CLAUDE.md for the full 3x3
            table): canceled='true' always wins regardless of completed (e.g.
            completed='false', canceled='true' results in canceled). Whenever
            canceled is not 'true', completed (if given) decides the result:
            'true' -> completed, 'false' -> open. canceled='false' alone (with
            completed omitted) also reopens the todo - this is NOT a no-op.
            Omitting both leaves status unchanged. completed/canceled only accept
            the strings 'true'/'false' (case-insensitive) - any other value (e.g.
            'yes', '1') is rejected with a structured VALIDATION_ERROR rather than
            being silently coerced to False.

            Clear-field semantics for partial updates: a field left at its
            default (None/omitted) leaves the existing value unchanged.
            Passing notes='' or deadline='' clears that field. Passing
            tags='' clears all tags. title='' is rejected with a validation
            error (titles cannot be cleared). when='' is also rejected -
            use when='anytime' or when='someday' to unschedule instead.

            list_id/list_title move the to-do into a project or area.
            Without heading, this happens via AppleScript in the same write
            as the other AppleScript-only fields (title/notes/tags/etc.) -
            it can move a to-do INTO a project or area but CANNOT place it
            in the inbox/today/anytime/someday lists; use move_record() for
            those destinations. With heading also given, the move instead
            happens via the Things URL scheme together with the
            heading placement (see below). list_id takes precedence over
            list_title if both are given; an unresolvable list_id/list_title
            (unknown id, or a title matching zero or more than one
            project/area) is a structured error and no field in the same
            call is applied.

            heading moves the to-do under that heading via the Things URL
            scheme (things:///update) - AppleScript cannot do this. It
            requires the Things auth token to be configured; without one
            this returns {"success": False, "error": "...", "hint": "..."}
            and no field (including title/notes/tags/etc. in the same call)
            is applied. heading='' is rejected (no way to clear a heading
            via update). The heading must already exist in the target
            project or Things silently ignores it (ends up in the project,
            not under the heading) - a warning is returned when the heading
            could not be confirmed to exist. If the to-do has no project and
            neither list_id nor list_title is also given, a warning is
            returned (URL-scheme 'heading' has no effect without a
            project).

            when='evening' (alias 'tonight') schedules the to-do for This
            Evening. Like heading, this is only possible via the Things URL
            scheme (things:///update) and requires the Things auth token to
            be configured; without one this returns {"success": False,
            "error": "...", "hint": "..."} and no field in the same call is
            applied. If the token IS configured and when='evening' is
            combined with other fields (title/notes/tags/deadline/etc.) in
            the same call, those AppleScript-only fields are applied FIRST,
            then the URL-scheme evening schedule is applied second - if
            that second URL-scheme call itself fails, the already-applied
            fields are NOT rolled back (same ordering/caveat as heading).
            when='evening' combined with list_id/list_title but NO heading
            moves the to-do via the AppleScript write only (first field
            group above) - list_id/list_title is not also sent on the
            evening URL-scheme call, since that would re-apply the same
            move a second time.
            """
            try:
                # Validate date parameters. Empty strings ('') are clear/reject
                # requests handled by ParameterValidator.validate_update_params
                # downstream (in self.tools.update_todo), not here. Whitespace-
                # only when (e.g. '   ') is truthy so it would otherwise reach
                # validate_date_format() below, which strips and returns None
                # for it - silently treating the request as "no change"
                # instead of rejecting it the same way '' is rejected
                # downstream. Reject it explicitly here instead (hq-f0w.34).
                if isinstance(when, str) and when.strip() == '' and when != '':
                    return {
                        "success": False,
                        "error": "VALIDATION_ERROR",
                        "field": "when",
                        "message": "use when='anytime' or when='someday' to unschedule",
                        "invalid_value": when
                    }

                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        when = ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return self._write_error("INVALID_WHEN", str(e), field="when")

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return self._write_error("INVALID_DEADLINE", str(e), field="deadline")

                # Convert comma-separated tags to list. '' clears all tags,
                # None (tags not provided) leaves tags unchanged.
                tag_list = _parse_tag_list_for_update(tags)

                # Strictly parse completed/canceled: only an actual bool or
                # the strings 'true'/'false' (case-insensitive) are accepted;
                # anything else (e.g. 'yes', '1') is a structured error
                # rather than silently becoming False and reopening the todo.
                try:
                    completed_bool = _parse_strict_bool(completed, 'completed')
                    canceled_bool = _parse_strict_bool(canceled, 'canceled')
                except _StrictBoolError as e:
                    return {
                        "success": False,
                        "error": "VALIDATION_ERROR",
                        "field": e.field,
                        "message": e.message
                    }

                result = await self.tools.update_todo(
                    todo_id=id,
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    completed=completed_bool,
                    canceled=canceled_bool,
                    heading=heading,
                    list_id=list_id,
                    list_title=list_title
                )

                # Enhance response with tag validation feedback if available
                if (tag_list and self.tools.tag_validation_service and
                    hasattr(result, 'get') and result.get('success')):
                    # Get tag validation info from the result
                    if 'tag_info' in result:
                        tag_info = result['tag_info']
                        if tag_info.get('created'):
                            result['message'] = result.get('message', '') + f" Created new tags: {', '.join(tag_info['created'])}"
                        if tag_info.get('filtered'):
                            result['message'] = result.get('message', '') + f" Filtered tags: {', '.join(tag_info['filtered'])}"
                        if tag_info.get('warnings'):
                            result['tag_warnings'] = tag_info['warnings']

                return await self._todo_write_receipt(id, result)
            except Exception as e:
                logger.error(f"Error updating todo: {e}")
                raise

        @self.mcp.tool()
        async def bulk_update_todos(
            todo_ids: str = Field(..., description="Comma-separated list of todo IDs to update"),
            title: Optional[str] = Field(None, description="New title for all todos. Omit to leave unchanged; '' is rejected (titles cannot be cleared)"),
            notes: Optional[str] = Field(None, description="New notes for all todos. Omit to leave unchanged; pass '' to clear notes on all todos"),
            tags: Optional[str] = Field(None, description="Comma-separated tags to apply to all todos (replaces existing tags). Omit to leave unchanged; pass '' to clear all tags on all todos"),
            when: Optional[str] = Field(None, description="Schedule date: 'today', 'tomorrow', 'evening' (alias 'tonight', schedules for This Evening; requires the Things URL-scheme auth token), 'someday', 'anytime', or a date (e.g., '2024-12-25'). Omit to leave unchanged; '' is rejected - use 'anytime' or 'someday' to unschedule"),
            deadline: Optional[str] = Field(None, description="New deadline for all todos. Must be YYYY-MM-DD - relative keywords like 'today' are rejected. Omit to leave unchanged; pass '' to clear the deadline on all todos"),
            completed: Optional[str] = Field(None, description="Mark all as completed (true/false)"),
            canceled: Optional[str] = Field(None, description="Mark all as canceled (true/false)")
        ) -> Dict[str, Any]:
            """Update multiple todos with the same changes in a single operation.

            Status semantics for completed/canceled (identical across update_todo,
            bulk_update_todos, and update_project - see CLAUDE.md for the full 3x3
            table): canceled='true' always wins regardless of completed (e.g.
            completed='false', canceled='true' results in canceled for every
            todo). Whenever canceled is not 'true', completed (if given) decides
            the result: 'true' -> completed, 'false' -> open. canceled='false'
            alone (with completed omitted) also reopens every todo - this is NOT
            a no-op. Omitting both leaves status unchanged. completed/canceled
            only accept the strings 'true'/'false' (case-insensitive) - any
            other value (e.g. 'yes', '1') is rejected with a structured
            VALIDATION_ERROR rather than being silently coerced to False.

            Clear-field semantics for partial updates (same contract as
            update_todo): a field left at its default (None/omitted) leaves
            the existing value unchanged for every todo. Passing notes=''
            or deadline='' clears that field. Passing tags='' clears all
            tags. title='' is rejected with a validation error (titles
            cannot be cleared). when='' is also rejected - use
            when='anytime' or when='someday' to unschedule instead.
            when='evening' (alias 'tonight') schedules every todo for This
            Evening via the Things URL scheme and requires the Things auth
            token to be configured; without one this returns
            {"success": False, "error": "...", "hint": "..."} and no field
            is applied to any todo. If the token IS configured, other
            fields (title/notes/tags/deadline/etc.) are applied to each
            todo via AppleScript FIRST, then the URL-scheme evening
            schedule is applied second per todo - if the evening
            scheduling call fails for a given todo, the other fields
            already applied to that todo are NOT rolled back.
            """
            try:
                # Validate date parameters. Empty strings ('') are clear/reject
                # requests handled by ParameterValidator.validate_update_params
                # downstream (in self.tools.bulk_update_todos), not here.
                # Whitespace-only when (e.g. '   ') is truthy so it would
                # otherwise reach validate_date_format() below, which strips
                # and returns None for it - silently treating the request as
                # "no change" instead of rejecting it the same way '' is
                # rejected downstream. Reject it explicitly here instead
                # (hq-f0w.34).
                if isinstance(when, str) and when.strip() == '' and when != '':
                    return {
                        "success": False,
                        "error": "VALIDATION_ERROR",
                        "field": "when",
                        "message": "use when='anytime' or when='someday' to unschedule",
                        "invalid_value": when
                    }

                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        when = ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return self._write_error("INVALID_WHEN", str(e), field="when")

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return self._write_error("INVALID_DEADLINE", str(e), field="deadline")

                # Parse comma-separated IDs
                id_list = [id.strip() for id in todo_ids.split(",") if id.strip()]

                if not id_list:
                    return self._write_error("NO_TODO_IDS", "No valid todo IDs provided", updated_count=0)

                # Convert comma-separated tags to list. '' clears all tags,
                # None (tags not provided) leaves tags unchanged.
                tag_list = _parse_tag_list_for_update(tags)

                # Strictly parse completed/canceled: only an actual bool or
                # the strings 'true'/'false' (case-insensitive) are accepted;
                # anything else (e.g. 'yes', '1') is a structured error
                # rather than silently becoming False and reopening the todos.
                try:
                    completed_bool = _parse_strict_bool(completed, 'completed')
                    canceled_bool = _parse_strict_bool(canceled, 'canceled')
                except _StrictBoolError as e:
                    return {
                        "success": False,
                        "error": "VALIDATION_ERROR",
                        "field": e.field,
                        "message": e.message,
                        "updated_count": 0
                    }

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
                return self._write_error(
                    "APPLESCRIPT_ERROR", "Failed to perform bulk update",
                    details=str(e), updated_count=0
                )

        @self.mcp.tool()
        async def add_checklist_items(
            todo_id: str = Field(..., description="ID of the todo to add checklist items to"),
            items: List[str] = Field(..., description="List of checklist items to add")
        ) -> Dict[str, Any]:
            """Add checklist items to an existing todo. Items will be appended to the end of the existing checklist.

            Requires a Things URL-scheme auth token (Things: Settings > General >
            Enable Things URLs > Manage; save it to .things-auth, things-auth.txt,
            or ~/.things-auth). Without a configured token this returns
            success=false with an actionable error instead of silently no-op'ing.
            """
            try:
                if not items:
                    return self._write_error("NO_CHECKLIST_ITEMS", "At least one checklist item is required")

                result = await self.tools.add_checklist_items(todo_id=todo_id, items=items)
                return result
            except Exception as e:
                logger.error(f"Error adding checklist items: {e}")
                raise

        @self.mcp.tool()
        async def prepend_checklist_items(
            todo_id: str = Field(..., description="ID of the todo to prepend checklist items to"),
            items: List[str] = Field(..., description="List of checklist items to prepend")
        ) -> Dict[str, Any]:
            """Prepend checklist items to an existing todo. Items will be added at the beginning of the existing checklist.

            Requires a Things URL-scheme auth token (Things: Settings > General >
            Enable Things URLs > Manage; save it to .things-auth, things-auth.txt,
            or ~/.things-auth). Without a configured token this returns
            success=false with an actionable error instead of silently no-op'ing.
            """
            try:
                if not items:
                    return self._write_error("NO_CHECKLIST_ITEMS", "At least one checklist item is required")

                result = await self.tools.prepend_checklist_items(todo_id=todo_id, items=items)
                return result
            except Exception as e:
                logger.error(f"Error prepending checklist items: {e}")
                raise

        @self.mcp.tool()
        async def replace_checklist_items(
            todo_id: str = Field(..., description="ID of the todo to replace checklist items in"),
            items: List[str] = Field(..., description="List of checklist items to replace with (empty list to clear all)")
        ) -> Dict[str, Any]:
            """Replace all checklist items in a todo. This will remove all existing checklist items and replace them with the provided items.

            Requires a Things URL-scheme auth token (Things: Settings > General >
            Enable Things URLs > Manage; save it to .things-auth, things-auth.txt,
            or ~/.things-auth). Without a configured token this returns
            success=false with an actionable error instead of silently no-op'ing.
            """
            try:
                result = await self.tools.replace_checklist_items(todo_id=todo_id, items=items)
                return result
            except Exception as e:
                logger.error(f"Error replacing checklist items: {e}")
                raise

        @self.mcp.tool()
        async def get_todo_by_id(
            todo_id: str = Field(..., description="ID of the todo to retrieve")
        ) -> Dict[str, Any]:
            """Get a specific Things item by its ID.

            Resolves any Things item id, not just to-dos - projects, headings,
            and areas resolve too. The returned item's `type` field
            ('to-do', 'heading', 'project', or 'area') tells you which kind
            it is. Trashed items also resolve, with `trashed: true` included
            in the result.

            A tag id returns the canonical structured error at the top level
            (`{"success": false, "error": "invalid_type", "message": ...}`,
            not nested under `item`) instead of an item - a tag is a label,
            not a retrievable item; use `get_tags()` or `get_tagged_items()`
            for tags. An id that does not exist at all raises an error.
            """
            try:
                todo = await self.tools.get_todo_by_id(todo_id)
                if isinstance(todo, dict) and todo.get('success') is False:
                    return todo
                return {"item": todo}
            except Exception as e:
                logger.error(f"Error getting todo by ID: {e}")
                raise
        
        @self.mcp.tool()
        async def delete_todo(
            todo_id: str = Field(..., description="ID of the todo or project to delete")
        ) -> Dict[str, Any]:
            """Trash a to-do or project by ID (moves it to Things' Trash, not a permanent delete).

            Works for both to-do ids and project ids - the type is
            auto-detected so the right AppleScript delete form is used
            (Things' AppleScript dictionary does not accept a project id
            where a to-do id is expected, and vice versa). Headings, areas,
            and tags cannot be deleted via this tool (Things' AppleScript
            dictionary has no delete support for them); those ids return a
            structured `not_deletable` error explaining what to use instead
            - delete them manually in the Things UI.
            """
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
            """Move a todo to a different list, project, or area.

            A successful response includes ``todo_id`` and ``verified``.
            When verified is true, ``item`` is the final state returned by
            ``get_todo_by_id``. If readback fails after the write, success
            remains true, verified is false, and ``verification_error`` plus
            a warning explain that callers must not retry automatically.
            """
            try:
                result = await self.tools.move_record(
                    todo_id=todo_id, destination_list=destination_list
                )
                return await self._todo_write_receipt(todo_id, result)
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
                    return self._read_error(
                        "invalid_mode",
                        f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}",
                    )

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

                return self._read_result(
                    optimized_response,
                    mode=response_mode.value,
                    total=len(raw_data),
                )
            except Exception as e:
                logger.error(f"Error getting projects: {e}")
                raise
        
        @self.mcp.tool()
        async def add_project(
            title: str = Field(..., min_length=1, description="Title of the project"),
            notes: Optional[str] = Field(None, description="Notes for the project"),
            tags: Optional[str] = Field(None, description="Comma-separated tags to apply to the project"),
            when: Optional[str] = Field(None, description="Schedule date/time: 'today', 'tomorrow', 'someday', 'anytime', or a date (e.g., '2024-12-25@14:30'). 'evening'/'tonight' is not supported for projects - Things has no This Evening concept for projects"),
            deadline: Optional[str] = Field(None, description="Deadline for the project. Must be YYYY-MM-DD - relative keywords like 'today' are rejected"),
            area_id: Optional[str] = Field(None, description="ID of area to add to"),
            area_title: Optional[str] = Field(None, description="Title of area to add to"),
            todos: Optional[str] = Field(None, description="Newline-separated initial todos to create in the project. A line prefixed with '##' (e.g. '##Phase 1') creates a real heading instead of a to-do, and subsequent lines nest under the most recently seen heading; any '##' line routes the whole call through the Things URL scheme instead of the faster AppleScript-only path")
        ) -> Dict[str, Any]:
            """Create a new project. Supports areas, deadlines, tags, initial todos (optionally organized under '##'-prefixed headings), and scheduling. The response includes todos_created (and headings_created, when requested) so callers can confirm every requested line was actually created."""
            try:
                # Validate date parameters. Whitespace-only when (e.g. '   ')
                # must be rejected explicitly here: validate_date_format()
                # strips and returns None for it, which would otherwise be
                # silently treated as "no schedule requested" instead of a
                # rejection (hq-f0w.34).
                if isinstance(when, str) and when.strip() == '' and when != '':
                    return {
                        "success": False,
                        "error": "VALIDATION_ERROR",
                        "field": "when",
                        "message": "use when='anytime' or when='someday' to unschedule",
                        "invalid_value": when
                    }

                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        when = ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return self._write_error("INVALID_WHEN", str(e), field="when")

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return self._write_error("INVALID_DEADLINE", str(e), field="deadline")

                # Convert comma-separated tags to list
                tag_list = _parse_tag_list(tags)
                # Convert newline-separated todos to list
                todos_list = [todo.strip() for todo in todos.split("\n")] if todos else None
                return await self.tools.add_project(
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    area_id=area_id,
                    area_title=area_title,
                    todos=todos_list
                )
            except Exception as e:
                logger.error(f"Error adding project: {e}")
                raise
        
        @self.mcp.tool()
        async def update_project(
            id: str = Field(..., description="ID of the project to update"),
            title: Optional[str] = Field(None, description="New title. Omit to leave unchanged; '' is rejected (titles cannot be cleared)"),
            notes: Optional[str] = Field(None, description="New notes. Omit to leave unchanged; pass '' to clear existing notes"),
            tags: Optional[str] = Field(None, description="Comma-separated new tags (replaces existing tags). Omit to leave unchanged; pass '' to clear all tags"),
            when: Optional[str] = Field(None, description="Schedule date/time: 'today', 'tomorrow', 'someday', 'anytime', or a date (e.g., '2024-12-25@14:30'). 'evening'/'tonight' is not supported for projects - Things has no This Evening concept for projects. Omit to leave unchanged; '' is rejected - use 'anytime' or 'someday' to unschedule"),
            deadline: Optional[str] = Field(None, description="New deadline. Must be YYYY-MM-DD - relative keywords like 'today' are rejected. Omit to leave unchanged; pass '' to clear the existing deadline"),
            area_id: Optional[str] = Field(None, description="ID of area to move to"),
            area_title: Optional[str] = Field(None, description="Title of area to move to"),
            completed: Optional[str] = Field(None, description="Mark as completed (true/false)"),
            canceled: Optional[str] = Field(None, description="Mark as canceled (true/false)")
        ) -> Dict[str, Any]:
            """Update an existing project. Supports partial updates to any field including status, scheduling, tags, and content.

            Status semantics for completed/canceled (identical across update_todo,
            bulk_update_todos, and update_project - see CLAUDE.md for the full 3x3
            table): canceled='true' always wins regardless of completed (e.g.
            completed='false', canceled='true' results in canceled). Whenever
            canceled is not 'true', completed (if given) decides the result:
            'true' -> completed, 'false' -> open. canceled='false' alone (with
            completed omitted) also reopens the project - this is NOT a no-op.
            Omitting both leaves status unchanged. completed/canceled only accept
            the strings 'true'/'false' (case-insensitive) - any other value (e.g.
            'yes', '1') is rejected with a structured VALIDATION_ERROR rather than
            being silently coerced to False.

            Clear-field semantics for partial updates: a field left at its
            default (None/omitted) leaves the existing value unchanged.
            Passing notes='' or deadline='' clears that field. Passing
            tags='' clears all tags. title='' is rejected with a validation
            error (titles cannot be cleared). when='' is also rejected -
            use when='anytime' or when='someday' to unschedule instead.
            """
            try:
                # Validate date parameters. Empty strings ('') are clear/reject
                # requests handled by ParameterValidator.validate_update_params
                # downstream (in self.tools.update_project), not here.
                # Whitespace-only when (e.g. '   ') is truthy so it would
                # otherwise reach validate_date_format() below, which strips
                # and returns None for it - silently treating the request as
                # "no change" instead of rejecting it the same way '' is
                # rejected downstream. Reject it explicitly here instead
                # (hq-f0w.34).
                if isinstance(when, str) and when.strip() == '' and when != '':
                    return {
                        "success": False,
                        "error": "VALIDATION_ERROR",
                        "field": "when",
                        "message": "use when='anytime' or when='someday' to unschedule",
                        "invalid_value": when
                    }

                if when:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        when = ParameterValidator.validate_date_format(when, 'when', allow_relative=True)
                    except Exception as e:
                        return self._write_error("INVALID_WHEN", str(e), field="when")

                if deadline:
                    try:
                        from things_mcp.parameter_validator import ParameterValidator
                        ParameterValidator.validate_date_format(deadline, 'deadline', allow_relative=False)
                    except Exception as e:
                        return self._write_error("INVALID_DEADLINE", str(e), field="deadline")

                # Convert comma-separated tags to list. '' clears all tags,
                # None (tags not provided) leaves tags unchanged.
                tag_list = _parse_tag_list_for_update(tags)

                # Strictly parse completed/canceled: only an actual bool or
                # the strings 'true'/'false' (case-insensitive) are accepted;
                # anything else (e.g. 'yes', '1') is a structured error
                # rather than silently becoming False and reopening the project.
                try:
                    completed_bool = _parse_strict_bool(completed, 'completed')
                    canceled_bool = _parse_strict_bool(canceled, 'canceled')
                except _StrictBoolError as e:
                    return {
                        "success": False,
                        "error": "VALIDATION_ERROR",
                        "field": e.field,
                        "message": e.message
                    }

                return await self.tools.update_project(
                    project_id=id,
                    title=title,
                    notes=notes,
                    tags=tag_list,
                    when=when,
                    deadline=deadline,
                    area_id=area_id,
                    area_title=area_title,
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
                    return self._read_error(
                        "invalid_mode",
                        f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}",
                    )

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

                return self._read_result(
                    optimized_response,
                    mode=response_mode.value,
                    total=len(raw_data),
                )
            except Exception as e:
                logger.error(f"Error getting areas: {e}")
                raise

        @self.mcp.tool()
        async def add_area(
            title: str = Field(..., min_length=1, description="Title of the area"),
            tags: Optional[str] = Field(None, description="Comma-separated existing tags to apply to the area. Tags that don't already exist in Things 3 are silently filtered out.")
        ) -> Dict[str, Any]:
            """Create a new area. Areas represent life/work domains (e.g. Work, Personal) and can contain projects and todos. Note: there is no delete_area tool, since deleting an area also deletes its projects."""
            try:
                tag_list = _parse_tag_list(tags)
                return await self.tools.add_area(title=title, tags=tag_list)
            except Exception as e:
                logger.error(f"Error adding area: {e}")
                raise

        @self.mcp.tool()
        async def update_area(
            id: str = Field(..., description="ID of the area to update"),
            title: Optional[str] = Field(None, description="New title for the area. Omit to leave unchanged; '' is rejected (titles cannot be cleared)"),
            tags: Optional[str] = Field(None, description="Comma-separated existing tags to apply to the area (replaces current tags). Omit to leave unchanged; pass '' to clear all tags. Tags that don't already exist in Things 3 are silently filtered out.")
        ) -> Dict[str, Any]:
            """Update an existing area's title and/or tags. Only provided fields are changed.
            Note: there is no delete_area tool, since deleting an area also deletes its projects.

            Clear-field semantics: title left at its default (None/omitted) leaves the
            existing title unchanged; title='' is rejected with a validation error
            (titles cannot be cleared). tags left at its default (None/omitted) leaves
            existing tags unchanged; tags='' clears all tags.
            """
            try:
                # '' clears all tags, None (tags not provided) leaves tags unchanged.
                tag_list = _parse_tag_list_for_update(tags)
                return await self.tools.update_area(area_id=id, title=title, tags=tag_list)
            except Exception as e:
                logger.error(f"Error updating area: {e}")
                raise

        # List-based tools
        @self.mcp.tool()
        async def get_inbox(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500)
        ) -> Dict[str, Any]:
            """Get todos from Inbox. Supports response optimization via mode parameter and limit.

            Note: filter_someday_project_tasks is NOT applied here - it is a no-op for
            Inbox in any case, since Inbox items cannot belong to a project.
            """
            try:
                # Fetch the full unbounded set first so `total` reflects the
                # pre-limit count (CLAUDE.md contract), then slice to `limit`
                # here - mirrors the existing get_upcoming(days=...) pattern.
                full_data = await self.tools.get_inbox(limit=None)
                pre_limit_total = len(full_data)
                raw_data = full_data[:limit] if limit else full_data

                # Apply context-aware optimization, treating an omitted mode as 'auto'
                # so structured_content.mode always reports the concrete resolved mode.
                request_params = {'mode': mode or 'auto', 'limit': limit}
                optimized_params, _ = self.context_manager.optimize_request('get_inbox', request_params)
                response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                optimized_response = self.context_manager.optimize_response(raw_data, 'get_inbox', response_mode, optimized_params)
                return self._read_result(optimized_response, mode=mode, limit=limit, total=pre_limit_total)
            except Exception as e:
                logger.error(f"Error getting inbox: {e}")
                raise
        
        @self.mcp.tool()
        async def get_today(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500),
            include_projects: bool = Field(False, description="Also include projects due today. Default false: headings are never returned; projects are excluded unless this is true, matching the Things app's Today list view.")
        ) -> Dict[str, Any]:
            """Get todos due today. Supports response optimization via mode parameter and limit."""
            try:
                # Fetch the full unbounded set first so `total` reflects the
                # pre-limit count (CLAUDE.md contract), then slice to `limit`
                # here - mirrors the existing get_upcoming(days=...) pattern.
                full_data = await self.tools.get_today(limit=None, include_projects=include_projects)
                pre_limit_total = len(full_data)
                raw_data = full_data[:limit] if limit else full_data

                # Apply context-aware optimization, treating an omitted mode as 'auto'
                # so structured_content.mode always reports the concrete resolved mode.
                request_params = {'mode': mode or 'auto', 'limit': limit}
                optimized_params, _ = self.context_manager.optimize_request('get_today', request_params)
                response_mode = ResponseMode(optimized_params.get('mode', 'standard'))  # Default to standard for Today
                optimized_response = self.context_manager.optimize_response(raw_data, 'get_today', response_mode, optimized_params)
                return self._read_result(optimized_response, mode=mode, limit=limit, total=pre_limit_total)
            except Exception as e:
                logger.error(f"Error getting today's todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_upcoming(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500),
            days: Optional[int] = Field(None, description="If provided, returns todos due/activating within this many days (1-365). Without days, returns items from Things 3's Upcoming list.", ge=1, le=365),
            include_projects: bool = Field(False, description="Only applies when 'days' is not provided. Also include upcoming projects. Default false: headings are never returned; projects are excluded unless this is true, matching the Things app's Upcoming list view.")
        ) -> Dict[str, Any]:
            """Get upcoming todos. Supports response optimization via mode parameter and limit.

            If 'days' is provided, returns todos due or activating within that timeframe.
            Without 'days', returns items from Things 3's built-in Upcoming list.
            """
            try:
                # If days is specified, filter todos by date range
                if days is not None:
                    logger.info(f"Getting todos upcoming in {days} days")
                    todos = await self.tools.get_todos_upcoming_in_days(days)
                    pre_limit_total = len(todos)

                    # Apply limit if specified
                    if limit and len(todos) > limit:
                        todos = todos[:limit]

                    # Apply context-aware optimization, treating an omitted mode as
                    # 'auto' so structured_content.mode always reports the concrete
                    # resolved mode.
                    request_params = {'mode': mode or 'auto', 'days': days}
                    optimized_params, _ = self.context_manager.optimize_request('get_upcoming', request_params)
                    response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                    optimized_response = self.context_manager.optimize_response(todos, 'get_upcoming', response_mode, optimized_params)
                    result = self._read_result(optimized_response, mode=mode, limit=limit, total=pre_limit_total)
                    result['days'] = days
                    return result

                # Original behavior: get items from Things 3's Upcoming list.
                # Fetch the full unbounded set first so `total` reflects the
                # pre-limit count (CLAUDE.md contract), then slice to `limit`.
                full_data = await self.tools.get_upcoming(limit=None, include_projects=include_projects)
                pre_limit_total = len(full_data)
                raw_data = full_data[:limit] if limit else full_data

                # Apply context-aware optimization, treating an omitted mode as 'auto'
                # so structured_content.mode always reports the concrete resolved mode.
                request_params = {'mode': mode or 'auto', 'limit': limit}
                optimized_params, _ = self.context_manager.optimize_request('get_upcoming', request_params)
                response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                optimized_response = self.context_manager.optimize_response(raw_data, 'get_upcoming', response_mode, optimized_params)
                return self._read_result(optimized_response, mode=mode, limit=limit, total=pre_limit_total)
            except Exception as e:
                logger.error(f"Error getting upcoming todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_anytime(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500),
            include_projects: bool = Field(False, description="Also include Anytime projects. Default false: headings are never returned; projects are excluded unless this is true, matching the Things app's Anytime list view.")
        ) -> Dict[str, Any]:
            """Get todos from Anytime list. Supports response optimization via mode parameter and limit."""
            try:
                # Fetch the full unbounded set first so `total` reflects the
                # pre-limit count (CLAUDE.md contract), then slice to `limit`
                # here - mirrors the existing get_upcoming(days=...) pattern.
                full_data = await self.tools.get_anytime(limit=None, include_projects=include_projects)
                pre_limit_total = len(full_data)
                raw_data = full_data[:limit] if limit else full_data

                # Apply context-aware optimization, treating an omitted mode as 'auto'
                # so structured_content.mode always reports the concrete resolved mode.
                request_params = {'mode': mode or 'auto', 'limit': limit}
                optimized_params, _ = self.context_manager.optimize_request('get_anytime', request_params)
                response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                optimized_response = self.context_manager.optimize_response(raw_data, 'get_anytime', response_mode, optimized_params)
                return self._read_result(optimized_response, mode=mode, limit=limit, total=pre_limit_total)
            except Exception as e:
                logger.error(f"Error getting anytime todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_someday(
            mode: Optional[str] = Field(None, description="Response mode: auto/summary/minimal/standard/detailed/raw"),
            limit: Optional[int] = Field(None, description="Maximum number of items to return (1-500)", ge=1, le=500),
            include_project_tasks: bool = Field(False, description="Also include tasks that live inside Someday projects (marked inheritedSomeday=true). Default false; can be large on databases with many Someday projects."),
            include_projects: bool = Field(False, description="Also include Someday projects themselves. Default false: headings are never returned; projects are excluded unless this is true, matching the Things app's Someday list view.")
        ) -> Dict[str, Any]:
            """Get todos from Someday list. Supports response optimization via mode parameter and limit."""
            try:
                # Fetch the full unbounded set first so `total` reflects the
                # pre-limit count (CLAUDE.md contract), then slice to `limit`
                # here - mirrors the existing get_upcoming(days=...) pattern.
                full_data = await self.tools.get_someday(
                    limit=None, include_project_tasks=include_project_tasks,
                    include_projects=include_projects)
                pre_limit_total = len(full_data)
                raw_data = full_data[:limit] if limit else full_data

                # Apply context-aware optimization, treating an omitted mode as 'auto'
                # so structured_content.mode always reports the concrete resolved mode.
                request_params = {'mode': mode or 'auto', 'limit': limit}
                optimized_params, _ = self.context_manager.optimize_request('get_someday', request_params)
                response_mode = ResponseMode(optimized_params.get('mode', 'auto'))
                optimized_response = self.context_manager.optimize_response(raw_data, 'get_someday', response_mode, optimized_params)
                return self._read_result(optimized_response, mode=mode, limit=limit, total=pre_limit_total)
            except Exception as e:
                logger.error(f"Error getting someday todos: {e}")
                raise
        
        @self.mcp.tool()
        async def get_logbook(
            limit: int = Field(50, description="Maximum number of entries to return. Defaults to 50 (1-500)", ge=1, le=500),
            period: str = Field("7d", description="Time period to look back (e.g., '3d', '1w', '2m', '1y'). Defaults to '7d'", pattern=r"^\d+[dwmy]$"),
            offset: int = Field(0, description="Number of matching entries to skip before applying limit (default: 0)", ge=0),
            include_canceled: bool = Field(True, description="Also include canceled to-dos alongside completed ones, matching the Things app's own Logbook view. Defaults to true. Each item's `status` field ('completed' or 'canceled') distinguishes them; set false to return only completed to-dos.")
        ) -> Dict[str, Any]:
            """Get completed (and, by default, canceled) todos from Logbook. Supports limit (max 500), offset, and period filters (e.g., '7d', '1w')."""
            try:
                logbook_data = await self.tools.get_logbook(
                    limit=limit, period=period, offset=offset, include_canceled=include_canceled)
                total = getattr(logbook_data, 'total_count', None)
                result = self._read_result(logbook_data, mode='standard', limit=limit, offset=offset, total=total)
                result['period'] = period
                return result
            except Exception as e:
                logger.error(f"Error getting logbook: {e}")
                raise
        
        @self.mcp.tool()
        async def get_trash(
            limit: int = Field(50, description="Maximum number of items to return (default: 50, max: 100)", ge=1, le=100),
            offset: int = Field(0, description="Number of items to skip (default: 0)", ge=0),
            include_projects: bool = Field(False, description="Also include trashed projects. Default false: headings are never returned; projects are excluded unless this is true, matching the Things app's Trash list view.")
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
                trash_data = await self.tools.get_trash(limit=limit, offset=offset, include_projects=include_projects)
                return self._read_result(
                    trash_data,
                    mode='standard',
                    limit=limit,
                    offset=offset,
                    total=trash_data.get('total_count') if isinstance(trash_data, dict) else None,
                )
            except Exception as e:
                logger.error(f"Error getting trash: {e}")
                raise
        
        # Efficient date-range query tools using AppleScript 'whose' clause
        @self.mcp.tool()
        async def get_due_in_days(
            days: int = Field(30, description="Number of days ahead to check for due todos", ge=1, le=365),
            include_overdue: bool = Field(True, description="Include todos whose deadline is already in the past. Default true preserves historical behavior; set false to restrict results to today <= deadline <= target date.")
        ) -> Dict[str, Any]:
            """Get todos due within specified days (1-365). By default also includes already-overdue todos (include_overdue=True); set include_overdue=False to restrict to the forward window only."""
            try:
                due_todos = await self.tools.get_todos_due_in_days(days, include_overdue=include_overdue)
                result = self._read_result(due_todos, mode='standard')
                result['days'] = days
                result['include_overdue'] = include_overdue
                return result
            except Exception as e:
                logger.error(f"Error getting todos due in {days} days: {e}")
                return self._read_error(
                    "internal_error", str(e),
                    todos=[], items=[], count=0, total=0, mode=None, limit=None, offset=None,
                )

        @self.mcp.tool()
        async def get_activating_in_days(
            days: int = Field(30, description="Number of days ahead to check for activating todos", ge=1, le=365)
        ) -> Dict[str, Any]:
            """Get todos activating within specified days (1-365). Only returns todos whose start date falls within the forward window (today through the target date); todos already active are excluded."""
            try:
                activating_todos = await self.tools.get_todos_activating_in_days(days)
                result = self._read_result(activating_todos, mode='standard')
                result['days'] = days
                return result
            except Exception as e:
                logger.error(f"Error getting todos activating in {days} days: {e}")
                return self._read_error(
                    "internal_error", str(e),
                    todos=[], items=[], count=0, total=0, mode=None, limit=None, offset=None,
                )
        
        # Tag management tools
        @self.mcp.tool()
        async def get_tags(
            include_items: bool = Field(False, description="Include items list (True) or just counts (False)")
        ) -> Dict[str, Any]:
            """Get all tags with item counts or full items. Use include_items=true for full item lists."""
            try:
                tags_data = await self.tools.get_tags(include_items=include_items)
                return self._read_result(tags_data, mode='standard')
            except Exception as e:
                logger.error(f"Error getting tags: {e}")
                raise
        
        @self.mcp.tool()
        async def get_tagged_items(
            tag: str = Field(..., description="Tag title to filter by")
        ) -> Dict[str, Any]:
            """Get todos with a specific tag.

            Note: tag matching is case-sensitive. An unknown tag (including a
            wrong-case variant of a real tag, e.g. 'work' vs 'Work') returns a
            structured error ({"success": false, "error": "unknown_tag", ...})
            with case-insensitive suggestions instead of an empty result.
            """
            try:
                tagged_items = await self.tools.get_tagged_items(tag=tag)
                if isinstance(tagged_items, dict) and tagged_items.get('error') == 'unknown_tag':
                    # 'tag' is already set on this dict by
                    # _build_unknown_tag_error (read_operations.py) - no need
                    # to overwrite it here.
                    return tagged_items
                result = self._read_result(tagged_items, mode='standard')
                result['tag'] = tag
                return result
            except Exception as e:
                logger.error(f"Error getting tagged items: {e}")
                raise

        @self.mcp.tool()
        async def get_project_headings(
            project_id: str = Field(..., description="UUID of the project to read headings from"),
            mode: Optional[str] = Field(None, description="Response mode (auto/summary/minimal/standard/detailed/raw)")
        ) -> Dict[str, Any]:
            """Get the heading structure of a project, in Things' own display order.

            Each item has: uuid, title, index (Things' internal ordering value,
            lower sorts first), and todoCount (number of open to-dos directly
            under that heading, via things.todos(heading=uuid, status='incomplete')).

            Read-only by design: headings can only be created at
            project-creation time, via add_project(todos=...)'s ``##`` lines
            (things:///json) - not by this tool. Existing headings cannot be
            renamed or deleted via any public Things 3 API: there is no
            AppleScript heading class, and the URL scheme can only place
            to-dos under headings that already exist. This tool exists purely
            to read the heading structure that already exists in a project.

            Args:
                project_id: UUID of the project. Must resolve to an item of
                    type 'project' - ids for to-dos, areas, or headings, and
                    unknown ids, return a structured error instead of raising.
                mode: Response mode for the items list - 'auto' (default,
                    resolves to a concrete mode based on data size), 'summary',
                    'minimal', 'standard', 'detailed', or 'raw'.
            """
            try:
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return self._read_error(
                        "invalid_mode",
                        f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}",
                    )

                headings_result = await self.tools.get_project_headings(project_id=project_id)
                if isinstance(headings_result, dict) and headings_result.get('error'):
                    return headings_result
                raw_data = headings_result.get('items', []) if isinstance(headings_result, dict) else headings_result

                # Apply smart defaults and optimization
                request_params = {'mode': mode}
                optimized_params, was_modified = self.context_manager.optimize_request(
                    'get_project_headings', request_params
                )
                response_mode = ResponseMode(optimized_params.get('mode', 'standard'))

                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'get_project_headings', response_mode, optimized_params
                )

                return self._read_result(
                    optimized_response,
                    mode=response_mode.value,
                    total=len(raw_data),
                )
            except Exception as e:
                logger.error(f"Error getting project headings: {e}")
                raise

        @self.mcp.tool()
        async def get_tag_usage(
            only_unused: bool = Field(False, description="If true, only return tags with zero items (cleanup candidates)"),
            mode: str = Field("standard", description="Response mode: summary, minimal, standard, or detailed")
        ) -> Dict[str, Any]:
            """Report how many items (todos, projects, and areas; open and total) use each tag, sorted by usage (highest first).

            Useful for weekly-review tag cleanup: identify rarely-used or unused tags,
            then remove them from remaining items or delete the tag manually in Things.

            Args:
                only_unused: If true, return only tags with zero items (open_count and total_count both 0).
                mode: Response mode - 'summary' (tag_count/unused_count/top 5), 'minimal' (title+open_count only),
                    'standard'/'detailed' (full rows with title, uuid, open_count, total_count, area_count).

            Caveats:
                - Title collisions: usage is keyed by tag title, not uuid. If two distinct
                  tags (e.g. a parent tag and a same-named child tag) share the exact same
                  title, their counts are merged into a single row and the reported uuid
                  is whichever tag was returned last for that title by the underlying tag
                  list.
                - Area tags: tags applied to Areas are counted via `area_count` and are
                  included in `total_count`, so a tag used only on an area will not be
                  reported as unused. Areas have no open/closed state, so area usage never
                  contributes to `open_count`.
            """
            try:
                if mode not in ("summary", "minimal", "standard", "detailed"):
                    return self._read_error(
                        "invalid_mode",
                        f"Mode must be one of: summary, minimal, standard, detailed. Got: {mode}",
                    )
                usage_data = await self.tools.get_tag_usage(only_unused=only_unused, mode=mode)
                return self._read_result(usage_data, mode=mode)
            except Exception as e:
                logger.error(f"Error getting tag usage: {e}")
                raise
        
        # Search tools
        @self.mcp.tool()
        async def search_todos(
            query: str = Field(..., description="Search term to look for in todo titles and notes"),
            limit: int = Field(50, description="Maximum number of results to return (1-500)", ge=1, le=500),
            mode: Optional[str] = None,
            status: Optional[str] = 'incomplete',
            offset: int = Field(0, description="Number of matching results to skip before applying limit (default: 0)", ge=0)
        ) -> Dict[str, Any]:
            """Search todos by query term. Supports limit (1-500), offset, and response modes for context optimization.

            Args:
                query: Search term to look for in todo titles and notes (case-insensitive
                    substring match). Cannot be empty or whitespace-only.
                limit: Maximum number of results to return (1-500).
                mode: Response mode (auto/summary/minimal/standard/detailed/raw).
                status: Filter by status - 'incomplete' (default, for backward compatibility),
                    'completed', 'canceled', or None to search all statuses. Note the default
                    means a completed or canceled todo will NOT match unless you pass
                    status='completed'/'canceled'/None explicitly.
                offset: Number of matching results to skip before applying limit (default 0).

            Note: filter_someday_project_tasks is NOT applied to search - todos inside a
            Someday project (hidden from Today/Anytime/Upcoming in the Things UI) can still
            match a search.
            """
            try:
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return self._read_error(
                        "invalid_mode",
                        f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}",
                    )

                # Normalize status parameter (MCP may pass string "None")
                if status == "None" or status == "null":
                    status = None

                # Validate status parameter
                if status is not None and status not in ["incomplete", "completed", "canceled"]:
                    return self._read_error(
                        "invalid_status",
                        f"Status must be one of: 'incomplete', 'completed', 'canceled', or None for all. Got: {status}",
                    )

                # Reject empty/whitespace-only query - an empty substring matches
                # every todo's title/notes, which is never a useful search result.
                if not query or not query.strip():
                    return self._read_error(
                        "invalid_query",
                        "query must not be empty or whitespace-only",
                    )

                # Prepare request parameters
                request_params = {
                    'query': query,
                    'limit': limit,
                    'mode': mode,
                    'status': status
                }

                # Apply smart defaults and optimization
                optimized_params, was_modified = self.context_manager.optimize_request('search_todos', request_params)

                # Extract optimized parameters
                final_limit = optimized_params.get('limit', 50)
                response_mode = ResponseMode(optimized_params.get('mode', 'auto'))

                # Get raw data from tools layer
                raw_data = await self.tools.search_todos(query=query, limit=final_limit, status=status, offset=offset)
                pre_limit_total = getattr(raw_data, 'total_count', None)
                if pre_limit_total is None:
                    pre_limit_total = len(raw_data)

                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'search_todos', response_mode, optimized_params
                )

                # Add minimal optimization metadata
                if was_modified:
                    optimized_response['optimized'] = True

                return self._read_result(
                    optimized_response,
                    mode=response_mode.value,
                    limit=final_limit,
                    offset=offset,
                    total=pre_limit_total,
                )

            except Exception as e:
                logger.error(f"Error searching todos: {e}")
                raise
        
        @self.mcp.tool()
        async def search_advanced(
            status: Optional[str] = Field(None, description="Filter by todo status. If omitted, ALL statuses (incomplete, completed, canceled) are searched", pattern="^(incomplete|completed|canceled)$"),
            type: Optional[str] = Field(None, description="Filter by item type", pattern="^(to-do|project|heading)$"),
            tag: Optional[str] = Field(None, description="Filter by tag (case-sensitive)"),
            area: Optional[str] = Field(None, description="Filter by area UUID"),
            start_date: Optional[str] = Field(None, description="Filter by start date (YYYY-MM-DD)"),
            deadline: Optional[str] = Field(None, description="Filter by deadline (YYYY-MM-DD)"),
            limit: int = Field(50, description="Maximum number of results to return (1-500)", ge=1, le=500),
            mode: Optional[str] = None,
            offset: int = Field(0, description="Number of matching results to skip before applying limit (default: 0)", ge=0)
        ) -> Dict[str, Any]:
            """Advanced search with multiple filters: status, type, tag, area, start_date, deadline. Supports response modes, limit (1-500), and offset for efficient retrieval.

            Note: the tag filter is case-sensitive. An unknown tag (including a
            wrong-case variant of a real tag, e.g. 'work' vs 'Work') returns a
            structured error ({"success": false, "error": "unknown_tag", ...})
            with case-insensitive suggestions instead of an empty result.

            Unlike search_todos() and get_todos() (which default to 'incomplete' only),
            search_advanced with no `status` filter searches items of ALL statuses
            (incomplete, completed, and canceled). Pass status='incomplete' explicitly
            to restrict to open items.

            Note: filter_someday_project_tasks is NOT applied here - todos inside a
            Someday project (hidden from Today/Anytime/Upcoming in the Things UI) can
            still match search_advanced.
            """
            try:
                # Import datetime for validation
                from datetime import datetime
                
                # Validate mode parameter
                if mode and mode not in ["auto", "summary", "minimal", "standard", "detailed", "raw"]:
                    return self._read_error(
                        "invalid_mode",
                        f"Mode must be one of: auto, summary, minimal, standard, detailed, raw. Got: {mode}",
                        valid_modes=["auto", "summary", "minimal", "standard", "detailed", "raw"],
                    )

                # Validate date formats
                if start_date:
                    try:
                        datetime.strptime(start_date, '%Y-%m-%d')
                    except ValueError:
                        return self._read_error(
                            "invalid_start_date_format",
                            f"start_date must be in YYYY-MM-DD format. Got: {start_date}",
                            example="2024-12-25",
                        )

                if deadline:
                    try:
                        datetime.strptime(deadline, '%Y-%m-%d')
                    except ValueError:
                        return self._read_error(
                            "invalid_deadline_format",
                            f"deadline must be in YYYY-MM-DD format. Got: {deadline}",
                            example="2024-12-31",
                        )
                
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
                    limit=final_limit,
                    offset=offset
                )

                # A structured error (e.g. unknown_tag, invalid_parameter)
                # comes back from ReadOperations.search_advanced as a
                # single-element list wrapping a `read_error(...)` dict
                # (`{"success": False, "error": ..., "message": ...}`).
                # Surface it directly rather than feeding it through
                # optimize_response, which expects a list of todos.
                if (
                    len(raw_data) == 1
                    and isinstance(raw_data[0], dict)
                    and raw_data[0].get('success') is False
                ):
                    return raw_data[0]

                pre_limit_total = getattr(raw_data, 'total_count', None)
                if pre_limit_total is None:
                    pre_limit_total = len(raw_data)

                # Apply context-aware response optimization
                optimized_response = self.context_manager.optimize_response(
                    raw_data, 'search_advanced', response_mode, optimized_params
                )

                # Add minimal optimization metadata
                if was_modified:
                    optimized_response['optimized'] = True

                return self._read_result(
                    optimized_response,
                    mode=response_mode.value,
                    limit=final_limit,
                    offset=offset,
                    total=pre_limit_total,
                )

            except Exception as e:
                logger.error(f"Error in advanced search: {e}")
                raise
        
        @self.mcp.tool()
        async def get_recent(
            period: str = Field(..., description="Time period (e.g., '3d', '1w', '2m', '1y')", pattern=r"^\d+[dwmy]$"),
            status: Optional[str] = Field(None, description="Filter by status - 'incomplete', 'completed', 'canceled', or None (default) for all statuses", pattern="^(incomplete|completed|canceled)$"),
            type: Optional[str] = Field(None, description="Filter by item type - 'to-do', 'project', 'heading', or None (default) for to-dos and projects (headings are never included by default; pass type='heading' explicitly to fetch them)", pattern="^(to-do|project|heading)$")
        ) -> Dict[str, Any]:
            """Get recently created items within a time period (e.g., '3d', '1w').

            By default returns items of ALL statuses and both to-dos and projects -
            completed/canceled to-dos and recently created projects are included, not
            just open to-dos. Headings are NEVER included by default (list tools never
            return headings by default - they aren't user-facing items); pass
            type='heading' explicitly if you need recently created headings. Pass
            status and/or type to narrow the results.

            Note: filter_someday_project_tasks is NOT applied here - items inside a
            Someday project (hidden from Today/Anytime/Upcoming in the Things UI) can
            still appear in get_recent results.
            """
            try:
                recent_items = await self.tools.get_recent(period=period, status=status, type=type)
                result = self._read_result(recent_items, mode='standard')
                result['period'] = period
                return result
            except Exception as e:
                logger.error(f"Error getting recent items: {e}")
                raise
        
        # Navigation tools
        @self.mcp.tool()
        async def add_tags(
            todo_id: str = Field(..., description="ID of the todo"),
            tags: str = Field(..., description="Comma-separated tags to add")
        ) -> Dict[str, Any]:
            """Add tags to a todo. Only existing tags can be applied.

            The response `message` reports how many tags were newly attached
            (tags already present on the todo are not double-counted). The
            `tags` parameter is comma-separated, and the comma is the tag
            separator - tag names cannot contain a comma. "a,b" is always
            treated as two tags ("a" and "b"), never as one tag named "a,b";
            there is no way to pass a literal comma in a tag name through
            this string-based parameter.
            """
            try:
                # Convert comma-separated tags to list
                tag_list = _parse_tag_list(tags) or []
                result = await self.tools.add_tags(todo_id=todo_id, tags=tag_list)
                
                # Enhance response with tag policy feedback
                if self.tools.tag_validation_service and result.get('success'):
                    policy = self.tools.config.tag_creation_policy if self.tools.config else 'allow_all'
                    
                    # Add policy information to response
                    result['tag_policy'] = {
                        'policy': policy.value if hasattr(policy, 'value') else str(policy),
                        'description': self._get_policy_description(policy)
                    }
                    
                    # Get tag validation info from the result
                    if 'tag_info' in result:
                        tag_info = result['tag_info']
                        if tag_info.get('created'):
                            result['message'] = result.get('message', 'Tags added successfully.') + f" Created new tags: {', '.join(tag_info['created'])}"
                        if tag_info.get('filtered'):
                            result['message'] = result.get('message', 'Tags added successfully.') + f" Filtered tags per policy: {', '.join(tag_info['filtered'])}"
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
            """Remove tags from a todo.

            Removing a tag the todo doesn't currently have is a no-op, not an
            error - it does not go through the configured tag_creation_policy
            (there is nothing to create or filter when removing). The
            response includes `removed_count` (the number of tags actually
            removed - a set difference against the todo's current tags, not
            the number requested) and `not_present` (any requested tags that
            were not on the todo).
            """
            try:
                # Convert comma-separated tags to list
                tag_list = _parse_tag_list(tags) or []
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
                total_tools = await self._registered_tool_count()
                capabilities = {
                    "server_info": {
                        "name": "Things 3 MCP Server",
                        "version": __version__,
                        "platform": "macOS",
                        "framework": "FastMCP 3.x",
                        "total_tools": total_tools
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
                        "total_tools": total_tools,
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

    @staticmethod
    def _read_error(code: str, message: str, **extra: Any) -> Dict[str, Any]:
        """Build the canonical structured-error shape for a read tool.

        Every read tool's structured (non-raising) error path should return
        this shape so MCP clients can rely on a single contract:
        ``{"success": False, "error": "<snake_case_code>", "message": "<human text>", ...}``.

        Delegates to ``tools_helpers.read_operations.read_error`` - the
        single shared implementation used by both this server-tool layer and
        the tools layer (``ReadOperations``), so the two can never diverge.

        Args:
            code: Short, stable, machine-readable snake_case error code (e.g.
                'invalid_mode', 'unknown_tag', 'not_found'). Stable across
                releases - clients may switch on this value.
            message: Human-readable explanation of the error.
            **extra: Additional fields to merge into the result (e.g. 'tag',
                'suggestions', 'valid_modes', 'example').

        Returns:
            A dict with 'success', 'error', 'message', plus any extra fields.
        """
        return _tools_read_error(code, message, **extra)

    @staticmethod
    def _write_error(code: str, message: str, **extra: Any) -> Dict[str, Any]:
        """Build the canonical structured-error shape for a write tool.

        Every write tool's structured (non-raising) error path should return
        this shape so MCP clients can rely on a single contract:
        ``{"success": False, "error": "<UPPER_SNAKE_CODE>", "message": "<human text>", ...}``.

        Delegates to ``tools_helpers.errors.write_error`` - the single
        shared implementation used across this server-tool layer and the
        tools layer (``WriteOperations``/``BulkOperations``), so they can
        never diverge. Mirrors ``_read_error`` but uses UPPER_SNAKE_CASE
        codes (matching the convention already established by
        ``VALIDATION_ERROR`` / ``TARGET_COMPLETED`` / ``NO_VALID_TAGS``)
        rather than the read-tool contract's lower_snake_case codes.

        Args:
            code: Short, stable, machine-readable UPPER_SNAKE_CASE error
                code (e.g. 'INVALID_WHEN', 'INVALID_DEADLINE'). Stable
                across releases - clients may switch on this value.
            message: Human-readable explanation of the error.
            **extra: Additional fields to merge into the result (e.g.
                'field', 'invalid_value', 'hint').

        Returns:
            A dict with 'success', 'error', 'message', plus any extra fields.
        """
        return _tools_write_error(code, message, **extra)

    async def _todo_write_receipt(
        self, todo_id: str, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Attach the target id and final item state to a successful write."""
        if not result.get("success"):
            return result

        try:
            item = await self.tools.get_todo_by_id(todo_id)
        except Exception as exc:
            verification_error = self._read_error(
                "readback_failed",
                "Final item readback failed.",
                details=str(exc),
            )
            return self._unverified_todo_write_receipt(
                todo_id, result, verification_error
            )

        if isinstance(item, dict) and item.get("success") is False:
            return self._unverified_todo_write_receipt(todo_id, result, item)

        return {
            **result,
            "todo_id": todo_id,
            "verified": True,
            "item": item,
        }

    @staticmethod
    def _unverified_todo_write_receipt(
        todo_id: str,
        result: Dict[str, Any],
        verification_error: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Report readback failure without misreporting the completed write."""
        warning = (
            "Write succeeded, but final item state could not be verified; "
            "do not retry automatically."
        )
        existing_warnings = result.get("warnings")
        warnings = (
            list(existing_warnings) if isinstance(existing_warnings, list) else []
        )
        warnings.append(warning)
        return {
            **result,
            "todo_id": todo_id,
            "verified": False,
            "verification_error": verification_error,
            "warnings": warnings,
        }

    def _read_result(
        self,
        response: Union[Dict[str, Any], List[Dict[str, Any]]],
        mode: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        total: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Normalize a read-tool response into a consistent structured-content shape.

        FastMCP requires tool return values to be a dict (or a ``ToolResult``) so it can
        populate both the human-readable text content and machine-readable
        ``structured_content`` for the client. This helper guarantees that shape for every
        read tool while preserving the existing text/JSON rendering produced by
        ``context_manager.optimize_response`` (or a raw list, for tools that don't go
        through the context manager).

        The resulting envelope always contains:
            - ``items``: the list of item dicts appropriate for the effective mode. In
              ``summary`` mode this is intentionally a small preview (not the full list) to
              avoid context explosion, matching the existing summary behaviour.
            - ``count``: len(items)
            - ``total``: total items available before any limit was applied (falls back to
              ``count`` when the true pre-limit total isn't known/tracked).
            - ``mode``: the effective response mode that was actually applied. If the
              caller requested ``'auto'`` (or omitted ``mode``), this reports the concrete
              mode resolved by ``context_manager.optimize_response`` (from ``meta['mode']``)
              rather than echoing back ``'auto'``.
            - ``requested_mode``: the mode originally requested by the caller (may be
              ``'auto'`` or ``None``), preserved for callers that want to distinguish
              "what was asked for" from "what was returned".
            - ``limit`` / ``offset``: echoed back from the request, or None.

        Any other keys already present on a dict ``response`` (e.g. ``meta``,
        ``status_breakdown``, ``optimized``, error fields, etc.) are preserved so existing
        text/JSON substance is unchanged.

        Args:
            response: Either the dict already produced by context_manager.optimize_response
                (which may be a summary-style dict with a preview list, or a
                {"data": [...], "meta": {...}} dict), or a raw list of item dicts for tools
                that don't apply response-mode optimization.
            mode: Requested response mode, if known (e.g. 'auto', 'summary', 'standard').
                When this is 'auto' or None, the resolved effective mode is reported
                instead: meta['mode'] if present, else a top-level 'mode' key (summary
                responses carry no meta), else the requested value.
            limit: The limit that was applied/requested, if any.
            offset: The offset that was applied/requested, if any.
            total: Total item count before limiting, if known/tracked separately from the
                returned items (e.g. pagination endpoints like get_trash).

        Returns:
            A dict containing at least items/count/total/mode/limit/offset, plus any
            pre-existing keys from a dict response.
        """
        if isinstance(response, list):
            items = response
            result: Dict[str, Any] = {
                "items": items,
                "count": len(items),
                "total": total if total is not None else len(items),
                "mode": mode,
                "limit": limit,
                "offset": offset,
            }
            return result

        # response is already a dict (e.g. from context_manager.optimize_response,
        # or a hand-built {"items": ..., ...} / {"data": ..., "meta": ...} payload).
        result = dict(response)

        if "items" in result and isinstance(result["items"], list):
            items = result["items"]
        elif "data" in result and isinstance(result["data"], list):
            items = result["data"]
        else:
            # Summary-style responses (and other non-list-bearing dicts) don't carry a
            # full item list - use whatever preview list is present (e.g.
            # 'recent_preview', 'recent_projects', 'most_common') without inventing one,
            # to avoid materializing full items in summary mode.
            preview = (
                result.get("recent_preview")
                or result.get("recent_projects")
                or result.get("tags")
                or result.get("top")
                or []
            )
            items = preview if isinstance(preview, list) else []

        meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}

        # When the requested mode is 'auto' (or unspecified), the *effective* mode chosen
        # by context_manager.optimize_response is recorded either in meta['mode'] (the
        # {"data": ..., "meta": ...} shape) or as a top-level 'mode' key (the summary-shaped
        # payload from create_summary_response, which carries no 'meta' at all). Prefer
        # whichever of those is actually present so structured_content reflects what was
        # returned, per docs, instead of echoing back the literal 'auto' request.
        requested_mode = mode
        if mode in (None, "auto"):
            effective_mode = meta.get("mode") or result.get("mode") or mode
        else:
            effective_mode = mode or result.get("mode") or meta.get("mode")
        effective_total = total
        if effective_total is None:
            effective_total = meta.get("total") if isinstance(meta.get("total"), int) else None
        if effective_total is None:
            effective_total = result.get("count") if isinstance(result.get("count"), int) else None
        if effective_total is None:
            effective_total = result.get("tag_count") if isinstance(result.get("tag_count"), int) else None
        if effective_total is None:
            effective_total = len(items)

        result.setdefault("items", items)
        result["count"] = len(items)
        result["total"] = effective_total
        result["mode"] = effective_mode
        result["requested_mode"] = requested_mode
        result["limit"] = limit
        result["offset"] = offset

        return result

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
        """Run the MCP server.

        Uses stdio transport by default. If ``THINGS_MCP_TRANSPORT`` (or
        ``--transport``) is set to ``http``, runs an HTTP transport instead,
        bound to ``self.config.host``/``self.config.port``. This is the
        recommended workaround when a client's stdio subprocess lacks TCC
        (Automation) access: run this process from a Terminal that has been
        granted access, then point the client at the HTTP URL.
        """
        try:
            logger.info("Starting Things MCP Server...")
            if self.config.transport == "http":
                boot_marker("calling-mcp.run-http")
                logger.info(
                    f"Starting HTTP transport on http://{self.config.host}:{self.config.port}/mcp"
                )
                self.mcp.run(
                    transport="http",
                    host=self.config.host,
                    port=self.config.port,
                )
            else:
                boot_marker("calling-mcp.run")
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
