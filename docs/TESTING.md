# Testing Policy

This document is the short version of the testing gap analysis behind the
hq-f0w epic (hq-f0w.14). It states the rules; it does not re-derive them.

## The five rules

1. **Write-path tests must assert on the emitted AppleScript/URL, not just
   success.** A test that only checks `result["success"] is True` against a
   mocked `AppleScriptManager` can pass even when the generated script or
   URL-scheme call is wrong (wrong field, wrong escaping, wrong action) -
   the mock never validates the payload it was handed. Write-path unit
   tests must capture the script/URL actually built and assert on its
   content (title/notes/tags encoding, the action name, the parameter set).
   A meta-test enforces this pattern is followed for new write-path tests.

2. **Any future parser of AppleScript/URL-scheme output must be tested
   against captured real producer output, not a hand-rolled fixture
   string.** A test that hand-rolls its own sample output (rather than the
   format the real producer emits) can silently drift from what Things 3
   actually returns, passing against a fixture that no longer matches
   reality. This project's own AppleScript list-output read-parser stack
   (`AppleScriptParser` and its ~230-line legacy string parser) was
   removed in hq-f0w.33 once reads moved entirely to `things.py`, so there
   is currently no parser in this codebase to which this rule applies -
   it is a forward-looking constraint for if/when one is reintroduced.

3. **List-tool/convert tests must use the realistic fixtures module.**
   `convert_todo`/`convert_project` and the list tools built on them
   (`get_todos`, `get_today`, etc.) must be tested against fixtures that
   mirror the real `things.py` key set (see `tools_helpers/helpers.py`'s
   `convert_todo` docstring for the captured-live key set) rather than
   ad hoc dicts with guessed keys, so a field rename or removal in
   `things.py` is caught by the fixtures module rather than passing
   silently against a stale hand-written dict.

4. **Every declared tool parameter must be covered by a parameter-reach
   generator.** A parameter that's declared in a tool's signature/schema
   but never exercised by any test is a silent gap - a parameter-reach
   generator should enumerate declared parameters per tool and fail when
   one has no covering test, so new parameters can't be added without
   test coverage by construction (`tests/unit/test_parameter_reach.py`,
   hq-f0w.9).

5. **The live smoke suite runs before release.** Unit tests run entirely
   against mocked AppleScript/`things.py` calls and cannot catch a real
   Things 3 behavioral mismatch (e.g. a URL-scheme field Things silently
   ignores, an AppleScript command that errors against a real database
   state unit tests can't reproduce). `tests/live` (see below) is the
   end-to-end gate that gives an actual Things 3 the final say before a
   release ships.

## The live smoke suite (`tests/live/`)

`tests/live/` is an opt-in, self-cleaning suite that exercises the real
AppleScript and Things URL-scheme write paths against a real, running
Things 3 - not a mock.

- **Opt-in only.** The whole directory is skipped unless
  `THINGS_MCP_LIVE_TESTS=1` is set AND Things 3 is actually running
  (probed with a fast, non-launching AppleScript check). It never runs by
  accident, and it never hangs waiting on Things 3 to launch.
- **Self-cleaning.** A session-scoped fixture creates exactly one
  throwaway project (prefixed `hq-f0w-smoke live `) per test run. Every
  item created during the session is tracked and trashed in a
  session-scoped teardown that runs even if tests fail, and the teardown
  verifies via `things.py` that every tracked id actually ended up in the
  Trash - a leftover id fails the teardown itself (surfaced as a test
  error) rather than silently leaving data behind.
- **Never touches pre-existing data.** Every live test writes only into
  the suite's own throwaway project/heading. No live test creates, moves
  into, or modifies any project/area/heading that existed before the
  session started.

Run it locally with:

```bash
make test-live
# equivalent to:
THINGS_MCP_LIVE_TESTS=1 pytest tests/live -q
```

### Live-gated integration fixtures

`tests/integration/conftest.py`'s `real_things_tools` and
`cleanup_test_todos` fixtures both construct a real `AppleScriptManager`
and are gated the same way - they skip with a clear reason unless
`THINGS_MCP_LIVE_TESTS=1` is set. Integration tests that use only mocked
fixtures, or these two gated fixtures, are unaffected and run normally
(or skip cleanly) without the env var.

`tests/integration/test_bulk_operations_comprehensive.py`,
`test_search_comprehensive.py`, `test_search_performance.py`,
`test_cleanup_mechanism.py`, `test_date_scheduling_integration.py`,
`test_month_edge_cases.py`, and `test_temporal_queries.py` build their own
local `applescript_manager`/`things_tools` fixtures (or construct
`AppleScriptManager()` inline per test) instead of using
`real_things_tools`; each of those local fixtures/tests now calls the
same `_require_live_tests_env()` guard directly and the modules are
marked `live`, so `pytest tests/integration` as a whole is all skips
(zero real AppleScript/`osascript` calls) without `THINGS_MCP_LIVE_TESTS=1`
(hq-f0w.42, hq-f0w.44; an earlier accidental ungated run of
`test_bulk_operations_comprehensive.py` had hung and leaked items during
hq-f0w.14's own testing). `tests/integration/verify_cleanup.py` is a
standalone `__main__` script (not collected by pytest) that exits with an
error unless `THINGS_MCP_LIVE_TESTS=1` is set.

## The API regression suite (`tests/regression/`)

`tests/regression/` is a second opt-in, self-cleaning live suite. It
complements `tests/live/`, not replaces it: `tests/live/` drives
`ThingsTools` directly, while `tests/regression/` drives the real **MCP
tool boundary** - a real `fastmcp.Client` against a real
`ThingsMCPServer().mcp` - so it exercises the exact structured-content and
structured-error shapes an MCP client actually sees (schema validation,
tool registration, and all).

- **Opt-in only, same gate as `tests/live/`.** The whole directory is
  skipped (not failed) unless `THINGS_MCP_LIVE_TESTS=1` is set AND Things 3
  is actually running (probed the same way as `tests/live`). It is safe to
  run `pytest tests/regression -q` with no env var set in CI or on a
  machine without Things 3 - everything collects and skips.
- **Sandbox objects.** A session-scoped `sandbox` fixture
  (`tests/regression/conftest.py`) creates, once per session, its own
  throwaway area, two throwaway projects (one seeded with a real heading
  and a to-do, one empty as a move target), a throwaway tag, and a
  throwaway completed project (for `TARGET_COMPLETED` error-path tests) -
  every object is uniquely named with the prefix `hq-gbl-reg ` (tag names
  use `hq-gbl-reg-tag-`; see `tests/regression/helpers.py`'s
  `SANDBOX_PREFIX`/`sandbox_title()`). Tests that need additional objects
  call `sandbox.track(id)` / `sandbox.track_many(ids)` /
  `sandbox.track_area(area_id)` so teardown finds and removes them too.
  Every test in this suite must create only objects inside/derived from
  this sandbox (or explicitly tracked) - never modify, tag, move into,
  complete, or delete any pre-existing to-do/project/area/tag. See
  `tests/regression/README.md` for the exact teardown order (tag, then
  to-dos, then projects, then area).
- **The zero-collateral-writes guard.** A session-scoped, autouse fixture
  (`_collateral_guard`) snapshots the *entire* database (every
  to-do/project/heading via `things.tasks(type=None, status=None,
  trashed=None)`, plus `things.areas()` and `things.tags()`) before the
  sandbox is created, and re-snapshots after teardown completes. It fails
  the run - listing the offending `type`/`uuid`/`title` - if any
  pre-existing to-do/project/heading's `modified` key changed (or the
  object disappeared), or if any pre-existing area/tag's presence or title
  changed. This is the suite's real safety net against writing into a
  user's live database by accident. Set
  `THINGS_MCP_REG_SKIP_COLLATERAL_GUARD=1` to downgrade a failure to a
  `warnings.warn` instead of a hard failure - only for debugging a
  suspected guard false-positive, not for routine runs.
- **How to run:**
  ```bash
  make test-regression
  # equivalent to (the Makefile target uses -v instead of -q):
  THINGS_MCP_LIVE_TESTS=1 pytest tests/regression -q
  ```
  Run from the repo root so the Things URL-scheme auth token file
  (`.things-auth` / `things-auth.txt`) is found. Never print, log, or
  commit that token. The suite takes roughly 30 minutes against a real
  Things 3 - budget accordingly, and never run it concurrently with
  another live `tests/regression` or `tests/live` run against the same
  Things database (they share the real DB; a concurrent run will cross-trip
  the collateral guard with false positives).
- **When the collateral guard fires:** read the failure message - it lists
  the `type`/`uuid`/`title` of every object it believes changed
  unexpectedly. First check whether another live suite (`tests/regression`
  or `tests/live`) was running concurrently against the same Things
  database; if so, the failure is very likely a false positive from that
  second run's writes, not a real bug - re-run alone. If no concurrent run
  was in play, treat the listed uuids as a real regression: look up each
  one (`things.get(uuid, trashed=None)`) to see what changed, and trace it
  back to the test/tool call that caused it.
- **Strict-xfail convention for known bugs.** Where this suite has already
  found and documented a real live-behavior bug that isn't being fixed as
  part of adding the test, the assertion is pinned as
  `pytest.mark.xfail(strict=True, reason="observed: ... (bead-id)")`
  instead of skipped or asserted as correct - see
  `tests/regression/test_update_todo.py`, `test_seed_oracle.py`,
  `test_projects_areas.py`, and `test_bulk_and_move.py` for examples.
  `strict=True` means the xfail itself fails the run (XPASS) once the
  underlying bug is fixed, forcing the xfail marker to be removed rather
  than silently staying in place after a fix ships.
- **How to add coverage for a new tool:**
  1. Add/adjust the tool's declared parameters as normal, then regenerate
     the golden schema snapshot the new/changed schema will otherwise fail
     against: `THINGS_MCP_UPDATE_SCHEMA_SNAPSHOT=1 pytest
     tests/unit/test_tool_schema_snapshot.py`.
  2. `tests/unit/test_read_input_matrix.py` (for a read tool) or
     `tests/unit/test_write_input_matrix.py` (for a write tool) each end
     with a `TestCompleteness` check that introspects every tool's declared
     parameters via `Client.list_tools()` and fails if any `(tool, param)`
     pair has fewer than 3 `CASES` entries - so a new tool or a new
     parameter on an existing tool is forced into these matrices by
     construction; add the missing `CASES` rows there.
  3. Add a new regression module under `tests/regression/` (or extend an
     existing one, e.g. `test_list_tools.py`/`test_tags.py`) that exercises
     the new tool against a real Things 3 through the `mcp` fixture, and -
     if the tool reads back state that the seed oracle
     (`tests/regression/seed.py`/`test_seed_oracle.py`) already covers -
     add oracle rows/assertions there too rather than duplicating seed
     setup.

## Release gate

`THINGS_MCP_LIVE_TESTS=1 pytest tests/live -q` and
`THINGS_MCP_LIVE_TESTS=1 pytest tests/regression -q` must both pass on a
machine with Things 3 installed and running before tagging a release - see
the Release Checklist in `CLAUDE.md`.
