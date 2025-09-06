"""
Operation Queue for Things 3 MCP Server

Provides serialized execution of write operations to ensure data consistency
and prevent race conditions when multiple operations are performed concurrently.
"""

import asyncio
import logging
import time
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, List, Awaitable
from uuid import uuid4
import traceback

logger = logging.getLogger(__name__)


def safe_log(level: int, message: str, *args, **kwargs):
    """Safe logging that prevents errors during shutdown when streams are closed."""
    try:
        # Check if stdout/stderr are still available
        if hasattr(sys.stdout, 'closed') and sys.stdout.closed:
            return
        if hasattr(sys.stderr, 'closed') and sys.stderr.closed:
            return
        
        # Use the logger normally if streams are available
        logger.log(level, message, *args, **kwargs)
    except (ValueError, OSError):
        # Streams are closed or unavailable, silently ignore
        pass


class Priority(Enum):
    """Operation priority levels"""
    HIGH = 1
    NORMAL = 2
    LOW = 3


class OperationStatus(Enum):
    """Operation status states"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class Operation:
    """Represents a queued operation"""
    id: str = field(default_factory=lambda: str(uuid4())[:8])
    name: str = ""
    func: Callable[..., Awaitable[Any]] = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    priority: Priority = Priority.NORMAL
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: OperationStatus = OperationStatus.PENDING
    result: Any = None
    error: Optional[Exception] = None
    retry_count: int = 0

    def __post_init__(self):
        if not self.name and self.func:
            self.name = f"{self.func.__name__}({self.id})"

    @property
    def duration(self) -> Optional[float]:
        """Get operation duration if completed"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    @property
    def wait_time(self) -> float:
        """Get time spent waiting in queue"""
        start_time = self.started_at or time.time()
        return start_time - self.created_at


class OperationQueue:
    """
    Async operation queue with priority support, timeouts, and retry logic.
    
    Ensures write operations are executed serially to prevent race conditions
    and data inconsistency in Things 3.
    """

    def __init__(self, max_concurrent: int = 1):
        """
        Initialize the operation queue.
        
        Args:
            max_concurrent: Maximum concurrent operations (default 1 for serialization)
        """
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._active_operations: Dict[str, Operation] = {}
        self._completed_operations: List[Operation] = []
        self._max_completed_history = 100
        self._max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._worker_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._stats = {
            'total_operations': 0,
            'completed_operations': 0,
            'failed_operations': 0,
            'timeout_operations': 0,
            'retried_operations': 0
        }

    async def start(self):
        """Start the queue worker"""
        if self._worker_task and not self._worker_task.done():
            logger.warning("Queue worker already running")
            return

        self._shutdown_event.clear()
        self._worker_task = asyncio.create_task(self._worker())
        logger.info("Operation queue worker started")

    async def stop(self, timeout: float = 10.0):
        """Stop the queue worker"""
        if not self._worker_task:
            return

        self._shutdown_event.set()
        
        try:
            await asyncio.wait_for(self._worker_task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Queue worker did not stop gracefully, cancelling")
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        safe_log(logging.INFO, "Operation queue worker stopped")

    async def enqueue(
        self,
        func: Callable[..., Awaitable[Any]],
        *args,
        name: str = "",
        priority: Priority = Priority.NORMAL,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        **kwargs
    ) -> str:
        """
        Enqueue an operation for execution.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for the function
            name: Human-readable operation name
            priority: Operation priority
            timeout: Timeout in seconds
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries in seconds
            **kwargs: Keyword arguments for the function
            
        Returns:
            Operation ID
        """
        operation = Operation(
            name=name,
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority,
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

        # Priority queue uses tuple (priority_value, counter, item)
        priority_value = priority.value
        counter = self._stats['total_operations']
        
        await self._queue.put((priority_value, counter, operation))
        self._stats['total_operations'] += 1

        logger.debug(f"Enqueued operation {operation.id}: {operation.name}")
        return operation.id

    async def wait_for_operation(self, operation_id: str, timeout: float = None) -> Any:
        """
        Wait for a specific operation to complete.
        
        Args:
            operation_id: ID of the operation to wait for
            timeout: Maximum time to wait
            
        Returns:
            Operation result
            
        Raises:
            asyncio.TimeoutError: If operation doesn't complete within timeout
            Exception: If operation failed
        """
        start_time = time.time()
        
        while True:
            # Check if operation is completed
            for op in self._completed_operations:
                if op.id == operation_id:
                    if op.status == OperationStatus.COMPLETED:
                        return op.result
                    elif op.status == OperationStatus.FAILED:
                        raise op.error or Exception(f"Operation {operation_id} failed")
                    else:
                        raise Exception(f"Operation {operation_id} ended with status: {op.status}")

            # Check if operation is still active
            if operation_id not in self._active_operations:
                # Check if we've been waiting too long
                if timeout and (time.time() - start_time) > timeout:
                    raise asyncio.TimeoutError(f"Operation {operation_id} did not complete within {timeout}s")

            await asyncio.sleep(0.1)

    def get_operation_status(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get status information for an operation"""
        # Check active operations
        if operation_id in self._active_operations:
            op = self._active_operations[operation_id]
            return {
                'id': op.id,
                'name': op.name,
                'status': op.status.value,
                'priority': op.priority.name,
                'created_at': op.created_at,
                'started_at': op.started_at,
                'wait_time': op.wait_time,
                'retry_count': op.retry_count
            }

        # Check completed operations
        for op in self._completed_operations:
            if op.id == operation_id:
                return {
                    'id': op.id,
                    'name': op.name,
                    'status': op.status.value,
                    'priority': op.priority.name,
                    'created_at': op.created_at,
                    'started_at': op.started_at,
                    'completed_at': op.completed_at,
                    'duration': op.duration,
                    'wait_time': op.wait_time,
                    'retry_count': op.retry_count,
                    'error': str(op.error) if op.error else None
                }

        return None

    def get_queue_status(self) -> Dict[str, Any]:
        """Get overall queue status"""
        return {
            'queue_size': self._queue.qsize(),
            'active_operations': len(self._active_operations),
            'completed_operations_history': len(self._completed_operations),
            'max_concurrent': self._max_concurrent,
            'statistics': self._stats.copy()
        }

    def get_active_operations(self) -> List[Dict[str, Any]]:
        """Get list of currently active operations"""
        return [
            {
                'id': op.id,
                'name': op.name,
                'status': op.status.value,
                'priority': op.priority.name,
                'started_at': op.started_at,
                'wait_time': op.wait_time
            }
            for op in self._active_operations.values()
        ]

    async def cancel_operation(self, operation_id: str) -> bool:
        """
        Cancel a pending or active operation.
        
        Args:
            operation_id: ID of operation to cancel
            
        Returns:
            True if operation was cancelled, False if not found or already completed
        """
        if operation_id in self._active_operations:
            op = self._active_operations[operation_id]
            if op.status == OperationStatus.RUNNING:
                # Can't cancel running operation, but mark it for cancellation
                logger.warning(f"Cannot cancel running operation {operation_id}")
                return False
            
            op.status = OperationStatus.CANCELLED
            self._move_to_completed(op)
            return True

        return False

    async def _worker(self):
        """Main worker loop that processes queued operations"""
        logger.info("Queue worker started")
        
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Get next operation with timeout to allow checking shutdown
                    _, _, operation = await asyncio.wait_for(
                        self._queue.get(), timeout=1.0
                    )
                    
                    # Process the operation
                    await self._process_operation(operation)
                    
                except asyncio.TimeoutError:
                    # Timeout is normal, just check shutdown and continue
                    continue
                except Exception as e:
                    logger.error(f"Unexpected error in queue worker: {e}")
                    logger.debug(traceback.format_exc())
                    
        except asyncio.CancelledError:
            safe_log(logging.INFO, "Queue worker cancelled")
        finally:
            safe_log(logging.INFO, "Queue worker stopped")

    async def _process_operation(self, operation: Operation):
        """Process a single operation with timeout and retry logic"""
        async with self._semaphore:
            self._active_operations[operation.id] = operation
            operation.status = OperationStatus.RUNNING
            operation.started_at = time.time()
            
            logger.debug(f"Processing operation {operation.id}: {operation.name}")
            
            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    operation.func(*operation.args, **operation.kwargs),
                    timeout=operation.timeout
                )
                
                operation.result = result
                operation.status = OperationStatus.COMPLETED
                operation.completed_at = time.time()
                self._stats['completed_operations'] += 1
                
                logger.debug(f"Operation {operation.id} completed successfully")
                
            except asyncio.TimeoutError:
                logger.warning(f"Operation {operation.id} timed out after {operation.timeout}s")
                await self._handle_operation_failure(operation, TimeoutError("Operation timed out"))
                
            except Exception as e:
                logger.warning(f"Operation {operation.id} failed: {e}")
                await self._handle_operation_failure(operation, e)
            
            finally:
                # Only move to completed if the operation is actually done (not re-queued for retry)
                if operation.status != OperationStatus.PENDING:
                    self._move_to_completed(operation)
                else:
                    # Remove from active operations since it's been re-queued
                    if operation.id in self._active_operations:
                        del self._active_operations[operation.id]

    async def _handle_operation_failure(self, operation: Operation, error: Exception):
        """Handle operation failure with retry logic"""
        operation.error = error
        operation.retry_count += 1
        
        if operation.retry_count <= operation.max_retries:
            logger.info(f"Retrying operation {operation.id} (attempt {operation.retry_count}/{operation.max_retries})")
            
            # Reset operation state for retry
            operation.status = OperationStatus.PENDING
            operation.started_at = None
            self._stats['retried_operations'] += 1
            
            # Re-queue with delay
            if operation.retry_delay > 0:
                await asyncio.sleep(operation.retry_delay)
            
            priority_value = operation.priority.value
            counter = self._stats['total_operations']
            await self._queue.put((priority_value, counter, operation))
            
        else:
            # Max retries exceeded
            if isinstance(error, TimeoutError):
                operation.status = OperationStatus.TIMEOUT
                self._stats['timeout_operations'] += 1
            else:
                operation.status = OperationStatus.FAILED
                self._stats['failed_operations'] += 1
            
            operation.completed_at = time.time()
            logger.error(f"Operation {operation.id} failed permanently after {operation.retry_count} attempts: {error}")

    def _move_to_completed(self, operation: Operation):
        """Move operation from active to completed list"""
        if operation.id in self._active_operations:
            del self._active_operations[operation.id]
        
        self._completed_operations.append(operation)
        
        # Maintain history size limit
        if len(self._completed_operations) > self._max_completed_history:
            self._completed_operations = self._completed_operations[-self._max_completed_history:]


# Global queue instance
_global_queue: Optional[OperationQueue] = None


async def get_operation_queue() -> OperationQueue:
    """Get or create the global operation queue instance"""
    global _global_queue
    
    if _global_queue is None:
        _global_queue = OperationQueue()
        await _global_queue.start()
    elif _global_queue._worker_task is None or _global_queue._worker_task.done():
        # Worker is not running, restart it
        logger.warning("Queue worker was not running, restarting...")
        await _global_queue.start()
    
    return _global_queue


async def shutdown_operation_queue():
    """Shutdown the global operation queue"""
    global _global_queue
    
    if _global_queue is not None:
        await _global_queue.stop()
        _global_queue = None