#!/usr/bin/env bash
# tcc_probe.sh - read-only support bundle for macOS permission problems -
# paste the output into a bug report.
#
# Safe to run and paste the output back: this script only reads files,
# runs codesign/sqlite3 in read-only modes, and prints to stdout. It
# never writes to any file, TCC database, or system setting.
set -uo pipefail

section() { printf '\n=== %s ===\n' "$1"; }

CONFIG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"

section "1. Claude Desktop interpreter(s)"
INTERPS=""
if [ -f "$CONFIG" ]; then
  MATCHES=$(python3 - "$CONFIG" <<'PYEOF' 2>/dev/null
import json, sys
try:
    with open(sys.argv[1]) as f:
        cfg = json.load(f)
except Exception as e:
    print(f"__error__\t{e}")
    sys.exit(0)
for name, srv in (cfg.get("mcpServers") or {}).items():
    cmd = srv.get("command", "")
    args = srv.get("args", []) or []
    blob = " ".join([cmd] + [str(a) for a in args])
    if "things_mcp" in blob or "mcp-server-things" in blob:
        print(f"{cmd}\t{' '.join(str(a) for a in args)}")
PYEOF
)
  if [ -z "$MATCHES" ]; then
    echo "no things_mcp/mcp-server-things entry found in claude_desktop_config.json"
  fi
  while IFS=$'\t' read -r cmd args; do
    [ -z "$cmd" ] && continue
    if [ "$cmd" = "__error__" ]; then
      echo "failed to parse claude_desktop_config.json: $args"
      continue
    fi
    base=$(basename "$cmd")
    if [ "$base" = "uvx" ] || [ "$base" = "uv" ]; then
      pyargs=$(printf '%s' "$args" | grep -oE -- '--python[^ ]*( [^ -][^ ]*)?' | tr '\n' ' ')
      RESOLVED=$(perl -e 'alarm 30; exec @ARGV' "$cmd" $pyargs python -c \
        "import os,sys;print(os.path.realpath(sys.executable))" 2>/dev/null)
      echo "uvx-resolved interpreter: ${RESOLVED:-failed: could not resolve within 30s}"
      [ -n "$RESOLVED" ] && INTERPS="$INTERPS $RESOLVED"
    else
      RESOLVED=$(readlink -f "$cmd" 2>/dev/null || echo "$cmd")
      echo "direct interpreter: $RESOLVED"
      INTERPS="$INTERPS $RESOLVED"
    fi
  done <<< "$MATCHES"
else
  echo "no claude_desktop_config.json"
fi

section "2. Things 3 database path + read-only open test"
DB_MATCHES=()
for f in "$HOME/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/ThingsData-"*/"Things Database.thingsdatabase/main.sqlite"; do
  [ -f "$f" ] && DB_MATCHES+=("$f")
done
if [ "${#DB_MATCHES[@]}" -eq 0 ]; then
  echo "not found (no ThingsData-* database under Group Containers)"
elif [ "${#DB_MATCHES[@]}" -gt 1 ]; then
  echo "multiple candidate databases found:"
  printf '  %s\n' "${DB_MATCHES[@]}"
else
  DB_PATH="${DB_MATCHES[0]}"
  echo "path: $DB_PATH"
  if command -v sqlite3 >/dev/null 2>&1; then
    RESULT=$(sqlite3 -readonly "$DB_PATH" "select count(*) from TMTask;" 2>/dev/null)
    RC=$?
    if [ $RC -eq 0 ]; then
      echo "OK - readable, TMTask row count: $RESULT"
    else
      echo "failed: could not open database read-only (no Full Disk Access for this terminal?)"
    fi
  else
    echo "sqlite3 not found on PATH - cannot test"
  fi
fi

section "3. user TCC.db AppData/AllFiles rows (python|uv|Claude|culturedcode clients)"
TCC_DB="$HOME/Library/Application Support/com.apple.TCC/TCC.db"
TCC_ROWS=""
if [ -r "$TCC_DB" ] && command -v sqlite3 >/dev/null 2>&1; then
  QUERY="select service, client, client_type, auth_value,
    case when csreq is not null then 'yes' else 'no' end,
    datetime(last_modified,'unixepoch')
    from access
    where service in ('kTCCServiceSystemPolicyAppData','kTCCServiceSystemPolicyAllFiles')
    and (client like '%python%' or client like '%uv%' or client like '%Claude%' or client like '%culturedcode%');"
  ROWS=$(sqlite3 -readonly -separator ' | ' "$TCC_DB" "$QUERY" 2>/dev/null)
  RC=$?
  if [ $RC -eq 0 ]; then
    echo "service | client | client_type | auth_value | csreq | last_modified"
    echo "${ROWS:-<no matching rows>}"
    TCC_ROWS="$ROWS"
  else
    echo "failed: could not open TCC.db read-only (no Full Disk Access for this terminal?)"
  fi
else
  echo "TCC.db unreadable - this terminal likely lacks Full Disk Access"
fi

section "4. codesign summary of distinct TCC client paths (client_type=1)"
if [ -n "$TCC_ROWS" ]; then
  PATHS=$(printf '%s\n' "$TCC_ROWS" | awk -F ' \\| ' '$3 == "1" {print $2}' | sort -u)
  if [ -z "$PATHS" ]; then
    echo "no client_type=1 (path) rows above"
  else
    while IFS= read -r p; do
      [ -z "$p" ] && continue
      if [ ! -e "$p" ]; then
        echo "$p: missing"
        continue
      fi
      SUMMARY=$(codesign -dv --verbose=2 "$p" 2>&1 | grep -Ei 'Identifier=|flags=' | tr '\n' ' ')
      echo "$p: ${SUMMARY:-<no codesign info>}"
    done <<< "$PATHS"
  fi
else
  echo "no TCC.db rows available above"
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
  done
fi

section "Done"
echo "Paste the full output above into a bug report."
