#!/usr/bin/env python3
"""Test AppleScript process-level locking implementation."""

import asyncio
import time
import logging
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.things_mcp.services.applescript_manager import AppleScriptManager

# Set up logging to see lock timing
logging.basicConfig(level=logging.DEBUG)

class TestAppleScriptLocking:
    """Test AppleScript execution locking to prevent race conditions."""
    
    @pytest.fixture
    def manager(self):
        """Create an AppleScriptManager instance for testing."""
        return AppleScriptManager(timeout=10, retry_count=1)
    
    @pytest.mark.asyncio
    async def test_sequential_execution_with_lock(self, manager):
        """Test that AppleScript commands execute sequentially due to locking."""
        execution_order = []
        
        async def mock_create_subprocess_exec(*args, **kwargs):
            """Mock subprocess that records execution order and simulates work."""
            # Record when this execution starts
            script_content = args[2]  # The script content is the third argument
            execution_order.append(f"start_{script_content}")
            
            # Simulate some execution time
            await asyncio.sleep(0.1)
            
            # Create a mock process
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"success", b""))
            
            execution_order.append(f"end_{script_content}")
            return mock_process
        
        # Test concurrent executions
        with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess_exec):
            # Start multiple AppleScript executions concurrently
            tasks = [
                manager.execute_applescript(f'script_{i}')
                for i in range(3)
            ]
            
            results = await asyncio.gather(*tasks)
        
        # Verify all executions succeeded
        for result in results:
            assert result['success'] is True
        
        # Verify execution order - starts and ends should be properly serialized
        print("Execution order:", execution_order)
        
        # Due to locking, we should see complete execution of each script before the next starts
        # Format: start_script_0, end_script_0, start_script_1, end_script_1, start_script_2, end_script_2
        assert len(execution_order) == 6
        
        # Check that each script completes before the next one starts
        for i in range(3):
            start_idx = execution_order.index(f"start_script_{i}")
            end_idx = execution_order.index(f"end_script_{i}")
            
            # End should come immediately after start (no interleaving)
            assert end_idx == start_idx + 1, f"Script {i} execution was interleaved"
    
    @pytest.mark.asyncio
    async def test_lock_wait_time_logging(self, manager, caplog):
        """Test that significant lock wait times are logged."""
        
        async def slow_mock_create_subprocess_exec(*args, **kwargs):
            """Mock subprocess that takes time to simulate lock contention."""
            await asyncio.sleep(0.2)  # Simulate slow execution
            
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"success", b""))
            return mock_process
        
        with patch('asyncio.create_subprocess_exec', side_effect=slow_mock_create_subprocess_exec):
            with caplog.at_level(logging.DEBUG):
                # Start two concurrent executions
                tasks = [
                    manager.execute_applescript('script_1'),
                    manager.execute_applescript('script_2')
                ]
                
                await asyncio.gather(*tasks)
        
        # Check that lock wait time was logged for the second script
        lock_wait_logs = [record for record in caplog.records if "AppleScript lock waited" in record.message]
        assert len(lock_wait_logs) >= 1, "Expected lock wait time to be logged"
    
    @pytest.mark.asyncio
    async def test_multiple_manager_instances_share_lock(self):
        """Test that multiple AppleScriptManager instances share the same lock."""
        manager1 = AppleScriptManager(timeout=10, retry_count=1)
        manager2 = AppleScriptManager(timeout=10, retry_count=1)
        
        # Verify they share the same lock object
        assert manager1._applescript_lock is manager2._applescript_lock
        
        execution_order = []
        
        async def mock_create_subprocess_exec(*args, **kwargs):
            """Mock subprocess that records execution order."""
            script_content = args[2]
            execution_order.append(f"start_{script_content}")
            await asyncio.sleep(0.05)
            
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"success", b""))
            
            execution_order.append(f"end_{script_content}")
            return mock_process
        
        with patch('asyncio.create_subprocess_exec', side_effect=mock_create_subprocess_exec):
            # Execute scripts from different manager instances concurrently
            tasks = [
                manager1.execute_applescript('manager1_script'),
                manager2.execute_applescript('manager2_script')
            ]
            
            results = await asyncio.gather(*tasks)
        
        # Both should succeed
        for result in results:
            assert result['success'] is True
        
        # Execution should be serialized across managers
        assert len(execution_order) == 4
        # One script should complete fully before the other starts
        assert execution_order == [
            'start_manager1_script', 'end_manager1_script',
            'start_manager2_script', 'end_manager2_script'
        ] or execution_order == [
            'start_manager2_script', 'end_manager2_script',
            'start_manager1_script', 'end_manager1_script'
        ]
    
    @pytest.mark.asyncio
    async def test_lock_timeout_handling(self, manager):
        """Test that lock doesn't interfere with normal timeout handling."""
        
        async def timeout_mock_create_subprocess_exec(*args, **kwargs):
            """Mock subprocess that simulates timeout."""
            mock_process = AsyncMock()
            # Simulate a process that takes forever
            mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
            mock_process.kill = MagicMock()
            mock_process.wait = AsyncMock(return_value=None)
            return mock_process
        
        with patch('asyncio.create_subprocess_exec', side_effect=timeout_mock_create_subprocess_exec):
            result = await manager.execute_applescript('timeout_script')
        
        assert result['success'] is False
        assert "timed out" in result['error']
    
    @pytest.mark.asyncio
    async def test_error_handling_with_lock(self, manager):
        """Test that errors are properly handled when using the lock."""
        
        async def error_mock_create_subprocess_exec(*args, **kwargs):
            """Mock subprocess that raises an exception."""
            raise Exception("Simulated subprocess error")
        
        with patch('asyncio.create_subprocess_exec', side_effect=error_mock_create_subprocess_exec):
            result = await manager.execute_applescript('error_script')
        
        assert result['success'] is False
        assert "Execution error" in result['error']
        assert "Simulated subprocess error" in result['error']
    
    @pytest.mark.asyncio
    async def test_execution_time_tracking(self, manager):
        """Test that execution time is properly tracked with locking."""
        
        async def timed_mock_create_subprocess_exec(*args, **kwargs):
            """Mock subprocess that takes a known amount of time."""
            await asyncio.sleep(0.05)  # 50ms execution
            
            mock_process = AsyncMock()
            mock_process.returncode = 0
            mock_process.communicate = AsyncMock(return_value=(b"success", b""))
            return mock_process
        
        with patch('asyncio.create_subprocess_exec', side_effect=timed_mock_create_subprocess_exec):
            result = await manager.execute_applescript('timed_script')
        
        assert result['success'] is True
        assert 'execution_time' in result
        # Should be approximately 50ms, allow some variance
        assert 0.04 < result['execution_time'] < 0.1


if __name__ == "__main__":
    """Run the locking tests directly."""
    async def run_tests():
        """Run all tests manually."""
        print("Testing AppleScript locking implementation...")
        
        # Test basic sequential execution
        print("\n1. Testing sequential execution...")
        manager = AppleScriptManager(timeout=10, retry_count=1)
        test_instance = TestAppleScriptLocking()
        
        try:
            await test_instance.test_sequential_execution_with_lock(manager)
            print("✓ Sequential execution test passed")
        except Exception as e:
            print(f"✗ Sequential execution test failed: {e}")
        
        # Test lock sharing between instances
        print("\n2. Testing lock sharing...")
        try:
            await test_instance.test_multiple_manager_instances_share_lock()
            print("✓ Lock sharing test passed")
        except Exception as e:
            print(f"✗ Lock sharing test failed: {e}")
        
        print("\nAppleScript locking tests completed!")
    
    # Run the tests
    asyncio.run(run_tests())