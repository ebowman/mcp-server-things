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
- **Every bare Python interpreter is ad-hoc signed and keyed by realpath**,
  so a grant made to it is lost after that interpreter is upgraded - this is
  true of the `uvx`-managed interpreter *and* a Homebrew framework build,
  not just the former. `uvx`'s resolved interpreter has no code-signing Team
  ID and isn't wrapped in an `.app` bundle (`codesign -dv` reports
  `Signature=adhoc`, `TeamIdentifier=not set`, `Identifier=-`), so TCC falls
  back to identifying the process **by its exact executable path** - a path
  like `~/.local/share/uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12`
  that embeds the exact patch version. Any `uv python install --reinstall`,
  or uv simply resolving a newer patch release later, changes this path
  outright, so the previous grant no longer matches anything and macOS
  treats the "new" path as a never-before-seen program requiring a fresh
  prompt.

  It is tempting to assume a Homebrew **framework** build of Python avoids
  this, since it re-execs through a bundled `Python.app` carrying a stable
  `CFBundleIdentifier` of `org.python.python`. **Live evidence refutes
  that** (hq-gxt.7/hq-gxt.10, 2026-09-09): the bare interpreter binary
  itself (e.g. `.../Frameworks/Python.framework/Versions/3.13/bin/python3.13`)
  is a *separately* ad-hoc-signed stub, not the `Python.app` bundle -
  `codesign -dv` reports its own `Identifier` (e.g. `python3-5555...`,
  `flags=adhoc`), distinct from `org.python.python`. The app-data TCC grant
  this server actually needs is keyed to that stub's realpath, exactly like
  the `uvx`-managed case, and a pre-existing `org.python.python` grant does
  not cover it. **There is no known upgrade-proof identity for a bare
  python interpreter, uv-managed or Homebrew framework** - every one of
  three observed Homebrew `python@3.13` patch upgrades on the investigation
  machine produced its own new path-keyed grant requirement (see "What we
  observed on a real machine" below). `mcp-server-things doctor`'s
  "Interpreter identity" check reports the exact resolved binary path and
  classifies it as `uv-managed`, `venv`, `framework`, or `other` - the
  classification is informational (which kind of interpreter this is), not
  a stability guarantee.

## (c) Fix ladder for an unattended/headless Mac

> **Grant it to the RIGHT interpreter.** Every step below only works if you
> grant Full Disk Access to the exact binary Claude Desktop itself will run
> - not whatever `python`/`python3` happens to be on your terminal's PATH,
> and not a venv you invoke `doctor` from interactively. Find that exact
> path with, in order of preference:
> 1. `mcp-server-things doctor`'s **"Claude Desktop interpreter"** check -
>    it reads `claude_desktop_config.json` (and any installed `.mcpb`
>    manifest) directly and prints `Claude Desktop will run: <path> - grant
>    Full Disk Access to THIS file`.
> 2. `scripts/tcc_probe.sh` for a read-only snapshot you can paste back for
>    troubleshooting.
> 3. Manually: read the `command`/`args` for this server out of
>    `claude_desktop_config.json`, then resolve it yourself with
>    `readlink -f <command>` (or, for the `.mcpb`/`uvx` case, let `doctor`'s
>    bounded `uvx`/`uv` probe do this resolution for you - it invokes the
>    same `uvx` command Claude Desktop would and reports the interpreter it
>    resolves to).
>
> `doctor`'s "Interpreter identity" check instead reports the interpreter
> running `doctor` itself, which is frequently a *different* binary (e.g. a
> project venv) - useful for understanding what kind of interpreter you're
> looking at, but not a substitute for the "Claude Desktop interpreter"
> check above when deciding where to click "Allow".

Ordered per the hq-gxt.1 findings, corrected by live observation
(hq-gxt.7/hq-gxt.10, 2026-09-09 - see the matrix and "What we observed on a
real machine" below):

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

     > **The picker will not let you select `python3.X`.** Cause: Launch
     > Services parses the trailing `.11`/`.12` in the filename as a file
     > extension rather than part of the interpreter's name, so the binary
     > gets classified as a generic document type instead of a Unix
     > executable - even though it's a real Mach-O executable. Confirmed
     > 2026-09-09 on macOS 26.6: `mdls -name kMDItemContentType
     > <path-to-python3.X>` reports a `dyn.*` dynamic type synthesized
     > per-extension (e.g. `dyn.ah62d4rv4ge8xcqk` for `.11`,
     > `dyn.ah62d4rv4ge8xcqu` for `.12` - the exact string varies by
     > extension, it is not one fixed UTI), with a type tree of only
     > `public.item`/`public.data` (no `public.executable`), while a
     > sibling binary without a numeric suffix (e.g. `pip3` in the same
     > directory) correctly reports `public.unix-executable`; the "+"
     > picker's Kind column shows `python3.X` as "Document" and greys it
     > out accordingly. Workaround (verified working - creates a real TCC
     > grant, `auth_value 2`, same as picker-based grants):
     > 1. Open Finder, press Cmd+Shift+G, and paste the *directory*
     >    containing the interpreter (the path `mcp-server-things doctor`
     >    printed, minus the filename).
     > 2. Back in System Settings, cancel the "+" picker dialog.
     > 3. Drag the real `python3.X` file (not the `python3` alias/symlink)
     >    from that Finder window directly onto the Full Disk Access list.
     >    **Drag directly from the Finder window - never via a drag-shelf
     >    or clipboard utility (Yoink, Dropover, etc.)**: these can re-stamp
     >    the file with a `com.apple.quarantine` attribute as it passes
     >    through their shelf, which makes Gatekeeper (`spctl`) start
     >    rejecting the binary outright.
     > 4. Confirm the toggle next to it is switched on.
     >
     > **If the interpreter stops launching afterwards:** the symptom is an
     > instant exit code `137` (SIGKILL) on every invocation, and `spctl -a
     > -v <path>` reports `rejected`. Check with `xattr -l <path>` - if you
     > see a `com.apple.quarantine` line, that's the cause. Fix with
     > `xattr -d com.apple.quarantine <path>`.
   - Quit and relaunch Claude Desktop, then run `mcp-server-things doctor`
     again to verify the database-readability check now PASSes.
   - **Caveat:** this grant is keyed to the resolved path of whichever
     interpreter you granted it to. Any later patch upgrade of that
     interpreter - the `uvx`-managed interpreter, **or** a Homebrew
     framework build - changes its resolved path and the grant must be
     redone (see step 2 below and the live evidence there); this is a known
     limitation of this option, not a sign the fix failed. `doctor`'s
     "Interpreter identity" check currently only WARNs for this on
     `uv-managed` (tracked separately for `framework` as hq-b49) - a PASS
     there does not mean the grant is upgrade-proof.
2. **There is no known upgrade-proof alternative interpreter to switch to.**
   Any bare interpreter - `uv`-managed or a Homebrew framework build of
   Python, invoked via a venv or otherwise - is keyed by TCC to its resolved
   realpath and must be re-granted after that interpreter is next upgraded;
   live evidence (hq-gxt.7) shows this held true across three separate
   Homebrew `python@3.13` patch upgrades even though the framework build's
   `Python.app` carries a stable `org.python.python` bundle id, because the
   bare `bin/python3.13` binary itself is a separately ad-hoc-signed stub
   not covered by that bundle id. Switching interpreters does not turn step
   1 into a one-time cost - budget for re-granting Full Disk Access after
   every interpreter patch upgrade, whichever interpreter you choose.
3. **Pinning the `uv`-managed interpreter to a stable symlink path does not
   help.** A natural next idea is a launch path that stays fixed across
   upgrades (`uv tool install ... --python 3.12`'s
   `~/.local/share/uv/tools/.../bin/python3.12` symlink, or a project
   `venv/bin/python`) so the grant, keyed to that fixed path, survives an
   underlying interpreter upgrade. Live evidence refutes this: TCC records
   the fully resolved realpath the symlink points at (the versioned Cellar
   path), not the stable symlink path itself - a grant made to the symlink
   path is never actually consulted, and the real per-upgrade path still
   needs re-granting. This is not implemented or planned for that reason.
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

## Interactive verification matrix

Rows (a)-(c) describe scenarios that require an operator to click through
dialogs and relaunch Claude Desktop and have **not** been observed live yet
(`hq-gxt.7` remains open to run them). Rows (d) and (e) below **were**
observed live on 2026-09-09 (macOS 26.6) - see "What we observed on a real
machine" for the underlying TCC.db rows.

| Row | Scenario | Status | Operator steps / observation |
|---|---|---|---|
| (a) | Allow the AppData prompt, then quit and relaunch Claude Desktop entirely - does it re-prompt? | not yet verified | 1. Quit Claude Desktop fully (Cmd-Q; confirm no background helper remains via `pgrep -fl things_mcp`). 2. Relaunch Claude Desktop and invoke any Things MCP tool. 3. Watch for the "python wants access to other apps' data" dialog; click **Allow** if shown. 4. Quit and relaunch Claude Desktop a second time and repeat step 3 - record whether the dialog reappears. |
| (b) | Grant Full Disk Access to the realpath python3.12 binary, then relaunch Claude Desktop - does it re-prompt? | not yet verified | 1. Run `scripts/tcc_probe.sh` and note the resolved realpath under section 1. 2. Open System Settings > Privacy & Security > Full Disk Access. 3. Click "+", press Cmd-Shift-G, paste that exact path, and add it. 4. Quit and relaunch Claude Desktop. 5. Invoke a Things MCP tool and record whether the AppData prompt still appears. Caveat: if `uv` later reinstalls/upgrades this interpreter, the path (and this FDA grant) becomes stale and the new path needs to be added again - expected, not a failure. |
| (c) | Launch via a stable framework-Python path instead of the manifest.json `uvx` default, then relaunch Claude Desktop - does it re-prompt? | not yet verified | 1. Confirm the server config uses a framework-build interpreter (e.g. `venv/bin/python -m things_mcp` where the venv points at a Homebrew framework Python), not `uvx`. 2. Quit and relaunch Claude Desktop. 3. Invoke a Things MCP tool and record whether any AppData prompt appears. |
| (d) | Grant Full Disk Access via drag-and-drop (the picker greys out `python3.X`) to a uv-managed interpreter - does the grant register and take effect? | **observed** | Dragged `~/.local/share/uv/python/cpython-3.11.13-macos-aarch64-none/bin/python3.11` directly from a Finder window onto the Full Disk Access list. System TCC.db recorded `kTCCServiceSystemPolicyAllFiles`, `auth_value=2`, at 20:32:31 - the grant registered correctly. It had no effect on a *different* interpreter's app-data prompt (see (e)), which is expected - FDA is still per-binary. |
| (e) | Launch via a stable symlink path (`uv tool install`, `venv/bin/python`) instead of the versioned realpath - does the TCC grant key on the symlink path or the resolved realpath, and does a framework build's `org.python.python` bundle-id grant survive a patch upgrade? | **observed** | Claude Desktop's configured `venv/bin/python` resolved to the Homebrew framework realpath `.../Cellar/python@3.13/3.13.15/Frameworks/Python.framework/Versions/3.13/bin/python3.13`. 55s after the FDA grant in (d) (made to a *different*, python3.11 interpreter), the app-data dialog fired for this python3.13 process; clicking Allow wrote a user TCC.db row keyed to that exact Cellar realpath (`kTCCServiceSystemPolicyAppData`, `client_type=1`) at 20:33:26 - **not** to `venv/bin/python` or the `/opt/homebrew/opt/...` symlink. This is the third such path-keyed row observed across three separate Homebrew `python@3.13` patch upgrades (3.13.11, 3.13.12_1, 3.13.15); a pre-existing `org.python.python` (`client_type=0`) row from an earlier upgrade did not prevent this prompt. Conclusion: TCC keys on the fully resolved realpath, not a stable symlink or launch alias - a symlink-stable launch path does not avoid re-granting after an interpreter upgrade. Answered by this realpath-keying evidence; the specific `uv tool install` symlink variant described in the scenario column was not run separately as its own experiment. |

## What we observed on a real machine

Live TCC.db observations from `<user>`'s Mac, 2026-09-09, macOS 26.6 (paths
generalised to `<user>`, no secrets):

- User `TCC.db`, `kTCCServiceSystemPolicyAppData`, `client_type=1` (path-keyed),
  one row per Homebrew `python@3.13` patch upgrade: `3.13.11` (2026-02-25),
  `3.13.12_1` (2026-07-19), `3.13.15` (2026-09-09 20:33:26).
- A separate `org.python.python` row (`client_type=0`, dated 2026-08-13) did
  **not** prevent the 2026-09-09 prompt for `3.13.15` - `codesign` on the
  Cellar `bin/python3.13` binary reports `Identifier=python3-5555...`,
  `flags=adhoc`: an ad-hoc-signed stub, not the `Python.app` bundle that
  `org.python.python` actually names.
- TCC recorded the fully resolved realpath (the versioned Cellar path) in
  every row above - never `venv/bin/python`, nor an `/opt/homebrew/opt/...`
  symlink.
- System `TCC.db`, `kTCCServiceSystemPolicyAllFiles`, `auth_value=2`,
  20:32:31: the Full Disk Access drag-and-drop workaround (see the fix
  ladder's callout above) for a uv-managed `python3.11`, confirming the
  workaround produces a real grant indistinguishable from a picker-based one.

---

Folded in from `docs/MACOS_PERMISSIONS_FINDINGS.md` (hq-gxt.1's investigation
notes); that file has been deleted, but its full content - including the raw
TCC.db rows, unified-log excerpts, and interpreter codesign output backing
the claims above - remains available in git history.
