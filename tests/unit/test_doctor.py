"""Unit tests for the `doctor` diagnostic subcommand (things_mcp.doctor).

Covers each check's PASS path and its distinctive FAIL/WARN/INFO mapping,
exit-code logic (any FAIL -> 1, WARN/INFO-only -> 0), --json shape, and CLI
argv routing in main().
"""

import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from things_mcp import doctor


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
        fake_things = SimpleNamespace(todos=lambda status=None: [1, 2, 3])
        with patch("things_mcp.things_import.get_things", return_value=fake_things):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_PASS
        assert "3" in result.detail

    def test_fail_on_unable_to_open_database_file(self):
        def _raise(**kwargs):
            raise Exception("sqlite3.OperationalError: unable to open database file")

        fake_things = SimpleNamespace(todos=_raise)
        with patch("things_mcp.things_import.get_things", return_value=fake_things):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_FAIL
        assert "full disk access" in result.hint.lower()

    def test_fail_on_other_exception(self):
        def _raise(**kwargs):
            raise RuntimeError("boom")

        fake_things = SimpleNamespace(todos=_raise)
        with patch("things_mcp.things_import.get_things", return_value=fake_things):
            result = doctor.check_database_readable(timeout=2.0)
        assert result.status == doctor.STATUS_FAIL
        assert "boom" in result.detail

    def test_warn_on_timeout(self):
        import time

        def _slow(**kwargs):
            time.sleep(1.0)
            return []

        fake_things = SimpleNamespace(todos=_slow)
        with patch("things_mcp.things_import.get_things", return_value=fake_things):
            result = doctor.check_database_readable(timeout=0.05)
        assert result.status == doctor.STATUS_WARN


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
# check_auth_token
# ---------------------------------------------------------------------------

class TestCheckAuthToken:
    def test_info_when_present(self, tmp_path):
        token_file = tmp_path / ".things-auth"
        token_file.write_text("abc123")
        with patch("things_mcp.doctor._auth_token_paths", return_value=[token_file]):
            result = doctor.check_auth_token()
        assert result.status == doctor.STATUS_INFO
        assert "configured" in result.detail

    def test_info_when_absent_never_fail_or_warn(self, tmp_path):
        missing = tmp_path / ".things-auth"
        with patch("things_mcp.doctor._auth_token_paths", return_value=[missing]):
            result = doctor.check_auth_token()
        assert result.status == doctor.STATUS_INFO
        assert result.hint  # has a hint even though INFO


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
# run_doctor (drives run_all_checks + rendering + exit code)
# ---------------------------------------------------------------------------

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
