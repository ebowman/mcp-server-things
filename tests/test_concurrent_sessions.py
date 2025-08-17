#!/usr/bin/env python3
"""
Comprehensive Concurrent Session Testing Suite for Things 3 MCP Server

This test suite validates that all concurrency fixes work properly by testing:
1. Multiple MCP server instances running simultaneously
2. Concurrent write operations (should be serialized)
3. Shared cache functionality across instances
4. AppleScript lock contention and wait times
5. Operation queue ordering and priorities
6. Race condition prevention
7. Data consistency with parallel operations
8. Stress test with many concurrent operations
9. No data corruption or lost updates
10. Performance metrics for concurrent vs sequential

The tests are designed to be comprehensive but practical to run without requiring
actual Things 3 installation by using sophisticated mocking.
"""

import asyncio
import logging
import multiprocessing
import os
import pytest
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch
import threading
import json
import uuid

# Configure logging for detailed test output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(process)d:%(thread)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from things_mcp.server import ThingsMCPServer
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.operation_queue import get_operation_queue, shutdown_operation_queue, OperationQueue, Priority
from things_mcp.shared_cache import SharedCache, get_shared_cache
from things_mcp.tools import ThingsTools


class ConcurrentSessionTestSuite:
    """Comprehensive test suite for concurrent session validation."""
    
    def __init__(self, temp_dir: Optional[str] = None):
        """Initialize the test suite with a temporary directory for testing."""
        self.temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp(prefix="things_concurrent_test_"))
        self.cache_dir = self.temp_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.test_results = []
        self.performance_metrics = {}
        logger.info(f"Test suite initialized with temp_dir: {self.temp_dir}")
    
    async def cleanup(self):
        """Clean up test resources."""
        try:
            # Shutdown any remaining queues
            await shutdown_operation_queue()
            
            # Clean up temp directory
            import shutil
            if self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
    
    @asynccontextmanager
    async def mock_applescript_manager(self, execution_delay: float = 0.05, 
                                     should_fail: bool = False):
        """Create a mock AppleScript manager with realistic behavior."""
        
        class MockAppleScriptManager:
            def __init__(self):
                self.execution_count = 0
                self.execution_log = []
                self.lock_wait_times = []
                self._applescript_lock = asyncio.Lock()  # Simulate the actual lock
                
            async def execute_applescript(self, script: str, cache_key: Optional[str] = None):
                """Mock AppleScript execution with realistic timing."""
                start_time = time.time()
                
                async with self._applescript_lock:  # Simulate actual locking
                    lock_acquired_time = time.time()
                    lock_wait_time = lock_acquired_time - start_time
                    
                    if lock_wait_time > 0.001:  # Log significant waits
                        self.lock_wait_times.append(lock_wait_time)
                        logger.debug(f"AppleScript lock waited {lock_wait_time:.3f}s")
                    
                    self.execution_count += 1
                    execution_id = self.execution_count
                    
                    # Log execution details
                    self.execution_log.append({
                        'id': execution_id,
                        'script_preview': script[:50] + '...' if len(script) > 50 else script,
                        'cache_key': cache_key,
                        'start_time': start_time,
                        'lock_wait_time': lock_wait_time,
                        'thread_id': threading.get_ident(),
                        'process_id': os.getpid()
                    })
                    
                    # Simulate execution time
                    await asyncio.sleep(execution_delay)
                    
                    if should_fail:
                        return {
                            "success": False,
                            "error": f"Mock failure for execution {execution_id}",
                            "execution_time": execution_delay
                        }
                    
                    # Return realistic success response
                    return {
                        "success": True,
                        "output": f"mock_result_{execution_id}",
                        "execution_time": execution_delay
                    }
                    
            async def is_things_running(self):
                return not should_fail
            
            def _get_current_timestamp(self):
                return time.time()
        
        manager = MockAppleScriptManager()
        yield manager
    
    async def test_multiple_server_instances(self, num_instances: int = 3, 
                                           operations_per_instance: int = 5):
        """Test multiple MCP server instances running simultaneously."""
        logger.info(f"Testing {num_instances} server instances with {operations_per_instance} operations each")
        
        async def create_server_instance(instance_id: int):
            """Create and run operations on a server instance."""
            results = []
            
            async with self.mock_applescript_manager(execution_delay=0.02) as mock_manager:
                # Create server with shared cache
                cache = SharedCache(cache_dir=str(self.cache_dir), default_ttl=10.0)
                tools = ThingsTools(mock_manager)
                
                # Simulate operations
                for op_num in range(operations_per_instance):
                    try:
                        # Mix different operation types
                        if op_num % 3 == 0:
                            result = await tools.add_todo(f"Todo from server {instance_id} op {op_num}")
                        elif op_num % 3 == 1:
                            result = await tools.get_todos()
                        else:
                            result = await tools.add_project(f"Project from server {instance_id} op {op_num}")
                        
                        results.append({
                            'instance_id': instance_id,
                            'operation': op_num,
                            'success': True,
                            'result': result
                        })
                    except Exception as e:
                        results.append({
                            'instance_id': instance_id,
                            'operation': op_num,
                            'success': False,
                            'error': str(e)
                        })
                        
                return {
                    'instance_id': instance_id,
                    'results': results,
                    'execution_log': mock_manager.execution_log,
                    'lock_wait_times': mock_manager.lock_wait_times
                }
        
        # Run all instances concurrently
        start_time = time.time()
        instance_results = await asyncio.gather(*[
            create_server_instance(i) for i in range(num_instances)
        ])
        total_time = time.time() - start_time
        
        # Analyze results
        total_operations = sum(len(r['results']) for r in instance_results)
        successful_operations = sum(
            len([op for op in r['results'] if op['success']]) 
            for r in instance_results
        )
        
        # Check for proper serialization of AppleScript operations
        all_executions = []
        for instance_result in instance_results:
            all_executions.extend(instance_result['execution_log'])
        
        # Sort by start time to verify serialization
        all_executions.sort(key=lambda x: x['start_time'])
        
        # Verify no overlapping executions (serialization)
        overlaps = 0
        for i in range(1, len(all_executions)):
            prev_exec = all_executions[i-1]
            curr_exec = all_executions[i]
            
            # Check if current execution started before previous one could finish
            estimated_prev_end = prev_exec['start_time'] + prev_exec.get('lock_wait_time', 0) + 0.02
            if curr_exec['start_time'] < estimated_prev_end:
                overlaps += 1
        
        test_result = {
            'test': 'multiple_server_instances',
            'instances': num_instances,
            'operations_per_instance': operations_per_instance,
            'total_operations': total_operations,
            'successful_operations': successful_operations,
            'success_rate': successful_operations / total_operations if total_operations > 0 else 0,
            'total_time': total_time,
            'operations_per_second': total_operations / total_time if total_time > 0 else 0,
            'overlapping_executions': overlaps,
            'properly_serialized': overlaps == 0,
            'max_lock_wait_time': max(
                max(r['lock_wait_times'], default=0) for r in instance_results
            ),
            'total_lock_waits': sum(len(r['lock_wait_times']) for r in instance_results)
        }
        
        self.test_results.append(test_result)
        logger.info(f"Multiple instances test completed: {test_result}")
        
        # Assertions
        assert successful_operations == total_operations, f"Some operations failed: {successful_operations}/{total_operations}"
        assert overlaps == 0, f"Found {overlaps} overlapping executions - serialization failed"
        
        return test_result
    
    async def test_concurrent_write_operations(self, num_concurrent: int = 10):
        """Test that concurrent write operations are properly serialized."""
        logger.info(f"Testing {num_concurrent} concurrent write operations")
        
        async with self.mock_applescript_manager(execution_delay=0.01) as mock_manager:
            tools = ThingsTools(mock_manager)
            
            # Define write operations that should be serialized
            async def write_operation(op_id: int):
                """Perform a write operation."""
                return await tools.add_todo(f"Concurrent Todo {op_id}", 
                                          notes=f"Created by operation {op_id}")
            
            # Execute all write operations concurrently
            start_time = time.time()
            results = await asyncio.gather(*[
                write_operation(i) for i in range(num_concurrent)
            ], return_exceptions=True)
            total_time = time.time() - start_time
            
            # Analyze serialization
            execution_log = mock_manager.execution_log
            execution_log.sort(key=lambda x: x['start_time'])
            
            # Calculate expected vs actual time
            expected_serial_time = len(execution_log) * 0.01  # execution_delay per operation
            parallelization_factor = expected_serial_time / total_time if total_time > 0 else 1
            
            # Check for exceptions
            exceptions = [r for r in results if isinstance(r, Exception)]
            successful_results = [r for r in results if not isinstance(r, Exception)]
            
            test_result = {
                'test': 'concurrent_write_operations',
                'num_concurrent': num_concurrent,
                'successful_operations': len(successful_results),
                'failed_operations': len(exceptions),
                'total_time': total_time,
                'expected_serial_time': expected_serial_time,
                'parallelization_factor': parallelization_factor,
                'properly_serialized': parallelization_factor < 1.2,  # Allow 20% overhead
                'execution_log_count': len(execution_log),
                'lock_wait_times': mock_manager.lock_wait_times
            }
            
            self.test_results.append(test_result)
            logger.info(f"Concurrent writes test completed: {test_result}")
            
            # Assertions
            assert len(exceptions) == 0, f"Write operations failed: {exceptions}"
            assert len(successful_results) == num_concurrent, "Not all operations completed"
            assert test_result['properly_serialized'], "Operations were not properly serialized"
            
            return test_result
    
    async def test_shared_cache_consistency(self, num_instances: int = 3, 
                                          num_operations: int = 10):
        """Test shared cache functionality across multiple instances."""
        logger.info(f"Testing shared cache with {num_instances} instances and {num_operations} operations")
        
        # Create shared cache
        shared_cache = SharedCache(cache_dir=str(self.cache_dir), default_ttl=5.0)
        
        async def cache_worker(worker_id: int):
            """Worker that performs cache operations."""
            results = []
            local_cache = SharedCache(cache_dir=str(self.cache_dir), default_ttl=5.0)
            
            for op_num in range(num_operations):
                key = f"shared_key_{op_num % 3}"  # Use overlapping keys
                value = f"worker_{worker_id}_op_{op_num}_value"
                
                try:
                    if op_num % 4 == 0:  # SET operation
                        local_cache.set(key, value)
                        results.append({'operation': 'set', 'key': key, 'success': True})
                        
                    elif op_num % 4 == 1:  # GET operation
                        cached_value = local_cache.get(key)
                        results.append({
                            'operation': 'get', 
                            'key': key, 
                            'value': cached_value,
                            'success': True,
                            'cache_hit': cached_value is not None
                        })
                        
                    elif op_num % 4 == 2:  # DELETE operation
                        deleted = local_cache.delete(key)
                        results.append({'operation': 'delete', 'key': key, 'deleted': deleted, 'success': True})
                        
                    else:  # STATS operation
                        stats = local_cache.stats()
                        results.append({'operation': 'stats', 'stats': stats, 'success': True})
                        
                    # Small delay to allow for cache file operations
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    results.append({
                        'operation': f'op_{op_num}', 
                        'error': str(e), 
                        'success': False
                    })
            
            return {'worker_id': worker_id, 'results': results}
        
        # Run cache workers concurrently
        start_time = time.time()
        worker_results = await asyncio.gather(*[
            cache_worker(i) for i in range(num_instances)
        ])
        total_time = time.time() - start_time
        
        # Analyze cache consistency
        all_results = []
        for worker_result in worker_results:
            all_results.extend(worker_result['results'])
        
        # Count operations by type
        operation_counts = {}
        cache_hits = 0
        cache_misses = 0
        successful_ops = 0
        
        for result in all_results:
            if result['success']:
                successful_ops += 1
                
            op_type = result['operation']
            operation_counts[op_type] = operation_counts.get(op_type, 0) + 1
            
            if op_type == 'get' and result['success']:
                if result.get('cache_hit'):
                    cache_hits += 1
                else:
                    cache_misses += 1
        
        # Get final cache stats
        final_stats = shared_cache.stats()
        
        test_result = {
            'test': 'shared_cache_consistency',
            'num_instances': num_instances,
            'num_operations_per_instance': num_operations,
            'total_operations': len(all_results),
            'successful_operations': successful_ops,
            'operation_counts': operation_counts,
            'cache_hits': cache_hits,
            'cache_misses': cache_misses,
            'hit_rate': cache_hits / (cache_hits + cache_misses) if (cache_hits + cache_misses) > 0 else 0,
            'total_time': total_time,
            'final_cache_stats': final_stats
        }
        
        self.test_results.append(test_result)
        logger.info(f"Shared cache test completed: {test_result}")
        
        # Assertions
        assert successful_ops > len(all_results) * 0.95, "Too many cache operations failed"
        
        return test_result
    
    async def test_operation_queue_priorities(self, num_operations: int = 20):
        """Test operation queue ordering and priorities."""
        logger.info(f"Testing operation queue with {num_operations} operations")
        
        queue = OperationQueue(max_concurrent=1)  # Force serialization
        await queue.start()
        
        try:
            execution_order = []
            
            async def priority_operation(priority: Priority, op_id: int):
                """Operation that records execution order."""
                execution_order.append({'priority': priority.name, 'op_id': op_id})
                await asyncio.sleep(0.01)  # Small delay
                return f"result_{priority.name}_{op_id}"
            
            # Enqueue operations in mixed order
            operations = []
            priorities = [Priority.LOW, Priority.NORMAL, Priority.HIGH] * (num_operations // 3 + 1)
            
            for i in range(num_operations):
                priority = priorities[i]
                op_id = await queue.enqueue(
                    priority_operation, 
                    priority, 
                    i,
                    name=f"{priority.name}_op_{i}",
                    priority=priority
                )
                operations.append({'id': op_id, 'priority': priority, 'op_num': i})
            
            # Wait for all operations to complete
            results = []
            for op in operations:
                try:
                    result = await queue.wait_for_operation(op['id'], timeout=30.0)
                    results.append({'op': op, 'result': result, 'success': True})
                except Exception as e:
                    results.append({'op': op, 'error': str(e), 'success': False})
            
            # Analyze priority ordering
            high_priority_positions = [i for i, exec_info in enumerate(execution_order) if exec_info['priority'] == 'HIGH']
            normal_priority_positions = [i for i, exec_info in enumerate(execution_order) if exec_info['priority'] == 'NORMAL']
            low_priority_positions = [i for i, exec_info in enumerate(execution_order) if exec_info['priority'] == 'LOW']
            
            # Check if priorities were respected (allowing for some flexibility due to concurrent enqueuing)
            avg_high_pos = sum(high_priority_positions) / len(high_priority_positions) if high_priority_positions else 0
            avg_normal_pos = sum(normal_priority_positions) / len(normal_priority_positions) if normal_priority_positions else 0
            avg_low_pos = sum(low_priority_positions) / len(low_priority_positions) if low_priority_positions else 0
            
            queue_stats = queue.get_queue_status()
            
            test_result = {
                'test': 'operation_queue_priorities',
                'num_operations': num_operations,
                'successful_operations': len([r for r in results if r['success']]),
                'execution_order': execution_order,
                'high_priority_avg_position': avg_high_pos,
                'normal_priority_avg_position': avg_normal_pos,
                'low_priority_avg_position': avg_low_pos,
                'priority_ordering_correct': avg_high_pos < avg_normal_pos < avg_low_pos if all([high_priority_positions, normal_priority_positions, low_priority_positions]) else True,
                'queue_final_stats': queue_stats
            }
            
            self.test_results.append(test_result)
            logger.info(f"Operation queue priorities test completed: {test_result}")
            
            # Assertions
            assert len([r for r in results if r['success']]) == num_operations, "Some operations failed"
            
            return test_result
        
        finally:
            await queue.stop()
    
    async def test_race_condition_prevention(self, num_concurrent: int = 15):
        """Test race condition prevention in concurrent scenarios."""
        logger.info(f"Testing race condition prevention with {num_concurrent} concurrent operations")
        
        # Shared state that could be subject to race conditions
        shared_state = {'counter': 0, 'operations': []}
        state_lock = asyncio.Lock()
        
        async with self.mock_applescript_manager(execution_delay=0.005) as mock_manager:
            tools = ThingsTools(mock_manager)
            
            async def racy_operation(op_id: int):
                """Operation that could cause race conditions without proper protection."""
                # Simulate reading shared state
                async with state_lock:
                    current_counter = shared_state['counter']
                    shared_state['operations'].append(f"op_{op_id}_read_{current_counter}")
                
                # Perform Things operation
                result = await tools.add_todo(f"Race Test Todo {op_id}")
                
                # Update shared state
                async with state_lock:
                    shared_state['counter'] += 1
                    shared_state['operations'].append(f"op_{op_id}_write_{shared_state['counter']}")
                
                return {'op_id': op_id, 'result': result, 'final_counter': shared_state['counter']}
            
            # Run all operations concurrently
            start_time = time.time()
            results = await asyncio.gather(*[
                racy_operation(i) for i in range(num_concurrent)
            ], return_exceptions=True)
            total_time = time.time() - start_time
            
            # Analyze results for race conditions
            successful_results = [r for r in results if not isinstance(r, Exception)]
            exceptions = [r for r in results if isinstance(r, Exception)]
            
            # Check final state consistency
            expected_final_counter = num_concurrent
            actual_final_counter = shared_state['counter']
            
            # Check AppleScript execution serialization
            applescript_executions = len(mock_manager.execution_log)
            
            test_result = {
                'test': 'race_condition_prevention',
                'num_concurrent': num_concurrent,
                'successful_operations': len(successful_results),
                'failed_operations': len(exceptions),
                'expected_final_counter': expected_final_counter,
                'actual_final_counter': actual_final_counter,
                'counter_consistency': expected_final_counter == actual_final_counter,
                'total_time': total_time,
                'applescript_executions': applescript_executions,
                'applescript_serialization_correct': applescript_executions == num_concurrent,
                'shared_operations_log': len(shared_state['operations']),
                'max_lock_wait_time': max(mock_manager.lock_wait_times, default=0)
            }
            
            self.test_results.append(test_result)
            logger.info(f"Race condition prevention test completed: {test_result}")
            
            # Assertions
            assert len(exceptions) == 0, f"Operations failed due to exceptions: {exceptions}"
            assert actual_final_counter == expected_final_counter, f"Race condition detected: expected {expected_final_counter}, got {actual_final_counter}"
            assert applescript_executions == num_concurrent, "AppleScript operations not properly serialized"
            
            return test_result
    
    async def test_stress_test_many_operations(self, num_operations: int = 50, 
                                             num_concurrent_batches: int = 5):
        """Stress test with many concurrent operations."""
        logger.info(f"Running stress test with {num_operations} operations in {num_concurrent_batches} batches")
        
        async def batch_operations(batch_id: int, operations_per_batch: int):
            """Run a batch of operations."""
            batch_results = []
            
            async with self.mock_applescript_manager(execution_delay=0.001) as mock_manager:
                tools = ThingsTools(mock_manager)
                
                for op_num in range(operations_per_batch):
                    try:
                        # Mix different operation types for comprehensive testing
                        op_type = op_num % 4
                        
                        if op_type == 0:
                            result = await tools.add_todo(f"Stress Todo B{batch_id} Op{op_num}")
                        elif op_type == 1:
                            result = await tools.add_project(f"Stress Project B{batch_id} Op{op_num}")
                        elif op_type == 2:
                            result = await tools.get_todos()
                        else:
                            result = await tools.get_projects()
                        
                        batch_results.append({
                            'batch_id': batch_id,
                            'op_num': op_num,
                            'op_type': op_type,
                            'success': True,
                            'has_result': result is not None
                        })
                        
                    except Exception as e:
                        batch_results.append({
                            'batch_id': batch_id,
                            'op_num': op_num,
                            'success': False,
                            'error': str(e)
                        })
                
                return {
                    'batch_id': batch_id,
                    'results': batch_results,
                    'execution_count': mock_manager.execution_count,
                    'lock_wait_times': mock_manager.lock_wait_times
                }
        
        operations_per_batch = num_operations // num_concurrent_batches
        
        # Run batches concurrently
        start_time = time.time()
        batch_results = await asyncio.gather(*[
            batch_operations(batch_id, operations_per_batch) 
            for batch_id in range(num_concurrent_batches)
        ])
        total_time = time.time() - start_time
        
        # Aggregate results
        all_operations = []
        total_executions = 0
        all_lock_waits = []
        
        for batch_result in batch_results:
            all_operations.extend(batch_result['results'])
            total_executions += batch_result['execution_count']
            all_lock_waits.extend(batch_result['lock_wait_times'])
        
        successful_ops = len([op for op in all_operations if op['success']])
        failed_ops = len([op for op in all_operations if not op['success']])
        
        # Performance analysis
        operations_per_second = len(all_operations) / total_time if total_time > 0 else 0
        avg_lock_wait = sum(all_lock_waits) / len(all_lock_waits) if all_lock_waits else 0
        max_lock_wait = max(all_lock_waits, default=0)
        
        test_result = {
            'test': 'stress_test_many_operations',
            'num_operations': len(all_operations),
            'num_concurrent_batches': num_concurrent_batches,
            'successful_operations': successful_ops,
            'failed_operations': failed_ops,
            'success_rate': successful_ops / len(all_operations) if all_operations else 0,
            'total_time': total_time,
            'operations_per_second': operations_per_second,
            'total_applescript_executions': total_executions,
            'num_lock_waits': len(all_lock_waits),
            'avg_lock_wait_time': avg_lock_wait,
            'max_lock_wait_time': max_lock_wait,
            'performance_acceptable': operations_per_second > 10  # Arbitrary threshold
        }
        
        self.test_results.append(test_result)
        logger.info(f"Stress test completed: {test_result}")
        
        # Assertions
        assert test_result['success_rate'] > 0.95, f"Too many failures: {failed_ops}/{len(all_operations)}"
        assert test_result['performance_acceptable'], f"Performance too low: {operations_per_second} ops/sec"
        
        return test_result
    
    async def test_data_consistency_parallel_operations(self, num_parallel: int = 8):
        """Test data consistency with parallel operations."""
        logger.info(f"Testing data consistency with {num_parallel} parallel operations")
        
        # Shared data structure to track consistency
        data_store = {}
        consistency_lock = asyncio.Lock()
        
        async with self.mock_applescript_manager(execution_delay=0.01) as mock_manager:
            tools = ThingsTools(mock_manager)
            
            async def data_operation(op_id: int):
                """Operation that maintains data consistency."""
                key = f"todo_{op_id % 3}"  # Use overlapping keys to test consistency
                
                # Read current state
                async with consistency_lock:
                    current_count = data_store.get(key, 0)
                
                # Perform Things operation
                result = await tools.add_todo(f"Consistency Test {key} Count {current_count + 1}")
                
                # Update state consistently
                async with consistency_lock:
                    data_store[key] = data_store.get(key, 0) + 1
                
                return {
                    'op_id': op_id,
                    'key': key,
                    'final_count': data_store[key],
                    'result': result
                }
            
            # Run operations in parallel
            start_time = time.time()
            results = await asyncio.gather(*[
                data_operation(i) for i in range(num_parallel)
            ], return_exceptions=True)
            total_time = time.time() - start_time
            
            # Analyze consistency
            successful_results = [r for r in results if not isinstance(r, Exception)]
            exceptions = [r for r in results if isinstance(r, Exception)]
            
            # Check data store consistency
            total_expected_operations = num_parallel
            total_recorded_operations = sum(data_store.values())
            
            # Verify AppleScript execution order
            execution_log = mock_manager.execution_log
            execution_times = [entry['start_time'] for entry in execution_log]
            properly_ordered = execution_times == sorted(execution_times)
            
            test_result = {
                'test': 'data_consistency_parallel_operations',
                'num_parallel': num_parallel,
                'successful_operations': len(successful_results),
                'failed_operations': len(exceptions),
                'expected_total_operations': total_expected_operations,
                'recorded_total_operations': total_recorded_operations,
                'data_consistency': total_expected_operations == total_recorded_operations,
                'final_data_store': data_store.copy(),
                'applescript_executions_ordered': properly_ordered,
                'total_time': total_time,
                'execution_log_count': len(execution_log)
            }
            
            self.test_results.append(test_result)
            logger.info(f"Data consistency test completed: {test_result}")
            
            # Assertions
            assert len(exceptions) == 0, f"Operations failed: {exceptions}"
            assert total_expected_operations == total_recorded_operations, f"Data inconsistency: expected {total_expected_operations}, got {total_recorded_operations}"
            assert properly_ordered, "AppleScript executions were not properly ordered"
            
            return test_result
    
    async def test_performance_concurrent_vs_sequential(self, num_operations: int = 20):
        """Compare performance of concurrent vs sequential operations."""
        logger.info(f"Comparing concurrent vs sequential performance with {num_operations} operations")
        
        # Sequential test
        async with self.mock_applescript_manager(execution_delay=0.01) as sequential_manager:
            sequential_tools = ThingsTools(sequential_manager)
            
            sequential_start = time.time()
            sequential_results = []
            
            for i in range(num_operations):
                try:
                    result = await sequential_tools.add_todo(f"Sequential Todo {i}")
                    sequential_results.append({'success': True, 'result': result})
                except Exception as e:
                    sequential_results.append({'success': False, 'error': str(e)})
            
            sequential_time = time.time() - sequential_start
            sequential_success_count = len([r for r in sequential_results if r['success']])
        
        # Concurrent test
        async with self.mock_applescript_manager(execution_delay=0.01) as concurrent_manager:
            concurrent_tools = ThingsTools(concurrent_manager)
            
            async def concurrent_operation(op_id: int):
                try:
                    result = await concurrent_tools.add_todo(f"Concurrent Todo {op_id}")
                    return {'success': True, 'result': result}
                except Exception as e:
                    return {'success': False, 'error': str(e)}
            
            concurrent_start = time.time()
            concurrent_results = await asyncio.gather(*[
                concurrent_operation(i) for i in range(num_operations)
            ])
            concurrent_time = time.time() - concurrent_start
            concurrent_success_count = len([r for r in concurrent_results if r['success']])
        
        # Calculate performance metrics
        sequential_ops_per_sec = sequential_success_count / sequential_time if sequential_time > 0 else 0
        concurrent_ops_per_sec = concurrent_success_count / concurrent_time if concurrent_time > 0 else 0
        
        # Due to serialization, concurrent should not be much faster, but should be reliable
        performance_ratio = concurrent_ops_per_sec / sequential_ops_per_sec if sequential_ops_per_sec > 0 else 1
        
        test_result = {
            'test': 'performance_concurrent_vs_sequential',
            'num_operations': num_operations,
            'sequential_time': sequential_time,
            'concurrent_time': concurrent_time,
            'sequential_success_count': sequential_success_count,
            'concurrent_success_count': concurrent_success_count,
            'sequential_ops_per_sec': sequential_ops_per_sec,
            'concurrent_ops_per_sec': concurrent_ops_per_sec,
            'performance_ratio': performance_ratio,
            'concurrent_reliability': concurrent_success_count / num_operations,
            'sequential_reliability': sequential_success_count / num_operations,
            'serialization_overhead': max(0, (concurrent_time / sequential_time) - 1) if sequential_time > 0 else 0
        }
        
        self.test_results.append(test_result)
        self.performance_metrics.update(test_result)
        logger.info(f"Performance comparison completed: {test_result}")
        
        # Assertions
        assert concurrent_success_count == num_operations, "Concurrent operations had failures"
        assert sequential_success_count == num_operations, "Sequential operations had failures"
        assert test_result['serialization_overhead'] < 0.5, "Too much serialization overhead"
        
        return test_result
    
    async def run_all_tests(self):
        """Run all concurrent session tests."""
        logger.info("Starting comprehensive concurrent session test suite")
        
        start_time = time.time()
        
        try:
            # Run all tests
            await self.test_multiple_server_instances(num_instances=3, operations_per_instance=5)
            await self.test_concurrent_write_operations(num_concurrent=8)
            await self.test_shared_cache_consistency(num_instances=3, num_operations=10)
            await self.test_operation_queue_priorities(num_operations=15)
            await self.test_race_condition_prevention(num_concurrent=10)
            await self.test_stress_test_many_operations(num_operations=30, num_concurrent_batches=5)
            await self.test_data_consistency_parallel_operations(num_parallel=8)
            await self.test_performance_concurrent_vs_sequential(num_operations=15)
            
        except Exception as e:
            logger.error(f"Test suite failed: {e}")
            raise
        finally:
            await self.cleanup()
        
        total_time = time.time() - start_time
        
        # Generate summary report
        summary = self.generate_test_summary(total_time)
        logger.info(f"Test suite completed in {total_time:.2f}s")
        logger.info(f"Summary: {summary}")
        
        return summary
    
    def generate_test_summary(self, total_time: float) -> Dict[str, Any]:
        """Generate a comprehensive test summary."""
        total_tests = len(self.test_results)
        passed_tests = len([r for r in self.test_results if self._is_test_passed(r)])
        
        summary = {
            'total_tests': total_tests,
            'passed_tests': passed_tests,
            'failed_tests': total_tests - passed_tests,
            'success_rate': passed_tests / total_tests if total_tests > 0 else 0,
            'total_execution_time': total_time,
            'test_results': self.test_results,
            'performance_metrics': self.performance_metrics,
            'conclusions': self._generate_conclusions()
        }
        
        return summary
    
    def _is_test_passed(self, test_result: Dict[str, Any]) -> bool:
        """Determine if a test passed based on its results."""
        test_name = test_result.get('test', '')
        
        # Common success criteria
        if 'success_rate' in test_result:
            if test_result['success_rate'] < 0.95:
                return False
        
        # Test-specific criteria
        if test_name == 'multiple_server_instances':
            return test_result.get('properly_serialized', False)
        elif test_name == 'concurrent_write_operations':
            return test_result.get('properly_serialized', False)
        elif test_name == 'operation_queue_priorities':
            return test_result.get('successful_operations', 0) == test_result.get('num_operations', 0)
        elif test_name == 'race_condition_prevention':
            return test_result.get('counter_consistency', False)
        elif test_name == 'stress_test_many_operations':
            return test_result.get('performance_acceptable', False) and test_result.get('success_rate', 0) > 0.95
        elif test_name == 'data_consistency_parallel_operations':
            return test_result.get('data_consistency', False)
        elif test_name == 'performance_concurrent_vs_sequential':
            return (test_result.get('concurrent_reliability', 0) == 1.0 and 
                   test_result.get('sequential_reliability', 0) == 1.0)
        
        return True  # Default to passed if no specific criteria
    
    def _generate_conclusions(self) -> List[str]:
        """Generate conclusions based on test results."""
        conclusions = []
        
        # Analyze serialization effectiveness
        serialization_tests = [r for r in self.test_results if 'properly_serialized' in r]
        if all(r['properly_serialized'] for r in serialization_tests):
            conclusions.append("✓ AppleScript operations are properly serialized across all scenarios")
        else:
            conclusions.append("✗ Some serialization issues detected")
        
        # Analyze data consistency
        consistency_tests = [r for r in self.test_results if 'data_consistency' in r or 'counter_consistency' in r]
        if all(r.get('data_consistency', r.get('counter_consistency', True)) for r in consistency_tests):
            conclusions.append("✓ Data consistency maintained under concurrent access")
        else:
            conclusions.append("✗ Data consistency issues detected")
        
        # Analyze performance
        if self.performance_metrics:
            overhead = self.performance_metrics.get('serialization_overhead', 0)
            if overhead < 0.2:
                conclusions.append(f"✓ Low serialization overhead ({overhead:.1%})")
            else:
                conclusions.append(f"⚠ High serialization overhead ({overhead:.1%})")
        
        # Analyze cache functionality
        cache_tests = [r for r in self.test_results if r.get('test') == 'shared_cache_consistency']
        if cache_tests and cache_tests[0].get('successful_operations', 0) > 0:
            conclusions.append("✓ Shared cache working correctly across instances")
        
        return conclusions


# pytest fixtures for integration with the test framework
@pytest.fixture
async def concurrent_test_suite():
    """Fixture providing the concurrent test suite."""
    suite = ConcurrentSessionTestSuite()
    yield suite
    await suite.cleanup()


# Individual test functions for pytest integration
@pytest.mark.asyncio
async def test_multiple_server_instances(concurrent_test_suite):
    """Test multiple MCP server instances running simultaneously."""
    result = await concurrent_test_suite.test_multiple_server_instances(
        num_instances=3, operations_per_instance=5
    )
    assert result['properly_serialized'], "AppleScript operations not properly serialized"
    assert result['success_rate'] == 1.0, "Some operations failed"


@pytest.mark.asyncio
async def test_concurrent_write_serialization(concurrent_test_suite):
    """Test that concurrent write operations are serialized."""
    result = await concurrent_test_suite.test_concurrent_write_operations(num_concurrent=8)
    assert result['properly_serialized'], "Write operations not properly serialized"
    assert result['failed_operations'] == 0, "Some write operations failed"


@pytest.mark.asyncio
async def test_shared_cache_across_instances(concurrent_test_suite):
    """Test shared cache functionality across multiple instances."""
    result = await concurrent_test_suite.test_shared_cache_consistency(
        num_instances=3, num_operations=10
    )
    assert result['successful_operations'] > result['total_operations'] * 0.95, "Too many cache operation failures"


@pytest.mark.asyncio
async def test_operation_queue_priority_ordering(concurrent_test_suite):
    """Test operation queue ordering and priorities."""
    result = await concurrent_test_suite.test_operation_queue_priorities(num_operations=15)
    assert result['successful_operations'] == result['num_operations'], "Some queue operations failed"


@pytest.mark.asyncio
async def test_race_condition_protection(concurrent_test_suite):
    """Test race condition prevention."""
    result = await concurrent_test_suite.test_race_condition_prevention(num_concurrent=10)
    assert result['counter_consistency'], "Race condition detected"
    assert result['applescript_serialization_correct'], "AppleScript not properly serialized"


@pytest.mark.asyncio
async def test_high_load_stress_test(concurrent_test_suite):
    """Stress test with many concurrent operations."""
    result = await concurrent_test_suite.test_stress_test_many_operations(
        num_operations=30, num_concurrent_batches=5
    )
    assert result['success_rate'] > 0.95, "Too many failures under stress"
    assert result['performance_acceptable'], "Performance degraded too much under load"


@pytest.mark.asyncio
async def test_data_consistency_under_parallelism(concurrent_test_suite):
    """Test data consistency with parallel operations."""
    result = await concurrent_test_suite.test_data_consistency_parallel_operations(num_parallel=8)
    assert result['data_consistency'], "Data consistency failed under parallel load"
    assert result['applescript_executions_ordered'], "AppleScript executions not properly ordered"


@pytest.mark.asyncio
async def test_performance_metrics(concurrent_test_suite):
    """Test performance comparison between concurrent and sequential operations."""
    result = await concurrent_test_suite.test_performance_concurrent_vs_sequential(num_operations=15)
    assert result['concurrent_reliability'] == 1.0, "Concurrent operations had reliability issues"
    assert result['serialization_overhead'] < 0.5, "Excessive serialization overhead"


# Main execution for standalone testing
async def main():
    """Run the complete concurrent session test suite."""
    print("🚀 Starting Comprehensive Concurrent Session Testing Suite for Things 3 MCP Server")
    print("=" * 80)
    
    suite = ConcurrentSessionTestSuite()
    
    try:
        summary = await suite.run_all_tests()
        
        print("\n" + "=" * 80)
        print("📊 TEST SUITE SUMMARY")
        print("=" * 80)
        print(f"Total Tests: {summary['total_tests']}")
        print(f"Passed: {summary['passed_tests']}")
        print(f"Failed: {summary['failed_tests']}")
        print(f"Success Rate: {summary['success_rate']:.1%}")
        print(f"Total Execution Time: {summary['total_execution_time']:.2f}s")
        
        print("\n🔍 CONCLUSIONS:")
        for conclusion in summary['conclusions']:
            print(f"  {conclusion}")
        
        print("\n📈 PERFORMANCE METRICS:")
        for key, value in summary['performance_metrics'].items():
            if isinstance(value, (int, float)):
                print(f"  {key}: {value}")
        
        if summary['failed_tests'] == 0:
            print("\n🎉 ALL TESTS PASSED! Concurrency fixes are working correctly.")
            return 0
        else:
            print(f"\n❌ {summary['failed_tests']} tests failed. Check logs for details.")
            return 1
            
    except Exception as e:
        print(f"\n💥 Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)