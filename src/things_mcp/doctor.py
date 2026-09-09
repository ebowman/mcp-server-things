"""Diagnostic checks for the Things 3 MCP server ("doctor" subcommand).

This module implements a set of read-only diagnostic checks that verify the
local environment is correctly set up to run the Things 3 MCP server:
Things 3 installation, the app being running, macOS Automation (TCC)
permission, SQLite database readability (a separate TCC permission - Full
Disk Access), presence of ``uv``/``uvx`` on ``PATH``, whether the running
Python interpreter's architecture matches the host CPU (Rosetta detection),
the optional Things URL-scheme auth token, and basic environment/version
information.

Every check function here is pure with respect to the running process: none
of them start the FastMCP server, write to Things, or mutate any files.
They only shell out to read-only commands (``osascript ... get name``,
``mdfind``, ``shutil.which``) or read local files.

The CLI wiring in :mod:`things_mcp.main` is responsible for running these
checks, rendering the table, and choosing the process exit code.
"""

from __future__ import annotations

import errno
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
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
    "server via HTTP transport from Terminal - see docs/MACOS_PERMISSIONS.md."
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

            # Pre-open check: a direct, read-only open() of the database file
            # classifies a TCC (Full Disk Access) denial distinctly from a
            # generic "unable to open database file" sqlite3 error string,
            # and distinguishes a missing database from a permissions denial.
            # db_path is initialized before the lookup so the except handlers
            # below never reference an unbound name if resolving the path
            # itself (things_mod.database.Database().filepath) is what raises.
            db_path = None
            try:
                db_path = things_mod.database.Database().filepath
                with open(db_path, "rb"):
                    pass
            except PermissionError as e:
                path_desc = db_path if db_path is not None else "Things database path could not be resolved"
                errno_value = getattr(e, "errno", None)
                if errno_value in (errno.EPERM, errno.EACCES):
                    result_holder["preopen_fail"] = (
                        "tcc",
                        f"macOS privacy (TCC) denied access to {path_desc}: {e}",
                    )
                else:
                    result_holder["preopen_fail"] = (
                        "other",
                        f"Permission denied opening {path_desc}: {e}",
                    )
                return
            except FileNotFoundError as e:
                if db_path is not None:
                    message = f"Things database not found at {db_path}: {e}"
                else:
                    message = f"Things database path could not be resolved: {e}"
                result_holder["preopen_fail"] = ("not_found", message)
                return

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
                "symptoms), see docs/MACOS_PERMISSIONS.md."
            ),
        )

    if "preopen_fail" in result_holder:
        kind, message = result_holder["preopen_fail"]
        if kind == "tcc":
            return CheckResult(name, STATUS_FAIL, detail=message, hint=_TCC_HINT)
        if kind == "not_found":
            return CheckResult(
                name,
                STATUS_FAIL,
                detail=message,
                hint="Ensure Things 3 has been opened at least once and has created its database.",
            )
        return CheckResult(
            name,
            STATUS_FAIL,
            detail=message,
            hint="Unexpected error opening the Things database - see detail above.",
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


def _hardware_is_apple_silicon(interpreter_machine: str) -> bool:
    """Return True if the underlying hardware is Apple Silicon.

    ``platform.machine()`` reports the architecture of the *running
    interpreter*, not the hardware, when running under Rosetta 2 - an
    x86_64 Python on Apple Silicon still reports ``x86_64``. To detect the
    real hardware we shell out to ``sysctl -n hw.optional.arm64``, which
    returns ``"1"`` on Apple Silicon (even under Rosetta) and errors or is
    absent on genuine Intel Macs. Any failure is treated as "not Apple
    Silicon" (i.e. assume Intel) since that's the conservative choice for a
    read-only diagnostic that must never raise.
    """
    if interpreter_machine == "arm64":
        return True
    try:
        result = subprocess.run(
            ["sysctl", "-n", "hw.optional.arm64"],
            capture_output=True,
            text=True,
            timeout=_OSASCRIPT_SHORT_TIMEOUT_SECS,
        )
        return result.stdout.strip() == "1"
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return False


def check_python_architecture() -> CheckResult:
    """Check whether the running Python interpreter matches the host CPU architecture.

    ``uvx`` can select an x86_64 (Rosetta) Python on Apple Silicon Macs if
    that interpreter happens to be first on ``PATH`` (e.g. a Rosetta-mode
    miniconda). Transitive dependencies such as ``cryptography>=50`` ship no
    macOS x86_64 wheels, so ``uv`` falls back to a source build that fails
    without Rust/OpenSSL toolchains installed. This check never FAILs - a
    mismatch is only a WARN, since the server itself is not broken, just
    slower/riskier to install in that configuration.
    """
    name = "Python architecture"
    interpreter_machine = platform.machine()
    apple_silicon = _hardware_is_apple_silicon(interpreter_machine)

    if apple_silicon and interpreter_machine != "arm64":
        return CheckResult(
            name,
            STATUS_WARN,
            detail="Python is x86_64 (Rosetta) on Apple Silicon",
            hint=(
                "Transitive deps (e.g. cryptography>=50) ship no macOS x86_64 wheels; "
                "use an arm64 Python - e.g. 'uvx -p 3.12 mcp-server-things' with a "
                "Homebrew/uv-managed arm64 interpreter"
            ),
        )

    if apple_silicon:
        detail = f"Python is {interpreter_machine}, matching Apple Silicon hardware"
    else:
        detail = (
            f"Python is {interpreter_machine}, matching Intel hardware "
            "(note: some transitive deps like cryptography>=50 no longer ship macOS x86_64 wheels)"
        )
    return CheckResult(name, STATUS_PASS, detail=detail)


_UV_MANAGED_MARKER = "/uv/python/"
_PYTHON_FRAMEWORK_MARKER = "/Python.framework/"

_DRAG_DROP_HINT = (
    "If the file is greyed out in the picker, drag it from a Finder window onto "
    "the list instead (never via a drag-shelf/clipboard utility - it can stamp a "
    "quarantine flag that makes the binary stop launching)."
)


def check_interpreter_identity() -> CheckResult:
    """Report the interpreter *running doctor* and classify it for TCC purposes.

    macOS's TCC (Transparency, Consent, and Control) privacy system keys the
    "App Data" (Full Disk Access-adjacent) grant to the specific on-disk
    binary that requests it - not to a launching parent app such as Claude
    Desktop. This check reports ``os.path.realpath(sys.executable)`` for
    *this* process (always resolving through any symlink, e.g. a venv's
    ``bin/python``) and classifies it so the operator understands what kind
    of interpreter is running doctor right now, and whether a grant made to
    it would survive an interpreter upgrade.

    Note this is the interpreter running *doctor itself* - when doctor is
    run from a terminal, that is very often a different interpreter than
    the one Claude Desktop actually launches (e.g. a venv vs the Homebrew
    framework Python Claude Desktop's config points at). See the
    "Claude Desktop interpreter" check below for the interpreter Claude
    Desktop will actually run and grant Full Disk Access to.

    - ``uv-managed``: path lives under a ``.../uv/python/...`` directory
      (e.g. ``~/.local/share/uv/python/cpython-3.12.11-.../bin/python3.12``).
      The path embeds the exact patch version, so upgrading the uv-managed
      interpreter changes the path and the TCC grant must be redone.
    - ``venv``: ``sys.prefix != sys.base_prefix`` (a virtualenv's own
      ``bin/python``, which is typically a symlink resolved by realpath to
      the base interpreter - reported here as a fallback classification
      when the resolved path also isn't identifiable as uv-managed or
      framework).
    - ``framework``: path lives under a ``Python.framework`` bundle. A
      framework *build* of Python has a ``Python.app`` with stable bundle id
      ``org.python.python``, but live evidence (hq-gxt.7/hq-gxt.10, macOS
      26.6) shows the bare interpreter binary this check resolves to (e.g.
      ``.../Versions/3.13/bin/python3.13``) is a separately ad-hoc-signed
      stub (``codesign -dv`` reports its own ``Identifier``, distinct from
      ``org.python.python``) - TCC keyed a fresh, path-scoped app-data grant
      to it on every one of three observed Homebrew ``python@3.13`` patch
      upgrades, and the pre-existing ``org.python.python`` grant did not
      cover it. There is no known upgrade-proof identity for a bare
      interpreter binary, framework or otherwise; every classification below
      is keyed by realpath and must be re-granted after that interpreter is
      upgraded.
    - ``other``: none of the above.

    This check never FAILs - it is purely informational. ``uv-managed`` and
    ``framework`` report STATUS_WARN because their realpaths embed the
    interpreter's patch/formula version, so the Full Disk Access grant (keyed
    by resolved path) must be redone after every interpreter upgrade; ``venv``
    and ``other`` report STATUS_PASS.
    """
    name = "Interpreter identity"
    realpath = os.path.realpath(sys.executable)

    if _UV_MANAGED_MARKER in realpath:
        kind = "uv-managed"
    elif sys.prefix != sys.base_prefix:
        kind = "venv"
    elif _PYTHON_FRAMEWORK_MARKER in realpath:
        kind = "framework"
    else:
        kind = "other"

    # Consult the shared/memoized Claude Desktop resolution (order-independent
    # with check_claude_desktop_interpreter, and the uvx probe runs at most
    # once per process even if both checks run). If Claude Desktop launches a
    # *different* interpreter than the one running doctor right now, demote
    # this check to INFO with no grant instruction at all - granting Full
    # Disk Access to the wrong (doctor-only) interpreter is exactly the
    # recurring-TCC-prompt failure mode this bead fixes (hq-gxt/hq-gxt.13).
    claude_data = _resolve_claude_desktop_targets()
    claude_resolved_paths = [r for (_, _, _, r) in claude_data.get("results", []) if r]

    if claude_resolved_paths and realpath not in claude_resolved_paths:
        detail = (
            f"this is the interpreter running doctor ({kind}): {realpath}. It is NOT "
            "the one Claude Desktop launches - do not grant it Full Disk Access for "
            'the Things MCP server; see "Claude Desktop interpreter" below.'
        )
        return CheckResult(name, STATUS_INFO, detail=detail)

    lines = [f"interpreter={realpath} ({kind})", f"Grant Full Disk Access to: {realpath}"]
    if kind == "framework":
        lines.append(
            "Framework Python.app has a stable bundle id (org.python.python), but live "
            "evidence shows the bare interpreter binary is a separately ad-hoc-signed "
            "stub not covered by it - this grant must be redone after a patch upgrade too. "
            "WARNING: a Homebrew-installed framework interpreter's path embeds the "
            "formula version (e.g. Cellar/python@3.13/3.13.15) - the Full Disk Access "
            "grant must be redone after each brew upgrade."
        )
    elif kind == "uv-managed":
        lines.append(
            "WARNING: this path embeds the interpreter patch version - the Full Disk "
            "Access grant must be redone after any uv-managed interpreter upgrade."
        )

    # Framework realpaths also end in a patch-version segment (e.g. .../3.13/
    # bin/python3.13) and hit the same Launch Services "greyed out" picker bug
    # as uv-managed/venv/other paths (hq-gxt.9 reviewer nit) - the hint applies
    # to every classification, not just uv-managed/venv/other.
    lines.append(_DRAG_DROP_HINT)

    status = STATUS_WARN if kind in ("uv-managed", "framework") else STATUS_PASS
    return CheckResult(name, status, detail=" | ".join(lines))


def _walk_ppid_chain(max_levels: int = 6) -> List[str]:
    """Walk the parent-process chain via ``ps``, returning each ancestor's comm.

    Starts at the current process's parent (``os.getppid()``) and walks up
    to ``max_levels`` ancestors, using ``ps -o ppid=,comm= -p <pid>`` to read
    each process's own parent pid and command name. Returns as many comm
    strings as could be read; a ``ps`` failure at any level stops the walk
    (and any levels already read are still returned) rather than raising.
    """
    comms: List[str] = []
    pid = os.getppid()
    for _ in range(max_levels):
        try:
            result = subprocess.run(
                ["ps", "-o", "ppid=,comm=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=_OSASCRIPT_SHORT_TIMEOUT_SECS,
            )
        except (subprocess.TimeoutExpired, OSError):
            break

        line = (result.stdout or "").strip()
        if not line or result.returncode != 0:
            break

        parts = line.split(None, 1)
        if not parts:
            break

        try:
            next_pid = int(parts[0])
        except ValueError:
            break

        comm = parts[1].strip() if len(parts) > 1 else ""
        comms.append(comm)

        if next_pid <= 1:
            break
        pid = next_pid

    return comms


def check_launch_parent() -> CheckResult:
    """Detect whether the server was launched via Claude Desktop's disclaimer helper.

    Claude Desktop launches MCP servers via
    ``Claude.app/Contents/Helpers/disclaimer``, which means TCC grants made
    to Claude Desktop itself do not extend to the launched Python
    interpreter - the interpreter is its own TCC principal and needs its
    own Full Disk Access grant (see :func:`check_interpreter_identity`).
    This check walks the parent-process chain looking for that helper.
    """
    name = "Launch parent"
    try:
        comms = _walk_ppid_chain()
    except Exception as e:  # noqa: BLE001 - never crash doctor over a diagnostic probe
        return CheckResult(
            name,
            STATUS_INFO,
            detail=f"could not determine launch parent: {e}",
        )

    if not comms:
        return CheckResult(
            name,
            STATUS_INFO,
            detail="could not determine launch parent (ps produced no output)",
        )

    for comm in comms:
        if "Claude.app/Contents/Helpers/disclaimer" in comm:
            return CheckResult(
                name,
                STATUS_WARN,
                detail=f"launched via {comm}",
                hint=(
                    "TCC grants made to Claude Desktop do not apply to this process - "
                    "the Python interpreter itself needs Full Disk Access. See the "
                    "'Interpreter identity' check above for the exact path to grant."
                ),
            )

    return CheckResult(name, STATUS_INFO, detail=f"launch chain: {' <- '.join(comms)}")


# ---------------------------------------------------------------------------
# check_claude_desktop_interpreter
# ---------------------------------------------------------------------------

_CLAUDE_DESKTOP_CONFIG_PATH = (
    Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
)
_CLAUDE_EXTENSIONS_DIR = Path.home() / "Library" / "Application Support" / "Claude" / "Claude Extensions"
_THINGS_ENTRY_MARKERS = ("things_mcp", "mcp-server-things")
_UVX_PYTHON_SELECT_FLAGS = ("--python", "--python-preference", "-p")
_UVX_REALPATH_PROBE_CODE = "import os,sys;print(os.path.realpath(sys.executable))"
_UVX_PROBE_TOTAL_BUDGET_SECS = 35.0
_UVX_PROBE_SINGLE_TIMEOUT_SECS = 30.0


def _entry_matches_things(command: str, args: List[str]) -> bool:
    """Return True if this mcpServers entry looks like it launches this server."""
    haystacks = [command] + [a for a in args if isinstance(a, str)]
    lowered = [h.lower() for h in haystacks if isinstance(h, str)]
    return any(marker in h for h in lowered for marker in _THINGS_ENTRY_MARKERS)


def _extract_uvx_python_flags(args: List[str]) -> List[str]:
    """Keep only interpreter-selection flags (and their values) from a uvx arg list.

    Handles both split form (``--python``, ``3.13``) and inline ``=`` form
    (``--python=3.13``) - the latter is kept as a single whole token.
    """
    flags: List[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in _UVX_PYTHON_SELECT_FLAGS:
            flags.append(arg)
            if i + 1 < len(args):
                flags.append(str(args[i + 1]))
                i += 1
        elif isinstance(arg, str) and "=" in arg and arg.split("=", 1)[0] in _UVX_PYTHON_SELECT_FLAGS:
            flags.append(arg)
        i += 1
    return flags


def _resolve_uvx_entry(
    label: str, command: str, args: List[str], deadline: float
) -> tuple:
    """Resolve the interpreter a uvx/uv entry would select, via a probe subprocess.

    Returns (status, detail_line, hint_line_or_empty, resolved_path_or_None).
    """
    python_flags = _extract_uvx_python_flags(args)
    probe_cmd = [command] + python_flags + ["python", "-c", _UVX_REALPATH_PROBE_CODE]
    manual_cmd = " ".join(probe_cmd)

    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return (
            STATUS_INFO,
            f"{label}: uvx resolution skipped (time budget exhausted) - run manually: {manual_cmd}",
            "",
            None,
        )

    timeout = min(_UVX_PROBE_SINGLE_TIMEOUT_SECS, remaining)
    try:
        result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as e:
        return (
            STATUS_INFO,
            f"{label}: could not resolve uvx-selected interpreter ({e}) - run manually: {manual_cmd}",
            "",
            None,
        )

    stdout = (result.stdout or "").strip()
    if result.returncode != 0 or not stdout:
        stderr = (result.stderr or "").strip()
        return (
            STATUS_INFO,
            f"{label}: uvx probe exited {result.returncode} ({stderr or 'no output'}) - run manually: {manual_cmd}",
            "",
            None,
        )

    resolved = stdout.splitlines()[-1].strip()
    return _classify_resolved_interpreter(label, resolved)


def _resolve_plain_entry(label: str, command: str) -> tuple:
    """Resolve the interpreter a non-uvx mcpServers entry would run.

    Returns (status, detail_line, hint_line_or_empty, resolved_path_or_None).
    """
    expanded = os.path.expanduser(os.path.expandvars(command))
    if not os.path.isabs(expanded):
        which_path = shutil.which(expanded)
        if which_path:
            expanded = which_path

    resolved = os.path.realpath(expanded)
    if not os.path.exists(resolved):
        return (
            STATUS_WARN,
            f"{label}: command not found ({command} -> {resolved})",
            f"Configured command '{command}' does not resolve to an existing file.",
            None,
        )

    return _classify_resolved_interpreter(label, resolved)


_ALLOW_DIALOG_DOES_NOT_PERSIST = (
    'Clicking Allow on the "would like to access data from other apps" dialog does not '
    "persist for an interpreter launched by Claude Desktop - only Full Disk Access on "
    "this file stops the dialog (verified macOS 26.6)."
)


def _classify_resolved_interpreter(label: str, resolved: str) -> tuple:
    """Compare a resolved Claude-Desktop-launched interpreter to this process's own.

    Returns (status, detail_line, hint_line_or_empty, resolved_path).
    """
    own_realpath = os.path.realpath(sys.executable)
    if resolved == own_realpath:
        return (
            STATUS_PASS,
            f"GRANT FULL DISK ACCESS TO THIS FILE: {resolved}. {label}: Claude Desktop "
            f"will run: {resolved} (same as this process). {_ALLOW_DIALOG_DOES_NOT_PERSIST}",
            "",
            resolved,
        )

    return (
        STATUS_WARN,
        f"GRANT FULL DISK ACCESS TO THIS FILE: {resolved}. {label}: Claude Desktop will "
        f"run: {resolved}",
        (
            f"This differs from the interpreter running doctor ({own_realpath}) - Full Disk "
            f"Access must be granted to the Claude Desktop path ({resolved}), not the doctor "
            "path, or the app-data TCC prompt will keep recurring after a Claude Desktop "
            f"restart. {_ALLOW_DIALOG_DOES_NOT_PERSIST} " + _DRAG_DROP_HINT
        ),
        resolved,
    )


def _iter_things_entries() -> List[tuple]:
    """Yield (label, command, args) for every things-matching entry found.

    Reads ``claude_desktop_config.json`` (``mcpServers``) and every installed
    ``.mcpb`` extension's ``manifest.json`` (``server.mcp_config``). Read-only;
    any parse/read failure for either source is silently skipped (an absent
    or unparsable config is reported by the caller as INFO, not a crash).
    """
    entries: List[tuple] = []

    import json as _json

    try:
        with open(_CLAUDE_DESKTOP_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = _json.load(f)
        for name, entry in (config.get("mcpServers") or {}).items():
            command = entry.get("command") if isinstance(entry, dict) else None
            args = entry.get("args") if isinstance(entry, dict) else None
            if not isinstance(command, str) or not isinstance(args, list):
                continue
            if _entry_matches_things(command, args):
                entries.append((f"claude_desktop_config.json[{name}]", command, args))
    except (OSError, ValueError):
        pass

    try:
        if _CLAUDE_EXTENSIONS_DIR.is_dir():
            for child in _CLAUDE_EXTENSIONS_DIR.iterdir():
                manifest_path = child / "manifest.json"
                if not manifest_path.is_file():
                    continue
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = _json.load(f)
                except (OSError, ValueError):
                    continue
                mcp_config = (
                    manifest.get("server", {}).get("mcp_config", {})
                    if isinstance(manifest.get("server"), dict)
                    else {}
                )
                command = mcp_config.get("command")
                args = mcp_config.get("args")
                if not isinstance(command, str) or not isinstance(args, list):
                    continue
                if _entry_matches_things(command, args) or "mcp-server-things" in str(
                    manifest.get("name", "")
                ).lower():
                    entries.append((f"Claude Extensions/{child.name}/manifest.json", command, args))
    except OSError:
        pass

    return entries


_claude_desktop_targets_cache: Optional[dict] = None


def _reset_claude_desktop_targets_cache() -> None:
    """Test-only: clear the memoized Claude Desktop resolution.

    Production code never needs to call this - the resolution is stable for
    the life of a single doctor invocation (a fresh process each run), so
    memoizing it for the whole process is safe. Tests that monkeypatch the
    config path/subprocess between cases must call this to avoid observing a
    stale result from a previous test.
    """
    global _claude_desktop_targets_cache
    _claude_desktop_targets_cache = None


def _resolve_claude_desktop_targets() -> dict:
    """Resolve every Claude-Desktop-launched interpreter entry, once per process.

    Shared by :func:`check_interpreter_identity` and
    :func:`check_claude_desktop_interpreter` so check *order* never matters
    (either check can run first and both see the same resolution) and the
    potentially slow ``uvx``/``uv`` probe subprocess runs at most once per
    process no matter how many checks consult it. The result is memoized in
    a module-level cache for the remainder of the process.

    Returns a dict:
      - ``entries_found`` (bool): whether any things-matching mcpServers/
        mcp_config entry was found.
      - ``no_entries_detail`` (str | None): ready-made INFO detail text to
        use when ``entries_found`` is False.
      - ``error`` (str | None): set (with ``entries_found`` False) if reading
        the config itself raised.
      - ``results`` (list of (status, detail, hint, resolved_path_or_None)):
        one tuple per matching entry, only meaningful when ``entries_found``
        is True.
    """
    global _claude_desktop_targets_cache
    if _claude_desktop_targets_cache is not None:
        return _claude_desktop_targets_cache

    try:
        entries = _iter_things_entries()
    except Exception as e:  # noqa: BLE001 - never crash doctor over a diagnostic probe
        _claude_desktop_targets_cache = {
            "entries_found": False,
            "no_entries_detail": None,
            "error": str(e),
            "results": [],
        }
        return _claude_desktop_targets_cache

    if not entries:
        if not _CLAUDE_DESKTOP_CONFIG_PATH.exists():
            detail = (
                f"claude_desktop_config.json not found at {_CLAUDE_DESKTOP_CONFIG_PATH}, "
                "and no matching .mcpb extension manifest found"
            )
        else:
            detail = (
                "no 'things_mcp'/'mcp-server-things' entry found in "
                "claude_desktop_config.json or any installed .mcpb extension"
            )
        _claude_desktop_targets_cache = {
            "entries_found": False,
            "no_entries_detail": detail,
            "error": None,
            "results": [],
        }
        return _claude_desktop_targets_cache

    deadline = time.monotonic() + _UVX_PROBE_TOTAL_BUDGET_SECS
    results = []
    for label, command, args in entries:
        basename = os.path.basename(command).lower()
        if basename in ("uvx", "uv"):
            results.append(_resolve_uvx_entry(label, command, args, deadline))
        else:
            results.append(_resolve_plain_entry(label, command))

    _claude_desktop_targets_cache = {
        "entries_found": True,
        "no_entries_detail": None,
        "error": None,
        "results": results,
    }
    return _claude_desktop_targets_cache


def check_claude_desktop_interpreter() -> CheckResult:
    """Resolve the interpreter(s) Claude Desktop will actually launch for this server.

    Reads ``~/Library/Application Support/Claude/claude_desktop_config.json``
    and any installed ``.mcpb`` extension manifest, finds every
    ``mcpServers``/``mcp_config`` entry that looks like it launches this
    server (command or any arg containing ``things_mcp`` or
    ``mcp-server-things``, case-insensitive), and resolves the interpreter
    each one would actually run - via a bounded ``uvx``/``uv`` probe
    subprocess for those entries, or plain path resolution otherwise. WARNs
    when a resolved interpreter differs from the one running doctor (the
    common failure mode: Full Disk Access granted to the wrong binary).

    Uses :func:`_resolve_claude_desktop_targets` (shared/memoized with
    :func:`check_interpreter_identity`) so this check's result is identical
    regardless of which check runs first.
    """
    name = "Claude Desktop interpreter"

    data = _resolve_claude_desktop_targets()

    if data["error"] is not None:
        return CheckResult(name, STATUS_INFO, detail=f"could not read Claude Desktop config: {data['error']}")

    if not data["entries_found"]:
        return CheckResult(name, STATUS_INFO, detail=data["no_entries_detail"])

    results = data["results"]
    statuses = [s for s, _, _, _ in results]
    if STATUS_WARN in statuses:
        overall = STATUS_WARN
    elif STATUS_INFO in statuses:
        overall = STATUS_INFO
    else:
        overall = STATUS_PASS

    detail = " || ".join(d for _, d, _, _ in results)
    hint = " || ".join(h for _, _, h, _ in results if h)
    return CheckResult(name, overall, detail=detail, hint=hint)


# ---------------------------------------------------------------------------
# check_full_disk_access_effective
# ---------------------------------------------------------------------------

_TCC_DB_PATH = Path.home() / "Library" / "Application Support" / "com.apple.TCC" / "TCC.db"


def check_full_disk_access_effective() -> CheckResult:
    """Probe whether *this* process currently has Full Disk Access.

    Attempts a read-only open of the user's TCC.db (a file only readable
    with Full Disk Access granted to the reading process). This reflects
    the doctor process only - which may be inheriting a grant made to the
    launching terminal/shell - not the interpreter Claude Desktop actually
    launches (see the "Claude Desktop interpreter" check above for that).
    """
    name = "Full Disk Access effective (this process)"
    try:
        with open(_TCC_DB_PATH, "rb") as f:
            f.read(16)
        return CheckResult(
            name,
            STATUS_PASS,
            detail=(
                "this process has Full Disk Access (own grant or inherited from the "
                "terminal) - this reflects the doctor process only, not the interpreter "
                "Claude Desktop launches"
            ),
        )
    except PermissionError:
        return CheckResult(
            name,
            STATUS_WARN,
            detail="no Full Disk Access for this process (TCC.db could not be read)",
            hint=(
                "This reflects the doctor process only, which may inherit the terminal's "
                "grant, not the Claude Desktop-launched interpreter - see the 'Claude "
                "Desktop interpreter' check above."
            ),
        )
    except FileNotFoundError:
        return CheckResult(
            name,
            STATUS_INFO,
            detail=f"TCC.db not found at {_TCC_DB_PATH}",
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
    """Check for a Things URL-scheme auth token file.

    PASS when a non-empty token file is found. WARN (not FAIL - most tools
    don't need it) when missing, naming the specific tools that will fail
    with an actionable error until the token is configured:
    ``add_checklist_items``, ``prepend_checklist_items``,
    ``replace_checklist_items``, and any other ``things:///update``-based
    tool.
    """
    name = "Auth token file"
    for auth_file in _auth_token_paths():
        if auth_file.exists():
            try:
                token = auth_file.read_text().strip()
                if '=' in token:
                    token = token.split('=', 1)[1].strip()
            except OSError:
                token = ""
            if token:
                return CheckResult(name, STATUS_PASS, detail=f"token configured ({auth_file})")

    return CheckResult(
        name,
        STATUS_WARN,
        detail="no auth token file found",
        hint=(
            "Required by add_checklist_items, prepend_checklist_items, and "
            "replace_checklist_items (and any other things:///update-based tool) - "
            "these return an error instead of silently no-op'ing until a token is "
            "configured. Things -> Settings -> General -> Enable Things URLs -> "
            "Manage, then save it to .things-auth, things-auth.txt, or ~/.things-auth."
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
        check_python_architecture(),
        check_interpreter_identity(),
        check_launch_parent(),
        check_claude_desktop_interpreter(),
        check_full_disk_access_effective(),
        check_auth_token(),
        check_environment(),
    ]


def has_failure(results: List[CheckResult]) -> bool:
    """Return True if any result has status FAIL."""
    return any(r.status == STATUS_FAIL for r in results)


def _full_disk_access_targets() -> List[str]:
    """Return the deduped Claude-Desktop-resolved interpreter path(s), in encounter order.

    Consults the same memoized resolution used by
    :func:`check_interpreter_identity` and :func:`check_claude_desktop_interpreter`
    (:func:`_resolve_claude_desktop_targets`) - calling this never spawns an
    extra probe subprocess. Returns an empty list when no Claude Desktop
    interpreter could be resolved (config missing, no matching entry, or a
    read error).
    """
    data = _resolve_claude_desktop_targets()
    paths: List[str] = []
    for _status, _detail, _hint, resolved in data.get("results", []):
        if resolved and resolved not in paths:
            paths.append(resolved)
    return paths


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

    for path in _full_disk_access_targets():
        lines.append(f"Full Disk Access target for Claude Desktop: {path}")

    return "\n".join(lines)


def results_to_json(results: List[CheckResult]) -> dict:
    """Return a machine-readable dict for --json output."""
    return {
        "ok": not has_failure(results),
        "checks": [r.to_dict() for r in results],
        "full_disk_access_targets": _full_disk_access_targets(),
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
