"""Unit tests for the `doctor` diagnostic subcommand (things_mcp.doctor).

Covers each check's PASS path and its distinctive FAIL/WARN/INFO mapping,
exit-code logic (any FAIL -> 1, WARN/INFO-only -> 0), --json shape, and CLI
argv routing in main().
"""

import errno
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, mock_open, patch

import pytest

from things_mcp import doctor


def _fake_things(todos_fn):
    """Build a fake `things` module stub with a `database.Database().filepath`."""
    return SimpleNamespace(
        todos=todos_fn,
        database=SimpleNamespace(
            Database=lambda: SimpleNamespace(filepath="/fake/things.sqlite")
        ),
    )


# ---------------------------------------------------------------------------
# check_things_installed
# ---------------------------------------------------------------------------

class TestCheckThingsInstalled:
    def test_pass_when_app_bundle_exists(self, monkeypatch):
        monkeypatch.setattr(doctor.Path, "exists", lambda self: True)
        result = doctor.check_things_installed()
        assert result.status == doctor.STATUS_PASS

    def test_fail_when_not_found_anywhere(self, monkeypatch):
        monkeypatch.setattr(doctor.Path, "exists", lambda self: False)
        mock_result = MagicMock(stdout="")
        with patch("things_mcp.doctor.subprocess.run", return_value=mock_result):
            result = doctor.check_things_installed()
        assert result.status == doctor.STATUS_FAIL
        assert "culturedcode" in result.hint.lower() or "app store" in result.hint.lower()

    def test_pass_via_mdfind_fallback(self, monkeypatch):
        monkeypatch.setattr(doctor.Path, "exists", lambda self: False)
        mock_result = MagicMock(stdout="/Applications/Things3.app\n")
        with patch("things_mcp.doctor.subprocess.run", return_value=mock_result):
            result = doctor.check_things_installed()
        assert result.status == doctor.STATUS_PASS

    def test_fail_on_mdfind_timeout(self, monkeypatch):
        monkeypatch.setattr(doctor.Path, "exists", lambda self: False)
        with patch(
            "things_mcp.doctor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="mdfind", timeout=10),
        ):
            result = doctor.check_things_installed()
        assert result.status == doctor.STATUS_FAIL


# ---------------------------------------------------------------------------
# check_things_running
# ---------------------------------------------------------------------------

class TestCheckThingsRunning:
    def test_pass_when_running(self):
        mock_result = MagicMock(stdout="true\n", stderr="")
        with patch("things_mcp.doctor._run_osascript", return_value=mock_result):
            result = doctor.check_things_running()
        assert result.status == doctor.STATUS_PASS

    def test_warn_when_not_running(self):
        mock_result = MagicMock(stdout="false\n", stderr="")
        with patch("things_mcp.doctor._run_osascript", return_value=mock_result):
            result = doctor.check_things_running()
        assert result.status == doctor.STATUS_WARN
        assert "open things 3" in result.hint.lower()

    def test_warn_on_timeout(self):
        with patch(
            "things_mcp.doctor._run_osascript",
            side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=10),
        ):
            result = doctor.check_things_running()
        assert result.status == doctor.STATUS_WARN


# ---------------------------------------------------------------------------
# check_automation_permission
# ---------------------------------------------------------------------------

class TestCheckAutomationPermission:
    def test_pass_on_success(self):
        mock_result = MagicMock(returncode=0, stdout="Things3\n", stderr="")
        with patch("things_mcp.doctor._run_osascript", return_value=mock_result):
            result = doctor.check_automation_permission()
        assert result.status == doctor.STATUS_PASS

    def test_fail_on_dash_1743_not_authorized(self):
        mock_result = MagicMock(
            returncode=1,
            stdout="",
            stderr="execution error: Not authorized to send Apple events to Things3. (-1743)",
        )
        with patch("things_mcp.doctor._run_osascript", return_value=mock_result):
            result = doctor.check_automation_permission()
        assert result.status == doctor.STATUS_FAIL
        assert "automation" in result.hint.lower()
        assert "privacy" in result.hint.lower() or "security" in result.hint.lower()

    def test_warn_when_app_not_running_error(self):
        mock_result = MagicMock(
            returncode=1,
            stdout="",
            stderr="execution error: Things3 got an error: Application isn't running. (-600)",
        )
        with patch("things_mcp.doctor._run_osascript", return_value=mock_result):
            result = doctor.check_automation_permission()
        assert result.status == doctor.STATUS_WARN

    def test_fail_on_other_error_includes_raw_stderr(self):
        mock_result = MagicMock(returncode=1, stdout="", stderr="something else broke")
        with patch("things_mcp.doctor._run_osascript", return_value=mock_result):
            result = doctor.check_automation_permission()
        assert result.status == doctor.STATUS_FAIL
        assert "something else broke" in result.detail

    def test_fail_on_timeout(self):
        with patch(
            "things_mcp.doctor._run_osascript",
            side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=10),
        ):
            result = doctor.check_automation_permission()
        assert result.status == doctor.STATUS_FAIL


# ---------------------------------------------------------------------------
# check_database_readable
# ---------------------------------------------------------------------------

class TestCheckDatabaseReadable:
    def test_pass_returns_count(self):
        fake_things = _fake_things(lambda status=None: [1, 2, 3])
        with patch("things_mcp.things_import.get_things", return_value=fake_things), \
                patch("things_mcp.doctor.open", mock_open(read_data=b""), create=True):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_PASS
        assert "3" in result.detail

    def test_fail_on_unable_to_open_database_file(self):
        def _raise(**kwargs):
            raise Exception("sqlite3.OperationalError: unable to open database file")

        fake_things = _fake_things(_raise)
        with patch("things_mcp.things_import.get_things", return_value=fake_things), \
                patch("things_mcp.doctor.open", mock_open(read_data=b""), create=True):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_FAIL
        assert "full disk access" in result.hint.lower()

    def test_fail_on_other_exception(self):
        def _raise(**kwargs):
            raise RuntimeError("boom")

        fake_things = _fake_things(_raise)
        with patch("things_mcp.things_import.get_things", return_value=fake_things), \
                patch("things_mcp.doctor.open", mock_open(read_data=b""), create=True):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_FAIL
        assert "boom" in result.detail

    def test_warn_on_timeout(self):
        import time

        def _slow(**kwargs):
            time.sleep(1.0)
            return []

        fake_things = _fake_things(_slow)
        with patch("things_mcp.things_import.get_things", return_value=fake_things), \
                patch("things_mcp.doctor.open", mock_open(read_data=b""), create=True):
            result = doctor.check_database_readable(timeout=0.05)
        assert result.status == doctor.STATUS_WARN

    def test_fail_on_preopen_permission_error_eperm(self):
        fake_things = _fake_things(lambda status=None: [])
        err = PermissionError()
        err.errno = errno.EPERM
        with patch("things_mcp.things_import.get_things", return_value=fake_things), \
                patch("things_mcp.doctor.open", side_effect=err, create=True):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_FAIL
        assert "tcc" in result.detail.lower() or "privacy" in result.detail.lower()
        assert "full disk access" in result.hint.lower()

    def test_fail_on_preopen_permission_error_eacces(self):
        fake_things = _fake_things(lambda status=None: [])
        err = PermissionError()
        err.errno = errno.EACCES
        with patch("things_mcp.things_import.get_things", return_value=fake_things), \
                patch("things_mcp.doctor.open", side_effect=err, create=True):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_FAIL
        assert "full disk access" in result.hint.lower()

    def test_fail_on_preopen_file_not_found(self):
        fake_things = _fake_things(lambda status=None: [])
        with patch("things_mcp.things_import.get_things", return_value=fake_things), \
                patch("things_mcp.doctor.open", side_effect=FileNotFoundError(), create=True):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_FAIL
        assert "not found" in result.detail.lower()

    def test_fail_when_database_filepath_lookup_itself_raises(self):
        """Database().filepath raising must not produce an unbound-name NameError."""

        def _raise_filepath():
            raise FileNotFoundError("no such Things database")

        fake_things = SimpleNamespace(
            todos=lambda status=None: [],
            database=SimpleNamespace(Database=_raise_filepath),
        )
        with patch("things_mcp.things_import.get_things", return_value=fake_things):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_FAIL
        assert "NameError" not in result.detail
        assert "could not be resolved" in result.detail.lower()


# ---------------------------------------------------------------------------
# check_uv_installed
# ---------------------------------------------------------------------------

class TestCheckUvInstalled:
    def test_pass_when_found(self):
        with patch("things_mcp.doctor.shutil.which", return_value="/opt/homebrew/bin/uvx"):
            result = doctor.check_uv_installed()
        assert result.status == doctor.STATUS_PASS

    def test_warn_when_missing_never_fail(self):
        with patch("things_mcp.doctor.shutil.which", return_value=None):
            result = doctor.check_uv_installed()
        assert result.status == doctor.STATUS_WARN
        assert result.status != doctor.STATUS_FAIL
        assert "brew install uv" in result.hint


# ---------------------------------------------------------------------------
# check_python_architecture
# ---------------------------------------------------------------------------

class TestCheckPythonArchitecture:
    def test_pass_when_arm64_interpreter(self, monkeypatch):
        monkeypatch.setattr(doctor.platform, "machine", lambda: "arm64")
        with patch("things_mcp.doctor.subprocess.run") as mock_run:
            result = doctor.check_python_architecture()
        assert result.status == doctor.STATUS_PASS
        # Fast path: arm64 interpreter implies Apple Silicon without shelling out.
        mock_run.assert_not_called()

    def test_warn_when_x86_64_interpreter_on_apple_silicon(self, monkeypatch):
        monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
        mock_result = MagicMock(stdout="1\n")
        with patch("things_mcp.doctor.subprocess.run", return_value=mock_result):
            result = doctor.check_python_architecture()
        assert result.status == doctor.STATUS_WARN
        assert "rosetta" in result.detail.lower()
        assert "arm64" in result.hint.lower()
        assert "uvx" in result.hint.lower()

    def test_pass_when_x86_64_interpreter_on_intel_sysctl_returns_zero(self, monkeypatch):
        monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
        mock_result = MagicMock(stdout="0\n")
        with patch("things_mcp.doctor.subprocess.run", return_value=mock_result):
            result = doctor.check_python_architecture()
        assert result.status == doctor.STATUS_PASS
        assert "wheel" in result.detail.lower()

    def test_pass_when_x86_64_interpreter_and_sysctl_fails(self, monkeypatch):
        monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
        with patch(
            "things_mcp.doctor.subprocess.run",
            side_effect=FileNotFoundError("sysctl not found"),
        ):
            result = doctor.check_python_architecture()
        assert result.status == doctor.STATUS_PASS
        assert "wheel" in result.detail.lower()

    def test_no_exception_when_sysctl_raises(self, monkeypatch):
        monkeypatch.setattr(doctor.platform, "machine", lambda: "x86_64")
        with patch(
            "things_mcp.doctor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="sysctl", timeout=10),
        ):
            result = doctor.check_python_architecture()
        assert result.status in (doctor.STATUS_PASS, doctor.STATUS_WARN)
        assert result.status != doctor.STATUS_FAIL


# ---------------------------------------------------------------------------
# check_interpreter_identity
# ---------------------------------------------------------------------------

class TestCheckInterpreterIdentity:
    def test_classifies_uv_managed(self, monkeypatch):
        uv_path = "/Users/x/.local/share/uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12"
        monkeypatch.setattr(doctor.sys, "executable", uv_path)
        monkeypatch.setattr(doctor.os.path, "realpath", lambda p: uv_path)
        monkeypatch.setattr(doctor.sys, "prefix", "/a")
        monkeypatch.setattr(doctor.sys, "base_prefix", "/a")
        result = doctor.check_interpreter_identity()
        assert result.status == doctor.STATUS_WARN
        assert "uv-managed" in result.detail
        assert uv_path in result.detail
        assert "Grant Full Disk Access to" in result.detail
        assert "patch version" in result.detail.lower()

    def test_classifies_venv(self, monkeypatch):
        venv_path = "/Users/x/project/venv/bin/python3.11"
        monkeypatch.setattr(doctor.sys, "executable", venv_path)
        monkeypatch.setattr(doctor.os.path, "realpath", lambda p: venv_path)
        monkeypatch.setattr(doctor.sys, "prefix", "/Users/x/project/venv")
        monkeypatch.setattr(doctor.sys, "base_prefix", "/usr")
        result = doctor.check_interpreter_identity()
        assert result.status == doctor.STATUS_PASS
        assert "venv" in result.detail

    def test_classifies_framework(self, monkeypatch):
        fw_path = (
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11"
        )
        monkeypatch.setattr(doctor.sys, "executable", fw_path)
        monkeypatch.setattr(doctor.os.path, "realpath", lambda p: fw_path)
        monkeypatch.setattr(doctor.sys, "prefix", "/a")
        monkeypatch.setattr(doctor.sys, "base_prefix", "/a")
        result = doctor.check_interpreter_identity()
        assert result.status == doctor.STATUS_PASS
        assert "framework" in result.detail
        assert "org.python.python" in result.detail
        # hq-gxt.9 reviewer nit: framework realpaths also end in a patch-version
        # segment and hit the same greyed-out picker bug - the drag hint must
        # be included for framework too, not just uv-managed/venv/other.
        assert "drag it from a Finder window" in result.detail

    def test_classifies_other(self, monkeypatch):
        other_path = "/usr/bin/python3"
        monkeypatch.setattr(doctor.sys, "executable", other_path)
        monkeypatch.setattr(doctor.os.path, "realpath", lambda p: other_path)
        monkeypatch.setattr(doctor.sys, "prefix", "/a")
        monkeypatch.setattr(doctor.sys, "base_prefix", "/a")
        result = doctor.check_interpreter_identity()
        assert result.status == doctor.STATUS_PASS
        assert "other" in result.detail


# ---------------------------------------------------------------------------
# check_launch_parent
# ---------------------------------------------------------------------------

class TestCheckLaunchParent:
    def _ps_result(self, ppid, comm):
        return MagicMock(returncode=0, stdout=f"{ppid} {comm}\n")

    def test_warn_when_disclaimer_found(self, monkeypatch):
        monkeypatch.setattr(doctor.os, "getppid", lambda: 100)
        results = [
            self._ps_result(1, "/Applications/Claude.app/Contents/Helpers/disclaimer"),
        ]
        with patch("things_mcp.doctor.subprocess.run", side_effect=results):
            result = doctor.check_launch_parent()
        assert result.status == doctor.STATUS_WARN
        assert "disclaimer" in result.detail

    def test_info_when_not_found(self, monkeypatch):
        monkeypatch.setattr(doctor.os, "getppid", lambda: 100)
        results = [
            self._ps_result(1, "launchd"),
        ]
        with patch("things_mcp.doctor.subprocess.run", side_effect=results):
            result = doctor.check_launch_parent()
        assert result.status == doctor.STATUS_INFO
        assert "launchd" in result.detail

    def test_info_when_ps_fails(self, monkeypatch):
        monkeypatch.setattr(doctor.os, "getppid", lambda: 100)
        with patch(
            "things_mcp.doctor.subprocess.run",
            side_effect=OSError("ps not found"),
        ):
            result = doctor.check_launch_parent()
        assert result.status == doctor.STATUS_INFO


# ---------------------------------------------------------------------------
# check_auth_token
# ---------------------------------------------------------------------------

class TestCheckAuthToken:
    def test_pass_when_present(self, tmp_path):
        token_file = tmp_path / ".things-auth"
        token_file.write_text("abc123")
        with patch("things_mcp.doctor._auth_token_paths", return_value=[token_file]):
            result = doctor.check_auth_token()
        assert result.status == doctor.STATUS_PASS
        assert "configured" in result.detail

    def test_warn_when_absent_never_fail(self, tmp_path):
        missing = tmp_path / ".things-auth"
        with patch("things_mcp.doctor._auth_token_paths", return_value=[missing]):
            result = doctor.check_auth_token()
        assert result.status == doctor.STATUS_WARN
        assert result.status != doctor.STATUS_FAIL
        assert result.hint
        # WARN text must name the tools that need the token (bead hq-f0w.12).
        assert "add_checklist_items" in result.hint
        assert "prepend_checklist_items" in result.hint
        assert "replace_checklist_items" in result.hint

    def test_warn_when_present_but_empty(self, tmp_path):
        token_file = tmp_path / ".things-auth"
        token_file.write_text("   \n")
        with patch("things_mcp.doctor._auth_token_paths", return_value=[token_file]):
            result = doctor.check_auth_token()
        assert result.status == doctor.STATUS_WARN


# ---------------------------------------------------------------------------
# check_claude_desktop_interpreter
# ---------------------------------------------------------------------------

class TestCheckClaudeDesktopInterpreter:
    def _write_config(self, tmp_path, mcp_servers):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(json.dumps({"mcpServers": mcp_servers}))
        return config_path

    def _patch_paths(self, monkeypatch, config_path, tmp_path, extensions_dir=None):
        monkeypatch.setattr(doctor, "_CLAUDE_DESKTOP_CONFIG_PATH", config_path)
        monkeypatch.setattr(
            doctor, "_CLAUDE_EXTENSIONS_DIR", extensions_dir or (tmp_path / "Claude Extensions")
        )

    def test_info_when_config_missing(self, tmp_path, monkeypatch):
        self._patch_paths(monkeypatch, tmp_path / "missing.json", tmp_path)
        result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_INFO
        assert "not found" in result.detail

    def test_info_when_config_absent_and_no_mcpb(self, tmp_path, monkeypatch):
        """Both sources absent -> INFO (distinct from the .mcpb-only-install case,
        which must NOT be masked by config-not-found - bead hq-gxt.11 review fix)."""
        missing_config = tmp_path / "claude_desktop_config.json"
        missing_extensions = tmp_path / "Claude Extensions"
        self._patch_paths(monkeypatch, missing_config, tmp_path, extensions_dir=missing_extensions)
        assert not missing_config.exists()
        assert not missing_extensions.exists()
        result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_INFO
        assert "not found" in result.detail
        assert "no matching .mcpb" in result.detail

    def test_info_when_malformed_json(self, tmp_path, monkeypatch):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text("{not valid json")
        self._patch_paths(monkeypatch, config_path, tmp_path)
        result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_INFO

    def test_info_when_no_things_entry(self, tmp_path, monkeypatch):
        config_path = self._write_config(
            tmp_path, {"other": {"command": "npx", "args": ["-y", "other-mcp"]}}
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)
        result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_INFO
        assert "no 'things_mcp'" in result.detail

    def test_plain_command_mismatch_warns(self, tmp_path, monkeypatch):
        venv_python = tmp_path / "venv" / "bin" / "python"
        venv_python.parent.mkdir(parents=True)
        venv_python.write_text("")
        claude_target = tmp_path / "homebrew_python313"
        claude_target.write_text("")
        own_target = tmp_path / "own_python311"
        own_target.write_text("")

        config_path = self._write_config(
            tmp_path, {"things": {"command": str(venv_python), "args": ["-m", "things_mcp"]}}
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)

        real_realpath = os.path.realpath
        mapping = {str(venv_python): str(claude_target), doctor.sys.executable: str(own_target)}
        monkeypatch.setattr(
            doctor.os.path, "realpath", lambda p: mapping.get(str(p), real_realpath(p))
        )

        result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_WARN
        assert str(claude_target) in result.detail
        assert "grant Full Disk Access to THIS file" in result.detail
        assert str(own_target) in result.hint
        assert "Claude Desktop path" in result.hint

    def test_plain_command_match_passes(self, tmp_path, monkeypatch):
        python_path = tmp_path / "venv" / "bin" / "python"
        python_path.parent.mkdir(parents=True)
        python_path.write_text("")
        shared_target = tmp_path / "shared_interpreter"
        shared_target.write_text("")

        config_path = self._write_config(
            tmp_path, {"things": {"command": str(python_path), "args": ["-m", "things_mcp"]}}
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)

        real_realpath = os.path.realpath
        mapping = {str(python_path): str(shared_target), doctor.sys.executable: str(shared_target)}
        monkeypatch.setattr(
            doctor.os.path, "realpath", lambda p: mapping.get(str(p), real_realpath(p))
        )

        result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_PASS
        assert result.hint == ""

    def test_plain_command_not_found_warns(self, tmp_path, monkeypatch):
        missing = tmp_path / "does_not_exist"
        config_path = self._write_config(
            tmp_path, {"things": {"command": str(missing), "args": ["-m", "things_mcp"]}}
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)
        result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_WARN
        assert "command not found" in result.detail

    def test_uvx_entry_resolved_and_matches(self, tmp_path, monkeypatch):
        config_path = self._write_config(
            tmp_path,
            {
                "things": {
                    "command": "uvx",
                    "args": [
                        "--python-preference",
                        "only-managed",
                        "--python",
                        "3.12",
                        "mcp-server-things",
                    ],
                }
            },
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)

        own = os.path.realpath(sys.executable)
        mock_result = MagicMock(returncode=0, stdout=own + "\n", stderr="")
        with patch("things_mcp.doctor.subprocess.run", return_value=mock_result) as mock_run:
            result = doctor.check_claude_desktop_interpreter()

        assert result.status == doctor.STATUS_PASS
        called_cmd = mock_run.call_args[0][0]
        assert called_cmd[0] == "uvx"
        assert "--python-preference" in called_cmd
        assert "only-managed" in called_cmd
        assert "--python" in called_cmd
        assert "3.12" in called_cmd
        assert "mcp-server-things" not in called_cmd
        assert called_cmd[-2:] == ["-c", doctor._UVX_REALPATH_PROBE_CODE]
        assert "python" in called_cmd

    def test_extract_uvx_python_flags_handles_inline_equals_form(self):
        # bead hq-gxt.11 review fix: --python=3.13 / --python-preference=only-managed
        # must be kept as a single whole token, not silently dropped.
        args = ["--python-preference=only-managed", "--python=3.13", "mcp-server-things"]
        flags = doctor._extract_uvx_python_flags(args)
        assert flags == ["--python-preference=only-managed", "--python=3.13"]

    def test_uvx_entry_inline_equals_flags_preserved_in_probe_command(self, tmp_path, monkeypatch):
        config_path = self._write_config(
            tmp_path,
            {
                "things": {
                    "command": "uvx",
                    "args": ["--python-preference=only-managed", "--python=3.13", "mcp-server-things"],
                }
            },
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)

        own = os.path.realpath(sys.executable)
        mock_result = MagicMock(returncode=0, stdout=own + "\n", stderr="")
        with patch("things_mcp.doctor.subprocess.run", return_value=mock_result) as mock_run:
            result = doctor.check_claude_desktop_interpreter()

        assert result.status == doctor.STATUS_PASS
        called_cmd = mock_run.call_args[0][0]
        assert "--python-preference=only-managed" in called_cmd
        assert "--python=3.13" in called_cmd
        assert "mcp-server-things" not in called_cmd

    def test_uvx_entry_mismatch_warns(self, tmp_path, monkeypatch):
        config_path = self._write_config(
            tmp_path, {"things": {"command": "uvx", "args": ["mcp-server-things"]}}
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)

        mock_result = MagicMock(returncode=0, stdout="/opt/homebrew/some/python3.13\n", stderr="")
        with patch("things_mcp.doctor.subprocess.run", return_value=mock_result):
            result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_WARN
        assert "/opt/homebrew/some/python3.13" in result.detail

    def test_uvx_probe_timeout_is_info_with_manual_command(self, tmp_path, monkeypatch):
        config_path = self._write_config(
            tmp_path, {"things": {"command": "uvx", "args": ["mcp-server-things"]}}
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)

        with patch(
            "things_mcp.doctor.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="uvx", timeout=30),
        ):
            result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_INFO
        assert "uvx" in result.detail
        assert "python -c" in result.detail

    def test_uvx_probe_failure_is_info(self, tmp_path, monkeypatch):
        config_path = self._write_config(
            tmp_path, {"things": {"command": "uvx", "args": ["mcp-server-things"]}}
        )
        self._patch_paths(monkeypatch, config_path, tmp_path)

        with patch("things_mcp.doctor.subprocess.run", side_effect=OSError("uvx not found")):
            result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_INFO

    def test_mcpb_manifest_entry_detected(self, tmp_path, monkeypatch):
        # Deliberately no claude_desktop_config.json at all (.mcpb-only install,
        # bead hq-gxt.11 review fix) - must not be masked by config-not-found.
        config_path = tmp_path / "claude_desktop_config.json_does_not_exist"
        ext_dir = tmp_path / "Claude Extensions" / "mcp-server-things-abc123"
        ext_dir.mkdir(parents=True)
        manifest = {
            "name": "mcp-server-things",
            "server": {"mcp_config": {"command": "uvx", "args": ["mcp-server-things"]}},
        }
        (ext_dir / "manifest.json").write_text(json.dumps(manifest))
        self._patch_paths(monkeypatch, config_path, tmp_path, extensions_dir=tmp_path / "Claude Extensions")

        own = os.path.realpath(sys.executable)
        mock_result = MagicMock(returncode=0, stdout=own + "\n", stderr="")
        with patch("things_mcp.doctor.subprocess.run", return_value=mock_result):
            result = doctor.check_claude_desktop_interpreter()
        assert result.status == doctor.STATUS_PASS
        assert "manifest.json" in result.detail


# ---------------------------------------------------------------------------
# check_full_disk_access_effective
# ---------------------------------------------------------------------------

class TestCheckFullDiskAccessEffective:
    def test_pass_when_readable(self, tmp_path, monkeypatch):
        tcc_db = tmp_path / "TCC.db"
        tcc_db.write_bytes(b"0123456789abcdef")
        monkeypatch.setattr(doctor, "_TCC_DB_PATH", tcc_db)
        result = doctor.check_full_disk_access_effective()
        assert result.status == doctor.STATUS_PASS
        assert "Full Disk Access" in result.detail

    def test_warn_on_permission_error(self, monkeypatch):
        monkeypatch.setattr(doctor, "_TCC_DB_PATH", Path("/fake/TCC.db"))
        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = doctor.check_full_disk_access_effective()
        assert result.status == doctor.STATUS_WARN
        assert "doctor process" in result.hint

    def test_info_when_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor, "_TCC_DB_PATH", tmp_path / "missing.db")
        result = doctor.check_full_disk_access_effective()
        assert result.status == doctor.STATUS_INFO


# ---------------------------------------------------------------------------
# check_environment
# ---------------------------------------------------------------------------

class TestCheckEnvironment:
    def test_always_info(self):
        result = doctor.check_environment()
        assert result.status == doctor.STATUS_INFO
        assert "python=" in result.detail

    def test_unknown_when_things_not_in_sys_modules_and_no_import_attempted(self, monkeypatch):
        # Simulate the "import still stalled/not completed" case: 'things' is
        # absent from sys.modules. Guard that check_environment does NOT
        # attempt to import it itself (that bare import is exactly the hang
        # this check exists to avoid) by making any such import explode.
        monkeypatch.delitem(sys.modules, "things", raising=False)

        real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

        def _guarded_import(name, *args, **kwargs):
            if name == "things" or name.startswith("things."):
                raise AssertionError("check_environment must not import 'things'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", _guarded_import)

        result = doctor.check_environment()

        assert result.status == doctor.STATUS_INFO
        assert "things=unknown (import not completed)" in result.detail

    def test_version_from_sys_modules_when_already_imported(self, monkeypatch):
        fake_things = SimpleNamespace(__version__="9.9.9")
        monkeypatch.setitem(sys.modules, "things", fake_things)

        result = doctor.check_environment()

        assert result.status == doctor.STATUS_INFO
        assert "things=9.9.9" in result.detail


# ---------------------------------------------------------------------------
# has_failure / exit code logic
# ---------------------------------------------------------------------------

class TestHasFailure:
    def test_true_when_any_fail(self):
        results = [
            doctor.CheckResult("a", doctor.STATUS_PASS),
            doctor.CheckResult("b", doctor.STATUS_FAIL),
            doctor.CheckResult("c", doctor.STATUS_WARN),
        ]
        assert doctor.has_failure(results) is True

    def test_false_when_only_warn_and_info(self):
        results = [
            doctor.CheckResult("a", doctor.STATUS_PASS),
            doctor.CheckResult("b", doctor.STATUS_WARN),
            doctor.CheckResult("c", doctor.STATUS_INFO),
        ]
        assert doctor.has_failure(results) is False

    def test_false_when_all_pass(self):
        results = [doctor.CheckResult("a", doctor.STATUS_PASS)]
        assert doctor.has_failure(results) is False


# ---------------------------------------------------------------------------
# run_all_checks - new checks wired in (text and --json both derive from this)
# ---------------------------------------------------------------------------

class TestRunAllChecksIncludesNewChecks:
    def test_interpreter_identity_and_launch_parent_present_and_ordered(self, tmp_path, monkeypatch):
        # Keep check_claude_desktop_interpreter/check_full_disk_access_effective
        # unmocked (like Interpreter identity/Launch parent above) so their names
        # are asserted for real, but point them at nonexistent tmp paths so this
        # test never reads a real ~/Library config or spawns a real uvx probe on
        # another machine (bead hq-gxt.11 review fix).
        monkeypatch.setattr(doctor, "_CLAUDE_DESKTOP_CONFIG_PATH", tmp_path / "claude_desktop_config.json")
        monkeypatch.setattr(doctor, "_CLAUDE_EXTENSIONS_DIR", tmp_path / "Claude Extensions")
        monkeypatch.setattr(doctor, "_TCC_DB_PATH", tmp_path / "TCC.db")
        stub_result = doctor.CheckResult("stub", doctor.STATUS_PASS)
        with patch("things_mcp.doctor.check_things_installed", return_value=stub_result), \
                patch("things_mcp.doctor.check_things_running", return_value=stub_result), \
                patch("things_mcp.doctor.check_automation_permission", return_value=stub_result), \
                patch("things_mcp.doctor.check_database_readable", return_value=stub_result), \
                patch("things_mcp.doctor.check_uv_installed", return_value=stub_result), \
                patch("things_mcp.doctor.check_auth_token", return_value=stub_result), \
                patch("things_mcp.doctor.check_environment", return_value=stub_result):
            names = [r.name for r in doctor.run_all_checks()]
        assert "Interpreter identity" in names
        assert "Launch parent" in names
        assert "Claude Desktop interpreter" in names
        assert "Full Disk Access effective (this process)" in names
        # Ordered immediately after "Python architecture", per the bead.
        assert names.index("Interpreter identity") == names.index("Python architecture") + 1
        assert names.index("Launch parent") == names.index("Interpreter identity") + 1
        assert names.index("Claude Desktop interpreter") == names.index("Launch parent") + 1
        assert names.index("Full Disk Access effective (this process)") == names.index("Claude Desktop interpreter") + 1

    def test_interpreter_identity_present_in_json_output(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setattr(doctor, "_CLAUDE_DESKTOP_CONFIG_PATH", tmp_path / "claude_desktop_config.json")
        monkeypatch.setattr(doctor, "_CLAUDE_EXTENSIONS_DIR", tmp_path / "Claude Extensions")
        monkeypatch.setattr(doctor, "_TCC_DB_PATH", tmp_path / "TCC.db")
        stub_result = doctor.CheckResult("stub", doctor.STATUS_PASS)
        with patch("things_mcp.doctor.check_things_installed", return_value=stub_result), \
                patch("things_mcp.doctor.check_things_running", return_value=stub_result), \
                patch("things_mcp.doctor.check_automation_permission", return_value=stub_result), \
                patch("things_mcp.doctor.check_database_readable", return_value=stub_result), \
                patch("things_mcp.doctor.check_uv_installed", return_value=stub_result), \
                patch("things_mcp.doctor.check_auth_token", return_value=stub_result), \
                patch("things_mcp.doctor.check_environment", return_value=stub_result):
            doctor.run_doctor(json_output=True)
        payload = json.loads(capsys.readouterr().out)
        names = [c["name"] for c in payload["checks"]]
        assert "Interpreter identity" in names
        assert "Launch parent" in names
        assert "Claude Desktop interpreter" in names
        assert "Full Disk Access effective (this process)" in names


class TestRunDoctor:
    def _patch_all_checks(self, statuses):
        """Patch run_all_checks to return CheckResults with the given statuses."""
        results = [
            doctor.CheckResult(f"check-{i}", status, detail="d")
            for i, status in enumerate(statuses)
        ]
        return patch("things_mcp.doctor.run_all_checks", return_value=results)

    def test_exit_code_1_on_any_fail(self, capsys):
        with self._patch_all_checks([doctor.STATUS_PASS, doctor.STATUS_FAIL, doctor.STATUS_WARN]):
            code = doctor.run_doctor()
        assert code == 1

    def test_exit_code_0_when_warn_info_only(self, capsys):
        with self._patch_all_checks([doctor.STATUS_PASS, doctor.STATUS_WARN, doctor.STATUS_INFO]):
            code = doctor.run_doctor()
        assert code == 0

    def test_json_output_shape(self, capsys):
        with self._patch_all_checks([doctor.STATUS_PASS, doctor.STATUS_FAIL]):
            code = doctor.run_doctor(json_output=True)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is False
        assert isinstance(payload["checks"], list)
        assert len(payload["checks"]) == 2
        for check in payload["checks"]:
            assert set(check.keys()) == {"name", "status", "detail", "hint"}

    def test_json_ok_true_when_no_fail(self, capsys):
        with self._patch_all_checks([doctor.STATUS_PASS, doctor.STATUS_WARN]):
            doctor.run_doctor(json_output=True)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["ok"] is True

    def test_table_output_includes_hint_for_non_pass(self, capsys):
        results = [
            doctor.CheckResult("Thing", doctor.STATUS_FAIL, detail="broke", hint="fix it"),
        ]
        with patch("things_mcp.doctor.run_all_checks", return_value=results):
            doctor.run_doctor()
        captured = capsys.readouterr()
        assert "fix it" in captured.out
        assert "broke" in captured.out


# ---------------------------------------------------------------------------
# CLI argv routing (things_mcp.main)
# ---------------------------------------------------------------------------

class TestMainDoctorDispatch:
    def test_doctor_subcommand_calls_run_doctor(self, monkeypatch):
        from things_mcp import main as main_module

        monkeypatch.setattr(sys, "argv", ["mcp-server-things", "doctor"])
        with patch("things_mcp.doctor.run_doctor", return_value=0) as mock_run_doctor:
            code = main_module.main()
        mock_run_doctor.assert_called_once_with(json_output=False)
        assert code == 0

    def test_doctor_json_flag_passed_through(self, monkeypatch):
        from things_mcp import main as main_module

        monkeypatch.setattr(sys, "argv", ["mcp-server-things", "doctor", "--json"])
        with patch("things_mcp.doctor.run_doctor", return_value=1) as mock_run_doctor:
            code = main_module.main()
        mock_run_doctor.assert_called_once_with(json_output=True)
        assert code == 1

    def test_no_subcommand_does_not_call_doctor(self, monkeypatch):
        """Existing flags (e.g. --version) must keep working without invoking doctor."""
        from things_mcp import main as main_module

        monkeypatch.setattr(sys, "argv", ["mcp-server-things", "--version"])
        with patch("things_mcp.doctor.run_doctor") as mock_run_doctor:
            code = main_module.main()
        mock_run_doctor.assert_not_called()
        assert code == 0
