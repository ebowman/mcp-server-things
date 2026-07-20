"""Boot-phase diagnostic markers written to stderr.

This module is intentionally dependency-free (stdlib only) so it can be
imported and used at the very top of the process entrypoints, before any
other project modules (including logging configuration) are loaded. The
server has intermittently hung at cold-start before completing the MCP
stdio handshake, producing zero stderr output; these markers give a
timestamped trail showing exactly which boot phase was reached last.
"""

import sys
import time
from datetime import datetime, timezone

# Monotonic reference point captured at import time, used to compute the
# elapsed time reported alongside each marker.
_BOOT_START = time.monotonic()


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
