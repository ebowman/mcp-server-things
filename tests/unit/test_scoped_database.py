import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from things.database import list_factory

import things_mcp.scoped_database as scoped_database
import things_mcp.things_import as things_import
from things_mcp.scoped_database import (
    ScopedDatabase,
    ScopedHelperAccessError,
    ScopedHelperError,
    _HelperClient,
)


def test_scoped_database_preserves_things_row_factories(monkeypatch):
    database = object.__new__(ScopedDatabase)
    client = SimpleNamespace(
        query=lambda _sql, _parameters: (
            ["title", "area", "tags", "payload"],
            [["Test", None, 1, {"$blob": "YWJj"}]],
        )
    )
    monkeypatch.setattr(scoped_database, "_get_client", lambda: client)

    assert database.execute_query("SELECT ...") == [
        {"title": "Test", "tags": True, "payload": b"abc"}
    ]
    assert database.execute_query("SELECT ...", row_factory=list_factory) == ["Test"]


def test_proxy_injects_scoped_database_without_changing_callers(monkeypatch):
    marker = object()
    todos = Mock(return_value=[])
    monkeypatch.setattr(
        things_import, "get_things", lambda: SimpleNamespace(todos=todos)
    )
    monkeypatch.setenv("THINGS_MCP_SCOPED_HELPER_APP", "/tmp/ThingsReadHelper.app")
    monkeypatch.setattr(
        "things_mcp.scoped_database.get_scoped_database", lambda: marker
    )

    assert things_import.LazyThingsProxy().todos(status="incomplete") == []
    assert todos.call_args.kwargs == {"status": "incomplete", "database": marker}


def test_helper_rejects_malformed_rows():
    helper = object.__new__(_HelperClient)
    helper._lock = threading.Lock()
    helper._input = 1
    helper._write_message = lambda _message: None
    helper._read_message = lambda: {"ok": True, "columns": ["title"], "rows": [[1, 2]]}

    with pytest.raises(ScopedHelperError, match="invalid rows"):
        helper.query("SELECT title", ())


def test_scoped_database_accepts_things_library_constructor_kwargs(monkeypatch):
    monkeypatch.setattr(ScopedDatabase, "get_version", lambda _self: 22)

    assert isinstance(ScopedDatabase(filepath=None, print_sql=False), ScopedDatabase)
    with pytest.raises(ScopedHelperError, match="does not accept a filepath"):
        ScopedDatabase(filepath="/other/database.sqlite")


def test_timeout_discards_client_before_next_query(monkeypatch):
    first = object.__new__(_HelperClient)
    first._lock = threading.Lock()
    first._input = 1
    first._buffer = b""
    first._write_message = lambda _message: None
    first._read_message = Mock(side_effect=ScopedHelperAccessError("timed out"))
    first.abort = Mock()
    monkeypatch.setattr(scoped_database, "_client", first)

    with pytest.raises(ScopedHelperAccessError, match="timed out"):
        first.query("SELECT value", ())
    first._buffer = b'{"ok":true,"columns":["value"],"rows":[["old"]]}\n'
    assert scoped_database._client is None
    first.abort.assert_called_once()

    second = object.__new__(_HelperClient)
    second._lock = threading.Lock()
    second._input = 1
    second._write_message = lambda _message: None
    second._read_message = lambda: {"ok": True, "columns": ["value"], "rows": [["new"]]}
    monkeypatch.setenv(scoped_database.HELPER_APP_ENV, "/tmp/ThingsReadHelper.app")
    monkeypatch.setattr(scoped_database, "_HelperClient", lambda _path: second)
    monkeypatch.setattr(scoped_database.atexit, "register", lambda _callback: None)

    assert scoped_database._get_client() is second
    assert second.query("SELECT value", ()) == (["value"], [["new"]])


def test_stale_bookmark_requests_new_picker_grant(tmp_path, monkeypatch):
    app = tmp_path / "ThingsReadHelper.app"
    app.mkdir()
    launcher = SimpleNamespace(wait=lambda timeout: 0)
    monkeypatch.setattr(
        scoped_database.subprocess, "Popen", lambda *_a, **_kw: launcher
    )
    monkeypatch.setattr(
        _HelperClient,
        "_read_message",
        lambda _self: {"ready": False, "error": "bookmark_stale"},
    )

    with pytest.raises(ScopedHelperAccessError, match="select the bundle again"):
        _HelperClient(str(app))


def test_scoped_database_wrapper_is_cached(monkeypatch):
    marker = object()
    constructor = Mock(return_value=marker)
    scoped_database.get_scoped_database.cache_clear()
    monkeypatch.setattr(scoped_database, "ScopedDatabase", constructor)
    try:
        assert scoped_database.get_scoped_database() is marker
        assert scoped_database.get_scoped_database() is marker
        constructor.assert_called_once_with()
    finally:
        scoped_database.get_scoped_database.cache_clear()


def _bare_client():
    client = object.__new__(_HelperClient)
    client._lock = threading.Lock()
    client._input = 1
    client._output = 2
    return client


def test_timeout_is_not_access_error_and_drops_client(monkeypatch):
    client = _bare_client()
    dropped = []
    monkeypatch.setattr(scoped_database, "_drop_client", dropped.append)

    def timeout(_message):
        raise scoped_database.ScopedHelperTimeoutError("Timed out")

    monkeypatch.setattr(client, "_write_message", timeout)
    with pytest.raises(scoped_database.ScopedHelperTimeoutError) as info:
        client.query("SELECT 1", ())
    assert not isinstance(info.value, ScopedHelperAccessError)
    assert dropped == [client]


def test_closed_connection_retries_once_and_succeeds(monkeypatch):
    calls = []

    def query(_sql, _params):
        calls.append(1)
        if len(calls) == 1:
            raise scoped_database._ScopedHelperClosedError("closed")
        return ["a"], [[1]]

    monkeypatch.setattr(
        scoped_database, "_get_client", lambda: SimpleNamespace(query=query)
    )
    database = object.__new__(ScopedDatabase)
    assert database.execute_query("SELECT 1") == [{"a": 1}]
    assert len(calls) == 2


def test_closed_connection_twice_propagates(monkeypatch):
    calls = []

    def query(_sql, _params):
        calls.append(1)
        raise scoped_database._ScopedHelperClosedError("closed")

    monkeypatch.setattr(
        scoped_database, "_get_client", lambda: SimpleNamespace(query=query)
    )
    database = object.__new__(ScopedDatabase)
    with pytest.raises(scoped_database._ScopedHelperClosedError):
        database.execute_query("SELECT 1")
    assert len(calls) == 2


def test_timeout_is_not_retried(monkeypatch):
    calls = []

    def query(_sql, _params):
        calls.append(1)
        raise scoped_database.ScopedHelperTimeoutError("Timed out")

    monkeypatch.setattr(
        scoped_database, "_get_client", lambda: SimpleNamespace(query=query)
    )
    database = object.__new__(ScopedDatabase)
    with pytest.raises(scoped_database.ScopedHelperTimeoutError):
        database.execute_query("SELECT 1")
    assert len(calls) == 1


def test_bad_startup_json_is_access_error(monkeypatch, tmp_path):
    app = tmp_path / "Helper.app"
    app.mkdir()
    monkeypatch.setattr(scoped_database.subprocess, "Popen", lambda *a, **k: Mock())
    monkeypatch.setattr(
        _HelperClient,
        "_read_message",
        lambda self: (_ for _ in ()).throw(
            ScopedHelperError("Things helper returned invalid JSON")
        ),
    )
    monkeypatch.setattr(_HelperClient, "abort", lambda self: None)
    with pytest.raises(ScopedHelperAccessError):
        _HelperClient(str(app))


def test_importing_doctor_does_not_import_things_package():
    import subprocess
    import sys

    code = (
        "import sys, things_mcp.doctor; "
        "sys.exit(1 if 'things' in sys.modules or "
        "'things_mcp.scoped_database' in sys.modules else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_scoped_helper_timeout_maps_to_internal_error_not_access_denied():
    from things_mcp.tools_helpers.read_operations import (
        is_db_access_error,
        read_error_from_exception,
    )

    exc = scoped_database.ScopedHelperTimeoutError("Timed out waiting for the Things helper")
    assert is_db_access_error(exc) is False
    assert read_error_from_exception(exc)["error"] == "internal_error"
