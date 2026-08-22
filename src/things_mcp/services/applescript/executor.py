"""AppleScript execution with process-level locking and retry logic."""

import asyncio
import logging
import time
import weakref
from typing import Dict, Any

logger = logging.getLogger(__name__)


class AppleScriptExecutor:
    """Handles AppleScript execution with locking and retry mechanisms.

    This class implements process-level locking to prevent race conditions when
    multiple AppleScript commands are executed concurrently. The lock ensures
    that only one AppleScript executes at a time, preventing potential conflicts
    and ensuring reliable operation with Things 3.

    Serialization is guaranteed WITHIN each event loop - which is where
    concurrent osascript calls actually originate (e.g. bulk fan-outs gather
    tasks on a single loop). Across loops, callers are inherently sequential
    (asyncio.run() blocks the calling thread until the loop finishes), so
    process-wide serialization is preserved in every real usage even though
    each loop gets its own Lock instance.

    Locks are keyed per-event-loop (mirroring hq-5xa's operation_queue fix)
    rather than using a single class-level asyncio.Lock(), because CPython's
    asyncio.Lock only binds its internal loop reference on a CONTENDED
    acquire (a second waiter queueing while the lock is held) - an
    uncontended acquire never binds. A class-level lock that experiences a
    contended acquire on loop A becomes permanently bound to loop A; any
    later contended acquire from a *different* loop B then raises
    "RuntimeError: ... is bound to a different event loop" instead of
    serializing. Keying by the running loop in a WeakKeyDictionary avoids
    this entirely - each loop gets its own Lock, created lazily on first
    use. Note: a lock entry for an abandoned loop is not reclaimed by this
    alone and may persist for the life of the process - same bounded,
    inert-entry retention caveat as the operation_queue's WeakKeyDictionary
    (the Lock object itself holds no resources and is simply unheld).
    """

    # Per-event-loop locks, keyed by the running loop. Lazily populated by
    # _get_lock() at acquire time - see class docstring above and hq-yxu.
    _locks_by_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock]" = weakref.WeakKeyDictionary()

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        """Get or create the AppleScript serialization lock for the
        currently running event loop.

        Each event loop gets its own Lock instance, so repeated calls within
        the same loop return the same Lock (preserving intra-loop
        serialization), while calls from a different loop transparently get
        a fresh, unbound Lock instead of raising on a lock whose internal
        loop reference was bound to a foreign loop by a prior contended
        acquire.
        """
        loop = asyncio.get_running_loop()
        lock = cls._locks_by_loop.get(loop)
        if lock is None:
            lock = asyncio.Lock()
            cls._locks_by_loop[loop] = lock
        return lock

    def __init__(self, timeout: int = 45, retry_count: int = 3):
        """Initialize the AppleScript executor.

        Args:
            timeout: Command timeout in seconds
            retry_count: Number of retries for failed commands
        """
        self.timeout = timeout
        self.retry_count = retry_count

    async def is_things_running(self) -> bool:
        """Check if Things 3 is currently running."""
        try:
            script = 'tell application "Things3" to return true'
            result = await self.execute_script(script)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Error checking Things 3 status: {e}")
            return False

    async def execute_script(self, script: str) -> Dict[str, Any]:
        """Execute an AppleScript command with retry logic.

        Args:
            script: AppleScript code to execute

        Returns:
            Dict with success status, output, and error information
        """
        return await self._execute_script_with_retry(script)

    async def _execute_script_with_retry(self, script: str) -> Dict[str, Any]:
        """Execute script with retry logic.

        Two distinct failure shapes are treated as retryable:

        1. ``result["success"] is False`` - the osascript process itself
           exited non-zero (or timed out / raised).
        2. ``result["success"] is True`` but ``result["output"]`` starts
           with the ``"ERROR:"`` in-script error convention (see
           move_operations.py's ``_build_project_move_script`` /
           ``_build_area_move_script`` / ``_get_todo_info``, and
           tag_service.py's tag-creation script). Things 3's own AppleScript
           ``on error`` handlers in those scripts catch a failure and
           `return "ERROR: " & errMsg` - osascript itself still exits 0
           (it successfully ran the script and got a return value), so
           this failure shape bypasses case 1 entirely unless we also
           check the payload here. Only an *exact* ``"ERROR:"`` prefix
           (checked with ``.strip().startswith(...)``) is treated as
           retryable - this deliberately does not pattern-match the
           substring anywhere else in the payload, since a legitimate
           todo/note body could otherwise contain the word "ERROR".
        """
        last_error = None
        last_result: Dict[str, Any] = {}

        for attempt in range(self.retry_count):
            result = await self._execute_script(script)
            last_result = result

            if result.get("success") and not self._is_error_stdout(result.get("output")):
                return result

            if result.get("success"):
                # rc=0 but in-script "ERROR:"-prefixed stdout - retryable,
                # but must NOT be reported as a generic execution failure
                # if we exhaust retries (see fallthrough below).
                last_error = result.get("output")
            else:
                last_error = result.get("error")

            if attempt < self.retry_count - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Script execution failed, retrying in {wait_time}s: {last_error}")
                await asyncio.sleep(wait_time)

        if last_result.get("success"):
            # Exhausted retries on rc=0 "ERROR:"-prefixed stdout - return the
            # result exactly as produced (same shape callers already parse,
            # e.g. move_operations.py's `output.startswith("ERROR:")` check)
            # rather than wrapping it in a different failure envelope.
            return last_result

        return {
            "success": False,
            "error": f"Failed after {self.retry_count} attempts: {last_error}"
        }

    @staticmethod
    def _is_error_stdout(output: Any) -> bool:
        """True if a successful (rc=0) script's stdout is the in-script
        ``"ERROR:"`` convention used by ``on error`` handlers that `return
        "ERROR: " & errMsg` instead of failing the osascript process.
        """
        return isinstance(output, str) and output.strip().startswith("ERROR:")

    async def _execute_script(self, script: str) -> Dict[str, Any]:
        """Execute a single AppleScript command with process-level locking.

        This method uses an asyncio.Lock to ensure only one AppleScript command
        executes at a time across the entire process. This prevents race conditions
        and ensures reliable operation with Things 3.

        The lock is acquired before starting the subprocess and held until completion.
        Lock wait times > 100ms are logged for monitoring purposes.

        Args:
            script: AppleScript code to execute

        Returns:
            Dict with success status, output/error, and execution time
        """
        lock_start_time = time.time()

        async with self._get_lock():
            # Log if we waited more than 100ms for the lock
            lock_wait_time = time.time() - lock_start_time
            if lock_wait_time > 0.1:
                logger.debug(f"AppleScript lock waited {lock_wait_time:.3f}s")

            try:
                execution_start = time.time()

                # Use asyncio subprocess to execute the AppleScript
                process = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return {
                        "success": False,
                        "error": f"Script execution timed out after {self.timeout} seconds"
                    }

                execution_time = time.time() - execution_start

                if process.returncode == 0:
                    logger.debug(f"AppleScript executed successfully in {execution_time:.3f}s")
                    return {
                        "success": True,
                        "output": stdout.decode().strip(),
                        "execution_time": execution_time
                    }
                else:
                    logger.debug(f"AppleScript failed after {execution_time:.3f}s with return code {process.returncode}")
                    return {
                        "success": False,
                        "error": stderr.decode().strip() or "Unknown AppleScript error",
                        "return_code": process.returncode
                    }

            except Exception as e:
                logger.error(f"AppleScript execution error: {e}")
                return {
                    "success": False,
                    "error": f"Execution error: {str(e)}"
                }
