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

## Stop the dialog (verified procedure)

This is the fix. Verified on macOS 26.6, 2026-09-09/10, on one machine: with
Full Disk Access granted to the exact interpreter Claude Desktop launches,
the "would like to access data from other apps" dialog did not appear across
multiple relaunches; toggling that same grant off brought the dialog back
immediately on the next relaunch. Clicking **Allow** on the dialog itself was
also tried, three separate times across relaunches, and never stopped the
dialog from returning - **clicking Allow is not a fix**. Read the "Risks"
section below before doing this - granting Full Disk Access to a Python
interpreter is a broad grant, not a narrow one.

1. Find the exact interpreter file Claude Desktop launches. In order of
   preference:
   - Run `mcp-server-things doctor` and read the line starting
     `GRANT FULL DISK ACCESS TO THIS FILE:` (also echoed in the footer line
     `Full Disk Access target for Claude Desktop: <path>`).
   - Or resolve it yourself: read the `command`/`args` for this server out of
     `claude_desktop_config.json` and run `readlink -f <command>`.
   - Or run `scripts/tcc_probe.sh` for a read-only snapshot.
2. In Finder, press **Cmd+Shift+G** and paste the directory containing that
   file (the path above, minus the filename).
3. Open **System Settings > Privacy & Security > Full Disk Access**. Cancel
   the "+" picker if it's open (it greys out `python3.X` - see the callout
   in the fix ladder below for why), and instead **drag the real
   `python3.X` file directly from the Finder window** onto the Full Disk
   Access list. Never drag it via a drag-shelf or clipboard utility (Yoink,
   Dropover, etc.) - doing so can quarantine the file and cause every
   invocation to be SIGKILLed.
4. Toggle the switch next to it **on**.
5. Quit Claude Desktop completely and relaunch it.
6. Verify: run `mcp-server-things doctor` again (the database-readability
   check should PASS), or invoke any read tool (e.g. `get_today`) and
   confirm no dialog appears.

## Risks of granting Full Disk Access to a Python interpreter

Full Disk Access is a broad, all-or-nothing grant - there is no way to scope
it to a single folder or app's data. Before granting it, understand what you
are actually authorizing:

1. **The grant applies to every program run with that interpreter, not just
   this server.** Any script or package ever executed with that exact
   `python3.X` binary - including anything malicious that gets executed by
   it, now or later - inherits the same access: Mail, Messages, Safari
   history, other apps' containers, and Time Machine backups are all in
   scope, not only the Things 3 database.
2. **The binary is ad-hoc signed.** `codesign -dv` on a bare `python3.X`
   interpreter reports `flags=adhoc` and no `TeamIdentifier` - macOS has no
   cryptographic way to notice if that file is later replaced or modified,
   unlike a grant to a binary with a real Developer ID or Team ID.
3. **The grant is keyed to the resolved realpath and is silently lost on
   interpreter upgrades** (see "Why it recurs" below) - this trains users to
   re-grant reflexively on the next new path without stopping to check what
   they're granting it to.
4. **On a shared or headless/always-on machine, anyone who can run that
   interpreter** - locally, or via remote access - **inherits the access**
   too; the grant is not scoped to Claude Desktop's use of it.

Mitigations:
- **Dedicate an interpreter/venv to this server only** - not the system
  Python or your daily-use interpreter - so the grant covers as little as
  possible.
- **Review System Settings > Full Disk Access periodically** and remove
  stale versioned entries left behind by old interpreter upgrades.
- **Remove the grant when the server is uninstalled.**
- The `launchd` LaunchAgent + HTTP transport option (fix ladder step 4
  below) is **not yet verified to avoid Full Disk Access** - do not rely on it
  rather than implying it's a way around this section; it still requires
  Full Disk Access on the interpreter it invokes, it only removes the
  `disclaimer` hop.
- There is no way to scope Full Disk Access to a single folder; the
  mitigations above reduce blast radius, they do not eliminate it.

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

**What this dialog gates:** the Things 3 SQLite database, which lives inside
Things' own Group Container
(`~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/...`) - on
macOS 15+, that's classified as "another app's data" (`kTCCServiceSystemPolicyAppData`),
which is exactly what this dialog's wording describes.

**Choosing Don't Allow only breaks reads.** Write tools (`add_todo`,
`update_todo`, ...) go through AppleScript, gated separately by dialog 1
above, and continue to work normally; only the `things.py`-backed read tools
(`get_today`, `search_todos`, etc.) fail with `database_access_denied`.

**Why it reappears is not fully explained.** Clicking Allow does write a row
to the user's `TCC.db` for the resolved interpreter path, but that row does
not reliably stop the dialog from reappearing on the next Claude
Desktop-launched relaunch (see "Stop the dialog" above - Allow was clicked
three times across relaunches and the dialog kept returning). One candidate
mechanism, observed but not confirmed as the full explanation: a first Allow
click recorded a row with no code-signing requirement (`csreq NULL`) in
`TCC.db`; a later Allow click on the same path *did* record a 40-byte csreq,
and the dialog still came back. Since a row with a captured csreq recurred
just as a NULL-csreq row did, the presence or absence of a csreq alone does
not explain the recurrence - the actual mechanism by which a
disclaimer-launched process's Allow decision fails to persist is not fully
understood. Interpreter path stability (below) is a secondary, better-understood
contributor: an upgrade changes the path outright and invalidates any grant
keyed to it, Allow or Full Disk Access alike.

**3. Full Disk Access** (System Settings pane: **Privacy & Security > Full
Disk Access**) - not a dialog you click through in the moment; it's a
System Settings toggle you add the interpreter binary to yourself (see the
fix ladder below). Things 3's database lives under another app's protected
container, so reads need this grant, not just the Automation grant.

## (b) Why the prompt comes back after a restart

Live click-through-and-relaunch testing (hq-gxt.7, 2026-09-09/10) confirmed
the fix: granting Full Disk Access to the exact interpreter Claude Desktop
launches stops the dialog; that same grant, toggled off, brings it back. The
*full* mechanism behind per-launch recurrence when only Allow (not Full Disk
Access) is granted is not fully understood - see the "Why it reappears is not
fully explained" note under dialog (2) above for what was and wasn't
confirmed about the `TCC.db` row itself. Interpreter path instability
(described below) is a distinct, well-understood, **secondary** cause: it
explains why even a successful Full Disk Access grant has to be redone after
an interpreter upgrade, not why the dialog recurs on every single relaunch
of an otherwise-unchanged interpreter.

Three mechanisms were observed directly (the `disclaimer` parent chain via
`ps`, interpreter code-signing/path identity via `codesign`, and TCC.db
`access` rows for python clients) during the hq-gxt.1 investigation:

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
> check above when deciding which file to grant Full Disk Access to.

Ordered per the hq-gxt.1 findings, corrected by live observation
(hq-gxt.7/hq-gxt.10, 2026-09-09 - see the matrix and "What we observed on a
real machine" below):

1. **VERIFIED (one machine, macOS 26.6, 2026-09-09/10): grant Full Disk
   Access to the exact realpath interpreter Claude Desktop launches** -
   dragged directly from Finder (System Settings > Privacy & Security >
   Full Disk Access). This is the primary recommendation; see "Stop the
   dialog" above for the numbered procedure and the exact evidence
   (FDA on -> no dialog across relaunches; FDA off -> dialog returns;
   Allow-only, tried three times, never persisted):
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
     "Interpreter identity" check WARNs for both `uv-managed` and `framework`
     interpreters for this reason (hq-b49) - a WARN there is a reminder to
     re-grant after the next upgrade, not a failure.
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
4. **NOT YET VERIFIED to avoid the dialog: run the server as a `launchd`
   LaunchAgent over HTTP transport**, for a fully unattended/headless setup -
   the always-running form of "run from Terminal": a Terminal-launched
   process already has disk access, and a LaunchAgent launches the same way
   (not via Claude Desktop's `disclaimer` helper), so it inherits whatever
   grant was made under step 1 or 2 for the interpreter it invokes - **Full
   Disk Access still applies to that interpreter binary**, this step only
   removes the `disclaimer` hop. This has not been tried live; do not assume
   it avoids Full Disk Access or the dialog until it has been.

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
- "Interpreter identity" reports PASS (unless `uv-managed` or `framework`,
  which both report WARN even when currently working, since the grant is
  fragile) with the resolved path and classification (`uv-managed` / `venv`
  / `framework` / `other`).
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

All rows below have now been observed live (hq-gxt.7, macOS 26.6,
2026-09-09/10) except where noted - only a reboot test remains untested.

| Row | Scenario | Status | Operator steps / observation |
|---|---|---|---|
| (a) | Allow the AppData prompt only (no Full Disk Access), then quit and relaunch Claude Desktop entirely - does it re-prompt? | **observed: prompt returns** | Clicked Allow on the "would like to access data from other apps" dialog, quit and relaunched Claude Desktop, and repeated across three separate relaunches - the dialog reappeared every time, whether or not the underlying `TCC.db` row happened to carry a code-signing requirement (csreq). Allow alone does not stop the dialog. |
| (b) | Grant Full Disk Access to the exact realpath interpreter Claude Desktop launches, then relaunch Claude Desktop - does it re-prompt? | **observed: no prompt with FDA on; prompt returns with FDA off** | Dragged the exact Claude Desktop interpreter (`/opt/homebrew/Cellar/python@3.13/3.13.15/.../bin/python3.13`) directly from Finder onto the Full Disk Access list, toggled it on, quit and relaunched Claude Desktop, invoked a read tool - no dialog. Toggling that same Full Disk Access entry **off** and relaunching brought the dialog back immediately. This is the verified fix (see "Stop the dialog" above). Caveat unchanged: if the interpreter is later upgraded, the path (and this FDA grant) becomes stale and the new path needs to be added again - expected, not a failure. |
| (c) | Launch via a stable framework-Python path (`venv/bin/python` resolving to a Homebrew framework build) instead of a `uvx`-managed interpreter - does it re-prompt? | **observed** | This *was* the actual configuration under test throughout hq-gxt.7: Claude Desktop's configured `venv/bin/python` resolves to the Homebrew framework realpath. The framework build did not change rows (a)/(b)'s outcome - the dialog behaves the same way for a framework-build interpreter as for a `uvx`-managed one, keyed to its resolved realpath either way (see "Why it recurs" above). |
| (d) | Grant Full Disk Access via drag-and-drop (the picker greys out `python3.X`) to a uv-managed interpreter - does the grant register and take effect? | **observed** | Dragged `~/.local/share/uv/python/cpython-3.11.13-macos-aarch64-none/bin/python3.11` directly from a Finder window onto the Full Disk Access list. System TCC.db recorded `kTCCServiceSystemPolicyAllFiles`, `auth_value=2`, at 20:32:31 - the grant registered correctly. It had no effect on a *different* interpreter's app-data prompt (see (e)), which is expected - FDA is still per-binary. |
| (e) | Launch via a stable symlink path (`uv tool install`, `venv/bin/python`) instead of the versioned realpath - does the TCC grant key on the symlink path or the resolved realpath, and does a framework build's `org.python.python` bundle-id grant survive a patch upgrade? | **observed** | Claude Desktop's configured `venv/bin/python` resolved to the Homebrew framework realpath `.../Cellar/python@3.13/3.13.15/Frameworks/Python.framework/Versions/3.13/bin/python3.13`. 55s after the FDA grant in (d) (made to a *different*, python3.11 interpreter), the app-data dialog fired for this python3.13 process; clicking Allow wrote a user TCC.db row keyed to that exact Cellar realpath (`kTCCServiceSystemPolicyAppData`, `client_type=1`) at 20:33:26 - **not** to `venv/bin/python` or the `/opt/homebrew/opt/...` symlink. This is the third such path-keyed row observed across three separate Homebrew `python@3.13` patch upgrades (3.13.11, 3.13.12_1, 3.13.15); a pre-existing `org.python.python` (`client_type=0`) row from an earlier upgrade did not prevent this prompt. Conclusion: TCC keys on the fully resolved realpath, not a stable symlink or launch alias - a symlink-stable launch path does not avoid re-granting after an interpreter upgrade. Answered by this realpath-keying evidence; the specific `uv tool install` symlink variant described in the scenario column was not run separately as its own experiment. |
| (reboot) | Does a full machine reboot change any of the above? | **untested** | Not attempted; treat as unverified. |

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
- 2026-09-09 23:13: with Full Disk Access granted only to the *doctor*
  interpreter (a `uv`-managed `python3.12`, not the interpreter Claude
  Desktop actually launches), invoking a read tool re-triggered the
  app-data dialog for `python3.13`. User `TCC.db` rewrote the same
  (service, client) row at 23:14:01 with `csreq NULL`.
- 2026-09-09 23:53: an Allow click on that same dialog, before any correct
  Full Disk Access grant existed, captured a 40-byte csreq this time. Earlier
  Allow clicks (with and without a stored csreq) had all been followed by the
  dialog reappearing on the next relaunch (row (a) above, observed three
  times), so the presence of a csreq is not what stops the recurrence - the
  Full Disk Access grant below is.
- 2026-09-09 23:57:28: Full Disk Access (`kTCCServiceSystemPolicyAllFiles`,
  `auth_value=2`, `csreq` 40 bytes) granted directly to the exact Claude Desktop interpreter
  (`.../python@3.13/3.13.15/.../bin/python3.13`), dragged from Finder. The
  next relaunch produced no dialog. Toggling this grant off and relaunching
  again reproduced the dialog. This is the disambiguating pair of
  observations behind the "Stop the dialog" procedure and row (b) above.

---

Folded in from `docs/MACOS_PERMISSIONS_FINDINGS.md` (hq-gxt.1's investigation
notes); that file has been deleted, but its full content - including the raw
TCC.db rows, unified-log excerpts, and interpreter codesign output backing
the claims above - remains available in git history.
