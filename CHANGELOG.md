# Changelog

All notable changes to the Things 3 MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`get_todo_by_id` now reports `evening: true` for a to-do scheduled for This Evening, instead of silently dropping that state** (bead hq-wsa.9). `when='evening'` was previously invisible in every read tool's output - things.py's own SELECT never exposes `TMTask.startBucket`, so an Evening-scheduled to-do was indistinguishable from a plain `when='today'` to-do (both report only `start='Anytime'`/`startDate=<today>`). `get_todo_by_id` now reads `startBucket` for the single resolved to-do via a narrow, read-only (`mode=ro` URI) raw-SQL side channel (`_read_start_bucket`), gated by a cheap pre-filter (only queried when the item is a to-do with its own `start_date` set - never for projects/areas/headings, and never for a to-do with no start date at all) - `startBucket == 1` adds `evening: true` to the result; any other value, or any error reading it (missing/locked database, schema change, etc.), silently omits the key rather than failing the lookup. Deliberately scoped to `get_todo_by_id` only - no list tool (`get_today`, `get_todos`, etc.) gained this field, to avoid multiplying this raw SQL connection per row. See CLAUDE.md's date-formats bullet 5 and "Todo field lists per mode" section for the updated contract.
- **`get_todo_by_id` now resolves trashed state transitively through a to-do's/heading's containing project, instead of reporting a live-looking item that is actually unreachable** (bead hq-wsa.7). Things marks only the trashed *container* (e.g. a project moved to Trash), not each descendant - a to-do or heading filed under a trashed project carried no `trashed` key of its own in things.py, so `get_todo_by_id` previously reported it as a normal, live item. `_get_todo_by_id_sync` now resolves the container chain with at most two `things.get()` calls (item's own `project`, or - for a to-do under a heading with no `project` of its own - the heading's `project`) whenever the item itself is not directly trashed; if that container is trashed, the result now carries both `trashed: true` and a new `trashedViaParent: true` key, distinguishing "unreachable via a trashed ancestor" from direct trash (which keeps the existing `trashed: true`-only shape). Areas cannot be trashed, so there is no area hop; a failed container lookup (e.g. unreadable database) omits both keys rather than failing the lookup. Single-item lookup only - list tools already exclude trashed items via things.py's own filtering and are unaffected. See CLAUDE.md's `get_todo_by_id` section for the updated contract.
- **Things URL-scheme auth token no longer requires a server restart to pick up a newly-added or fixed token file, and its failure/status is now diagnosable** (bead hq-wsa.4). `AppleScriptManager` previously loaded the auth token exactly once, in `__init__`; a `.things-auth`/`things-auth.txt`/`~/.things-auth` file created (or an empty one fixed) after the server started had no effect until the process was restarted, and neither `health_check` nor `get_server_capabilities` exposed whether a token was actually loaded, so the only way to tell was to trigger an auth-gated write and read its error. Three changes: (1) **reload-on-miss** - every auth gate (the shared `AppleScriptManager.execute_url_scheme` gate, plus the four call sites in `scheduling/todo_operations.py`/`tools_helpers/bulk_operations.py` that check the token ahead of a URL-scheme call for `heading`/`when='evening'`/`when` with a `@HH:MM` time component) now calls a new `AppleScriptManager.reload_auth_token_if_missing()` immediately before failing, which re-reads the candidate paths only when no token is currently loaded (a token, once loaded, is never unloaded or re-read) - a token file added or fixed after startup now works on the very next auth-gated call, no restart needed. (2) **runtime visibility** - `health_check` and `get_server_capabilities` (`current_status`) now report `auth_token_configured: <bool>`, the live runtime state, alongside the existing static `url_scheme_support: true` build-capability flag on `get_server_capabilities` (unchanged). (3) **resolution trace** - `_load_auth_token` now also returns a `checked_paths` trace (`[{"path": ..., "status": "matched"|"empty"|"missing"|"unreadable"}, ...]`, one entry per candidate path in search order, path only - never the token value) which is included as a `checked_paths` field on every `AUTH_TOKEN_NOT_CONFIGURED` error, forwarded verbatim through `_propagate_url_scheme_error` (the checklist tools' and `update_todo`'s heading-move forwarding path) alongside the existing `hint`. See CLAUDE.md/README's "Things URL-scheme auth token" sections for the updated (no-restart) semantics.
- **`AppleScriptExecutor`'s serialization lock is now per-event-loop, fixing a latent cross-loop poisoning hazard** (bead hq-yxu). `AppleScriptExecutor._applescript_lock` was a single class-level `asyncio.Lock()` created at import time. CPython's `asyncio.Lock` only binds its internal loop reference on a CONTENDED acquire (a second waiter queueing while the lock is already held) - an uncontended acquire never binds. Once a contended acquire happened on one event loop, the lock became permanently bound to that loop; a later contended acquire from a *different* loop (e.g. a fresh `asyncio.run()` per call, as the regression test harness does) then raised `RuntimeError: ... is bound to a different event loop` instead of serializing - a `bulk_move_records` call with `max_concurrent > 1` reliably creates that intra-loop contention. The lock is now keyed by the currently running event loop in a `weakref.WeakKeyDictionary`, mirroring hq-5xa's `operation_queue` fix exactly: each loop lazily gets its own `Lock` instance via a new `AppleScriptExecutor._get_lock()` classmethod, so within-loop serialization is preserved while cross-loop calls never touch a foreign-bound lock. This unblocks hq-wsa.6 (whose `move_operations.py` change deterministically triggers the poisoning without this fix).
- **`move_record`/`bulk_move_records` now report the true pre-move `original_location` and a clean, unlabeled title in the success message** (bead hq-wsa.6). `MoveOperationsTools._get_todo_info` previously round-tripped through AppleScript via a `getCurrentLocation` helper that was a stub always returning the literal string `"inbox"`, and parsed the script's positional `"id, name, notes, status, current_list"` output with a fragile `output.split(", ")` - so `original_location` always reported `'current_list:inbox'` regardless of the to-do's true origin, and the success message's title carried a stray `'name:'` label (e.g. `"Todo 'name:My Task' moved to ..."`). `_get_todo_info` now reads the to-do via `things.get(todo_id)` instead: `title`/`notes`/`status` come straight from the clean field, and a new `_derive_original_location` helper reports the real prior location - `'project:<id>'` for a to-do filed directly in a project or under a heading (resolved via the heading's own record, mirroring `read_operations._fill_project_from_heading`), `'inbox'`/`'someday'`/`'anytime'` for the corresponding Inbox/Someday/Anytime start states, `'today'` for an Anytime to-do whose start date is today or earlier (matching Things' own Today-list membership rule), and the literal ISO date string (e.g. `'2026-09-01'`) for an Anytime to-do with a future start date (chosen over inventing an `'upcoming'`-style token, since that isn't a valid `move_record` destination itself). If the `things.get()` lookup itself raises (DB unreadable / Full Disk Access missing), the move now proceeds anyway with `original_location` omitted entirely from the response (not present as `null`) and the raw id used in the message, matching the existing DB-unreadable fallback convention used by `add_todo`'s `list_id` resolution. The pre-move existence check retains a short bounded retry (two 250ms re-checks) before reporting `TODO_NOT_FOUND`, so the existing hq-c7a concurrency-race tolerance for a just-created todo isn't worsened by this AppleScript-to-things.py switch. `bulk_move_records` shares this same code path (each id delegates to `move_record` under the hood) and is fixed identically with no field-shape change. One additional safety guard rides along: an id that resolves to something other than a to-do (e.g. a project uuid, which AppleScript's `to do id` lookup would previously have resolved and moved) now returns `TODO_NOT_FOUND` instead of moving the wrong item, mirroring hq-wbm's update_todo pre-check.
- **BREAKING (minor): search summary envelopes no longer carry a misleading `total_matches` key** (bead hq-wsa.5). `ProgressiveDisclosureEngine._summarize_search_results` (`context_manager.py`) emitted `total_matches: len(results)`, but the data it receives is already limit/offset-truncated by the time it gets there (`server.py` passes the final window down) - so e.g. `limit=1` yielded `total_matches: 1` even though the true, pre-limit match count (correctly reported by the envelope's separately-injected `total`) was much larger. `total_matches` is now dropped entirely rather than threaded through as a correct value; `total` was already correct in every mode and is the sole source of truth for the pre-limit match count. `search_results_breakdown` (a per-status breakdown of the returned window) is unaffected - it's explicitly window-scoped, not total-sounding. Callers reading `total_matches` off a `search_todos`/`search_advanced` `mode='summary'` response must switch to `total`.
- **`get_projects(mode='summary')` no longer always reports `active: 0`** (bead hq-wsa.1). `ProgressiveDisclosureEngine._summarize_projects` (`context_manager.py`) counted `p.get('status') == 'open'` for the `active` count, but `things.py`/`convert_project` emit `status == 'incomplete'` for open projects, never the literal string `'open'` - on a live database this meant `active` was always `0` regardless of how many open projects existed. `_summarize_projects` now builds a dynamic `status_breakdown` from the rows' actual status values (same pattern already used by `_summarize_todos`) and derives `active = status_breakdown.get('incomplete', 0)`, `completed = status_breakdown.get('completed', 0)`, and a new `canceled = status_breakdown.get('canceled', 0)` field. The summary envelope's key set grows from `{active, completed, recent_projects}` to `{active, completed, canceled, status_breakdown, recent_projects}` - existing `active`/`completed`/`recent_projects` keys are unchanged in shape, `canceled` and `status_breakdown` are additive.
- **BREAKING (minor): structured envelopes no longer double-serialize the item payload under a second, legacy key** (bead hq-wsa.2). `ThingsMCPServer._read_result`'s dict branch extracted `items` from whichever source key was present (`data` from `optimize_response`, or a summary-preview key: `recent_preview`/`recent_projects`/`result_preview`, or `get_tag_usage`'s `tags` rows list) but then kept that source key in the returned envelope via `dict(response)` while also `setdefault`-ing the same list object under `items` - every optimized read carried the identical item list twice (byte-identical: `result['data'] is result['items']` was `True`). The source key is now popped once `items` has been populated from it, so `items` is the one canonical payload array; payload size on affected reads drops by roughly half. Clients that re-parsed the raw `data`/`recent_preview`/`recent_projects`/`result_preview`/`tags` keys directly (rather than the documented `items` contract) must switch to `items` - the documented contract itself is unchanged, and `count`/`total`/`mode`/`requested_mode`/`limit`/`offset`/`meta`/`truncated`/`truncation_hint` are untouched. `get_tags()` itself is unaffected (it's a bare-list response, routed through the list branch, not the dict branch this fix touches).

### Changed

- **`get_due_in_days`/`get_activating_in_days` now accept `mode`/`limit` and route through the same response-optimization pipeline as the other date-window list tools** (bead hq-wsa.3). Previously both tools passed their full, unfiltered `convert_todo` list straight to `ThingsMCPServer._read_result`'s list branch, bypassing `context_manager.optimize_response`/`_apply_field_filtering` entirely - notes and every other field shipped untrimmed regardless of size, the envelope always reported `mode: 'standard'` even though the rows were effectively DETAILED-shaped, and there was no way to cap a large overdue backlog. Both tools now accept `mode: Optional[str]` (`auto`/`summary`/`minimal`/`standard`/`detailed`/`raw`, validated via the shared `_validate_mode` helper) and `limit: Optional[int]` (1-500), fetch the full window first so `total` reflects the pre-limit count, slice to `limit` client-side, and route the result through `context_manager.optimize_response` exactly like `get_anytime`/`get_someday` (both added to `SmartDefaultManager.DEFAULT_MODES`/`DEFAULT_LIMITS` with `AUTO`/`40` respectively, matching `get_anytime`'s defaults). **Envelope contract change**: these two tools leave the "no mode parameter" group - `requested_mode` now echoes the caller's actual request (`None`/`'auto'`/a concrete mode) instead of always being `None`; `mode` continues to report the concrete resolved mode. `include_overdue`/`days` behavior is unchanged. See CLAUDE.md's "Due/activating date-window tools" section for the updated contract.

### Documentation

- **Documented that checklist-only edits do not bump a to-do's `modificationDate`** (bead hq-wsa.8). Verified live: `add_checklist_items`/`prepend_checklist_items`/`replace_checklist_items` are thin `things:///update` calls, but Things tracks a checklist item's own `userModificationDate` on `TMChecklistItem` independently of the parent `TMTask` row - three consecutive checklist writes left the parent to-do's `modificationDate` pinned, while a heading move (which rewrites the task row) advanced it as expected. This is upstream Things behavior, not a bug in this server. Added a warning to the `add_checklist_items`/`prepend_checklist_items`/`replace_checklist_items` docstrings and `add_todo`'s `checklist_items` parameter description, and a matching note in CLAUDE.md's "Managing Checklist Items" section: change-detection consumers polling `modificationDate` will not observe checklist-only edits - compare checklist content via `get_todo_by_id(include_items=true)` instead. `tests/live/test_smoke.py::test_checklist_tools_require_auth_token_or_roundtrip` now also asserts `modificationDate` is unchanged across a checklist write when a token is configured, so an unexpected upstream behavior change would be caught.
- **Documented the upstream Things completion-cascade asymmetry on `update_project`** (bead hq-wsa.7). `update_project(id=..., completed="true")` cascades completion to a project's child to-dos (matching the Things app), but `completed="false"` does not cascade a reopen back to those children - confirmed this repo's AppleScript write is a single `set status of targetProject ...` with no child-iteration logic, so the asymmetry is a Things/AppleScript behavior, not a bug here. Documented in CLAUDE.md's status-semantics truth-table section and in README's `update_project` tool entry.

## [1.8.0] - 2026-08-22

### Fixed

#### Scheduling (`when=`)
- **`when='today'` (and an explicit ISO date equal to today) now schedules into the Anytime list, not an "unconfirmed" Someday state, and is visible in `get_anytime`** (bead hq-x9z). `add_todo`, `update_todo`, `bulk_update_todos`, `add_project`, and `update_project` share the same AppleScript scheduler (`scheduling/strategies.py`'s `SchedulingStrategies`), which previously scheduled `when='today'` via `schedule theTodo for (current date)` - Things' own "schedule" AppleScript verb, confirmed live, always leaves the to-do in its unconfirmed/yellow-dot state (`things.get()` reports `start='Someday'`, `start_date=today`), which shows up in `things.today()`/`get_today` (whose own predicate explicitly includes that state) but not `things.anytime()`/`get_anytime` - unlike the Things URL-scheme `when='today'` path (checklist/heading/evening adds), Things' own "Today" UI button, or the equivalent `move_record(destination_list='today')`, all of which yield `start='Anytime'`. The scheduler now issues `move theTodo to list "Today"` instead of the `schedule` verb whenever the resolved date is today (confirmed live via `things.get()` reporting `start='Anytime'`, `start_date=today`, and membership in both `things.today()` and `things.anytime()`); `schedule` is unchanged for any other date (e.g. `'tomorrow'` or a future ISO date), where Things' own `start='Someday'` + future `start_date` representation is normal and expected (`things.upcoming()` explicitly keys off exactly that state).
- **`when='anytime'` now schedules into the Anytime list, not Someday** (bead hq-z5d). `add_todo`, `update_todo`, `bulk_update_todos`, `add_project`, and `update_project` all share the same AppleScript scheduling fallback (`scheduling/helpers.py`'s `determine_target_list`), which previously mapped the literal string `'anytime'` to the same `"Someday"` list-move target as `'someday'` - a to-do/project scheduled with `when='anytime'` ended up with `start='Someday'`, indistinguishable from a native `when='someday'` item. It now maps to `"Anytime"`, matching CLAUDE.md's documented behavior and Things' own Anytime list (`move theTodo to list "Anytime"`, confirmed live via `things.get()` reporting `start='Anytime'`, `start_date=None`).
- **`when='YYYY-MM-DD@HH:MM'` now actually sets a reminder** (bead hq-4gn). `add_todo`, `update_todo`, `bulk_update_todos`, `add_project`, and `update_project` all accepted this date+time form (`ParameterValidator.validate_date_format` allows the `@HH:MM` suffix), but the AppleScript scheduling path (`SchedulingStrategies.schedule_todo_reliable` -> `locale_aware_dates.normalize_date_input`) only ever extracted year/month/day, so the time component was silently dropped and no reminder was ever set. `when` values with a `@HH:MM` component are now routed through the Things URL scheme instead (which supports this form natively and sets `reminder_time`), the same way `when='evening'` already was: `add_todo` via `things:///add` (no auth token required); `update_todo`/`bulk_update_todos` via `things:///update` (requires the Things auth token, checked before any AppleScript write so a missing token never partially applies other fields in the same call). Unlike `evening`, this form IS supported for projects (live-verified against `things:///add-project`/`things:///update-project`, both of which set a project reminder natively) - `add_project`/`update_project` route it via `things:///update-project` (also auth-token-gated). Also fixes a related validation gap: `ParameterValidator.validate_date_format` previously accepted any `@H:MM`/`@HH:MM`-shaped string without validating the hour/minute ranges (e.g. `'2026-01-01@25:99'` passed validation) - it now rejects out-of-range times with `INVALID_WHEN`, the same as any other malformed `when`.

#### Move destinations
- **`move_record`/`bulk_move_records` now reject `destination_list='upcoming'` at validation instead of accepting it and later failing with `APPLESCRIPT_ERROR`** (bead hq-cag). Things has no direct "Upcoming" move target - an item is Upcoming by having a future start date, and Things' own AppleScript move verb rejects `move ... to list "upcoming"` with "Cannot move to-do". Rather than silently guessing an arbitrary future date, `'upcoming'` is no longer accepted as a destination: `move_record` returns `VALIDATION_ERROR` and `bulk_move_records` returns `INVALID_DESTINATION` (validated once up front, before any per-todo move is attempted, so nothing in the batch moves), both with a message pointing callers at `update_todo(id=..., when='<YYYY-MM-DD>')` (or `when='tomorrow'`) to schedule the to-do for a future date instead.
- **`move_record`/`bulk_move_records` now actually route `destination_list='logbook'`/`'trash'` instead of always returning `INVALID_DESTINATION`** (bead hq-edj). `MoveOperationsTools._validate_destination` already accepted `'logbook'` and `'trash'` in its `valid_lists`, but `_execute_move`'s destination-routing `if`/`elif` chain only recognized `['inbox', 'today', 'upcoming', 'anytime', 'someday']` as built-in list moves - `'logbook'` and `'trash'` fell through to the `else` branch and returned `INVALID_DESTINATION` even though validation had accepted them (both `move_record` and `bulk_move_records` share this code path, so both were affected). `'trash'` now uses the same `move theTodo to list "trash"` verb already used for the other built-in lists (live-verified). `'logbook'` has no direct move target in Things' AppleScript dictionary - the only documented way an item reaches the Logbook is completion - so it now issues `set status of theTodo to completed` (live-verified: reports `status='completed'` and membership in `things.logbook()`).

#### Structured envelope / response contract
- **BREAKING: `mode='summary'` preview rows (`recent_preview`/`recent_projects`/`result_preview`) now emit the documented SUMMARY field set instead of `{id, name}`** (bead hq-9tm). `get_todos`/`get_today`/`get_inbox`/`get_upcoming`/`get_anytime`/`get_someday`/`get_projects`/`search_todos`/`search_advanced` under `mode='summary'` build their preview items via `ProgressiveDisclosureEngine._summarize_todos`/`_summarize_projects`/`_summarize_search_results`, which previously hand-built each preview row as `{"id": <uuid>, "name": <title>[:50]}` - contradicting CLAUDE.md's "Todo field lists per mode" SUMMARY contract of `{uuid, title, status, tags, dueDate}` (and the parallel PROJECT_FIELD_SETS entry, which is identical). Preview rows now go through the same field-filtering convention as every other mode: each row is built from `TODO_FIELD_SETS[SUMMARY]`/`PROJECT_FIELD_SETS[SUMMARY]` (dispatched per-row by the item's own `type`, matching `_apply_field_filtering`'s existing per-row logic), so `{uuid, title, status, tags, dueDate}` are present when non-null on the source item and absent otherwise (fields are never invented) - `id`/`name` no longer appear at all. Any caller reading `id`/`name` off a summary-mode preview row must switch to `uuid`/`title`.
- **List tools no longer silently drop items via relevance-ranked pagination when the ~80KB response-size budget is exceeded** (bead hq-cal.2). `ContextAwareResponseManager.optimize_response` (`context_manager.py`) enforced the budget by re-ranking items with a relevance heuristic and returning only the top-scoring subset - this fired even when the caller passed no `limit`, and `total` still reported the full pre-truncation count, so a freshly created but low-relevance item (e.g. a new project on a large Anytime list) could be unreachable via that list tool even though it appeared to have been requested in full (list tools like `get_anytime`/`get_today`/`get_upcoming`/`get_someday` have no `offset`). `_handle_oversized_response` now keeps a deterministic **prefix of the list in its original order** (the order the tool produced it in, i.e. things.py order) instead of relevance re-ranking, and the structured envelope now carries an explicit `truncated: true` + `truncation_hint` (a short string explaining how to reach the rest, e.g. via a smaller mode/limit/more specific filter) whenever this budget truncation fires - both keys are absent (not `false`) when it doesn't, so untruncated envelopes remain byte-stable. This propagates through `ThingsMCPServer._read_result` to `structured_content` for every list tool that routes through `optimize_response` (`get_today`/`get_inbox`/`get_upcoming`/`get_anytime`/`get_someday`/`get_todos`/`get_projects`/etc.). See CLAUDE.md's Structured Output section for the full contract.
- **`search_todos(mode='summary')`/`search_advanced(mode='summary')` now return a non-empty `items` preview instead of always `items=[]`** (bead hq-cal.4). `ThingsMCPServer._read_result`'s summary-preview fallback checked `recent_preview`/`recent_projects`/`tags`/`top` (the preview keys used by the todo/project/tag summarizers) but never `result_preview`, the key `ProgressiveDisclosureEngine._summarize_search_results` actually populates - so search summaries always resolved to an empty preview list even though `count`/`total` were already correct. `result_preview` is now included in the fallback chain.
- **`get_logbook`/`get_due_in_days`/`get_activating_in_days`/`get_tags`/`get_tagged_items`/`get_recent` now carry `requested_mode` in `structured_content`, matching CLAUDE.md's documented uniform envelope contract** (bead hq-lsb). `ThingsMCPServer._read_result`'s list branch (taken by these six tools, which each pass a raw list rather than the `{"data": ..., "meta": ...}` dict shape `context_manager.optimize_response` produces) only ever set `items`/`count`/`total`/`mode`/`limit`/`offset`, never `requested_mode` - the key was silently absent from their `structured_content`, unlike every other list-returning read tool. None of these six tools has a `mode` parameter at all, so `requested_mode` now reports `None` (nothing was requested) while `mode` continues to report the effective/concrete shape (`'standard'`) of the returned items - the same `mode`-vs-`requested_mode` distinction already documented for tools that do accept `mode`.
- **`get_trash` now carries `requested_mode: None` in `structured_content`, matching the other no-`mode`-parameter list tools** (bead hq-cal.3). `get_trash` has no `mode` parameter, but routed through `ThingsMCPServer._read_result`'s dict branch (`server.py`) without passing `requested_mode=None` explicitly, so it fell through to echoing `mode='standard'` back as `requested_mode` too - unlike `get_logbook`/`get_due_in_days`/`get_activating_in_days`/`get_tags`/`get_tagged_items`/`get_recent`, which were already fixed to report `requested_mode: None` by hq-lsb. `get_trash`'s call site now passes `requested_mode=None` explicitly; `mode` continues to report the effective/concrete shape (`'standard'`). Audited every other `_read_result` call site in `server.py` - no other dict- or list-branch caller has this defect.
- **`get_inbox`/`get_today`/`get_upcoming`/`get_anytime`/`get_someday` now return the canonical structured `invalid_mode` error for a bogus `mode` instead of crashing with an opaque `ToolError`** (bead hq-exd). These five list tools passed `mode` straight into `ResponseMode(...)` unguarded - a bogus mode string (e.g. `mode='bogus'`) raised an unhandled `ValueError`, surfaced by FastMCP as a `ToolError` with no `structured_content`, unlike `get_todos`/`get_projects`/`get_areas`/`get_project_headings`/`search_todos`/`search_advanced`, which already returned `read_error('invalid_mode', ...)`. The inline validation duplicated across those six tools is now a single shared `ThingsMCPServer._validate_mode` helper, applied uniformly to all eleven `mode`-accepting read tools so the check and error shape can never drift apart again.

#### Tag handling
- **`bulk_update_todos(tags=...)` no longer double-emits newly-created tags in the AppleScript tag string under the `allow_all` tag policy** (bead hq-3bp). `TagValidationResult.valid_tags` already includes `created_tags` under `ALLOW_ALL` (`TagValidationService._apply_policy` extends `valid_tags` with the tags it auto-creates), but `bulk_operations.py::_validate_bulk_params` concatenated `tag_validation['existing']` (mapped from `valid_tags`) with `tag_validation['created']` again at the call site - so `bulk_update_todos(tags='a,b')` under `ALLOW_ALL` emitted `'a, b, a, b'` to AppleScript instead of `'a, b'` (Things itself deduplicates the applied tags, so the visible end-state was correct, but the emitted payload was wrong and wasteful). Fixed by using `tag_validation['existing']` alone, which is already the complete, correctly-deduplicated set under every policy (`ALLOW_ALL`/`FILTER_SILENT`/`FILTER_WARN`/`FAIL_ON_UNKNOWN` - `created_tags` is always empty under the three filtering policies, so this is a no-op change there). The identical pattern existed in `write_operations.py::_prepare_tags` (shared by `add_todo`/`update_todo`/`add_project`/`update_project`/`add_area`/`update_area`/`add_tags`) but was masked there by a `dict.fromkeys()` dedup already applied to its result before use - fixed the same way for consistency, with no behavior change to its callers.
- **`THINGS_MCP_TAG_CREATION_POLICY` (env var / env_file) is no longer a dead configuration knob - `filter_silent` and `fail_on_unknown` are now reachable** (bead hq-nb1). `config.py`'s `tag_creation_policy` and `ai_can_create_tags` fields were cross-synced via a pair of `field_validator(mode='before')` validators whose order was determined by field-declaration order, not by which value the caller actually set: `ai_can_create_tags` (declared first) was always validated before `tag_creation_policy`, so `tag_creation_policy`'s validator always found `ai_can_create_tags` already present and unconditionally derived the policy from *that* field alone, discarding whatever `tag_creation_policy` had been explicitly set to. As a result `THINGS_MCP_TAG_CREATION_POLICY=filter_silent`/`fail_on_unknown` (env var or env_file) silently collapsed to `ALLOW_ALL`/`FILTER_WARN` depending only on `ai_can_create_tags`, and the same collapse applied to constructing `ThingsMCPConfig(tag_creation_policy=...)` directly. Both field_validators are replaced with a single `model_validator(mode='after')` that reconciles the two fields using `model_fields_set` to detect which one(s) were actually provided (env var, env_file, or constructor kwarg) versus left at their defaults: an explicitly-set `tag_creation_policy` now always wins and is never silently overridden; `ai_can_create_tags` alone (policy unset) still derives the policy as before (`True` -> `ALLOW_ALL`, `False` -> `FILTER_WARN`); when both are explicitly set and conflict, `tag_creation_policy` wins and `ai_can_create_tags` is recomputed to match (`policy == ALLOW_ALL <-> True`), with a logged warning noting the conflict. All four policies (`allow_all`/`filter_silent`/`filter_warn`/`fail_on_unknown`) are now reachable via env var, env_file, and constructor kwargs alike. The declared default for `tag_creation_policy` is also corrected from `fail_on_unknown` to `filter_warn` in this same change: the pre-fix validator bug meant an unconfigured `tag_creation_policy` never actually resolved to its then-declared `FAIL_ON_UNKNOWN` default (it was always silently rewritten to `FILTER_WARN`, derived from `ai_can_create_tags`'s default of `False`) - so every unconfigured deployment has always behaved as `filter_warn` in practice, matching CLAUDE.md's documented "Non-existent tags are silently filtered (no error)". Correcting the declared default to `filter_warn` means there is no actual behavior change for unconfigured users from this fix - only the previously-dead `THINGS_MCP_TAG_CREATION_POLICY` env var and explicit-conflict reconciliation are new.
- **`create_tag` no longer creates a blank-titled tag from a whitespace-only name** (bead hq-r87). `create_tag('   ')` previously reached AppleScript unchanged - Things silently trimmed the whitespace and created a real tag with an empty title, unlike `create_tag('')`, which was already rejected with `TAG_CREATION_FAILED` at the AppleScript layer. `create_tag` now strips and rejects a whitespace-only `tag_name` with the same `TAG_CREATION_FAILED` error before any AppleScript call is made (checked after the `ai_can_create_tags`/`TAG_CREATION_RESTRICTED` gate, matching the existing empty-name check's position). `add_tags`'s MCP-boundary tag parsing (`server.py`'s `_parse_tag_list`) already filters whitespace-only tokens out entirely (`if t.strip()` per token) before they ever reach tag validation/AppleScript - reviewed and confirmed no separate fix was needed there; a whitespace-only `add_tags(tags=...)` request resolves to the pre-existing `NO_VALID_TAGS` error, not a blank tag.

#### Validation / write-safety pre-checks
- **`update_todo`/`bulk_update_todos` now pre-check the primary todo_id via things.py before any write, returning `NOT_FOUND` for an unknown id instead of an opaque `APPLESCRIPT_ERROR`** (bead hq-wbm). AppleScript's `to do id "<uuid>"` unexpectedly also resolves a **project** uuid (Things treats projects as a "selected to do" class internally - verified live), so without this pre-check `update_todo(id=<project-uuid>, ...)` would silently rename/modify the project instead of failing; `update_todo` now rejects an id that resolves to anything other than a to-do with `VALIDATION_ERROR` (naming the actual type, e.g. "id 'X' is a project, not a to-do; use update_project() instead"), and a genuinely unknown id with `NOT_FOUND` - both returned before any AppleScript write, consistent with `list_id`/`list_title` resolution. `bulk_update_todos` pre-checks every id in the batch (batches are small - 2-50 ids per the documented optimal range) and excludes unresolvable ids from the AppleScript script entirely, reporting them in a new `not_found` list field in the response while still updating the valid ids; `updated_count`/`failed_count`/`total_requested` continue to reflect the full original request. If the things.py lookup itself raises (e.g. the Things database is unreadable / Full Disk Access missing), both tools fall back to proceeding with the write unchecked - the same documented fallback pattern as `list_id`'s DB-unreadable case. `delete_todo` already resolved id types via things.py and required no change.
- **`add_project`/`update_project` no longer orphan a project when `area_id`/`area_title` is unresolvable** (bead hq-rmh). `_build_create_project_script` (`add_project`) and `update_project`'s AppleScript both ran the whole write - including `set area of ... to area "<title>"` - inside a single `try` block with no transactional rollback: an unresolvable area threw partway through, so `add_project` created a real, un-areaed orphan project (and `update_project` silently discarded every other field in the same call - title/notes/tags/deadline/status) while still reporting `APPLESCRIPT_ERROR`. Both now pre-resolve `area_id`/`area_title` via things.py (`TodoOperations._resolve_area`, mirroring `add_todo`'s existing `list_id`/`list_title` pre-resolution) **before** any write: an unknown `area_id`/`area_title` returns `NOT_FOUND` and creates/changes nothing; an `area_title` matching more than one area returns `AMBIGUOUS_TARGET` (with the matching ids); a successful `area_title` match is normalized to its concrete `area_id` before the script is built. If the things.py lookup itself raises (e.g. an unreadable Things database / missing Full Disk Access), the pre-bead behavior is preserved - the raw `area_id`/`area_title` is emitted unchecked rather than refusing the write, the same documented fallback `add_todo`'s `list_id` already has. `add_project`'s URL-scheme heading-creation path (`_add_project_via_url_scheme`, used when a `todos` payload contains `##` lines) shares the same pre-resolution. `add_todo` has no public `area`/`area_id`/`area_title` parameter (only `list_id`/`list_title`, already pre-resolved) so it was not affected.
- **`add_tags`/`remove_tags`/`move_record` now reject an empty or whitespace-only `todo_id` with a structured `VALIDATION_ERROR` instead of sending it straight through to AppleScript** (bead hq-a5j). `add_tags`/`remove_tags` (`tools_helpers/write_operations.py`) never validated `todo_id` at all - `''`/`'   '` were embedded verbatim as `to do id ""` / `to do id "   "` in the generated AppleScript, unlike `update_todo`/`delete_todo`, which already call `ParameterValidator.validate_non_empty_string`. Both now call the same validator first and return `create_validation_error_response`'s `VALIDATION_ERROR` shape (`field: "todo_id"`) before any AppleScript call. `move_record`'s own `_validate_move_inputs` (`move_operations.py`) only rejected a falsy/empty `todo_id`, not a whitespace-only one (`'   '` previously passed through to the AppleScript move) - it now also rejects whitespace-only ids, and its `VALIDATION_ERROR` response carries `field: "todo_id"` for this case. `create_tag`'s `tag_name` parameter now declares `min_length=1` in its MCP tool schema, so an empty string (`''`) is rejected by pydantic at the tool boundary (a `ToolError`) rather than reaching the AppleScript layer as a no-op call; a whitespace-only name (`'   '`) continues to be rejected by the existing runtime guard (`TAG_CREATION_FAILED`, bead hq-r87), unaffected by this change.
- **The documented 100-item checklist cap is now actually enforced** (bead hq-exe). CLAUDE.md and the checklist tool docstrings stated "Maximum 100 checklist items per todo", but no code path checked the count before sending `checklist-items`/`append-checklist-items`/`prepend-checklist-items` to the Things URL scheme - 101+ items were silently accepted and created. `add_todo(checklist_items=...)`, `add_checklist_items`, `prepend_checklist_items`, and `replace_checklist_items` (`scheduling/todo_operations.py`'s new shared `_check_checklist_item_count` helper, `MAX_CHECKLIST_ITEMS = 100`) now reject a request whose `checklist_items`/`items` list (or newline-separated string, for `add_todo`) exceeds 100 with a structured `{"success": false, "error": "TOO_MANY_CHECKLIST_ITEMS", "field": "checklist_items"|"items", "message": "checklist supports at most 100 items, got N"}` error, checked before any AppleScript/URL-scheme write - exactly 100 items is still accepted, and `replace_checklist_items(items=[])` still clears the checklist as before. This is a per-request limit only: Things gives no cheap way to read how many checklist items a to-do already has, so `add_checklist_items`/`prepend_checklist_items` do not count pre-existing items on the target to-do, only the items being submitted in the current call.

#### Infrastructure
- **AppleScript executor now retries `rc=0` results whose stdout is the in-script `"ERROR:"`-prefixed convention, and a duplicate dead lock was removed** (bead hq-c7a). Several AppleScript script builders (`move_operations.py`'s project/area move scripts and `_get_todo_info`, `tag_service.py`'s tag-creation script) catch a failure inside their own `on error` handler and `return "ERROR: " & errMsg` instead of letting osascript itself exit non-zero - so `AppleScriptExecutor._execute_script_with_retry` (`services/applescript/executor.py`), which previously only retried on `returncode != 0`, treated these as a successful result and never retried them, even though Things 3 intermittently errors under rapid, unpaced back-to-back AppleEvents (AppleScript execution IS serialized process-wide via `AppleScriptExecutor._applescript_lock`, held around every osascript call - the failures are a pacing/burst issue, not a missing-lock issue). The retry loop now also treats a successful (`rc=0`) result whose stripped stdout starts with the exact literal `"ERROR:"` as retryable, reusing the existing bounded retry count and exponential backoff; on final exhaustion the result is still returned exactly as produced (same shape existing callers already parse via `output.startswith("ERROR:")`), so the failure contract is unchanged. Also removes `AppleScriptManager._applescript_lock` (`services/applescript_manager.py`) - a duplicate `asyncio.Lock()` that was declared but never acquired anywhere in that class (dead code); the real process-wide serialization has always lived in `AppleScriptExecutor._applescript_lock`. Live-measured (`tests/regression/test_bulk_and_move.py`, two full runs plus a targeted third): this fix does not fully eliminate `bulk_move_records`' known concurrency-related `failed_moves` under load - a distinct, narrower residual failure mode remains at `move_record`'s own `_get_todo_info` pre-check intermittently reporting a just-created, genuinely-valid todo as `TODO_NOT_FOUND` under concurrent AppleScript bursts; the regression suite's `_bulk_move_tolerating_concurrency_race` retry helper was tightened to retry only that specific `TODO_NOT_FOUND` signature (previously it retried on any failure) so a real regression still fails the suite instead of being silently masked.
- **`operation_queue`'s singleton no longer hangs when called from a second event loop** (bead hq-5xa). `get_operation_queue()` held a single module-level `OperationQueue` whose worker task was created via `asyncio.create_task(...)` inside `start()`, permanently binding that task (and anything it awaits) to whichever event loop was running at creation time - a later call from a *different* event loop (e.g. an MCP client doing a fresh `asyncio.run()` per call) reused that stale worker task and hung awaiting/restarting it against a foreign, possibly-closed loop; reproduced live with as few as two sequential bare `asyncio.run(get_operation_queue())` calls (hung at the second loop's teardown). Fixed by keying the queue by the currently-running event loop (`asyncio.get_running_loop()`) in a `WeakKeyDictionary`, so each loop gets its own `OperationQueue` + worker task - no cross-loop teardown/await is attempted at all (single-loop behavior is unchanged: repeated calls within one loop still return the same instance). Note: an *abandoned* loop's dict entry is not actually garbage-collected by this alone - the still-running worker `Task` strongly references its own loop, pinning the `WeakKeyDictionary` key for the life of the process (a small, bounded leak: one inert entry per abandoned loop, not unbounded growth or a hang); `shutdown_operation_queue()` avoids this for callers that control their own loop lifecycle by explicitly popping and stopping the current loop's entry before the loop is discarded. `tests/regression/test_utility_tools.py`'s `queue_status`/`get_server_capabilities` tests, previously batched into a single shared-event-loop test as a workaround for this hang (with a docstring that misattributed the mechanism to `.done()` itself rather than the cross-loop worker restart), are split back into normal independent per-test `call_sync` calls and the docstring corrected. Also adds `pytest-timeout` as a declared dev dependency (`pyproject.toml`'s `dev`/`test` extras, `requirements.txt`) and installs it into the dev venv, and enables the previously-commented-out `timeout = 300` in `pytest.ini` (the actually-effective pytest config in this repo - `pyproject.toml`'s `[tool.pytest.ini_options]` is ignored whenever `pytest.ini` is present), so a future cross-loop-hang-style regression fails the suite with a timeout instead of wedging it indefinitely.

### Documentation
- **`search_advanced`'s scope semantics are now documented (bead hq-frf) - no behavior change.** The tool's docstring and CLAUDE.md ("search_advanced scope semantics", under Tag Best Practices) now spell out three pre-existing, unchanged facts: (1) without an explicit `type` filter, only to-dos are searched - a bare `area=`/`start_date=`/`deadline=` filter can never return a project or heading, so pass `type='project'`/`'heading'` explicitly to search those kinds; (2) `area=` matches only items directly assigned to the area and does not cascade into to-dos living inside that area's projects - use `get_todos(project_uuid=...)` per project, or `get_areas(include_items=true)` to enumerate the area's projects first; (3) there is no `project=` filter parameter - use `get_todos(project_uuid=...)` to scope a search to one project.

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
