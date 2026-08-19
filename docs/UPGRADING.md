# Upgrading to 1.6

1.6.0 doesn't change how the server talks to Things 3 — it makes the server
easier to install and diagnose. The recommended install path is now
`uvx`-first (no venv to manage), there are new `doctor` and `config` CLI
subcommands for diagnosing problems and generating client config, an optional
HTTP transport for the TCC-permission workaround, and every read tool now
returns FastMCP 3 structured output (`structured_content`) alongside its text
response. Existing installs are not required to change anything; see
"Nothing breaks" below.

## Nothing breaks

- The `things-mcp` console-script alias still works, and as of 1.6.0 it
  actually works from a wheel install (`pip install mcp-server-things` /
  `uvx mcp-server-things`) — in published wheels before 1.6.0 the
  `things-mcp` entry point was broken and only worked in editable
  (`pip install -e .`) source installs.
- `python -m things_mcp` continues to work unchanged.
- Existing venv-based `claude_desktop_config.json` entries (pointing at a
  venv's `python -m things_mcp` with `PYTHONPATH` set for source installs)
  keep working exactly as before — nothing needs to be edited.
- All existing tool names and parameters are backward compatible. Every
  change in 1.6.0 is additive (new optional parameters, new fields in
  responses) — no tool was renamed and no existing parameter was removed or
  had its meaning changed.

## Behavioural changes to review

A few response *contents* changed even though no tool signature broke. If you
have automation or prompts that depend on exact output shape, check these:

- **`get_someday` no longer includes tasks inside Someday projects by
  default.** Previously it also returned tasks that inherited "Someday" from
  a parent project, which could return a much larger set than Things' own
  Someday list. What to do: pass `include_project_tasks=true` to restore the
  old (superset) behavior; inherited items are now marked
  `inheritedSomeday: true` so you can distinguish them.
- **`tag_creation_policy=fail_on_unknown` now actually aborts writes with
  unknown tags.** It previously silently proceeded and wrote the known tags
  anyway (across todos, projects, areas, and `add_tags`). What to do: if you
  rely on `fail_on_unknown`, expect writes with any unrecognized tag to now
  fail with a structured error instead of partially succeeding — create the
  tag in Things 3 first, or switch to `filter_silent`/`filter_warn` if
  partial success is what you want.
- **Read tools now return `structured_content`** shaped
  `{items, count, total, mode, limit, offset}` (`{item: {...}}` for
  single-item lookups like `get_todo_by_id`) in addition to the existing text
  response. What to do: under `mode='summary'`, `count` is the size of the
  preview list, not the full dataset — read `total` for the true count before
  any `limit` was applied.
- **`search_advanced` with a `type=` filter used to crash** with a
  `TypeError` (`got multiple values for keyword argument 'type'`); it now
  works correctly for `type` values `'to-do'`, `'project'`, and `'heading'`.
  What to do: nothing — this is a straightforward bug fix, but if you were
  working around the crash (e.g. filtering results by type client-side after
  the call), you can now pass `type=` directly.
- **Empty entries in comma-separated tag strings are now dropped.** Inputs
  like `"a,,b"` or `"a, "` previously could send an empty-string tag name
  through to Things 3; they're now stripped before validation. What to do:
  nothing — this only removes previously-invalid empty tag entries.

## Recommended: switch to uvx

If you're on a venv-based config, switching to `uvx` removes the need to
manage a virtual environment or Python path for this server.

**Before** (venv-based, source checkout):

```json
{
  "mcpServers": {
    "things": {
      "command": "/path/to/mcp-server-things/venv/bin/python",
      "args": ["-m", "things_mcp"],
      "env": {
        "PYTHONPATH": "/path/to/mcp-server-things/src",
        "THINGS_MCP_LOG_LEVEL": "INFO",
        "THINGS_MCP_APPLESCRIPT_TIMEOUT": "30"
      }
    }
  }
}
```

**After** (uvx, no venv to maintain):

```json
{
  "mcpServers": {
    "things": {
      "command": "uvx",
      "args": ["mcp-server-things"]
    }
  }
}
```

The fastest way to make this switch for Claude Desktop is the `config` CLI
shortcut, which safely merges the entry into your existing config (backing up
the previous file first, and refusing to clobber a differing existing entry
unless `--force` is passed):

```bash
mcp-server-things config --client claude-desktop --write
```

For Claude Code, add the server with one command:

```bash
claude mcp add-json things '{"command":"uvx","args":["mcp-server-things"]}'
```

**Note:** the `uvx mcp-server-things` path requires the 1.6.0 PyPI release
(it depends on the `things-mcp`/`mcp-server-things` wheel entry-point fix
described above). Until 1.6.0 is published, keep your existing venv-based
config — it will continue to work unchanged.

## Verify

```bash
mcp-server-things doctor
```

Checks Things 3 installation, whether it's running, macOS Automation (TCC)
permission, database readability (Full Disk Access), `uv`/`uvx` on `PATH`,
and version info, then prints a PASS/FAIL/WARN/INFO table with a one-line fix
hint for anything that isn't a PASS.

## Rollback

If you need to go back to 1.5.0:

```bash
pip install mcp-server-things==1.5.0
```

Or, to pin an exact version when launching via `uvx` (the `package@version`
syntax is `uv`'s documented shorthand for `uvx --from package==version
package`):

```bash
uvx mcp-server-things@1.5.0
```
