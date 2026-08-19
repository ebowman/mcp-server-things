"""Unit tests for the `config` CLI subcommand (things_mcp.client_config + CLI routing).

Covers pure config-snippet generation for each client x via combo, the
filesystem-mutating --write path (fresh file, preserving other servers,
no-op on identical entry, refusal without --force, --force replacing with a
backup, and invalid JSON refusal), and CLI argv routing in main().
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from things_mcp import client_config

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"


# ---------------------------------------------------------------------------
# build_server_config / snippet formatting per client x via combo
# ---------------------------------------------------------------------------

class TestBuildServerConfig:
    def test_uvx(self):
        assert client_config.build_server_config("uvx") == {
            "command": "uvx",
            "args": list(client_config.UVX_ARGS),
        }

    def test_current_python(self):
        cfg = client_config.build_server_config("current-python")
        assert cfg == {"command": sys.executable, "args": ["-m", "things_mcp"]}

    def test_unknown_via_raises(self):
        with pytest.raises(ValueError):
            client_config.build_server_config("bogus")


class TestFormatClaudeDesktopSnippet:
    def test_uvx(self):
        snippet = client_config.format_claude_desktop_snippet(via="uvx")
        data = json.loads(snippet)
        assert data == {
            "mcpServers": {
                "things": {"command": "uvx", "args": list(client_config.UVX_ARGS)}
            }
        }

    def test_current_python(self):
        snippet = client_config.format_claude_desktop_snippet(via="current-python")
        data = json.loads(snippet)
        assert data == {
            "mcpServers": {
                "things": {"command": sys.executable, "args": ["-m", "things_mcp"]}
            }
        }


class TestFormatClaudeCodeCommands:
    def test_uvx(self):
        out = client_config.format_claude_code_commands(via="uvx")
        expected_json = json.dumps(
            {"command": "uvx", "args": list(client_config.UVX_ARGS)},
            separators=(",", ":"),
        )
        lines = out.splitlines()
        assert lines == [
            f"claude mcp add-json things '{expected_json}'",
            f"claude mcp add-json things '{expected_json}' -s user",
        ]

    def test_current_python(self):
        out = client_config.format_claude_code_commands(via="current-python")
        expected_json = json.dumps(
            {"command": sys.executable, "args": ["-m", "things_mcp"]},
            separators=(",", ":"),
        )
        lines = out.splitlines()
        assert lines[0] == f"claude mcp add-json things '{expected_json}'"
        assert lines[1] == f"claude mcp add-json things '{expected_json}' -s user"


class TestFormatGenericSnippet:
    def test_uvx(self):
        snippet = client_config.format_generic_snippet(via="uvx")
        assert json.loads(snippet) == {"command": "uvx", "args": list(client_config.UVX_ARGS)}

    def test_current_python(self):
        snippet = client_config.format_generic_snippet(via="current-python")
        assert json.loads(snippet) == {
            "command": sys.executable,
            "args": ["-m", "things_mcp"],
        }


class TestCurrentPythonSourceTreeCaveat:
    def test_returns_none_when_not_under_src(self, monkeypatch):
        fake_file = "/usr/lib/python3.12/site-packages/things_mcp/client_config.py"
        monkeypatch.setattr(client_config, "__file__", fake_file)
        assert client_config.current_python_source_tree_caveat() is None

    def test_returns_note_when_under_src(self, monkeypatch):
        fake_file = "/Users/example/mcp-server-things/src/things_mcp/client_config.py"
        monkeypatch.setattr(client_config, "__file__", fake_file)
        note = client_config.current_python_source_tree_caveat()
        assert note is not None
        assert "PYTHONPATH" in note


# ---------------------------------------------------------------------------
# write_claude_desktop_config
# ---------------------------------------------------------------------------

class TestWriteClaudeDesktopConfig:
    def test_fresh_file(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        result = client_config.write_claude_desktop_config(
            via="uvx", config_path=config_path
        )

        assert result.changed is True
        assert result.backup_path is None  # nothing to back up - file didn't exist
        assert result.old_server_config is None
        assert result.new_server_config == {
            "command": "uvx",
            "args": list(client_config.UVX_ARGS),
        }

        on_disk = json.loads(config_path.read_text())
        assert on_disk == {
            "mcpServers": {
                "things": {"command": "uvx", "args": list(client_config.UVX_ARGS)}
            }
        }
        assert config_path.read_text().endswith("\n")

    def test_preserves_other_servers(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        initial = {
            "mcpServers": {
                "other-server": {"command": "foo", "args": ["bar"]}
            },
            "someOtherTopLevelKey": "keep-me",
        }
        config_path.write_text(json.dumps(initial, indent=2))

        result = client_config.write_claude_desktop_config(
            via="uvx", config_path=config_path
        )

        assert result.changed is True
        on_disk = json.loads(config_path.read_text())
        assert on_disk["mcpServers"]["other-server"] == {"command": "foo", "args": ["bar"]}
        assert on_disk["mcpServers"]["things"] == {
            "command": "uvx",
            "args": list(client_config.UVX_ARGS),
        }
        assert on_disk["someOtherTopLevelKey"] == "keep-me"

        # A backup should have been made since the file pre-existed.
        assert result.backup_path is not None
        assert result.backup_path.exists()
        backup_data = json.loads(result.backup_path.read_text())
        assert backup_data == initial

    def test_noop_when_identical_entry_exists(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        initial = {
            "mcpServers": {
                "things": {"command": "uvx", "args": list(client_config.UVX_ARGS)}
            }
        }
        config_path.write_text(json.dumps(initial, indent=2))
        before_mtime = config_path.stat().st_mtime_ns
        before_text = config_path.read_text()

        result = client_config.write_claude_desktop_config(
            via="uvx", config_path=config_path
        )

        assert result.changed is False
        assert result.backup_path is None  # no-op must not write or back up
        # File must be untouched.
        assert config_path.read_text() == before_text
        assert config_path.stat().st_mtime_ns == before_mtime
        # No backup files created alongside it.
        backups = list(tmp_path.glob("claude_desktop_config.json.bak.*"))
        assert backups == []

    def test_refuses_differing_entry_without_force(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        initial = {
            "mcpServers": {"things": {"command": "old-command", "args": ["old"]}}
        }
        config_path.write_text(json.dumps(initial, indent=2))
        before_text = config_path.read_text()

        with pytest.raises(client_config.ClientConfigError):
            client_config.write_claude_desktop_config(via="uvx", config_path=config_path)

        # File must be unchanged and no backup created.
        assert config_path.read_text() == before_text
        backups = list(tmp_path.glob("claude_desktop_config.json.bak.*"))
        assert backups == []

    def test_force_replaces_and_backs_up(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        initial = {
            "mcpServers": {"things": {"command": "old-command", "args": ["old"]}}
        }
        config_path.write_text(json.dumps(initial, indent=2))

        result = client_config.write_claude_desktop_config(
            via="uvx", force=True, config_path=config_path
        )

        assert result.changed is True
        assert result.old_server_config == {"command": "old-command", "args": ["old"]}
        assert result.new_server_config == {
            "command": "uvx",
            "args": list(client_config.UVX_ARGS),
        }

        on_disk = json.loads(config_path.read_text())
        assert on_disk["mcpServers"]["things"] == {
            "command": "uvx",
            "args": list(client_config.UVX_ARGS),
        }

        assert result.backup_path is not None
        assert result.backup_path.exists()
        backup_data = json.loads(result.backup_path.read_text())
        assert backup_data == initial

    def test_invalid_json_refused(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text("{not valid json")
        before_text = config_path.read_text()

        with pytest.raises(client_config.ClientConfigError):
            client_config.write_claude_desktop_config(via="uvx", config_path=config_path)

        assert config_path.read_text() == before_text
        backups = list(tmp_path.glob("claude_desktop_config.json.bak.*"))
        assert backups == []

    def test_env_override_path(self, tmp_path, monkeypatch):
        config_path = tmp_path / "custom_config.json"
        monkeypatch.setenv("THINGS_MCP_CLAUDE_CONFIG_PATH", str(config_path))
        assert client_config.get_claude_desktop_config_path() == config_path


# ---------------------------------------------------------------------------
# CLI argv routing (things_mcp.main)
# ---------------------------------------------------------------------------

class TestMainConfigDispatch:
    def test_config_requires_client(self, monkeypatch, capsys):
        from things_mcp import main as main_module

        monkeypatch.setattr(sys, "argv", ["mcp-server-things", "config"])
        code = main_module.main()
        assert code != 0
        captured = capsys.readouterr()
        assert "--client" in captured.err

    def test_config_claude_desktop_prints_snippet(self, monkeypatch, capsys):
        from things_mcp import main as main_module

        monkeypatch.setattr(
            sys, "argv", ["mcp-server-things", "config", "--client", "claude-desktop"]
        )
        code = main_module.main()
        assert code == 0
        captured = capsys.readouterr()
        assert '"mcpServers"' in captured.out
        assert "uvx" in captured.out

    def test_config_claude_code_prints_commands(self, monkeypatch, capsys):
        from things_mcp import main as main_module

        monkeypatch.setattr(
            sys, "argv", ["mcp-server-things", "config", "--client", "claude-code"]
        )
        code = main_module.main()
        assert code == 0
        captured = capsys.readouterr()
        assert "claude mcp add-json things" in captured.out
        assert "-s user" in captured.out

    def test_config_generic_prints_server_config(self, monkeypatch, capsys):
        from things_mcp import main as main_module

        monkeypatch.setattr(
            sys, "argv", ["mcp-server-things", "config", "--client", "generic"]
        )
        code = main_module.main()
        assert code == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data == {"command": "uvx", "args": list(client_config.UVX_ARGS)}

    def test_config_write_rejected_for_non_claude_desktop(self, monkeypatch, capsys):
        from things_mcp import main as main_module

        monkeypatch.setattr(
            sys,
            "argv",
            ["mcp-server-things", "config", "--client", "generic", "--write"],
        )
        code = main_module.main()
        assert code != 0
        captured = capsys.readouterr()
        assert "--write" in captured.err

    def test_config_write_invokes_client_config_write(self, monkeypatch, capsys, tmp_path):
        from things_mcp import main as main_module

        config_path = tmp_path / "claude_desktop_config.json"
        monkeypatch.setenv("THINGS_MCP_CLAUDE_CONFIG_PATH", str(config_path))
        monkeypatch.setattr(
            sys,
            "argv",
            ["mcp-server-things", "config", "--client", "claude-desktop", "--write"],
        )
        code = main_module.main()
        assert code == 0
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["mcpServers"]["things"] == {
            "command": "uvx",
            "args": list(client_config.UVX_ARGS),
        }

    def test_config_write_refused_reports_nonzero_exit(self, monkeypatch, capsys, tmp_path):
        from things_mcp import main as main_module

        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(
            json.dumps({"mcpServers": {"things": {"command": "old", "args": []}}})
        )
        monkeypatch.setenv("THINGS_MCP_CLAUDE_CONFIG_PATH", str(config_path))
        monkeypatch.setattr(
            sys,
            "argv",
            ["mcp-server-things", "config", "--client", "claude-desktop", "--write"],
        )
        code = main_module.main()
        assert code != 0
        captured = capsys.readouterr()
        assert "--force" in captured.err

    def test_no_subcommand_does_not_call_config(self, monkeypatch):
        from things_mcp import main as main_module

        monkeypatch.setattr(sys, "argv", ["mcp-server-things", "--version"])
        with patch("things_mcp.client_config.build_server_config") as mock_build:
            code = main_module.main()
        mock_build.assert_not_called()
        assert code == 0


# ---------------------------------------------------------------------------
# manifest.json / client_config single-source-of-truth guard
# ---------------------------------------------------------------------------

class TestManifestUvxArgsMatchClientConfig:
    def test_manifest_args_match_uvx_args_constant(self):
        """manifest.json's server.mcp_config.args must match client_config.UVX_ARGS.

        Guards against the two hardened-uvx-args copies (manifest.json for the
        .mcpb bundle, client_config.UVX_ARGS for the `config` CLI) drifting
        apart.
        """
        manifest = json.loads(MANIFEST_PATH.read_text())
        manifest_args = manifest["server"]["mcp_config"]["args"]
        assert manifest_args == client_config.UVX_ARGS
