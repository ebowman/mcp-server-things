# Changelog

All notable changes to the Things 3 MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Successful `update_todo` and `move_record` calls now return verified write receipts** containing the stable target `todo_id` and an `item` readback in the same shape as `get_todo_by_id`. Structured write failures are returned unchanged and do not trigger a readback.

## [1.7.0] - 2026-08-19

This release closes out two user-reported issues: [#9](https://github.com/ebowman/mcp-server-things/issues/9)
(list tools returning projects/headings instead of just tasks, and no way to read or
place tasks under a project's headings) and [#10](https://github.com/ebowman/mcp-server-things/issues/10)
(read-path title corruption on titles containing commas/quotes, and multi-line notes
losing their line breaks on write (the AppleScript string escaper collapsed them) -
the title corruption was on the AppleScript-based read path, which this release also
removes in favor of reading exclusively through things.py, see below). Alongside those, this release also folds
in a broad read/write correctness sweep - pagination totals, structured error shapes,
tag/date/status edge cases, and a large expansion of test coverage (unit suite: 1349
passed, 1 skipped).

### Added
- **`get_project_headings(project_id, mode?)`** - new read-only tool for a project's heading structure (issue #9). Returns `{uuid, title, index, todoCount}` per heading, in Things' own display order, where `todoCount` is the number of open to-dos directly under that heading. An unknown `project_id`, or one that resolves to something other than a project, returns a structured error instead of raising. Read-only by design: headings can only be created via `add_project`'s `##` lines - placing a to-do under a heading with `add_todo`/`update_todo`'s `heading=...` requires an existing heading and creates nothing if it doesn't exist (an unknown heading name produces a `warnings` entry, not a new heading) - there is no public Things 3 API to rename or delete a heading.
- **`update_todo(heading=..., list_id=..., list_title=...)`** - moves an existing to-do under a heading, optionally into a different project at the same time (issue #9). Requires the Things URL-scheme auth token (checked before any write, so a missing token never partially applies other fields in the same call). `heading=''` is rejected - use `move_record()` to move a to-do out of a heading. If the named heading doesn't exist in the target project, a `warnings` entry is added rather than erroring, since Things itself ignores an unknown heading silently.
- **`add_project`'s `todos` payload now supports real `##Heading` lines** - a `todos` line like `"##Phase 1"` now creates a real Things heading (via the URL scheme's structured `json` action), with subsequent lines nesting under it; a payload with no `##` lines still uses the faster AppleScript path. The AppleScript path also now verifies and reports `todos_created`/`headings_created` counts (with a `warnings` entry if fewer were created than requested) instead of trusting the request blindly.
- **`update_todo` can move a to-do to a project or area** via new `list_id`/`list_title` parameters, matching `add_todo`'s existing project/area targeting. Combined with `heading`, this moves and places under a heading in one call.
- **`get_logbook` gains `include_canceled` (default `true`)** and now also returns canceled to-dos alongside completed ones, matching what the Things app's own Logbook view shows (previously only completed to-dos were returned). Its `limit` cap is also raised from 100 to 500.
- **`get_due_in_days` gains `include_overdue` (default `true`, preserving prior behavior)**; pass `false` to restrict results to `today <= deadline <= target date` instead of also including already-overdue todos.
- **`search_todos` gains a `status` parameter** (`'incomplete'` default / `'completed'` / `'canceled'` / `None` for all).
- **`get_logbook`, `search_todos`, and `search_advanced` gain `offset`** for pagination past the first page of results, alongside the existing `limit`.
- **`get_today`/`get_upcoming`/`get_anytime`/`get_someday`/`get_trash` gain `include_projects` (default `false`)** to opt back into seeing projects in these lists (headings are never returned by any list tool, with or without this flag).
- **Opt-in live Things 3 smoke suite (`tests/live/`)** - a new, self-cleaning test suite that exercises real reads/writes against a running Things 3 (skipped unless `THINGS_MCP_LIVE_TESTS=1` is set and Things 3 is actually running), plus a `make test-live` target and `docs/TESTING.md` describing the full testing policy. All of `tests/integration`'s real-Things-writing fixtures are now gated behind the same env var - previously several integration test files could write to (and delete from) a live Things 3 database with no opt-in at all.

### Changed
- **`get_today`, `get_upcoming`, `get_anytime`, `get_someday`, and `get_trash` no longer return projects or headings by default** (issue #9) - these list tools previously mixed projects and headings in with to-dos (e.g. `get_anytime()` on a real database returned 1175 items - 1106 to-dos, 39 projects, 30 headings - instead of the 1106 to-dos a caller would expect). Pass the new `include_projects=true` parameter to opt back into projects; headings are never returned by these tools. `get_inbox` is unaffected (the Inbox can never contain projects).
- **Todo/project dicts gained new fields; `checklist` changed from a bool-or-list to a dedicated `hasChecklist` boolean.** `convert_todo`/`convert_project` were rewritten against the real things.py key set: completed/canceled todos and projects now correctly report `completionDate`/`cancellationDate` (previously always empty). New fields: `type`, `start` (Inbox/Anytime/Someday, distinct from `startDate`), `projectTitle`, `heading`/`headingTitle`, `index`, `todayIndex`, `reminderTime`; projects also gained `areaTitle`/`start`/`startDate`/`index`/`todayIndex`. `checklist` (previously an ambiguous bool-or-list) is now `hasChecklist` (bool); `checklist` only appears as a real item list when `include_items=true` (or `get_todo_by_id`) actually fetched it. The phantom `area` key on todo dicts (things.py never actually populates it there) was removed.
- **`search_advanced` with no `status` filter now searches all statuses** instead of silently defaulting to incomplete-only; pass `status='incomplete'` to restrict, as before. `get_recent` now defaults to all statuses and both to-dos and projects (previously incomplete to-dos only); headings are still never included by default. `search_todos('')` (empty/whitespace query) is now rejected with a structured error instead of matching everything.
- **`total` in structured output is now the pre-limit count on every list tool.** Previously `get_inbox`/`get_today`/`get_upcoming`/`get_anytime`/`get_someday` computed `total` from the already-`limit`-truncated result, so `total` always equaled `count`; they (and `search_todos`/`search_advanced`/`get_logbook`) now compute the true pre-limit/offset match count.
- **Read tools' structured errors now share one canonical shape**: `{"success": false, "error": "<snake_case_code>", "message": "..."}`. Previously some tools put a human sentence directly in `error` (e.g. `"Invalid mode"`), and `get_project_headings` used a different shape entirely. See `docs/UPGRADING.md` for the full code list.
- **Write tools' structured errors now share one canonical UPPER_SNAKE_CASE shape**: `{"success": false, "error": "INVALID_WHEN", "field": "when", "message": "..."}`. Previously several write tools put a human sentence or a raw `str(exception)` directly in `error`. AppleScript/exception text now lives in a separate `details` field. See `docs/UPGRADING.md` for the full code list.
- **`update_todo`/`update_project`/`update_area`/`bulk_update_todos` can now clear `notes`, `deadline`, and `tags`** by passing `''` - previously an empty string was silently treated as "not provided" (a no-op), so there was no way to clear these fields. `title=''` and `when=''` are now rejected with a structured error instead of being silently ignored (`when=''` - use `'anytime'`/`'someday'` to unschedule).
- **`when='evening'` (and alias `'tonight'`) is now accepted** and correctly schedules to-dos for "This Evening" on `add_todo`/`update_todo`/`bulk_update_todos` (previously rejected by validation); `add_project`/`update_project` explicitly reject it, since Things has no "This Evening" concept for projects. `deadline` relative-keyword rejection (`'today'`, etc.) is now consistent between create and update paths - deadlines must always be `YYYY-MM-DD`.
- **`update_todo`/`bulk_update_todos`/`update_project` share one `completed`/`canceled` status-precedence rule**, and the MCP boundary now strictly parses `completed`/`canceled` as `true`/`false` (case-insensitive) - previously a typo like `completed='yes'` was silently treated as `false` and could unintentionally reopen a completed item; it now returns a structured validation error instead.
- **`get_projects`/`get_areas` no longer drop `area`/`areaTitle`/`tags` under `minimal`/`standard` response modes** - project and area rows now use their own field sets distinct from the to-do field set, so these fields survive filtering at every mode. This also fixes mixed-list project rows returned by `get_today`/`get_upcoming`/`get_anytime`/`get_someday`/`get_trash`/`search_advanced` (with `include_projects=true`), which previously lost `area`/`areaTitle` because they were converted as if they were to-dos.
- **`delete_todo` can now delete a project id** (previously always errored with a generic AppleScript failure). Headings, areas, and tags still cannot be deleted via any public Things 3 API and now return a structured `not_deletable` error naming the manual UI workflow, instead of attempting a doomed AppleScript call.
- **`get_todos(project_uuid=...)` now reads via things.py instead of AppleScript** - the AppleScript path existed to work around a suspected read-after-write lag that measurement showed does not meaningfully exist (~7-8ms observed). This also fixes `get_todos(project_uuid=..., status=...)` silently ignoring `status` when a project was given. The dead AppleScript read-parser stack (`services/applescript/parser.py`, `services/applescript/queries.py`, and related dead code) was removed as a result.
- **`get_tagged_items`/`search_advanced` no longer silently return an empty list for an unknown or wrong-case tag** - Things tag matching is exact-case, and these tools now return a structured `unknown_tag` error with title-based suggestions instead.
- **`validate_tag_list` rejects a comma inside an individual tag name** (list-input API callers only - the comma-separated string form every MCP tool actually uses is unaffected). **`remove_tags`/`add_tags` no longer over-report** the number of tags changed, and `remove_tags` no longer applies tag-creation policy (removing a tag a todo doesn't have is a no-op, not a creation/filtering decision).
- **`get_inbox`/`get_today`/`get_upcoming`/`get_anytime`/`get_someday` with `mode` omitted now behave as `mode='auto'` instead of bypassing response-mode handling entirely.** Previously an omitted `mode` skipped the context manager altogether, returning raw, unfiltered rows with `structured_content.mode` left as `None`; it's now treated the same as `mode='auto'` (AUTO sizing applies - a large list becomes a summary preview) and the resolved mode is reported. Pass `mode='standard'` or `mode='raw'` explicitly if you relied on getting full, untruncated rows with `mode` omitted.
- **`update_project` now honours `canceled` instead of silently ignoring it and `completed="true"` set a completion date instead of the project's status.**
- **`get_todos` now rejects an unrecognized `status` value with a structured `invalid_status` error** instead of silently falling through to the incomplete-only default (the MCP boundary already validated `status`; this is a defence-in-depth check at the helper layer).

### Fixed
- **`add_project`/`update_project`/`add_todo`/`update_todo` no longer collapse newlines in notes** (issue #10, bug 3) - the AppleScript string escaper collapsed `\n`/`\r` to a single space before this release, so multi-line project/todo notes written through any of these tools lost their paragraph breaks. All AppleScript-string-building call sites now share one escaper that maps newlines/carriage returns/tabs to their AppleScript literal escape sequences, so they survive intact inside the generated script. A related bug where a value ending in a literal double quote (e.g. `title='Say "hi"'`) could produce an unbalanced, syntactically-broken AppleScript string was fixed as part of the same consolidation.
- **`add_todo` via the Things URL scheme no longer risks returning the wrong id when two to-dos share a title** - it previously identified the newly-created to-do by title and 1-second-granularity creation timestamp after a fixed sleep; it now snapshots existing ids before the create and polls for the new id, disambiguating (with a warning) when more than one appears and returning a clear failure instead of a false success when none appears within the poll window.
- **`add_todo(heading=...)` is now honoured on every path, and `list_id` is properly escaped/resolved** - `heading` and `list_title` were previously only forwarded when a checklist was also supplied, and `list_id` was interpolated into AppleScript unescaped.
- **Moving/adding under a completed heading or project no longer silently reopens it** - `add_todo`/`update_todo` now pre-check the target's status and reject the write with a structured `TARGET_COMPLETED` error instead of visibly reopening pre-existing user data in Things.
- **`get_todo_by_id` now resolves projects, headings, trashed items, and areas** (previously raised `ValueError: Todo not found` for anything but a to-do); a tag uuid now returns a structured error instead of a misleading, mostly-empty to-do-shaped dict.
- **Todos filed under a heading now report `project`/`projectTitle`** (previously always `None` - things.py only carries these fields on the heading's own row, not its children).
- **`get_activating_in_days` no longer returns already-active todos**, and **`get_due_in_days`'s overdue-inclusion behavior is now explicit** via `include_overdue` (see Added).
- **`get_logbook`/`get_recent` no longer silently drop rows with a timezone-aware completion/creation date** in the (unlikely, but possible) case things.py emits one.
- **Empty list results now report a concrete effective `mode`** instead of the literal string `"auto"` when `mode` was omitted or `'auto'`.
- **Whitespace-only `when` (e.g. `'   '`) is now rejected** with the same structured error as `when=''`, instead of silently becoming a no-op.
- **Checklist tools (`add_checklist_items`/`prepend_checklist_items`/`replace_checklist_items`) now surface the auth-token `hint`** on failure, matching `update_todo`'s heading/evening paths.
- **URL-scheme-based write tools now fail fast with a structured error when the Things auth token is missing, instead of returning `success: true` while silently doing nothing.** `add_checklist_items`/`prepend_checklist_items`/`replace_checklist_items` (and any other tool routed through `things:///update`, e.g. `update_todo`'s heading/evening paths) previously invoked `open` on the URL scheme even with no token configured; Things itself rejects the un-authenticated request, but `open -g` still exits 0, so the tool reported success though nothing happened. A new `AUTH_REQUIRING_ACTIONS` gate now checks for a configured token before ever invoking `open`, returning a structured error with an actionable `hint` instead.
- **Removed 4 stale tests asserting `add_todo` accepts undocumented `url`/`status` kwargs** - `url` and `status` were never real parameters exposed by the MCP tool (only reachable via direct `ThingsTools` calls, always a silent no-op); no production code changed, only the dead `xfail` tests were dropped.
- **`scheduling/todo_operations.py` (`add_todo`/`update_todo`/`add_project`/`update_project`/checklist scheduling) now returns the same structured UPPER_SNAKE_CASE write-tool error shape as the rest of the write layer**, instead of human-string/`str(exception)` values in `error` (e.g. an unknown `list_id`/`list_title` now reports `NOT_FOUND`, an ambiguous `list_title` reports `AMBIGUOUS_TARGET` with the matching ids in a new `ids` field, an unconfirmed URL-scheme create reports `CREATE_UNCONFIRMED`, `when='evening'` on a project reports `UNSUPPORTED_FOR_PROJECTS`, and an empty `heading` on `update_todo` reports `INVALID_HEADING`); the Things URL-scheme auth-gate (`AppleScriptManager.execute_url_scheme`) now reports a stable `AUTH_TOKEN_NOT_CONFIGURED` code with the previous literal error text preserved verbatim in `message`, forwarded as-is by every consumer (`add_checklist_items`/`prepend_checklist_items`/`replace_checklist_items`/`update_todo`/`bulk_update_todos`).

### Removed
- **Dead AppleScript read-parser stack** (`services/applescript/parser.py`, `services/applescript/queries.py`, related manager methods and config flags) - reads have gone through things.py exclusively since the `get_todos(project_uuid=...)` fix above; nothing called this code anymore.
- **Dead `ResponseOptimizer`/`response_optimizer.py`** - unused, and built against a stale pre-1.7.0 field schema that no longer matched real converter output.

### Docs
- **README "Why this server?" section and `docs/COMPARISON.md`** - a new README section answering "why this instead of hald/things-mcp?", pointing to a dated feature-matrix comparison doc.

### Known limitations
- Headings cannot be renamed or deleted via any public Things 3 API (no AppleScript heading class); they can only be created via `add_project`'s `##` lines - placing a to-do under a heading via `add_todo`/`update_todo`'s `heading=...` requires the heading to already exist and creates nothing on its own (an unknown heading name produces a `warnings` entry, not a new heading).
- `things.py` reads can lag a Things URL-scheme write (`things:///add`, `things:///update` - used for headings, checklists, `when='evening'`) by roughly 1-2 seconds, since the write is processed asynchronously while things.py reads the local SQLite snapshot directly. Plain AppleScript writes do not have this lag.
- Writing into (or moving a to-do into) a completed/canceled project or heading is refused with a structured `TARGET_COMPLETED` error rather than reopening it - reopen the target manually in Things first, or choose another target.

## [1.6.2] - 2026-08-19

### Fixed
- **Generated uvx launch configs now pin a managed Python, fixing `.mcpb` startup failures in Claude Desktop** - the 1.6.1 `.mcpb`, launched via `uvx mcp-server-things`, could resolve an x86_64 Python from the host app's environment (e.g. a bundled miniconda); `cryptography==50.0.0` has no macOS x86_64 wheels, so `uvx` fell back to a maturin source build that fails without a Rust toolchain, silently killing server startup. `manifest.json`'s `server.mcp_config.args` and `client_config.build_server_config`'s `uvx` variant (used by `mcp-server-things config` and `--write`) now both emit `["--python-preference", "only-managed", "--python", "3.12", "mcp-server-things"]`, forcing uv to use its own managed, native-arch CPython instead of anything discovered on `PATH`. Trade-off: first launch may download a managed CPython (one-time). Plain `uvx mcp-server-things` remains in prose/troubleshooting examples for interactive use; only generated configs are hardened. Verified: `uvx --python-preference only-managed --python 3.12 mcp-server-things@1.6.1 doctor` passes all checks on affected hardware.

## [1.6.1] - 2026-08-19

### Added
- **`mcp-server-things doctor` now checks Python architecture** - a new "Python architecture" check WARNs when the running interpreter is x86_64 (Rosetta) on Apple Silicon hardware, since transitive dependencies (e.g. `cryptography>=50`) ship no macOS x86_64 wheels and `uvx mcp-server-things` can fail with `Building cryptography==...` maturin/Rust build errors in that case. PASSes on a matching arm64-on-Apple-Silicon or x86_64-on-Intel setup (noting the same wheel gap for genuine Intel Macs). README and docs/UPGRADING.md now call out the fix (`uvx -p 3.12 mcp-server-things` with an arm64 interpreter).

## [1.6.0] - 2026-08-19

Upgrading from an existing install? See [docs/UPGRADING.md](docs/UPGRADING.md)
for what's new, what (if anything) to review, and how to switch to `uvx`.

### Added
- **Optional HTTP transport** - `THINGS_MCP_TRANSPORT=stdio|http` (default `stdio`), `THINGS_MCP_HOST` (default `127.0.0.1`), and `THINGS_MCP_PORT` (default `8000`) env vars, plus matching `--transport {stdio,http}`/`--host`/`--port` CLI flags (CLI overrides env), select and configure the MCP transport. `http` serves the MCP endpoint at `/mcp` via FastMCP's built-in HTTP transport - the reliable workaround when a client's stdio subprocess lacks Automation (TCC) access to Things 3: run the server from a Terminal that has been granted access, then point the client at the HTTP URL (e.g. `claude mcp add --transport http things http://127.0.0.1:8000/mcp`) instead of launching it as a subprocess. Invalid transport values raise a clear startup error.
- **`mcp-server-things config`** - a `--client claude-desktop|claude-code|generic [--via uvx|current-python] [--write] [--force]` subcommand (also `python -m things_mcp config`) that prints the MCP client configuration for the requested client instead of requiring users to hand-edit JSON: `claude-desktop` prints the `{"mcpServers": {"things": ...}}` snippet plus the config file location; `claude-code` prints the exact `claude mcp add-json things '...'` one-liner and its `-s user` variant; `generic` prints just the server-config object. `--via current-python` targets the currently-running interpreter (`sys.executable -m things_mcp`) for existing venv/pip installs instead of the default `uvx mcp-server-things`. `--write` (claude-desktop only) safely merges the config into `~/Library/Application Support/Claude/claude_desktop_config.json`: it preserves all other file content, backs up the previous file to a timestamped `.bak.<UTC timestamp>` before writing, refuses to overwrite an existing, different `things` entry unless `--force` is passed, and is a no-op (no write, no backup) when the entry already matches.
- **`mcp-server-things doctor`** - a read-only diagnostic subcommand (also `python -m things_mcp doctor`) that checks Things 3 installation, whether it's running, macOS Automation (TCC) permission, database readability (Full Disk Access), `uv`/`uvx` on `PATH`, the optional Things URL-scheme auth token file, and Python/fastmcp/things.py/server version info. Prints a PASS/FAIL/WARN/INFO table with a one-line fix hint per non-PASS row and exits non-zero only if any check FAILs; `--json` prints machine-readable output instead. Never starts the FastMCP server or modifies Things data. README Troubleshooting now points to it first.
- **Packaging entry points are now test-guarded** - `tests/unit/test_packaging_entry_points.py` asserts `[project.scripts]` maps `mcp-server-things` and `things-mcp` to importable, callable `things_mcp.main:main`, verifies `python -m things_mcp --version` and the console-script call path both print the version and exit 0, and (best-effort, skips gracefully if the build environment can't build) checks a built wheel's `entry_points.txt` and that no `src/`-prefixed paths leak into the wheel.
- **`get_tag_usage` now counts Area tag usage** - previously only todos and projects were tallied, so a tag applied solely to an Area (e.g. an area-level organizational tag) was incorrectly reported as unused. Each row now includes an `area_count` field (also added into `total_count`); areas have no open/closed state, so area usage never contributes to `open_count`. Documented in the tool docstring, README, and CLAUDE.md, along with a pre-existing caveat that usage rows are keyed by tag *title*, so two distinct tags sharing an identical title (e.g. a parent tag and a same-named child tag) are silently merged into one row.
- **`scripts/gen_manifest_tools.py`** - generates `manifest.json`'s `tools` array from the server's actually-registered MCP tools (`--check` to detect drift, `--write` to sync); `scripts/build_mcpb.sh` now runs `--check` before packing (best-effort: skipped with a warning if `fastmcp` isn't importable by the system `python3`), and a new unit test (`tests/unit/test_manifest_tools_sync.py`) guards against drift going forward. Fixes `manifest.json` listing a removed tool (`show_item`) and omitting 11 registered tools (`create_tag`, `delete_todo`, `get_todo_by_id`, `get_tag_usage`, `get_due_in_days`, `get_activating_in_days`, `health_check`, `queue_status`, `context_stats`, `get_server_capabilities`, `get_usage_recommendations`)
- **`docs/UPGRADING.md`** - an upgrade guide for existing (≤1.5.0) users covering what's backward compatible, behavioural changes to review (`get_someday` default, `tag_creation_policy=fail_on_unknown` now enforced, `structured_content` shape, the `search_advanced` `type=` fix, empty tag-entry stripping), how to switch to `uvx`, and how to roll back. Linked from the README's Advanced install details and from this section. Servers launched via the legacy `things-mcp` console alias or a `src/`-layout `PYTHONPATH` checkout now print a one-line INFO tip pointing at it once logging is configured at startup.
- **README Troubleshooting: "Reads fail but writes work" section** - documents the TCC/Full Disk Access failure mode where Claude Desktop's disclaimer launch helper prevents the spawned server from inheriting Full Disk Access, so every read tool fails instantly with `unable to open database file` while writes and AppleScript still work; includes a fix ladder (HTTP transport from Terminal, granting FDA to the actual launched binary, confirming via `doctor`) and credits the upstream report at [hald/things-mcp#62](https://github.com/hald/things-mcp/issues/62). The `doctor` "Database readable" FAIL hint now cross-links to this section.

### Changed
- **README installation rewritten uvx-first, hald-style** - the top of the README is now Prerequisites (4 bullets) → Install (Claude Desktop / Claude Code / Any MCP client, each with copy-pasteable one-liners) → Verify (`doctor` + a smoke-test prompt), all in ~70 lines. The pip/virtualenv/from-source/existing-venv install paths and Claude Desktop's PyPI/source JSON configs are preserved verbatim inside a collapsed `<details>` block rather than removed. `## Configuration` is trimmed to a 5-row table of the highest-impact env vars plus a link to `.env.example` for the full list; the previously-inline "Key Configuration Options" block is dropped since every var it listed is already documented in `.env.example`. Also fixed a heading-nesting inconsistency in Troubleshooting: "Reads fail but writes work" is now `###` (a sibling of `### Common Issues`) instead of `####`.
- `get_someday` no longer includes tasks from Someday projects by default; pass `include_project_tasks=true` to include them (marked `inheritedSomeday`)
- Read tools return structured_content `{items, count, total, mode, limit, offset}`; under `mode=summary` count = number of preview items and the full count is in `total`

### Fixed
- **`add_tags`/`add_todo`/`update_todo` message enrichment read the wrong `tag_info` keys** - the MCP tool layer looked up `tag_info['created_tags']`/`['filtered_tags']`, but `write_operations._prepare_tags`/`_validate_tags_with_policy` actually populate `created`/`filtered`/`existing`/`warnings`/`errors`, so the "Created new tags: ..." / "Filtered tags..." message enrichment was silently a no-op in all three tools. Also fixed: every comma-separated tag string parsed in `server.py` (`add_todo`, `update_todo`, `bulk_update_todos`, `add_project`, `update_project`, `add_area`, `update_area`, `add_tags`, `remove_tags`) kept empty entries for inputs like `"a,,b"` or `"a, "`, which could send an empty-string tag name through to Things 3; all sites now share a single `_parse_tag_list()` helper that strips and drops empty entries.
- **`add_tags` ignored `tag_creation_policy` failures** - it called `_validate_tags_with_policy` directly and never checked the `errors` field, so under `fail_on_unknown` it still wrote the known tags to AppleScript and reported success instead of aborting. `add_tags` now goes through the shared `_prepare_tags` helper (like `add_todo`/`add_project`/`add_area`) and returns a structured `{"success": false, "error", "message", "tag_info"}` without touching AppleScript when the policy rejects the tags.
- **Duplicate tag names in generated AppleScript under `allow_all`** - `_prepare_tags` computed `valid_tags = existing + created`, but `TagValidationService.valid_tags` already includes newly-created tags, so a newly-created tag appeared twice in the resulting `set tag names` script. `_prepare_tags` now dedupes with an order-preserving `list(dict.fromkeys(...))`.
- **Hermetic URL-scheme unit test**: `test_execute_url_scheme_without_parameters` no longer depends on whether a local `.things-auth` file exists (it now clears the manager's auth token explicitly).
- **`get_server_capabilities` reported a hardcoded, stale `total_tools` (30) instead of the real number of registered tools** - `server_info.total_tools` and `api_coverage.total_tools` are now computed at runtime from the FastMCP tool registry (`FastMCP.list_tools()`) via a new `ThingsMCPServer._registered_tool_count()` helper, so the reported count can never drift from what's actually registered
- **`tag_creation_policy` was not honoured for `add_project`/`update_project`/`add_area`/`update_area`** - only `add_todo`/`update_todo`/`add_tags` validated tags against the configured policy (`allow_all`/`filter_silent`/`filter_warn`/`fail_on_unknown`) before writing; projects validated *after* already sending the unfiltered tags to AppleScript, and areas never consulted the tag validation service at all
  - All five write operations now share a `WriteOperations._prepare_tags()` helper that validates and filters tags via `TagValidationService` before the AppleScript write; `fail_on_unknown` now actually aborts the operation (previously the `errors` field was silently dropped and never checked)
  - When every requested tag is filtered out, `add_*` proceeds without tags and `update_*` leaves existing tags unchanged (skips the `set tag names` statement rather than clearing)
- **`structured_content['mode']` echoed the literal string `"auto"` instead of the effective response mode** - when a read tool was called with `mode='auto'` (or `mode` omitted), `_read_result` reported the requested mode instead of the resolved one
  - `context_manager.optimize_response` records the concrete mode it selected (`"summary"`, `"minimal"`, etc.) either in `meta['mode']` or, for the summary-shaped payload from `create_summary_response`, as a top-level `mode` key with no `meta` at all
  - `_read_result` now resolves `mode='auto'`/`None` from `meta['mode']` or the top-level `mode` key (in that order) instead of echoing back the request; the originally-requested mode is preserved in the new `requested_mode` field
- **`search_advanced` crashed when `type` was supplied** - `things.api.tasks() got multiple values for keyword argument 'type'`
  - `_search_advanced_sync` always called `things.todos(**query_params)`, which internally hardcodes `type="to-do"`; passing a caller-supplied `type` filter raised a `TypeError`
  - Now calls `things.tasks(**query_params)` directly when a `type` filter is present (preserving `things.todos()` for the no-`type` case), and validates `type` against `{'to-do', 'project', 'heading'}` up front, returning a structured error for invalid values
- **`doctor`'s Environment check could hang on the exact TCC stall it exists to diagnose** - `check_environment()` did a bare `import things` to read the package version, but `things` performs an unbounded filesystem glob at import time; if `check_database_readable`'s bounded worker thread was already stuck inside that same import, `check_environment`'s own `import things` would block indefinitely on Python's per-module import lock (which has no timeout), hanging `doctor` on precisely the broken machines it's meant to help. It now reads the version from `sys.modules` without importing - if `check_database_readable` (which runs first) already completed the import, the version is available; otherwise the detail reports `things=unknown (import not completed)` and no import is attempted. The "Database readable" WARN-on-timeout hint now also references the README's "Reads fail but writes work" troubleshooting section, since a persistent timeout there is one symptom of the same TCC issue.

## [1.5.0] - 2026-07-20

### Added
- **Boot-phase diagnostics** - stderr markers and a startup watchdog to make cold-start hangs diagnosable
  - Timestamped `things-mcp boot: <ts> +<elapsed>s <phase>` marker lines are written to stderr at each boot phase, from process start through the MCP stdio handshake
  - A one-shot startup watchdog (`THINGS_MCP_BOOT_WATCHDOG_SECS`, default 25s) dumps every thread's Python stack to stderr if boot stalls past the deadline; setting the value to `0` (or any value `<= 0`) disables it
  - The watchdog cannot be canceled once armed, so a healthy, long-running server will emit one benign stack dump to stderr when the deadline elapses during normal operation - this is expected and does not affect the MCP stdio protocol (which only uses stdout)
  - `THINGS_MCP_THINGS_IMPORT_TIMEOUT_SECS` (default 10s) bounds the lazy import of the third-party `things` package; a value `<= 0` makes the import unbounded (blocking, like a plain `import things`)

### Fixed
- **Intermittent overnight cold-start hang** - `import things` executed an unbounded, synchronous module-level `glob.iglob()` scan of `~/Library/Group Containers/.../ThingsData-*` on the boot critical path, before the MCP handshake completed
  - The import is now lazy and timeout-bounded (default 10s via `THINGS_MCP_THINGS_IMPORT_TIMEOUT_SECS`), raising `ThingsImportTimeoutError` with boot markers on stall instead of silently hanging until the client's own connect timeout fires

## [1.4.5] - 2026-06-05

### Fixed
- **Removed blocking AppleScript probe from server startup** - fixes intermittent "failed to connect" errors
  - `ServerManager.start()` ran a synchronous `osascript "tell application Things3"` probe before the MCP stdio loop started
  - The probe gated nothing (it only logged) but blocked the MCP handshake for up to 5s, auto-launched Things 3, and could trigger a macOS Automation (TCC) consent dialog that stalled long enough for clients to mark the server as failed
  - Things 3 availability is already checked lazily on the first tool call via `AppleScriptManager` (async, with retries); explicit checks remain via `--health-check` / `--test-applescript`
- **Fixed stale hardcoded version in `--version` output** - now reports the actual package version instead of "1.0.0"

## [1.4.4] - 2026-02-25

### Fixed
- **Upgraded things.py to v1.0.0** to fix SQLite lock contention with Things 3
  - things.py 0.x held open SQLite connections via the `things3` module, blocking Things 3's WAL commits during cloud sync
  - things.py 1.0.0 uses read-only connections with proper cleanup via `weakref.finalize()`
  - Resolves intermittent Things 3 UI freezes caused by `btreeInvokeBusyHandler` blocking on sync commits

## [1.4.3] - 2026-02-02

### Fixed
- **Fixed Claude API JSON schema error** - Removed `Union` types from tool return annotations
  - Claude API rejects schemas with `oneOf`/`allOf`/`anyOf` at top level
  - FastMCP generates `oneOf` from `Union[...]` return type annotations
  - Changed 5 tools (`get_inbox`, `get_today`, `get_upcoming`, `get_anytime`, `get_someday`) from `Union[List[Dict], Dict]` to `Dict[str, Any]`
  - These functions already wrap responses via `context_manager.optimize_response()`, so the type annotation now matches actual behavior

## [1.4.2] - 2025-12-22

### Changed
- **Consolidated `get_upcoming` API** - Added optional `days` parameter to `get_upcoming`
  - `get_upcoming()` - Returns items from Things 3's Upcoming list (unchanged)
  - `get_upcoming(days=30)` - Returns todos due/activating within 30 days (new)
  - Removed redundant `get_upcoming_in_days` tool - use `get_upcoming(days=N)` instead
  - Simpler, more intuitive API with one tool instead of two

### Fixed
- **Fixed validation error** - `get_upcoming(days=30)` now works correctly
  - Previously failed with "Unexpected keyword argument" error

## [1.4.1] - 2025-10-04

### Changed
- **Checklist API improvement** - Changed checklist parameters from newline-delimited strings to List[str]
  - `add_todo(checklist_items=...)` now accepts `List[str]` instead of `str`
  - `add_checklist_items(items=...)` now accepts `List[str]` instead of `str`
  - `prepend_checklist_items(items=...)` now accepts `List[str]` instead of `str`
  - `replace_checklist_items(items=...)` now accepts `List[str]` instead of `str`
  - More idiomatic API design - pass lists directly instead of manually joining with newlines
  - Internal conversion to URL scheme format happens transparently

### Documentation
- Updated CLAUDE.md with List[str] examples for all checklist operations
- Updated test examples to use list format

## [1.4.0] - 2025-10-04

### Added
- **Checklist item support** - Full support for creating and managing checklist items via Things URL scheme
  - `add_todo()` automatically uses URL scheme when `checklist_items` parameter is provided
  - New `add_checklist_items()` tool to append items to existing todo checklists
  - New `prepend_checklist_items()` tool to prepend items to existing todo checklists
  - New `replace_checklist_items()` tool to replace all checklist items
  - Checklist items returned in todo queries with status (complete/incomplete)
  - Maximum 100 checklist items per todo

### Changed
- **Smart hybrid approach** - `add_todo()` now automatically selects optimal creation method
  - Uses Things URL scheme when checklist items are provided (only way to create checklists)
  - Uses AppleScript for non-checklist todos (faster, more reliable)
  - No API changes required - transparent to users

### Fixed
- **Removed checklist limitation** - Previous limitation documented in CLAUDE.md is now resolved
  - Checklists were not supported via AppleScript (Things 3 API limitation)
  - Now fully supported via Things URL scheme integration

### Documentation
- Added comprehensive checklist usage examples to CLAUDE.md
- Added checklist architecture documentation to ARCHITECTURE.md
- Updated known limitations section (checklist support now complete)

## [1.3.2] - 2025-10-04

### Fixed
- **CRITICAL: Project initial todos not retrieved** - Fixed parser consuming multiple records as single field value
  - AppleScript parser now correctly handles "missing value" in date fields
  - Prevents field bleeding when date values are missing
  - All initial todos now properly returned by get_todos(project_uuid=...)
- **HIGH: Summary mode empty preview** - Fixed preview showing null IDs and empty names
  - Updated to check both uuid/id and title/name dictionary keys
  - Summary mode now displays actual todo/project information
  - Backwards compatible with different data schemas

## [1.3.1] - 2025-10-03

### Fixed
- **Bug fix: NoneType error in mode='standard'** - Fixed crash when notes field is None
  - Added null check before len() operation in context_manager.py
  - Affected get_todos() and other operations using standard response mode
- **Bug fix: Date field formatting** - Fixed §COLON§ markers and field bleeding in dates
  - Added comma escaping to AppleScript date formatting
  - Prevents date values from breaking field boundaries
  - Affects creation_date, modification_date, activation_date, due_date fields

### Changed
- **Documentation: add_project todos parameter** - Corrected CLAUDE.md to reflect that todos parameter works correctly
  - Removed incorrect "Known Limitation" entry
  - Added usage examples and best practices

### Added
- **Test infrastructure** - Added comprehensive integration and unit test suites
  - 17 integration tests with automatic cleanup mechanism
  - 27 new unit tests for date utilities and edge cases
  - Test fixtures and shared test data
  - Integration test documentation and verification tools

## [1.3.0] - 2025-10-03

### Changed
- **NEW: State machine AppleScript parser** - Default parser changed from legacy string manipulation to state machine (BREAKING: fixes bugs)
  - New state machine parser is now the default (`use_new_applescript_parser=True`)
  - Legacy parser deprecated with warning messages
  - Set `use_new_applescript_parser=False` to temporarily use legacy parser
  - Legacy parser will be removed in v2.0.0

### Fixed
- **Bug fix: completion_date parsing** - New parser correctly handles completion_date with commas
  - Legacy parser left §COMMA§ placeholders (bug)
  - New parser correctly parses dates: "Monday, January 15, 2024 at 2:30:00 PM"
- **Bug fix: cancellation_date parsing** - New parser correctly handles cancellation_date with commas
  - Same §COMMA§ placeholder bug fixed
  - Dates now properly parsed to ISO format
- **Bug fix: Date validation** - Added validation for when/deadline parameters across all operations
  - Validates dates before sending to AppleScript, preventing silent failures
  - Supports relative dates (today, tomorrow, someday) and absolute dates (YYYY-MM-DD)
  - Applied to add_todo, update_todo, bulk_update_todos, add_project, update_project
- **Bug fix: Status parameter normalization** - Handle MCP passing string "None" for status parameter
  - MCP clients may pass status="None" as a string instead of null
  - Now correctly normalizes to None for get_todos and other operations
- **Bug fix: Parameter sanitization** - Filter out None values from sanitized parameters
  - Prevents None values from being included in validated parameter dictionaries
  - Improves reliability of bulk operations and tag handling

### Added
- **Feature flag: use_new_applescript_parser** - Configuration option to control parser selection
  - Default: true (new state machine parser)
  - Set to false for legacy behavior (deprecated)
- **State machine parser implementation** - Clean room implementation with proper state machine
  - Handles quoted strings with commas and colons correctly
  - Handles nested lists with braces properly
  - Intelligent date field parsing
  - No placeholder workarounds needed
- **Comprehensive parser tests** - 62 new test cases added
  - 44 unit tests for state machine parser
  - 18 integration tests comparing old vs new parsers
  - All tests validate parser equivalence
- **Performance: Optimized search operations** - 10-100x faster using things.py instead of AppleScript
  - get_due_in_days now uses database queries for instant results
  - get_activating_in_days optimized with direct database access
  - search_advanced now searches entire database including project todos (previously limited to lists only)

### Deprecated
- **Legacy string manipulation parser** - Will be removed in v2.0.0
  - Warning logged on initialization if legacy parser is used
  - Known bugs: completion_date and cancellation_date field parsing
  - Recommend setting `use_new_applescript_parser=True`

## [1.2.7] - 2025-10-01

### Removed
- **THINGS_MCP_SERVER_VERSION environment variable** - Removed unused configuration option
  - Version is now automatically managed from package metadata (`__version__` in `__init__.py`)
  - No need for manual version configuration
  - Updated README.md to remove this configuration example

### Documentation
- **Release process** - Added comprehensive release process documentation to CLAUDE.md
  - Step-by-step guide for version updates across all files
  - Git tagging and GitHub release creation instructions
  - PyPI publishing workflow
  - Release checklist to ensure consistency
  - Version consistency notes explaining where versions live

## [1.2.6] - 2025-10-01

### Fixed
- **Version reporting** - Server now correctly reports actual package version (was hardcoded to "2.0")
  - Added `__version__` variable to `src/things_mcp/__init__.py`
  - Updated `get_server_capabilities()` to use dynamic `__version__` instead of hardcoded string
  - When AI asks "what version is running?", it now correctly reports 1.2.6 instead of 2.0
  - Version is automatically synced with pyproject.toml

### Added
- **Version management** - Single source of truth for version number
  - `__version__` in package __init__.py
  - Imported by server.py for runtime reporting
  - Ensures pyproject.toml and runtime version always match

## [1.2.5] - 2025-10-01

### Fixed
- **Critical: bulk_update_todos tag handling** - Added extra defensive code to handle edge case where tags parameter might be passed as string instead of list
  - If tags is a string, it's now automatically split by comma before processing
  - Prevents individual characters from being treated as separate tags
  - Fixes AppleScript error: "Can't make {\"E\", \"v\", \"a\", ...} into type text" (-1700)
  - Added comprehensive unit tests to verify the fix
  - BUG FIX #8: This adds an extra safety layer on top of server.py's string-to-list conversion

### Added
- **Test coverage** - Added `test_bulk_update_tags_string_bug.py` with 3 test cases
  - Test single-tag string handling without splitting into characters
  - Test comma-separated tag string splitting
  - Test list format handling (correct format)

## [1.2.4] - 2025-10-01

### Documentation
- **USER_EXAMPLES.md complete rewrite** - Comprehensive tested workflows (935 lines)
  - All examples verified with actual Things 3 MCP server operations
  - GTD-focused workflows: inbox processing, weekly review, context switching
  - Document/email parsing examples with real action item extraction
  - Bulk operations: quarterly cleanup, quick wins sprints, multi-field updates
  - Smart queries: stalled work detection, deadline dashboards, tag-based filtering
  - Advanced automation: meeting preparation, time-blocked planning, energy-based scheduling
  - Progressive learning path from simple to power user workflows
  - Generic, non-personal data used throughout all examples
  - Includes exact MCP function calls with parameters and expected results
  - 15 major workflow categories with copy-paste conversation starters
  - Troubleshooting guide and best practices for mode parameters
  - Creative use cases: reading challenges, learning paths, habit tracking

### Changed
- **Test artifacts in .gitignore** - Added pytest.log, *.log, htmlcov/, .pytest_cache/
  - Prevents test logs and coverage reports from being committed
  - Cleaner git status for development workflow

## [1.2.3] - 2025-10-01

### Fixed
- **Status filtering enhancements** - Improved `get_todos()` status parameter handling
  - Fixed status filtering logic to properly use AppleScript status property values
  - Automatically includes Logbook when searching for completed or canceled todos
  - Properly maps between MCP status values ('incomplete', 'completed', 'canceled') and AppleScript ('open', 'completed', 'canceled')
- **Project todo assignment** - Fixed `list_id` parameter handling in `add_todo()`
  - Now correctly uses `project id "UUID"` syntax to assign todos to projects
  - Handles both `project` and `list_id` parameters for backward compatibility
- **Project query reliability** - Implemented hybrid approach for project-filtered queries
  - Uses AppleScript for project queries to avoid SQLite database sync timing issues
  - Ensures queries return immediately accurate results after AppleScript writes
  - Falls back to things.py database queries when AppleScript unavailable

### Added
- **Enhanced test coverage** - Added 4 comprehensive unit test suites
  - `test_tag_management_comprehensive.py` - 29 tests for all tag operations
  - `test_status_filter.py` - Tests for status filtering edge cases
  - `test_search_advanced_status_filter.py` - Advanced search status tests
  - `test_delete_validation.py` - Delete operation validation tests
  - All tests passing (327 total unit tests)

### Documentation
- **CLAUDE.md enhancements** - Comprehensive updates to AI assistant instructions
  - Added detailed status filtering documentation with examples
  - Documented project/area hierarchical organization best practices
  - Enhanced common pitfalls section with tag management guides
  - Added multi-field bulk update usage examples
- **Repository cleanup** - Removed 87 temporary analysis and test report files
  - Cleaned up docs/ directory (removed temporary FIX_STRATEGY files)
  - Removed diagnostic test scripts and log files
  - Improved repository organization and maintainability

### Changed
- Status parameter now defaults to 'incomplete' for `get_todos()` (explicit default)
- Project queries optimized for real-time accuracy using application state
- Improved error messages for validation failures

## [1.2.2] - 2025-09-30

### Fixed
- **Tag concatenation bug** - Fixed critical bug where multi-tag operations concatenated tags into single malformed tag (#5)
  - `add_tags()`, `remove_tags()`, and `bulk_update_todos()` now properly handle comma-separated tags
  - Changed from AppleScript list syntax to comma-separated string format per Things 3 API requirements
  - Example: `add_tags(tags="test,urgent,High")` now creates 3 separate tags instead of "testurgentHigh"
- **Bulk update multi-field support** - Fixed bug where only last field was applied in multi-field updates
  - `bulk_update_todos()` now correctly applies all specified fields (tags, when, deadline, notes, etc.)
  - Enhanced with separate scheduling via reliable_scheduler to prevent field conflicts
- **Zero limit handling** - Fixed search operations returning all results when `limit=0`
  - Now correctly returns empty list when `limit=0` is specified
  - Added explicit zero-check validation in search operations
- **Empty result handling** - Fixed inconsistent empty result behavior in time-based queries
  - `get_todos_due_in_days()`, `get_todos_activating_in_days()`, `get_recent()` now consistently return empty lists
  - Added informative logging for empty result scenarios
- **Status update parameters** - Fixed string boolean parameter handling in todo updates
  - `update_todo()` now accepts both string ("true"/"false") and boolean (True/False) parameters
  - Added `_convert_to_boolean()` helper method for comprehensive type conversion
  - Supports case-insensitive string values: "true", "True", "TRUE", etc.

### Added
- **Comprehensive parameter validation layer** - New `parameter_validator.py` module
  - Validates limit, offset, days, status, dates, periods, tags, and more
  - Standardized error responses with field-specific validation messages
  - Type conversion for flexible parameter handling
  - 76 unit tests covering all validation methods
- **Enhanced test coverage** - 14 new regression tests for bug fixes
  - 6 tests for tag removal string parsing (`TestRemoveTags`)
  - 8 tests for bulk update multi-field operations (`TestBulkUpdateTodos`)
  - 11 tests for empty result handling (`tests/unit/test_empty_results.py`)
  - All tests passing (100% success rate)
- **Debug logging enhancements** - Added detailed logging for edge cases
  - Zero limit scenarios
  - Empty result detection
  - Boolean parameter conversion
  - AppleScript generation for troubleshooting

### Changed
- **Test pass rate improved** - From 92% (46/50) to 100% (50/50) after bug fixes
- **Quality score increased** - From 90% to 95% (production-ready)
- **Tag operation architecture** - Complete rewrite of tag handling pattern
  - All tag operations now use comma-separated string format
  - Hybrid approach: Parse in Python, set as string in AppleScript
  - Improved reliability and consistency across all tag operations

### Documentation
- Updated CLAUDE.md with comprehensive bug fix documentation
  - Tag management best practices and pitfalls
  - Bulk operation multi-field usage examples
  - Common error scenarios and solutions
- Added detailed inline code comments explaining AppleScript API quirks
- Enhanced validation documentation with usage examples

## [1.2.1] - 2025-09-29

### Fixed
- Tag concatenation bug in `add_tags` function (#5)
- Tags now properly joined with commas instead of being concatenated

## [1.2.0] - 2025-09-25

### Added
- Bulk update functionality for efficient batch operations
- `bulk_update_todos()` method for updating multiple todos at once
- `bulk_move_records()` method for moving multiple todos efficiently

### Changed
- Improved context management for large operations
- Enhanced response optimization modes

## [1.1.3] - 2025-09-20

### Fixed
- Fixed deadline property name in Things 3 AppleScript API (#4)
- Corrected property name from `due_date` to `deadline` in AppleScript commands

## [1.1.2] - 2025-09-15

### Fixed
- Missing dateparser dependency in requirements

### Changed
- Updated README with correct PyPI vs source installation instructions
- Clarified configuration documentation

## [1.1.1] - 2025-09-10

### Fixed
- Tag validation and simplified codebase architecture (#3)
- Improved error handling for tag operations

## [1.1.0] - 2025-09-05

### Added
- Context-aware response optimization
- Progressive disclosure modes (auto/summary/minimal/standard/detailed/raw)
- Smart limiting for search operations

### Fixed
- Date validation bug in scheduling operations

## [1.0.0] - 2025-09-01

### Added
- Initial public release
- MCP server implementation for Things 3
- Hybrid architecture (things.py for reads, AppleScript for writes)
- Support for todos, projects, areas, tags
- Comprehensive test suite

---

## Version 1.2.2 - Bug Fix Summary

This release resolves **critical bugs** discovered during comprehensive edge case testing, improving reliability and production readiness.

### Critical Bugs Fixed

1. **Tag Concatenation Bug** (CRITICAL)
   - **Severity:** HIGH - Data corruption in tag management
   - **Impact:** Multi-tag operations created single malformed tags
   - **Resolution:** Complete rewrite of tag operations using comma-separated strings
   - **Files Modified:** `src/things_mcp/tools.py` (3 functions)
   - **Tests Added:** 6 regression tests in `TestRemoveTags`

2. **Bulk Update Multi-Field Bug** (CRITICAL)
   - **Severity:** HIGH - Only last field applied in batch operations
   - **Impact:** Multi-field bulk updates failed silently
   - **Resolution:** Enhanced architecture with separate scheduling handling
   - **Files Modified:** `src/things_mcp/tools.py` (bulk_update_todos)
   - **Tests Added:** 8 regression tests in `TestBulkUpdateTodos`

3. **Zero Limit Bug** (MEDIUM)
   - **Severity:** MEDIUM - Edge case in search operations
   - **Impact:** `limit=0` returned all results instead of empty list
   - **Resolution:** Added explicit zero validation
   - **Location:** `src/things_mcp/tools.py:266-268`
   - **Test:** `test_zero_limit` now passing

4. **Empty Result Handling Bug** (MEDIUM)
   - **Severity:** MEDIUM - Inconsistent behavior in time queries
   - **Impact:** 3 functions returned unpredictable values for empty results
   - **Resolution:** Added empty list validation with logging
   - **Location:** `src/things_mcp/pure_applescript_scheduler.py` (3 functions)
   - **Tests Added:** 11 tests in `test_empty_results.py`

5. **Status Update Bug** (HIGH)
   - **Severity:** HIGH - Core functionality broken
   - **Impact:** Could not complete/cancel todos via API
   - **Resolution:** Added `_convert_to_boolean()` with comprehensive type conversion
   - **Location:** `src/things_mcp/pure_applescript_scheduler.py:275-311`
   - **Tests:** `test_complete_todo`, `test_cancel_todo` now passing

### Test Results
- **Before:** 46/50 tests passing (92%)
- **After:** 50/50 tests passing (100%) ✅

### Quality Score
- **Before:** 90% (Production-ready after fixes)
- **After:** 95% (Production-ready) ✅

### Files Modified
- `src/things_mcp/tools.py` - Tag operations, zero limit, bulk update
- `src/things_mcp/pure_applescript_scheduler.py` - Empty results, boolean conversion
- `src/things_mcp/parameter_validator.py` - New validation layer (295 lines)
- `tests/unit/test_tools.py` - 14 new regression tests
- `tests/unit/test_empty_results.py` - 11 new tests for empty result handling
- `tests/unit/test_parameter_validator.py` - 76 validation tests
- `CLAUDE.md` - Updated with bug fix documentation and best practices

### Breaking Changes
None - All fixes maintain backward compatibility with existing API.

### Migration Guide
No migration needed - all bug fixes are transparent to existing code.

### Performance Impact
- **Tag operations:** Slight increase (< 0.2s per operation) due to additional AppleScript call
- **Validation layer:** Negligible overhead (< 1ms per operation)
- **Overall:** No noticeable performance degradation

### Recommendations for Users
1. **Update immediately** - This release fixes critical data corruption bugs
2. **Verify existing tags** - Check for any concatenated tags (e.g., "testurgentHigh")
3. **Test multi-field bulk updates** - Ensure all fields are being applied as expected
4. **Review status updates** - Verify completed/canceled operations work as expected

### Known Limitations
- Project `todos` parameter still non-functional (create project first, then add todos separately)
- Project content queries via `get_todos(project_uuid=...)` have known issues (use `search_todos()` instead)

---

## Support

- **Issues:** [GitHub Issues](https://github.com/ebowman/mcp-server-things/issues)
- **Discussions:** [GitHub Discussions](https://github.com/ebowman/mcp-server-things/discussions)
- **Email:** ebowman@boboco.ie
