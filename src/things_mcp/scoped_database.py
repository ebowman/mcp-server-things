"""Read Things through the picker-granted, sandboxed SQLite helper."""

import atexit
import json
import os
import select
import subprocess
import tempfile
import threading
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

from things.database import Database, dict_factory

from .things_import import ScopedHelperAccessError, ScopedHelperError

HELPER_APP_ENV = "THINGS_MCP_SCOPED_HELPER_APP"
_TIMEOUT = 15.0
_MAX_RESPONSE = 64 * 1024 * 1024
_client = None
_client_lock = threading.Lock()


class _HelperClient:
    def __init__(self, app_path: str):
        app = Path(app_path)
        if not app.is_absolute() or not app.is_dir() or app.suffix != ".app":
            raise ScopedHelperAccessError(
                "THINGS_MCP_SCOPED_HELPER_APP must name a built .app"
            )

        self._lock = threading.Lock()
        self._buffer = b""
        self._input = None
        self._output = None
        self._launcher = None
        self._folder = tempfile.TemporaryDirectory(prefix="things-mcp-scoped-")
        try:
            input_path = os.path.join(self._folder.name, "input")
            output_path = os.path.join(self._folder.name, "output")
            os.mkfifo(input_path, 0o600)
            os.mkfifo(output_path, 0o600)
            self._input = os.open(input_path, os.O_RDWR | os.O_NONBLOCK)
            self._output = os.open(output_path, os.O_RDWR | os.O_NONBLOCK)
            self._launcher = subprocess.Popen(
                [
                    "open",
                    "-g",
                    "-n",
                    "-W",
                    "-i",
                    input_path,
                    "-o",
                    output_path,
                    str(app),
                    "--args",
                    "serve",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ready = self._read_message()
            if ready.get("ready") is not True or ready.get("readonly") is not True:
                if ready.get("error") == "no_saved_bookmark":
                    raise ScopedHelperAccessError(
                        "Grant the Things database in the helper first"
                    )
                if ready.get("error") == "bookmark_stale":
                    raise ScopedHelperAccessError(
                        "Saved Things database grant is stale; select the bundle again"
                    )
                raise ScopedHelperAccessError(
                    f"Things helper could not open the database ({ready.get('error', 'unknown')})"
                )
        except Exception as exc:
            self.abort()
            if isinstance(exc, OSError):
                raise ScopedHelperAccessError(
                    "Could not launch the Things helper"
                ) from exc
            raise

    def _read_message(self):
        deadline = time.monotonic() + _TIMEOUT
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ScopedHelperAccessError("Timed out waiting for the Things helper")
            if select.select([self._output], [], [], remaining)[0]:
                chunk = os.read(self._output, 65536)
                if chunk:
                    self._buffer += chunk
                    if len(self._buffer) > _MAX_RESPONSE:
                        raise ScopedHelperError("Things helper response is too large")
        line, self._buffer = self._buffer.split(b"\n", 1)
        try:
            result = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ScopedHelperError("Things helper returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise ScopedHelperError("Things helper returned an invalid response")
        return result

    def _write_message(self, message):
        data = (json.dumps(message, separators=(",", ":")) + "\n").encode()
        if len(data) > 1024 * 1024:
            raise ScopedHelperError("Things query is too large")
        deadline = time.monotonic() + _TIMEOUT
        while data:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([], [self._input], [], remaining)[1]:
                raise ScopedHelperAccessError("Timed out sending a Things query")
            data = data[os.write(self._input, data) :]

    def query(self, sql, parameters):
        with self._lock:
            try:
                if self._input is None:
                    raise ScopedHelperAccessError("Things helper connection was closed")
                self._write_message({"sql": sql, "parameters": list(parameters)})
                result = self._read_message()
            except (ScopedHelperError, OSError) as exc:
                _drop_client(self)
                if isinstance(exc, OSError):
                    raise ScopedHelperAccessError(
                        "Things helper connection failed"
                    ) from exc
                raise
        if result.get("ok") is not True:
            raise ScopedHelperError(
                "Things helper rejected a read-only query "
                f"({result.get('error', 'unknown')}, code {result.get('code', 'unknown')})"
            )
        columns, rows = result.get("columns"), result.get("rows")
        if not isinstance(columns, list) or not all(
            isinstance(c, str) for c in columns
        ):
            raise ScopedHelperError("Things helper returned invalid columns")
        if not isinstance(rows, list) or not all(
            isinstance(row, list) and len(row) == len(columns) for row in rows
        ):
            raise ScopedHelperError("Things helper returned invalid rows")
        return columns, rows

    def close(self):
        if self._launcher is not None and self._input is not None:
            try:
                os.write(self._input, b'{"action":"quit"}\n')
            except OSError:
                pass
        self.abort()

    def abort(self) -> None:
        launcher = self._launcher
        self._launcher = None
        for name in ("_input", "_output"):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                setattr(self, name, None)
                try:
                    os.close(descriptor)
                except OSError:
                    pass
        if self._folder is not None:
            self._folder.cleanup()
            self._folder = None
        if launcher is not None:
            try:
                launcher.wait(timeout=2)
            except subprocess.TimeoutExpired:
                launcher.terminate()
                try:
                    launcher.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    launcher.kill()
                    launcher.wait()


def _drop_client(client: _HelperClient) -> None:
    global _client
    with _client_lock:
        if _client is client:
            _client = None
    atexit.unregister(client.close)
    client.abort()


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            app_path = os.environ.get(HELPER_APP_ENV)
            if not app_path:
                raise ScopedHelperAccessError(f"{HELPER_APP_ENV} is not set")
            _client = _HelperClient(app_path)
            atexit.register(_client.close)
        return _client


def _decode(value):
    if isinstance(value, dict) and set(value) == {"$blob"}:
        import base64

        return base64.b64decode(value["$blob"], validate=True)
    return value


class ScopedDatabase(Database):
    """Use things.py's SQL and conversion logic with a scoped query transport."""

    def __init__(self, filepath=None, print_sql=False):
        if filepath is not None or print_sql:
            raise ScopedHelperError(
                "Scoped Things access does not accept a filepath or SQL logging"
            )
        self.print_sql = False
        self.filepath = "<picker-selected Things database>"
        if self.get_version() <= 21:
            raise ScopedHelperError("Things database format is too old for things.py")

    def execute_query(self, sql_query, parameters=(), row_factory=None):
        columns, rows = _get_client().query(sql_query, parameters)
        cursor = SimpleNamespace(description=[(name,) for name in columns])
        factory = row_factory or dict_factory
        return [factory(cursor, tuple(_decode(value) for value in row)) for row in rows]


@lru_cache(maxsize=1)
def get_scoped_database() -> ScopedDatabase:
    """Reuse things.py's database wrapper while reconnecting its transport as needed."""
    return ScopedDatabase()
