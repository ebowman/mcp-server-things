"""AppleScript manager for Things 3 integration.

This module serves as a facade that delegates to specialized modules:
- executor: AppleScript execution with locking and retry
- formatters: Date/tag/URL formatting
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..locale_aware_dates import locale_handler
from ..config import ThingsMCPConfig
from .applescript import (
    AppleScriptExecutor,
    AppleScriptFormatters,
)

logger = logging.getLogger(__name__)

# Things URL-scheme actions that require the auth token per the official
# Things URL Scheme docs (https://culturedcode.com/things/support/articles/2803573/,
# "Modifying existing to-dos and projects requires authentication"). ``add`` /
# ``add-project`` / ``show`` / ``search`` / ``json`` (add mode) do NOT require a
# token; only actions that modify existing items do.
AUTH_REQUIRING_ACTIONS = frozenset({"update", "update-project"})

AUTH_TOKEN_HINT = (
    "Things URL-scheme auth token not configured. Add it via one of: "
    "a '.things-auth' file in the project root, a 'things-auth.txt' file in "
    "the project root, or a '~/.things-auth' file in your home directory "
    "(first match wins). Find your token in Things: Settings > General > "
    "Enable Things URLs > Manage."
)


class AppleScriptManager:
    """Manages AppleScript execution and Things URL schemes.

    This class acts as a facade that delegates to specialized modules for
    execution and formatting. It maintains backwards compatibility with
    the original interface.
    """

    # Class-level lock shared across all instances (delegated to executor)
    _applescript_lock = asyncio.Lock()

    def __init__(self, timeout: int = 45, retry_count: int = 3, config: Optional[ThingsMCPConfig] = None):
        """Initialize the AppleScript manager.

        Args:
            timeout: Command timeout in seconds
            retry_count: Number of retries for failed commands
            config: Optional configuration object for feature flags
        """
        self.timeout = timeout
        self.retry_count = retry_count
        self.config = config or ThingsMCPConfig()
        self.auth_token = self._load_auth_token()

        # Initialize specialized modules
        self.executor = AppleScriptExecutor(timeout=timeout, retry_count=retry_count)
        self.formatters = AppleScriptFormatters()

        logger.info("AppleScript manager initialized - cache removed for hybrid implementation")

    def _load_auth_token(self) -> Optional[str]:
        """Load Things auth token from file if it exists."""
        # Path from services/applescript_manager.py -> services -> things_mcp -> src -> project root
        project_root = Path(__file__).parent.parent.parent.parent
        auth_files = [
            project_root / '.things-auth',
            project_root / 'things-auth.txt',
            Path.home() / '.things-auth'
        ]

        for auth_file in auth_files:
            if auth_file.exists():
                try:
                    token = auth_file.read_text().strip()
                    # Handle format: THINGS_AUTH_TOKEN=xxx or just xxx
                    if '=' in token:
                        token = token.split('=', 1)[1].strip()
                    if not token:
                        # Empty/whitespace-only token file: treat as missing and
                        # keep looking at the remaining candidate paths.
                        logger.warning(f"Auth token file {auth_file} is empty - treating as missing")
                        continue
                    logger.info(f"Loaded Things auth token from {auth_file}")
                    return token
                except Exception as e:
                    logger.warning(f"Failed to read auth token from {auth_file}: {e}")

        logger.debug("No Things auth token found - will use direct AppleScript execution")
        return None

    async def is_things_running(self) -> bool:
        """Check if Things 3 is currently running."""
        return await self.executor.is_things_running()

    async def execute_applescript(self, script: str, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """Execute an AppleScript command.

        Args:
            script: AppleScript code to execute
            cache_key: Ignored - caching removed for hybrid implementation

        Returns:
            Dict with success status, output, and error information
        """
        return await self.executor.execute_script(script)

    async def execute_url_scheme(self, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a Things URL scheme command.

        Args:
            action: Things URL action (add, update, show, etc.)
            parameters: Optional parameters for the action

        Returns:
            Dict with success status and result information
        """
        try:
            # Actions that modify existing items (update, update-project, ...)
            # require the Things URL-scheme auth token. Fail fast with an
            # actionable error instead of calling `open`, which exits 0 even
            # when Things silently rejects the un-authenticated URL.
            if action in AUTH_REQUIRING_ACTIONS and not self.auth_token:
                logger.warning(
                    f"Refusing to execute Things URL-scheme action '{action}' "
                    "without an auth token"
                )
                return {
                    "success": False,
                    "error": "Things URL-scheme auth token not configured",
                    "hint": AUTH_TOKEN_HINT,
                }

            # Handle url_override for complete URLs (for reminder functionality)
            if parameters and "url_override" in parameters:
                url = parameters["url_override"]
            else:
                url = self.formatters.build_things_url(action, parameters or {}, self.auth_token)

            # Use do shell script with open -g to avoid bringing Things to foreground
            script = f'''do shell script "open -g '{url}'"'''

            result = await self.executor.execute_script(script)

            # For URL schemes, success is usually indicated by no error
            if result.get("success"):
                return {
                    "success": True,
                    "url": url,
                    "message": f"Successfully executed {action} action"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "url": url
                }

        except Exception as e:
            logger.error(f"Error executing URL scheme: {e}")
            return {
                "success": False,
                "error": str(e)
            }

    # NOTE (hq-nxu.8): get_todos()/get_projects()/get_areas() AppleScript
    # read methods (and their query builders in applescript/queries.py)
    # were removed here - they had zero production callers. The one former
    # caller, ReadOperations.get_todos(project_uuid=...), was measured to
    # need no AppleScript workaround (things.py sees AppleScript-created
    # to-dos with ~6ms lag - see read_operations.py's get_todos docstring)
    # and now goes through things.py directly for both project-scoped and
    # unscoped queries.

    # Delegate formatting methods to formatters module
    def _parse_applescript_date(self, date_str: str) -> Optional[str]:
        """Parse AppleScript date format to ISO string (delegates to formatters)."""
        return self.formatters.parse_applescript_date(date_str)

    def get_applescript_date_formatter(self, date_property: str, fallback_value: str = "missing value") -> str:
        """Generate AppleScript code to format a date property (delegates to formatters)."""
        return self.formatters.get_applescript_date_formatter(date_property, fallback_value)

    def format_applescript_date_to_iso(self, date_str: str) -> Optional[str]:
        """Convert AppleScript date string to ISO format (delegates to formatters)."""
        return self.formatters.format_applescript_date_to_iso(date_str)

    def _parse_applescript_tags(self, tags_str: str) -> List[str]:
        """Parse AppleScript tag names list (delegates to formatters)."""
        return self.formatters.parse_applescript_tags(tags_str)

    def _build_things_url(self, action: str, parameters: Dict[str, Any]) -> str:
        """Build a Things URL scheme string (delegates to formatters)."""
        return self.formatters.build_things_url(action, parameters, self.auth_token)

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    async def update_project_direct(self, project_id: str, title: Optional[str] = None,
                                   notes: Optional[str] = None, tags: Optional[List[str]] = None,
                                   when: Optional[str] = None, deadline: Optional[str] = None,
                                   completed: Optional[bool] = None, canceled: Optional[bool] = None) -> Dict[str, Any]:
        """Update a project directly using AppleScript (no URL scheme).

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
            Dict with success status and result information
        """
        try:
            # Build the AppleScript to update the project
            script_parts = [
                'tell application "Things3"',
                '    try'
            ]

            # First check if project exists
            script_parts.extend([
                f'        set theProject to project id "{project_id}"',
                '        -- Project exists, proceed with updates'
            ])

            # Update title if provided
            if title is not None:
                escaped_title = title.replace('"', '\\"')
                script_parts.append(f'        set name of theProject to "{escaped_title}"')

            # Update notes if provided
            if notes is not None:
                escaped_notes = notes.replace('"', '\\"').replace('\n', '\\n')
                script_parts.append(f'        set notes of theProject to "{escaped_notes}"')

            # Handle status changes
            if completed is not None:
                if completed:
                    script_parts.append('        set status of theProject to completed')
                elif canceled is not None and canceled:
                    script_parts.append('        set status of theProject to canceled')
                else:
                    script_parts.append('        set status of theProject to open')
            elif canceled is not None:
                if canceled:
                    script_parts.append('        set status of theProject to canceled')
                else:
                    script_parts.append('        set status of theProject to open')

            # Handle tags if provided
            if tags is not None:
                # First clear existing tags, then add new ones
                script_parts.append('        set tag names of theProject to {}')
                if tags:
                    for tag in tags:
                        escaped_tag = tag.replace('"', '\\"')
                        script_parts.extend([
                            '        try',
                            f'            set theTag to tag named "{escaped_tag}"',
                            '        on error',
                            f'            set theTag to make new tag with properties {{name:"{escaped_tag}"}}',
                            '        end try',
                            '        set tag names of theProject to tag names of theProject & {theTag}'
                        ])

            # Handle scheduling if provided
            if when is not None:
                when_lower = when.lower()
                if when_lower == "today":
                    script_parts.append('        set start date of theProject to current date')
                elif when_lower == "tomorrow":
                    script_parts.append('        set start date of theProject to (current date) + 1 * days')
                elif when_lower == "evening":
                    script_parts.append('        set start date of theProject to current date')
                elif when_lower in ["anytime", "someday"]:
                    script_parts.append('        set start date of theProject to missing value')
                else:
                    # Try to parse as date string (YYYY-MM-DD) using locale-aware handler
                    try:
                        date_components = locale_handler.normalize_date_input(when)
                        if date_components:
                            year, month, day = date_components
                            date_expr = locale_handler.build_applescript_date_property(year, month, day)
                            script_parts.append(f'        set start date of theProject to ({date_expr})')
                        else:
                            logger.warning(f"Could not normalize when date: {when}")
                    except Exception as e:
                        logger.warning(f"Error parsing when date '{when}': {e}")

            # Handle deadline if provided
            if deadline is not None:
                try:
                    date_components = locale_handler.normalize_date_input(deadline)
                    if date_components:
                        year, month, day = date_components
                        date_expr = locale_handler.build_applescript_date_property(year, month, day)
                        script_parts.append(f'        set due date of theProject to ({date_expr})')
                    else:
                        logger.warning(f"Could not normalize deadline date: {deadline}")
                except Exception as e:
                    logger.warning(f"Error parsing deadline date '{deadline}': {e}")

            # Close the try block and handle errors
            script_parts.extend([
                '        return "success"',
                '    on error errMsg',
                '        if errMsg contains "Can\'t get project id" then',
                '            return "error:Project not found"',
                '        else',
                '            return "error:" & errMsg',
                '        end if',
                '    end try',
                'end tell'
            ])

            script = '\n'.join(script_parts)
            logger.debug(f"Executing project update script for project {project_id}")

            result = await self.executor.execute_script(script)

            if result.get("success"):
                output = result.get("output", "").strip()
                if output == "success":
                    return {
                        "success": True,
                        "message": "Project updated successfully",
                        "project_id": project_id
                    }
                elif output.startswith("error:"):
                    error_msg = output[6:]  # Remove "error:" prefix
                    return {
                        "success": False,
                        "error": error_msg
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Unexpected output: {output}"
                    }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown AppleScript error")
                }

        except Exception as e:
            logger.error(f"Error updating project {project_id}: {e}")
            return {
                "success": False,
                "error": f"Exception during update: {str(e)}"
            }

    def clear_cache(self) -> None:
        """Clear all cached results - no-op in hybrid implementation."""
        logger.info("Cache clearing requested but caching is disabled in hybrid implementation")

