# Upgrading

## Upgrading to 1.7

1.7.0 closes out two user-reported issues - list tools returning projects and
headings instead of just to-dos, and multi-line notes losing their line breaks
on write (the AppleScript string escaper collapsed them) - plus a broad
read/write correctness sweep (see
the [CHANGELOG](../CHANGELOG.md#170---2026-08-19) for the full list). All
existing tool names and parameters remain backward compatible: every change
is additive (new optional parameters, new or renamed response fields) - no
tool was renamed and no existing parameter was removed. If you have
automation or prompts that depend on exact output shape, review the
behavioural changes below.

### Behavioural changes to review

- **`get_today`, `get_upcoming`, `get_anytime`, `get_someday`, and
  `get_trash` no longer include projects or headings by default.**
  Previously these list tools returned a mix of to-dos, projects, and
  headings straight from things.py; headings were never meant to be
  user-facing items in these lists and projects crowded out to-dos in
  response-mode truncation. What to do: pass the new `include_projects=true`
  parameter on any of these five tools to restore projects in the results
  (headings are never returned, even with this flag) — `get_inbox` is
  unaffected since the Inbox can never contain projects.
- **`search_todos` gained a `status` parameter and `search_advanced`/
  `get_recent` changed their default status scope.** `search_todos` now
  accepts `status` (`'incomplete'` (default, unchanged) / `'completed'` /
  `'canceled'` / `None` for all) - previously it always searched only
  incomplete todos with no way to search completed/canceled ones. What to
  do: pass `status='completed'`, `status='canceled'`, or `status=None` if
  you need to find a completed/canceled todo by search. `search_advanced`
  with no `status` filter now searches items of **all** statuses (it
  previously silently defaulted to incomplete-only, same bug as above);
  pass `status='incomplete'` explicitly to restrict to open items as
  before. `get_recent` now defaults to **all** statuses, and to both
  to-dos and projects (previously incomplete to-dos only), so
  recently-created completed/canceled to-dos and recently-created
  projects now appear in the results; headings are still NEVER included
  by default (list tools never return headings by default), pass
  `type='heading'` explicitly if you need recently created headings.
  Pass the new `status`/`type` parameters to narrow the results.
  `search_todos` also now rejects an empty or whitespace-only `query` with
  a structured error instead of silently matching every todo.
- **Todo/project dicts gained new fields and one field changed shape**
  (hq-f0w.4). New: `type` (`'to-do'`/`'project'`/etc.), `start` (Inbox /
  Anytime / Someday — distinct from the existing `startDate`, a specific
  date), `projectTitle`, `heading`, `headingTitle`, `hasChecklist` (bool),
  `index`, `todayIndex`; projects also gained `areaTitle`. `area` was
  removed from todo dicts — it was always `null`/absent in practice, since
  things.py to-do rows never actually carry an `area` key (only projects
  do). `checklist` is now only present as a list of items when
  `include_items=true` (or `get_todo_by_id`) actually fetched them; it no
  longer appears as a stray, usually-empty-looking bool/list mix — check
  `hasChecklist` instead if you just need to know whether a todo has a
  checklist. `completionDate`/`cancellationDate` are unaffected in shape
  but are now correctly populated (previously always absent). What to do:
  nothing required for existing integrations reading
  `dueDate`/`startDate`/`tags`/etc.; if you read `area` off a todo dict,
  switch to reading it off the todo's parent project instead (fetch the
  project by `project` uuid), and if you check for a `checklist` key's
  *presence* to mean "has a checklist", switch to the new `hasChecklist`
  boolean.
- **`update_todo`/`update_project`/`update_area`/`bulk_update_todos` can now
  clear `notes`, `deadline`, and `tags` by passing `''` (an empty string).**
  Previously an empty string for any of these fields was silently treated
  the same as "not provided" (a no-op) — there was no way to clear a
  todo/project's notes or deadline, or remove all its tags, through any
  tool. `notes=''`/`deadline=''` now clear those fields; `tags=''` now
  clears all tags. Two related tightenings ship alongside this:
  `title=''` (or whitespace-only) is now rejected with a structured
  `VALIDATION_ERROR` (titles cannot be cleared — previously this was
  silently ignored), and `when=''` is now rejected the same way, with a
  hint to use `when='anytime'` or `when='someday'` to unschedule instead.
  What to do: if any caller relied on passing `''` as a no-op sentinel for
  `notes`/`deadline`/`tags`, switch to omitting the parameter (or passing
  `None`) to preserve the old "leave unchanged" behavior; if any caller
  passed `title=''` or `when=''` expecting it to be silently ignored,
  expect a `VALIDATION_ERROR` response instead.
- **Read tools' structured errors now use a single canonical shape:
  `{"success": false, "error": "<snake_case_code>", "message": "..."}`.**
  Previously the `error` field's meaning varied by tool: some tools (e.g.
  `get_todos`/`get_projects`/`get_areas`/`search_todos`/`search_advanced`
  on an invalid `mode`) put a human-readable sentence directly in `error`
  (e.g. `"Invalid mode"`); `get_project_headings` used a different shape
  entirely (`{"error": true, "error_type": "not_found", "message": "..."}`).
  All read tools now put a short, stable, machine-readable code in `error`
  (e.g. `invalid_mode`, `invalid_status`, `invalid_query`, `invalid_limit`,
  `not_found`, `invalid_type`, `invalid_parameter`, `internal_error`) and
  move the human-readable sentence to `message`; `unknown_tag` was already
  code-shaped but previously carried no `message` at all - it now does too
  (e.g. `"Unknown tag 'LLM-WIKI'. Did you mean: llm-wiki?"`). What to do: if
  any caller pattern-matched on the literal text previously in `error` (e.g.
  checked `error == "Invalid mode"` or `error is True`), switch to checking
  the new code (e.g. `error == "invalid_mode"`) and/or `success is False`;
  reading `message` for display text is unaffected, and any caller that
  already read `message` off an `unknown_tag` error should note it is now
  always present rather than absent. `get_todo_by_id` still raises
  (`ValueError`, surfaced as a FastMCP `ToolError`) for an id that doesn't
  exist at all, but as of hq-f0w.23 it now returns a structured
  `invalid_type` error (at the top level of the tool response, not nested
  under `item`) instead of raising when the id resolves to a tag - a tag
  is a label, not a retrievable item; use `get_tags()`/`get_tagged_items()`
  for tags.
- **Write tools' structured errors now use a single canonical shape too:
  `{"success": false, "error": "<UPPER_SNAKE_CODE>", "message": "..."}`**
  (hq-f0w.35, the write-tool counterpart of the read-tool change above).
  Previously several write tools (`add_todo`/`update_todo`/
  `bulk_update_todos`/`add_project`/`update_project` on a malformed
  `when`/`deadline`; `create_tag`; `add_checklist_items`/
  `prepend_checklist_items` on an empty `items` list; `add_area`/
  `update_area`/`add_tags`/`remove_tags`/`delete_todo`'s AppleScript-failure
  paths) put a human-readable sentence or a raw `str(exception)` directly
  in `error` (e.g. `"Invalid when date"`, `"Tag creation is restricted to
  human users only"`, `"No valid checklist items provided"`). `add_tags`
  and `remove_tags` were a step further: their AppleScript-execution-failure
  path put the raw AppleScript error text in `message` only, with **no**
  `error` key present at all on failure - callers checking `"error" in
  result` (rather than `result["success"]`) to detect failure would have
  missed it entirely. All write tools now put a short, stable,
  machine-readable UPPER_SNAKE_CASE code in `error` (e.g. `INVALID_WHEN`,
  `INVALID_DEADLINE`, `NO_CHECKLIST_ITEMS`, `NO_TODO_IDS`,
  `TAG_CREATION_RESTRICTED`, `TAG_CREATION_FAILED`, `APPLESCRIPT_ERROR`,
  `NOT_FOUND`, `NO_FIELDS_PROVIDED`) and move the human-readable sentence to
  `message`; dynamic AppleScript/exception text that used to live in `error`
  now lives in a `details` field instead where applicable (`NOT_FOUND` is
  the one exception - `update_area`'s "Area not found: `<id>`" text is
  constructed/human-readable, not raw AppleScript passthrough, so it stays
  in `message`). This now covers every AppleScript-execution-failure/
  exception path in `server.py`, `write_operations.py`, and
  `bulk_operations.py`, including `delete_todo`'s final "all attempts
  failed" branch and `bulk_update_todos`'s outer exception handler at both
  the tools layer and the MCP tool boundary. Codes that were already
  established before this bead (`VALIDATION_ERROR`, `TARGET_COMPLETED`,
  `NO_VALID_TAGS`, and `move_record`/`bulk_move_records`' pre-existing
  UPPER_SNAKE codes) are unchanged. `delete_todo`'s `not_deletable`/
  `not_found` codes are deliberately left lower_snake_case (they predate
  this bead, share the `not_found` convention with the read-tool contract,
  and have extensive existing test coverage) - see CLAUDE.md's "Structured
  error contract (write tools)" section for the full list of intentional
  exceptions. What to do: if any caller pattern-matched on the literal text
  previously in a write tool's `error` field, switch to checking the new
  UPPER_SNAKE_CASE code and/or `success is False`; if any caller checked
  `"error" in result` to detect an `add_tags`/`remove_tags` AppleScript
  failure, note that path always has an `error` key now (it didn't
  before); reading `message` for display text is unaffected.
- **`scheduling/todo_operations.py` (`add_todo`/`update_todo`/
  `add_project`/`update_project`/checklist scheduling) now uses the same
  UPPER_SNAKE_CASE write-tool contract** (hq-f0w.46, closing out the
  follow-up from hq-f0w.35 above). New codes: `NOT_FOUND` (an unknown
  `list_id`/`list_title`), `AMBIGUOUS_TARGET` (a `list_title` matching more
  than one project/area - the matching `kind:id` strings are in the `ids`
  field), `CREATE_UNCONFIRMED` (a URL-scheme create that could not be
  confirmed within the polling deadline), `UNSUPPORTED_FOR_PROJECTS`
  (`when='evening'` on `add_project`/`update_project`), `INVALID_HEADING`
  (an empty/whitespace-only `heading` on `update_todo`), and
  `AUTH_TOKEN_NOT_CONFIGURED` (the Things URL-scheme auth-gate, moved from
  `services/applescript_manager.py`'s `execute_url_scheme` - the previous
  literal error text `"Things URL-scheme auth token not configured"` is
  unchanged but now lives in `message`, not `error`; this also affects
  `add_checklist_items`/`prepend_checklist_items`/`replace_checklist_items`/
  `bulk_update_todos`, which forward the same code/message/hint). What to
  do: if any caller pattern-matched on `error == "Things URL-scheme auth
  token not configured"` or on any of the human-string `error` values this
  file used to return (e.g. `"... does not match any known project or
  area"`, `"... is ambiguous - matches multiple projects/areas: ..."`,
  `"heading cannot be empty; ..."`, `"when='evening' is not supported for
  projects; ..."`), switch to checking the new UPPER_SNAKE_CASE code and
  read the descriptive text from `message` instead.
- **`add_project`/`update_project`/`add_todo`/`update_todo` no longer
  collapse newlines in notes.** The AppleScript string escaper previously
  mapped `\n`/`\r` to a single space, so multi-line project/todo notes lost
  their paragraph breaks on write; every AppleScript-string-building call
  site now shares one escaper that maps newlines/carriage returns/tabs to
  their AppleScript literal escape sequences instead, so they survive
  intact inside the generated script. What to do: nothing — this only
  restores newlines that were previously being silently destroyed; if any
  caller was working around the collapse (e.g. re-inserting `\n\n` after
  reading notes back), that workaround is no longer necessary.
- **`get_todos(project_uuid=...)` now reads via things.py instead of
  AppleScript**, fixing a silently incomplete-only `status` filter when
  `project_uuid` was combined with `status`. What to do: nothing — this is
  a straightforward bug fix; the dead AppleScript read-parser code path is
  also removed as a result.
- **`delete_todo` can now delete a project id** (previously errored with a
  generic AppleScript failure). Headings, areas, and tags still cannot be
  deleted via any public Things 3 API and now return a structured
  `not_deletable` error instead of a failed AppleScript attempt. What to
  do: nothing — this only adds a previously-unsupported capability and
  clarifies previously-opaque failures.
- **`get_logbook` now includes canceled to-dos alongside completed ones by
  default**, matching what the Things app's own Logbook view shows
  (previously only completed to-dos were returned, even though canceled
  to-dos also appear in Things' Logbook). What to do: pass the new
  `include_canceled=false` parameter to restore the completed-only view;
  each item's existing `status` field (`'completed'`/`'canceled'`) tells
  them apart. `get_logbook`'s `limit` cap is also raised from 100 to 500,
  and it gains an `offset` parameter for paging past the first 500.
- **`update_todo`/`bulk_update_todos`/`update_project` now share one
  `completed`/`canceled` status-precedence rule, and the MCP boundary
  strictly parses `completed`/`canceled`.** Previously `canceled=False`
  alone (with `completed` omitted) was a silent no-op on `update_todo`
  specifically, and the `completed`/`canceled` string-to-bool conversion
  treated any non-`'true'` string (including typos like `'yes'`) as
  `false`, which could unintentionally reopen a completed/canceled item.
  What to do: `canceled=True` now always wins regardless of `completed`;
  otherwise `completed=True`/`completed=False` sets completed/open;
  otherwise `canceled=False` alone reopens. Pass the literal strings
  `'true'`/`'false'` (case-insensitive) or an actual bool for
  `completed`/`canceled` - anything else now returns a structured
  `VALIDATION_ERROR` instead of silently being treated as `false`.
- **Writing into (or moving a to-do into) a completed/canceled heading or
  project is now refused instead of silently reopening it.** `add_todo`/
  `update_todo` now pre-check the target's status before any write and
  return a structured `TARGET_COMPLETED` error if the target heading or
  project (via `list_id`/`list_title`) is completed/canceled - previously
  Things would silently reopen the project/heading, a real, visible change
  to pre-existing user data. What to do: reopen the target manually in
  Things first, or choose another target; there is no `allow_reopen`
  override.
- **`when='evening'` (and alias `'tonight'`) is now accepted** on
  `add_todo`/`update_todo`/`bulk_update_todos` and correctly schedules
  to-dos for "This Evening" (previously rejected by validation with no way
  to set it at all). `update_todo`/`bulk_update_todos` with
  `when='evening'` route through the Things URL scheme and require the
  Things auth token (see "Things URL-scheme auth token" in the README) -
  a missing token now returns a structured error/hint instead of silently
  no-op'ing; `add_todo` does not need a token. `add_project`/
  `update_project` explicitly reject `when='evening'` with a structured
  error, since Things has no "This Evening" concept for projects. `deadline`
  now consistently rejects relative keywords (`'today'`, etc.) on every
  validation path - it must always be `YYYY-MM-DD`.
- **URL-scheme-based write tools now fail fast with an explicit error when
  the Things auth token is missing**, instead of returning `success: true`
  while silently doing nothing. `add_checklist_items`,
  `prepend_checklist_items`, `replace_checklist_items`, and `update_todo`/
  `bulk_update_todos` with `heading=...` or `when='evening'` all go
  through `things:///update`, which Things itself rejects without a
  configured token - but `open -g` (used to fire the URL) still exits 0,
  so before this release these tools reported success even though nothing
  happened. What to do: configure a Things auth token (see the README) if
  you use any of these tools' URL-scheme-only parameters; check for a
  `hint` field in the error response for setup instructions.
- **Empty list results (and `mode` omitted or `'auto'`) now report a
  concrete effective `mode`** (e.g. `"standard"`) instead of the literal
  string `"auto"` or `None`. `get_inbox`/`get_today`/`get_upcoming`/
  `get_anytime`/`get_someday` with `mode` omitted previously bypassed the
  context manager entirely, returning raw, unfiltered rows with `mode`
  left as `None`; they now behave the same as `mode='auto'` (AUTO sizing
  applies - a large list becomes a summary preview) and report the
  resolved mode. What to do: pass `mode='standard'` or `mode='raw'`
  explicitly on these five tools if you relied on getting full,
  untruncated rows back with `mode` omitted; `requested_mode` still
  preserves what you actually passed (`None` for omitted, `"auto"` for
  explicit).

## Upgrading to 1.6

1.6.0 doesn't change how the server talks to Things 3 — it makes the server
easier to install and diagnose. The recommended install path is now
`uvx`-first (no venv to manage), there are new `doctor` and `config` CLI
subcommands for diagnosing problems and generating client config, an optional
HTTP transport for the TCC-permission workaround, and every read tool now
returns FastMCP 3 structured output (`structured_content`) alongside its text
response. Existing installs are not required to change anything; see
"Nothing breaks" below.

### Nothing breaks

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

### Behavioural changes to review

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
      "args": ["--python-preference", "only-managed", "--python", "3.12", "mcp-server-things"]
    }
  }
}
```

The generated config pins uv's managed Python (`--python-preference
only-managed`) so a stray Intel/Rosetta Python on your PATH can't break the
install; first launch may download a managed CPython.

The fastest way to make this switch for Claude Desktop is the `config` CLI
shortcut, which safely merges the entry into your existing config (backing up
the previous file first, and refusing to clobber a differing existing entry
unless `--force` is passed):

```bash
mcp-server-things config --client claude-desktop --write
```

For Claude Code, add the server with one command:

```bash
claude mcp add-json things '{"command":"uvx","args":["--python-preference","only-managed","--python","3.12","mcp-server-things"]}'
```

**Note:** the `uvx mcp-server-things` path requires release 1.6.0 or later
(earlier published wheels had a broken console-script entry point). Your
existing venv-based config also continues to work unchanged if you prefer
not to switch.

- If `uvx mcp-server-things` fails while `Building cryptography==...` with Rust/maturin
  errors, your default Python is an x86_64 (Intel/Rosetta) build — fix with an arm64
  interpreter, e.g. `uvx -p 3.12 mcp-server-things`; `mcp-server-things doctor` warns
  about this.

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
