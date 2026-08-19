# Changelog

All notable changes to the Things 3 MCP Server will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- `get_someday` no longer includes tasks from Someday projects by default; pass `include_project_tasks=true` to include them (marked `inheritedSomeday`)
- Read tools return structured_content `{items, count, total, mode, limit, offset}`; under `mode=summary` count = number of preview items and the full count is in `total`

### Fixed
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
