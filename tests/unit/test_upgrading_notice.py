"""Tests for the legacy-launch upgrade notice and docs/UPGRADING.md.

Covers `things_mcp.main._legacy_launch_notice`, which prints a one-line INFO
tip pointing at docs/UPGRADING.md when the server is started via a legacy
launch path (the `things-mcp` console-script alias, or a `src/`-layout
checkout run via PYTHONPATH), and a guard that the upgrade doc itself exists
and documents the key behavioural changes.
"""

from pathlib import Path

import pytest

from things_mcp.main import _legacy_launch_notice

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UPGRADING_PATH = REPO_ROOT / "docs" / "UPGRADING.md"


def test_legacy_alias_argv0_returns_notice(monkeypatch):
    """sys.argv[0] basename 'things-mcp' triggers the notice."""
    monkeypatch.setattr("sys.argv", ["/usr/local/bin/things-mcp"])
    notice = _legacy_launch_notice()
    assert notice is not None
    assert "UPGRADING.md" in notice


def test_src_layout_file_returns_notice(monkeypatch):
    """A things_mcp.__file__ path containing a 'src' segment triggers the notice."""
    monkeypatch.setattr("sys.argv", ["mcp-server-things"])
    monkeypatch.setattr(
        "things_mcp.__file__",
        "/Users/dev/mcp-server-things/src/things_mcp/__init__.py",
    )
    notice = _legacy_launch_notice()
    assert notice is not None
    assert "UPGRADING.md" in notice


def test_normal_launch_returns_none(monkeypatch):
    """Console-script argv0 plus a site-packages-style __file__ returns None."""
    monkeypatch.setattr("sys.argv", ["mcp-server-things"])
    monkeypatch.setattr(
        "things_mcp.__file__",
        "/Users/dev/.venv/lib/python3.11/site-packages/things_mcp/__init__.py",
    )
    notice = _legacy_launch_notice()
    assert notice is None


def test_notice_never_raises_with_empty_argv(monkeypatch):
    """An empty sys.argv must not raise (e.g. some embedding contexts)."""
    monkeypatch.setattr("sys.argv", [])
    # Should not raise regardless of return value.
    _legacy_launch_notice()


def test_notice_never_raises_with_weird_argv(monkeypatch):
    """Non-string / unusual sys.argv[0] values must not raise."""
    monkeypatch.setattr("sys.argv", [None])
    _legacy_launch_notice()


def test_upgrading_doc_exists_and_covers_key_behavioural_changes():
    """docs/UPGRADING.md must exist and mention the key behavioural changes."""
    assert UPGRADING_PATH.exists(), "docs/UPGRADING.md is missing"
    content = UPGRADING_PATH.read_text()

    for term in [
        "include_project_tasks",
        "fail_on_unknown",
        "structured_content",
        "search_advanced",
        "uvx",
    ]:
        assert term in content, f"docs/UPGRADING.md is missing expected term: {term!r}"
