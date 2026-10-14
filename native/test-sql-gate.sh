#!/bin/sh
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
mkdir -p "$repo/build"
clang -fobjc-arc -Wall -Wextra -framework AppKit -lsqlite3 \
  "$repo/native/test-sql-gate.m" -o "$repo/build/test-sql-gate"
"$repo/build/test-sql-gate" | python3 -c '
import json
import sys

results = [json.loads(line) for line in sys.stdin]
assert len(results) == 8, results
assert results[0] == {"ok": True, "columns": ["title", "payload"],
                      "rows": [["Synthetic task", {"$blob": "AQI="}]]}, results[0]
assert results[1] == {"ok": True, "columns": ["COUNT(*)"], "rows": [[1]]}, results[1]
assert all(result["ok"] is False for result in results[2:]), results[2:]
print("synthetic SQL gate passed")
'
