"""Golden tool-schema snapshot for all registered MCP tools.

Dumps a deterministic, comparable projection of every tool's public schema
(name, description hash, inputSchema property shapes, required list,
outputSchema presence) and compares it against a committed JSON snapshot
(tests/fixtures/tool_schema_snapshot.json). This catches accidental schema
drift (e.g. a changed default, an added/removed parameter, a renamed field)
that wouldn't otherwise be caught by behavioral tests.

Uses the real ThingsMCPServer + FastMCP tool registration via an in-memory
fastmcp.Client (no stdio, no real Things 3), mirroring the pattern in
tests/unit/test_structured_output.py and
tests/unit/test_manifest_tools_sync.py. The ThingsTools layer is replaced
with a mock so nothing touches AppleScript/things.py.

Regenerating the snapshot:
    THINGS_MCP_UPDATE_SCHEMA_SNAPSHOT=1 pytest tests/unit/test_tool_schema_snapshot.py

This test intentionally does NOT duplicate test_manifest_tools_sync.py's
deep manifest-vs-registered-tools checks; it only cross-checks the tool
*name set* against manifest.json as a sanity guard (see
test_tool_names_match_manifest below).
"""

import asyncio
import difflib
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastmcp import Client

from things_mcp.server import ThingsMCPServer

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"
SNAPSHOT_PATH = REPO_ROOT / "tests" / "fixtures" / "tool_schema_snapshot.json"
UPDATE_ENV_VAR = "THINGS_MCP_UPDATE_SCHEMA_SNAPSHOT"

EXPECTED_TOOL_COUNT = 41

def _make_server_with_mock_tools():
    """Build a ThingsMCPServer with a mocked ThingsTools layer (no AppleScript).

    Mirrors tests/unit/test_structured_output.py's
    _make_server_with_mock_tools / test_manifest_tools_sync.py's helper of
    the same name.
    """
    server = ThingsMCPServer()
    mock_tools = MagicMock()
    mock_tools.tag_validation_service = None
    server.tools = mock_tools
    return server


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_CONSTRAINT_KEYS = ("enum", "minimum", "maximum", "pattern", "minLength", "maxLength")


def _snapshot_member(member_schema: dict) -> dict:
    """Project a single schema (top-level or anyOf member) to type + constraints."""
    out = {"type": member_schema.get("type", "unknown")}
    for key in _CONSTRAINT_KEYS:
        if key in member_schema:
            out[key] = member_schema[key]
    return out


def _snapshot_property(prop_schema: dict) -> dict:
    """Project a single inputSchema property to its comparable attributes.

    Handles both plain `{"type": ...}` schemas and `anyOf` union schemas
    (used by FastMCP/pydantic for Optional[...] parameters). For `anyOf`,
    each member's type AND constraints (enum/minimum/maximum/pattern/
    minLength/maxLength) are recorded under `anyOf_members`, sorted by a
    JSON-serialized key for determinism - otherwise per-member constraints
    (e.g. a numeric le/ge bound or a string pattern on one anyOf member)
    would be silently dropped.
    """
    out = {}

    if "type" in prop_schema:
        out["type"] = prop_schema["type"]

    if "anyOf" in prop_schema:
        members = [_snapshot_member(m) for m in prop_schema["anyOf"]]
        members.sort(key=lambda m: json.dumps(m, sort_keys=True))
        out["anyOf_members"] = members

    for key in ("default",) + _CONSTRAINT_KEYS:
        if key in prop_schema:
            out[key] = prop_schema[key]

    return out


def _snapshot_tool(tool) -> dict:
    """Project a single mcp.types.Tool to its comparable, deterministic shape."""
    input_schema = tool.inputSchema or {}
    properties = input_schema.get("properties", {}) or {}

    snapshot_properties = {
        name: _snapshot_property(prop_schema)
        for name, prop_schema in properties.items()
    }

    return {
        "name": tool.name,
        "description_sha256": _sha256(tool.description or ""),
        "properties": snapshot_properties,
        "required": sorted(input_schema.get("required", []) or []),
        "has_output_schema": tool.outputSchema is not None,
    }


async def _list_tools_snapshot() -> dict:
    """Build the full deterministic snapshot dict for all registered tools."""
    server = _make_server_with_mock_tools()
    client = Client(server.mcp)
    async with client:
        tools = await client.list_tools()

    tools_by_name = {t.name: _snapshot_tool(t) for t in tools}
    return {name: tools_by_name[name] for name in sorted(tools_by_name)}


def _build_snapshot_sync() -> dict:
    return asyncio.run(_list_tools_snapshot())


def _dump_json(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def _load_committed_snapshot() -> dict:
    with open(SNAPSHOT_PATH, "r") as f:
        return json.load(f)


def _tool_diff(tool_name: str, expected: dict, actual: dict) -> str:
    expected_lines = _dump_json({tool_name: expected}).splitlines(keepends=True)
    actual_lines = _dump_json({tool_name: actual}).splitlines(keepends=True)
    diff = difflib.unified_diff(
        expected_lines,
        actual_lines,
        fromfile=f"committed/{tool_name}",
        tofile=f"actual/{tool_name}",
    )
    return "".join(diff)


class TestToolSchemaSnapshot:
    """Golden snapshot of every registered tool's public schema."""

    def test_exactly_41_tools_registered(self):
        snapshot = _build_snapshot_sync()
        assert len(snapshot) == EXPECTED_TOOL_COUNT, (
            f"Expected exactly {EXPECTED_TOOL_COUNT} registered tools, got "
            f"{len(snapshot)}: {sorted(snapshot)}"
        )

    def test_tool_names_match_manifest(self):
        """Cross-check only the tool *name set* against manifest.json.

        This is intentionally shallow - test_manifest_tools_sync.py already
        owns the deeper manifest-vs-registered-tools contract (including
        descriptions); this is just a sanity guard so this snapshot file
        can't silently drift to cover a different tool set than the
        manifest advertises.
        """
        snapshot = _build_snapshot_sync()
        registered_names = set(snapshot)

        with open(MANIFEST_PATH, "r") as f:
            manifest = json.load(f)
        manifest_names = {entry["name"] for entry in manifest.get("tools", [])}

        assert registered_names == manifest_names, (
            "Tool name set from schema snapshot does not match manifest.json. "
            f"Missing from manifest: {sorted(registered_names - manifest_names)}. "
            f"Extra in manifest: {sorted(manifest_names - registered_names)}."
        )

    def test_schema_matches_committed_snapshot(self):
        actual = _build_snapshot_sync()

        if os.environ.get(UPDATE_ENV_VAR) == "1":
            SNAPSHOT_PATH.write_text(_dump_json(actual))
            return

        expected = _load_committed_snapshot()

        if actual == expected:
            return

        all_names = sorted(set(expected) | set(actual))
        diffs = []
        for name in all_names:
            exp = expected.get(name)
            act = actual.get(name)
            if exp != act:
                diffs.append(_tool_diff(name, exp, act))

        diff_text = "\n".join(diffs)
        pytest.fail(
            "Tool schema snapshot mismatch for "
            f"{len([n for n in all_names if expected.get(n) != actual.get(n)])} tool(s).\n"
            f"{diff_text}\n"
            f"Run with {UPDATE_ENV_VAR}=1 to regenerate the snapshot."
        )

    def test_snapshot_is_deterministic_across_runs(self):
        """Building the snapshot twice in the same process must be byte-identical."""
        first = _dump_json(_build_snapshot_sync())
        second = _dump_json(_build_snapshot_sync())
        assert first == second
