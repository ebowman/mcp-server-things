"""Boot-phase diagnostic markers written to stderr.

This module is intentionally dependency-free (stdlib only) so it can be
imported and used at the very top of the process entrypoints, before any
other project modules (including logging configuration) are loaded. The
server has intermittently hung at cold-start before completing the MCP
stdio handshake, producing zero stderr output; these markers give a
timestamped trail showing exactly which boot phase was reached last.
"""

import os
import sys
import time
from datetime import datetime, timezone

# Monotonic reference point captured at import time, used to compute the
# elapsed time reported alongside each marker.
_BOOT_START = time.monotonic()

_WATCHDOG_ENV_VAR = "THINGS_MCP_BOOT_WATCHDOG_SECS"
_WATCHDOG_DEFAULT_SECS = 25.0


def boot_marker(phase: str) -> None:
    """Write a single timestamped boot-phase marker line to stderr.

    Args:
        phase: Short, human-readable name identifying the boot phase that
            was just reached (e.g. ``"process-start"``, ``"config-loaded"``).

    Returns:
        None.
    """
    try:
        now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        elapsed = time.monotonic() - _BOOT_START
        sys.stderr.write(
            f"things-mcp boot: {now} +{elapsed:.3f}s {phase}\n"
        )
        sys.stderr.flush()
    except (OSError, ValueError):
        # stderr may be a closed pipe (e.g. during shutdown) or otherwise
        # unwritable; boot markers are best-effort diagnostics and must
        # never crash the process.
        pass


def arm_boot_watchdog() -> None:
    """Arm a one-shot startup watchdog that dumps all thread stacks on stall.

    Uses ``faulthandler.dump_traceback_later()`` to schedule a single dump of
    every thread's Python stack to stderr after a configurable deadline. This
    is intended to catch the case where boot hangs somewhere between process
    start and completion of the MCP stdio handshake with zero other stderr
    output.

    Important limitations, by design:

    * ``faulthandler`` supports only ONE pending "dump later" timer per
      process -- each call to ``dump_traceback_later()`` replaces any
      previously scheduled one. This function is therefore called as early
      as possible in both entrypoints (``__main__.py`` and
      ``main.py:main()``); calling it twice is harmless (idempotent: the
      second call simply re-arms the same single timer), but there is only
      ever one deadline in flight, not multiple staggered dumps.
    * There is no cancellation of the timer anywhere in the codebase. The
      hang this watchdog targets can occur inside FastMCP's handshake logic
      after ``mcp.run()`` starts, so disarming the watchdog before that point
      would blind us exactly where the hang tends to happen. The accepted
      consequence is that on a *healthy* boot, the process will still emit
      one thread-stack dump to stderr when the deadline elapses during
      normal operation. This is considered safe: the MCP stdio protocol only
      uses stdout, so stray stderr output does not corrupt the protocol
      stream, and it happens at most once per process lifetime.

    The deadline is read from the ``THINGS_MCP_BOOT_WATCHDOG_SECS``
    environment variable (seconds, may be fractional). Parsing is
    defensive:

    * Unset or unparseable (e.g. ``"banana"``) falls back to the default of
      25 seconds.
    * A value that parses to <= 0 (e.g. ``"0"`` or ``"-3"``) disables the
      watchdog entirely.

    Any failure while arming (e.g. ``faulthandler`` unavailable, stderr
    unwritable) is swallowed -- this diagnostic must never break boot.

    Returns:
        None.
    """
    raw = os.environ.get(_WATCHDOG_ENV_VAR)
    if raw is None:
        timeout = _WATCHDOG_DEFAULT_SECS
    else:
        try:
            timeout = float(raw)
        except ValueError:
            timeout = _WATCHDOG_DEFAULT_SECS

    if timeout <= 0:
        boot_marker("watchdog-disabled")
        return

    try:
        import faulthandler

        faulthandler.dump_traceback_later(
            timeout, repeat=False, file=sys.stderr, exit=False
        )
    except (OSError, ValueError, RuntimeError):
        # Arming the watchdog is best-effort; a broken stderr or an
        # unsupported faulthandler state must never break boot.
        return

    boot_marker(f"watchdog-armed ({timeout}s)")
