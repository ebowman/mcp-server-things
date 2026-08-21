"""hq-gbl.6: list-tool membership regression against the deterministic seed
set (regression.seed).

For every (tool call, seed class) pair in ORACLE, asserts the seed class's
uuid is present in the tool's results if it's in that pair's 'must' set,
and absent if it's in 'must_not'. Classes not mentioned for a given tool
are not asserted on for that tool (deliberately - not every class is
relevant to every list).

Results are always read with mode='minimal', limit=500 (get_trash is
capped at 100 by its own schema - paged via offset instead), and paged via
offset for the tools that support it (search_todos, get_logbook,
get_trash) so a full page of the sandbox's own throwaway objects can never
hide a seed uuid.

Every entry in XFAILS documents one (tool_key, class_name, direction) pair
where live Things behavior contradicts the CLAUDE.md-derived expectation
encoded in ORACLE. _iter_pairs() emits those pairs as pytest.param(...,
marks=pytest.mark.xfail(strict=True, ...)) so the real assertion still
runs on every collected pair - an XFAILS entry that stops reproducing the
observed contradiction now XPASSes loudly (strict=True) instead of being
silently marked xfail forever without ever executing its assertion.
"""
from typing import Any, Dict, List, Optional, Set, Tuple

import pytest

from regression.seed import CLASS_NAMES

pytestmark = pytest.mark.live


# ---------------------------------------------------------------------------
# Tool-call registry: each entry describes how to invoke one tool call and
# collect the full set of uuids it returns (paging via offset where the
# tool supports it).
# ---------------------------------------------------------------------------


def _collect_minimal_uuids(
    mcp,
    tool: str,
    kwargs: Dict[str, Any],
    *,
    paged: bool = False,
    page_size: int = 500,
) -> Set[str]:
    """Call `tool` with mode='minimal' (tools that accept mode) and collect
    every uuid across all items, paging via offset when `paged` is True."""
    uuids: Set[str] = set()
    if not paged:
        result = mcp.call_sync(tool, **kwargs)
        items = result.get("items", []) if isinstance(result, dict) else []
        for item in items:
            if "uuid" in item:
                uuids.add(item["uuid"])
        return uuids

    offset = 0
    while True:
        result = mcp.call_sync(tool, offset=offset, **kwargs)
        items = result.get("items", []) if isinstance(result, dict) else []
        if not items:
            break
        for item in items:
            if "uuid" in item:
                uuids.add(item["uuid"])
        if len(items) < page_size:
            break
        offset += page_size
    return uuids


class ToolCall:
    """One (key, invocation) pair for the oracle: `key` identifies the pair
    in ORACLE/XFAILS; `fetch(mcp)` returns the full set of uuids visible
    through that call."""

    def __init__(self, key: str, fetch):
        self.key = key
        self.fetch = fetch

    def __repr__(self):
        return f"ToolCall({self.key!r})"


def _build_tool_calls(sandbox) -> List[ToolCall]:
    tag = sandbox.tag_name
    project_id = sandbox.project_id

    return [
        ToolCall("get_inbox", lambda mcp: _collect_minimal_uuids(
            mcp, "get_inbox", {"mode": "minimal", "limit": 500})),
        ToolCall("get_today", lambda mcp: _collect_minimal_uuids(
            mcp, "get_today", {"mode": "minimal", "limit": 500})),
        ToolCall("get_upcoming", lambda mcp: _collect_minimal_uuids(
            mcp, "get_upcoming", {"mode": "minimal", "limit": 500})),
        ToolCall("get_upcoming_days7", lambda mcp: _collect_minimal_uuids(
            mcp, "get_upcoming", {"mode": "minimal", "limit": 500, "days": 7})),
        ToolCall("get_anytime", lambda mcp: _collect_minimal_uuids(
            mcp, "get_anytime", {"mode": "minimal", "limit": 500})),
        ToolCall("get_someday", lambda mcp: _collect_minimal_uuids(
            mcp, "get_someday", {"mode": "minimal", "limit": 500})),
        ToolCall("get_logbook", lambda mcp: _collect_minimal_uuids(
            # get_logbook does not accept a `mode` parameter at all (always
            # 'standard' internally) - passing one is a FastMCP schema
            # validation error, not a Things behavior difference.
            mcp, "get_logbook", {"limit": 500, "period": "1d"},
            paged=True, page_size=500)),
        ToolCall("get_trash", lambda mcp: _collect_minimal_uuids(
            mcp, "get_trash", {"limit": 100},
            paged=True, page_size=100)),
        ToolCall("get_due_in_days7_overdueT", lambda mcp: _collect_minimal_uuids(
            mcp, "get_due_in_days", {"days": 7, "include_overdue": True})),
        ToolCall("get_due_in_days7_overdueF", lambda mcp: _collect_minimal_uuids(
            mcp, "get_due_in_days", {"days": 7, "include_overdue": False})),
        ToolCall("get_due_in_days30", lambda mcp: _collect_minimal_uuids(
            mcp, "get_due_in_days", {"days": 30})),
        ToolCall("get_due_in_days90", lambda mcp: _collect_minimal_uuids(
            mcp, "get_due_in_days", {"days": 90})),
        ToolCall("get_activating_in_days7", lambda mcp: _collect_minimal_uuids(
            mcp, "get_activating_in_days", {"days": 7})),
        ToolCall("get_activating_in_days30", lambda mcp: _collect_minimal_uuids(
            mcp, "get_activating_in_days", {"days": 30})),
        ToolCall("get_recent_1d", lambda mcp: _collect_minimal_uuids(
            mcp, "get_recent", {"period": "1d"})),
        ToolCall("search_todos", lambda mcp: _collect_minimal_uuids(
            mcp, "search_todos", {"mode": "minimal", "limit": 500, "query": "hq-gbl-reg seed"},
            paged=True, page_size=500)),
        ToolCall("get_tagged_items", lambda mcp: _collect_minimal_uuids(
            mcp, "get_tagged_items", {"tag": tag})),
        ToolCall("get_todos_project_incomplete", lambda mcp: _collect_minimal_uuids(
            mcp, "get_todos", {"mode": "minimal", "limit": 500,
                                "project_uuid": project_id, "status": "incomplete"})),
        ToolCall("get_todos_project_completed", lambda mcp: _collect_minimal_uuids(
            mcp, "get_todos", {"mode": "minimal", "limit": 500,
                                "project_uuid": project_id, "status": "completed"})),
        ToolCall("get_todos_project_canceled", lambda mcp: _collect_minimal_uuids(
            mcp, "get_todos", {"mode": "minimal", "limit": 500,
                                "project_uuid": project_id, "status": "canceled"})),
        ToolCall("get_todos_project_all", lambda mcp: _collect_minimal_uuids(
            mcp, "get_todos", {"mode": "minimal", "limit": 500,
                                "project_uuid": project_id, "status": None})),
    ]


# ---------------------------------------------------------------------------
# ORACLE: tool_key -> {"must": {class_name, ...}, "must_not": {class_name, ...}}
#
# Only classes actually asserted for a given tool are listed; a class absent
# from both 'must' and 'must_not' for a tool is not checked against that
# tool at all.
# ---------------------------------------------------------------------------

ALL_CLASSES: Set[str] = set(CLASS_NAMES)

# Synthetic pseudo-class for the sandbox project's own heading (not a seed
# to-do at all - resolved via sandbox.heading_id in test_seed_oracle_pair,
# not via seeded.uuid()). Included as an extra must_not row on every list/
# search tool call below: headings are never returned by any list tool
# (CLAUDE.md "List tools: headings never returned"), so the heading itself
# must never appear in any of these result sets either.
HEADING_CLASS = "__sandbox_heading__"

ORACLE: Dict[str, Dict[str, Set[str]]] = {
    "get_inbox": {
        # Only the dedicated 'inbox' class is created with no `when` and no
        # `list_id`/`list_title` (see seed.py) - every other class is
        # either explicitly scheduled or filed inside the sandbox project/
        # area/project-B. The sandbox heading itself must never appear
        # either (headings are never returned by any list tool).
        "must": {"inbox"},
        "must_not": (ALL_CLASSES - {"inbox"}) | {HEADING_CLASS},
    },
    "get_today": {
        "must": {"today", "evening", "overdue"},
        "must_not": {
            "inbox", "tomorrow", "plus5d", "plus40d", "someday",
            "deadline_plus3d", "deadline_plus20d", "deadline_plus60d",
            "completed", "canceled", "trashed", "in_area", "in_project_b",
            HEADING_CLASS,
        },
    },
    "get_upcoming": {
        # Native things.py Upcoming list: start_date in the future AND
        # start != 'Someday'. Deadline-only items (no `when`) are NOT
        # included here per things.upcoming()'s own docstring.
        "must": {"tomorrow", "plus5d", "plus40d", "activating_plus10d"},
        "must_not": {
            "inbox", "someday", "deadline_today", "deadline_plus3d",
            "deadline_plus20d", "deadline_plus60d", "overdue",
            "completed", "canceled", "trashed", HEADING_CLASS,
        },
    },
    "get_upcoming_days7": {
        # get_upcoming(days=7): due OR activating within the next 7 days
        # (today <= date <= today+7), based on deadline or start_date.
        "must": {"deadline_today", "deadline_plus3d", "overdue"},
        "must_not": {
            "inbox", "someday", "deadline_plus20d", "deadline_plus60d",
            "plus40d", "activating_plus10d",
            "completed", "canceled", "trashed", HEADING_CLASS,
        },
    },
    "get_anytime": {
        # things.anytime() matches start='Anytime' regardless of start_date,
        # so any in-project/in-area/in-project-B item created with no
        # explicit `when` (default start state - deadline-only/tag/
        # checklist/notes classes, plus in_area/in_project_b) lands here.
        # 'evening' (URL-scheme 'add' path) reliably lands here too -
        # confirmed live: start='Anytime', start_date == today. Plain
        # `when='today'` (AppleScript path, used for the 'today' seed
        # class) is fixed as of hq-x9z: it now uses `move theTodo to list
        # "Today"` instead of the `schedule` verb, which live-probing
        # confirmed also yields start='Anytime', start_date == today - so
        # 'today' is a normal (non-xfail) member of get_anytime, same as
        # the URL-scheme when='today' path.
        # Per CLAUDE.md, when='anytime' schedules into the Anytime list -
        # 'anytime_in_project' is documented here as such.
        "must": {
            "anytime_in_project", "under_heading", "in_area", "in_project_b",
            "evening", "today",
            "deadline_today", "deadline_plus3d", "deadline_plus20d",
            "deadline_plus60d", "overdue", "with_tag", "with_checklist",
            "with_multiline_notes",
        },
        "must_not": {
            "inbox", "someday", "trashed", "completed", "canceled",
            "tomorrow", "plus5d", "plus40d", "activating_plus10d",
            HEADING_CLASS,
        },
    },
    "get_someday": {
        # things.someday() = start_date=False, start='Someday' - a pure
        # "someday, no date" item. 'anytime_in_project' (when='anytime')
        # is documented as NOT belonging here per CLAUDE.md.
        "must": {"someday"},
        "must_not": (ALL_CLASSES - {"someday"}) | {HEADING_CLASS},
    },
    "get_logbook": {
        # includes both completed and canceled by default, sorted by stop
        # date - '1d' period comfortably covers this session.
        "must": {"completed", "canceled"},
        "must_not": {"inbox", "trashed", HEADING_CLASS} | (ALL_CLASSES - {
            "completed", "canceled", "inbox", "trashed",
        }),
    },
    "get_trash": {
        "must": {"trashed"},
        "must_not": (ALL_CLASSES - {"trashed"}) | {HEADING_CLASS},
    },
    "get_due_in_days7_overdueT": {
        "must": {"deadline_today", "deadline_plus3d", "overdue"},
        "must_not": {
            "deadline_plus20d", "deadline_plus60d", "inbox", "someday",
            "completed", "canceled", "trashed", HEADING_CLASS,
        },
    },
    "get_due_in_days7_overdueF": {
        "must": {"deadline_today", "deadline_plus3d"},
        "must_not": {
            "overdue", "deadline_plus20d", "deadline_plus60d", "inbox",
            "someday", "completed", "canceled", "trashed", HEADING_CLASS,
        },
    },
    "get_due_in_days30": {
        "must": {"deadline_today", "deadline_plus3d", "deadline_plus20d", "overdue"},
        "must_not": {
            "deadline_plus60d", "inbox", "someday", "completed", "canceled",
            "trashed", HEADING_CLASS,
        },
    },
    "get_due_in_days90": {
        "must": {
            "deadline_today", "deadline_plus3d", "deadline_plus20d",
            "deadline_plus60d", "overdue",
        },
        "must_not": {
            "inbox", "someday", "completed", "canceled", "trashed",
            HEADING_CLASS,
        },
    },
    "get_activating_in_days7": {
        # Forward window today <= start_date <= today+7, inclusive on both
        # ends (CLAUDE.md: "Boundary dates are inclusive on both ends").
        # 'today' has start_date == today (in-window, not "already active
        # in the past"); 'tomorrow' has start_date == today+1 (in-window).
        "must": {"today", "tomorrow"},
        "must_not": {
            "activating_plus10d", "inbox", "someday",
            "completed", "canceled", "trashed", HEADING_CLASS,
        },
    },
    "get_activating_in_days30": {
        "must": {"today", "tomorrow", "activating_plus10d"},
        "must_not": {
            "inbox", "someday", "completed", "canceled", "trashed",
            HEADING_CLASS,
        },
    },
    "get_recent_1d": {
        # All statuses, to-dos + projects, but trashed excluded by default
        # (things.tasks() default trashed=False) and headings excluded
        # (get_recent never includes headings unless type='heading' is
        # explicitly requested, which this call does not do).
        "must": ALL_CLASSES - {"trashed"},
        "must_not": {"trashed", HEADING_CLASS},
    },
    "search_todos": {
        # status='incomplete' default (search_todos), and things.todos()
        # always excludes trashed regardless of status - completed/
        # canceled/trashed must all be absent. things.todos() also never
        # returns heading rows (type='to-do' only).
        "must": ALL_CLASSES - {"completed", "canceled", "trashed"},
        "must_not": {"completed", "canceled", "trashed", HEADING_CLASS},
    },
    "get_tagged_items": {
        "must": {"with_tag"},
        "must_not": (ALL_CLASSES - {"with_tag"}) | {HEADING_CLASS},
    },
    "get_todos_project_incomplete": {
        # Every incomplete class filed directly in the sandbox project (or
        # under its heading) via list_id=sandbox.project_id in seed.py -
        # not area/project-B/inbox items, and not the heading itself
        # (things.todos() only returns type='to-do' rows).
        "must": {
            "today", "evening", "tomorrow", "plus5d", "plus40d",
            "anytime_in_project", "under_heading",
            "deadline_today", "deadline_plus3d", "deadline_plus20d",
            "deadline_plus60d", "overdue", "with_tag", "with_checklist",
            "with_multiline_notes", "activating_plus10d",
        },
        "must_not": {
            "inbox", "in_area", "in_project_b", "someday",
            "completed", "canceled", "trashed", HEADING_CLASS,
        },
    },
    "get_todos_project_completed": {
        "must": {"completed"},
        "must_not": (ALL_CLASSES - {"completed"}) | {HEADING_CLASS},
    },
    "get_todos_project_canceled": {
        "must": {"canceled"},
        "must_not": (ALL_CLASSES - {"canceled"}) | {HEADING_CLASS},
    },
    "get_todos_project_all": {
        # status=None: every status filed directly in the project (or
        # under its heading), still excluding trashed (things.todos()
        # always defaults trashed=False regardless of status) and the
        # heading row itself.
        "must": {
            "today", "evening", "tomorrow", "plus5d", "plus40d",
            "anytime_in_project", "under_heading",
            "deadline_today", "deadline_plus3d", "deadline_plus20d",
            "deadline_plus60d", "overdue", "with_tag", "with_checklist",
            "with_multiline_notes", "activating_plus10d",
            "completed", "canceled",
        },
        "must_not": {
            "inbox", "in_area", "in_project_b", "someday", "trashed",
            HEADING_CLASS,
        },
    },
}


# ---------------------------------------------------------------------------
# XFAILS: (tool_key, class_name, direction) -> observed-behavior reason.
# direction is 'must' or 'must_not', matching which ORACLE assertion is
# expected to fail against live Things behavior.
# ---------------------------------------------------------------------------

XFAILS: Dict[Tuple[str, str, str], str] = {
    # (empty) - hq-x9z fixed: when='today' now uses `move theTodo to list
    # "Today"` instead of the `schedule` verb, so it yields start='Anytime'
    # like the URL-scheme when='today' path and is a normal member of
    # get_anytime. No current XFAILS entries.
}


def _iter_pairs():
    """Yield (tool_key, class_name, direction) triples, or - for a pair
    listed in XFAILS - a pytest.param wrapping the same triple with a real
    pytest.mark.xfail(strict=True, ...) attached. The xfail marker lets the
    real assertion in test_seed_oracle_pair still execute (and XPASS
    loudly, strict=True, if the underlying bug is ever fixed) instead of
    the test bailing out via an imperative pytest.xfail() call before the
    assertion ever runs."""
    for tool_key, spec in ORACLE.items():
        for class_name in sorted(spec.get("must", ())):
            yield _pair_or_xfail_param(tool_key, class_name, "must")
        for class_name in sorted(spec.get("must_not", ())):
            yield _pair_or_xfail_param(tool_key, class_name, "must_not")


def _pair_or_xfail_param(tool_key: str, class_name: str, direction: str):
    triple = (tool_key, class_name, direction)
    reason = XFAILS.get(triple)
    if reason is None:
        return triple
    return pytest.param(
        *triple,
        marks=pytest.mark.xfail(strict=True, reason=f"observed: {reason}"),
    )


PAIR_IDS = [
    f"{tool_key}::{class_name}::{direction}"
    for tool_key, spec in ORACLE.items()
    for class_name, direction in (
        [(c, "must") for c in sorted(spec.get("must", ()))]
        + [(c, "must_not") for c in sorted(spec.get("must_not", ()))]
    )
]


@pytest.fixture(scope="module")
def tool_call_map(sandbox):
    return {tc.key: tc for tc in _build_tool_calls(sandbox)}


@pytest.fixture(scope="module")
def tool_result_cache():
    """Per-tool-key uuid-set cache, populated lazily so each distinct tool
    call happens exactly once per test session regardless of how many
    (tool, class) pairs reference it."""
    return {}


def _get_uuids(tool_key: str, tool_call_map, tool_result_cache, mcp) -> Set[str]:
    if tool_key not in tool_result_cache:
        tool_result_cache[tool_key] = tool_call_map[tool_key].fetch(mcp)
    return tool_result_cache[tool_key]


@pytest.mark.parametrize("tool_key,class_name,direction", _iter_pairs(), ids=PAIR_IDS)
def test_seed_oracle_pair(
    tool_key, class_name, direction, mcp, sandbox, seeded, tool_call_map, tool_result_cache
):
    # XFAILS pairs already carry a real pytest.mark.xfail(strict=True, ...)
    # from _pair_or_xfail_param() (see _iter_pairs) - the assertion below
    # always runs for every pair, xfail or not.
    if class_name == HEADING_CLASS:
        todo_id = sandbox.heading_id
        if todo_id is None:
            pytest.skip("sandbox.heading_id is None (heading not confirmed)")
    else:
        todo_id = seeded.uuid(class_name)
        if todo_id is None:
            skip_reason = seeded.skipped.get(class_name)
            pytest.skip(skip_reason or f"seed class {class_name!r} was not created")

    uuids = _get_uuids(tool_key, tool_call_map, tool_result_cache, mcp)

    if direction == "must":
        assert todo_id in uuids, (
            f"{tool_key}: expected seed class {class_name!r} (uuid {todo_id}) "
            f"to be present, but it was not in the {len(uuids)} returned uuids"
        )
    else:
        assert todo_id not in uuids, (
            f"{tool_key}: expected seed class {class_name!r} (uuid {todo_id}) "
            f"to be ABSENT, but it was found"
        )


def test_all_classes_covered_by_seed():
    """Sanity check: CLASS_NAMES and ALL_CLASSES agree (guards against a
    typo silently excluding a class from every oracle assertion)."""
    assert ALL_CLASSES == set(CLASS_NAMES)
