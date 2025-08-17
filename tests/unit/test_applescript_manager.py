"""
Unit tests for the AppleScript Manager.

Tests AppleScript execution, URL scheme handling, caching, error handling,
and retry logic with comprehensive mocking to avoid Things 3 dependency.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call
from typing import Dict, Any, List

from src.things_mcp.services.applescript_manager import AppleScriptManager
from src.things_mcp.config import ThingsMCPConfig


class TestAppleScriptManagerInit:
    """Test AppleScript Manager initialization."""
    
    def test_init_with_default_config(self):
        """Test initialization with default configuration.""" 
        manager = AppleScriptManager()
        
        assert manager.config is not None
        assert manager.lock is not None
        assert hasattr(manager, 'timeout')
        assert hasattr(manager, 'retries')
    
    def test_init_with_custom_config(self):
        """Test initialization with custom configuration."""
        config = ThingsMCPConfig(
            applescript_timeout=60,
            applescript_retry_count=5,
            cache_max_size=1000
        )
        
        manager = AppleScriptManager(config=config)
        
        assert manager.config == config
        assert manager.timeout == 60
        assert manager.retries == 5
        
        assert manager.config.timeout == 60
        assert manager.config.retry_count == 5
        assert manager.config.cache_ttl == 600
        assert manager.error_handler == error_handler
        assert manager.cache_manager == cache_manager
    
    def test_init_without_dependencies(self):
        """Test initialization without optional dependencies."""
        config = ExecutionConfig()
        manager = AppleScriptManager(config=config)
        
        # Should initialize without error even without error_handler and cache_manager
        assert manager.config == config
        assert hasattr(manager, 'stats')


class TestAppleScriptExecution:
    """Test AppleScript execution functionality."""
    
    @pytest.fixture
    def manager_with_mocks(self, mock_error_handler, mock_cache_manager):
        """Fixture providing manager with mocked dependencies."""
        config = ExecutionConfig(timeout=5, retry_count=2)
        return AppleScriptManager(
            config=config,
            error_handler=mock_error_handler,
            cache_manager=mock_cache_manager
        )
    
    @pytest.mark.asyncio
    async def test_execute_applescript_success(self, manager_with_mocks):
        """Test successful AppleScript execution."""
        script = 'tell application "Things3" to return version'
        script_name = "version_check"
        
        with patch('subprocess.run') as mock_run:
            # Mock successful subprocess execution
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="3.20.1",
                stderr=""
            )
            
            result = await manager_with_mocks.execute_applescript(script, script_name)
            
            assert result["success"] is True
            assert result["output"] == "3.20.1"
            assert result["error"] is None
            assert result["method"] == "applescript"
            
            # Verify subprocess was called correctly
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args == ["osascript", "-e", script]
    
    @pytest.mark.asyncio
    async def test_execute_applescript_failure(self, manager_with_mocks):
        """Test failed AppleScript execution."""
        script = 'invalid applescript'
        
        with patch('subprocess.run') as mock_run:
            # Mock failed subprocess execution
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="syntax error"
            )
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is False
            assert result["output"] is None
            assert "syntax error" in result["error"]
            assert result["method"] == "applescript"
    
    @pytest.mark.asyncio
    async def test_execute_applescript_timeout(self, manager_with_mocks):
        """Test AppleScript execution timeout."""
        script = 'delay 10'
        
        with patch('subprocess.run') as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired("osascript", 5)
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is False
            assert "timeout" in result["error"].lower()
            assert result["method"] == "applescript"
    
    @pytest.mark.asyncio
    async def test_execute_applescript_with_caching(self, manager_with_mocks):
        """Test AppleScript execution with caching."""
        script = 'tell application "Things3" to return version'
        cache_key = "version_check"
        
        # Mock cache miss first, then hit
        manager_with_mocks.cache_manager.get.side_effect = [None, {"success": True, "output": "cached_result"}]
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="3.20.1",
                stderr=""
            )
            
            # First call should execute and cache
            result1 = await manager_with_mocks.execute_applescript(script, cache_key=cache_key)
            assert result1["success"] is True
            assert result1["output"] == "3.20.1"
            
            # Verify cache set was called
            manager_with_mocks.cache_manager.set.assert_called_once()
            
            # Second call should return cached result
            result2 = await manager_with_mocks.execute_applescript(script, cache_key=cache_key)
            assert result2["success"] is True
            assert result2["output"] == "cached_result"
            
            # Subprocess should only be called once
            assert mock_run.call_count == 1


class TestURLSchemeExecution:
    """Test URL scheme execution functionality."""
    
    @pytest.fixture
    def manager_with_mocks(self, mock_error_handler, mock_cache_manager):
        """Fixture providing manager with mocked dependencies."""
        config = ExecutionConfig(preferred_method="url_scheme")
        return AppleScriptManager(
            config=config,
            error_handler=mock_error_handler,
            cache_manager=mock_cache_manager
        )
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_success(self, manager_with_mocks):
        """Test successful URL scheme execution."""
        action = "add"
        parameters = {"title": "Test Todo", "notes": "Test notes"}
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            assert result["method"] == "url_scheme"
            assert "url" in result
            assert "things:///add" in result["url"]
            
            # Verify the URL was constructed correctly
            expected_url_parts = ["title=Test%20Todo", "notes=Test%20notes"]
            for part in expected_url_parts:
                assert part in result["url"]
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_with_complex_parameters(self, manager_with_mocks):
        """Test URL scheme execution with complex parameters."""
        action = "add"
        parameters = {
            "title": "Complex Todo",
            "tags": ["work", "urgent"],
            "when": "today",
            "deadline": "2024-12-31",
            "list-id": "project-123"
        }
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            url = result["url"]
            
            # Check that all parameters are properly encoded
            assert "title=Complex%20Todo" in url
            assert "tags=work%2Curgent" in url  # Comma-separated list
            assert "when=today" in url
            assert "deadline=2024-12-31" in url
            assert "list-id=project-123" in url
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_failure(self, manager_with_mocks):
        """Test failed URL scheme execution."""
        action = "invalid_action"
        parameters = {"title": "Test"}
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Invalid URL scheme"
            )
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is False
            assert "Invalid URL scheme" in result["error"]
            assert result["method"] == "url_scheme"
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_without_parameters(self, manager_with_mocks):
        """Test URL scheme execution without parameters."""
        action = "show"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            result = await manager_with_mocks.execute_url_scheme(action)
            
            assert result["success"] is True
            assert result["url"] == "things:///show"
    
    @pytest.mark.asyncio
    async def test_url_parameter_encoding(self, manager_with_mocks):
        """Test URL parameter encoding handles special characters."""
        action = "add"
        parameters = {
            "title": "Todo with special chars: @#$%^&*()!",
            "notes": "Notes with\nnewlines and\ttabs",
            "tags": ["tag with spaces", "tag/with/slashes"]
        }
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            url = result["url"]
            
            # Special characters should be URL encoded
            assert "%20" in url  # Space
            assert "%0A" in url or "%0D" in url  # Newline
            assert "%2F" in url  # Slash
            
            # Should not contain unencoded special characters
            assert " " not in url.split("?")[1] if "?" in url else True
            assert "\n" not in url
            assert "\t" not in url


class TestThingsAvailabilityCheck:
    """Test Things 3 availability checking."""
    
    @pytest.fixture
    def manager_with_mocks(self, mock_error_handler, mock_cache_manager):
        """Fixture providing manager with mocked dependencies."""
        config = ExecutionConfig()
        return AppleScriptManager(
            config=config,
            error_handler=mock_error_handler,
            cache_manager=mock_cache_manager
        )
    
    @pytest.mark.asyncio
    async def test_check_things_availability_success(self, manager_with_mocks):
        """Test successful Things 3 availability check."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="3.20.1",
                stderr=""
            )
            
            result = await manager_with_mocks.check_things_availability()
            
            assert result["success"] is True
            assert result["data"]["version"] == "3.20.1"
            assert result["data"]["available"] is True
            assert result["error"] is None
    
    @pytest.mark.asyncio
    async def test_check_things_availability_failure(self, manager_with_mocks):
        """Test Things 3 availability check when Things is not available."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Application is not running"
            )
            
            result = await manager_with_mocks.check_things_availability()
            
            assert result["success"] is False
            assert "not running" in result["error"].lower()
            assert result["data"] == {}
    
    @pytest.mark.asyncio
    async def test_check_things_availability_timeout(self, manager_with_mocks):
        """Test Things 3 availability check timeout."""
        with patch('subprocess.run') as mock_run:
            from subprocess import TimeoutExpired
            mock_run.side_effect = TimeoutExpired("osascript", 30)
            
            result = await manager_with_mocks.check_things_availability()
            
            assert result["success"] is False
            assert "timeout" in result["error"].lower()


class TestRetryLogic:
    """Test retry logic for failed operations."""
    
    @pytest.fixture
    def manager_with_retries(self, mock_error_handler, mock_cache_manager):
        """Fixture providing manager with retry configuration."""
        config = ExecutionConfig(retry_count=3, timeout=5)
        return AppleScriptManager(
            config=config,
            error_handler=mock_error_handler,
            cache_manager=mock_cache_manager
        )
    
    @pytest.mark.asyncio
    async def test_applescript_retry_success_on_second_attempt(self, manager_with_retries):
        """Test AppleScript retry succeeds on second attempt."""
        script = 'tell application "Things3" to return version'
        
        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep') as mock_sleep:
            
            # First call fails, second succeeds
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="Temporary error"),
                MagicMock(returncode=0, stdout="3.20.1", stderr="")
            ]
            
            result = await manager_with_retries.execute_applescript(script)
            
            assert result["success"] is True
            assert result["output"] == "3.20.1"
            assert mock_run.call_count == 2
            assert mock_sleep.call_count == 1  # One retry delay
    
    @pytest.mark.asyncio
    async def test_applescript_retry_exhausted(self, manager_with_retries):
        """Test AppleScript retry exhaustion after all attempts fail."""
        script = 'tell application "Things3" to return version'
        
        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep') as mock_sleep:
            
            # All attempts fail
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Persistent error"
            )
            
            result = await manager_with_retries.execute_applescript(script)
            
            assert result["success"] is False
            assert "Persistent error" in result["error"]
            assert mock_run.call_count == 3  # Initial + 2 retries
            assert mock_sleep.call_count == 2  # Two retry delays
    
    @pytest.mark.asyncio
    async def test_url_scheme_retry_logic(self, manager_with_retries):
        """Test URL scheme retry logic."""
        action = "add"
        parameters = {"title": "Test"}
        
        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep') as mock_sleep:
            
            # First call fails, second succeeds
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="Temporary failure"),
                MagicMock(returncode=0, stdout="", stderr="")
            ]
            
            result = await manager_with_retries.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            assert mock_run.call_count == 2
            assert mock_sleep.call_count == 1
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self, manager_with_retries):
        """Test exponential backoff delay calculation."""
        script = 'failing script'
        
        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep') as mock_sleep:
            
            # All attempts fail
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Error"
            )
            
            await manager_with_retries.execute_applescript(script)
            
            # Check that sleep was called with exponential backoff
            sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
            assert len(sleep_calls) == 2  # 2 retries
            assert sleep_calls[0] == 1  # First retry: 2^0 = 1
            assert sleep_calls[1] == 2  # Second retry: 2^1 = 2


class TestExecutionStatistics:
    """Test execution statistics tracking."""
    
    @pytest.fixture
    def manager_with_mocks(self, mock_error_handler, mock_cache_manager):
        """Fixture providing manager with mocked dependencies."""
        config = ExecutionConfig()
        return AppleScriptManager(
            config=config,
            error_handler=mock_error_handler,
            cache_manager=mock_cache_manager
        )
    
    @pytest.mark.asyncio
    async def test_execution_stats_tracking(self, manager_with_mocks):
        """Test execution statistics are properly tracked."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="result",
                stderr=""
            )
            
            # Execute several operations
            await manager_with_mocks.execute_applescript("script1")
            await manager_with_mocks.execute_applescript("script2")
            await manager_with_mocks.execute_url_scheme("add", {"title": "test"})
            
            stats = await manager_with_mocks.get_execution_stats()
            
            assert stats["total_executions"] >= 3
            assert stats["applescript_executions"] >= 2
            assert stats["url_scheme_executions"] >= 1
            assert stats["success_rate"] > 0
            assert "average_execution_time" in stats
    
    @pytest.mark.asyncio
    async def test_cache_hit_stats(self, manager_with_mocks):
        """Test cache hit statistics tracking."""
        script = "test script"
        cache_key = "test_key"
        
        # Mock cache behavior
        manager_with_mocks.cache_manager.get.side_effect = [
            None,  # Cache miss
            {"success": True, "output": "cached"}  # Cache hit
        ]
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="fresh",
                stderr=""
            )
            
            # First call - cache miss
            await manager_with_mocks.execute_applescript(script, cache_key=cache_key)
            
            # Second call - cache hit
            await manager_with_mocks.execute_applescript(script, cache_key=cache_key)
            
            stats = await manager_with_mocks.get_execution_stats()
            
            # Verify cache statistics are tracked
            assert "cache_hits" in stats
            assert "cache_misses" in stats


class TestErrorHandling:
    """Test error handling and logging."""
    
    @pytest.fixture
    def manager_with_mocks(self, mock_error_handler, mock_cache_manager):
        """Fixture providing manager with mocked dependencies."""
        config = ExecutionConfig(enable_logging=True)
        return AppleScriptManager(
            config=config,
            error_handler=mock_error_handler,
            cache_manager=mock_cache_manager
        )
    
    @pytest.mark.asyncio
    async def test_error_handler_called_on_failure(self, manager_with_mocks):
        """Test error handler is called when operations fail."""
        script = "failing script"
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Script error"
            )
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is False
            # Error handler should have been called
            assert len(manager_with_mocks.error_handler.errors) > 0
    
    @pytest.mark.asyncio
    async def test_exception_handling(self, manager_with_mocks):
        """Test handling of unexpected exceptions."""
        script = "test script"
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Unexpected error")
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is False
            assert "Unexpected error" in result["error"]
    
    @pytest.mark.asyncio
    async def test_logging_configuration(self, manager_with_mocks):
        """Test logging is properly configured."""
        # This test verifies logging setup - actual log output testing
        # would require more complex setup with log capture
        assert manager_with_mocks.config.enable_logging is True
        
        # Test that operations don't fail when logging is enabled
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="success",
                stderr=""
            )
            
            result = await manager_with_mocks.execute_applescript("test")
            assert result["success"] is True


class TestMethodSelection:
    """Test execution method selection logic."""
    
    @pytest.mark.asyncio
    async def test_preferred_method_applescript(self, mock_error_handler, mock_cache_manager):
        """Test preferred method selection for AppleScript."""
        config = ExecutionConfig(preferred_method="applescript")
        manager = AppleScriptManager(
            config=config,
            error_handler=mock_error_handler,
            cache_manager=mock_cache_manager
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="result",
                stderr=""
            )
            
            result = await manager.execute_applescript("test script")
            
            assert result["success"] is True
            assert result["method"] == "applescript"
    
    @pytest.mark.asyncio
    async def test_preferred_method_url_scheme(self, mock_error_handler, mock_cache_manager):
        """Test preferred method selection for URL scheme."""
        config = ExecutionConfig(preferred_method="url_scheme")
        manager = AppleScriptManager(
            config=config,
            error_handler=mock_error_handler,
            cache_manager=mock_cache_manager
        )
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr=""
            )
            
            result = await manager.execute_url_scheme("add", {"title": "test"})
            
            assert result["success"] is True
            assert result["method"] == "url_scheme"


class TestConfigurationValidation:
    """Test configuration validation and edge cases."""
    
    def test_execution_config_defaults(self):
        """Test ExecutionConfig default values."""
        config = ExecutionConfig()
        
        assert config.timeout == 30
        assert config.retry_count == 3
        assert config.cache_ttl == 300
        assert config.preferred_method == "auto"
        assert config.enable_logging is False
    
    def test_execution_config_custom_values(self):
        """Test ExecutionConfig with custom values."""
        config = ExecutionConfig(
            timeout=60,
            retry_count=5,
            cache_ttl=600,
            preferred_method="applescript",
            enable_logging=True
        )
        
        assert config.timeout == 60
        assert config.retry_count == 5
        assert config.cache_ttl == 600
        assert config.preferred_method == "applescript"
        assert config.enable_logging is True
    
    def test_invalid_configuration_values(self):
        """Test handling of invalid configuration values."""
        # These should be handled gracefully or raise appropriate errors
        config = ExecutionConfig(
            timeout=0,  # Invalid timeout
            retry_count=-1,  # Invalid retry count
            cache_ttl=-100  # Invalid TTL
        )
        
        # The configuration should either handle these gracefully
        # or raise validation errors
        assert isinstance(config.timeout, (int, float))
        assert isinstance(config.retry_count, int)
        assert isinstance(config.cache_ttl, int)


class TestAppleScriptManagerStrategicCoverage:
    """Strategic test coverage for AppleScript manager - targeting 6.40% -> 15%."""
    
    @pytest.mark.asyncio
    async def test_execute_applescript_success(self):
        """Test successful AppleScript execution."""
        config = ThingsMCPConfig()
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = '{"result": "success"}'
            mock_run.return_value.stderr = ''
            
            result = await manager.execute_applescript('test script')
            
            assert result.success is True
            assert result.output == '{"result": "success"}'
            assert result.error is None
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_applescript_failure(self):
        """Test AppleScript execution failure."""
        config = ThingsMCPConfig()
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 1
            mock_run.return_value.stdout = ''
            mock_run.return_value.stderr = 'AppleScript error'
            
            result = await manager.execute_applescript('test script')
            
            assert result.success is False
            assert result.error == 'AppleScript error'
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_url_scheme_success(self):
        """Test successful URL scheme execution."""
        config = ThingsMCPConfig()
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = 'URL executed successfully'
            mock_run.return_value.stderr = ''
            
            result = await manager.execute_url_scheme('things:///add?title=Test')
            
            assert result.success is True
            assert 'URL executed successfully' in result.output
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_things_availability(self):
        """Test Things availability check."""
        config = ThingsMCPConfig()
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = 'true'
            mock_run.return_value.stderr = ''
            
            result = await manager.check_things_availability()
            
            assert result.success is True
            mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_todos_method(self):
        """Test get_todos method."""
        config = ThingsMCPConfig()
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = '[]'
            mock_run.return_value.stderr = ''
            
            result = await manager.get_todos()
            
            assert isinstance(result, list)
            mock_run.assert_called()

    @pytest.mark.asyncio  
    async def test_get_projects_method(self):
        """Test get_projects method."""
        config = ThingsMCPConfig()
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = '[]'
            mock_run.return_value.stderr = ''
            
            result = await manager.get_projects()
            
            assert isinstance(result, list)
            mock_run.assert_called()

    @pytest.mark.asyncio
    async def test_get_areas_method(self):
        """Test get_areas method."""
        config = ThingsMCPConfig()
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = '[]'  
            mock_run.return_value.stderr = ''
            
            result = await manager.get_areas()
            
            assert isinstance(result, list)
            mock_run.assert_called()

    def test_manager_properties(self):
        """Test manager property access."""
        config = ThingsMCPConfig(
            applescript_timeout=45,
            applescript_retry_count=4
        )
        manager = AppleScriptManager(config=config)
        
        assert manager.timeout == 45
        assert manager.retries == 4
        assert manager.config.applescript_timeout == 45

    @pytest.mark.asyncio
    async def test_subprocess_exception_handling(self):
        """Test subprocess exception handling."""
        config = ThingsMCPConfig()
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = Exception("Subprocess failed")
            
            result = await manager.execute_applescript('test script')
            
            assert result.success is False
            assert "Subprocess failed" in result.error

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test timeout handling in subprocess calls."""
        config = ThingsMCPConfig(applescript_timeout=1)  # Very short timeout
        manager = AppleScriptManager(config=config)
        
        with patch('subprocess.run') as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired('cmd', 1)
            
            result = await manager.execute_applescript('long running script')
            
            assert result.success is False
            assert "timeout" in result.error.lower() or "expired" in result.error.lower()