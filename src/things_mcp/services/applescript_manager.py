"""AppleScript manager for Things 3 integration.

This module serves as a facade that delegates to specialized modules:
- executor: AppleScript execution with locking and retry
- formatters: Date/tag/URL formatting
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

    # NOTE: process-wide AppleScript serialization actually lives in
    # AppleScriptExecutor's per-event-loop lock (services/applescript/executor.py, _get_lock() since hq-yxu),
    # which IS acquired around every osascript call. A duplicate lock used
    # to be declared here too, but it was never acquired anywhere in this
    # class (dead code) - removed (hq-c7a).

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
        self.auth_token, self._auth_token_trace = self._load_auth_token()

        # Initialize specialized modules
        self.executor = AppleScriptExecutor(timeout=timeout, retry_count=retry_count)
        self.formatters = AppleScriptFormatters()

        logger.info("AppleScript manager initialized - cache removed for hybrid implementation")

    @staticmethod
    def _display_path(path: Path) -> str:
        """Render a candidate auth-token path for the resolution trace,
        abbreviating the home directory to '~' the way shells display it.
        Never logged/returned with file contents - path only."""
        try:
            return "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            return str(path)

    def _load_auth_token(self) -> Tuple[Optional[str], List[Dict[str, str]]]:
        """Load Things auth token from file if it exists.

        Returns a ``(token, trace)`` tuple. ``trace`` is a list of
        ``{"path": <str>, "status": <matched|empty|missing|unreadable>}``
        dicts, one per candidate path in search order - never the token
        value itself, so it is safe to surface to callers/consumers (e.g.
        the ``checked_paths`` field on ``AUTH_TOKEN_NOT_CONFIGURED``).
        """
        # Path from services/applescript_manager.py -> services -> things_mcp -> src -> project root
        project_root = Path(__file__).parent.parent.parent.parent
        auth_files = [
            project_root / '.things-auth',
            project_root / 'things-auth.txt',
            Path.home() / '.things-auth'
        ]

        trace: List[Dict[str, str]] = []
        found_token: Optional[str] = None

        for auth_file in auth_files:
            display = self._display_path(auth_file)
            if not auth_file.exists():
                trace.append({"path": display, "status": "missing"})
                continue

            try:
                token = auth_file.read_text().strip()
                # Handle format: THINGS_AUTH_TOKEN=xxx or just xxx
                if '=' in token:
                    token = token.split('=', 1)[1].strip()
                if not token:
                    # Empty/whitespace-only token file: treat as missing and
                    # keep looking at the remaining candidate paths.
                    logger.warning(f"Auth token file {auth_file} is empty - treating as missing")
                    trace.append({"path": display, "status": "empty"})
                    continue
                logger.info(f"Loaded Things auth token from {auth_file}")
                trace.append({"path": display, "status": "matched"})
                found_token = token
                break
            except Exception as e:
                logger.warning(f"Failed to read auth token from {auth_file}: {e}")
                trace.append({"path": display, "status": "unreadable"})

        if found_token is None:
            logger.debug("No Things auth token found - will use direct AppleScript execution")

        return found_token, trace

    def reload_auth_token_if_missing(self) -> Optional[str]:
        """Reload the auth token from disk if none is currently loaded.

        Side-effect-free when a token is already loaded (no-op, returns it
        immediately) - a token is never unloaded mid-flight, so the only
        cost is a redundant file read per gated call while genuinely
        unconfigured. Call this immediately before failing an
        auth-required action so a token file created (or fixed) after this
        manager was constructed is picked up without a server restart.

        Defensive against being called on a test double whose
        ``_load_auth_token`` is itself mocked (e.g.
        ``MagicMock(spec=AppleScriptManager)``) and therefore doesn't
        return the real ``(token, trace)`` tuple shape - in that case this
        leaves ``self.auth_token``/``self._auth_token_trace`` untouched
        rather than raising, so existing tests that stub a manager and set
        ``.auth_token`` directly are unaffected.
        """
        if self.auth_token:
            return self.auth_token
        try:
            loaded = self._load_auth_token()
            token, trace = loaded
        except (TypeError, ValueError):
            # Not a real (token, trace) tuple - e.g. a mocked
            # _load_auth_token on a test double. Leave state untouched.
            return self.auth_token
        self.auth_token = token
        self._auth_token_trace = trace
        return self.auth_token

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
                # Reload-on-miss: a token file created (or fixed) after this
                # manager was constructed is picked up here, so a missing
                # token no longer requires a server restart to start
                # working.
                self.reload_auth_token_if_missing()

            if action in AUTH_REQUIRING_ACTIONS and not self.auth_token:
                logger.warning(
                    f"Refusing to execute Things URL-scheme action '{action}' "
                    "without an auth token"
                )
                return {
                    "success": False,
                    "error": "AUTH_TOKEN_NOT_CONFIGURED",
                    "message": "Things URL-scheme auth token not configured",
                    "hint": AUTH_TOKEN_HINT,
                    "checked_paths": getattr(self, "_auth_token_trace", []),
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

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        return datetime.now().isoformat()

    def clear_cache(self) -> None:
        """Clear all cached results - no-op in hybrid implementation."""
        logger.info("Cache clearing requested but caching is disabled in hybrid implementation")

