# Changelog

All notable changes to the Things 3 MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`get_project_headings(project_id, mode?)` - new read-only tool for a project's heading structure** (GH#9 item 3c) - things.py supports `things.tasks(type='heading', project=...)` but no tool exposed it; the nearest workaround, `search_advanced(type='heading')`, returns headings without their to-do counts. Returns `{uuid, title, index, todoCount}` per heading, in Things' own display order, where `todoCount` is the number of open to-dos directly under that heading (`things.todos(heading=uuid)`). An unknown `project_id`, or one that resolves to something other than a project (area/to-do/heading), returns a structured error (`{"success": false, "error": "not_found"|"invalid_type", "message": ...}`) instead of raising. Read-only by design: there is no public Things 3 API to create, rename, or delete headings (no AppleScript heading class; the URL scheme only places to-dos under existing headings or seeds them at project creation via `add-project`'s `##` lines).
- **`update_todo(heading=...)` moves an existing to-do under a heading** (GH#9 item 3d) - AppleScript has no way to move a to-do under a heading, only `add_todo` (creation) had this via the Things URL scheme until now. `update_todo` now accepts `heading` (moves the to-do under that heading within its current project) and `list_id` (when given alongside `heading`, moves the to-do into that project and places it under the heading there in the same `things:///update` call). Like the other `things:///update`-based tools, this requires the Things auth token; the auth check runs *before* any AppleScript write, so a missing token returns `{"success": false, "error": "...", "hint": "..."}` without partially applying other fields passed in the same call (title, notes, tags, etc. still get applied together with the heading move when the token is configured). `heading=''` (or whitespace-only) is rejected with a structured error - Things' URL scheme has no documented way to clear a to-do out of a heading via `update` (use `move_record()` instead). If the named heading doesn't exist in the target project, or the to-do has no project and `list_id` isn't given, a `warnings` entry is added to the response since Things silently ignores `heading` in both cases rather than erroring; `list_id` resolving to an area (not a project) is also warned, since Things ignores `heading` for area targets. Correctly handles re-filing a to-do that is already under a *different* heading: `things.py` reports `project: None` for a to-do whose parent is a heading (the project only appears on the heading record), so the current-project resolution falls back to the to-do's existing heading record instead of wrongly warning that the to-do has no project.

### Fixed
- **Read tools' structured errors now share one canonical shape, built by a single implementation** (hq-f0w.19, found by the hq-f0w.6 reviewer) - read tools previously used three different structured-error conventions: `get_todos`/`get_projects`/`get_areas`/`search_todos`/`search_advanced` put a human sentence directly in `error` (e.g. `"Invalid mode"`, `"Invalid status"`, `"Invalid query"`); `get_tagged_items`/`search_advanced`'s unknown-tag path already used a code (`{"success": false, "error": "unknown_tag", ...}`) but carried no `message`; `get_project_headings` used a distinct shape entirely (`{"error": true, "error_type": "not_found"|"invalid_type"|"internal_error", "message": ...}`), as did `get_tag_usage`'s internal-exception fallback (`{"error": str(e), "tags": []}`) and `get_due_in_days`/`get_activating_in_days`'s (`{"error": str(e), ...}`). Every read-tool structured error - at both the MCP tool boundary (`server.py`) and the tools layer (`tools_helpers/read_operations.py`) - now goes through one function, `read_operations.read_error(code, message, **extra)`, and returns `{"success": false, "error": "<snake_case_code>", "message": "<human text>", ...}`; `ThingsMCPServer._read_error` delegates to it rather than re-implementing the dict literal, so the two layers cannot drift apart. `error` codes: `invalid_mode`, `invalid_status`, `invalid_query`, `invalid_limit`, `invalid_start_date_format`, `invalid_deadline_format`, `not_found`, `invalid_type`, `invalid_parameter`, `internal_error`, `unknown_tag` (now with a `message`, e.g. `"Unknown tag 'LLM-WIKI'. Did you mean: llm-wiki?"`). Also fixed in passing: `search_advanced`'s internal invalid-`type`-filter error (`ReadOperations.search_advanced`) previously used the divergent `{"error": true, "error_type": "invalid_parameter", ...}` shape, which the server-level `search_advanced` MCP tool's `raw_data[0].get('success') is False` short-circuit did not recognize, so an invalid `type` from a direct `ThingsTools` caller would have been fed into response-mode optimization as if it were a todo list instead of surfacing as an error (unreachable from the MCP tool itself, since `type` is schema-validated by FastMCP before reaching `ReadOperations`). `get_todo_by_id` is unchanged - it still raises (surfaced as a FastMCP `ToolError`) rather than returning a structured error, since it has no natural envelope shape to fall back to. See `docs/UPGRADING.md` for the full before/after and `error`-code list.
- **Removed dead `ResponseOptimizer`/`response_optimizer.py`, and fixed the stale field-set list `get_optimization_capabilities()` advertised** (read sweep C12/C13) - `response_optimizer.py`'s `ResponseOptimizer.optimize_todo`/`optimize_project`/`optimize_area`/`optimize_tag` had zero callers anywhere in `src/` or tests (only instantiated and stored on `ThingsTools`/`ReadOperations`, never invoked); their field references (`id`, `name`, `when`, `tag_names`, `has_reminder`, ...) were also a snake_case schema left over from before `convert_todo`/`convert_project` were rewritten to the real things.py key set (hq-f0w.4) and no longer match the camelCase output those converters actually emit. The module, its import/instantiation in `tools.py` and `tools_helpers/read_operations.py`, and `FieldStandardizer` (which mapped the same stale snake_case keys) are removed. Separately, `context_manager.py`'s `get_optimization_capabilities()` advertised a hand-maintained, stale `field_sets` sample (`["id", "name", "status"]`, ...) that had drifted from the real per-mode field sets used for actual filtering; those sets are now a single class attribute (`TODO_FIELD_SETS`) that both `_apply_field_filtering` and `get_optimization_capabilities()` read from, so the two can no longer diverge.
- **`add_todo` via the Things URL scheme no longer risks returning the wrong id (or a false success) when two to-dos share a title** (hq-nxu.12) - `_add_todo_via_url_scheme` (used for checklist and heading creates, since Things' AppleScript dictionary supports neither) previously found the new to-do by searching for `to dos whose name is <title>` after a fixed 0.5s sleep and taking the one with the latest AppleScript `creation date`, which only has 1-second granularity - two to-dos created with the same title within that window were indistinguishable, so the wrong id (or either id, nondeterministically) could be returned. It also reported `success: true` with a `"Todo ID not available"` warning on any lookup miss, hiding a real failure behind a success response. It now snapshots the set of existing to-do ids with that exact title *before* issuing the `things:///add` call, then polls (up to 3s, every 250ms) for new ids (`after - before`) instead of sleeping a fixed amount: exactly one new id returns cleanly; several new ids (e.g. a concurrent same-title create) returns the most recently created one with a `warnings` entry noting the ambiguity; no new id within the deadline now returns `success: false` with an error explaining the to-do may still have been created in Things and to check manually before retrying.

- **`validate_tag_list` now rejects a comma inside an individual tag name (list-input API callers only), and `remove_tags` no longer over-reports or applies tag-creation policy** (write sweep C8/C9) - all tag write sites join a todo's tags with `', '.join(tags)` for Things' AppleScript tag API, but `ParameterValidator.validate_tag_list` passed a tag name containing a literal comma straight through when given as a list element (e.g. `['home, office']`), so Things received `'home, office, urgent'` and created three tags instead of two. `validate_tag_list` now rejects any tag name containing a comma with a structured `ValidationError` naming the offending tag. Note this only protects direct Python/API callers that pass a list: every MCP tool that accepts `tags` (`add_tags`, `remove_tags`, `add_todo`, `update_todo`, `update_project`, `update_area`, `bulk_update_todos`) takes it as a comma-separated **string**, which is always split on `,` into individual tags before validation runs - the comma is unconditionally the tag separator for those tools, `tags="a,b"` is always two tags, and no error is ever raised for a comma in that string. Separately, `remove_tags` reported `len(tags requested)` as the removed count regardless of how many were actually present - `remove_tags(todo_id, tags=['a', 'b'])` on a todo with only `'a'` reported "Removed 2 tags successfully". It now reports `removed_count = len(current tags) - len(remaining tags)` (an actual set difference) and adds a `not_present` field listing requested tags that weren't on the todo. `remove_tags` intentionally does **not** apply `tag_creation_policy` - removing a tag the todo lacks (or that doesn't exist at all) is a no-op, not a creation or filtering decision. `add_tags`'s message had the same over-reporting bug (counting tags requested-and-policy-valid rather than tags newly attached, e.g. re-adding an already-present tag reported "Added 1 tags" though nothing changed) and is fixed the same way. Before: `remove_tags(todo_id, tags='urgent,nonexistent')` on a todo with only `urgent` → `{"success": true, "message": "Removed 2 tags successfully"}`. After: `{"success": true, "message": "Removed 1 tags successfully", "removed_count": 1, "not_present": ["nonexistent"]}`.
- **`when='evening'` (and alias `'tonight'`) is now accepted and correctly schedules to-dos for "This Evening"; `deadline` relative-keyword rejection is now consistent between create and update** (write sweep C6/C7) - Things 3's AppleScript `schedule` command has no way to set the "This Evening" flag (verified against the AppleScript dictionary - `schedule ... for <date>` only accepts a date object, and confirmed against a live Things 3 install: a to-do created via the URL scheme's `when=evening` has a different internal `startBucket` than one scheduled for plain "Today" via AppleScript, even though both report the same start date). `ParameterValidator.validate_date_format` previously only allowed `today`/`tomorrow`/`yesterday`/`someday`/`anytime`, so `update_todo(when='evening')` failed validation before ever reaching Things. `when='evening'`/`'tonight'` (normalized to `'evening'`) is now accepted everywhere `when` is validated (`add_todo`, `update_todo`, `bulk_update_todos`) and routed through the Things URL scheme instead of AppleScript: `add_todo` uses `things:///add` (no auth token required); `update_todo` and `bulk_update_todos` use `things:///update`, which requires the Things auth token - checked *before* any AppleScript write, so a missing token returns a structured error/hint instead of partially applying other fields (same pattern as the existing `heading=...` URL-scheme gate). `add_project`/`update_project` explicitly reject `when='evening'` with a structured error instead of silently falling back to a plain "Today" schedule, since Things has no "This Evening" concept for projects. Separately, `deadline` validation was inconsistent: `server.py`'s pre-validation for `add_todo`/`update_todo`/`bulk_update_todos` already rejected relative keywords for `deadline` (`allow_relative=False`), but the downstream `ParameterValidator.validate_update_params` (used by `update_todo`/`update_project`/`bulk_update_todos`) still allowed them (`allow_relative=True`), a latent inconsistency between the two validation layers. `deadline` now rejects relative keywords like `'today'` identically at both layers everywhere - deadlines must be `YYYY-MM-DD`.
- **`total` in structured output is now the pre-limit count on every list tool, and `search_todos`/`search_advanced`/`get_logbook` gain `offset` for pagination** (read sweep C14) - CLAUDE.md documents `total` as "items available before any limit was applied", but `get_inbox`/`get_today`/`get_upcoming`/`get_anytime`/`get_someday` computed it from the already-limited result (`total=len(raw_data)` after the underlying `things.py` call had already truncated to `limit`), so `total` always equaled `count` and callers had no way to tell if more items existed. Only `get_trash` counted before slicing. These five tools now fetch the full unbounded set, compute `total` from it, then slice to `limit` themselves (the same pattern `get_upcoming(days=...)` already used). `search_todos`, `search_advanced`, and `get_logbook` had the same bug and additionally had no `offset` parameter at all, making results past `limit` permanently unreachable; they now compute the full pre-limit/offset match count and accept `offset: int = 0` (same semantics as `get_trash`) so callers can page through with `offset += limit`. Before: `get_anytime(limit=5)` → `{"total": 5, "count": 5, ...}` on a database with 613 anytime items. After: `{"total": 613, "count": 5, ...}`. Existing callers of the underlying `ThingsTools`/`ReadOperations` methods are unaffected - they still return a plain list-like object (`isinstance(result, list)` holds); the true pre-limit total is additionally available via `.total_count` for internal callers.
- **`get_todo_by_id` now resolves projects, headings, and trashed items, not just to-dos** (read sweep C10) - it previously unioned `things.todos(status=...)` (to-do only, excludes trashed) and linear-searched the result for a matching uuid, so a valid project/heading/trashed uuid raised `ValueError: Todo not found` even though the item exists. It now uses `things.get(uuid)`, a direct-by-id lookup across all item types, and dispatches conversion by the returned item's `type` (`to-do`/`heading` → `convert_todo`, `project` → `convert_project`). Checklist items are still fetched and merged in only for `to-do` rows (headings/projects have no checklist). Trashed items now resolve instead of raising, with a new `trashed: true` field included in the result when the item is in the trash. Unknown ids still raise `ValueError: Todo not found: <id>`.
- **`search_todos`/`search_advanced`/`get_recent` undisclosed incomplete-only defaults fixed, and empty search queries are now rejected** (read sweep C4/C5/C16) - `search_todos` and `search_advanced` (when no `status` filter was given) called `things.todos()`, whose own default is `status='incomplete'`, so a completed or canceled todo could never match a search regardless of query text; `get_recent` likewise missed completed/canceled todos and all projects in its "recently created items" window (a live 7-day check missed 3 completed todos and 5 projects). Also, `search_todos('')` matched arbitrary items because `''.lower() in title` is always `True`. Fixes: `search_todos` gains a `status` param (`'incomplete'` (default, unchanged for backward compatibility) / `'completed'` / `'canceled'` / `None` for all); `search_advanced` with no `status` filter now explicitly searches **all** statuses instead of silently defaulting to incomplete-only (pass `status='incomplete'` to restrict, as before); `get_recent` now defaults to `status=None, type=None` (all statuses, to-dos + projects) - headings are NEVER included by default, matching the epic-wide ruling that list tools never return headings unless explicitly requested (pass `type='heading'` to fetch them) - with new optional `status`/`type` params to narrow results. `search_todos` now rejects an empty or whitespace-only `query` with a structured `{"success": false, ...}` error instead of matching everything. `filter_someday_project_tasks` is documented as NOT applied to `search_todos`/`search_advanced`/`get_recent`/`get_inbox` (sweep S2). See `docs/UPGRADING.md` for the full behavioral before/after.
- **`get_activating_in_days` no longer returns already-active todos, and `get_due_in_days` no longer silently includes overdue todos by default** (read sweep C8/C9) - `get_activating_in_days` queried `start_date <= target date` with no lower bound, so `get_activating_in_days(days=1)` on a real database returned 113 items, nearly all already active (`start_date` in the past), contradicting the tool's docstring ("todos activating within specified days"). It now restricts results to `today <= start_date <= target date`. `get_due_in_days` queried `deadline <= target date` the same way, so `get_due_in_days(days=1)` returned 17 items, 15 of which were already overdue. It gains a new `include_overdue: bool = True` parameter (default preserves the historical due-plus-overdue behavior); pass `include_overdue=false` to restrict to `today <= deadline <= target date`. Both boundaries are inclusive (a deadline/start_date of exactly today or exactly the target date is included), and both tools continue to filter out tasks belonging to Someday projects.
- **`get_tagged_items` and `search_advanced` no longer silently return an empty list for an unknown or wrong-case tag** (sweep C11) - Things 3 tag matching is exact-case (e.g. `'llm-wiki'` and `'LLM-WIKI'` are different tags), and `things.py` raises `ValueError('Unrecognized tag type')` when asked for a tag it doesn't recognize; both tools caught that alongside every other error and returned `[]`, indistinguishable from a genuinely empty tag. Before: `get_tagged_items(tag='LLM-WIKI')` on a database with 86 `llm-wiki` items → `{"items": [], "count": 0, ...}`. After: `{"success": false, "error": "unknown_tag", "tag": "LLM-WIKI", "suggestions": ["llm-wiki"]}`, with `suggestions` populated from case-insensitive title matches against `things.tags()`. `search_advanced` reports the same shape (unwrapped from its internal single-element list convention) when its `tag` filter is unknown. Docstrings for both tools now note that tag matching is case-sensitive.
- **`get_today`, `get_upcoming`, `get_anytime`, `get_someday`, and `get_trash` no longer leak projects and headings into to-do lists** (GH#9 items 1-2 + sweep C6) - these list tools called their underlying `things.py` list functions with no `type=` filter, so e.g. `get_anytime()` on a real database returned 1175 items (1106 to-dos + 39 projects + 30 headings) instead of the 1106 to-dos a caller would expect, and `get_trash()` similarly mixed in projects despite its docstring saying "Get trashed todos". Headings are now never returned by these five tools plus `get_inbox`. Before: `get_anytime()` → 1175 mixed items. After: `get_anytime()` → 1106 to-dos only; pass the new `include_projects=true` parameter on `get_today`/`get_upcoming`/`get_anytime`/`get_someday`/`get_trash` to opt back into projects (headings remain excluded even then). `get_inbox` has no such flag since the Inbox can never contain projects.
- **URL-scheme update tools now fail fast when the Things auth token is missing** - `add_checklist_items`, `prepend_checklist_items`, and `replace_checklist_items` go through `things:///update`, which Things 3 silently rejects without a configured auth token; `open -g` still exits 0 in that case, so before this fix these tools returned `success: true` while nothing actually happened. `AppleScriptManager.execute_url_scheme` now checks a new `AUTH_REQUIRING_ACTIONS` set (`update`, `update-project`) before invoking `open`, returning `{"success": false, "error": "Things URL-scheme auth token not configured", "hint": ...}` without ever shelling out when the token is missing or empty/whitespace-only. `things:///add`-based tools (`add_todo`, `add_project`, including todo creation with a checklist) are unaffected since they never required a token. `mcp-server-things doctor`'s "Auth token file" check now WARNs (was INFO) when no token is configured, naming the three affected tools in its hint. README (Configuration and Troubleshooting) and CLAUDE.md document the token requirement and setup; the three checklist tool docstrings do too.
- **`convert_todo`/`convert_project` rewritten against the real things.py key set - completed/canceled todos and projects now correctly report `completionDate`/`cancellationDate`** (GH#9 item 3a + sweep C1-C3) - things.py never emits `completion_date`/`cancellation_date`/`area` keys on to-do rows (0/3699 rows, live-verified); the real key is `stop_date`, disambiguated by `status`. Every completed/canceled todo previously came back with no completion/cancellation date at all. Also fixed: `checklist` was read as if it were a list of items, but things.py emits it as a plain bool "has a checklist" flag - the default `get_todos` path was therefore returning `"checklist": true` where callers expecting a list would misread it; it's now exposed as `hasChecklist` (bool), and `checklist` only appears as a real item list when `include_items=true` (or `get_todo_by_id`) fetched it. Also newly exposed: `type`, `start` (Inbox/Anytime/Someday - the only way to tell where a todo lives, distinct from `startDate`), `projectTitle`, `heading`/`headingTitle` (present on todos under a project heading), `index`, `today_index` → `todayIndex`; projects gained `areaTitle`; the phantom `area`-on-todo and `tags`-on-area lookups (permanently empty/absent in practice) were removed/documented. `context_manager.py`'s `minimal`/`standard` response-mode field sets were updated to include the new fields (and drop `area`, which to-do rows never actually carry). See `docs/UPGRADING.md` for the full before/after field list.
- **`add_todo(heading=...)` is now honoured on every path, `list_title` now works without a checklist, and `list_id` is escaped** - previously `heading` and `list_title` were only forwarded when `checklist_items` was also supplied (they were silently dropped otherwise, e.g. a todo created with `list_title` alone landed in the Inbox with `success: true`), and the AppleScript path interpolated `list_id` into the script unescaped. `add_todo` now takes the URL-scheme path whenever `heading` is set (with or without a checklist) - required since Things 3's AppleScript dictionary has no heading class - and returns a structured error (`"heading requires a target project (list_id or list_title)"`) if `heading` is given without a target; if the named heading doesn't exist in the target project, a `warnings` entry is added since Things silently ignores an unknown heading rather than erroring. `list_title` is now resolved to a project or area via an exact-title match on *every* path (AppleScript and URL-scheme), including when `heading` or `checklist_items` alone triggers the URL-scheme branch - previously the URL-scheme path passed an unresolved `list_title` straight through as the raw `list=` param, so an unknown or ambiguous title silently succeeded with the to-do landing in the Inbox; both paths now return the same structured error on no match or ambiguous matches instead. `list_id` is resolved to project-vs-area via a `things.get()` lookup and escaped through the shared AppleScript string escaper instead of being interpolated raw; if that lookup itself raises (e.g. the Things database is unreadable or Full Disk Access is missing), `add_todo` falls back to treating `list_id` as a project id and proceeds via AppleScript rather than refusing the write, preserving pre-1.7.0 behavior for that failure mode. Also fixed the URL-scheme builder using `list=<uuid>` (name-targeting param) instead of `list-id=<uuid>` (id-targeting param) for `list_id`, which silently failed to resolve and left the to-do in the Inbox. `scheduling/todo_operations.py`'s `things` import is now routed through the existing lazy, timeout-bounded proxy (`things_import.LazyThingsProxy`) rather than a module-level `import things`, preserving the v1.5.0 boot diagnostics (bounded import off the synchronous server-boot path).
- **`update_todo`/`update_project`/`update_area`/`bulk_update_todos` can now clear `notes`, `deadline`, and `tags`** (sweep C5) - these tools treated an empty string the same as "not provided" for every field (`sanitize_string('') -> None`), so `update_todo(id, notes='')` silently no-opped instead of clearing notes, and there was no way to clear a deadline or remove all tags through any tool. `notes=''`/`deadline=''` now clear those fields on todos and projects (`delete due date of X` - Things 3's AppleScript dictionary rejects `set due date of X to missing value` with "Can't make missing value into type date"); `tags=''` now clears all tags on todos, projects, and areas. `title=''` (or whitespace-only) is now rejected with a structured `VALIDATION_ERROR` ("title cannot be empty") instead of being silently ignored - titles cannot be cleared. `when=''` is likewise rejected, pointing callers at `when='anytime'`/`when='someday'` to unschedule instead. Before: `update_todo(id, notes='')` → `success: true`, notes unchanged. After: `update_todo(id, notes='')` → notes cleared. Tag-policy interaction is unchanged: if every requested tag is filtered out by `tag_creation_policy` (a non-empty `tags=` request, not an explicit clear), existing tags are left unchanged, not cleared.
- **`convert_todo`/`convert_project` now emit `reminderTime`; `convert_project` also gains `start`/`startDate`/`index`/`todayIndex`** (found by hq-f0w.10 reviewer) - things.py emits `reminder_time` (e.g. `'09:00'`) on the small subset of to-do and project rows that actually have a reminder (live: 8/1699 todos, 8/67 projects), but `convert_todo`/`convert_project` dropped it entirely; `convert_project` additionally dropped `start`/`start_date`/`index`/`today_index`, fields `convert_todo` already emitted for to-dos. Both converters now emit `reminderTime` the same way, and `convert_project` now emits `start`/`startDate`/`index`/`todayIndex` the same way `convert_todo` does (`start` is always present, `None` when absent). `reminderTime` is now included in the `standard` and `detailed` response modes (see CLAUDE.md's "Todo field lists per mode").
- **`get_todos(project_uuid=...)` now reads via things.py instead of AppleScript, fixing a silently incomplete-only `status` filter, and the dead AppleScript read path was removed** (hq-nxu.8) - the project-scoped branch used AppleScript to work around a suspected database-sync-timing issue (things.py reading a stale snapshot right after an AppleScript-driven write), but measured directly (create a to-do via AppleScript, immediately poll `things.todos(project=...)`) showed no meaningful lag: 5 initial trials at ~6ms and 2 independent re-measurement trials at ~7.7-8.1ms, all visible on the first poll. The AppleScript branch, its best-effort heading/start enrichment shim, and the now-dead `AppleScriptManager.get_todos`/`get_projects`/`get_areas`/`get_todos_due_in_days`/`get_todos_activating_in_days`/`get_todos_upcoming_in_days` methods (zero remaining callers) plus their query builders in `services/applescript/queries.py` were removed. Also fixed as a result: `get_todos(project_uuid=..., status=...)` previously ignored `status` entirely when `project_uuid` was given (always returned all statuses); it now honours `status` (`'incomplete'`/`'completed'`/`'canceled'`/`None`) the same way the unscoped call does, via `things.todos(project=..., status=...)`.

- **`get_logbook`/`get_recent` no longer silently drop rows with a timezone-aware completion/creation date, and `get_todos`'s sync helper now rejects an unrecognized `status` instead of silently returning unfiltered results** (read sweep C17/S3/S1) - `_get_logbook_sync`/`_get_recent_sync` parsed `stop_date`/`created` with `datetime.fromisoformat(x.replace('Z', '+00:00'))` and compared the result directly against a naive `datetime.now()`-based cutoff; this only worked because things.py happens to emit local-naive strings today, but any timezone-aware value (e.g. an explicit UTC or offset string) raised `TypeError` on the naive/aware comparison, which was caught as "invalid date" and the row was silently dropped from the response. Both now route through a new shared `ToolsHelpers.parse_things_datetime()` helper that normalizes any input (naive-local string, aware string with `Z`/offset, or an already-parsed `datetime`) to a consistent naive-local `datetime`, so aware and naive inputs compare like-with-like against the cutoff. Separately, `ReadOperations._get_todos_sync` fell through an `if/elif` chain to `things.todos(**extra_kwargs)` (no `status=` at all, i.e. unfiltered) for any status string it didn't recognize (e.g. `status='done'`), even though `server.py`'s `get_todos` MCP tool already validates `status` up front - a direct/non-MCP caller of the tools layer could still get silently wrong (unfiltered) results. `_get_todos_sync` now validates `status` against `{'incomplete', 'completed', 'canceled', None}` itself and returns a structured `{"success": False, "error": "invalid_status", "message": ...}` dict (not a list) for anything else; `server.py`'s `get_todos` tool checks for this dict and returns it as-is, the same pattern `search_todos` already uses for its own "Invalid status" short-circuit. Also verified (read-only, against both the things.py schema and a live Things 3 database) that `get_tag_usage`'s per-tag counting deliberately excludes headings: `things.tasks(type='heading')` rows never carry a `'tags'` key at all - headings cannot have tags assigned in Things 3 (only to-dos and projects can) - so there was nothing for the existing todos/projects/areas-only scan to undercount; this is now documented explicitly in `get_tag_usage`'s docstring rather than left implicit.
- **Todos parented under a heading now report `project`/`projectTitle` (were always `None`)** (hq-f0w.24, from hq-f0w.4 review) - things.py to-do rows carry `heading`/`heading_title` when a to-do is filed under a heading, but leave `project`/`project_title` unset on the to-do row itself (only the heading's own row carries them; live-confirmed: 0/40 heading-children have a populated `project` field) - even project-scoped queries (`things.todos(project=...)`) don't backfill it. Every read tool that goes through `convert_todo` (`get_todos`, `get_today`, `get_upcoming`, `get_anytime`, `get_someday`, `get_inbox`, `get_logbook`, `get_trash`, `search_todos`, `search_advanced`, `get_recent`, `get_tagged_items`, `get_todo_by_id`, `get_due_in_days`, `get_activating_in_days`, and the `include_items` project/area/tag todo lists) now backfills `project`/`projectTitle` for heading-children via a new post-conversion pass in `read_operations.py` (`_fill_project_from_heading`), resolving the heading's parent project from a single batched `things.tasks(type='heading', status=None)` call per request (only made when at least one item actually needs it) or, for `get_todo_by_id`'s single-item lookup, a direct `things.get()` call on the heading. `status=None` is required: `things.tasks()`'s own default status filter is `'incomplete'`, which only covers headings belonging to open projects (live: 30/674 headings) - an earlier version of this fix used the default filter and left every to-do under a completed/canceled-project heading (completed projects, finished repeating-project instances) unresolved (live-confirmed regression: `get_todos(status='completed')` had 912 heading-children, 0 resolved; `get_logbook(period='365d')` had 18 heading-children, 0 resolved); with `status=None` all 674 headings are fetched regardless of status. Before: `get_todo_by_id('WMVVPmqvWnmbMXsZ8GPdER')` (a to-do under the 'Review Calendar' heading) → `{"project": null, "projectTitle": null, "heading": "6PsfVfwwHh8vD3jNXcwgsJ", "headingTitle": "Review Calendar", ...}`. After: `{"project": "9r4F1446LXfRcj6a9fmpRD", "projectTitle": "Complete Weekly Review", ...}`.

### Docs
- **README "Why this server?" section and `docs/COMPARISON.md`** - a new README section right after the opening description answers "why this instead of hald/things-mcp?" (AppleScript-enabled delete/move/remove-tags vs URL-scheme trade-offs, `doctor`/`config`/response-mode tooling), pointing to a new `docs/COMPARISON.md` with a detailed, dated feature matrix and a "which should you pick?" recommendation.

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
