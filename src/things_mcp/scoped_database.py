"""Read Things through the picker-granted, sandboxed SQLite helper."""

import atexit
import json
import os
import select
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from things.database import Database, dict_factory

HELPER_APP_ENV = "THINGS_MCP_SCOPED_HELPER_APP"
_TIMEOUT = 15.0
_MAX_RESPONSE = 64 * 1024 * 1024
_client = None
_client_lock = threading.Lock()


class ScopedHelperError(RuntimeError):
    """The sandboxed Things reader could not answer a query."""


class _HelperClient:
    def __init__(self, app_path: str):
        app = Path(app_path)
        if not app.is_absolute() or not app.is_dir() or app.suffix != ".app":
            raise ScopedHelperError(
                "THINGS_MCP_SCOPED_HELPER_APP must name a built .app"
            )

        self._lock = threading.Lock()
        self._buffer = b""
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
                    raise ScopedHelperError(
                        "Grant the Things database in the helper first"
                    )
                raise ScopedHelperError("Things helper did not start in read-only mode")
        except Exception:
            self.close()
            raise

    def _read_message(self):
        deadline = time.monotonic() + _TIMEOUT
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ScopedHelperError("Timed out waiting for the Things helper")
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
                raise ScopedHelperError("Timed out sending a Things query")
            data = data[os.write(self._input, data) :]

    def query(self, sql, parameters):
        with self._lock:
            self._write_message({"sql": sql, "parameters": list(parameters)})
            result = self._read_message()
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
        if getattr(self, "_launcher", None) is not None:
            try:
                self._write_message({"action": "quit"})
                self._launcher.wait(timeout=2)
            except (OSError, ScopedHelperError, subprocess.TimeoutExpired):
                pass
        for name in ("_input", "_output"):
            descriptor = getattr(self, name, None)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, name, None)
        if getattr(self, "_folder", None) is not None:
            self._folder.cleanup()
            self._folder = None


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            app_path = os.environ.get(HELPER_APP_ENV)
            if not app_path:
                raise ScopedHelperError(f"{HELPER_APP_ENV} is not set")
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
        self._client = _get_client()
        if self.get_version() <= 21:
            raise ScopedHelperError("Things database format is too old for things.py")

    def execute_query(self, sql_query, parameters=(), row_factory=None):
        columns, rows = self._client.query(sql_query, parameters)
        cursor = SimpleNamespace(description=[(name,) for name in columns])
        factory = row_factory or dict_factory
        return [factory(cursor, tuple(_decode(value) for value in row)) for row in rows]
