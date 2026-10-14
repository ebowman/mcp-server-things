"""Shared, leak-proof cleanup primitives for the opt-in live suites (hq-8vx).

Used by tests/regression/conftest.py and tests/live/conftest.py.

Design rules (see docs/TESTING.md "Teardown, sweep and Trash hygiene"):
  - Deletions are BATCHED: one osascript invocation per kind (to-dos, then
    projects, then areas) per <= BATCH_SIZE ids, with a per-id `try` inside
    the script. A 15s-per-item loop over hundreds of items is what blew the
    300s pytest-timeout in the past.
  - Everything runs under an overall wall-clock budget (`Budget`), and
    whatever could not be deleted is logged to stderr rather than raised.
  - The callers run this from `pytest_sessionfinish` (NOT a fixture
    finalizer): pytest-timeout's per-test timer covers setup+call+teardown of
    each item, so a session-fixture finalizer executes inside the LAST test's
    timer and can be killed mid-cleanup. sessionfinish runs after every item
    protocol has ended, outside any timer.
  - Only items whose title starts with the suite-owned prefix (and the
    children of such projects/areas) are ever swept. Trashed items are never
    touched; the Trash is only emptied on explicit opt-in
    (THINGS_MCP_LIVE_EMPTY_TRASH=1).
"""
import os
import subprocess
import sys
import time
from typing import Dict, Iterable, List, Sequence, Tuple

BATCH_SIZE = 50
DEFAULT_BUDGET_SECS = 240.0
_BATCH_TIMEOUT_SECS = 90


def log(msg: str) -> None:
    print(f"[suite-cleanup] {msg}", file=sys.stderr, flush=True)


class Budget:
    """Overall wall-clock budget for a cleanup phase."""

    def __init__(self, secs: float = DEFAULT_BUDGET_SECS):
        self.deadline = time.monotonic() + secs

    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def expired(self) -> bool:
        return self.remaining() <= 0


def _q(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _batch_script(kind: str, ids: Sequence[str]) -> str:
    """AppleScript deleting `ids` of `kind` ('todo'|'project'|'area').

    Returns the ids it could NOT delete, newline-separated (empty string if
    all went through). To-dos fall back to `move ... to list "Trash"` for the
    "Can't get to do id" orphan case (parent project already trashed).
    """
    id_list = ", ".join(f'"{_q(i)}"' for i in ids)
    if kind == "todo":
        body = '''
                try
                    delete (to do id theId)
                on error
                    try
                        move (to do id theId) to list "Trash"
                    on error
                        set failed to failed & theId & linefeed
                    end try
                end try'''
    elif kind == "project":
        body = '''
                try
                    delete (project id theId)
                on error
                    set failed to failed & theId & linefeed
                end try'''
    elif kind == "area":
        body = '''
                try
                    delete (area id theId)
                on error
                    set failed to failed & theId & linefeed
                end try'''
    else:
        raise ValueError(kind)
    return f'''
    tell application "Things3"
        set failed to ""
        repeat with anId in {{{id_list}}}
            set theId to contents of anId
            {body}
        end repeat
        return failed
    end tell
    '''


def delete_batch(kind: str, ids: Iterable[str], budget: Budget) -> Tuple[int, List[str]]:
    """Delete ids of one kind, batched. Returns (deleted_count, undeleted_ids)."""
    ids = [i for i in dict.fromkeys(ids) if i]
    deleted = 0
    undeleted: List[str] = []
    for start in range(0, len(ids), BATCH_SIZE):
        chunk = ids[start:start + BATCH_SIZE]
        if budget.expired():
            undeleted.extend(chunk)
            continue
        timeout = max(5.0, min(_BATCH_TIMEOUT_SECS, budget.remaining()))
        try:
            result = subprocess.run(
                ["osascript", "-e", _batch_script(kind, chunk)],
                capture_output=True, text=True, timeout=timeout,
            )
        except (subprocess.TimeoutExpired, OSError) as e:
            log(f"{kind} batch of {len(chunk)} failed/timed out: {e}")
            undeleted.extend(chunk)
            continue
        if result.returncode != 0:
            log(f"{kind} batch error: {result.stderr.strip()[:200]}")
            undeleted.extend(chunk)
            continue
        failed = [x.strip() for x in result.stdout.splitlines() if x.strip()]
        undeleted.extend(failed)
        deleted += len(chunk) - len(failed)
    return deleted, undeleted


def delete_all(todo_ids: Iterable[str], project_ids: Iterable[str],
               area_ids: Iterable[str], budget: Budget) -> Dict[str, Tuple[int, List[str]]]:
    """to-dos first, then projects, then areas (area delete purges the area and
    trashes its projects but NOT their to-dos)."""
    out = {}
    out["todos"] = delete_batch("todo", todo_ids, budget)
    out["projects"] = delete_batch("project", project_ids, budget)
    out["areas"] = delete_batch("area", area_ids, budget)
    for kind, (_n, left) in out.items():
        if left:
            log(f"NOT DELETED {kind} ({len(left)}): {left}")
    return out


MIN_PREFIX_LEN = 8
MAX_SWEEP_CANDIDATES = 500

# Loud failures recorded by sweeps (e.g. cap exceeded); the conftests'
# pytest_sessionfinish folds these into the session's failure status.
FAILURES: List[str] = []


def select_sweep_targets(prefix: str) -> Tuple[List[str], List[str], List[str]]:
    """Return (todo_ids, project_ids, area_ids) selected for `prefix` via
    things.py reads (read-only): active to-dos/projects/areas titled with the
    prefix, plus ALL children of prefixed projects (incl. under headings) and
    of prefixed areas (their to-dos AND their projects, and those projects'
    to-dos even if the project title is not prefixed). Contents of a
    non-prefixed area are never selected (unless individually prefixed)."""
    import things

    projects: Dict[str, None] = {}
    for p in things.projects(status=None) or []:
        if (p.get("title") or "").startswith(prefix):
            projects[p["uuid"]] = None
    areas = [
        a["uuid"] for a in things.areas() or []
        if (a.get("title") or "").startswith(prefix)
    ]
    todo_ids: Dict[str, None] = {}
    for t in things.todos(status=None) or []:
        if (t.get("title") or "").startswith(prefix):
            todo_ids[t["uuid"]] = None
    for area_id in areas:
        for t in things.todos(area=area_id, status=None) or []:
            todo_ids[t["uuid"]] = None
        for p in things.projects(area=area_id, status=None) or []:
            projects[p["uuid"]] = None
    for project_id in list(projects):
        for t in things.tasks(project=project_id, type=None, status=None) or []:
            if t.get("type") == "heading":
                for c in things.tasks(heading=t["uuid"], type=None, status=None) or []:
                    todo_ids[c["uuid"]] = None
            else:
                todo_ids[t["uuid"]] = None
    return list(todo_ids), list(projects), areas


def sweep_prefix(prefix: str, label: str, budget: Budget) -> Dict[str, int]:
    """Delete every ACTIVE (non-trashed, any status) item selected by
    `select_sweep_targets`, regardless of age. Reports counts on stderr.

    Safety: raises ValueError unless `prefix` is a str of >= MIN_PREFIX_LEN
    non-blank chars (an empty prefix would select the whole database), and
    deletes NOTHING (logs loudly, records a FAILURES entry) if the candidate
    count exceeds MAX_SWEEP_CANDIDATES.
    """
    if not isinstance(prefix, str) or len(prefix.strip()) < MIN_PREFIX_LEN:
        raise ValueError(
            f"refusing to sweep: prefix {prefix!r} must be a string of at least "
            f"{MIN_PREFIX_LEN} non-blank characters")
    counts = {"todos": 0, "projects": 0, "areas": 0}
    try:
        todo_ids, project_ids, area_ids = select_sweep_targets(prefix)
    except Exception as e:  # reads unavailable: never fail the suite from here
        log(f"{label} sweep skipped (things.py read failed): {e!r}")
        return counts

    total = len(todo_ids) + len(project_ids) + len(area_ids)
    if total > MAX_SWEEP_CANDIDATES:
        msg = (f"{label} sweep ABORTED, deleted NOTHING: prefix {prefix!r} matched "
               f"{total} items ({len(todo_ids)} to-dos / {len(project_ids)} projects / "
               f"{len(area_ids)} areas) > cap {MAX_SWEEP_CANDIDATES}")
        log("!!! " + msg)
        FAILURES.append(msg)
        return counts

    res = delete_all(todo_ids, project_ids, area_ids, budget)
    counts = {k: v[0] for k, v in res.items()}
    log(f"{label} sweep of prefix {prefix!r}: found {len(todo_ids)} to-dos / "
        f"{len(project_ids)} projects / {len(area_ids)} areas; deleted "
        f"{counts['todos']} / {counts['projects']} / {counts['areas']}")
    return counts


def maybe_empty_trash() -> None:
    """Opt-in (THINGS_MCP_LIVE_EMPTY_TRASH=1): ask Things to empty the Trash.

    Asynchronous - Things purges in the background; we do not block on it.
    """
    if os.environ.get("THINGS_MCP_LIVE_EMPTY_TRASH") != "1":
        return
    try:
        subprocess.run(
            ["osascript", "-e", 'tell application "Things3" to empty trash'],
            capture_output=True, text=True, timeout=30,
        )
        log("THINGS_MCP_LIVE_EMPTY_TRASH=1: empty trash requested (Things purges asynchronously)")
    except (subprocess.TimeoutExpired, OSError) as e:
        log(f"empty trash request failed: {e}")
