"""Main entry point for the Things 3 MCP server."""

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

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
    
    def start(self, debug: bool = False, timeout: int = 30, retry_count: int = 3, env_file: Optional[str] = None):
        """Start the MCP server.
        
        Args:
            debug: Enable debug logging
            timeout: AppleScript timeout in seconds
            retry_count: Number of retries for failed operations
            env_file: Optional path to .env file
        """
        try:
            # Create server first (it will configure logging)
            self.server = ThingsMCPServer(env_file=env_file)
            
            # Override with debug if specified
            if debug:
                logging.getLogger().setLevel(logging.DEBUG)
                logger.debug("Debug logging enabled")
            
            # Check if Things 3 is available
            applescript_manager = AppleScriptManager(timeout=timeout, retry_count=retry_count)
            
            if not applescript_manager.is_things_running():
                logger.warning("Things 3 is not running or not accessible")
                logger.info("Please ensure Things 3 is installed and running")
                # Continue anyway - it might start later
            else:
                logger.info("Things 3 detected and accessible")
            
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

Environment:
  The server requires Things 3 to be installed on macOS.
  AppleScript execution is used for interacting with Things 3.
        """
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
    print("Things 3 MCP Server")
    print("Version: 1.0.0")
    print("FastMCP-based Model Context Protocol server for Things 3 integration")
    print("")
    print("Requirements:")
    print("  - macOS with AppleScript support")
    print("  - Things 3 application")
    print("  - Python 3.8+")
    print("  - FastMCP 2.0+")


def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
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
            env_file=args.env_file
        )
        return 0
    
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
