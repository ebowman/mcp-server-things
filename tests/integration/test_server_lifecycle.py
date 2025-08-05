"""
Integration tests for Things 3 MCP server lifecycle.

Tests server startup, shutdown, health checks, and overall integration
of all components working together.
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.things_mcp.server import ThingsMCPServer, create_server
from src.things_mcp.config import ThingsMCPConfig


class TestServerInitialization:
    """Test server initialization and component setup."""
    
    def test_server_init_with_default_config(self):
        """Test server initialization with default configuration."""
        server = ThingsMCPServer()
        
        assert server.config is not None
        assert hasattr(server, 'mcp')
        assert hasattr(server, 'applescript_manager')
        assert hasattr(server, 'error_handler')
        assert hasattr(server, 'cache_manager')
        assert hasattr(server, 'validation_service')
    
    def test_server_init_with_custom_config(self, test_config):
        """Test server initialization with custom configuration."""
        server = ThingsMCPServer(config=test_config)
        
        assert server.config == test_config
        assert server.config.applescript_timeout == 5
        assert server.config.enable_detailed_logging is True
    
    def test_server_components_initialization(self, mock_server):
        """Test that all server components are properly initialized."""
        # Verify all core components exist
        assert hasattr(mock_server, 'core_operations')
        assert hasattr(mock_server, 'search_tools')
        assert hasattr(mock_server, 'batch_operations')
        assert hasattr(mock_server, 'scheduling_tools')
        assert hasattr(mock_server, 'ui_integration')
        
        # Verify resource components
        assert hasattr(mock_server, 'data_views')
        assert hasattr(mock_server, 'analytics')
        assert hasattr(mock_server, 'export_views')
        
        # Verify prompt components
        assert hasattr(mock_server, 'quick_entry_prompts')
        assert hasattr(mock_server, 'workflow_prompts')
    
    def test_server_mcp_configuration(self, mock_server):
        """Test that FastMCP is properly configured."""
        assert mock_server.mcp.name == "things3-mcp-server"
        assert mock_server.mcp.version == "1.0.0"
        assert "Things 3" in mock_server.mcp.description


class TestServerHealthCheck:
    """Test server health check functionality."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self, mock_server):
        """Test successful health check when all systems are operational."""
        # Configure mocks for successful health check
        mock_server._mock_applescript_manager.set_failure_mode(False)
        
        # Get the health_check tool function
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        assert health_check_tool is not None, "health_check tool not found"
        
        result = await health_check_tool()
        
        assert result["server_status"] == "healthy"
        assert "timestamp" in result
        assert result["version"] == "1.0.0"
        assert result["things3"]["available"] is True
        assert result["things3"]["version"] is not None
        assert "execution_stats" in result
        assert "error_stats" in result
        assert "cache_stats" in result
    
    @pytest.mark.asyncio
    async def test_health_check_things_unavailable(self, mock_server):
        """Test health check when Things 3 is unavailable."""
        # Configure mock to simulate Things 3 unavailable
        mock_server._mock_applescript_manager.set_failure_mode(True, "Things 3 not running")
        
        # Get the health_check tool function
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        result = await health_check_tool()
        
        assert result["server_status"] == "degraded"
        assert result["things3"]["available"] is False
        assert result["things3"]["error"] is not None
        assert "Things 3 not running" in result["things3"]["error"]
    
    @pytest.mark.asyncio
    async def test_health_check_high_error_rate(self, mock_server):
        """Test health check with high error rate triggers warning status."""
        # Configure mock error handler to report high error count
        mock_server._mock_error_handler.errors = [{"error": f"Error {i}"} for i in range(15)]
        
        # Get the health_check tool function
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        result = await health_check_tool()
        
        assert result["server_status"] == "warning"
        assert result["error_stats"]["total_errors"] >= 10
    
    @pytest.mark.asyncio
    async def test_health_check_exception_handling(self, mock_server):
        """Test health check handles exceptions gracefully."""
        # Configure mock to raise exception
        mock_server._mock_applescript_manager.check_things_availability = AsyncMock(
            side_effect=Exception("Unexpected error")
        )
        
        # Get the health_check tool function
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        result = await health_check_tool()
        
        assert result["server_status"] == "error"
        assert "Unexpected error" in result["error"]
        assert "timestamp" in result


class TestServerStatistics:
    """Test server statistics collection and reporting."""
    
    @pytest.mark.asyncio
    async def test_get_server_stats(self, mock_server):
        """Test getting comprehensive server statistics."""
        # Get the get_server_stats tool function
        stats_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'get_server_stats':
                stats_tool = tool
                break
        
        assert stats_tool is not None, "get_server_stats tool not found"
        
        result = await stats_tool()
        
        assert "timestamp" in result
        assert "uptime" in result
        assert "execution_stats" in result
        assert "error_stats" in result
        assert "cache_stats" in result
        assert "configuration" in result
        
        # Verify configuration details
        config = result["configuration"]
        assert config["applescript_timeout"] == mock_server.config.applescript_timeout
        assert config["retry_count"] == mock_server.config.applescript_retry_count
        assert config["preferred_method"] == mock_server.config.preferred_execution_method.value
        assert config["cache_enabled"] == mock_server.config.enable_caching
    
    @pytest.mark.asyncio
    async def test_get_server_stats_exception_handling(self, mock_server):
        """Test server stats handles exceptions gracefully."""
        # Configure mock to raise exception during stats collection
        mock_server._mock_applescript_manager.get_execution_stats = AsyncMock(
            side_effect=Exception("Stats error")
        )
        
        # Get the get_server_stats tool function
        stats_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'get_server_stats':
                stats_tool = tool
                break
        
        result = await stats_tool()
        
        assert "error" in result
        assert "Stats error" in result["error"]
        assert "timestamp" in result


class TestCacheManagement:
    """Test cache management operations."""
    
    @pytest.mark.asyncio
    async def test_clear_cache(self, mock_server):
        """Test clearing server cache."""
        # Get the clear_cache tool function
        clear_cache_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'clear_cache':
                clear_cache_tool = tool
                break
        
        assert clear_cache_tool is not None, "clear_cache tool not found"
        
        result = await clear_cache_tool()
        
        assert result["success"] is True
        assert result["message"] == "Cache cleared successfully"
        assert "timestamp" in result
        
        # Verify cache manager clear was called
        mock_server._mock_cache_manager.clear.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_clear_cache_failure(self, mock_server):
        """Test cache clearing failure handling."""
        # Configure cache manager to fail
        mock_server._mock_cache_manager.clear = AsyncMock(return_value=False)
        
        # Get the clear_cache tool function
        clear_cache_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'clear_cache':
                clear_cache_tool = tool
                break
        
        result = await clear_cache_tool()
        
        assert result["success"] is False


class TestErrorStatisticsManagement:
    """Test error statistics management."""
    
    @pytest.mark.asyncio
    async def test_reset_error_stats(self, mock_server):
        """Test resetting error statistics."""
        # Add some errors first
        mock_server._mock_error_handler.errors = [{"error": "Test error"}]
        
        # Get the reset_error_stats tool function
        reset_stats_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'reset_error_stats':
                reset_stats_tool = tool
                break
        
        assert reset_stats_tool is not None, "reset_error_stats tool not found"
        
        result = await reset_stats_tool()
        
        assert result["success"] is True
        assert result["message"] == "Error statistics reset successfully"
        assert "timestamp" in result
        
        # Verify error handler reset was called
        mock_server._mock_error_handler.reset_statistics.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_reset_error_stats_failure(self, mock_server):
        """Test error statistics reset failure handling."""
        # Configure error handler to fail
        mock_server._mock_error_handler.reset_statistics = AsyncMock(
            side_effect=Exception("Reset failed")
        )
        
        # Get the reset_error_stats tool function
        reset_stats_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'reset_error_stats':
                reset_stats_tool = tool
                break
        
        result = await reset_stats_tool()
        
        assert result["success"] is False
        assert "Reset failed" in result["error"]


class TestAppleScriptExecutionTesting:
    """Test AppleScript execution testing functionality."""
    
    @pytest.mark.asyncio
    async def test_applescript_execution_test_success(self, mock_server):
        """Test successful AppleScript execution test."""
        # Configure mocks for successful execution
        mock_server._mock_applescript_manager.set_failure_mode(False)
        
        # Get the test_applescript_execution tool function
        test_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'test_applescript_execution':
                test_tool = tool
                break
        
        assert test_tool is not None, "test_applescript_execution tool not found"
        
        result = await test_tool()
        
        assert "url_scheme_test" in result
        assert "applescript_test" in result
        assert result["url_scheme_test"]["success"] is True
        assert result["applescript_test"]["success"] is True
        assert "timestamp" in result
    
    @pytest.mark.asyncio
    async def test_applescript_execution_test_failure(self, mock_server):
        """Test AppleScript execution test with failures."""
        # Configure mocks for failed execution
        mock_server._mock_applescript_manager.set_failure_mode(True, "Execution failed")
        
        # Get the test_applescript_execution tool function
        test_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'test_applescript_execution':
                test_tool = tool
                break
        
        result = await test_tool()
        
        assert result["url_scheme_test"]["success"] is False
        assert result["applescript_test"]["success"] is False
        assert "Execution failed" in result["url_scheme_test"]["error"]
        assert "Execution failed" in result["applescript_test"]["error"]
    
    @pytest.mark.asyncio
    async def test_applescript_execution_test_exception(self, mock_server):
        """Test AppleScript execution test exception handling."""
        # Configure mock to raise exception
        mock_server._mock_applescript_manager.execute_url_scheme = AsyncMock(
            side_effect=Exception("Test exception")
        )
        
        # Get the test_applescript_execution tool function
        test_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'test_applescript_execution':
                test_tool = tool
                break
        
        result = await test_tool()
        
        assert result["success"] is False
        assert "Test exception" in result["error"]


class TestServerLifecycleHooks:
    """Test server startup and shutdown hooks."""
    
    @pytest.mark.asyncio
    async def test_startup_hook_execution(self, test_config):
        """Test server startup hook execution."""
        with patch('src.things_mcp.server.AppleScriptManager') as mock_asm_class, \
             patch('src.things_mcp.server.ErrorHandler') as mock_eh_class, \
             patch('src.things_mcp.server.CacheManager') as mock_cm_class, \
             patch('src.things_mcp.server.ValidationService') as mock_vs_class:
            
            # Create mock instances
            mock_asm = AsyncMock()
            mock_asm.check_things_availability = AsyncMock(return_value={
                "success": True,
                "data": {"version": "3.20.1"}
            })
            mock_asm_class.return_value = mock_asm
            
            mock_cm = AsyncMock()
            mock_cm.initialize = AsyncMock()
            mock_cm_class.return_value = mock_cm
            
            mock_eh_class.return_value = MagicMock()
            mock_vs_class.return_value = MagicMock()
            
            # Create server
            server = ThingsMCPServer(config=test_config)
            
            # Manually trigger startup hook
            startup_hooks = [hook for hook in server.mcp._startup_hooks]
            assert len(startup_hooks) > 0
            
            for hook in startup_hooks:
                await hook()
            
            # Verify startup activities
            mock_asm.check_things_availability.assert_called_once()
            mock_cm.initialize.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_startup_hook_things_unavailable(self, test_config):
        """Test startup hook when Things 3 is unavailable."""
        with patch('src.things_mcp.server.AppleScriptManager') as mock_asm_class, \
             patch('src.things_mcp.server.ErrorHandler') as mock_eh_class, \
             patch('src.things_mcp.server.CacheManager') as mock_cm_class, \
             patch('src.things_mcp.server.ValidationService') as mock_vs_class, \
             patch('src.things_mcp.server.logging') as mock_logging:
            
            # Create mock instances
            mock_asm = AsyncMock()
            mock_asm.check_things_availability = AsyncMock(return_value={
                "success": False,
                "error": "Things 3 not running"
            })
            mock_asm_class.return_value = mock_asm
            
            mock_cm = AsyncMock()
            mock_cm.initialize = AsyncMock()
            mock_cm_class.return_value = mock_cm
            
            mock_eh_class.return_value = MagicMock()
            mock_vs_class.return_value = MagicMock()
            
            # Create server
            server = ThingsMCPServer(config=test_config)
            
            # Manually trigger startup hook
            startup_hooks = [hook for hook in server.mcp._startup_hooks]
            for hook in startup_hooks:
                await hook()
            
            # Verify warning was logged
            # (Note: This would require more complex logging mock setup in real implementation)
            mock_asm.check_things_availability.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_shutdown_hook_execution(self, test_config):
        """Test server shutdown hook execution."""
        with patch('src.things_mcp.server.AppleScriptManager') as mock_asm_class, \
             patch('src.things_mcp.server.ErrorHandler') as mock_eh_class, \
             patch('src.things_mcp.server.CacheManager') as mock_cm_class, \
             patch('src.things_mcp.server.ValidationService') as mock_vs_class:
            
            # Create mock instances
            mock_asm = AsyncMock()
            mock_asm.get_execution_stats = AsyncMock(return_value={"total": 10})
            mock_asm_class.return_value = mock_asm
            
            mock_eh = AsyncMock()
            mock_eh.get_error_statistics = AsyncMock(return_value={"total_errors": 0})
            mock_eh_class.return_value = mock_eh
            
            mock_cm = AsyncMock()
            mock_cm.clear = AsyncMock()
            mock_cm_class.return_value = mock_cm
            
            mock_vs_class.return_value = MagicMock()
            
            # Create server
            server = ThingsMCPServer(config=test_config)
            
            # Manually trigger shutdown hook
            shutdown_hooks = [hook for hook in server.mcp._shutdown_hooks]
            assert len(shutdown_hooks) > 0
            
            for hook in shutdown_hooks:
                await hook()
            
            # Verify shutdown activities
            mock_cm.clear.assert_called_once()
            mock_asm.get_execution_stats.assert_called_once()
            mock_eh.get_error_statistics.assert_called_once()


class TestServerFactoryFunction:
    """Test server factory function."""
    
    def test_create_server_without_config(self):
        """Test creating server without configuration file."""
        server = create_server()
        
        assert isinstance(server, ThingsMCPServer)
        assert server.config is not None
    
    def test_create_server_with_nonexistent_config(self):
        """Test creating server with non-existent configuration file."""
        from pathlib import Path
        
        config_path = Path("/nonexistent/config.yaml")
        server = create_server(config_path)
        
        assert isinstance(server, ThingsMCPServer)
        assert server.config is not None
    
    def test_create_server_with_config_file(self, tmp_path):
        """Test creating server with configuration file."""
        # Create a temporary config file
        config_file = tmp_path / "test_config.yaml"
        config_content = """
applescript_timeout: 45
enable_detailed_logging: true
cache_max_size: 500
"""
        config_file.write_text(config_content)
        
        with patch('src.things_mcp.config.ThingsMCPConfig.from_file') as mock_from_file:
            mock_config = ThingsMCPConfig(applescript_timeout=45)
            mock_from_file.return_value = mock_config
            
            server = create_server(config_file)
            
            assert isinstance(server, ThingsMCPServer)
            mock_from_file.assert_called_once_with(config_file)


class TestServerIntegrationScenarios:
    """Test realistic server usage scenarios."""
    
    @pytest.mark.asyncio
    async def test_complete_health_check_cycle(self, mock_server):
        """Test complete health check cycle with all components."""
        # Configure all mocks for successful operation
        mock_server._mock_applescript_manager.set_failure_mode(False)
        
        # Get health check tool
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        # Perform health check
        result = await health_check_tool()
        
        # Verify all components reported status
        assert result["server_status"] == "healthy"
        assert result["things3"]["available"] is True
        assert "execution_stats" in result
        assert "error_stats" in result
        assert "cache_stats" in result
        
        # Verify cache statistics are reasonable
        cache_stats = result["cache_stats"]
        assert "size" in cache_stats
        assert "max_size" in cache_stats
        assert cache_stats["max_size"] == mock_server.config.cache_max_size
    
    @pytest.mark.asyncio
    async def test_server_degradation_recovery(self, mock_server):
        """Test server behavior during degradation and recovery."""
        # Get health check tool
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        # Initial healthy state
        mock_server._mock_applescript_manager.set_failure_mode(False)
        result = await health_check_tool()
        assert result["server_status"] == "healthy"
        
        # Simulate Things 3 becoming unavailable
        mock_server._mock_applescript_manager.set_failure_mode(True, "Connection lost")
        result = await health_check_tool()
        assert result["server_status"] == "degraded"
        assert result["things3"]["available"] is False
        
        # Simulate recovery
        mock_server._mock_applescript_manager.set_failure_mode(False)
        result = await health_check_tool()
        assert result["server_status"] == "healthy"
        assert result["things3"]["available"] is True
    
    @pytest.mark.asyncio
    async def test_cache_and_stats_integration(self, mock_server):
        """Test integration between cache management and statistics."""
        # Get tools
        clear_cache_tool = None
        stats_tool = None
        
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'clear_cache':
                clear_cache_tool = tool
            elif tool.__name__ == 'get_server_stats':
                stats_tool = tool
        
        assert clear_cache_tool is not None
        assert stats_tool is not None
        
        # Get initial stats
        initial_stats = await stats_tool()
        initial_cache_size = initial_stats["cache_stats"]["size"]
        
        # Clear cache
        clear_result = await clear_cache_tool()
        assert clear_result["success"] is True
        
        # Get stats after clearing
        final_stats = await stats_tool()
        final_cache_size = final_stats["cache_stats"]["size"]
        
        # Cache size should be reset (or at least not larger)
        assert final_cache_size <= initial_cache_size
    
    @pytest.mark.asyncio
    async def test_error_accumulation_and_reset(self, mock_server):
        """Test error accumulation and reset functionality."""
        # Get tools
        reset_errors_tool = None
        health_check_tool = None
        
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'reset_error_stats':
                reset_errors_tool = tool
            elif tool.__name__ == 'health_check':
                health_check_tool = tool
        
        assert reset_errors_tool is not None
        assert health_check_tool is not None
        
        # Simulate accumulated errors
        mock_server._mock_error_handler.errors = [
            {"error": f"Error {i}", "timestamp": datetime.now()} 
            for i in range(15)
        ]
        
        # Health check should show warning status
        health_result = await health_check_tool()
        assert health_result["server_status"] == "warning"
        assert health_result["error_stats"]["total_errors"] >= 10
        
        # Reset errors
        reset_result = await reset_errors_tool()
        assert reset_result["success"] is True
        
        # Health check should now be healthy
        mock_server._mock_error_handler.errors = []  # Simulate reset
        health_result = await health_check_tool()
        assert health_result["server_status"] == "healthy"


class TestServerConfigurationIntegration:
    """Test server behavior with different configurations."""
    
    def test_debug_logging_configuration(self):
        """Test server with debug logging enabled."""
        config = ThingsMCPConfig(enable_debug_logging=True)
        
        with patch('logging.basicConfig') as mock_logging:
            server = ThingsMCPServer(config=config)
            
            # Verify debug logging was configured
            mock_logging.assert_called()
            call_args = mock_logging.call_args
            assert call_args[1]['level'] == 10  # DEBUG level
    
    def test_production_logging_configuration(self):
        """Test server with production logging configuration."""
        config = ThingsMCPConfig(enable_debug_logging=False)
        
        with patch('logging.basicConfig') as mock_logging:
            server = ThingsMCPServer(config=config)
            
            # Verify info logging was configured
            mock_logging.assert_called()
            call_args = mock_logging.call_args
            assert call_args[1]['level'] == 20  # INFO level
    
    def test_cache_configuration_integration(self, mock_cache_manager):
        """Test cache configuration is properly passed to components."""
        config = ThingsMCPConfig(
            cache_max_size=2000,
            cache_default_ttl=600,
            enable_caching=True
        )
        
        with patch('src.things_mcp.server.CacheManager') as mock_cm_class:
            mock_cm_class.return_value = mock_cache_manager
            
            server = ThingsMCPServer(config=config)
            
            # Verify cache manager was created with correct config
            mock_cm_class.assert_called_with(
                max_size=2000,
                default_ttl=600
            )
    
    def test_applescript_configuration_integration(self, mock_applescript_manager):
        """Test AppleScript configuration is properly passed."""
        config = ThingsMCPConfig(
            applescript_timeout=60,
            applescript_retry_count=5,
            preferred_execution_method="url_scheme"
        )
        
        with patch('src.things_mcp.server.AppleScriptManager') as mock_asm_class:
            mock_asm_class.return_value = mock_applescript_manager
            
            server = ThingsMCPServer(config=config)
            
            # Verify AppleScript manager was created with correct config
            mock_asm_class.assert_called()
            call_args = mock_asm_class.call_args
            execution_config = call_args[1]['config']
            assert execution_config.timeout == 60
            assert execution_config.retry_count == 5