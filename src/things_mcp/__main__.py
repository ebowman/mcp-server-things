"""Entry point for running the Things MCP server as a module."""

import sys

from .boot_trace import arm_boot_watchdog, boot_marker

boot_marker("process-start")
arm_boot_watchdog()

from .main import main  # noqa: E402  must follow boot_marker/arm_boot_watchdog so boot tracing starts first

if __name__ == "__main__":
    sys.exit(main())
