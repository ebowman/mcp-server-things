"""Real-pipe and real-lifecycle tests for the scoped helper client (hq-w6p.8)."""

import os
import threading
from unittest.mock import Mock

import pytest

import things_mcp.scoped_database as sd
from things_mcp.scoped_database import (
    ScopedDatabase,
    ScopedHelperAccessError,
    ScopedHelperError,
    ScopedHelperTimeoutError,
    _HelperClient,
)


def _client(input_fd=None, output_fd=None):
    client = object.__new__(_HelperClient)
    client._lock = threading.Lock()
    client._buffer = b""
    client._input = input_fd
    client._output = output_fd
    client._launcher = None
    client._folder = None
    return client


@pytest.fixture
def pipe():
    """A real non-blocking pipe: (read_fd, write_fd)."""
    r, w = os.pipe()
    os.set_blocking(r, False)
    os.set_blocking(w, False)
    try:
        yield r, w
    finally:
        for fd in (r, w):
            try:
                os.close(fd)
            except OSError:
                pass


@pytest.fixture(autouse=True)
def fast_timeout(monkeypatch):
    monkeypatch.setattr(sd, "_TIMEOUT", 0.05)


def test_read_message_times_out_on_silent_pipe(pipe):
    r, _w = pipe
    with pytest.raises(ScopedHelperTimeoutError, match="Timed out waiting for the Things helper"):
        _client(output_fd=r)._read_message()


def test_write_message_times_out_on_full_pipe(pipe):
    r, w = pipe
    try:
        while True:
            os.write(w, b"x" * 65536)
    except BlockingIOError:
        pass
    with pytest.raises(ScopedHelperTimeoutError, match="Timed out sending a Things query"):
        _client(input_fd=w)._write_message({"sql": "SELECT 1"})


def test_write_message_rejects_oversized_query_before_touching_fd():
    # fd -1 would raise if select/os.write were reached
    with pytest.raises(ScopedHelperError, match="Things query is too large") as info:
        _client(input_fd=-1)._write_message({"sql": "x" * (1024 * 1024 + 1)})
    assert not isinstance(info.value, ScopedHelperTimeoutError)


def test_write_message_writes_newline_terminated_json(pipe):
    r, w = pipe
    _client(input_fd=w)._write_message({"sql": "SELECT 1"})
    assert os.read(r, 4096) == b'{"sql":"SELECT 1"}\n'


def test_read_message_rejects_oversized_response_without_newline(pipe, monkeypatch):
    r, w = pipe
    monkeypatch.setattr(sd, "_MAX_RESPONSE", 16)
    os.write(w, b"a" * 64)
    with pytest.raises(ScopedHelperError, match="response is too large"):
        _client(output_fd=r)._read_message()


def test_read_message_invalid_json(pipe):
    r, w = pipe
    os.write(w, b"not json\n")
    with pytest.raises(ScopedHelperError, match="invalid JSON"):
        _client(output_fd=r)._read_message()


def test_read_message_non_object_json(pipe):
    r, w = pipe
    os.write(w, b"[]\n")
    with pytest.raises(ScopedHelperError, match="invalid response"):
        _client(output_fd=r)._read_message()


def test_read_message_returns_dict_and_keeps_remainder(pipe):
    r, w = pipe
    os.write(w, b'{"a":1}\n{"b":2}\n')
    client = _client(output_fd=r)
    assert client._read_message() == {"a": 1}
    assert client._read_message() == {"b": 2}


@pytest.mark.parametrize(
    "error, message",
    [
        (ScopedHelperTimeoutError("Timed out waiting for the Things helper"), "Timed out"),
        (ScopedHelperError("Things helper response is too large"), "too large"),
    ],
)
def test_startup_read_failure_is_wrapped_as_access_error(monkeypatch, tmp_path, error, message):
    # ScopedHelperTimeoutError is a plain ScopedHelperError (not an access error),
    # so startup wraps it into ScopedHelperAccessError("... startup failed: ...").
    app = tmp_path / "Helper.app"
    app.mkdir()
    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **k: Mock())
    monkeypatch.setattr(_HelperClient, "_read_message", Mock(side_effect=error))
    # Spy on abort but run the real one so the constructor's FIFOs and temp
    # directory are released (a bare Mock would leak the two pipe fds).
    real_abort = _HelperClient.abort
    abort_calls = []

    def spying_abort(self):
        abort_calls.append(self)
        return real_abort(self)

    monkeypatch.setattr(_HelperClient, "abort", spying_abort)
    with pytest.raises(ScopedHelperAccessError, match="startup failed") as info:
        _HelperClient(str(app))
    assert message in str(info.value)
    assert info.value.__cause__ is error
    assert len(abort_calls) == 1


def test_startup_real_timeout_on_silent_helper(monkeypatch, tmp_path):
    app = tmp_path / "Helper.app"
    app.mkdir()
    launcher = Mock()
    launcher.wait.return_value = 0
    monkeypatch.setattr(sd.subprocess, "Popen", lambda *a, **k: launcher)
    with pytest.raises(ScopedHelperAccessError, match="startup failed: Timed out waiting"):
        _HelperClient(str(app))
    launcher.wait.assert_called()


def test_ok_false_reply_raises_and_does_not_drop_client(monkeypatch):
    client = _client(input_fd=1)
    client._write_message = lambda _m: None
    client._read_message = Mock(
        return_value={"ok": False, "error": "not_readonly", "code": 7}
    )
    dropped = Mock()
    monkeypatch.setattr(sd, "_drop_client", dropped)
    monkeypatch.setattr(sd, "_client", client)
    with pytest.raises(ScopedHelperError, match="rejected a read-only query") as info:
        client.query("DELETE FROM x", ())
    assert "not_readonly" in str(info.value) and "code 7" in str(info.value)
    assert not isinstance(info.value, ScopedHelperAccessError)
    dropped.assert_not_called()
    assert sd._client is client


def test_ok_false_is_not_retried_by_execute_query(monkeypatch):
    client = _client(input_fd=1)
    client._write_message = lambda _m: None
    client._read_message = Mock(return_value={"ok": False, "error": "bad", "code": 1})
    query = Mock(wraps=client.query)
    monkeypatch.setattr(client, "query", query)
    monkeypatch.setattr(sd, "_client", client)
    monkeypatch.setattr(sd, "_get_client", lambda: client)
    with pytest.raises(ScopedHelperError, match="rejected a read-only query"):
        object.__new__(ScopedDatabase).execute_query("SELECT 1")
    assert query.call_count == 1
    assert client._read_message.call_count == 1
    assert sd._client is client


def test_real_drop_and_get_client_retry_on_fresh_client(monkeypatch):
    first = _client(input_fd=None)  # closed: query raises _ScopedHelperClosedError
    first.abort = Mock()
    second = _client(input_fd=1)
    second._write_message = lambda _m: None
    second._read_message = lambda: {"ok": True, "columns": ["a"], "rows": [[7]]}
    second.close = Mock()
    factory = Mock(return_value=second)
    register = Mock()
    unregister = Mock()
    monkeypatch.setattr(sd, "_client", first)
    monkeypatch.setattr(sd, "_HelperClient", factory)
    monkeypatch.setattr(sd.atexit, "register", register)
    monkeypatch.setattr(sd.atexit, "unregister", unregister)
    monkeypatch.setenv(sd.HELPER_APP_ENV, "/tmp/ThingsReadHelper.app")

    assert sd._get_client() is first  # existing client reused, nothing constructed
    factory.assert_not_called()

    rows = object.__new__(ScopedDatabase).execute_query("SELECT a")

    assert rows == [{"a": 7}]
    unregister.assert_called_once_with(first.close)
    first.abort.assert_called_once()
    factory.assert_called_once_with("/tmp/ThingsReadHelper.app")
    register.assert_called_once_with(second.close)
    assert sd._client is second
