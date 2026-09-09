# macOS permissions: the three dialogs, why they recur, and how to fix a headless Mac

This server talks to Things 3 via AppleScript (writes) and reads the Things
SQLite database directly via `things.py` (reads). Both paths are gated by
macOS's TCC (Transparency, Consent, and Control) privacy system, which is why
you may see one or more of the dialogs below - and, on some machines, see
them come back after a Claude Desktop restart even though you already clicked
Allow.

## Symptoms

| Operation | Result |
|---|---|
| Read tools (`get_today`, `get_inbox`, `search_todos`, ...) | Fail instantly with `unable to open database file`, or a structured `database_access_denied` error (see "How to verify" below) |
| Write tools (`add_todo`, `update_todo`, ...) | Work normally |
| URL-scheme features needing the auth token | Also fail (the token is read from the same database) |

If you're grepping logs or error messages, look for either of these
strings: `unable to open database file` (the raw `things.py`/sqlite error)
or `database_access_denied` (this server's structured error code for the
same underlying cause).

## (a) The three dialogs you may see

**1. Automation (AppleScript writes, e.g. `add_todo`/`update_todo`):**

> "Claude" wants access to control "Things3".

Click **Allow**. This is the one-time prompt described in the README's "Why
this server?" section - AppleScript is what enables `delete_todo`,
`move_record`/`bulk_move_records`, `remove_tags`, and real IDs returned
synchronously, at the cost of this prompt.

**2. App-data protection (reads, macOS 15+, `kTCCServiceSystemPolicyAppData`):**

> "python3.12" would like to access data from other apps.

Russian wording (for grepping non-English screenshots/logs):

> «Приложение «python3.12» запрашивает доступ к данным других приложений.»

Buttons: Allow / Don't Allow (Russian: «Разрешить» / «Не разрешать»).

**3. Full Disk Access** (System Settings pane: **Privacy & Security > Full
Disk Access**) - not a dialog you click through in the moment; it's a
System Settings toggle you add the interpreter binary to yourself (see the
fix ladder below). Things 3's database lives under another app's protected
container, so reads need this grant, not just the Automation grant.

## (b) Why the prompt comes back after a restart

Three mechanisms were observed directly (the `disclaimer` parent chain via
`ps`, interpreter code-signing/path identity via `codesign`, and TCC.db
`access` rows for python clients) during the hq-gxt.1 investigation. That
these three combine to explain *why the prompt specifically recurs after a
restart* is the working explanation built from that evidence, not yet
confirmed end-to-end by an actual click-through-and-relaunch test - the
operator matrix below (hq-gxt.7) will confirm or correct it:

- **The database path is another app's container.** The Things 3 SQLite
  database lives at
  `~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/ThingsData-*/Things Database.thingsdatabase/main.sqlite`
  - a container belonging to Things 3, not to this server or to Claude. On
  macOS 15+, any process reading another app's container data is gated
  under `kTCCServiceSystemPolicyAppData`, which is what produces dialog (2)
  above.
- **Claude Desktop launches servers via its `disclaimer` helper**, so the
  Python process - not Claude.app - is the TCC principal. Concretely,
  Claude Desktop spawns MCP servers as
  `/Applications/Claude.app/Contents/Helpers/disclaimer --pgroup -- <python> -m things_mcp`.
  The `disclaimer` helper disclaims TCC responsibility for the process it
  launches, so the spawned Python interpreter does **not** inherit
  Claude.app's own Full Disk Access grant, even though Claude.app itself has
  one. `mcp-server-things doctor`'s "Launch parent" check detects this by
  walking the process's parent chain and WARNs when it finds `disclaimer`
  in it.
- **The `uvx`-managed interpreter is ad-hoc signed and keyed by path that
  embeds the patch version**, so a grant made to it is lost after
  interpreter upgrades. `uvx`'s resolved interpreter has no code-signing
  Team ID and isn't wrapped in an `.app` bundle
  (`codesign -dv` reports `Signature=adhoc`, `TeamIdentifier=not set`,
  `Identifier=-`), so TCC has no stable bundle identity to key off and falls
  back to identifying the process **by its exact executable path** - a path
  like `~/.local/share/uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12`
  that embeds the exact patch version. Any `uv python install --reinstall`,
  or uv simply resolving a newer patch release later, changes this path
  outright, so the previous grant no longer matches anything and macOS
  treats the "new" path as a never-before-seen program requiring a fresh
  prompt. By contrast, a Homebrew **framework** build of Python re-execs
  through its bundled `Python.app`, which carries a stable
  `CFBundleIdentifier` of `org.python.python` - a version-independent
  identity that TCC.db evidence shows holding a live grant across multiple
  Homebrew `python@3.13` rebuilds on the investigation machine.
  `mcp-server-things doctor`'s "Interpreter identity" check reports the
  exact resolved binary path and classifies it as `uv-managed` (WARN - grant
  is fragile across upgrades), `venv`, `framework` (stable), or `other`.

## (c) Fix ladder for an unattended/headless Mac

Ordered per the hq-gxt.1 findings' recommended ordering - **recommended,
pending verification** (the operator matrix below is not yet confirmed
live; see hq-gxt.7):

1. **Grant Full Disk Access to the exact realpath interpreter** (System
   Settings > Privacy & Security > Full Disk Access):
   - Find the exact path to add via either:
     - `mcp-server-things doctor` and read the "Interpreter identity" row
       (`Grant Full Disk Access to: <path>`), or
     - `scripts/tcc_probe.sh`, a read-only diagnostic you can run and paste
       the output back for troubleshooting.
   - Open System Settings > Privacy & Security > Full Disk Access, click
     "+", press Cmd-Shift-G, paste the exact path, and add it. (The FDA
     picker sometimes greys out these paths - drag-and-drop from Finder
     works when the "+" dialog won't accept the path directly.)
   - Quit and relaunch Claude Desktop, then run `mcp-server-things doctor`
     again to verify the database-readability check now PASSes.
   - **Caveat:** this grant is keyed to the exact path. If it's the
     `uvx`-managed interpreter, any later `uv python` reinstall/upgrade
     changes the path and the grant must be redone - this is a known
     limitation of this option, flagged by doctor's "Interpreter identity"
     WARN, not a sign the fix failed.
2. **Use a bundle-identified interpreter** (a Homebrew framework build of
   Python, invoked via a stable venv path so it re-execs through
   `Python.app`) instead of the `uvx`-managed interpreter from
   `manifest.json`. This is the only configuration with direct evidence
   (TCC.db) of a currently-granted, version-independent identity
   (`org.python.python`), so the grant should survive interpreter patch
   upgrades and Claude Desktop restarts - trading step 1's per-upgrade
   redo for a one-time interpreter-choice change.
3. **Pin the `uv`-managed interpreter to a stable location**, if `uv`/`uvx`
   must remain the launch mechanism. This is the findings' uv-pinning
   recommendation and is not yet implemented or verified - tracked
   separately as hq-gxt.5; it would avoid step 1's per-upgrade FDA redo
   without switching away from `uv`.
4. **Run the server as a `launchd` LaunchAgent over HTTP transport**, for a
   fully unattended/headless setup - the always-running form of "run from
   Terminal": a Terminal-launched process already has disk access, and a
   LaunchAgent launches the same way (not via Claude Desktop's `disclaimer`
   helper), so it inherits whatever grant was made under step 1 or 2 for the
   interpreter it invokes - **Full Disk Access still applies to that
   interpreter binary**, this step only removes the `disclaimer` hop.

   Minimal LaunchAgent plist example
   (`~/Library/LaunchAgents/com.example.mcp-server-things.plist`), running
   the same command as README's HTTP-transport option:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
     <key>Label</key>
     <string>com.example.mcp-server-things</string>
     <key>ProgramArguments</key>
     <array>
       <string>/usr/bin/env</string>
       <string>uvx</string>
       <string>mcp-server-things</string>
     </array>
     <key>EnvironmentVariables</key>
     <dict>
       <key>THINGS_MCP_TRANSPORT</key>
       <string>http</string>
       <key>THINGS_MCP_PORT</key>
       <string>8000</string>
     </dict>
     <key>RunAtLoad</key>
     <true/>
     <key>KeepAlive</key>
     <true/>
   </dict>
   </plist>
   ```
   Load it with `launchctl load ~/Library/LaunchAgents/com.example.mcp-server-things.plist`.
   Then bridge Claude Desktop (or any stdio-only client) to it with
   [`mcp-remote`](https://www.npmjs.com/package/mcp-remote):
   ```bash
   npx mcp-remote http://127.0.0.1:8000/mcp
   ```
   or point Claude Code directly at the HTTP endpoint:
   ```bash
   claude mcp add --transport http things http://127.0.0.1:8000/mcp
   ```

## Resetting

If a grant seems stuck in a bad state, reset it and start over:

```bash
tccutil reset AppleEvents            # clears all Automation (AppleScript) grants for every app
tccutil reset SystemPolicyAllFiles   # clears all Full Disk Access grants for every app
tccutil reset SystemPolicyAppData    # clears all "access data from other apps" grants for every app
```

Each of these resets the named service **system-wide** (all apps, not just
this server) - macOS provides no narrower per-app reset for these services
from the command line. After resetting, the next write (`AppleEvents`) or
read (`SystemPolicyAppData`/`SystemPolicyAllFiles`, depending on which path
your read failures are keyed to) will re-trigger the corresponding dialog so
you can grant it again cleanly.

## How to verify

**`mcp-server-things doctor`**, healthy:
- "Interpreter identity" reports PASS (unless `uv-managed`, which reports
  WARN even when currently working, since the grant is fragile) with the
  resolved path and classification (`uv-managed` / `venv` / `framework` /
  `other`).
- "Launch parent" reports INFO with the launch chain when no `disclaimer`
  helper is present, or WARN naming `disclaimer` when it is.
- The database-readability check reports PASS.

**`mcp-server-things doctor`, denied:** the database-readability check
FAILs and classifies the cause - a macOS privacy (TCC) denial
(`PermissionError`, errno `EPERM`/`EACCES`) is reported distinctly from a
missing database file (`FileNotFoundError`), with a fix hint pointing at the
"Interpreter identity" row's path.

**In a tool response:** a read tool that hits a TCC denial returns a
structured error instead of results:

```json
{
  "success": false,
  "error": "database_access_denied",
  "message": "macOS privacy settings are blocking access to the Things database",
  "hint": "Grant Full Disk Access to <interpreter path>; run `mcp-server-things doctor` for diagnostics; see docs/MACOS_PERMISSIONS.md.",
  "interpreter": "<interpreter path>"
}
```

## Interactive verification matrix (not yet verified)

The rows below describe scenarios that require an operator to click through
dialogs and relaunch Claude Desktop - they have **not** been observed live.
`hq-gxt.7` will run these and record actual results here.

| Row | Scenario | Status | Operator steps |
|---|---|---|---|
| (a) | Allow the AppData prompt, then quit and relaunch Claude Desktop entirely - does it re-prompt? | not yet verified | 1. Quit Claude Desktop fully (Cmd-Q; confirm no background helper remains via `pgrep -fl things_mcp`). 2. Relaunch Claude Desktop and invoke any Things MCP tool. 3. Watch for the "python wants access to other apps' data" dialog; click **Allow** if shown. 4. Quit and relaunch Claude Desktop a second time and repeat step 3 - record whether the dialog reappears. |
| (b) | Grant Full Disk Access to the realpath python3.12 binary, then relaunch Claude Desktop - does it re-prompt? | not yet verified | 1. Run `scripts/tcc_probe.sh` and note the resolved realpath under section 1. 2. Open System Settings > Privacy & Security > Full Disk Access. 3. Click "+", press Cmd-Shift-G, paste that exact path, and add it. 4. Quit and relaunch Claude Desktop. 5. Invoke a Things MCP tool and record whether the AppData prompt still appears. Caveat: if `uv` later reinstalls/upgrades this interpreter, the path (and this FDA grant) becomes stale and the new path needs to be added again - expected, not a failure. |
| (c) | Launch via a stable framework-Python path instead of the manifest.json `uvx` default, then relaunch Claude Desktop - does it re-prompt? | not yet verified | 1. Confirm the server config uses a framework-build interpreter (e.g. `venv/bin/python -m things_mcp` where the venv points at a Homebrew framework Python), not `uvx`. 2. Quit and relaunch Claude Desktop. 3. Invoke a Things MCP tool and record whether any AppData prompt appears. |

---

Folded in from `docs/MACOS_PERMISSIONS_FINDINGS.md` (hq-gxt.1's investigation
notes); that file has been deleted, but its full content - including the raw
TCC.db rows, unified-log excerpts, and interpreter codesign output backing
the claims above - remains available in git history.
