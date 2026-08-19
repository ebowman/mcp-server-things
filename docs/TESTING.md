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
`test_search_comprehensive.py`, and `test_search_performance.py` build
their own local `applescript_manager`/`things_tools` fixtures instead of
using `real_things_tools`; each of those local fixtures now calls the
same `_require_live_tests_env()` guard directly and the modules are
marked `live`, so `pytest tests/integration` as a whole is all skips
(zero real AppleScript/`osascript` calls) without `THINGS_MCP_LIVE_TESTS=1`
(hq-f0w.42; an earlier accidental ungated run of
`test_bulk_operations_comprehensive.py` had hung and leaked items during
hq-f0w.14's own testing).

## Release gate

`THINGS_MCP_LIVE_TESTS=1 pytest tests/live -q` must pass on a machine with
Things 3 installed and running before tagging a release - see the Release
Checklist in `CLAUDE.md`.
