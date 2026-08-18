#!/bin/bash
#
# build_mcpb.sh - Build a Claude Desktop .mcpb bundle for mcp-server-things.
#
# This bundle does NOT vendor the package or its dependencies. It follows the
# same pattern as hald/things-mcp's build script: the manifest tells Claude
# Desktop to invoke `uvx mcp-server-things`, which fetches the published
# package from PyPI at first run (and caches it via uv). The bundle itself
# only ships manifest.json plus a stub entry_point file required by the MCPB
# format.
#
# Version handling: the manifest.json checked into the repo carries a
# placeholder version ("0.0.0"). This script reads the authoritative version
# from src/things_mcp/__init__.py (__version__) and writes a version-substituted manifest into the
# staging directory before packing, so the two files never drift out of sync
# by hand-editing. Do not hand-edit the version in manifest.json.
#
# Packing tool: prefers the official `mcpb` CLI (`npm install -g
# @anthropic-ai/mcpb`, or available ad-hoc via `npx @anthropic-ai/mcpb`).
# Falls back to plain `zip` (an .mcpb file is just a zip archive of the
# bundle directory) if neither is available, since only `zip` is guaranteed
# to be present in this project's tooling. This mirrors hald's script, which
# assumes `mcpb` is installed; we additionally add the zip fallback so the
# build doesn't hard-fail on machines without Node/npm tooling.
#
# Usage: scripts/build_mcpb.sh   (run from repo root)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Building mcp-server-things .mcpb bundle..."

# --- Resolve version from src/things_mcp/__init__.py (single source of truth) ---
VERSION=$(grep -m1 '^__version__' src/things_mcp/__init__.py | sed -E 's/__version__ = "(.*)"/\1/')
if [ -z "$VERSION" ]; then
  echo "ERROR: could not read version from src/things_mcp/__init__.py" >&2
  exit 1
fi
echo "Version: $VERSION"

# --- Clean previous build ---
rm -rf dist/
mkdir -p dist/

# --- Stage bundle contents ---
STAGE_DIR=$(mktemp -d)
trap 'rm -rf "$STAGE_DIR"' EXIT
echo "Staging in: $STAGE_DIR"

# Write the versioned manifest (source manifest.json + injected version).
python3 - "$REPO_ROOT/manifest.json" "$STAGE_DIR/manifest.json" "$VERSION" <<'PYEOF'
import json
import sys

src, dst, version = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src) as f:
    manifest = json.load(f)
manifest["version"] = version
with open(dst, "w") as f:
    json.dump(manifest, f, indent=2)
    f.write("\n")
PYEOF

# Minimal stub required by the MCPB format; actual server code is fetched by
# `uvx` from PyPI at runtime, so nothing else needs to be staged here.
mkdir -p "$STAGE_DIR/server"
cat > "$STAGE_DIR/server/stub.py" <<'EOF'
# Stub entry point required by the MCPB manifest schema.
# The real server is fetched and run via `uvx mcp-server-things` (see manifest.json).
EOF

OUT_FILE="dist/mcp-server-things-${VERSION}.mcpb"

# --- Pack ---
if command -v mcpb >/dev/null 2>&1; then
  echo "Packaging with installed 'mcpb' CLI..."
  mcpb pack "$STAGE_DIR" "$OUT_FILE"
elif command -v npx >/dev/null 2>&1; then
  echo "Packaging with 'npx @anthropic-ai/mcpb' (no global install found)..."
  npx --yes @anthropic-ai/mcpb pack "$STAGE_DIR" "$OUT_FILE"
elif command -v zip >/dev/null 2>&1; then
  echo "WARNING: mcpb CLI not found (npm install -g @anthropic-ai/mcpb)." >&2
  echo "Falling back to plain 'zip' to produce the .mcpb archive." >&2
  (cd "$STAGE_DIR" && zip -r -q "$REPO_ROOT/$OUT_FILE" .)
else
  echo "ERROR: none of 'mcpb', 'npx', or 'zip' are available on this machine." >&2
  echo "Install one of them to build the .mcpb bundle:" >&2
  echo "  npm install -g @anthropic-ai/mcpb   (preferred)" >&2
  echo "  or ensure 'zip' is on PATH (fallback)" >&2
  exit 1
fi

echo "MCPB package created: $OUT_FILE"
ls -la dist/
echo "Build completed successfully!"
