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

from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.config import ThingsMCPConfig


class TestAppleScriptManagerInit:
    """Test AppleScript Manager initialization."""
    
    def test_init_with_default_config(self):
        """Test initialization with default configuration.""" 
        manager = AppleScriptManager()
        
        assert manager.timeout == 45  # default timeout
        assert manager.retry_count == 3  # default retry count
        # Cache removed in hybrid implementation
        assert hasattr(manager, 'auth_token')
    
    def test_init_with_custom_config(self):
        """Test initialization with custom configuration."""
        manager = AppleScriptManager(timeout=60, retry_count=5)
        
        assert manager.timeout == 60
        assert manager.retry_count == 5
        # Cache removed in hybrid implementation
        assert hasattr(manager, 'auth_token')
    
    def test_init_without_dependencies(self):
        """Test initialization without optional dependencies."""
        manager = AppleScriptManager()
        
        # Should initialize without error
        assert manager.timeout == 45
        assert manager.retry_count == 3
        # Cache removed in hybrid implementation


class TestAppleScriptExecution:
    """Test AppleScript execution functionality."""
    
    @pytest.fixture
    def manager_with_mocks(self):
        """Fixture providing manager with mocked dependencies."""
        manager = AppleScriptManager(timeout=5, retry_count=2)
        # Cache removed in hybrid implementation, no need to clear
        return manager
    
    @pytest.mark.asyncio
    async def test_execute_applescript_success(self, manager_with_mocks):
        """Test successful AppleScript execution."""
        script = 'tell application "Things3" to return version'
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock successful subprocess execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"3.20.1", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is True
            assert result["output"] == "3.20.1"
            assert "execution_time" in result
            
            # Verify subprocess was called correctly
            mock_create.assert_called_once_with(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
    
    @pytest.mark.asyncio
    async def test_execute_applescript_failure(self, manager_with_mocks):
        """Test failed AppleScript execution."""
        script = 'invalid applescript'
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock failed subprocess execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"syntax error")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is False
            assert "syntax error" in result["error"]
    
    @pytest.mark.asyncio
    async def test_execute_applescript_timeout(self, manager_with_mocks):
        """Test AppleScript execution timeout."""
        script = 'delay 10'
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_process.kill = AsyncMock()
            mock_process.wait = AsyncMock()
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_applescript(script)
            
            assert result["success"] is False
            assert "timed out" in result["error"].lower()
    
    @pytest.mark.asyncio
    async def test_execute_applescript_with_caching(self, manager_with_mocks):
        """Test AppleScript execution with caching."""
        script = 'tell application "Things3" to return version'
        cache_key = "todos_all"  # Use a cache key pattern that gets cached
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock successful subprocess execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"3.20.1", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            # First call should execute and cache
            result1 = await manager_with_mocks.execute_applescript(script, cache_key)
            assert result1["success"] is True
            assert result1["output"] == "3.20.1"
            
            # Second call should also execute (no caching in hybrid mode)
            result2 = await manager_with_mocks.execute_applescript(script, cache_key)
            assert result2["success"] is True
            assert result2["output"] == "3.20.1"  
            
            # Both calls should have been made
            assert mock_create.call_count == 2


class TestURLSchemeExecution:
    """Test URL scheme execution functionality."""
    
    @pytest.fixture
    def manager_with_mocks(self):
        """Fixture providing manager with mocked dependencies."""
        return AppleScriptManager()
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_success(self, manager_with_mocks):
        """Test successful URL scheme execution."""
        action = "add"
        parameters = {"title": "Test Todo", "notes": "Test notes"}
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            # Mock successful subprocess execution
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            assert "url" in result
            assert "things:///add" in result["url"]
            assert "message" in result
            
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
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
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
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Invalid URL scheme")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is False
            assert "Invalid URL scheme" in result["error"]
            assert "url" in result
    
    @pytest.mark.asyncio
    async def test_execute_url_scheme_without_parameters(self, manager_with_mocks):
        """Test URL scheme execution without parameters."""
        action = "show"
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_url_scheme(action)

            assert result["success"] is True
            assert result["url"].startswith("things:///show")
            assert "auth-token" in result["url"]
    
    @pytest.mark.asyncio
    async def test_url_parameter_encoding(self, manager_with_mocks):
        """Test URL parameter encoding handles special characters."""
        action = "add"
        parameters = {
            "title": "Todo with special chars: @#$%^&*()!",
            "notes": "Notes with\nnewlines and\ttabs",
            "tags": ["tag with spaces", "tag/with/slashes"]
        }
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.execute_url_scheme(action, parameters)
            
            assert result["success"] is True
            url = result["url"]
            
            # Special characters should be URL encoded
            assert "%20" in url  # Space
            assert "%0A" in url or "\\n" in url  # Newline (might be escaped differently)
            assert "%2C" in url  # Comma in tags
            
            # Should not contain unencoded special characters
            assert " " not in url.split("?")[1] if "?" in url else True
            assert "\n" not in url
            assert "\t" not in url


class TestThingsAvailabilityCheck:
    """Test Things 3 availability checking."""
    
    @pytest.fixture
    def manager_with_mocks(self):
        """Fixture providing manager with mocked dependencies."""
        return AppleScriptManager()
    
    @pytest.mark.asyncio
    async def test_check_things_availability_success(self, manager_with_mocks):
        """Test successful Things 3 availability check."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"true", b"")
            mock_process.returncode = 0
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.is_things_running()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_check_things_availability_failure(self, manager_with_mocks):
        """Test Things 3 availability check when Things is not available."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Application is not running")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.is_things_running()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_check_things_availability_timeout(self, manager_with_mocks):
        """Test Things 3 availability check timeout."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_process.kill = AsyncMock()
            mock_process.wait = AsyncMock()
            mock_create.return_value = mock_process
            
            result = await manager_with_mocks.is_things_running()
            
            assert result is False


class TestRetryLogic:
    """Test retry logic for failed operations."""
    
    @pytest.fixture
    def manager_with_retries(self):
        """Fixture providing manager with retry configuration."""
        return AppleScriptManager(timeout=5, retry_count=2)
    
    @pytest.mark.asyncio
    async def test_applescript_retry_success_on_second_attempt(self, manager_with_retries):
        """Test AppleScript retry succeeds on second attempt."""
        script = 'tell application "Things3" to return version'
        
        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:
            
            # First call fails, second succeeds
            process1 = AsyncMock()
            process1.communicate.return_value = (b"", b"Temporary error")
            process1.returncode = 1
            
            process2 = AsyncMock()
            process2.communicate.return_value = (b"3.21.15", b"") # Use actual Things version
            process2.returncode = 0
            
            mock_create.side_effect = [process1, process2]
            
            result = await manager_with_retries.execute_applescript(script)
            
            assert result["success"] is True
            assert result["output"] == "3.21.15"
            assert mock_create.call_count == 2
            assert mock_sleep.call_count == 1  # One retry delay
    
    @pytest.mark.asyncio
    async def test_applescript_retry_exhausted(self, manager_with_retries):
        """Test AppleScript retry exhaustion after all attempts fail."""
        script = 'tell application "Things3" to return version'
        
        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:
            
            # All attempts fail
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Persistent error")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            result = await manager_with_retries.execute_applescript(script)
            
            assert result["success"] is False
            assert "Persistent error" in result["error"]
            assert mock_create.call_count == 2  # Initial + 1 retry (retry_count=2)
            assert mock_sleep.call_count == 1  # One retry delay
    
    # URL scheme retry test removed - retry logic is already tested for AppleScript execution
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self, manager_with_retries):
        """Test exponential backoff delay calculation."""
        script = 'failing script'
        
        with patch('asyncio.create_subprocess_exec') as mock_create, \
             patch('asyncio.sleep') as mock_sleep:
            
            # All attempts fail
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"Error")
            mock_process.returncode = 1
            mock_create.return_value = mock_process
            
            await manager_with_retries.execute_applescript(script)
            
            # Check that sleep was called with exponential backoff
            sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
            assert len(sleep_calls) == 1  # 1 retry (retry_count=2 -> initial + 1 retry)
            assert sleep_calls[0] == 1  # First retry: 2^0 = 1


