"""Guard against manifest.json's 'tools' array drifting from registered MCP tools.

manifest.json (repo root) carries a hand-curated `tools` array used as
advisory metadata for the Claude Desktop MCPB bundle listing. It has no
effect on which tools are actually available at runtime, so it can silently
go stale as tools are added/renamed/removed in the server. This test asserts
the set of tool names listed in manifest.json matches the set of tool names
FastMCP actually has registered, via scripts/gen_manifest_tools.py's
generate_tools().
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"
GEN_SCRIPT_PATH = REPO_ROOT / "scripts" / "gen_manifest_tools.py"


def _load_gen_manifest_tools_module():
    """Import scripts/gen_manifest_tools.py as a module (scripts/ isn't a package)."""
    spec = importlib.util.spec_from_file_location("gen_manifest_tools", GEN_SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["gen_manifest_tools"] = module
    spec.loader.exec_module(module)
    return module


def _make_server_with_mock_tools():
    """Build a ThingsMCPServer with a mocked ThingsTools layer (no AppleScript).

    Mirrors tests/unit/test_structured_output.py's _make_server_with_mock_tools
    helper.
    """
    from things_mcp.server import ThingsMCPServer

    server = ThingsMCPServer()
    mock_tools = MagicMock()
    mock_tools.tag_validation_service = None
    server.tools = mock_tools
    return server


class TestManifestToolsSync:
    """manifest.json's tools list must match the server's registered tool names."""

    def test_manifest_tools_match_registered_tools(self):
        server = _make_server_with_mock_tools()
        registered_names = {tool.name for tool in asyncio.run(server.mcp.list_tools())}

        with open(MANIFEST_PATH, "r") as f:
            manifest = json.load(f)
        manifest_names = {entry["name"] for entry in manifest.get("tools", [])}

        missing = registered_names - manifest_names
        extra = manifest_names - registered_names

        assert not missing and not extra, (
            "manifest.json 'tools' array is out of sync with registered MCP tools. "
            f"Missing from manifest: {sorted(missing)}. "
            f"Stale in manifest (no longer registered): {sorted(extra)}. "
            "Run: python3 scripts/gen_manifest_tools.py --write"
        )

    def test_generate_tools_matches_manifest_exactly(self):
        """generate_tools() output (names + descriptions) should equal manifest.json's
        tools array when the manifest is up to date (guards against forgetting
        to re-run --write after a description change)."""
        gen_module = _load_gen_manifest_tools_module()
        generated = gen_module.generate_tools()

        with open(MANIFEST_PATH, "r") as f:
            manifest = json.load(f)
        current = manifest.get("tools", [])

        assert generated == current, (
            "manifest.json 'tools' array does not match the generated output. "
            "Run: python3 scripts/gen_manifest_tools.py --write"
        )
