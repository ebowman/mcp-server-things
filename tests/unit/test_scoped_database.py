import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from things.database import list_factory

import things_mcp.scoped_database as scoped_database
import things_mcp.things_import as things_import
from things_mcp.scoped_database import ScopedDatabase, ScopedHelperError, _HelperClient


def test_scoped_database_preserves_things_row_factories():
    database = object.__new__(ScopedDatabase)
    database._client = SimpleNamespace(
        query=lambda _sql, _parameters: (
            ["title", "area", "tags", "payload"],
            [["Test", None, 1, {"$blob": "YWJj"}]],
        )
    )

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
    monkeypatch.setattr("things_mcp.scoped_database.ScopedDatabase", lambda: marker)

    assert things_import.LazyThingsProxy().todos(status="incomplete") == []
    assert todos.call_args.kwargs == {"status": "incomplete", "database": marker}


def test_helper_rejects_malformed_rows():
    helper = object.__new__(_HelperClient)
    helper._lock = threading.Lock()
    helper._write_message = lambda _message: None
    helper._read_message = lambda: {"ok": True, "columns": ["title"], "rows": [[1, 2]]}

    with pytest.raises(ScopedHelperError, match="invalid rows"):
        helper.query("SELECT title", ())


def test_scoped_database_accepts_things_library_constructor_kwargs(monkeypatch):
    monkeypatch.setattr(scoped_database, "_get_client", lambda: object())
    monkeypatch.setattr(ScopedDatabase, "get_version", lambda _self: 22)

    assert isinstance(ScopedDatabase(filepath=None, print_sql=False), ScopedDatabase)
    with pytest.raises(ScopedHelperError, match="does not accept a filepath"):
        ScopedDatabase(filepath="/other/database.sqlite")
