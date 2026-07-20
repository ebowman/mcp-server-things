"""Lazy, timeout-bounded import of the ``things`` (things.py) package.

The ``things`` package performs a module-level, synchronous, unbounded
``glob.iglob()`` scan of the Things 3 Group Containers directory at import
time (``things/database.py``, resolving the sqlite database path). If that
filesystem path stalls -- a sleeping external volume, FileVault unlock
delay, or heavy Spotlight/Time Machine contention -- a plain ``import
things`` at module load time can hang the whole process silently, well
before the MCP stdio handshake completes.

This module moves that import off the synchronous critical path: the first
call to :func:`get_things` performs the import in a background daemon
thread and joins it with a bounded timeout, emitting boot markers so a
stall is loudly diagnosable instead of a silent hang. Subsequent calls
return the cached module instantly with no thread/markers involved.
"""

import importlib
import os
import sys
import threading
from typing import Optional
from types import ModuleType

from .boot_trace import boot_marker

_TIMEOUT_ENV_VAR = "THINGS_MCP_THINGS_IMPORT_TIMEOUT_SECS"
_TIMEOUT_DEFAULT_SECS = 10.0

_lock = threading.Lock()
_things_module: Optional[ModuleType] = None
_import_error: Optional[BaseException] = None


class ThingsImportTimeoutError(RuntimeError):
    """Raised when importing the ``things`` package exceeds the configured timeout.

    This most likely indicates a stall in the module-level filesystem scan
    that ``things.py`` performs at import time (a ``glob.iglob()`` walk of
    the Things 3 Group Containers directory, looking for the SQLite
    database). Likely causes: a sleeping/unmounted external volume, a
    FileVault unlock delay, or heavy Spotlight/Time Machine contention on
    that path.
    """


def _resolve_timeout(explicit: Optional[float]) -> Optional[float]:
    """Resolve the effective import timeout in seconds.

    Args:
        explicit: Caller-supplied timeout override, if any. Takes
            precedence over the environment variable.

    Returns:
        The timeout in seconds to pass to ``Thread.join()``, or ``None``
        if the import should block without any bound (i.e. a plain,
        unbounded import).
    """
    if explicit is not None:
        value = explicit
    else:
        raw = os.environ.get(_TIMEOUT_ENV_VAR)
        if raw is None:
            value = _TIMEOUT_DEFAULT_SECS
        else:
            try:
                value = float(raw)
            except ValueError:
                value = _TIMEOUT_DEFAULT_SECS

    if value <= 0:
        # <= 0 means "no timeout bound": block on the import like a plain
        # `import things` would. Documented behavior, not a fallback to
        # the default.
        return None
    return value


def get_things(timeout: Optional[float] = None) -> ModuleType:
    """Return the ``things`` package module, importing it lazily if needed.

    On first call, imports ``things`` in a background daemon thread and
    joins it with a bounded timeout (see ``_resolve_timeout``). If the
    import completes within the timeout, the resulting module is cached
    and returned on this and all subsequent calls (subsequent calls do not
    spawn a thread or emit boot markers -- they return the cached module
    instantly).

    If the import does not complete within the timeout, this raises
    :class:`ThingsImportTimeoutError` and emits a boot marker documenting
    the stall. Note that the background daemon thread is not killed in
    this case -- it may still complete the import later. A subsequent call
    to ``get_things()`` will notice the module landed in ``sys.modules``
    (or in our cache, if the earlier thread's result gets stored) and
    return it gracefully rather than re-attempting or re-raising.

    If the import thread raised an exception (e.g. ``ImportError``), that
    exception is re-raised here (on the call that observed the failure).

    Args:
        timeout: Optional override for the timeout in seconds. If omitted,
            the ``THINGS_MCP_THINGS_IMPORT_TIMEOUT_SECS`` environment
            variable is consulted (default 10.0 seconds). A resolved value
            of <= 0 disables the timeout bound entirely (blocking import).

    Returns:
        The imported ``things`` module.

    Raises:
        ThingsImportTimeoutError: If the import does not complete within
            the resolved timeout.
        Exception: Whatever exception the import itself raised, if any.
    """
    global _things_module, _import_error

    with _lock:
        if _things_module is not None:
            return _things_module

        # A previous call may have timed out but the background thread
        # since completed and populated sys.modules. Notice that here
        # before spawning another import thread.
        cached = sys.modules.get("things")
        if cached is not None:
            _things_module = cached
            return _things_module

        if _import_error is not None:
            raise _import_error

        effective_timeout = _resolve_timeout(timeout)

        result: dict = {}

        def _do_import() -> None:
            try:
                result["module"] = importlib.import_module("things")
            except BaseException as exc:  # noqa: BLE001 - propagate any failure
                result["error"] = exc

        boot_marker("things-import-start")
        thread = threading.Thread(target=_do_import, daemon=True)
        thread.start()
        thread.join(effective_timeout)

        if thread.is_alive():
            boot_marker(
                "things-import-timeout "
                f"(exceeded {effective_timeout}s; likely stalled in the "
                "things.py module-level glob.iglob() scan of the Things 3 "
                "Group Containers directory -- see ThingsImportTimeoutError)"
            )
            raise ThingsImportTimeoutError(
                f"Importing the 'things' package did not complete within "
                f"{effective_timeout}s. This is most likely a stall in "
                "things.py's module-level glob.iglob() scan of "
                "'~/Library/Group Containers/JLMPQHK86H.com.culturedcode."
                "ThingsMac/ThingsData-*/...' (e.g. a sleeping/unmounted "
                "volume, FileVault unlock delay, or Spotlight/Time Machine "
                "contention on that path). The import continues in a "
                "background thread; a later call to get_things() may "
                "succeed if it eventually completes."
            )

        if "error" in result:
            _import_error = result["error"]
            raise _import_error

        boot_marker("things-import-done")
        _things_module = result["module"]
        return _things_module


class LazyThingsProxy:
    """Attribute-forwarding proxy that defers importing ``things`` until first use.

    Modules that previously did ``import things`` at module scope can
    instead hold a module-level instance of this proxy under the same
    name (``things = LazyThingsProxy()``) and keep all call sites
    unchanged (``things.todos(...)``, etc.) -- the proxy transparently
    triggers :func:`get_things` on first attribute access and forwards to
    the real module from then on.

    This also preserves existing test seams that use
    ``unittest.mock.patch`` on a dotted attribute path, e.g.
    ``patch('some_module.things.today')``: ``mock.patch`` resolves
    ``some_module.things`` (this proxy instance) and then does
    ``setattr(proxy, 'today', Mock())``, which creates a real instance
    attribute that shadows ``__getattr__`` for the duration of the patch,
    and is cleanly removed (``delattr``) on exit -- falling back to
    ``__getattr__`` (and thus the real module) again afterward.
    """

    def __getattr__(self, name: str):
        return getattr(get_things(), name)
