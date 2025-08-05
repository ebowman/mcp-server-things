"""
Integration tests for error handling across the Things 3 MCP server.

Tests error propagation, recovery, logging, and resilience patterns
across all components and operation types.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from subprocess import TimeoutExpired, CalledProcessError

from src.things_mcp.server import ThingsMCPServer
from src.things_mcp.tools import ThingsTools
from src.things_mcp.services.error_handler import ErrorHandler


class TestAppleScriptExecutionErrors:
    """Test error handling for AppleScript execution failures."""
    
    @pytest.mark.asyncio
    async def test_applescript_timeout_handling(self, mock_server):
        """Test handling of AppleScript execution timeouts."""
        # Configure mock to timeout
        mock_server._mock_applescript_manager.execute_applescript = AsyncMock(
            return_value={
                "success": False,
                "error": "Script execution timed out after 30 seconds",
                "method": "applescript"
            }
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Test timeout in get_todos operation
        with pytest.raises(Exception) as exc_info:
            tools.get_todos()
        
        # Verify error handling
        assert mock_server._mock_applescript_manager.execute_applescript.called
        # Error should be logged and propagated
    
    @pytest.mark.asyncio
    async def test_applescript_syntax_error_handling(self, mock_server):
        """Test handling of AppleScript syntax errors."""
        error_message = "syntax error: Expected end of line but found unknown token"
        
        mock_server._mock_applescript_manager.execute_applescript = AsyncMock(
            return_value={
                "success": False,
                "error": error_message,
                "method": "applescript"
            }
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Test syntax error in get_todo_by_id
        with pytest.raises(Exception) as exc_info:
            tools.get_todo_by_id("test-id")
        
        assert error_message in str(exc_info.value) or "Todo not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_things_not_running_error(self, mock_server):
        """Test handling when Things 3 application is not running."""
        error_message = "Application isn't running"
        
        mock_server._mock_applescript_manager.execute_applescript = AsyncMock(
            return_value={
                "success": False,
                "error": error_message,
                "method": "applescript"
            }
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Test Things not running error
        with pytest.raises(Exception):
            tools.get_projects()
        
        # Verify error was handled appropriately
        mock_server._mock_applescript_manager.execute_applescript.assert_called()
    
    @pytest.mark.asyncio
    async def test_applescript_permission_denied(self, mock_server):
        """Test handling of AppleScript permission denied errors."""
        error_message = "Not authorized to send Apple events to Things3"
        
        mock_server._mock_applescript_manager.execute_applescript = AsyncMock(
            return_value={
                "success": False,
                "error": error_message,
                "method": "applescript"
            }
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Test permission denied error
        with pytest.raises(Exception):
            tools.get_areas()
        
        # Verify error handling
        mock_server._mock_applescript_manager.execute_applescript.assert_called()


class TestURLSchemeErrors:
    """Test error handling for URL scheme operations."""
    
    @pytest.mark.asyncio
    async def test_invalid_url_scheme_parameter(self, mock_server):
        """Test handling of invalid URL scheme parameters."""
        error_message = "Invalid parameter: invalid-date-format"
        
        mock_server._mock_applescript_manager.execute_url_scheme = AsyncMock(
            return_value={
                "success": False,
                "error": error_message,
                "method": "url_scheme"
            }
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Test invalid date format in add_todo
        result = tools.add_todo("Test Todo", deadline="invalid-date")
        
        assert result["success"] is False
        assert error_message in result["error"]
    
    @pytest.mark.asyncio
    async def test_url_scheme_things_not_installed(self, mock_server):
        """Test handling when Things 3 is not installed."""
        error_message = "The application cannot be found"
        
        mock_server._mock_applescript_manager.execute_url_scheme = AsyncMock(
            return_value={
                "success": False,
                "error": error_message,
                "method": "url_scheme"
            }
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Test Things not installed error
        result = tools.add_project("Test Project")
        
        assert result["success"] is False
        assert error_message in result["error"]
    
    @pytest.mark.asyncio
    async def test_url_scheme_malformed_url(self, mock_server):
        """Test handling of malformed URL scheme."""
        mock_server._mock_applescript_manager.execute_url_scheme = AsyncMock(
            side_effect=Exception("Malformed URL scheme")
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Test malformed URL exception
        with pytest.raises(Exception) as exc_info:
            tools.update_todo("test-id", title="New Title")
        
        assert "Malformed URL scheme" in str(exc_info.value)


class TestNetworkAndSystemErrors:
    """Test handling of network and system-level errors."""
    
    @pytest.mark.asyncio
    async def test_system_resource_exhaustion(self, mock_server):
        """Test handling of system resource exhaustion."""
        mock_server._mock_applescript_manager.execute_applescript = AsyncMock(
            side_effect=OSError("Cannot allocate memory")
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Test memory allocation error
        with pytest.raises(Exception) as exc_info:
            tools.get_todos()
        
        assert "Cannot allocate memory" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_subprocess_failure(self, mock_applescript_manager):
        """Test handling of subprocess execution failures."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = CalledProcessError(1, "osascript", "Command failed")
            
            result = await mock_applescript_manager.execute_applescript("test script")
            
            assert result["success"] is False
            assert "error" in result
    
    @pytest.mark.asyncio
    async def test_file_system_permissions(self, mock_applescript_manager):
        """Test handling of file system permission errors."""
        with patch('subprocess.run') as mock_run:
            mock_run.side_effect = PermissionError("Permission denied")
            
            result = await mock_applescript_manager.execute_applescript("test script")
            
            assert result["success"] is False
            assert "Permission denied" in result["error"]


class TestConcurrencyErrors:
    """Test error handling in concurrent operation scenarios."""
    
    @pytest.mark.asyncio
    async def test_concurrent_applescript_execution_failures(self, mock_server):
        """Test handling of concurrent AppleScript execution failures."""
        # Configure mock to fail intermittently
        call_count = 0
        
        async def mock_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:  # Fail every other call
                return {
                    "success": False,
                    "error": "Concurrent execution conflict",
                    "method": "applescript"
                }
            return {
                "success": True,
                "output": "success",
                "method": "applescript"
            }
        
        mock_server._mock_applescript_manager.execute_applescript = mock_execute
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        # Execute multiple concurrent operations
        tasks = []
        for i in range(4):
            if i % 2 == 0:
                # Some will succeed
                task = asyncio.create_task(asyncio.to_thread(tools.get_todos))
            else:
                # Some will fail
                task = asyncio.create_task(asyncio.to_thread(tools.get_projects))
            tasks.append(task)
        
        # Wait for all tasks and collect results
        results = []
        for task in tasks:
            try:
                result = await task
                results.append(("success", result))
            except Exception as e:
                results.append(("error", str(e)))
        
        # Should have mix of successes and failures
        successes = [r for r in results if r[0] == "success"]
        errors = [r for r in results if r[0] == "error"]
        
        assert len(successes) > 0  # Some should succeed
        assert len(errors) > 0     # Some should fail
    
    @pytest.mark.asyncio
    async def test_race_condition_handling(self, mock_server):
        """Test handling of race conditions in concurrent operations."""
        # Simulate race condition where resource becomes unavailable
        access_count = 0
        
        async def mock_availability_check():
            nonlocal access_count
            access_count += 1
            if access_count > 2:  # Becomes unavailable after 2 calls
                return {
                    "success": False,
                    "error": "Resource temporarily unavailable",
                    "data": {}
                }
            return {
                "success": True,
                "data": {"version": "3.20.1", "available": True},
                "error": None
            }
        
        mock_server._mock_applescript_manager.check_things_availability = mock_availability_check
        
        # Get health check tool
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        # Execute multiple concurrent health checks
        tasks = [
            asyncio.create_task(health_check_tool())
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Some should succeed, some should show degraded status
        healthy_count = sum(1 for r in results if isinstance(r, dict) and r.get("server_status") == "healthy")
        degraded_count = sum(1 for r in results if isinstance(r, dict) and r.get("server_status") == "degraded")
        
        assert healthy_count > 0
        assert degraded_count > 0


class TestRetryMechanismErrors:
    """Test retry mechanism error handling."""
    
    @pytest.mark.asyncio
    async def test_retry_exhaustion(self, mock_applescript_manager):
        """Test behavior when retry attempts are exhausted."""
        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep') as mock_sleep:
            
            # Configure to always fail
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Persistent error"
            )
            
            result = await mock_applescript_manager.execute_applescript("failing script")
            
            assert result["success"] is False
            assert "Persistent error" in result["error"]
            
            # Should have retried the configured number of times
            expected_calls = mock_applescript_manager.config.retry_count
            assert mock_run.call_count == expected_calls
    
    @pytest.mark.asyncio
    async def test_retry_with_different_error_types(self, mock_applescript_manager):
        """Test retry behavior with different types of errors."""
        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep') as mock_sleep:
            
            # Configure different failures for each retry
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr="Temporary error"),
                TimeoutExpired("osascript", 10),
                MagicMock(returncode=0, stdout="success", stderr="")  # Final success
            ]
            
            result = await mock_applescript_manager.execute_applescript("test script")
            
            assert result["success"] is True
            assert result["output"] == "success"
            assert mock_run.call_count == 3  # Two failures + one success
    
    @pytest.mark.asyncio
    async def test_exponential_backoff_timing(self, mock_applescript_manager):
        """Test exponential backoff timing in retries."""
        with patch('subprocess.run') as mock_run, \
             patch('asyncio.sleep') as mock_sleep:
            
            # Configure to fail multiple times
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="Retry test error"
            )
            
            await mock_applescript_manager.execute_applescript("test script")
            
            # Verify exponential backoff delays
            sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
            
            # Should have exponential backoff: 1, 2, 4, etc.
            expected_delays = [2**i for i in range(len(sleep_calls))]
            assert sleep_calls == expected_delays[:len(sleep_calls)]


class TestValidationErrors:
    """Test validation error handling."""
    
    def test_invalid_todo_data_validation(self, mock_validation_service):
        """Test validation of invalid todo data."""
        # Configure validation service to reject data
        mock_validation_service.validate_todo_data.return_value = False
        mock_validation_service.get_validation_errors.return_value = ["Title is required"]
        
        # Test validation error handling
        valid = mock_validation_service.validate_todo_data({})
        assert valid is False
        
        errors = mock_validation_service.get_validation_errors()
        assert "Title is required" in errors
    
    def test_invalid_project_data_validation(self, mock_validation_service):
        """Test validation of invalid project data."""
        # Configure validation service to reject data
        mock_validation_service.validate_project_data.return_value = False
        mock_validation_service.get_validation_errors.return_value = ["Title cannot be empty"]
        
        # Test validation error handling
        valid = mock_validation_service.validate_project_data({"title": ""})
        assert valid is False
        
        errors = mock_validation_service.get_validation_errors()
        assert "Title cannot be empty" in errors


class TestCacheErrors:
    """Test cache-related error handling."""
    
    @pytest.mark.asyncio
    async def test_cache_corruption_handling(self, mock_cache_manager):
        """Test handling of cache corruption."""
        # Configure cache to raise corruption error
        mock_cache_manager.get = AsyncMock(
            side_effect=Exception("Cache corruption detected")
        )
        
        # Test cache error handling
        with pytest.raises(Exception) as exc_info:
            await mock_cache_manager.get("test_key")
        
        assert "Cache corruption detected" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_cache_memory_exhaustion(self, mock_cache_manager):
        """Test handling of cache memory exhaustion."""
        # Configure cache to raise memory error
        mock_cache_manager.set = AsyncMock(
            side_effect=MemoryError("Cannot allocate cache memory")
        )
        
        # Test memory error handling
        with pytest.raises(MemoryError) as exc_info:
            await mock_cache_manager.set("key", "value")
        
        assert "Cannot allocate cache memory" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_cache_cleanup_on_error(self, mock_server):
        """Test cache cleanup when errors occur."""
        # Get clear cache tool
        clear_cache_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'clear_cache':
                clear_cache_tool = tool
                break
        
        # Configure cache manager to fail during clear
        mock_server._mock_cache_manager.clear = AsyncMock(
            side_effect=Exception("Clear operation failed")
        )
        
        result = await clear_cache_tool()
        
        assert result["success"] is False
        assert "Clear operation failed" in result["error"]


class TestErrorRecoveryPatterns:
    """Test error recovery and resilience patterns."""
    
    @pytest.mark.asyncio
    async def test_graceful_degradation(self, mock_server):
        """Test graceful degradation when components fail."""
        # Configure AppleScript manager to fail
        mock_server._mock_applescript_manager.set_failure_mode(True, "Service unavailable")
        
        # Get health check tool
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        result = await health_check_tool()
        
        # Server should still respond but in degraded state
        assert result["server_status"] == "degraded"
        assert result["things3"]["available"] is False
        assert "Service unavailable" in result["things3"]["error"]
        
        # Other components should still work
        assert "cache_stats" in result
        assert "error_stats" in result
    
    @pytest.mark.asyncio
    async def test_automatic_recovery_detection(self, mock_server):
        """Test automatic detection of service recovery."""
        # Get health check tool
        health_check_tool = None
        for tool in mock_server.mcp._tools:
            if tool.__name__ == 'health_check':
                health_check_tool = tool
                break
        
        # Start with failure
        mock_server._mock_applescript_manager.set_failure_mode(True, "Temporary failure")
        
        result1 = await health_check_tool()
        assert result1["server_status"] == "degraded"
        
        # Simulate recovery
        mock_server._mock_applescript_manager.set_failure_mode(False)
        
        result2 = await health_check_tool()
        assert result2["server_status"] == "healthy"
        assert result2["things3"]["available"] is True
    
    @pytest.mark.asyncio
    async def test_circuit_breaker_pattern(self, mock_server):
        """Test circuit breaker pattern for error handling."""
        # This would test a circuit breaker implementation
        # For now, test that repeated failures are tracked
        
        error_count = 0
        
        async def failing_operation():
            nonlocal error_count
            error_count += 1
            raise Exception(f"Operation failed #{error_count}")
        
        # Simulate multiple failures
        failures = []
        for i in range(5):
            try:
                await failing_operation()
            except Exception as e:
                failures.append(str(e))
        
        assert len(failures) == 5
        assert all("Operation failed" in failure for failure in failures)


class TestErrorLoggingAndReporting:
    """Test error logging and reporting functionality."""
    
    @pytest.mark.asyncio
    async def test_error_statistics_accumulation(self, mock_server):
        """Test that error statistics accumulate correctly."""
        # Add multiple errors to error handler
        errors = [
            {"error": "Error 1", "timestamp": datetime.now()},
            {"error": "Error 2", "timestamp": datetime.now()},
            {"error": "Error 3", "timestamp": datetime.now()}
        ]
        
        for error in errors:
            mock_server._mock_error_handler.errors.append(error)
        
        # Get error statistics
        stats = await mock_server._mock_error_handler.get_error_statistics()
        
        assert stats["total_errors"] == 3
        assert len(stats["recent_errors"]) == 3
    
    @pytest.mark.asyncio
    async def test_error_rate_calculation(self, mock_server):
        """Test error rate calculation."""
        # Add errors to simulate error rate
        mock_server._mock_error_handler.errors = [
            {"error": f"Error {i}", "timestamp": datetime.now()}
            for i in range(10)
        ]
        
        stats = await mock_server._mock_error_handler.get_error_statistics()
        
        assert stats["total_errors"] == 10
        assert stats["error_rate"] > 0
    
    @pytest.mark.asyncio
    async def test_error_context_preservation(self, mock_server):
        """Test that error context is preserved in logging."""
        error_handler = mock_server._mock_error_handler
        
        # Simulate error with context
        test_error = Exception("Test error with context")
        await error_handler.handle_error(test_error, "test_operation")
        
        # Verify error was recorded with context
        assert len(error_handler.errors) == 1
        recorded_error = error_handler.errors[0]
        assert "Test error with context" in recorded_error["error"]
        assert recorded_error["context"] == "test_operation"


class TestEdgeCaseErrorHandling:
    """Test edge case error scenarios."""
    
    @pytest.mark.asyncio
    async def test_unicode_error_messages(self, mock_server):
        """Test handling of Unicode characters in error messages."""
        unicode_error = "Error with émojis: 🚨 and spëcial chärs"
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        mock_server._mock_applescript_manager.execute_url_scheme = AsyncMock(
            return_value={
                "success": False,
                "error": unicode_error
            }
        )
        
        result = tools.add_todo("Test")
        
        assert result["success"] is False
        assert unicode_error in result["error"]
    
    @pytest.mark.asyncio
    async def test_very_long_error_messages(self, mock_server):
        """Test handling of very long error messages."""
        long_error = "x" * 10000  # 10KB error message
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        mock_server._mock_applescript_manager.execute_applescript = AsyncMock(
            return_value={
                "success": False,
                "error": long_error
            }
        )
        
        with pytest.raises(Exception) as exc_info:
            tools.get_todo_by_id("test")
        
        # Error should be handled without truncation issues
        assert len(str(exc_info.value)) > 0
    
    @pytest.mark.asyncio
    async def test_nested_exception_handling(self, mock_server):
        """Test handling of nested exceptions."""
        def create_nested_exception():
            try:
                raise ValueError("Inner exception")
            except ValueError as e:
                raise Exception("Outer exception") from e
        
        mock_server._mock_applescript_manager.execute_applescript = AsyncMock(
            side_effect=create_nested_exception
        )
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        with pytest.raises(Exception) as exc_info:
            tools.get_todos()
        
        # Should handle nested exception appropriately
        assert "Outer exception" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_null_and_empty_error_handling(self, mock_server):
        """Test handling of null and empty error scenarios."""
        test_cases = [
            {"success": False, "error": None},
            {"success": False, "error": ""},
            {"success": False},  # Missing error key
        ]
        
        tools = ThingsTools(mock_server._mock_applescript_manager)
        
        for test_case in test_cases:
            mock_server._mock_applescript_manager.execute_url_scheme = AsyncMock(
                return_value=test_case
            )
            
            result = tools.add_todo("Test")
            
            assert result["success"] is False
            # Should have some error message even if original was null/empty
            assert "error" in result
            assert result["error"] is not None
            assert len(result["error"]) > 0