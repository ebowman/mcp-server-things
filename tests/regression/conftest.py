"""Session fixtures for the opt-in live-Things-3 regression harness (hq-gbl.2).

This whole directory is skipped unless BOTH:
  - THINGS_MCP_LIVE_TESTS=1 is set in the environment, AND
  - Things 3 is actually running (probed via a fast, non-launching
    `application "Things3" is running` AppleScript call).

Same gate/probe as tests/live/conftest.py (not imported directly, to avoid
coupling the two suites' collection - reproduced here faithfully instead;
tests/live's own behavior is unchanged by this file).

Unlike tests/live (which drives ThingsTools directly), this suite calls
through the actual MCP tool boundary - a real `fastmcp.Client` against a
real `ThingsMCPServer().mcp` - so it exercises the exact structured-content
and structured-error shapes an MCP client sees (see tests/unit/
test_structured_output.py for the same Client(server.mcp) pattern used
against a mocked-tools server).

LIVE-WRITE SAFETY: the `sandbox` fixture creates its own throwaway area,
two throwaway projects (one seeded, one empty), a throwaway tag, and a
throwaway completed project - every object is uniquely named with the
`hq-gbl-reg ` prefix (see helpers.SANDBOX_PREFIX) and tracked for teardown.
Nothing here ever writes into, moves into, or otherwise touches a
pre-existing area/project/todo/tag - see COMMON.md's "LIVE-WRITE SAFETY"
rule. The session-scoped `_collateral_guard` fixture independently verifies
this by snapshotting the whole database before sandbox creation and after
teardown.
"""
import asyncio
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

import pytest

from regression import suite_cleanup
from regression.helpers import SANDBOX_PREFIX, sandbox_title, ts
from regression.seed import create_seed_set

_OSASCRIPT_PROBE_TIMEOUT_SECS = 5

# hq-8vx: session cleanup state, consumed by pytest_sessionfinish (below).
# Cleanup deliberately does NOT live in fixture finalizers: pytest-timeout's
# per-test timer spans setup+call+teardown, so a session-fixture finalizer
# runs inside the LAST test's 300s timer and was killed mid-cleanup, leaking
# sandbox objects into the user's active lists. sessionfinish is outside
# every item's timer.
_STATE: Dict[str, Any] = {"sandbox": None, "guard": None}


def _things_running() -> bool:
    """Fast, non-launching probe for whether Things 3 is running.

    Mirrors tests/live/conftest.py's _things_running (same probe as
    things_mcp.doctor.check_things_running).
    """
    try:
        result = subprocess.run(
            ["osascript", "-e", 'application "Things3" is running'],
            capture_output=True,
            text=True,
            timeout=_OSASCRIPT_PROBE_TIMEOUT_SECS,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return result.returncode == 0 and result.stdout.strip().lower() == "true"


def pytest_collection_modifyitems(config, items):
    """Apply the 'live' marker to every item under tests/regression (a bare
    module-level `pytestmark` in a conftest.py has no effect on sibling test
    modules' collected markers - verified live: `-m "not live"
    --collect-only` still collected all 6 items with only a conftest-level
    pytestmark, so the marker must be applied explicitly per-item here
    instead; test_harness_smoke.py additionally sets its own module-level
    `pytestmark = pytest.mark.live`, which DOES work for markers declared
    directly in a test module - both together make `-m live` /
    `-m "not live"` selection correct regardless of which mechanism a given
    test file relies on), then skip the whole directory unless opted in and
    Things is running."""
    skip_reason = None
    if os.environ.get("THINGS_MCP_LIVE_TESTS") != "1":
        skip_reason = (
            "regression suite requires THINGS_MCP_LIVE_TESTS=1 "
            "(opt-in; writes to a real Things 3 database)"
        )
    elif not _things_running():
        skip_reason = (
            "Things 3 is not running - regression suite skipped rather than "
            "risk an auto-launch/hang"
        )

    skip_marker = pytest.mark.skip(reason=skip_reason) if skip_reason else None
    for item in items:
        if "tests/regression" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(pytest.mark.live)
            if skip_marker is not None:
                item.add_marker(skip_marker)


# ---------------------------------------------------------------------------
# live_server / mcp fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def live_server():
    """A real ThingsMCPServer, built with the real AppleScriptManager and
    config from the environment as normal (same construction the actual
    server entrypoint uses). Only constructed inside this already-gated
    session, so importing this module never touches Things 3 at collection
    time.
    """
    from things_mcp.server import ThingsMCPServer

    return ThingsMCPServer()


class _MCPCallHelper:
    """Wraps a fastmcp Client(server.mcp) with a `call`/`call_sync` helper
    that returns structured_content (or a {"tool_error": str} dict when
    FastMCP raised a ToolError instead of returning a structured error)."""

    def __init__(self, server):
        self._server = server

    async def call(self, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
        from fastmcp import Client

        from regression.mcp_call import call_tool_structured

        client = Client(self._server.mcp)
        async with client:
            return await call_tool_structured(client, tool_name, kwargs)

    def call_sync(self, tool_name: str, **kwargs: Any) -> Dict[str, Any]:
        return asyncio.run(self.call(tool_name, **kwargs))


@pytest.fixture(scope="session")
def mcp(live_server):
    """Async `await mcp.call(tool_name, **kwargs)` / sync `mcp.call_sync(...)`
    helper bound to the real live_server, returning structured_content."""
    return _MCPCallHelper(live_server)


@pytest.fixture(scope="session")
def server_tools(live_server):
    """Direct access to live_server.tools for rare cases that need to bypass
    the MCP tool boundary (e.g. inspecting internals)."""
    return live_server.tools


# ---------------------------------------------------------------------------
# AppleScript fallback used for sandbox setup/teardown (not itself under
# test - mirrors REGRESSION_SPIKE_FINDINGS.md's verified recipes and
# tests/live/conftest.py's _delete_via_applescript).
# ---------------------------------------------------------------------------


def _run_applescript(script: str, timeout: int = 15) -> Dict[str, Any]:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return {"success": False, "output": "", "error": str(e)}
    output = result.stdout.strip()
    return {
        "success": result.returncode == 0 and not output.startswith("error:"),
        "output": output,
        "error": result.stderr.strip(),
    }


def _create_tag_via_applescript(tag_name: str) -> bool:
    """Fallback tag creation when ai_can_create_tags is False (the
    create_tag MCP tool is then restricted - see CLAUDE.md/config.py).
    Uses the verified `make new tag with properties {...}` recipe from
    REGRESSION_SPIKE_FINDINGS.md."""
    escaped = tag_name.replace('"', '\\"')
    script = f'''
    tell application "Things3"
        try
            make new tag with properties {{name:"{escaped}"}}
            return "created"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_applescript(script)
    return result["success"] and result["output"] == "created"


def _delete_via_applescript(item_id: str) -> None:
    """Delete a to-do/project by id via raw AppleScript `delete`, falling
    back to `move ... to list "Trash"` for a to-do orphaned by an
    already-trashed parent project (see REGRESSION_SPIKE_FINDINGS.md's
    "Working delete recipe" / tests/live/conftest.py's own copy of this
    same fallback). Best-effort: failures are not raised here, the
    leftover-check in the sandbox teardown is the real safety net.
    """
    escaped = item_id.replace('"', '\\"')

    def _try_delete(target_expr: str) -> bool:
        script = f'''
        tell application "Things3"
            try
                set targetItem to {target_expr}
                delete targetItem
                return "deleted"
            on error errMsg
                return "error: " & errMsg
            end try
        end tell
        '''
        result = _run_applescript(script)
        return result["success"] and result["output"] == "deleted"

    if _try_delete(f'to do id "{escaped}"'):
        return
    if _try_delete(f'project id "{escaped}"'):
        return

    move_script = (
        'tell application "Things3"\n'
        '    try\n'
        f'        set targetItem to to do id "{escaped}"\n'
        '        move targetItem to list "Trash"\n'
        '    end try\n'
        'end tell'
    )
    _run_applescript(move_script)


def _delete_area_via_applescript(area_id: str) -> bool:
    escaped = area_id.replace('"', '\\"')
    script = f'''
    tell application "Things3"
        try
            delete (area id "{escaped}")
            return "deleted"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_applescript(script)
    return result["success"] and result["output"] == "deleted"


def _delete_tag_via_applescript(tag_id: str) -> bool:
    escaped = tag_id.replace('"', '\\"')
    script = f'''
    tell application "Things3"
        try
            delete (tag id "{escaped}")
            return "deleted"
        on error errMsg
            return "error: " & errMsg
        end try
    end tell
    '''
    result = _run_applescript(script)
    return result["success"] and result["output"] == "deleted"


# ---------------------------------------------------------------------------
# sandbox fixture
# ---------------------------------------------------------------------------


class Sandbox:
    """Tracks every uuid created during the regression session for
    teardown, plus the resolved ids/titles regression tests use."""

    def __init__(self):
        self.area_id: Optional[str] = None
        self.area_title: Optional[str] = None

        self.project_id: Optional[str] = None
        self.project_title: Optional[str] = None
        self.heading_title: Optional[str] = None
        self.heading_id: Optional[str] = None

        self.project_b_id: Optional[str] = None
        self.project_b_title: Optional[str] = None

        self.done_project_id: Optional[str] = None
        self.done_project_title: Optional[str] = None

        self.tag_name: Optional[str] = None
        self.tag_id: Optional[str] = None
        self.tag_created_via: Optional[str] = None  # 'create_tag' or 'applescript'

        self.tracked_todo_ids: List[str] = []
        self.tracked_project_ids: List[str] = []
        self.tracked_area_ids: List[str] = []

    def track(self, item_id: Optional[str]) -> Optional[str]:
        if item_id:
            self.tracked_todo_ids.append(item_id)
        return item_id

    def track_many(self, ids) -> None:
        for item_id in ids:
            self.track(item_id)

    def track_area(self, area_id: Optional[str]) -> Optional[str]:
        """Track an extra area (beyond the main sandbox area) created by a
        test - e.g. a second area used as an update_project(area_id=...)
        move target. Swept and deleted by the sandbox teardown, after its
        contained projects/todos are handled, the same way the main
        sandbox area is."""
        if area_id:
            self.tracked_area_ids.append(area_id)
        return area_id


@pytest.fixture(scope="session")
def sandbox(request, live_server, mcp):
    import things

    session = Sandbox()
    _STATE["sandbox"] = session  # cleaned up in pytest_sessionfinish (hq-8vx)

    # (a) area
    session.area_title = sandbox_title("area")
    area_result = asyncio.run(mcp.call("add_area", title=session.area_title))
    assert area_result.get("success"), f"Failed to create sandbox area: {area_result}"
    session.area_id = area_result["area_id"]

    # (b) seeded project (with a real heading + one seed todo) inside the area
    session.project_title = sandbox_title("project")
    heading_title = "Reg Heading"
    project_result = asyncio.run(
        mcp.call(
            "add_project",
            title=session.project_title,
            area_id=session.area_id,
            todos=f"##{heading_title}\nReg seed todo",
        )
    )
    assert project_result.get("success"), f"Failed to create sandbox project: {project_result}"
    session.project_id = project_result["project_id"]
    session.tracked_project_ids.append(session.project_id)

    # Let the URL-scheme json-action write settle before reading back.
    time.sleep(1)
    headings = [
        t for t in things.tasks(project=session.project_id, type="heading") or []
        if t.get("title") == heading_title
    ]
    session.heading_title = heading_title if headings else None
    session.heading_id = headings[0]["uuid"] if headings else None

    # Track the seed to-do(s) actually produced, not just the expected one.
    for t in things.tasks(project=session.project_id, type="to-do") or []:
        session.track(t["uuid"])

    # (c) second EMPTY project (move target)
    session.project_b_title = sandbox_title("project B")
    project_b_result = asyncio.run(
        mcp.call(
            "add_project",
            title=session.project_b_title,
            area_id=session.area_id,
        )
    )
    assert project_b_result.get("success"), f"Failed to create sandbox project B: {project_b_result}"
    session.project_b_id = project_b_result["project_id"]
    session.tracked_project_ids.append(session.project_b_id)

    # (d) tag - via create_tag if ai_can_create_tags, else AppleScript fallback
    session.tag_name = f"hq-gbl-reg-tag-{ts()}"
    if live_server.config.ai_can_create_tags:
        tag_result = asyncio.run(mcp.call("create_tag", tag_name=session.tag_name))
        assert tag_result.get("success"), f"Failed to create sandbox tag: {tag_result}"
        session.tag_created_via = "create_tag"
    else:
        # ai_can_create_tags is False in this environment's config (see
        # config.py's default), so create_tag is restricted
        # (TAG_CREATION_RESTRICTED) - fall back to raw AppleScript
        # `make new tag with properties {...}`, the verified recipe from
        # REGRESSION_SPIKE_FINDINGS.md.
        created = _create_tag_via_applescript(session.tag_name)
        assert created, f"Failed to create sandbox tag {session.tag_name!r} via AppleScript fallback"
        session.tag_created_via = "applescript"
    # Resolve the tag's uuid via things.py for teardown/verification.
    time.sleep(0.5)
    matching_tags = [t for t in things.tags() or [] if t.get("title") == session.tag_name]
    session.tag_id = matching_tags[0]["uuid"] if matching_tags else None

    # (e) completed project (for TARGET_COMPLETED tests)
    session.done_project_title = sandbox_title("done")
    done_result = asyncio.run(
        mcp.call(
            "add_project",
            title=session.done_project_title,
            area_id=session.area_id,
        )
    )
    assert done_result.get("success"), f"Failed to create sandbox done project: {done_result}"
    session.done_project_id = done_result["project_id"]
    session.tracked_project_ids.append(session.done_project_id)

    complete_result = asyncio.run(
        mcp.call("update_project", id=session.done_project_id, completed="true")
    )
    assert complete_result.get("success"), (
        f"Failed to mark sandbox done project completed: {complete_result}"
    )

    return session


@pytest.fixture(scope="session")
def seeded(sandbox, mcp):
    """Session-scoped: creates the deterministic seed set (hq-gbl.6) once,
    via `regression.seed.create_seed_set`. Every created id is tracked on
    `sandbox` by `create_seed_set` itself (including ids created outside
    the sandbox project - inbox, area, project B - which live outside the
    sandbox project subtree and would not otherwise be found by the
    session teardown's per-project child sweep), so no additional teardown
    is needed here - cleanup happens in `pytest_sessionfinish` (hq-8vx).
    """
    return create_seed_set(mcp, sandbox)


def _teardown_sandbox(session: Sandbox, budget: Optional[suite_cleanup.Budget] = None) -> List[str]:
    """Sweep every child of every sandbox project, trash to-dos then
    projects, delete the tag then the area, then verify via things.py that
    everything tracked is gone/trashed. Returns the list of leftovers (the
    caller, pytest_sessionfinish, reports them and fails the run) - runs even
    if tests failed.

    Order matters (REGRESSION_SPIKE_FINDINGS.md's "Recipe for the harness"):
    tag delete first (cheap, no cascade), then to-dos (including any swept
    up that were never explicitly tracked), then projects, then the area
    last (area delete purges the area and trashes any *projects* still
    inside it, but does NOT cascade onto to-dos - so to-dos must already be
    handled by this point).

    Headings: Things' AppleScript dictionary has no heading class at all -
    there is no `delete`/`move` verb that can target one directly (same gap
    documented in tests/live/conftest.py's `_trash_and_verify`). A heading
    swept up from a sandbox project (e.g. the seeded 'Reg Heading', or one
    created by a future bead's add_project(todos='##...')) is therefore
    excluded from the delete loop entirely, and the leftover check below
    treats a heading as cleaned up once its parent project is itself
    trashed/gone - matching _trash_and_verify's own heading handling - so
    this must not false-fail future headed-project sandboxes.

    Extra areas (`session.tracked_area_ids`, e.g. a second area used as an
    update_project(area_id=...) move target): any project things.py
    reports as living inside one of these tracked areas is added to the
    same project sweep (so its to-dos/headings/project are handled by the
    same steps 2-3 below, before the area itself is deleted), then each
    tracked extra area is deleted the same way as the main sandbox area
    (step 4) and independently verified gone via things.areas().
    """
    import things

    budget = budget or suite_cleanup.Budget()

    # Extra areas: pull in any project things.py reports as belonging to a
    # tracked extra area, so its to-dos/headings are swept the same way as
    # the main sandbox area's projects, before the area itself is deleted.
    extra_area_project_ids: List[str] = []
    if session.tracked_area_ids:
        for area_id in session.tracked_area_ids:
            if not area_id:
                continue
            for p in things.projects(area=area_id, status=None, trashed=None) or []:
                extra_area_project_ids.append(p["uuid"])

    # Sweep every current child (any type/status/trashed) of every sandbox
    # project (main sandbox projects plus any project living in a tracked
    # extra area) - catches anything created but not explicitly tracked.
    # Headings are collected separately (see docstring) since there is no
    # AppleScript verb to delete/move one directly.
    child_todo_ids: List[str] = []
    child_heading_ids: List[str] = []
    all_project_ids = list(
        dict.fromkeys(session.tracked_project_ids + extra_area_project_ids)
    )
    for project_id in all_project_ids:
        if not project_id:
            continue
        for t in things.tasks(project=project_id, type=None, status=None, trashed=None) or []:
            if t.get("type") == "heading":
                child_heading_ids.append(t["uuid"])
            else:
                child_todo_ids.append(t["uuid"])

    all_todo_ids = list(dict.fromkeys(session.tracked_todo_ids + child_todo_ids))
    # Any explicitly-tracked id that things.py reports as a heading is
    # rerouted here too (rather than through the AppleScript delete loop),
    # in case a future test tracks a heading id directly.
    tracked_heading_ids: List[str] = []
    still_todo_ids: List[str] = []
    for todo_id in all_todo_ids:
        record = things.get(todo_id, trashed=None)
        if record is not None and record.get("type") == "heading":
            tracked_heading_ids.append(todo_id)
        else:
            still_todo_ids.append(todo_id)
    all_todo_ids = still_todo_ids
    all_heading_ids = list(dict.fromkeys(child_heading_ids + tracked_heading_ids))

    # 1. Tag delete first - cheap, no cascade risk.
    if session.tag_id:
        _delete_tag_via_applescript(session.tag_id)
    elif session.tag_name:
        # Fall back to a fresh uuid lookup if it wasn't resolved earlier.
        matching = [t for t in things.tags() or [] if t.get("title") == session.tag_name]
        if matching:
            _delete_tag_via_applescript(matching[0]["uuid"])

    # 2-4. Batched deletes (one osascript per kind, per-id try inside):
    #    to-dos first (so `delete (to do id ...)` doesn't hit the "Can't get
    #    to do id" orphan gap; the script falls back to move-to-Trash),
    #    then projects (incl. those swept from tracked extra areas), then
    #    areas last (area delete purges the area and trashes any projects
    #    still inside it, but NOT their to-dos). Headings are skipped - see
    #    docstring. Anything not deleted is logged to stderr by delete_all.
    suite_cleanup.delete_all(
        all_todo_ids,
        [pid for pid in all_project_ids if pid],
        [a for a in [session.area_id] + list(session.tracked_area_ids) if a],
        budget,
    )

    # Give Things a moment to process the deletes before verifying.
    time.sleep(1)

    leftovers: List[str] = []

    # Verify to-dos/projects: things.get(id, trashed=None) must be None
    # (purged) or trashed=True.
    for item_id in all_todo_ids + [pid for pid in session.tracked_project_ids if pid]:
        record = things.get(item_id, trashed=None)
        if record is None:
            continue
        if record.get("trashed"):
            continue
        leftovers.append(f"todo/project {item_id} still active: {record.get('title')!r}")

    # Verify headings: no independent trashed flag, but a heading is
    # cleaned up once its parent project (things.py's 'project' field on
    # the heading record) is itself trashed or gone - matching
    # tests/live/conftest.py's _trash_and_verify heading handling.
    for heading_id in all_heading_ids:
        record = things.get(heading_id, trashed=None)
        if record is None:
            continue
        parent_project_id = record.get("project")
        parent = things.get(parent_project_id, trashed=None) if parent_project_id else None
        if parent is not None and not parent.get("trashed"):
            leftovers.append(
                f"heading {heading_id} ({record.get('title')!r}) parent project "
                f"{parent_project_id} is not trashed"
            )

    # Verify area: bare things.get(id) (trashed kwarg raises TypeError for
    # areas/tags - REGRESSION_SPIKE_FINDINGS.md's "things.py area/tag
    # quirk") must be None, and it must not appear in things.areas().
    if session.area_id:
        area_record = things.get(session.area_id)
        still_listed = any(a["uuid"] == session.area_id for a in things.areas() or [])
        if area_record is not None or still_listed:
            leftovers.append(f"area {session.area_id} still present: {session.area_title!r}")

    # Verify tracked extra areas the same way as the main sandbox area.
    for area_id in session.tracked_area_ids:
        if not area_id:
            continue
        area_record = things.get(area_id)
        still_listed = any(a["uuid"] == area_id for a in things.areas() or [])
        if area_record is not None or still_listed:
            leftovers.append(f"extra area {area_id} still present")

    # Verify tag: same bare-get quirk; must be gone from things.tags().
    if session.tag_id:
        tag_record = things.get(session.tag_id)
        still_listed = any(t["uuid"] == session.tag_id for t in things.tags() or [])
        if tag_record is not None or still_listed:
            leftovers.append(f"tag {session.tag_id} still present: {session.tag_name!r}")
    elif session.tag_name:
        still_listed = any(t["title"] == session.tag_name for t in things.tags() or [])
        if still_listed:
            leftovers.append(f"tag (unresolved id) still present: {session.tag_name!r}")

    return leftovers


# ---------------------------------------------------------------------------
# Zero-collateral-writes guard
# ---------------------------------------------------------------------------


def _snapshot_db() -> Dict[str, Dict[str, Any]]:
    """Snapshot every task/area/tag in the database, keyed by uuid.

    Tasks (to-dos/projects/headings) carry a 'modified' key (things.tasks()
    row keys observed live: created, deadline, index, modified, notes,
    start, start_date, status, stop_date, title, today_index, trashed,
    type, uuid). Areas/tags carry no modified-style key at all (observed
    live: areas -> title/type/uuid; tags -> shortcut/title/type/uuid) so
    for those we snapshot {uuid: title} and assert presence/title
    unchanged instead.
    """
    import things

    snapshot: Dict[str, Dict[str, Any]] = {}
    for row in things.tasks(type=None, status=None, trashed=None) or []:
        snapshot[row["uuid"]] = {
            "kind": "task",
            "type": row.get("type"),
            "title": row.get("title"),
            "modified": row.get("modified"),
        }
    for row in things.areas() or []:
        snapshot[row["uuid"]] = {"kind": "area", "type": "area", "title": row.get("title")}
    for row in things.tags() or []:
        snapshot[row["uuid"]] = {"kind": "tag", "type": "tag", "title": row.get("title")}
    return snapshot


@pytest.fixture(scope="session", autouse=True)
def _collateral_guard(request):
    """Session-scoped, autouse: snapshots the whole database BEFORE any
    sandbox object is created (so sandbox ids are excluded as 'new' and
    never checked) and asserts, after ALL teardown has run, that no
    PRE-EXISTING uuid changed ('modified' for tasks; presence/title for
    areas/tags with no modified-style key) or disappeared.

    Ordering: this fixture is function/request-order independent of
    `sandbox` (both are session-scoped), but pytest finalizers run in
    reverse registration order - this fixture's own finalizer must run
    AFTER the sandbox's teardown finalizer so the post-snapshot reflects
    the fully-cleaned-up database, not mid-teardown state. We guarantee
    that here by depending on nothing and instead taking the "before"
    snapshot eagerly at fixture setup (session start, before sandbox is
    ever requested) and registering our own finalizer immediately - since
    autouse session fixtures are instantiated before any test-requested
    session fixture the first test needs (including `sandbox`, which is
    pulled in lazily by whichever test first requests it), this fixture's
    finalizer is registered first and therefore (LIFO) runs LAST, after
    sandbox's finalizer.
    """
    skip_reason_env = os.environ.get("THINGS_MCP_REG_SKIP_COLLATERAL_GUARD") == "1"

    # hq-8vx: session-START sweep of any prefixed leftovers from previous
    # (crashed/killed) runs - BEFORE the snapshot so they aren't treated as
    # pre-existing objects whose disappearance is "collateral".
    suite_cleanup.sweep_prefix(SANDBOX_PREFIX, "regression start", suite_cleanup.Budget())

    try:
        before = _snapshot_db()
    except Exception:
        # things.py unavailable at this point (e.g. DB unreadable) - nothing
        # to compare; let tests proceed, they'll fail on their own if things
        # is really broken.
        before = None

    def _check():
        if before is None:
            return
        try:
            after = _snapshot_db()
        except Exception:
            return

        offenders = []
        for uuid, before_row in before.items():
            after_row = after.get(uuid)
            if after_row is None:
                offenders.append(
                    f"{before_row['kind']} {uuid} ({before_row.get('title')!r}) disappeared"
                )
                continue
            if before_row["kind"] == "task":
                if after_row.get("modified") != before_row.get("modified"):
                    offenders.append(
                        f"task {uuid} ({before_row.get('title')!r}) 'modified' changed: "
                        f"{before_row.get('modified')!r} -> {after_row.get('modified')!r}"
                    )
            else:
                # area/tag: no modified-style key - assert title unchanged.
                if after_row.get("title") != before_row.get("title"):
                    offenders.append(
                        f"{before_row['kind']} {uuid} title changed: "
                        f"{before_row.get('title')!r} -> {after_row.get('title')!r}"
                    )

        if offenders:
            message = (
                "Zero-collateral-writes guard: the following PRE-EXISTING "
                f"Things objects were modified or disappeared during this "
                f"regression run: {offenders}"
            )
            if skip_reason_env:
                import warnings

                warnings.warn(message)
            else:
                raise AssertionError(message)

    _STATE["guard"] = _check


def pytest_sessionfinish(session, exitstatus):
    """hq-8vx: leak-proof session cleanup, outside every per-test timeout.

    Order: sandbox teardown (batched, tracked ids + children) -> end sweep of
    every active SANDBOX_PREFIX item -> optional empty-trash -> collateral
    guard check. Total budget 240s (own wall clock); failures are logged to
    stderr and flip the exit status instead of raising.
    """
    sandbox_session = _STATE.pop("sandbox", None)
    guard = _STATE.pop("guard", None)
    if sandbox_session is None and guard is None:
        return
    failures: List[str] = []
    budget = suite_cleanup.Budget()
    if sandbox_session is not None:
        try:
            left = _teardown_sandbox(sandbox_session, budget)
            if left:
                failures.append(f"sandbox teardown leftovers: {left}")
        except Exception as e:  # never let cleanup crash the session
            failures.append(f"sandbox teardown raised: {e!r}")
    suite_cleanup.sweep_prefix(SANDBOX_PREFIX, "regression end", budget)
    suite_cleanup.maybe_empty_trash()
    if guard is not None:
        try:
            guard()
        except AssertionError as e:
            failures.append(str(e))
    for f in failures:
        suite_cleanup.log(f"FAILURE: {f}")
    if failures and session.exitstatus == 0:
        session.exitstatus = int(pytest.ExitCode.TESTS_FAILED)
