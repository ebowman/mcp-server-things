"""Main entry point for the Things 3 MCP server."""

import argparse
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from .boot_trace import arm_boot_watchdog, boot_marker
from .client_config import CLIENT_CHOICES as _CLIENT_CHOICES
from .client_config import VIA_CHOICES as _VIA_CHOICES
from .server import ThingsMCPServer
from .services.applescript_manager import AppleScriptManager

logger = logging.getLogger(__name__)


class ServerManager:
    """Manages the MCP server lifecycle."""
    
    def __init__(self):
        """Initialize the server manager."""
        self.server: Optional[ThingsMCPServer] = None
        self.running = False
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup graceful shutdown signal handlers."""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown...")
            self.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def start(
        self,
        debug: bool = False,
        timeout: int = 30,
        retry_count: int = 3,
        env_file: Optional[str] = None,
        transport: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ):
        """Start the MCP server.

        Args:
            debug: Enable debug logging
            timeout: AppleScript timeout in seconds
            retry_count: Number of retries for failed operations
            env_file: Optional path to .env file
            transport: Optional transport override ('stdio' or 'http'); CLI flag
                takes precedence over THINGS_MCP_TRANSPORT when provided
            host: Optional host override for http transport; CLI flag takes
                precedence over THINGS_MCP_HOST when provided
            port: Optional port override for http transport; CLI flag takes
                precedence over THINGS_MCP_PORT when provided
        """
        try:
            # Create server first (it will configure logging)
            self.server = ThingsMCPServer(env_file=env_file)

            # CLI flags override env/config for transport settings
            if transport is not None:
                self.server.config.transport = transport
            if host is not None:
                self.server.config.host = host
            if port is not None:
                self.server.config.port = port

            # Override with debug if specified
            if debug:
                logging.getLogger().setLevel(logging.DEBUG)
                logger.debug("Debug logging enabled")
            
            # Note: Things 3 availability is checked lazily on the first tool call
            # via AppleScriptManager (async, with timeout + retries). We intentionally
            # do NOT probe Things 3 here: a synchronous `osascript` call at startup
            # blocks the MCP stdio handshake and can trigger a macOS Automation (TCC)
            # consent dialog, which stalls long enough for the client to mark the
            # server as "failed to connect". It also auto-launches Things 3 unnecessarily.
            # Use `--health-check` or `--test-applescript` for explicit connectivity checks.

            # Mark as running
            self.running = True
            
            logger.info("Starting Things 3 MCP Server...")
            logger.info("Server is ready to handle requests")
            logger.info("Press Ctrl+C to stop")
            
            # Run the server
            self.server.run()
        
        except KeyboardInterrupt:
            logger.info("Server stopped by user")
        except Exception as e:
            logger.error(f"Server startup error: {e}")
            sys.exit(1)
        finally:
            self.stop()
    
    def stop(self):
        """Stop the MCP server gracefully."""
        if self.running and self.server:
            logger.info("Stopping server...")
            self.server.stop()
            self.running = False
            logger.info("Server stopped")


def create_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Things 3 MCP Server - Model Context Protocol server for Things 3 integration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Start server with default settings
  %(prog)s --debug                  # Start with debug logging
  %(prog)s --timeout 60             # Set AppleScript timeout to 60 seconds
  %(prog)s --retry-count 5          # Set retry count to 5 attempts
  %(prog)s --health-check           # Check system health and exit
  %(prog)s --version                # Show version information
  %(prog)s doctor                   # Run diagnostic checks and exit
  %(prog)s doctor --json            # Diagnostic checks with machine-readable JSON output
  %(prog)s config --client claude-desktop --write   # Safely add/update this server in Claude Desktop's config
  %(prog)s config --client claude-code              # Print the 'claude mcp add-json' one-liners

Environment:
  The server requires Things 3 to be installed on macOS.
  AppleScript execution is used for interacting with Things 3.
        """
    )

    parser.add_argument(
        "command",
        nargs="?",
        choices=["doctor", "config"],
        help=(
            "Optional subcommand. 'doctor' runs read-only diagnostic checks and exits. "
            "'config' prints (or writes) MCP client configuration and exits."
        )
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="With 'doctor': print machine-readable JSON instead of a table"
    )

    # 'config' subcommand options
    parser.add_argument(
        "--client",
        choices=list(_CLIENT_CHOICES),
        help="With 'config': target MCP client (claude-desktop, claude-code, or generic)"
    )

    parser.add_argument(
        "--via",
        choices=list(_VIA_CHOICES),
        default="uvx",
        help="With 'config': how the server is launched (default: uvx)"
    )

    parser.add_argument(
        "--write",
        action="store_true",
        help="With 'config' --client claude-desktop: write/merge the config file instead of just printing it"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="With 'config' --write: overwrite an existing differing 'things' entry"
    )

    # Server options
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="AppleScript execution timeout in seconds (default: 30)"
    )
    
    parser.add_argument(
        "--retry-count",
        type=int,
        default=3,
        help="Number of retries for failed operations (default: 3)"
    )
    
    parser.add_argument(
        "--env-file",
        type=str,
        help="Path to .env configuration file"
    )

    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=None,
        help="MCP transport to use: 'stdio' (default) or 'http'. Overrides THINGS_MCP_TRANSPORT."
    )

    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind to when --transport=http (default: 127.0.0.1). Overrides THINGS_MCP_HOST."
    )

    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to when --transport=http (default: 8000). Overrides THINGS_MCP_PORT."
    )

    # Utility commands
    parser.add_argument(
        "--health-check",
        action="store_true",
        help="Perform health check and exit"
    )
    
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information and exit"
    )
    
    parser.add_argument(
        "--test-applescript",
        action="store_true",
        help="Test AppleScript connectivity and exit"
    )
    
    return parser


async def perform_health_check(timeout: int, retry_count: int) -> int:
    """Perform system health check.
    
    Args:
        timeout: AppleScript timeout
        retry_count: Retry count
        
    Returns:
        Exit code (0 for healthy, 1 for issues)
    """
    try:
        logger.info("Performing health check...")
        
        # Check AppleScript availability
        import subprocess
        result = subprocess.run(["which", "osascript"], capture_output=True)
        if result.returncode != 0:
            logger.error("osascript not found - AppleScript not available")
            return 1
        
        logger.info("✓ AppleScript available")
        
        # Check Things 3 connectivity
        applescript_manager = AppleScriptManager(timeout=timeout, retry_count=retry_count)
        
        if await applescript_manager.is_things_running():
            logger.info("✓ Things 3 is running and accessible")
        else:
            logger.warning("⚠ Things 3 is not running or not accessible")
            logger.info("  Please ensure Things 3 is installed and running")
        
        # Test basic AppleScript execution
        script = 'return "Hello from AppleScript"'
        result = await applescript_manager.execute_applescript(script)
        
        if result.get("success"):
            logger.info("✓ AppleScript execution working")
        else:
            logger.error(f"✗ AppleScript execution failed: {result.get('error')}")
            return 1
        
        logger.info("Health check completed successfully")
        return 0
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return 1


async def test_applescript_connectivity(timeout: int, retry_count: int) -> int:
    """Test AppleScript connectivity to Things 3.
    
    Args:
        timeout: AppleScript timeout
        retry_count: Retry count
        
    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        logger.info("Testing AppleScript connectivity...")
        
        applescript_manager = AppleScriptManager(timeout=timeout, retry_count=retry_count)
        
        # Test basic script execution
        logger.info("Testing basic AppleScript execution...")
        result = await applescript_manager.execute_applescript('return "test"')
        
        if result.get("success"):
            logger.info("✓ Basic AppleScript execution successful")
        else:
            logger.error(f"✗ Basic AppleScript execution failed: {result.get('error')}")
            return 1
        
        # Test Things 3 specific script
        logger.info("Testing Things 3 connectivity...")
        script = 'tell application "Things3" to return "connected"'
        result = await applescript_manager.execute_applescript(script)
        
        if result.get("success"):
            logger.info("✓ Things 3 AppleScript connectivity successful")
            logger.info(f"Response: {result.get('output')}")
        else:
            logger.error(f"✗ Things 3 AppleScript connectivity failed: {result.get('error')}")
            return 1
        
        # Test URL scheme
        logger.info("Testing Things 3 URL scheme...")
        result = await applescript_manager.execute_url_scheme("show", {"id": "today"})
        
        if result.get("success"):
            logger.info("✓ Things 3 URL scheme successful")
        else:
            logger.error(f"✗ Things 3 URL scheme failed: {result.get('error')}")
            return 1
        
        logger.info("All connectivity tests passed!")
        return 0
    
    except Exception as e:
        logger.error(f"Connectivity test failed: {e}")
        return 1


def show_version():
    """Show version information."""
    from . import __version__
    print("Things 3 MCP Server")
    print(f"Version: {__version__}")
    print("FastMCP-based Model Context Protocol server for Things 3 integration")
    print("")
    print("Requirements:")
    print("  - macOS with AppleScript support")
    print("  - Things 3 application")
    print("  - Python 3.8+")
    print("  - FastMCP 3.0+")


def run_config(client: Optional[str], via: str, write: bool, force: bool) -> int:
    """Handle the 'config' subcommand: print or write client configuration.

    Args:
        client: One of 'claude-desktop', 'claude-code', 'generic', or None.
        via: 'uvx' or 'current-python'.
        write: If True, write/merge the config file (claude-desktop only).
        force: If True, overwrite an existing differing entry when writing.

    Returns:
        Process exit code: 0 on success/no-op, non-zero on refusal/error.
    """
    from . import client_config

    if client is None:
        print("Error: 'config' requires --client (claude-desktop, claude-code, or generic)", file=sys.stderr)
        return 2

    if write and client != "claude-desktop":
        print("Error: --write is only supported with --client claude-desktop", file=sys.stderr)
        return 2

    caveat = client_config.current_python_source_tree_caveat() if via == "current-python" else None
    if caveat:
        print(caveat, file=sys.stderr)

    if client == "claude-desktop":
        if write:
            try:
                result = client_config.write_claude_desktop_config(via=via, force=force)
            except client_config.ClientConfigError as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1

            if not result.changed:
                print(f"No changes needed - {result.path} already has the requested 'things' entry.")
                return 0

            print(f"Updated {result.path}")
            print(f"  old: {json.dumps(result.old_server_config)}")
            print(f"  new: {json.dumps(result.new_server_config)}")
            if result.backup_path is not None:
                print(f"Backup written to {result.backup_path}")
            return 0

        print(client_config.format_claude_desktop_snippet(via=via))
        print(f"\n# Config file location: {client_config.get_claude_desktop_config_path()}")
        return 0

    if client == "claude-code":
        print(client_config.format_claude_code_commands(via=via))
        return 0

    if client == "generic":
        print(client_config.format_generic_snippet(via=via))
        return 0

    print(f"Error: unknown client {client!r}", file=sys.stderr)
    return 2


def main():
    """Main entry point."""
    boot_marker("process-start")
    arm_boot_watchdog()
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "doctor":
        from .doctor import run_doctor
        return run_doctor(json_output=args.json)

    if args.command == "config":
        return run_config(client=args.client, via=args.via, write=args.write, force=args.force)

    # Handle utility commands
    if args.version:
        show_version()
        return 0
    
    if args.health_check:
        return asyncio.run(perform_health_check(args.timeout, args.retry_count))
    
    if args.test_applescript:
        return asyncio.run(test_applescript_connectivity(args.timeout, args.retry_count))
    
    # Configure basic logging if no server will do it
    if args.version or args.health_check or args.test_applescript:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    # Start the server
    server_manager = ServerManager()
    
    try:
        server_manager.start(
            debug=args.debug,
            timeout=args.timeout,
            retry_count=args.retry_count,
            env_file=args.env_file,
            transport=args.transport,
            host=args.host,
            port=args.port
        )
        return 0
    
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
