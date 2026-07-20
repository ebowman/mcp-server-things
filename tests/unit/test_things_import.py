"""
Unit tests for the things_import lazy-import helper.

Covers: successful lazy import + caching, timeout behavior on a slow
import (with boot marker emission), timeout env-var parsing (default,
override, and the <= 0 "unbounded" case), and graceful recovery when a
previously-timed-out background import completes later.
"""

import io
import sys
import time
import threading

import pytest

import things_mcp.things_import as ti
from things_mcp.things_import import (
    ThingsImportTimeoutError,
    get_things,
)


@pytest.fixture(autouse=True)
def reset_things_import_state(monkeypatch):
    """Reset module-level cache/error state and hide any already-imported
    real 'things' module for the duration of each test.

    Other test modules in the suite do a plain `import things` (or
    `patch('things.xyz')`, which imports it too) at collection/run time,
    which would otherwise populate sys.modules['things'] before these
    tests run -- short-circuiting get_things()'s "already cached" fast
    path and making it impossible to exercise the timeout/slow-import
    behavior under test here.
    """
    orig_module = ti._things_module
    orig_error = ti._import_error
    ti._things_module = None
    ti._import_error = None

    orig_sys_things = sys.modules.pop("things", None)

    yield

    ti._things_module = orig_module
    ti._import_error = orig_error
    if orig_sys_things is not None:
        sys.modules["things"] = orig_sys_things
    else:
        sys.modules.pop("things", None)


class TestSuccessPath:
    """get_things() returns and caches the real module on success."""

    def test_returns_real_module_and_caches(self):
        module1 = get_things()
        assert hasattr(module1, "todos")

        module2 = get_things()
        assert module2 is module1


class TestTimeout:
    """get_things() bounds a stalled import with a timeout."""

    def test_slow_import_raises_timeout_and_emits_boot_marker(self, monkeypatch):
        def slow_import(name):
            time.sleep(0.3)
            return object()

        monkeypatch.setattr(ti.importlib, "import_module", slow_import)

        fake_stderr = io.StringIO()
        monkeypatch.setattr(sys, "stderr", fake_stderr)

        with pytest.raises(ThingsImportTimeoutError, match="Group Containers"):
            get_things(timeout=0.05)

        output = fake_stderr.getvalue()
        assert "things-import-timeout" in output

    def test_import_thread_error_is_reraised(self, monkeypatch):
        def failing_import(name):
            raise ImportError("boom")

        monkeypatch.setattr(ti.importlib, "import_module", failing_import)

        with pytest.raises(ImportError, match="boom"):
            get_things(timeout=1.0)


class TestEnvParsing:
    """Timeout resolution: explicit param, env var, default, and <= 0 unbounded."""

    def _patch_fast_import(self, monkeypatch):
        monkeypatch.setattr(
            ti.importlib, "import_module", lambda name: object()
        )

    def _capture_join_timeout(self, monkeypatch):
        captured = {}
        original_join = threading.Thread.join

        def fake_join(self, timeout=None):
            captured["timeout"] = timeout
            return original_join(self, timeout)

        monkeypatch.setattr(threading.Thread, "join", fake_join)
        return captured

    def test_default_timeout_is_ten_seconds(self, monkeypatch):
        self._patch_fast_import(monkeypatch)
        monkeypatch.delenv(ti._TIMEOUT_ENV_VAR, raising=False)
        captured = self._capture_join_timeout(monkeypatch)

        get_things()

        assert captured["timeout"] == 10.0

    def test_env_override_is_honored(self, monkeypatch):
        self._patch_fast_import(monkeypatch)
        monkeypatch.setenv(ti._TIMEOUT_ENV_VAR, "2.5")
        captured = self._capture_join_timeout(monkeypatch)

        get_things()

        assert captured["timeout"] == 2.5

    def test_env_zero_or_negative_is_unbounded(self, monkeypatch):
        self._patch_fast_import(monkeypatch)
        monkeypatch.setenv(ti._TIMEOUT_ENV_VAR, "0")
        captured = self._capture_join_timeout(monkeypatch)

        get_things()

        assert captured["timeout"] is None

    def test_explicit_timeout_overrides_env(self, monkeypatch):
        self._patch_fast_import(monkeypatch)
        monkeypatch.setenv(ti._TIMEOUT_ENV_VAR, "99")
        captured = self._capture_join_timeout(monkeypatch)

        get_things(timeout=3.0)

        assert captured["timeout"] == 3.0


class TestLateCompletion:
    """A background import that completes after a prior timeout is picked up gracefully."""

    def test_late_completion_is_returned_by_subsequent_call(self, monkeypatch):
        sentinel_module = object()

        def delayed_import(name):
            time.sleep(0.15)
            sys.modules["things"] = sentinel_module
            return sentinel_module

        monkeypatch.setattr(ti.importlib, "import_module", delayed_import)

        with pytest.raises(ThingsImportTimeoutError):
            get_things(timeout=0.02)

        # Let the background daemon thread finish and populate sys.modules.
        time.sleep(0.3)

        result = get_things()
        assert result is sentinel_module
