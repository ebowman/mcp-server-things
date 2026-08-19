"""Session fixtures for the opt-in live Things 3 smoke suite.

This whole directory is skipped unless BOTH:
  - THINGS_MCP_LIVE_TESTS=1 is set in the environment, AND
  - Things 3 is actually running (probed via a fast, non-launching
    `application "Things3" is running` AppleScript call).

When the suite does run, a single throwaway project (see
`SMOKE_PROJECT_PREFIX`) is created once per session and every test-created
item (todos, the project itself) is tracked and trashed in a
session-scoped teardown that runs even if tests fail (via
`request.addfinalizer`). Teardown verifies via things.py that every
tracked uuid is actually trashed and raises (test error) listing any
leftover uuids if not - this suite must never leave live data behind.

LIVE-WRITE SAFETY: every fixture in this file creates its own brand-new
project scoped to this test session. Nothing here ever writes into,
moves into, or otherwise touches a pre-existing project/area/heading -
see COMMON.md's "LIVE-WRITE SAFETY" rule.
"""
import os
import subprocess
import time
from datetime import datetime, timezone
from typing import List, Optional

import pytest

# Marker registration lives in pytest.ini/pyproject.toml (see hq-f0w.14).

SMOKE_PROJECT_PREFIX = "hq-f0w-smoke live "
_OSASCRIPT_PROBE_TIMEOUT_SECS = 5


def _things_running() -> bool:
    """Fast, non-launching probe for whether Things 3 is running.

    Mirrors things_mcp.doctor.check_things_running's probe
    (`application "Things3" is running`), which does not launch the app
    if it isn't already open.
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
    """Skip the whole tests/live directory unless opted in and Things is running."""
    skip_reason = None
    if os.environ.get("THINGS_MCP_LIVE_TESTS") != "1":
        skip_reason = (
            "live Things 3 smoke suite requires THINGS_MCP_LIVE_TESTS=1 "
            "(opt-in; writes to a real Things 3 database)"
        )
    elif not _things_running():
        skip_reason = (
            "Things 3 is not running - live smoke suite skipped rather than "
            "risk an auto-launch/hang"
        )

    if skip_reason is None:
        return

    skip_marker = pytest.mark.skip(reason=skip_reason)
    for item in items:
        if "tests/live" in str(item.fspath).replace(os.sep, "/"):
            item.add_marker(skip_marker)


@pytest.fixture(scope="session")
def live_things_tools():
    """A real ThingsTools backed by a real AppleScriptManager.

    Only constructed when the session actually needs it (i.e. inside the
    live suite, which is already gated by pytest_collection_modifyitems
    above), so importing this module never touches Things 3 at collection
    time.
    """
    from things_mcp.services.applescript_manager import AppleScriptManager
    from things_mcp.tools import ThingsTools

    manager = AppleScriptManager()
    return ThingsTools(manager)


@pytest.fixture(scope="session")
def has_auth_token(live_things_tools) -> bool:
    """Whether a Things URL-scheme auth token is configured for this run.

    Heading-move / checklist-on-existing-todo tests require the token
    (see AUTH_REQUIRING_ACTIONS); tests that need it should skip with a
    clear reason via this fixture rather than failing when it's absent.
    """
    return bool(live_things_tools.write_ops.applescript.auth_token)


class _SmokeSession:
    """Tracks every uuid created during the live session for teardown."""

    def __init__(self, project_id: str, project_name: str, heading_title: Optional[str]):
        self.project_id = project_id
        self.project_name = project_name
        self.heading_title = heading_title
        self.created_todo_ids: List[str] = []

    def track(self, todo_id: str) -> str:
        """Record a created todo/child id for teardown and return it unchanged."""
        if todo_id:
            self.created_todo_ids.append(todo_id)
        return todo_id


@pytest.fixture(scope="session")
def smoke_session(request, live_things_tools):
    """Creates ONE throwaway project for the whole live session and trashes
    it (and everything created inside it) on teardown - even on failure.

    Seeds one real heading via add_project's ``todos`` payload using the
    ``##Heading`` line syntax (hq-f0w.41): a ``##``-prefixed line now
    routes add_project through the Things URL scheme's ``json`` action
    (`_add_project_via_url_scheme` in scheduling/todo_operations.py),
    which is the only Things API able to create a real heading at
    project-creation time - the AppleScript build path
    (`_build_create_project_script`) still has no heading concept and
    would create a plain to-do literally titled "##Heading" instead. This
    is verified below by reading the project's children back via
    things.py; if no real heading was created (e.g. a live-environment
    regression), `smoke_session.heading_title` is left None so
    heading-dependent tests skip with a clear reason instead of silently
    testing against a project with no heading.
    """
    import things

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    project_name = f"{SMOKE_PROJECT_PREFIX}{ts}"
    heading_title = "Smoke Heading"

    import asyncio

    async def _create():
        return await live_things_tools.add_project(
            title=project_name,
            todos=f"##{heading_title}\nSmoke seed todo",
        )

    result = asyncio.run(_create())
    assert result.get("success"), f"Failed to create smoke project: {result}"
    project_id = result["project_id"]

    # Verify the heading was really created (rather than trusting
    # add_project's response blindly) via a fresh things.py read - this is
    # what lets heading-dependent tests un-skip automatically, and would
    # re-skip them with a clear reason if heading creation ever regresses.
    time.sleep(1)  # let Things settle before reading back via things.py
    headings = [
        t for t in things.tasks(project=project_id, type="heading") or []
        if t.get("title") == heading_title
    ]
    resolved_heading_title = heading_title if headings else None

    session = _SmokeSession(project_id, project_name, resolved_heading_title)

    # Track every to-do the seed payload actually produced (not just ones
    # matching an expected title - defensive in case a future Things
    # version's json-action heading placement changes), so teardown's
    # leftover-check covers every seed item
    # explicitly rather than relying solely on the project delete
    # cascading (which, per the review-round-2 finding above
    # _trash_and_verify's own docstring, does not actually cascade a
    # trashed flag onto children anyway).
    for t in things.tasks(project=project_id, type="to-do") or []:
        session.track(t["uuid"])

    def _teardown():
        _trash_and_verify(session)

    request.addfinalizer(_teardown)
    return session


def _trash_and_verify(session: _SmokeSession) -> None:
    """Trash every tracked todo id and the smoke project, then verify via
    things.py that nothing tracked remains outside the Trash. Raises
    (surfacing as a test error) listing any leftover uuids.

    Deleting the project does NOT cascade a trashed flag onto its children
    (measured live, hq-f0w.14 review round 2): a to-do left under the
    project at delete time can be orphaned - still `incomplete`, still
    pointing at the now-trashed project via things.py's `project` field,
    but never itself marked trashed. So before deleting anything, sweep
    every current child of the project (any type/status, not-yet-trashed)
    and union those uuids into the set to delete/verify - this catches
    seed/test items that were created but never explicitly tracked via
    session.track(), not just the ones already in created_todo_ids.

    Headings (hq-f0w.41 review): a heading seeded via add_project's
    ``##Heading`` lines (things:///json) is a real heading now, but
    Things' AppleScript dictionary has no heading class at all - there is
    no `delete`/`move` verb that can target one directly (confirmed live:
    every `heading id "..."` form errors). _delete_via_applescript is
    therefore skipped entirely for heading ids (it would only waste three
    failing osascript round-trips), and the leftover check treats a
    heading as cleaned up if its parent project (`things.get(id,
    trashed=None)['project']`) is itself trashed - the heading is not
    independently reachable as an active item once its project is in the
    Trash, even though things.py never sets a `trashed` flag on the
    heading record itself. Any other still-untrashed record (a genuine
    leftover) still fails this check as before.
    """
    import things

    child_ids = [
        t["uuid"]
        for t in things.tasks(project=session.project_id, type=None, status=None, trashed=None) or []
    ]

    all_ids = list(dict.fromkeys(session.created_todo_ids + child_ids + [session.project_id]))
    leftovers = []

    for item_id in all_ids:
        record = things.get(item_id, trashed=None)
        if record is not None and record.get("type") == "heading":
            # No AppleScript heading class - nothing to delete directly;
            # the heading is cleaned up once its parent project is
            # trashed (see leftover check below).
            continue
        _delete_via_applescript(item_id)

    # Give Things a moment to process the deletes before verifying.
    time.sleep(1)

    for item_id in all_ids:
        record = things.get(item_id, trashed=None)
        if record is None:
            # Not found at all (fully purged) counts as cleaned up.
            continue
        if record.get("trashed"):
            continue
        if record.get("type") == "heading":
            parent_project_id = record.get("project")
            parent = things.get(parent_project_id, trashed=None) if parent_project_id else None
            if parent is not None and parent.get("trashed"):
                # Heading has no independent trashed flag, but its parent
                # project is trashed - not reachable as an active item.
                continue
        leftovers.append(item_id)

    if leftovers:
        raise AssertionError(
            "Live smoke teardown failed to trash the following ids "
            f"(still present and NOT in Trash): {leftovers}"
        )


def _delete_via_applescript(item_id: str) -> None:
    """Delete a to-do/project by id via raw AppleScript `delete`.

    Tries `to do id` first (matching the existing delete_todo() write
    operation's own script), then falls back to `project id` if that
    fails. Measured live (hq-f0w.14): `to do id "<project-uuid>"`
    resolves fine for *reads* on a project, but `delete (to do id
    "<project-uuid>")` reliably errors with "Can't get to do id ..." -
    Things' AppleScript dictionary does NOT treat a project as a to-do
    subtype for `delete`, only `project id` works there. `delete_todo()`
    itself (tools_helpers/write_operations.py) has this same latent gap
    for project ids - noted as discovered work, out of scope here.
    Best-effort: failures are not raised here so the loop can continue
    attempting the rest of the ids; leftover verification in
    _trash_and_verify is the real safety net.
    """
    escaped = item_id.replace('"', '\\"')

    def _run(target_expr: str) -> bool:
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
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.TimeoutExpired, OSError):
            return False
        return result.returncode == 0 and result.stdout.strip() == "deleted"

    if _run(f'to do id "{escaped}"'):
        return
    if _run(f'project id "{escaped}"'):
        return

    # Last-resort fallback: `delete` can itself fail ("Can't get to do
    # id ...") for a to-do whose parent project has already been trashed
    # in this same teardown pass, even though the to-do is still fully
    # resolvable and enumerable via `to dos of project id "..."` at that
    # point (measured live, hq-f0w.14 review round 2 - the orphan this
    # uncovered, QJQBBaGVKdMv6dtr4K2PEi, was fixed this way). `move ...
    # to list "Trash"` succeeds where `delete` does not. The sweep in
    # _trash_and_verify already orders children before their parent
    # project to avoid triggering this in the first place; this is
    # defense-in-depth for any id this loop still could not place.
    move_script = (
        'tell application "Things3"\n'
        '    try\n'
        f'        set targetItem to to do id "{escaped}"\n'
        '        move targetItem to list "Trash"\n'
        '    end try\n'
        'end tell'
    )
    try:
        subprocess.run(
            ["osascript", "-e", move_script],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass
