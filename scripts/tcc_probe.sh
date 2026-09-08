#!/usr/bin/env bash
# tcc_probe.sh - read-only diagnostic for the recurring macOS "python wants
# access to other apps' data" TCC prompt (bead hq-gxt).
#
# Safe to run and paste the output back: this script only reads files,
# runs codesign/log/sqlite3 in read-only modes, and prints to stdout. It
# never writes to any file, TCC database, or system setting.
set -uo pipefail

section() { printf '\n=== %s ===\n' "$1"; }

section "1. Resolved uvx-managed Python 3.12 interpreter"
UVX_PY=""
if command -v uvx >/dev/null 2>&1; then
  UVX_PY=$(uvx --python-preference only-managed --python 3.12 python -c \
    "import sys,os;print(os.path.realpath(sys.executable))" 2>/dev/null)
  echo "resolved realpath: ${UVX_PY:-<failed to resolve>}"
else
  echo "uvx not found on PATH; trying 'uv python find 3.12' instead"
  if command -v uv >/dev/null 2>&1; then
    UVX_PY=$(uv python find 3.12 2>/dev/null)
    echo "uv python find 3.12: ${UVX_PY:-<none found>}"
  else
    echo "uv not found either - cannot resolve the uvx-managed interpreter"
  fi
fi

if [ -n "${UVX_PY:-}" ] && [ -x "$UVX_PY" ]; then
  section "2. codesign identity of the resolved interpreter"
  codesign -dv --verbose=2 "$UVX_PY" 2>&1 | grep -Ei 'Identifier|TeamIdentifier|flags|Signature'
  echo
  echo "NOTE: if 'Signature=adhoc' and no Info.plist/.app bundle wraps this"
  echo "binary, macOS TCC identifies it by this exact filesystem PATH, not by"
  echo "a bundle id. If the path embeds an exact patch version (e.g."
  echo "cpython-3.12.11-macos-...), any uv reinstall/patch upgrade that"
  echo "changes the path will be treated by TCC as a brand-new, never-before"
  echo "-authorized program, requiring a fresh prompt."
fi

section "3. Things 3 database path (via things.py)"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -x "$REPO_DIR/venv/bin/python" ]; then
  DB_PATH=$("$REPO_DIR/venv/bin/python" -c \
    "import things; print(things.database.Database().filepath)" 2>&1)
  echo "$DB_PATH"
else
  echo "repo venv (venv/bin/python) not found at $REPO_DIR/venv/bin/python"
  DB_PATH=""
fi

section "4. Read-only open test against the Things database"
if [ -n "${DB_PATH:-}" ] && [ -f "$DB_PATH" ]; then
  if command -v sqlite3 >/dev/null 2>&1; then
    RESULT=$(sqlite3 -readonly "$DB_PATH" "select count(*) from TMTask;" 2>&1)
    if [ $? -eq 0 ]; then
      echo "OK - readable, TMTask row count: $RESULT"
    else
      echo "FAILED to open read-only. sqlite3 error:"
      echo "$RESULT"
      echo "(a permission-denied/unable-to-open error here usually means"
      echo "the *calling process* - this terminal/shell, or whatever ran"
      echo "this script - lacks Full Disk Access, since the Things database"
      echo "lives under ~/Library/Group Containers.)"
    fi
  else
    echo "sqlite3 not found on PATH - cannot test"
  fi
else
  echo "no valid database path resolved above; skipping open test"
fi

section "5. things_mcp process parent chain (if running)"
PIDS=$(pgrep -f things_mcp 2>/dev/null)
if [ -z "$PIDS" ]; then
  echo "no things_mcp process currently running"
else
  for pid in $PIDS; do
    echo "--- chain for pid $pid ---"
    p=$pid
    for _ in 1 2 3 4 5; do
      ps -o pid,ppid,comm -p "$p" 2>/dev/null || break
      ppid=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
      [ -z "$ppid" ] && break
      [ "$ppid" = "0" ] && break
      p=$ppid
    done
    echo
  done
fi

section "Done"
echo "Paste the full output above back to the implementer/orchestrator."
