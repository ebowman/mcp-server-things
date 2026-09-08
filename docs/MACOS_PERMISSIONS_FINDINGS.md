# macOS TCC "app data" prompt - findings (hq-gxt.1)

**Status: temporary working file.** This will be folded into
`docs/MACOS_PERMISSIONS.md` and deleted by hq-gxt.4.

## Environment

- macOS 26.6, Apple Silicon (aarch64), Eric Bowman's machine.
- Claude Desktop launches this server per `manifest.json`:
  `uvx --python-preference only-managed --python 3.12 mcp-server-things`.
- Eric's *local* Claude Desktop config (observed via running processes, not
  the manifest default) instead launches
  `/Users/eric.bowman/Projects/src/mcp-server-things/venv/bin/python -m things_mcp`,
  where `venv/bin/python` resolves to a Homebrew **framework** build of
  Python 3.13 (`python@3.13` 3.13.15). These are two different interpreter
  provisioning strategies and, per the evidence below, they are identified
  completely differently by TCC.

## Interpreter identity

### A. `uvx`-managed Python 3.12 (the manifest.json default)

```
$ uvx --python-preference only-managed --python 3.12 python -c "import sys,os;print(sys.executable);print(os.path.realpath(sys.executable))"
/Users/eric.bowman/.cache/uv/archive-v0/m_SOCWFmC8LfTsBfwwTyD/bin/python
/Users/eric.bowman/.local/share/uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12
```

```
$ codesign -dv --verbose=2 /Users/eric.bowman/.local/share/uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12
Identifier=-
CodeDirectory v=20400 size=520 flags=0x20002(adhoc,linker-signed) hashes=13+0 location=embedded
Signature=adhoc
TeamIdentifier=not set
```

- **Ad-hoc signed**, no Team ID, no bundle (`Identifier=-`, plain executable,
  not a `.app`).
- The resolved realpath **embeds the exact patch version**:
  `cpython-3.12.11-macos-aarch64-none`. A `uv python install 3.12 --reinstall`,
  or uv simply picking up a newer 3.12 patch release later, changes this path
  outright - a structurally different filesystem location, not merely a
  different file at the same path.
- Because this binary is not wrapped in an `.app` bundle with a
  `CFBundleIdentifier`, TCC has no bundle identity to key off of and must
  fall back to identifying the requesting program **by its exact executable
  path** (confirmed in the TCC.db/log evidence below: `client_type=1`,
  "path" form, for every ad-hoc/bundle-less Python binary observed).

### B. Repo venv Python (`venv/bin/python`, Eric's actual local launch config)

```
$ realpath venv/bin/python
/opt/homebrew/Cellar/python@3.13/3.13.15/Frameworks/Python.framework/Versions/3.13/bin/python3.13
```

```
$ codesign -dv --verbose=2 <that path>
Identifier=python3-555549448fac8957486a32f0829dfa26484d693a
CodeDirectory v=20400 size=489 flags=0x2(adhoc) hashes=9+2 location=embedded
Signature=adhoc
TeamIdentifier=not set
```

Also ad-hoc, no Team ID. **However**, this is a Homebrew *framework* build of
Python, and `python -m things_mcp` under a framework build does not run as
this bare executable - it re-execs through the framework's bundled
`Python.app` launcher (confirmed via `ps`, see "Launch parent chain" below).
That `.app` bundle **does** carry a stable `CFBundleIdentifier`:

```
$ /usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" \
  ".../Python.framework/Versions/3.13/Resources/Python.app/Contents/Info.plist"
org.python.python
```

```
$ codesign -dv --verbose=2 ".../Python.app/Contents/MacOS/Python"
Identifier=Python-55554944ac3e9b01a26d3e329e62dc96ee48a15d
Signature=adhoc
TeamIdentifier=not set
```

The binary's own codesign `Identifier` is a per-build hash-derived string
(also changes across Homebrew rebuilds), but the **bundle's**
`CFBundleIdentifier` (`org.python.python`) is what TCC records for
bundle-form processes (`client_type=0`), and that string does **not** change
across Python patch/rebuild versions - see the TCC.db evidence below, which
shows exactly this bundle id recurring across multiple Homebrew `python@3.13`
rebuild dates.

**Path stability verdict:**
- Path A (uvx-managed, ad-hoc, no bundle): **UNSTABLE** - keyed by exact path,
  which embeds the patch version and changes on any uv reinstall/upgrade.
- Path B (Homebrew framework build, via `Python.app`): **STABLE** for TCC
  purposes, because the running interpreter reaches TCC as a bundle
  (`org.python.python`) rather than as a bare path, and that bundle id is
  version-independent. The underlying `venv/bin/python` symlink target path
  itself does still change across Homebrew python@3.13 point releases (e.g.
  `3.13.12_1` -> `3.13.15`, both observed in TCC.db below), but this does not
  matter because TCC is not keying off that path for this particular
  process - it observes the bundle it re-execs into.

## Launch parent chain

A `things_mcp` process **is** currently running (Eric's local venv-based
config, not the manifest.json uvx default):

```
$ pgrep -fl things_mcp
1856 /Applications/Claude.app/Contents/Helpers/disclaimer --pgroup -- .../venv/bin/python -m things_mcp
1861 .../python@3.13/.../Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python -m things_mcp
65217 .../python@3.13/.../Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python -m things_mcp
```

Parent chains:

```
pid 1856: disclaimer (ppid 823 = Claude) -> Claude (ppid 1 = launchd)
pid 1861: Python.app (ppid 1856 = disclaimer) -> disclaimer -> Claude -> launchd
pid 65217: Python.app (ppid 1 = launchd, i.e. REPARENTED/orphaned)
```

Confirms:
- `/Applications/Claude.app/Contents/Helpers/disclaimer` **is** the direct
  parent of the freshly-launched interpreter process (pid 1861), consistent
  with README's disclaimer-helper description.
- A second, older `things_mcp` process (pid 65217) has since been reparented
  to `launchd` (ppid 1) after its original `disclaimer` parent exited - i.e.
  once the disclaimer helper's job is done (permission prompt shown/dismissed
  or already granted), the server process outlives it and gets adopted by
  launchd. This means process-tree evidence of "disclaimer was the parent"
  is only observable near launch time, not for a long-running server.

## TCC log evidence (verbatim excerpts)

`log show --last 3d --predicate 'subsystem == "com.apple.TCC"' --style compact`
produced 133k+ lines over 3 days system-wide. Filtering for
python/AppData/culturedcode/kTCCService showed **no literal
`kTCCServiceSystemPolicyAppData` string** in that specific 3-day TCC-subsystem
window for a python client (the AppData grant events themselves appear to
predate the 3-day window on this machine - the most recent AppData grant for
python was 2026-08-13, see TCC.db below, more than 3 days before this probe
was run on 2026-09-08).

What *did* appear repeatedly in that window were `TCCAccessRequestIndirect`
events (Apple Events automation, not AppData) naming a bundle-less Homebrew
`python@3.14` binary by **path**, identified with `kTCCCodeIdentityIdentifierType
= 1` (path form) and empty `kTCCCodeIdentityTeamID`:

```
2026-09-08 13:09:48.060 Df System Events[52919:...] TCCAccessRequestIndirect: ... target_identity: {
    kTCCCodeIdentityExecutableURL = "file:///opt/homebrew/Cellar/python@3.14/3.14.6/.../bin/python3.14";
    kTCCCodeIdentityIdentifier = "/opt/homebrew/Cellar/python@3.14/3.14.6/.../bin/python3.14";
    kTCCCodeIdentityIdentifierType = 1;
    kTCCCodeIdentityTeamID = "";
    ...
}
```

This is a *different* service (Apple Events, requested indirectly by
`System Events`/`Terminal`/`DEVONthink` against a python process), but it
corroborates the general mechanism: a bare, ad-hoc/unbundled Python
executable is identified to TCC **by absolute path** (`IdentifierType = 1`),
with no Team ID - exactly the identity class that breaks when uv's
version-pinned path changes.

No line naming the service for the python client was found in the unified
log for this investigation. `log show --predicate 'subsystem ==
"com.apple.TCC"'` was re-run against the full retained window (not just the
3-day slice above); every hit for a string resembling
`kTCCServiceSystemPolicyAppData` was the search command itself being echoed
back (e.g. by `log show`'s own argument logging), not a genuine `sandboxd`/
`tccd` log line naming the service for a python process. The service
identity `kTCCServiceSystemPolicyAppData` is therefore **not** established
by any unified-log excerpt in this investigation - it rests entirely on the
TCC.db evidence in the next section, which has 14 `access` rows for that
exact service string, including the `org.python.python` bundle-id row.

## TCC.db evidence

Read successfully (calling terminal has Full Disk Access):

```
$ sqlite3 -readonly "$HOME/Library/Application Support/com.apple.TCC/TCC.db" \
  "select service, client, client_type, auth_value, auth_reason, datetime(last_modified,'unixepoch') from access where client like '%python%' or client like '%Claude%' or client like '%uv%' order by last_modified desc;"
```

Relevant rows (full output has more; `kTCCServiceSystemPolicyAppData`-relevant
rows only, newest first):

```
kTCCServiceSystemPolicyAppData|org.python.python|0|5|2|2026-08-13 08:21:07
kTCCServiceSystemPolicyAppData|/opt/homebrew/Cellar/python@3.13/3.13.12_1/Frameworks/Python.framework/Versions/3.13/bin/python3.13|1|5|2|2026-07-19 19:08:20
kTCCServiceSystemPolicyAppData|/Users/eric.bowman/.local/share/claude/versions/2.1.114|1|5|2|2026-04-18 21:53:08
kTCCServiceSystemPolicyAppData|com.anthropic.claudefordesktop|0|5|2|2025-09-15 21:58:49
kTCCServiceSystemPolicyAppData|/opt/homebrew/Cellar/python@3.13/3.13.11/Frameworks/Python.framework/Versions/3.13/bin/python3.13|1|5|2|2026-02-25 07:50:53
```

`client_type`: 0 = bundle id, 1 = absolute path (per the task brief's own
definition, consistent with Apple's TCC.db schema).

**This is the single most important piece of evidence in this investigation:**

- The **most recent** AppData grant for a python client (2026-08-13) is keyed
  by **bundle id `org.python.python`** (`client_type=0`) - not a path. This
  is the Homebrew framework build's `Python.app` bundle identity (see
  "Interpreter identity" section B above). Because this identity string is
  version-independent, this grant should survive a `python@3.13` Homebrew
  point-release upgrade or a Claude Desktop relaunch, *as long as the
  process continues to be launched in a way that re-execs through
  `Python.app`* (true for `python -m <module>` under a framework build,
  observed directly via `ps` above).
- Two **older** grants (2026-07-19, 2026-02-25) are keyed by the exact
  Homebrew Cellar **path** for two different past `python@3.13` patch
  builds (`3.13.12_1`, `3.13.11`) - `client_type=1`. Each of those is now
  stale/orphaned (the current binary lives at a `3.13.15` path that does not
  match either), which is direct historical evidence that **before this
  machine's most recent grant, path-keyed AppData grants for python did go
  stale across Homebrew point releases** - each patch bump created a "new"
  program from TCC's point of view and (per the epic's bug report) presumably
  re-prompted.
- This strongly supports the hypothesis that **whether the prompt recurs
  depends entirely on whether the launched interpreter is bundle-identified
  or path-identified by TCC**, and that path-identified interpreters (like
  the `uvx`-managed one in `manifest.json`, which embeds an exact patch
  version in its path) are the higher-risk configuration.

No permission/authorization error was encountered reading TCC.db - the
calling shell already has Full Disk Access.

## Test matrix

| Row | Scenario | Result |
|---|---|---|
| (a) | Allow the AppData prompt, then quit and relaunch Claude Desktop entirely - does it re-prompt? | **NOT TESTED - requires operator.** Steps: 1. Quit Claude Desktop fully (Cmd-Q, confirm no background helper remains via `pgrep -fl things_mcp`). 2. Relaunch Claude Desktop and open a conversation that invokes any Things MCP tool. 3. Watch for the "python wants access to other apps' data" dialog. 4. If it appears, click **Allow**. 5. Quit and relaunch Claude Desktop again (second time) and repeat step 3 - record whether the dialog reappears. |
| (b) | Grant Full Disk Access to the realpath python3.12 binary (System Settings > Privacy & Security > Full Disk Access, add the binary via Cmd-Shift-G to type the exact path), then relaunch Claude Desktop - does it re-prompt? | **NOT TESTED - requires operator.** Steps: 1. Run `scripts/tcc_probe.sh` and note the "resolved realpath" line under section 1 (the exact `uvx`-managed interpreter path). 2. Open System Settings > Privacy & Security > Full Disk Access. 3. Click "+", press Cmd-Shift-G, paste that exact path, and add it. 4. Quit and relaunch Claude Desktop. 5. Invoke a Things MCP tool and record whether the AppData prompt still appears. **Caveat established by this investigation:** if uv later reinstalls/upgrades this Python 3.12 patch build, the path (and this FDA grant) becomes stale and the *new* path will need to be added again - this is expected, not a failure of the fix. |
| (c) | Launch via a stable venv python path (`venv/bin/python -m things_mcp`, matching Eric's current local config) instead of the manifest.json `uvx` default, then relaunch Claude Desktop - does it re-prompt? | **NOT TESTED (relaunch step) - requires operator**, though static evidence strongly suggests **no re-prompt**: this is Eric's actual current running configuration (confirmed via `pgrep -fl things_mcp`/`ps` above), the interpreter re-execs through the `org.python.python`-identified `Python.app` bundle, and TCC.db already shows a *granted* (`auth_value=5`) AppData entry for exactly that bundle id, dated 2026-08-13, more recent than the currently-running Homebrew `python@3.13.15` build's install. Operator steps to confirm definitively: 1. Confirm `manifest.json`/Claude Desktop config uses `venv/bin/python -m things_mcp` (or equivalent framework-build interpreter), not `uvx`. 2. Quit and relaunch Claude Desktop. 3. Invoke a Things MCP tool and record whether any AppData prompt appears. |
| (d) | Does a uv Python 3.12 patch upgrade change the binary path/cdhash? | **CONFIRMED YES, from static evidence (no upgrade needed to demonstrate this) in step 1 and TCC.db.** The resolved uvx path is `.../uv/python/cpython-3.12.11-macos-aarch64-none/bin/python3.12` - it embeds the exact patch version (`3.12.11`) in the directory name itself, not just in a version file; `uv python install 3.12 --reinstall` (or uv simply resolving a newer 3.12.x release later) installs into a **new** `cpython-3.12.<N>-macos-aarch64-none` directory, a structurally different path. TCC.db independently corroborates this same failure mode for a *different* interpreter family: two now-stale path-keyed AppData grants exist for two different past Homebrew `python@3.13` patch builds (`3.13.12_1`, `3.13.11`), neither of which matches the currently-installed `3.13.15` path - i.e. on this machine, path-keyed grants for python interpreters have historically gone stale across ordinary patch upgrades. The codesign identity also changes: `Identifier=-` (uvx build, no persistent code identity at all beyond adhoc/linker-signed) and the Homebrew framework binary's own `Identifier=python3-<hash>` both vary per build. Reboot was not (and cannot be) tested as part of this row. |

## Recommended fix ladder for a headless Mac (HYPOTHESIS - pending operator verification of rows a-c above)

Ordered by robustness (most robust first). None of these have been verified
end-to-end via an actual Claude-Desktop-relaunch test on this machine (rows
a-c above are NOT TESTED); this ladder is built from the identity mechanism
evidence above and should be validated before being presented as fact in
`docs/MACOS_PERMISSIONS.md` (hq-gxt.4).

1. **Launch via a bundle-identified interpreter (framework Python via
   `Python.app`, or an equivalent `.app`-wrapped interpreter), not a bare
   ad-hoc executable.** This is the only configuration on this machine with
   direct TCC.db evidence of a currently-*granted*, version-independent
   identity (`org.python.python`). Concretely: point Claude Desktop's server
   config at a Homebrew **framework** build of Python (`python@3.1x`,
   installed via `brew install python@3.12` et al, which ships a
   `Python.framework`/`Python.app`), invoked as `python -m things_mcp` (or
   equivalent) via a stable wrapper path (e.g. a venv whose `pyvenv.cfg`
   points at the framework build) - not the `uvx`-managed interpreter from
   `manifest.json`.
2. **If `uvx`/`uv`-managed Python must be used, pin the interpreter to a
   `uv tool install`-style stable location rather than resolving a fresh
   ad-hoc build path per version.** This does not eliminate the "ad-hoc,
   path-keyed" identity problem, but avoids the exact-patch-version
   embedding in the path if `uv tool install` (or a symlink `uv` maintains
   at a fixed location) can be relied upon not to change across patch
   bumps - needs verification against `uv`'s actual install-path behavior,
   which was not covered by this investigation's steps.
3. **Full Disk Access on the exact realpath binary** (matrix row b) is a
   viable manual workaround but is **not durable** against uv reinstalls/
   upgrades, since the grant is keyed to the ephemeral path - would need to
   be redone after any interpreter upgrade. Lowest robustness of the three.
4. Reboot as a variable was explicitly **not tested and cannot be tested**
   on this machine per the task constraints - no claim is made about
   whether a reboot alone affects any of the above.

## Recommendation for bead hq-gxt.5 (interpreter stability)

Pin the interpreter used by `manifest.json` (and any README install
snippets) to a stable, non-version-embedding path - concretely, prefer:

- A Homebrew **framework** Python build (bundle-identified, evidence above
  shows this currently holds a live grant), invoked via a fixed venv path
  (mirroring Eric's current working local config), OR
- If `uv`/`uvx` must remain the mechanism, investigate whether `uv tool
  install mcp-server-things --python 3.12` (or pinning via a `.python-version`
  /`uv.lock`-controlled venv at a fixed repo-relative path) yields a stable
  invocation path that does not change on every `uv python` patch
  resolution, as the current `uvx --python-preference only-managed --python
  3.12 mcp-server-things` invocation does (per the `cpython-3.12.11-...`
  path evidence above). This needs its own verification pass in hq-gxt.5;
  this task only establishes *why* path stability matters, not which of
  uv's install modes achieves it.

Whichever path is chosen, hq-gxt.5 should re-run `scripts/tcc_probe.sh`
before and after the change to confirm the resolved interpreter path (and,
where applicable, whether it re-execs through a bundle) is stable across a
`uv`/Homebrew upgrade cycle.

## Reboot

Not tested. A full reboot was out of scope/not performed for this
investigation per task constraints - no claim is made about whether a
reboot affects TCC grant persistence beyond what is documented above.
