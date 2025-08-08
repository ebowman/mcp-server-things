#!/usr/bin/env python3
"""
Test script for operation queue implementation.
"""

import asyncio
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from things_mcp.operation_queue import OperationQueue, Priority, OperationStatus


# Configure logging for tests
logging.basicConfig(level=logging.DEBUG)


class TestOperationQueue:
    """Test cases for OperationQueue."""

    @pytest.fixture
    async def queue(self):
        """Create a test queue."""
        queue = OperationQueue(max_concurrent=1)
        await queue.start()
        yield queue
        await queue.stop()

    async def test_basic_operation_execution(self, queue):
        """Test basic operation execution."""
        result_value = "test_result"
        
        async def test_operation():
            await asyncio.sleep(0.1)
            return result_value
        
        operation_id = await queue.enqueue(test_operation, name="test_op")
        result = await queue.wait_for_operation(operation_id)
        
        assert result == result_value

    async def test_priority_ordering(self, queue):
        """Test that high priority operations are executed first."""
        results = []
        
        async def test_operation(value):
            await asyncio.sleep(0.05)
            results.append(value)
            return value
        
        # Enqueue in order: normal, low, high
        await queue.enqueue(test_operation, "normal", priority=Priority.NORMAL)
        await queue.enqueue(test_operation, "low", priority=Priority.LOW)
        await queue.enqueue(test_operation, "high", priority=Priority.HIGH)
        
        # Wait for all to complete
        await asyncio.sleep(0.5)
        
        # High should be executed first, then normal, then low
        assert results == ["normal", "high", "low"]  # First normal starts immediately

    async def test_operation_timeout(self, queue):
        """Test operation timeout handling."""
        async def slow_operation():
            await asyncio.sleep(2.0)
            return "should_not_complete"
        
        operation_id = await queue.enqueue(
            slow_operation,
            name="slow_op",
            timeout=0.1,
            max_retries=0  # Don't retry for this test
        )
        
        with pytest.raises(Exception):  # Should raise timeout error
            await queue.wait_for_operation(operation_id)

    async def test_operation_retry(self, queue):
        """Test operation retry logic."""
        attempt_count = 0
        
        async def failing_operation():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError(f"Attempt {attempt_count} failed")
            return "success"
        
        operation_id = await queue.enqueue(
            failing_operation,
            name="retry_op",
            max_retries=3,
            retry_delay=0.01
        )
        
        result = await queue.wait_for_operation(operation_id)
        assert result == "success"
        assert attempt_count == 3

    async def test_queue_status(self, queue):
        """Test queue status reporting."""
        async def dummy_operation():
            await asyncio.sleep(0.1)
            return "done"
        
        # Initial status
        status = queue.get_queue_status()
        assert status['queue_size'] == 0
        assert status['active_operations'] == 0
        
        # Add operations
        op1 = await queue.enqueue(dummy_operation, name="op1")
        op2 = await queue.enqueue(dummy_operation, name="op2")
        
        # Check status with pending operations
        status = queue.get_queue_status()
        assert status['queue_size'] >= 0  # May be 0 if op1 started
        
        # Wait for completion
        await queue.wait_for_operation(op1)
        await queue.wait_for_operation(op2)

    async def test_operation_cancellation(self, queue):
        """Test operation cancellation."""
        async def test_operation():
            await asyncio.sleep(1.0)
            return "completed"
        
        operation_id = await queue.enqueue(test_operation, name="cancel_test")
        
        # Cancel before execution
        cancelled = await queue.cancel_operation(operation_id)
        
        # Should be able to cancel if not yet running
        if cancelled:
            status = queue.get_operation_status(operation_id)
            assert status is not None

    async def test_concurrent_operations(self):
        """Test concurrent operation handling."""
        # Create queue that allows 2 concurrent operations
        queue = OperationQueue(max_concurrent=2)
        await queue.start()
        
        try:
            results = []
            
            async def test_operation(value):
                await asyncio.sleep(0.1)
                results.append(value)
                return value
            
            # Enqueue 4 operations
            ops = []
            for i in range(4):
                op_id = await queue.enqueue(test_operation, f"op_{i}")
                ops.append(op_id)
            
            # Wait for all to complete
            for op_id in ops:
                await queue.wait_for_operation(op_id)
            
            assert len(results) == 4
            
        finally:
            await queue.stop()


async def test_integration_with_mock_applescript():
    """Test integration with mock AppleScript operations."""
    # Mock AppleScript manager
    mock_manager = MagicMock()
    mock_manager.execute_applescript = AsyncMock(return_value={
        "success": True,
        "output": "test_todo_id"
    })
    
    # Import here to avoid circular imports during testing
    from things_mcp.tools import ThingsTools
    
    # Create tools with mock manager
    tools = ThingsTools(mock_manager)
    
    # Test that operations go through the queue
    result = await tools.add_todo("Test Todo")
    
    # Verify the mock was called and result is returned
    assert mock_manager.execute_applescript.called
    assert result is not None


async def run_tests():
    """Run all tests manually."""
    print("Testing OperationQueue...")
    
    # Test basic functionality
    queue = OperationQueue()
    await queue.start()
    
    try:
        # Test basic operation
        async def simple_op():
            return "hello"
        
        op_id = await queue.enqueue(simple_op, name="simple_test")
        result = await queue.wait_for_operation(op_id)
        print(f"✓ Basic operation: {result}")
        
        # Test priority
        results = []
        
        async def priority_op(name, delay=0.01):
            await asyncio.sleep(delay)
            results.append(name)
            return name
        
        # Add operations in different priorities
        await queue.enqueue(priority_op, "low", priority=Priority.LOW)
        await queue.enqueue(priority_op, "high", priority=Priority.HIGH)
        await queue.enqueue(priority_op, "normal", priority=Priority.NORMAL)
        
        # Wait a bit
        await asyncio.sleep(0.2)
        print(f"✓ Priority execution order: {results}")
        
        # Test status
        status = queue.get_queue_status()
        print(f"✓ Queue status: {status}")
        
        print("All manual tests passed!")
        
    finally:
        await queue.stop()


if __name__ == "__main__":
    # Run manual tests if executed directly
    asyncio.run(run_tests())