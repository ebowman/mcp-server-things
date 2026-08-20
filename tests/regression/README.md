# tests/regression

Opt-in regression harness that drives the real MCP tool boundary (a real
`fastmcp.Client` against a real `ThingsMCPServer().mcp`) against a real,
running Things 3. Complements `tests/live/` (which drives `ThingsTools`
directly, without going through FastMCP tool registration).

## Running

```bash
make test-regression
```

or directly:

```bash
THINGS_MCP_LIVE_TESTS=1 PYTHONPATH=src \
  /Users/ebowman/src/mcp-server-things-wt/.venv/bin/python -m pytest tests/regression -q
```

Must be run from the repo root so the Things URL-scheme auth token file
(`.things-auth` / `things-auth.txt`) is found. Never print, log, or commit
that token.

The whole directory is skipped (not failed) unless BOTH:
- `THINGS_MCP_LIVE_TESTS=1` is set, AND
- Things 3 is actually running (probed the same way as `tests/live/`).

Without `THINGS_MCP_LIVE_TESTS=1`, `pytest tests/regression -q` collects and
skips every test - it is safe to run in CI or any environment without
Things 3.

## What the sandbox creates

The session-scoped `sandbox` fixture (`conftest.py`) creates, once per test
session, and tracks every id for teardown:

- an area: `hq-gbl-reg area <ts>`
- a project inside that area, seeded with a real heading (`##Reg Heading`)
  and one seed to-do via `add_project(todos=...)`: `hq-gbl-reg project <ts>`
- a second, empty project in the same area (a move target for tests that
  need one): `hq-gbl-reg project B <ts>`
- a tag: `hq-gbl-reg-tag-<ts>` - created via the `create_tag` MCP tool if
  `ai_can_create_tags` is enabled in config, otherwise via a raw AppleScript
  `make new tag with properties {...}` fallback (this environment's default
  config has `ai_can_create_tags=False`, so the fallback is the normal path)
- a completed project (for `TARGET_COMPLETED` error-path tests):
  `hq-gbl-reg done <ts>` - created via `add_project` then
  `update_project(completed='true')` through the MCP client

All names use the shared prefix `hq-gbl-reg ` (tag: `hq-gbl-reg-tag-`) from
`helpers.SANDBOX_PREFIX` / `helpers.sandbox_title()`.

Every test in this suite MUST create only new objects inside/derived from
this sandbox (or track any other object it creates via `sandbox.track(id)`)
- never modify, tag, move into, complete, or delete any pre-existing
  to-do/project/area/tag.

## Teardown

Session-scoped teardown (`request.addfinalizer`, runs even on failure)
sweeps every current child of every sandbox project, then deletes/trashes
in this order: the tag first (cheap, no cascade risk), then every to-do
(before their parent projects, to avoid the "Can't get to do id" orphan
gap), then every project directly, then the area last (its delete purges
the area and trashes any projects still inside it, but does not cascade
onto to-dos - which were already handled by this point) - matching
REGRESSION_SPIKE_FINDINGS.md's "Recipe for the harness". It then verifies
via `things.py` that every tracked id is trashed/gone and the area/tag no
longer exist - raising `AssertionError` listing any leftovers. See
`docs/testing/REGRESSION_SPIKE_FINDINGS.md` for the verified delete
recipes and cascade behavior this teardown is built from (delete order,
the `move ... to list "Trash"` fallback for to-dos orphaned by an
already-trashed parent project, and the `things.get(id, trashed=None)`
`TypeError` quirk for area/tag ids).

## Zero-collateral-writes guard

A session-scoped, autouse fixture (`_collateral_guard`) snapshots the
*entire* database (every to-do/project/heading via `things.tasks(type=None,
status=None, trashed=None)`, plus `things.areas()` and `things.tags()`)
BEFORE the sandbox is created, and re-snapshots after teardown completes.
It asserts no pre-existing object changed:

- to-dos/projects/headings: their `modified` key must be unchanged (or the
  object must still exist at all)
- areas/tags: they carry no `modified`-style key at all, so only
  presence and `title` are checked

Any offender fails the run with a listing of `type`/`uuid`/`title`. Set
`THINGS_MCP_REG_SKIP_COLLATERAL_GUARD=1` to downgrade this to a
`warnings.warn` instead of a hard failure (not recommended - only for
debugging a suspected guard false-positive).

## Fixtures (`conftest.py`)

- `live_server` (session): a real `ThingsMCPServer()`.
- `mcp` (session): `await mcp.call(tool_name, **kwargs)` (async) /
  `mcp.call_sync(tool_name, **kwargs)` (sync) - opens a `fastmcp.Client`
  against `live_server.mcp`, calls the tool, and returns
  `result.structured_content` (or `{"tool_error": str(e)}` if FastMCP
  raised a `ToolError`).
- `server_tools` (session): `live_server.tools`, for the rare case that
  needs to bypass the MCP tool boundary entirely.
- `sandbox` (session): see above. `sandbox.track(id)`/`track_many(ids)`
  track extra to-dos/projects; `sandbox.track_area(area_id)` tracks an
  extra area (e.g. a second area used as an `update_project(area_id=...)`
  move target) - teardown sweeps its contained projects/todos the same way
  as the main sandbox area, deletes it, and verifies it's gone via
  `things.areas()`.

## Helpers (`helpers.py`)

- `ts()` - a unique UTC timestamp suffix.
- `sandbox_title(name)` - prefixes `name` with `hq-gbl-reg `.
- `items_by_uuid(structured)` - indexes a list/single-item tool's
  structured_content by uuid.
- `read_back(todo_id, predicate, timeout=20, interval=0.25)` - polls
  `things.get()` until `predicate(record)` is true; default timeout is 20s
  (not the documented 3s poll window) per the outlier measured in
  `REGRESSION_SPIKE_FINDINGS.md` step 4.
- `assert_read_error(result, code)` / `assert_write_error(result, code)` -
  assert `success is False`, an exact error `code` (lower_snake for reads,
  UPPER_SNAKE for writes), and a non-empty string `message`.
