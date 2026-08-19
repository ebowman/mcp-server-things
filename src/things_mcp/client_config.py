"""Client configuration helpers for the `config` CLI subcommand.

This module produces (and optionally writes) the MCP client configuration
snippets needed to register the Things 3 MCP server with a given client
(Claude Desktop, Claude Code, or a generic MCP client), so users don't have
to hand-edit JSON files or guess at command/args shapes.

Everything in this module is a pure function with respect to process state
except for :func:`write_claude_desktop_config`, which is the single function
that touches the filesystem. Keeping the filesystem-mutating logic isolated
here (and out of ``things_mcp.main``) makes it straightforward to unit test
both the pure "what should the config look like" logic and the "how do we
safely merge/write it" logic independently, without importing FastMCP or the
server.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SERVER_KEY = "things"

CLIENT_CHOICES = ("claude-desktop", "claude-code", "generic")
VIA_CHOICES = ("uvx", "current-python")

DEFAULT_CLAUDE_DESKTOP_CONFIG_PATH = (
    Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
)

_CLAUDE_CONFIG_PATH_ENV_VAR = "THINGS_MCP_CLAUDE_CONFIG_PATH"


class ClientConfigError(Exception):
    """Raised when a config request cannot be satisfied (refusal or error).

    Callers (the CLI layer) should catch this, print ``str(error)`` to
    stderr, and exit non-zero.
    """


def get_claude_desktop_config_path() -> Path:
    """Return the path to the Claude Desktop config file.

    Honors the ``THINGS_MCP_CLAUDE_CONFIG_PATH`` environment variable so
    tests (and advanced users) can redirect writes away from the real file.
    """
    override = os.environ.get(_CLAUDE_CONFIG_PATH_ENV_VAR)
    if override:
        return Path(override)
    return DEFAULT_CLAUDE_DESKTOP_CONFIG_PATH


def build_server_config(via: str = "uvx") -> dict:
    """Build the ``{"command": ..., "args": [...]}`` server config dict.

    Args:
        via: ``"uvx"`` (default) for ``uvx mcp-server-things``, or
            ``"current-python"`` for ``sys.executable -m things_mcp``.

    Returns:
        A dict with ``command`` and ``args`` keys.

    Raises:
        ValueError: If ``via`` is not one of the supported choices.
    """
    if via == "uvx":
        return {"command": "uvx", "args": ["mcp-server-things"]}
    if via == "current-python":
        return {"command": sys.executable, "args": ["-m", "things_mcp"]}
    raise ValueError(f"Unknown via option: {via!r} (expected one of {VIA_CHOICES})")


def current_python_source_tree_caveat() -> Optional[str]:
    """Return a one-line caveat string if `things_mcp` looks like a source checkout.

    ``--via current-python`` assumes ``things_mcp`` is importable by
    ``sys.executable`` (true for pip/venv installs). In a source checkout
    (package located under a ``src/`` directory) that import may require
    ``PYTHONPATH`` to be set. Returns ``None`` when no caveat applies.
    """
    try:
        package_file = Path(__file__).resolve()
    except (OSError, ValueError):
        return None

    if "src" in package_file.parts:
        return (
            "Note: things_mcp appears to be running from a source checkout (src/ layout); "
            "the target interpreter may need PYTHONPATH set to import things_mcp."
        )
    return None


def format_claude_desktop_snippet(via: str = "uvx") -> str:
    """Return the pretty-printed ``{"mcpServers": {"things": {...}}}`` JSON snippet."""
    server_config = build_server_config(via)
    snippet = {"mcpServers": {SERVER_KEY: server_config}}
    return json.dumps(snippet, indent=2)


def format_claude_code_commands(via: str = "uvx") -> str:
    """Return the `claude mcp add-json` one-liners (default scope and `-s user`)."""
    server_config = build_server_config(via)
    server_json = json.dumps(server_config, separators=(",", ":"))
    line1 = f"claude mcp add-json {SERVER_KEY} '{server_json}'"
    line2 = f"claude mcp add-json {SERVER_KEY} '{server_json}' -s user"
    return f"{line1}\n{line2}"


def format_generic_snippet(via: str = "uvx") -> str:
    """Return just the server-config JSON object, pretty-printed."""
    server_config = build_server_config(via)
    return json.dumps(server_config, indent=2)


@dataclass
class WriteResult:
    """Result of a successful (or no-op) config write.

    Attributes:
        changed: True if the file was written, False if it was already
            up to date (no-op).
        path: Path to the config file that was read/written.
        backup_path: Path to the backup file, or None if no backup was made
            (no-op case, or fresh-file case where there was nothing to back up).
        old_server_config: The previous "things" server config dict, or None
            if there wasn't one.
        new_server_config: The new "things" server config dict that is now
            in place.
    """

    changed: bool
    path: Path
    backup_path: Optional[Path]
    old_server_config: Optional[dict]
    new_server_config: dict


def write_claude_desktop_config(
    via: str = "uvx",
    force: bool = False,
    config_path: Optional[Path] = None,
) -> WriteResult:
    """Merge the things server config into the Claude Desktop config file.

    Args:
        via: ``"uvx"`` or ``"current-python"`` (see :func:`build_server_config`).
        force: If True, overwrite an existing, differing ``mcpServers.things``
            entry. If False and an entry already exists and differs, refuse.
        config_path: Override for the config file path (defaults to
            :func:`get_claude_desktop_config_path`).

    Returns:
        A :class:`WriteResult` describing what happened.

    Raises:
        ClientConfigError: If the existing file contains invalid JSON, or if
            an existing differing entry is present and ``force`` is False.
    """
    path = config_path if config_path is not None else get_claude_desktop_config_path()
    new_server_config = build_server_config(via)

    if path.exists():
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ClientConfigError(f"Could not read {path}: {exc}") from exc

        try:
            existing_data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise ClientConfigError(
                f"Refusing to modify {path}: existing file is not valid JSON ({exc}). "
                "Fix or remove the file and try again."
            ) from exc

        if not isinstance(existing_data, dict):
            raise ClientConfigError(
                f"Refusing to modify {path}: existing top-level JSON value is not an object."
            )
    else:
        existing_data = {}

    mcp_servers = existing_data.get("mcpServers")
    if mcp_servers is None:
        mcp_servers = {}
    elif not isinstance(mcp_servers, dict):
        raise ClientConfigError(
            f"Refusing to modify {path}: existing 'mcpServers' value is not an object."
        )

    old_server_config = mcp_servers.get(SERVER_KEY)

    if old_server_config == new_server_config:
        return WriteResult(
            changed=False,
            path=path,
            backup_path=None,
            old_server_config=old_server_config,
            new_server_config=new_server_config,
        )

    if old_server_config is not None and not force:
        raise ClientConfigError(
            f"Refusing to overwrite existing 'mcpServers.{SERVER_KEY}' entry in {path} "
            f"(current: {json.dumps(old_server_config)}, new: {json.dumps(new_server_config)}). "
            "Re-run with --force to replace it."
        )

    # Back up the existing file before writing, if it exists.
    backup_path: Optional[Path] = None
    if path.exists():
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
        shutil.copy2(path, backup_path)

    existing_data["mcpServers"] = mcp_servers
    mcp_servers[SERVER_KEY] = new_server_config

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing_data, indent=2) + "\n", encoding="utf-8")

    return WriteResult(
        changed=True,
        path=path,
        backup_path=backup_path,
        old_server_config=old_server_config,
        new_server_config=new_server_config,
    )
