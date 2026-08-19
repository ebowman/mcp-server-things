"""Diagnostic checks for the Things 3 MCP server ("doctor" subcommand).

This module implements a set of read-only diagnostic checks that verify the
local environment is correctly set up to run the Things 3 MCP server:
Things 3 installation, the app being running, macOS Automation (TCC)
permission, SQLite database readability (a separate TCC permission - Full
Disk Access), presence of ``uv``/``uvx`` on ``PATH``, the optional Things
URL-scheme auth token, and basic environment/version information.

Every check function here is pure with respect to the running process: none
of them start the FastMCP server, write to Things, or mutate any files.
They only shell out to read-only commands (``osascript ... get name``,
``mdfind``, ``shutil.which``) or read local files.

The CLI wiring in :mod:`things_mcp.main` is responsible for running these
checks, rendering the table, and choosing the process exit code.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Status values, in the order they should be considered for severity.
STATUS_PASS = "PASS"
STATUS_WARN = "WARN"
STATUS_FAIL = "FAIL"
STATUS_INFO = "INFO"

_OSASCRIPT_SHORT_TIMEOUT_SECS = 10
_DB_READ_TIMEOUT_SECS = 10.0

# Substring markers used to classify osascript/AppleScript failures.
_AUTOMATION_DENIED_MARKERS = (
    "-1743",
    "not authorized to send apple events",
)
_APP_NOT_RUNNING_MARKERS = (
    "-600",
    "application isn't running",
    "application is not running",
)
_DB_UNREADABLE_MARKER = "unable to open database file"

_TCC_HINT = (
    "Grant Full Disk Access to the process launching the server, or run the "
    "server via HTTP transport from Terminal - see README Troubleshooting "
    "'Reads fail but writes work'."
)


@dataclass
class CheckResult:
    """Result of a single doctor check.

    Attributes:
        name: Short human-readable name of the check (e.g. "Things 3 installed").
        status: One of PASS, WARN, FAIL, INFO.
        detail: One-line human-readable detail about the result.
        hint: One-line fix hint. Empty string when status is PASS and no
            hint is needed.
    """

    name: str
    status: str
    detail: str = ""
    hint: str = ""

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict representation."""
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "hint": self.hint,
        }


def _run_osascript(script: str, timeout: float = _OSASCRIPT_SHORT_TIMEOUT_SECS) -> subprocess.CompletedProcess:
    """Run an osascript -e command and return the CompletedProcess.

    Raises subprocess.TimeoutExpired if the command exceeds ``timeout``.
    """
    return subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def check_things_installed() -> CheckResult:
    """Check that Things 3 is installed.

    Checks the default Applications path first, then falls back to
    ``mdfind`` (Spotlight) by bundle identifier for non-default install
    locations.
    """
    name = "Things 3 installed"
    if Path("/Applications/Things3.app").exists():
        return CheckResult(name, STATUS_PASS, detail="/Applications/Things3.app found")

    try:
        result = subprocess.run(
            ["mdfind", "kMDItemCFBundleIdentifier == 'com.culturedcode.ThingsMac'"],
            capture_output=True,
            text=True,
            timeout=_OSASCRIPT_SHORT_TIMEOUT_SECS,
        )
        found = result.stdout.strip()
        if found:
            return CheckResult(name, STATUS_PASS, detail=found.splitlines()[0])
    except (subprocess.TimeoutExpired, OSError) as e:
        return CheckResult(
            name,
            STATUS_FAIL,
            detail=f"mdfind lookup failed: {e}",
            hint="Install Things 3 from culturedcode.com or the Mac App Store, then open it once.",
        )

    return CheckResult(
        name,
        STATUS_FAIL,
        detail="Things3.app not found in /Applications or via Spotlight",
        hint="Install Things 3 from culturedcode.com or the Mac App Store, then open it once.",
    )


def check_things_running() -> CheckResult:
    """Check whether Things 3 is currently running.

    Not running is a WARN (not FAIL) because the server auto-launches
    Things 3 on first call.
    """
    name = "Things 3 running"
    try:
        result = _run_osascript('application "Things3" is running')
    except subprocess.TimeoutExpired:
        return CheckResult(
            name,
            STATUS_WARN,
            detail="osascript timed out checking run state",
            hint="Open Things 3 manually and re-run doctor.",
        )
    except OSError as e:
        return CheckResult(
            name,
            STATUS_WARN,
            detail=f"osascript unavailable: {e}",
            hint="Open Things 3 manually and re-run doctor.",
        )

    output = (result.stdout or "").strip().lower()
    if output == "true":
        return CheckResult(name, STATUS_PASS, detail="Things 3 is running")

    return CheckResult(
        name,
        STATUS_WARN,
        detail="Things 3 is not running (server auto-launches it on first call)",
        hint="Open Things 3.",
    )


def check_automation_permission() -> CheckResult:
    """Check macOS Automation (TCC) permission for controlling Things 3."""
    name = "Automation permission"
    try:
        result = _run_osascript('tell application "Things3" to get name')
    except subprocess.TimeoutExpired:
        return CheckResult(
            name,
            STATUS_FAIL,
            detail=f"osascript timed out after {_OSASCRIPT_SHORT_TIMEOUT_SECS}s",
            hint="Things 3 may be unresponsive - open it manually and re-run doctor.",
        )
    except OSError as e:
        return CheckResult(
            name,
            STATUS_FAIL,
            detail=f"osascript unavailable: {e}",
            hint="Ensure /usr/bin/osascript is available (part of macOS).",
        )

    if result.returncode == 0:
        return CheckResult(name, STATUS_PASS, detail=f"AppleScript control works ({result.stdout.strip()})")

    stderr = (result.stderr or "").strip()
    lowered = stderr.lower()

    if any(marker in stderr or marker in lowered for marker in _AUTOMATION_DENIED_MARKERS):
        return CheckResult(
            name,
            STATUS_FAIL,
            detail=stderr or "Not authorized to send Apple events",
            hint=(
                "System Settings -> Privacy & Security -> Automation -> enable "
                "Things 3 for your terminal/host app."
            ),
        )

    if any(marker in lowered for marker in _APP_NOT_RUNNING_MARKERS):
        return CheckResult(
            name,
            STATUS_WARN,
            detail=stderr or "Things 3 is not running",
            hint="Open Things 3, then re-run doctor (see 'Things 3 running' check).",
        )

    return CheckResult(
        name,
        STATUS_FAIL,
        detail=stderr or f"osascript exited with code {result.returncode}",
        hint="See detail above for the raw AppleScript error.",
    )


def check_database_readable(timeout: float = _DB_READ_TIMEOUT_SECS) -> CheckResult:
    """Check that the Things SQLite database is readable via things.py.

    Runs the ``things`` package call in a background thread with a bounded
    timeout, since the underlying import/query can stall on TCC prompts or
    slow filesystem access.
    """
    name = "Database readable"

    result_holder: dict = {}

    def _target():
        try:
            from .things_import import get_things

            things_mod = get_things()
            todos = things_mod.todos(status="incomplete")
            result_holder["count"] = len(todos)
        except Exception as e:  # noqa: BLE001 - surfaced to caller via result_holder
            result_holder["error"] = e

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(timeout)

    if thread.is_alive():
        return CheckResult(
            name,
            STATUS_WARN,
            detail=f"Database read timed out after {timeout}s",
            hint=(
                "Large database or first Spotlight scan - re-run doctor; if it keeps "
                "timing out (especially alongside 'unable to open database file' "
                "symptoms), see README Troubleshooting 'Reads fail but writes work'."
            ),
        )

    if "error" in result_holder:
        error = result_holder["error"]
        message = str(error)
        if _DB_UNREADABLE_MARKER in message.lower():
            return CheckResult(
                name,
                STATUS_FAIL,
                detail=message,
                hint=_TCC_HINT,
            )
        return CheckResult(
            name,
            STATUS_FAIL,
            detail=message,
            hint="Unexpected error reading the Things database - see detail above.",
        )

    count = result_holder.get("count", 0)
    return CheckResult(name, STATUS_PASS, detail=f"{count} incomplete todo(s) readable")


def check_uv_installed() -> CheckResult:
    """Check whether uv/uvx is on PATH. Never FAILs - WARN only."""
    name = "uv/uvx on PATH"
    path = shutil.which("uvx")
    if path:
        return CheckResult(name, STATUS_PASS, detail=path)
    return CheckResult(
        name,
        STATUS_WARN,
        detail="uvx not found on PATH",
        hint="brew install uv",
    )


def _auth_token_paths() -> List[Path]:
    """Return the auth-token file search paths, matching AppleScriptManager._load_auth_token."""
    # Path from src/things_mcp/doctor.py -> things_mcp -> src -> project root
    project_root = Path(__file__).parent.parent.parent
    return [
        project_root / ".things-auth",
        project_root / "things-auth.txt",
        Path.home() / ".things-auth",
    ]


def check_auth_token() -> CheckResult:
    """Check for a Things URL-scheme auth token file. INFO only - never FAIL/WARN."""
    name = "Auth token file"
    for auth_file in _auth_token_paths():
        if auth_file.exists():
            return CheckResult(name, STATUS_INFO, detail=f"token configured ({auth_file})")

    return CheckResult(
        name,
        STATUS_INFO,
        detail="no auth token file found",
        hint=(
            "Only needed for URL-scheme features. Things -> Settings -> General -> "
            "Enable Things URLs -> Manage."
        ),
    )


def check_environment() -> CheckResult:
    """Report Python, fastmcp, things.py, and server versions. Always INFO.

    The ``things`` package version is read from ``sys.modules`` without
    importing it. ``things`` performs an unbounded filesystem glob at import
    time (the same stall that :func:`check_database_readable` guards against
    with a bounded background-thread timeout); if that check's worker thread
    is still stuck inside the import when this check runs, a bare
    ``import things`` here would block on Python's per-module import lock
    with no timeout of its own, hanging doctor on exactly the machines it
    exists to diagnose. Reading ``sys.modules`` instead is a non-blocking
    probe: if the import already completed (in this process - e.g. via the
    database-readable check, which runs before this check in
    :func:`run_all_checks`), the version is available; otherwise (not yet
    imported, still stalled, or failed) we report "unknown (import not
    completed)" without triggering an import ourselves.
    """
    name = "Environment"
    py_version = sys.version.split()[0]

    try:
        import fastmcp

        fastmcp_version = getattr(fastmcp, "__version__", "unknown")
    except Exception:  # noqa: BLE001 - version probe only
        fastmcp_version = "not installed"

    things_pkg = sys.modules.get("things")
    if things_pkg is not None:
        things_version = getattr(things_pkg, "__version__", "unknown")
    else:
        things_version = "unknown (import not completed)"

    from . import __version__ as server_version

    detail = (
        f"python={py_version} fastmcp={fastmcp_version} "
        f"things={things_version} mcp-server-things={server_version}"
    )
    return CheckResult(name, STATUS_INFO, detail=detail)


def run_all_checks(db_timeout: float = _DB_READ_TIMEOUT_SECS) -> List[CheckResult]:
    """Run all doctor checks in order and return their results."""
    return [
        check_things_installed(),
        check_things_running(),
        check_automation_permission(),
        check_database_readable(timeout=db_timeout),
        check_uv_installed(),
        check_auth_token(),
        check_environment(),
    ]


def has_failure(results: List[CheckResult]) -> bool:
    """Return True if any result has status FAIL."""
    return any(r.status == STATUS_FAIL for r in results)


_STATUS_COLORS = {
    STATUS_PASS: "\033[32m",  # green
    STATUS_WARN: "\033[33m",  # yellow
    STATUS_FAIL: "\033[31m",  # red
    STATUS_INFO: "\033[36m",  # cyan
}
_COLOR_RESET = "\033[0m"


def format_table(results: List[CheckResult], use_color: Optional[bool] = None) -> str:
    """Render results as an aligned text table with hints on non-PASS rows.

    Args:
        results: Check results to render.
        use_color: Force color on/off. If None, colors are used only when
            stdout is a tty.
    """
    if use_color is None:
        use_color = sys.stdout.isatty()

    name_width = max((len(r.name) for r in results), default=4)
    status_width = max((len(r.status) for r in results), default=6)

    lines = []
    for r in results:
        status_text = r.status.ljust(status_width)
        if use_color:
            color = _STATUS_COLORS.get(r.status, "")
            status_text = f"{color}{status_text}{_COLOR_RESET}"
        line = f"{r.name.ljust(name_width)}  {status_text}  {r.detail}"
        lines.append(line)
        if r.status != STATUS_PASS and r.hint:
            lines.append(f"{' ' * (name_width + 2)}{' ' * status_width}  -> {r.hint}")

    fail_count = sum(1 for r in results if r.status == STATUS_FAIL)
    warn_count = sum(1 for r in results if r.status == STATUS_WARN)
    if fail_count:
        summary = f"{fail_count} FAIL, {warn_count} WARN - fix FAILs above before using the server."
    elif warn_count:
        summary = f"0 FAIL, {warn_count} WARN - server should work; review warnings above."
    else:
        summary = "All checks passed."

    lines.append("")
    lines.append(summary)
    return "\n".join(lines)


def results_to_json(results: List[CheckResult]) -> dict:
    """Return a machine-readable dict for --json output."""
    return {
        "ok": not has_failure(results),
        "checks": [r.to_dict() for r in results],
    }


def run_doctor(json_output: bool = False, db_timeout: float = _DB_READ_TIMEOUT_SECS) -> int:
    """Run all checks, print output, and return the process exit code.

    Args:
        json_output: If True, print machine-readable JSON instead of the table.
        db_timeout: Timeout in seconds for the database-readable check.

    Returns:
        0 if no check has status FAIL, else 1.
    """
    results = run_all_checks(db_timeout=db_timeout)

    if json_output:
        import json

        print(json.dumps(results_to_json(results), indent=2))
    else:
        print(format_table(results))

    return 1 if has_failure(results) else 0
