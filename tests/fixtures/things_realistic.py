"""Realistic things.py fixture data + factory helpers (hq-f0w.10).

Why: tests that patch `things_mcp.tools_helpers.read_operations.things.*`
(anytime/someday/today/upcoming/inbox/todos) previously mocked tame,
to-do-only dicts with no `type`/`heading`/`heading_title` keys and no
punctuation in titles/notes - so a project/heading leak (GH#9) or a dropped
field in convert_todo would be invisible: the mock data simply couldn't
exercise those code paths.

Real key sets (captured live via things.py, 2026-08-19 - see also
tests/unit/test_converters.py header for the original capture notes):

    things.todos()[0].keys()             -> created, deadline, index,
        modified, notes, start, start_date, status, stop_date, tags, title,
        today_index, type, uuid   (+ optional: heading, heading_title,
        project, project_title, checklist, reminder_time [live: 8/1699
        todos carry reminder_time, e.g. '09:00'])
    things.projects()[0].keys()          -> created, deadline, index,
        modified, notes, start, start_date, status, stop_date, title,
        today_index, type, uuid   (+ optional: area, area_title, tags
        [live: 5/67 projects carry a tags list], reminder_time [live:
        8/67 projects carry reminder_time, e.g. '09:00'])
    things.tasks(type='heading')[0].keys() -> created, deadline, index,
        modified, notes, project, project_title, start, start_date, status,
        stop_date, title, today_index, type, uuid
    things.areas()[0].keys()             -> title, type, uuid  (NEVER 'tags')
    things.tags()[0].keys()              -> shortcut, title, type, uuid

Real to-do/project/heading rows never carry separate
'completion_date'/'cancellation_date' keys - only 'stop_date',
disambiguated by 'status'. 'checklist' (when present on a to-do row) is a
bool "has a checklist" flag, not a list of items. Real heading-children
(to-dos with a 'heading' key) never also carry 'project'/'project_title' at
the things.py row level (live: 0/40 heading-children have a project key) - a
heading's own 'project'/'project_title' identify its parent project, but the
child to-do row itself is not separately stamped with that project.
ReadOperations backfills project/projectTitle for these rows in a
post-conversion pass (_fill_project_from_heading, hq-f0w.24), so the raw
fixture rows below intentionally omit project/project_title (matching real
things.py), while the MCP-layer converted output for a heading-child todo
does carry them once resolved.

Use the factory helpers (make_todo/make_project/make_heading/make_area/
make_tag) to build realistic rows for ad-hoc test data, or the canned
REALISTIC_MIXED_LIST / REALISTIC_* constants below for drop-in replacement
of tame mocks at the six things.* list call sites
(anytime/someday/today/upcoming/inbox/todos).
"""

from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def make_todo(
    uuid: str,
    title: str,
    *,
    status: str = "incomplete",
    start: str = "Anytime",
    notes: str = "",
    tags: Optional[List[str]] = None,
    heading: Optional[str] = None,
    heading_title: Optional[str] = None,
    project: Optional[str] = None,
    project_title: Optional[str] = None,
    checklist: Optional[bool] = None,
    start_date: Optional[str] = None,
    deadline: Optional[str] = None,
    stop_date: Optional[str] = None,
    reminder_time: Optional[str] = None,
    created: str = "2026-01-01 09:00:00",
    modified: str = "2026-01-01 09:00:00",
    index: int = 0,
    today_index: int = 0,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a realistic things.py to-do row.

    Mirrors the real key set exactly: always includes created/deadline/
    index/modified/notes/start/start_date/status/stop_date/title/
    today_index/type/uuid; heading/heading_title/project/project_title/
    checklist/tags/reminder_time are only included when a value is
    supplied, matching things.py's own behaviour of omitting keys that
    don't apply to a row (e.g. a todo with no tags has no 'tags' key at
    all). reminder_time is a real but rare optional key (live: 8/1699
    todos carry it, e.g. '09:00') - do not set it by default.
    """
    row: Dict[str, Any] = {
        "uuid": uuid,
        "type": "to-do",
        "title": title,
        "status": status,
        "notes": notes,
        "start": start,
        "start_date": start_date,
        "deadline": deadline,
        "stop_date": stop_date,
        "created": created,
        "modified": modified,
        "index": index,
        "today_index": today_index,
    }
    if tags is not None:
        row["tags"] = tags
    if heading is not None:
        row["heading"] = heading
    if heading_title is not None:
        row["heading_title"] = heading_title
    if project is not None:
        row["project"] = project
    if project_title is not None:
        row["project_title"] = project_title
    if checklist is not None:
        row["checklist"] = checklist
    if reminder_time is not None:
        row["reminder_time"] = reminder_time
    row.update(extra)
    return row


def make_project(
    uuid: str,
    title: str,
    *,
    status: str = "incomplete",
    start: str = "Anytime",
    notes: str = "",
    area: Optional[str] = None,
    area_title: Optional[str] = None,
    tags: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    deadline: Optional[str] = None,
    stop_date: Optional[str] = None,
    reminder_time: Optional[str] = None,
    created: str = "2026-01-01 09:00:00",
    modified: str = "2026-01-01 09:00:00",
    index: int = 0,
    today_index: int = 0,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a realistic things.py project row.

    area/area_title/tags/reminder_time are only included when a value is
    supplied, matching things.py's own behaviour of omitting keys that
    don't apply to a row. tags is a real but uncommon optional key on
    projects (live: 5/67 projects carry a tags list) - do not set it by
    default. reminder_time is likewise real but rare (live: 8/67 projects
    carry it, e.g. '09:00').
    """
    row: Dict[str, Any] = {
        "uuid": uuid,
        "type": "project",
        "title": title,
        "status": status,
        "notes": notes,
        "start": start,
        "start_date": start_date,
        "deadline": deadline,
        "stop_date": stop_date,
        "created": created,
        "modified": modified,
        "index": index,
        "today_index": today_index,
    }
    if area is not None:
        row["area"] = area
    if area_title is not None:
        row["area_title"] = area_title
    if tags is not None:
        row["tags"] = tags
    if reminder_time is not None:
        row["reminder_time"] = reminder_time
    row.update(extra)
    return row


def make_heading(
    uuid: str,
    title: str,
    *,
    project: str,
    project_title: str,
    status: str = "incomplete",
    start: str = "Anytime",
    notes: str = "",
    start_date: Optional[str] = None,
    deadline: Optional[str] = None,
    stop_date: Optional[str] = None,
    created: str = "2026-01-01 09:00:00",
    modified: str = "2026-01-01 09:00:00",
    index: int = 0,
    today_index: int = 0,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a realistic things.py heading row (things.tasks(type='heading'))."""
    row: Dict[str, Any] = {
        "uuid": uuid,
        "type": "heading",
        "title": title,
        "status": status,
        "notes": notes,
        "project": project,
        "project_title": project_title,
        "start": start,
        "start_date": start_date,
        "deadline": deadline,
        "stop_date": stop_date,
        "created": created,
        "modified": modified,
        "index": index,
        "today_index": today_index,
    }
    row.update(extra)
    return row


def make_area(uuid: str, title: str, **extra: Any) -> Dict[str, Any]:
    """Build a realistic things.py area row.

    Real areas never carry a 'tags' key (verified live, 4/4 areas including
    include_items=True) - do not add one here.
    """
    row: Dict[str, Any] = {"uuid": uuid, "type": "area", "title": title}
    row.update(extra)
    return row


def make_tag(uuid: str, title: str, *, shortcut: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    """Build a realistic things.py tag row."""
    row: Dict[str, Any] = {"uuid": uuid, "type": "tag", "title": title, "shortcut": shortcut}
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# Canned realistic dataset
# ---------------------------------------------------------------------------

# A Someday project with child tasks (both a direct child and one under a
# heading), used to exercise the Someday-project-inheritance filtering.
SOMEDAY_PROJECT = make_project(
    "proj-someday-1",
    "Q4 Roadmap: “Big Bets”, Redux",
    start="Someday",
)

ANYTIME_PROJECT = make_project(
    "proj-anytime-1",
    "Kitchen Remodel, Phase 2",
    area="area-1",
    area_title="Home",
)

HEADING_IN_SOMEDAY_PROJECT = make_heading(
    "heading-someday-1",
    "Research",
    project=SOMEDAY_PROJECT["uuid"],
    project_title=SOMEDAY_PROJECT["title"],
)

HEADING_IN_ANYTIME_PROJECT = make_heading(
    "heading-anytime-1",
    'Cabinets & "Hardware"',
    project=ANYTIME_PROJECT["uuid"],
    project_title=ANYTIME_PROJECT["title"],
)

# To-dos with and without heading/heading_title.
TODO_PLAIN = make_todo(
    "todo-plain-1",
    "Buy milk, eggs, and bread",
    tags=["errands"],
)

TODO_NO_TAGS = make_todo(
    "todo-no-tags-1",
    "File taxes",
    status="incomplete",
    # No tags key at all - matches real things.py behaviour for untagged rows.
)

# Real heading-children never also carry project/project_title at the raw
# things.py row level (live: 0/40 heading-children have a project key) -
# only heading/heading_title identify the parent chain for this row.
# ReadOperations._fill_project_from_heading() backfills project/projectTitle
# onto the *converted* MCP output for rows like this one (hq-f0w.24) by
# resolving HEADING_IN_ANYTIME_PROJECT's project/project_title.
TODO_UNDER_HEADING = make_todo(
    "todo-heading-1",
    "Pick a color: blue, green, or ‘slate’",
    heading=HEADING_IN_ANYTIME_PROJECT["uuid"],
    heading_title=HEADING_IN_ANYTIME_PROJECT["title"],
    tags=["home", "urgent"],
)

TODO_DIRECT_IN_SOMEDAY_PROJECT = make_todo(
    "todo-someday-direct-1",
    "Scope out vendors",
    project=SOMEDAY_PROJECT["uuid"],
    project_title=SOMEDAY_PROJECT["title"],
)

TODO_UNDER_HEADING_IN_SOMEDAY_PROJECT = make_todo(
    "todo-someday-heading-1",
    "Draft brief",
    heading=HEADING_IN_SOMEDAY_PROJECT["uuid"],
    heading_title=HEADING_IN_SOMEDAY_PROJECT["title"],
)

TODO_WITH_CHECKLIST = make_todo(
    "todo-checklist-1",
    "Release v2.0: run tests, update docs, tag",
    checklist=True,
    notes="Pre-release checklist:\n\n1. Run full suite\n2. Update CHANGELOG",
    tags=["release"],
)

TODO_WITH_COMMAS_QUOTES_COLONS = make_todo(
    "todo-punctuation-1",
    'Ship "v1.7.0": tags, notes, and colons — a test, of sorts',
    notes='Quote test: "curly" vs “curly” vs \'straight\'.\n\nSecond paragraph, with a comma.',
    tags=["release,notes"],
)

TODO_COMPLETED = make_todo(
    "todo-completed-1",
    "Renew passport",
    status="completed",
    stop_date="2026-06-01 12:00:00",
    tags=["admin"],
)

TODO_CANCELED = make_todo(
    "todo-canceled-1",
    "Old idea, abandoned",
    status="canceled",
    stop_date="2026-05-15 08:30:00",
)

TODO_WITH_DEADLINE = make_todo(
    "todo-deadline-1",
    "Submit expense report",
    deadline="2026-09-01",
    start_date="2026-08-01",
    tags=["finance"],
)

HEADING_STANDALONE = HEADING_IN_ANYTIME_PROJECT

# A mixed list of to-do / project / heading rows - the shape every one of
# the five list functions (things.anytime/someday/today/upcoming/inbox)
# actually returns from the live API (before this server's type='to-do'
# query-level filtering / post-hoc filtering is applied). Any test that
# mocks one of these functions with only to-do dicts cannot exercise the
# project/heading exclusion logic - use this instead.
REALISTIC_MIXED_LIST: List[Dict[str, Any]] = [
    TODO_PLAIN,
    TODO_NO_TAGS,
    TODO_UNDER_HEADING,
    TODO_WITH_CHECKLIST,
    TODO_WITH_COMMAS_QUOTES_COLONS,
    TODO_WITH_DEADLINE,
    ANYTIME_PROJECT,
    SOMEDAY_PROJECT,
    HEADING_IN_ANYTIME_PROJECT,
]

# To-do-only realistic list (still carries type/heading/notes punctuation
# variety) for call sites that only ever expect to-dos back (e.g. after
# type='to-do' filtering has already been applied at the things.py call).
REALISTIC_TODOS_ONLY: List[Dict[str, Any]] = [
    TODO_PLAIN,
    TODO_NO_TAGS,
    TODO_UNDER_HEADING,
    TODO_WITH_CHECKLIST,
    TODO_WITH_COMMAS_QUOTES_COLONS,
    TODO_WITH_DEADLINE,
    TODO_COMPLETED,
    TODO_CANCELED,
]

REALISTIC_PROJECTS: List[Dict[str, Any]] = [ANYTIME_PROJECT, SOMEDAY_PROJECT]

REALISTIC_HEADINGS: List[Dict[str, Any]] = [
    HEADING_IN_ANYTIME_PROJECT,
    HEADING_IN_SOMEDAY_PROJECT,
]

REALISTIC_AREAS: List[Dict[str, Any]] = [
    make_area("area-1", "Home"),
    make_area("area-2", 'Work: "Acme, Inc."'),
]

REALISTIC_TAGS: List[Dict[str, Any]] = [
    make_tag("tag-1", "errands"),
    make_tag("tag-2", "urgent", shortcut="u"),
]
