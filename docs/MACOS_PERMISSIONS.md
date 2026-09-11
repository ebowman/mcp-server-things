# macOS permissions: the three dialogs, why they recur, and how to fix a headless Mac

This server talks to Things 3 via AppleScript (writes) and reads the Things
SQLite database directly via `things.py` (reads). Both paths are gated by
macOS's TCC (Transparency, Consent, and Control) privacy system, which is
why you may see one or more of the dialogs below - and, on some machines,
see them come back after a Claude Desktop restart even though you already
clicked Allow.

## Symptoms

| Operation | Result |
|---|---|
| Read tools (`get_today`, `get_inbox`, `search_todos`, ...) | Fail instantly with `unable to open database file`, or a structured `database_access_denied` error (see "Verify and reset" below) |
| Write tools (`add_todo`, `update_todo`, ...) | Work normally |
| URL-scheme features needing the auth token | Also fail (the token is read from the same database) |

If grepping logs, look for `unable to open database file` (the raw
`things.py`/sqlite error) or `database_access_denied` (this server's error
code for the same cause).

## Stop the dialog (verified procedure)

This is the fix. Verified on macOS 26.6, on one machine: with Full Disk
Access granted to the exact interpreter Claude Desktop launches, the "would
like to access data from other apps" dialog did not appear across multiple
relaunches; toggling that grant off brought the dialog back immediately on
the next relaunch. Clicking **Allow** on the dialog itself was also tried
three times across relaunches, and never stopped the dialog from returning
- **clicking Allow is not a fix**. Read "Risks" below before doing this -
granting Full Disk Access to a Python interpreter is a broad grant, and you
must grant it to the **right** interpreter.

1. Find the exact interpreter file Claude Desktop launches. Run
   `mcp-server-things doctor` and read the line starting
   `GRANT FULL DISK ACCESS TO THIS FILE:` (also echoed in the footer line
   `Full Disk Access target for Claude Desktop: <path>`). Or resolve it
   yourself: read the `command`/`args` for this server out of
   `claude_desktop_config.json` - if the command is `uvx` (the `.mcpb`
   bundle and the README's JSON snippet both use it), print the interpreter
   `uvx` selects with
   `uvx --python-preference only-managed --python 3.12 python -c "import os,sys;print(os.path.realpath(sys.executable))"`
   (adjust `--python` to match your `args`); if the command is a Python path
   of your own, run `readlink -f <command>` on it instead. Or run
   `scripts/tcc_probe.sh` for a read-only support bundle to paste into a bug
   report. (`doctor`'s separate **"Interpreter identity"** row is INFO-only
   and reports the interpreter running `doctor` itself, often a different
   binary such as a project venv - it never prints a grant instruction; use
   the **"Claude Desktop interpreter"** row above instead.)
2. In Finder, press **Cmd+Shift+G** and paste the directory containing that
   file (the path above, minus the filename).
3. Open **System Settings > Privacy & Security > Full Disk Access**. Click
   "+"; if the picker greys out `python3.X` (Launch Services misparses the
   trailing `.11`/`.12` as a file extension, not part of the name, so the
   file is classified as a document instead of an executable), cancel the
   picker and instead **drag the real `python3.X` file directly from the
   Finder window** onto the Full Disk Access list. Never drag it via a
   drag-shelf or clipboard utility (Yoink, Dropover, etc.) - doing so can
   quarantine the file and cause every invocation to be SIGKILLed (exit code
   137); check with `xattr -l <path>` and fix with
   `xattr -d com.apple.quarantine <path>` if this happens.
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
   `python3.X` binary - including anything malicious executed by it, now or
   later - inherits the same access: Mail, Messages, Safari history, other
   apps' containers, and Time Machine backups are all in scope, not only the
   Things 3 database.
2. **The binary is ad-hoc signed.** `codesign -dv` on a bare `python3.X`
   interpreter reports `flags=adhoc` and no `TeamIdentifier` - macOS has no
   cryptographic way to notice if that file is later replaced or modified,
   unlike a grant to a binary with a real Developer ID or Team ID.
3. **The grant is keyed to the resolved realpath and is silently lost on
   interpreter upgrades** (see "Why it recurs" below) - this trains users to
   re-grant reflexively without stopping to check what they're granting it
   to.
4. **On a shared or headless/always-on machine, anyone who can run that
   interpreter** - locally, or via remote access - **inherits the access**
   too; the grant is not scoped to Claude Desktop's use of it.

Mitigations:
- **Dedicate an interpreter/venv to this server only** - not the system
  Python or your daily-use interpreter - so the grant covers as little as
  possible.
- **Review System Settings > Full Disk Access periodically** and remove
  stale versioned entries; **remove the grant when the server is
  uninstalled.**
- See "Headless / unattended setup" below for the LaunchAgent option.
- There is no way to scope Full Disk Access to a single folder; these
  mitigations reduce blast radius, they do not eliminate it.

## The dialogs you may see

**1. Automation (AppleScript writes, e.g. `add_todo`/`update_todo`):**

> "Claude" wants access to control "Things3".

Click **Allow**. This is a one-time prompt - AppleScript is what enables
`delete_todo`, `move_record`/`bulk_move_records`, `remove_tags`, and real
IDs returned synchronously, at the cost of this prompt.

**2. App-data protection (reads, macOS 15+, `kTCCServiceSystemPolicyAppData`):**

> "python3.12" would like to access data from other apps.

Russian wording (for grepping non-English screenshots/logs):

> «Приложение «python3.12» запрашивает доступ к данным других приложений.»

Buttons: «Разрешить» / «Не разрешать» (Allow / Don't Allow).

**What this dialog gates:** the Things 3 SQLite database, which lives inside
Things' own Group Container
(`~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/...`) -
on macOS 15+ that's classified as "another app's data"
(`kTCCServiceSystemPolicyAppData`), which is what the dialog's wording
describes. **Choosing Don't Allow only breaks reads** - write tools go
through AppleScript, gated separately by dialog 1 above, and keep working;
only `things.py`-backed read tools fail with `database_access_denied`.

**3. Full Disk Access** (System Settings pane: **Privacy & Security > Full
Disk Access**) - not a dialog you click through in the moment; it's a
System Settings toggle you add the interpreter binary to yourself (see
"Stop the dialog" above). Things 3's database lives under another app's
protected container, so reads need this grant, not just the Automation
grant.

## Why it recurs

Clicking Allow on the app-data dialog writes a row to the user's `TCC.db`
for the resolved interpreter path, but that row does not reliably stop the
dialog from reappearing on the next Claude Desktop-launched relaunch: Allow
was clicked three times across relaunches (once recording a row with no
code-signing requirement, `csreq NULL`, later a 40-byte csreq) and the
dialog kept returning both times. Since the presence or absence of a csreq
made no difference, the exact mechanism by which a disclaimer-launched
process's Allow decision fails to persist is not fully understood. What is
understood:

- **Claude Desktop launches MCP servers via its `disclaimer` helper**
  (`/Applications/Claude.app/Contents/Helpers/disclaimer --pgroup -- <python>
  -m things_mcp`), so the Python interpreter - not Claude.app - is the TCC
  principal, and does **not** inherit Claude.app's own Full Disk Access
  grant even though Claude.app itself has one. `doctor`'s "Launch parent"
  check detects this by walking the process's parent chain and WARNs when
  it finds `disclaimer` in it.
- **The grant is path-keyed and is lost on interpreter upgrades** (secondary
  cause). Every bare Python interpreter is ad-hoc signed (`codesign -dv`
  reports `Signature=adhoc`, `TeamIdentifier=not set`), so TCC identifies it
  by its exact resolved executable path. A `uvx`-managed interpreter's path
  embeds its patch version
  (e.g. `.../cpython-3.12.11-macos-aarch64-none/bin/python3.12`); any
  reinstall or newer patch resolution changes that path and invalidates the
  previous grant. A Homebrew **framework** build does not avoid this: even
  though it re-execs through a bundled `Python.app` with a stable
  `CFBundleIdentifier` of `org.python.python`, the bare interpreter binary
  (e.g. `.../Frameworks/Python.framework/Versions/3.13/bin/python3.13`) is a
  *separately* ad-hoc-signed stub, and the app-data grant is keyed to that
  stub's realpath - a pre-existing `org.python.python` grant does not cover
  it. This held true across three separate Homebrew `python@3.13` patch
  upgrades on the investigation machine (see the appendix); there is no
  known upgrade-proof identity for a bare interpreter, `uv`-managed or
  Homebrew framework. A symlink-stable launch path doesn't help either: TCC
  records the fully resolved realpath a symlink points at, not the symlink
  itself, so a grant made to a stable symlink (`uv tool install`'s
  `.../tools/.../bin/python3.12`, or a project `venv/bin/python`) is never
  actually consulted.

## Headless / unattended setup

The Full Disk Access procedure in "Stop the dialog" above applies the same
way on a headless/unattended Mac. Steps 2-4 of that procedure (Finder and
System Settings) need a GUI session on the Mac - Screen Sharing/Remote
Desktop, or a physical login - to grant the permission once; after that,
the machine can run unattended. The grant survives Claude Desktop restarts
(observed) and a full reboot (confirmed by a user running the server
unattended on a headless Mac mini).

For a fully unattended setup with no Claude Desktop involved, run the
server as a `launchd` LaunchAgent over HTTP transport instead - it launches
the same way a Terminal process does (not via Claude Desktop's `disclaimer`
helper), so it inherits whatever Full Disk Access grant was made to the
interpreter it invokes. **It still requires Full Disk Access on that
interpreter and has not been verified live to avoid the dialog** - don't
assume it does until confirmed on your own machine.

Minimal LaunchAgent plist (`~/Library/LaunchAgents/com.example.mcp-server-things.plist`),
running the same command as README's HTTP-transport option:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.example.mcp-server-things</string>
  <key>ProgramArguments</key>
  <array><string>/usr/bin/env</string><string>uvx</string><string>mcp-server-things</string></array>
  <key>EnvironmentVariables</key>
  <dict><key>THINGS_MCP_TRANSPORT</key><string>http</string><key>THINGS_MCP_PORT</key><string>8000</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
```

Load it with `launchctl load ~/Library/LaunchAgents/com.example.mcp-server-things.plist`.
Then bridge Claude Desktop (or any stdio-only client) to it with
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote)
(`npx mcp-remote http://127.0.0.1:8000/mcp`), or point Claude Code directly
at the HTTP endpoint:

```bash
claude mcp add --transport http things http://127.0.0.1:8000/mcp
```

## Verify and reset

**`mcp-server-things doctor`**, healthy: "Interpreter identity" reports INFO
with the resolved path and classification (`uv-managed`/`venv`/`framework`/
`other`, never a grant instruction); "Launch parent" reports INFO with the
launch chain (or WARN naming `disclaimer`); the database-readability check
reports PASS.

**Denied:** the database-readability check FAILs and classifies the cause -
a TCC denial (`PermissionError`, errno `EPERM`/`EACCES`) is reported
distinctly from a missing database file (`FileNotFoundError`), with a fix
hint pointing at the "Claude Desktop interpreter" row's path.

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

**Resetting a stuck grant:**

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

If you need more than the checks above provide, `scripts/tcc_probe.sh` is a
read-only support bundle (raw `TCC.db` rows, `codesign`, and parent-chain
output) you can run and paste into a bug report.

## Appendix: what we observed

Live TCC.db observations on one machine, macOS 26.6 (paths generalised, no
usernames):

- User `TCC.db`, `kTCCServiceSystemPolicyAppData` (`client_type=1`,
  path-keyed): one row per Homebrew `python@3.13` patch upgrade
  (`3.13.11`, `3.13.12_1`, `3.13.15`). A separate `org.python.python` row
  (`client_type=0`) did **not** prevent the `3.13.15` prompt - the Cellar
  `bin/python3.13` binary is its own ad-hoc-signed stub, not that bundle.
- System `TCC.db`, `kTCCServiceSystemPolicyAllFiles`, `auth_value=2`: the
  drag-and-drop workaround for a uv-managed `python3.11` registered as a
  real grant, same as a picker-based one.
- FDA granted only to a *different* (doctor-only) interpreter still let a
  read tool re-trigger the app-data dialog (`csreq NULL`); a later Allow
  click captured a 40-byte csreq instead, and the dialog still reappeared
  next relaunch (three Allow clicks observed, none persisted).
- FDA (`auth_value=2`, `csreq` 40 bytes) granted directly to the exact
  Claude Desktop interpreter, dragged from Finder: next relaunch produced
  no dialog; toggling it off and relaunching reproduced it. Reboot survival
  confirmed on a second machine (headless Mac mini, user report).
