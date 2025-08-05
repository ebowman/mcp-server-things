"""
Things 3 MCP Server

Main FastMCP server implementation with comprehensive tool registration,
resource management, and error handling for Things 3 integration.
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from fastmcp import FastMCP

# Import all tool modules
from .tools.core_operations import CoreOperationsTools
from .tools.search_tools import SearchTools
from .tools.batch_operations import BatchOperationsTools
from .tools.scheduling_tools import SchedulingTools
from .tools.ui_integration import UIIntegrationTools

# Import resource modules
from .resources.data_views import DataViewsResources
from .resources.analytics import AnalyticsResources
from .resources.export_views import ExportViewsResources

# Import prompt modules
from .prompts.quick_entry import QuickEntryPrompts
from .prompts.workflow_templates import WorkflowTemplatePrompts

# Import service modules
from .services.applescript_manager import AppleScriptManager, ExecutionConfig
from .services.error_handler import ErrorHandler
from .services.validation_service import ValidationService
from .services.cache_manager import CacheManager
from .services.url_scheme_handler import URLSchemeHandler

# Import configuration
from .config import ThingsMCPConfig


class ThingsMCPServer:
    """
    Main Things 3 MCP Server implementation.
    
    Provides a comprehensive interface to Things 3 through FastMCP,
    including CRUD operations, search, batch operations, scheduling,
    and UI integration.
    """
    
    def __init__(self, config: Optional[ThingsMCPConfig] = None):
        """
        Initialize the Things 3 MCP Server.
        
        Args:
            config: Optional configuration object
        """
        self.config = config or ThingsMCPConfig()
        
        # Initialize FastMCP server
        self.mcp = FastMCP(
            name="things3-mcp-server",
            version="1.0.0", 
            description="MCP server for Things 3 task management integration"
        )
        
        # Initialize services
        self._init_services()
        
        # Initialize and register tools
        self._init_tools()
        
        # Initialize and register resources
        self._init_resources()
        
        # Initialize and register prompts
        self._init_prompts()
        
        # Setup server lifecycle hooks
        self._setup_lifecycle_hooks()
        
        # Configure logging
        self._configure_logging()
    
    def _init_services(self):
        """Initialize all service dependencies"""
        # Error handler
        self.error_handler = ErrorHandler(
            enable_detailed_logging=self.config.enable_detailed_logging
        )
        
        # Cache manager
        self.cache_manager = CacheManager(
            max_size=self.config.cache_max_size,
            default_ttl=self.config.cache_default_ttl
        )
        
        # AppleScript manager
        execution_config = ExecutionConfig(
            timeout=self.config.applescript_timeout,
            retry_count=self.config.applescript_retry_count,
            cache_ttl=self.config.cache_default_ttl,
            preferred_method=self.config.preferred_execution_method,
            enable_logging=self.config.enable_detailed_logging
        )
        
        self.applescript_manager = AppleScriptManager(
            config=execution_config,
            error_handler=self.error_handler,
            cache_manager=self.cache_manager
        )
        
        # URL scheme handler
        self.url_scheme_handler = URLSchemeHandler(
            applescript_manager=self.applescript_manager
        )
        
        # Validation service
        self.validation_service = ValidationService(
            config=self.config
        )
    
    def _init_tools(self):
        """Initialize and register all MCP tools"""
        # Core CRUD operations (5 tools)
        self.core_operations = CoreOperationsTools(
            mcp=self.mcp,
            applescript_manager=self.applescript_manager,
            validation_service=self.validation_service
        )
        
        # Search and filtering tools (4 tools)
        self.search_tools = SearchTools(
            mcp=self.mcp,
            applescript_manager=self.applescript_manager,
            validation_service=self.validation_service
        )
        
        # Batch operations tools (3 tools)
        self.batch_operations = BatchOperationsTools(
            mcp=self.mcp,
            applescript_manager=self.applescript_manager,
            validation_service=self.validation_service
        )
        
        # Scheduling tools (4 tools)
        self.scheduling_tools = SchedulingTools(
            mcp=self.mcp,
            applescript_manager=self.applescript_manager,
            validation_service=self.validation_service
        )
        
        # UI integration tools (4 tools)
        self.ui_integration = UIIntegrationTools(
            mcp=self.mcp,
            applescript_manager=self.applescript_manager,
            url_scheme_handler=self.url_scheme_handler
        )
        
        # Register server management tools
        self._register_server_tools()
    
    def _init_resources(self):
        """Initialize and register all MCP resources"""
        # Data view resources (Today, Upcoming, etc.)
        self.data_views = DataViewsResources(
            mcp=self.mcp,
            applescript_manager=self.applescript_manager,
            cache_manager=self.cache_manager
        )
        
        # Analytics resources
        self.analytics = AnalyticsResources(
            mcp=self.mcp,
            applescript_manager=self.applescript_manager
        )
        
        # Export view resources
        self.export_views = ExportViewsResources(
            mcp=self.mcp,
            applescript_manager=self.applescript_manager
        )
    
    def _init_prompts(self):
        """Initialize and register all MCP prompts"""
        # Quick entry prompts
        self.quick_entry_prompts = QuickEntryPrompts(
            mcp=self.mcp
        )
        
        # Workflow template prompts
        self.workflow_prompts = WorkflowTemplatePrompts(
            mcp=self.mcp
        )
    
    def _register_server_tools(self):
        """Register server management and utility tools"""
        
        @self.mcp.tool
        async def health_check() -> Dict[str, Any]:
            """
            Perform comprehensive health check of the Things 3 MCP server.
            
            Returns:
                Dict with server health status, Things 3 connectivity, and system info
            """
            try:
                health_data = {
                    "server_status": "healthy",
                    "timestamp": self._get_timestamp(),
                    "version": "1.0.0"
                }
                
                # Check Things 3 connectivity
                things_check = await self.applescript_manager.check_things_availability()
                health_data["things3"] = {
                    "available": things_check.success,
                    "version": things_check.data.get("version") if things_check.success else None,
                    "error": things_check.error if not things_check.success else None
                }
                
                # Get execution statistics
                exec_stats = await self.applescript_manager.get_execution_stats()
                health_data["execution_stats"] = exec_stats
                
                # Get error statistics
                error_stats = await self.error_handler.get_error_statistics()
                health_data["error_stats"] = error_stats
                
                # Get cache statistics
                health_data["cache_stats"] = {
                    "size": await self.cache_manager.size(),
                    "max_size": self.config.cache_max_size,
                    "hit_rate": exec_stats.get("cache_hit_rate", 0)
                }
                
                # Overall health assessment
                if not things_check.success:
                    health_data["server_status"] = "degraded"
                elif error_stats["total_errors"] > 10:  # Threshold for concern
                    health_data["server_status"] = "warning"
                
                return health_data
                
            except Exception as e:
                return {
                    "server_status": "error",
                    "error": str(e),
                    "timestamp": self._get_timestamp()
                }
        
        @self.mcp.tool
        async def get_server_stats() -> Dict[str, Any]:
            """
            Get comprehensive server statistics and metrics.
            
            Returns:
                Dict with execution statistics, error rates, and performance metrics
            """
            try:
                stats = {
                    "timestamp": self._get_timestamp(),
                    "uptime": self._get_uptime(),
                    "execution_stats": await self.applescript_manager.get_execution_stats(),
                    "error_stats": await self.error_handler.get_error_statistics(),
                    "cache_stats": {
                        "size": await self.cache_manager.size(),
                        "max_size": self.config.cache_max_size,
                        "memory_usage": await self.cache_manager.get_memory_usage()
                    },
                    "configuration": {
                        "applescript_timeout": self.config.applescript_timeout,
                        "retry_count": self.config.applescript_retry_count,
                        "preferred_method": self.config.preferred_execution_method.value,
                        "cache_enabled": self.config.enable_caching
                    }
                }
                
                return stats
                
            except Exception as e:
                return {
                    "error": str(e),
                    "timestamp": self._get_timestamp()
                }
        
        @self.mcp.tool
        async def clear_cache() -> Dict[str, Any]:
            """
            Clear all cached data and reset cache statistics.
            
            Returns:
                Dict with cache clearing status
            """
            try:
                success = await self.cache_manager.clear()
                await self.applescript_manager.stats.update({"cache_hits": 0})
                
                return {
                    "success": success,
                    "message": "Cache cleared successfully",
                    "timestamp": self._get_timestamp()
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "timestamp": self._get_timestamp()
                }
        
        @self.mcp.tool
        async def reset_error_stats() -> Dict[str, Any]:
            """
            Reset error statistics and counters.
            
            Returns:
                Dict with reset status
            """
            try:
                await self.error_handler.reset_statistics()
                
                return {
                    "success": True,
                    "message": "Error statistics reset successfully",
                    "timestamp": self._get_timestamp()
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "timestamp": self._get_timestamp()
                }
        
        @self.mcp.tool
        async def test_applescript_execution() -> Dict[str, Any]:
            """
            Test AppleScript execution with a simple version check.
            
            Returns:
                Dict with test results and execution details
            """
            try:
                # Test URL scheme execution
                url_result = await self.applescript_manager.execute_url_scheme(
                    action="show",
                    parameters={"id": "today"},
                    cache_key=None
                )
                
                # Test AppleScript execution
                script_result = await self.applescript_manager.execute_applescript(
                    script='tell application "Things3" to return version',
                    script_name="version_test"
                )
                
                return {
                    "url_scheme_test": {
                        "success": url_result.success,
                        "method": url_result.method,
                        "error": url_result.error if not url_result.success else None
                    },
                    "applescript_test": {
                        "success": script_result.success,
                        "output": script_result.output if script_result.success else None,
                        "error": script_result.error if not script_result.success else None
                    },
                    "timestamp": self._get_timestamp()
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "error": str(e),
                    "timestamp": self._get_timestamp()
                }
    
    def _setup_lifecycle_hooks(self):
        """Setup server lifecycle hooks"""
        
        @self.mcp.startup
        async def startup():
            """Server startup hook"""
            self.logger.info("Things 3 MCP Server starting up...")
            
            # Test Things 3 connectivity
            availability = await self.applescript_manager.check_things_availability()
            if availability.success:
                self.logger.info(f"Things 3 detected: {availability.data.get('version', 'Unknown version')}")
            else:
                self.logger.warning(f"Things 3 connectivity issue: {availability.error}")
            
            # Initialize cache
            await self.cache_manager.initialize()
            
            self.logger.info("Things 3 MCP Server started successfully")
        
        @self.mcp.shutdown
        async def shutdown():
            """Server shutdown hook"""
            self.logger.info("Things 3 MCP Server shutting down...")
            
            # Clear cache
            await self.cache_manager.clear()
            
            # Log final statistics
            exec_stats = await self.applescript_manager.get_execution_stats()
            error_stats = await self.error_handler.get_error_statistics()
            
            self.logger.info(f"Final execution stats: {exec_stats}")
            self.logger.info(f"Final error stats: {error_stats}")
            
            self.logger.info("Things 3 MCP Server shutdown complete")
    
    def _configure_logging(self):
        """Configure logging for the server"""
        logging.basicConfig(
            level=logging.INFO if not self.config.enable_debug_logging else logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        self.logger = logging.getLogger(__name__)
        
        # Suppress verbose logging from dependencies if not in debug mode
        if not self.config.enable_debug_logging:
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("fastmcp").setLevel(logging.INFO)
    
    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def _get_uptime(self) -> str:
        """Get server uptime (placeholder implementation)"""
        return "0:00:00"  # Would track actual uptime in production
    
    async def run(self, **kwargs):
        """
        Run the MCP server.
        
        Args:
            **kwargs: Additional arguments to pass to FastMCP.run()
        """
        try:
            await self.mcp.run(**kwargs)
        except KeyboardInterrupt:
            self.logger.info("Server stopped by user")
        except Exception as e:
            self.logger.error(f"Server error: {e}")
            raise


# Server factory function
def create_server(config_path: Optional[Path] = None) -> ThingsMCPServer:
    """
    Factory function to create a Things 3 MCP server instance.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        Configured ThingsMCPServer instance
    """
    config = None
    if config_path and config_path.exists():
        config = ThingsMCPConfig.from_file(config_path)
    
    return ThingsMCPServer(config)


# Main entry point
async def main():
    """Main entry point for the server"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Things 3 MCP Server")
    parser.add_argument(
        "--config", 
        type=Path, 
        help="Path to configuration file"
    )
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Create and run server
    server = create_server(args.config)
    
    if args.debug:
        server.config.enable_debug_logging = True
        server._configure_logging()
    
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())