"""Entry point for running the Things MCP server as a module."""

from .boot_trace import boot_marker

boot_marker("process-start")

from .main import main

if __name__ == "__main__":
    main()