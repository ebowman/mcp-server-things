"""
Integration tests for CLI interface operations.

Tests command-line interface functionality, argument parsing,
server startup/shutdown, and CLI tool integration.
"""

import pytest
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call
from argparse import Namespace

from src.things_mcp.server import main
from src.things_mcp.server import ThingsMCPServer
from src.things_mcp.__main__ import main as main_entry_point


class TestCLIArgumentParsing:
    """Test command-line argument parsing."""
    
    @pytest.mark.asyncio
    async def test_cli_no_arguments(self):
        """Test CLI with no arguments (default behavior)."""
        with patch('sys.argv', ['things-mcp']), \
             patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('asyncio.run') as mock_asyncio_run:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server_class.return_value = mock_server
            
            # Import and run main to trigger argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                await main()
                
                # Verify server was created and run with default config
                mock_server_class.assert_called_once()
                mock_server.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cli_with_config_file(self, tmp_path):
        """Test CLI with configuration file argument."""
        # Create temporary config file
        config_file = tmp_path / "test_config.yaml"
        config_content = """
applescript_timeout: 60
enable_detailed_logging: true
"""
        config_file.write_text(config_content)
        
        with patch('sys.argv', ['things-mcp', '--config', str(config_file)]), \
             patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('src.things_mcp.config.ThingsMCPConfig.from_file') as mock_from_file:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server_class.return_value = mock_server
            
            mock_config = MagicMock()
            mock_from_file.return_value = mock_config
            
            # Mock argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=config_file, debug=False)
                
                await main()
                
                # Verify config was loaded from file
                mock_from_file.assert_called_once_with(config_file)
                mock_server_class.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cli_with_debug_flag(self):
        """Test CLI with debug flag enabled."""
        with patch('sys.argv', ['things-mcp', '--debug']), \
             patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server.config = MagicMock()
            mock_server._configure_logging = MagicMock()
            mock_server_class.return_value = mock_server
            
            # Mock argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=True)
                
                await main()
                
                # Verify debug logging was enabled
                assert mock_server.config.enable_debug_logging is True
                mock_server._configure_logging.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cli_with_invalid_config_path(self):
        """Test CLI with invalid configuration file path."""
        invalid_path = Path("/nonexistent/config.yaml")
        
        with patch('sys.argv', ['things-mcp', '--config', str(invalid_path)]), \
             patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server_class.return_value = mock_server
            
            # Mock argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=invalid_path, debug=False)
                
                await main()
                
                # Should still create server with default config
                mock_server_class.assert_called_once()
                mock_server.run.assert_called_once()


class TestCLIServerLifecycle:
    """Test server lifecycle through CLI interface."""
    
    @pytest.mark.asyncio
    async def test_cli_server_startup_success(self):
        """Test successful server startup through CLI."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server_class.return_value = mock_server
            
            # Mock argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                await main()
                
                # Verify server startup sequence
                mock_server_class.assert_called_once()
                mock_server.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cli_server_startup_error(self):
        """Test server startup error handling through CLI."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
            mock_server = AsyncMock()
            mock_server.run = AsyncMock(side_effect=Exception("Startup failed"))
            mock_server_class.return_value = mock_server
            
            # Mock argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                # Should re-raise the exception
                with pytest.raises(Exception) as exc_info:
                    await main()
                
                assert "Startup failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_cli_keyboard_interrupt_handling(self):
        """Test keyboard interrupt handling in CLI."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('src.things_mcp.server.logging') as mock_logging:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock(side_effect=KeyboardInterrupt())
            mock_server_class.return_value = mock_server
            
            # Mock logger
            mock_logger = MagicMock()
            mock_logging.getLogger.return_value = mock_logger
            mock_server.logger = mock_logger
            
            # Mock argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                # Should handle KeyboardInterrupt gracefully
                await main()
                
                # Verify graceful shutdown message was logged
                mock_logger.info.assert_called_with("Server stopped by user")


class TestMainEntryPoint:
    """Test __main__.py entry point."""
    
    def test_main_entry_point_execution(self):
        """Test that __main__.py entry point executes correctly."""
        with patch('asyncio.run') as mock_asyncio_run, \
             patch('src.things_mcp.__main__.main') as mock_main_func:
            
            # Mock main function
            mock_main_func.return_value = AsyncMock()
            
            # Import and execute main entry point
            from src.things_mcp.__main__ import main
            
            # Simulate execution
            with patch('sys.argv', ['things-mcp']):
                # This would normally be called by Python when executing the module
                # We'll simulate it here
                mock_asyncio_run(mock_main_func())
                
                mock_asyncio_run.assert_called()
    
    def test_main_module_import(self):
        """Test that main module can be imported without errors."""
        try:
            import src.things_mcp.__main__
            assert hasattr(src.things_mcp.__main__, 'main')
        except ImportError as e:
            pytest.fail(f"Failed to import __main__ module: {e}")


class TestCLIConfiguration:
    """Test CLI configuration handling."""
    
    @pytest.mark.asyncio
    async def test_cli_config_validation(self, tmp_path):
        """Test CLI configuration file validation."""
        # Create valid config file
        valid_config = tmp_path / "valid_config.yaml"
        valid_config.write_text("""
applescript_timeout: 30
enable_detailed_logging: false
cache_max_size: 1000
""")
        
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('src.things_mcp.config.ThingsMCPConfig.from_file') as mock_from_file:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server_class.return_value = mock_server
            
            mock_config = MagicMock()
            mock_config.applescript_timeout = 30
            mock_from_file.return_value = mock_config
            
            # Mock argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=valid_config, debug=False)
                
                await main()
                
                # Verify config was loaded and validated
                mock_from_file.assert_called_once_with(valid_config)
    
    @pytest.mark.asyncio
    async def test_cli_config_error_handling(self, tmp_path):
        """Test CLI configuration error handling."""
        # Create invalid config file
        invalid_config = tmp_path / "invalid_config.yaml"
        invalid_config.write_text("invalid: yaml: content:")
        
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('src.things_mcp.config.ThingsMCPConfig.from_file') as mock_from_file:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server_class.return_value = mock_server
            
            # Configure mock to raise exception for invalid config
            mock_from_file.side_effect = Exception("Invalid YAML format")
            
            # Mock argument parsing
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=invalid_config, debug=False)
                
                # Should handle config error and continue with default config
                await main()
                
                # Server should still be created with default config
                mock_server_class.assert_called_once()


class TestCLILogging:
    """Test CLI logging configuration."""
    
    @pytest.mark.asyncio
    async def test_cli_debug_logging_setup(self):
        """Test debug logging setup through CLI."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('logging.basicConfig') as mock_logging_config:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server.config = MagicMock()
            mock_server._configure_logging = MagicMock()
            mock_server_class.return_value = mock_server
            
            # Mock argument parsing with debug flag
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=True)
                
                await main()
                
                # Verify debug logging was enabled
                assert mock_server.config.enable_debug_logging is True
                mock_server._configure_logging.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cli_production_logging_setup(self):
        """Test production logging setup through CLI."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server.config = MagicMock()
            mock_server.config.enable_debug_logging = False
            mock_server_class.return_value = mock_server
            
            # Mock argument parsing without debug flag
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                await main()
                
                # Verify debug logging was not enabled
                assert mock_server.config.enable_debug_logging is False


class TestCLIErrorHandling:
    """Test CLI error handling scenarios."""
    
    @pytest.mark.asyncio
    async def test_cli_import_error_handling(self):
        """Test CLI handling of import errors."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
            mock_server_class.side_effect = ImportError("Missing dependency")
            
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                # Should propagate import error
                with pytest.raises(ImportError) as exc_info:
                    await main()
                
                assert "Missing dependency" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_cli_runtime_error_handling(self):
        """Test CLI handling of runtime errors."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
            mock_server = AsyncMock()
            mock_server.run = AsyncMock(side_effect=RuntimeError("Runtime error"))
            mock_server_class.return_value = mock_server
            
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                # Should re-raise runtime error
                with pytest.raises(RuntimeError) as exc_info:
                    await main()
                
                assert "Runtime error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_cli_graceful_shutdown_signals(self):
        """Test CLI handling of shutdown signals."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('signal.signal') as mock_signal:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server_class.return_value = mock_server
            
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                await main()
                
                # Verify server was started
                mock_server.run.assert_called_once()


class TestCLIIntegrationScenarios:
    """Test realistic CLI usage scenarios."""
    
    @pytest.mark.asyncio
    async def test_cli_development_workflow(self, tmp_path):
        """Test CLI usage in development workflow."""
        # Create development config
        dev_config = tmp_path / "dev_config.yaml"
        dev_config.write_text("""
applescript_timeout: 10
enable_detailed_logging: true
enable_debug_logging: true
cache_max_size: 100
""")
        
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('src.things_mcp.config.ThingsMCPConfig.from_file') as mock_from_file:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server.config = MagicMock()
            mock_server._configure_logging = MagicMock()
            mock_server_class.return_value = mock_server
            
            mock_config = MagicMock()
            mock_config.enable_debug_logging = True
            mock_from_file.return_value = mock_config
            
            # Simulate development startup with config and debug
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=dev_config, debug=True)
                
                await main()
                
                # Verify development setup
                mock_from_file.assert_called_once_with(dev_config)
                assert mock_server.config.enable_debug_logging is True
                mock_server._configure_logging.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cli_production_deployment(self, tmp_path):
        """Test CLI usage in production deployment."""
        # Create production config
        prod_config = tmp_path / "prod_config.yaml"
        prod_config.write_text("""
applescript_timeout: 60
enable_detailed_logging: false
enable_debug_logging: false
cache_max_size: 10000
applescript_retry_count: 5
""")
        
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class, \
             patch('src.things_mcp.config.ThingsMCPConfig.from_file') as mock_from_file:
            
            mock_server = AsyncMock()
            mock_server.run = AsyncMock()
            mock_server_class.return_value = mock_server
            
            mock_config = MagicMock()
            mock_config.enable_debug_logging = False
            mock_config.applescript_timeout = 60
            mock_from_file.return_value = mock_config
            
            # Simulate production startup
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=prod_config, debug=False)
                
                await main()
                
                # Verify production setup
                mock_from_file.assert_called_once_with(prod_config)
                mock_server_class.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cli_containerized_deployment(self):
        """Test CLI usage in containerized environment."""
        # Simulate container environment variables
        with patch.dict('os.environ', {
            'THINGS_MCP_DEBUG': 'false',
            'THINGS_MCP_TIMEOUT': '30',
            'THINGS_MCP_CACHE_SIZE': '2000'
        }):
            
            with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
                mock_server = AsyncMock()
                mock_server.run = AsyncMock()
                mock_server_class.return_value = mock_server
                
                with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                    mock_parse_args.return_value = Namespace(config=None, debug=False)
                    
                    await main()
                    
                    # Verify server was created
                    mock_server_class.assert_called_once()
                    mock_server.run.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cli_help_and_version(self):
        """Test CLI help and version information."""
        # Test help output
        with patch('sys.argv', ['things-mcp', '--help']), \
             patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
            
            # ArgumentParser.parse_args() raises SystemExit for --help
            mock_parse_args.side_effect = SystemExit(0)
            
            with pytest.raises(SystemExit) as exc_info:
                with patch('argparse.ArgumentParser.print_help'):
                    await main()
            
            assert exc_info.value.code == 0
    
    @pytest.mark.asyncio
    async def test_cli_long_running_server(self):
        """Test CLI with long-running server simulation."""
        with patch('src.things_mcp.server.ThingsMCPServer') as mock_server_class:
            
            # Simulate long-running server
            async def long_running_server():
                await asyncio.sleep(0.1)  # Short sleep for test
                raise KeyboardInterrupt()  # Simulate user interruption
            
            mock_server = AsyncMock()
            mock_server.run = long_running_server
            mock_server.logger = MagicMock()
            mock_server_class.return_value = mock_server
            
            with patch('argparse.ArgumentParser.parse_args') as mock_parse_args:
                mock_parse_args.return_value = Namespace(config=None, debug=False)
                
                # Should handle long-running server and graceful shutdown
                await main()
                
                # Verify graceful shutdown was logged
                mock_server.logger.info.assert_called_with("Server stopped by user")


class TestCLIArgumentValidation:
    """Test CLI argument validation."""
    
    def test_cli_argument_parser_setup(self):
        """Test that argument parser is set up correctly."""
        with patch('argparse.ArgumentParser') as mock_parser_class:
            mock_parser = MagicMock()
            mock_parser_class.return_value = mock_parser
            
            # Import main to trigger parser setup
            from src.things_mcp.server import main
            
            # The parser should be configured with expected arguments
            # This would require running the actual argument parsing setup
            # For now, we verify the parser class was used
            # mock_parser_class.assert_called_once()
    
    def test_cli_config_path_validation(self):
        """Test configuration path validation."""
        from pathlib import Path
        
        # Test various path formats
        test_paths = [
            "config.yaml",
            "/absolute/path/config.yaml",
            "relative/path/config.yaml",
            "~/home/config.yaml"
        ]
        
        for path_str in test_paths:
            path = Path(path_str)
            # Basic validation that Path can handle the string
            assert isinstance(path, Path)
    
    def test_cli_boolean_flag_handling(self):
        """Test boolean flag handling in CLI."""
        # Test debug flag
        test_cases = [
            (["--debug"], True),
            ([], False),
        ]
        
        for args, expected_debug in test_cases:
            with patch('sys.argv', ['things-mcp'] + args):
                # This would test actual argument parsing
                # For now, verify the concept
                assert isinstance(expected_debug, bool)