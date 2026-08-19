#!/usr/bin/env python3
"""Generate the manifest.json `tools` array from the server's registered MCP tools.

The MCPB manifest (manifest.json, repo root) carries a hand-curated `tools`
array used only as advisory metadata for the Claude Desktop bundle listing.
It has no effect on which tools are actually available at runtime - that is
entirely determined by `ThingsMCPServer._register_tools()`. Because of that,
the two lists can silently drift (a tool gets added/removed/renamed in the
server but the manifest is not updated).

This script is the single source of truth bridge: it imports the server
in-process, asks FastMCP for the live tool registry, and can either check
that manifest.json matches (--check) or rewrite manifest.json's tools array
to match (--write).

Usage:
    PYTHONPATH=src python3 scripts/gen_manifest_tools.py --check
    PYTHONPATH=src python3 scripts/gen_manifest_tools.py --write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPO_ROOT / "manifest.json"

MAX_DESCRIPTION_LENGTH = 200


def _first_sentence_or_line(description: str) -> str:
    """Extract a short summary from a (possibly multi-line, multi-sentence) docstring.

    Takes the first line, then (within that line) the first sentence if a
    sentence boundary is found before the max length. Always truncated to
    MAX_DESCRIPTION_LENGTH characters.

    Args:
        description: The full tool description/docstring text.

    Returns:
        A short, single-line summary string, at most MAX_DESCRIPTION_LENGTH
        characters.
    """
    if not description:
        return ""

    first_line = description.strip().splitlines()[0].strip()

    # Prefer truncating at the first sentence boundary ('. ') if present.
    sentence_end = first_line.find(". ")
    if sentence_end != -1:
        summary = first_line[: sentence_end + 1]
    elif first_line.endswith("."):
        summary = first_line
    else:
        summary = first_line

    return summary[:MAX_DESCRIPTION_LENGTH]


def _build_server():
    """Construct a ThingsMCPServer instance without touching Things 3.

    Server construction (`ThingsMCPServer()`) only builds config, an
    AppleScriptManager (no subprocess calls at construction time), the
    ThingsTools wrapper, and registers tool functions with FastMCP - it does
    not execute any AppleScript. This mirrors how the unit test suite builds
    the server in tests/unit/test_structured_output.py's
    `_make_server_with_mock_tools` (which additionally swaps in a mock
    ThingsTools before any tool is *called*; since we never call a tool here,
    only enumerate the registry, that swap is unnecessary for this script).

    Returns:
        A constructed ThingsMCPServer instance.
    """
    from things_mcp.server import ThingsMCPServer

    return ThingsMCPServer()


def generate_tools() -> list[dict[str, str]]:
    """Enumerate the server's registered MCP tools as manifest-ready entries.

    Returns:
        A list of {"name": str, "description": str} dicts, sorted by name,
        matching the shape expected in manifest.json's "tools" array.
    """
    server = _build_server()
    tools = asyncio.run(server.mcp.list_tools())
    entries = [
        {"name": tool.name, "description": _first_sentence_or_line(tool.description or "")}
        for tool in tools
    ]
    entries.sort(key=lambda entry: entry["name"])
    return entries


def _load_manifest() -> dict:
    with open(MANIFEST_PATH, "r") as f:
        return json.load(f)


def _write_manifest(manifest: dict) -> None:
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def check() -> int:
    """Compare manifest.json's tools array against the live registry.

    Returns:
        0 if they match, 1 if they differ (after printing a diff to stderr).
    """
    manifest = _load_manifest()
    current_tools = manifest.get("tools", [])
    generated_tools = generate_tools()

    if current_tools == generated_tools:
        print(f"manifest.json tools list is in sync ({len(generated_tools)} tools).")
        return 0

    current_names = {t["name"] for t in current_tools}
    generated_names = {t["name"] for t in generated_tools}
    missing = sorted(generated_names - current_names)
    extra = sorted(current_names - generated_names)
    changed_desc = sorted(
        t["name"]
        for t in generated_tools
        if t["name"] in current_names
        and t["name"] not in missing
        and t["name"] not in extra
        and next(c["description"] for c in current_tools if c["name"] == t["name"]) != t["description"]
    )

    print("manifest.json 'tools' array is out of sync with the registered MCP tools:", file=sys.stderr)
    if missing:
        print(f"  Missing from manifest.json (registered but not listed): {missing}", file=sys.stderr)
    if extra:
        print(f"  Stale in manifest.json (listed but no longer registered): {extra}", file=sys.stderr)
    if changed_desc:
        print(f"  Description drift: {changed_desc}", file=sys.stderr)
    print("Run: python3 scripts/gen_manifest_tools.py --write", file=sys.stderr)
    return 1


def write() -> int:
    """Rewrite manifest.json's tools array in place to match the live registry.

    Preserves all other top-level keys and the file's 2-space indent plus
    trailing newline convention.

    Returns:
        0 on success.
    """
    manifest = _load_manifest()
    before_count = len(manifest.get("tools", []))
    generated_tools = generate_tools()
    manifest["tools"] = generated_tools
    _write_manifest(manifest)
    print(f"manifest.json tools list updated: {before_count} -> {len(generated_tools)} tools.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 with a diff if manifest.json's tools differ from the live registry.",
    )
    group.add_argument(
        "--write",
        action="store_true",
        help="Rewrite manifest.json's tools array to match the live registry.",
    )
    args = parser.parse_args()

    if args.check:
        return check()
    return write()


if __name__ == "__main__":
    sys.exit(main())
