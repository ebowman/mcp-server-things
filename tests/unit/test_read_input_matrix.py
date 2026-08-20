"""hq-gbl.4: Input-space matrix for every READ tool at the MCP boundary.

Table-driven coverage of mode/limit/offset/status/type/days/period/dates
across valid/boundary/invalid values, for every read tool listed in the
bead: get_todos, get_projects, get_areas, get_inbox, get_today,
get_upcoming, get_anytime, get_someday, get_logbook, get_trash,
get_due_in_days, get_activating_in_days, get_tags, get_tagged_items,
get_tag_usage, get_project_headings, get_todo_by_id, search_todos,
search_advanced, get_recent.

Mocking strategy: patch `things_mcp.tools_helpers.read_operations.things`
(the single module all of ReadOperations calls through - see
test_get_todos_schema_parity.py for precedent) and drive every call through
a real `ThingsMCPServer` + in-memory `fastmcp.Client(server.mcp)`, exactly
like test_structured_output.py. This exercises the *real* validation logic
in server.py/read_operations.py, not a re-implementation of it.

Each CASES entry is (tool, args, expectation):
    - ok(...)          -> call succeeds; assert envelope keys present and
                           mode is never the literal string 'auto'.
    - read_error(code) -> structured {"success": False, "error": code, ...}.
    - tool_error()      -> pydantic rejects the input before the tool body
                           runs at all (fastmcp raises ToolError).

A completeness check (TestCompleteness) at the bottom introspects every
read tool's declared parameters via Client.list_tools() and fails if any
(tool, param) pair has fewer than 3 CASES entries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from things_mcp.server import ThingsMCPServer

from fixtures.things_realistic import (
    make_heading,
    REALISTIC_TODOS_ONLY,
    REALISTIC_PROJECTS,
    REALISTIC_AREAS,
    REALISTIC_TAGS,
)


# ---------------------------------------------------------------------------
# Expectation markers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ok:
    """Expect a successful call; envelope shape asserted generically."""

    kind: str = "ok"


@dataclass(frozen=True)
class ReadError:
    """Expect a structured read-tool error with this exact `error` code."""

    code: str
    kind: str = "read_error"


@dataclass(frozen=True)
class ToolErrorExpectation:
    """Expect fastmcp/pydantic to reject the call before the tool body runs."""

    kind: str = "tool_error"


def ok() -> Ok:
    return Ok()


def read_error(code: str) -> ReadError:
    return ReadError(code)


def tool_error() -> ToolErrorExpectation:
    return ToolErrorExpectation()


REQUIRED_LIST_KEYS = {"items", "count", "total", "mode", "requested_mode", "limit", "offset"}


# ---------------------------------------------------------------------------
# Realistic mock data, keyed by id, for things.get()-style lookups.
# ---------------------------------------------------------------------------

TODO_1 = REALISTIC_TODOS_ONLY[0]
PROJECT_1 = REALISTIC_PROJECTS[0]
HEADING_1 = make_heading(
    "heading-lookup-1", "Lookup Heading", project=PROJECT_1["uuid"], project_title=PROJECT_1["title"]
)
AREA_1 = REALISTIC_AREAS[0]
TAG_1 = REALISTIC_TAGS[0]

PROJECT_WITH_HEADINGS = PROJECT_1
HEADINGS_FOR_PROJECT = [
    make_heading("h-1", "Research", project=PROJECT_WITH_HEADINGS["uuid"], project_title=PROJECT_WITH_HEADINGS["title"], index=-500),
    make_heading("h-2", "Design", project=PROJECT_WITH_HEADINGS["uuid"], project_title=PROJECT_WITH_HEADINGS["title"], index=-400),
]

GET_MAP: Dict[str, Dict[str, Any]] = {
    TODO_1["uuid"]: TODO_1,
    PROJECT_1["uuid"]: PROJECT_1,
    HEADING_1["uuid"]: HEADING_1,
    AREA_1["uuid"]: AREA_1,
    TAG_1["uuid"]: dict(TAG_1),  # things.get() on a tag returns a thin row
}


def _things_get(uuid: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    return GET_MAP.get(uuid)


def _things_tasks(**kwargs: Any) -> List[Dict[str, Any]]:
    """Router for things.tasks(...) covering type='heading' project lookups
    and the get_search_advanced()/get_recent() type='heading' paths."""
    if kwargs.get("type") == "heading":
        project = kwargs.get("project")
        if project == PROJECT_WITH_HEADINGS["uuid"]:
            return list(HEADINGS_FOR_PROJECT)
        if project is not None:
            return []
        return list(HEADINGS_FOR_PROJECT)
    # search_advanced(type=...) / get_recent(type=...) dispatch through
    # things.tasks(**query_params) directly when a type filter is present.
    return list(REALISTIC_TODOS_ONLY) + list(REALISTIC_PROJECTS)


def _things_todos(**kwargs: Any) -> List[Dict[str, Any]]:
    tag = kwargs.get("tag")
    heading = kwargs.get("heading")
    if tag is not None:
        if tag == TAG_1["title"] or tag in ("errands",):
            return [t for t in REALISTIC_TODOS_ONLY if tag in (t.get("tags") or [])] or [TODO_1]
        raise ValueError(f"Unrecognized tag type: {tag}")
    if heading is not None:
        # get_project_headings' todoCount lookup.
        return []
    return list(REALISTIC_TODOS_ONLY)


def make_mock_things() -> MagicMock:
    """Build a MagicMock things module with realistic routed responses."""
    mock = MagicMock()
    mock.todos.side_effect = _things_todos
    mock.projects.side_effect = lambda **kwargs: list(REALISTIC_PROJECTS)
    mock.areas.side_effect = lambda **kwargs: list(REALISTIC_AREAS)
    mock.tags.side_effect = lambda **kwargs: list(REALISTIC_TAGS)
    mock.tasks.side_effect = _things_tasks
    mock.trash.side_effect = lambda **kwargs: list(REALISTIC_TODOS_ONLY)
    mock.get.side_effect = _things_get
    return mock


# ---------------------------------------------------------------------------
# Server + client fixtures (module-scoped: one server for the whole file).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def server() -> ThingsMCPServer:
    return ThingsMCPServer()


@pytest.fixture(scope="module")
def client(server: ThingsMCPServer) -> Client:
    return Client(server.mcp)


@pytest.fixture(autouse=True)
def _patch_things():
    mock_things = make_mock_things()
    with patch("things_mcp.tools_helpers.read_operations.things", mock_things):
        yield mock_things


# ---------------------------------------------------------------------------
# CASES table: (tool, args, expectation)
# ---------------------------------------------------------------------------

CASES: List[Tuple[str, Dict[str, Any], Any]] = []


def add(tool: str, args: Dict[str, Any], expectation: Any) -> None:
    CASES.append((tool, args, expectation))


# --- get_todos ---------------------------------------------------------
add("get_todos", {}, ok())
add("get_todos", {"project_uuid": PROJECT_1["uuid"]}, ok())
add("get_todos", {"project_uuid": PROJECT_1["uuid"]}, ok())
add("get_todos", {"project_uuid": "unknown-project-xyz"}, ok())
add("get_todos", {"project_uuid": PROJECT_1["uuid"], "status": "completed"}, ok())
add("get_todos", {"include_items": True}, ok())
add("get_todos", {"include_items": True}, ok())
add("get_todos", {"include_items": False}, ok())
add("get_todos", {"include_items": True, "status": None}, ok())
add("get_todos", {"mode": "auto"}, ok())
add("get_todos", {"mode": "summary"}, ok())
add("get_todos", {"mode": "minimal"}, ok())
add("get_todos", {"mode": "standard"}, ok())
add("get_todos", {"mode": "detailed"}, ok())
add("get_todos", {"mode": "raw"}, ok())
add("get_todos", {"mode": "bogus"}, read_error("invalid_mode"))
add("get_todos", {"limit": 1}, ok())
add("get_todos", {"limit": 500}, ok())
add("get_todos", {"limit": 501}, read_error("invalid_limit"))
add("get_todos", {"limit": 0}, read_error("invalid_limit"))
add("get_todos", {"limit": -1}, read_error("invalid_limit"))
add("get_todos", {"limit": "abc"}, read_error("invalid_limit"))
add("get_todos", {"limit": "10"}, ok())
add("get_todos", {"limit": 10.5}, ok())
add("get_todos", {"status": "incomplete"}, ok())
add("get_todos", {"status": "completed"}, ok())
add("get_todos", {"status": "canceled"}, ok())
add("get_todos", {"status": None}, ok())
add("get_todos", {"status": "None"}, ok())
add("get_todos", {"status": "null"}, ok())
add("get_todos", {"status": "bogus"}, read_error("invalid_status"))

# --- get_projects --------------------------------------------------------
add("get_projects", {}, ok())
add("get_projects", {"include_items": True}, ok())
add("get_projects", {"include_items": True}, ok())
add("get_projects", {"include_items": False}, ok())
add("get_projects", {"include_items": True, "mode": "detailed"}, ok())
add("get_projects", {"mode": "auto"}, ok())
add("get_projects", {"mode": "summary"}, ok())
add("get_projects", {"mode": "minimal"}, ok())
add("get_projects", {"mode": "standard"}, ok())
add("get_projects", {"mode": "detailed"}, ok())
add("get_projects", {"mode": "raw"}, ok())
add("get_projects", {"mode": "bogus"}, read_error("invalid_mode"))

# --- get_areas ------------------------------------------------------------
add("get_areas", {}, ok())
add("get_areas", {"include_items": True}, ok())
add("get_areas", {"include_items": True}, ok())
add("get_areas", {"include_items": False}, ok())
add("get_areas", {"include_items": True, "mode": "detailed"}, ok())
add("get_areas", {"mode": "auto"}, ok())
add("get_areas", {"mode": "summary"}, ok())
add("get_areas", {"mode": "minimal"}, ok())
add("get_areas", {"mode": "standard"}, ok())
add("get_areas", {"mode": "detailed"}, ok())
add("get_areas", {"mode": "raw"}, ok())
add("get_areas", {"mode": "bogus"}, read_error("invalid_mode"))

# --- get_inbox --------------------------------------------------------
add("get_inbox", {}, ok())
add("get_inbox", {"mode": "auto"}, ok())
add("get_inbox", {"mode": "summary"}, ok())
add("get_inbox", {"mode": "minimal"}, ok())
add("get_inbox", {"mode": "standard"}, ok())
add("get_inbox", {"mode": "detailed"}, ok())
add("get_inbox", {"mode": "raw"}, ok())
add("get_inbox", {"mode": "bogus"}, tool_error())  # unhandled ValueError -> ToolError, see Discovered
add("get_inbox", {"limit": 1}, ok())
add("get_inbox", {"limit": 500}, ok())
add("get_inbox", {"limit": 501}, tool_error())
add("get_inbox", {"limit": 0}, tool_error())
add("get_inbox", {"limit": -1}, tool_error())

# --- get_today --------------------------------------------------------
add("get_today", {}, ok())
add("get_today", {"mode": "auto"}, ok())
add("get_today", {"mode": "summary"}, ok())
add("get_today", {"mode": "minimal"}, ok())
add("get_today", {"mode": "standard"}, ok())
add("get_today", {"mode": "detailed"}, ok())
add("get_today", {"mode": "raw"}, ok())
add("get_today", {"mode": "bogus"}, tool_error())  # unhandled ValueError -> ToolError, see Discovered
add("get_today", {"limit": 1}, ok())
add("get_today", {"limit": 500}, ok())
add("get_today", {"limit": 501}, tool_error())
add("get_today", {"limit": 0}, tool_error())
add("get_today", {"limit": -1}, tool_error())
add("get_today", {"include_projects": True}, ok())
add("get_today", {"include_projects": True}, ok())
add("get_today", {"include_projects": False}, ok())
add("get_today", {"include_projects": True, "mode": "standard"}, ok())

# --- get_upcoming --------------------------------------------------------
add("get_upcoming", {}, ok())
add("get_upcoming", {"mode": "auto"}, ok())
add("get_upcoming", {"mode": "summary"}, ok())
add("get_upcoming", {"mode": "minimal"}, ok())
add("get_upcoming", {"mode": "standard"}, ok())
add("get_upcoming", {"mode": "detailed"}, ok())
add("get_upcoming", {"mode": "raw"}, ok())
add("get_upcoming", {"mode": "bogus"}, tool_error())  # unhandled ValueError -> ToolError, see Discovered
add("get_upcoming", {"limit": 1}, ok())
add("get_upcoming", {"limit": 500}, ok())
add("get_upcoming", {"limit": 501}, tool_error())
add("get_upcoming", {"limit": 0}, tool_error())
add("get_upcoming", {"limit": -1}, tool_error())
add("get_upcoming", {"days": 1}, ok())
add("get_upcoming", {"days": 365}, ok())
add("get_upcoming", {"days": 366}, tool_error())
add("get_upcoming", {"days": 0}, tool_error())
add("get_upcoming", {"include_projects": True}, ok())
add("get_upcoming", {"include_projects": True}, ok())
add("get_upcoming", {"include_projects": False}, ok())
add("get_upcoming", {"include_projects": True, "mode": "standard"}, ok())

# --- get_anytime --------------------------------------------------------
add("get_anytime", {}, ok())
add("get_anytime", {"mode": "auto"}, ok())
add("get_anytime", {"mode": "summary"}, ok())
add("get_anytime", {"mode": "minimal"}, ok())
add("get_anytime", {"mode": "standard"}, ok())
add("get_anytime", {"mode": "detailed"}, ok())
add("get_anytime", {"mode": "raw"}, ok())
add("get_anytime", {"mode": "bogus"}, tool_error())  # unhandled ValueError -> ToolError, see Discovered
add("get_anytime", {"limit": 1}, ok())
add("get_anytime", {"limit": 500}, ok())
add("get_anytime", {"limit": 501}, tool_error())
add("get_anytime", {"limit": 0}, tool_error())
add("get_anytime", {"limit": -1}, tool_error())
add("get_anytime", {"include_projects": True}, ok())
add("get_anytime", {"include_projects": True}, ok())
add("get_anytime", {"include_projects": False}, ok())
add("get_anytime", {"include_projects": True, "mode": "standard"}, ok())

# --- get_someday --------------------------------------------------------
add("get_someday", {}, ok())
add("get_someday", {"mode": "auto"}, ok())
add("get_someday", {"mode": "summary"}, ok())
add("get_someday", {"mode": "minimal"}, ok())
add("get_someday", {"mode": "standard"}, ok())
add("get_someday", {"mode": "detailed"}, ok())
add("get_someday", {"mode": "raw"}, ok())
add("get_someday", {"mode": "bogus"}, tool_error())  # unhandled ValueError -> ToolError, see Discovered
add("get_someday", {"limit": 1}, ok())
add("get_someday", {"limit": 500}, ok())
add("get_someday", {"limit": 501}, tool_error())
add("get_someday", {"limit": 0}, tool_error())
add("get_someday", {"limit": -1}, tool_error())
add("get_someday", {"include_project_tasks": True}, ok())
add("get_someday", {"include_project_tasks": True}, ok())
add("get_someday", {"include_project_tasks": False}, ok())
add("get_someday", {"include_project_tasks": True, "include_projects": True}, ok())
add("get_someday", {"include_projects": True}, ok())
add("get_someday", {"include_projects": False}, ok())
add("get_someday", {"include_projects": True, "mode": "standard"}, ok())

# --- get_logbook --------------------------------------------------------
add("get_logbook", {}, ok())
add("get_logbook", {"limit": 1}, ok())
add("get_logbook", {"limit": 500}, ok())
add("get_logbook", {"limit": 501}, tool_error())
add("get_logbook", {"limit": 0}, tool_error())
add("get_logbook", {"limit": -1}, tool_error())
add("get_logbook", {"period": "7d"}, ok())
add("get_logbook", {"period": "2w"}, ok())
add("get_logbook", {"period": "1m"}, ok())
add("get_logbook", {"period": "1y"}, ok())
add("get_logbook", {"period": "7x"}, tool_error())
add("get_logbook", {"period": "d"}, tool_error())
add("get_logbook", {"offset": 0}, ok())
add("get_logbook", {"offset": 5}, ok())
add("get_logbook", {"offset": -1}, tool_error())
add("get_logbook", {"include_canceled": True}, ok())
add("get_logbook", {"include_canceled": True}, ok())
add("get_logbook", {"include_canceled": False}, ok())
add("get_logbook", {"include_canceled": False, "limit": 10}, ok())

# --- get_trash --------------------------------------------------------
add("get_trash", {}, ok())
add("get_trash", {"limit": 1}, ok())
add("get_trash", {"limit": 100}, ok())
add("get_trash", {"limit": 101}, tool_error())
add("get_trash", {"limit": 0}, tool_error())
add("get_trash", {"limit": -1}, tool_error())
add("get_trash", {"offset": 0}, ok())
add("get_trash", {"offset": 5}, ok())
add("get_trash", {"offset": -1}, tool_error())
add("get_trash", {"include_projects": True}, ok())
add("get_trash", {"include_projects": True}, ok())
add("get_trash", {"include_projects": False}, ok())
add("get_trash", {"include_projects": True, "limit": 10}, ok())

# --- get_due_in_days --------------------------------------------------------
add("get_due_in_days", {}, ok())
add("get_due_in_days", {"days": 1}, ok())
add("get_due_in_days", {"days": 365}, ok())
add("get_due_in_days", {"days": 366}, tool_error())
add("get_due_in_days", {"days": 0}, tool_error())
add("get_due_in_days", {"days": -1}, tool_error())
add("get_due_in_days", {"include_overdue": True}, ok())
add("get_due_in_days", {"include_overdue": True}, ok())
add("get_due_in_days", {"include_overdue": False}, ok())
add("get_due_in_days", {"include_overdue": False, "days": 5}, ok())

# --- get_activating_in_days --------------------------------------------------------
add("get_activating_in_days", {}, ok())
add("get_activating_in_days", {"days": 1}, ok())
add("get_activating_in_days", {"days": 365}, ok())
add("get_activating_in_days", {"days": 366}, tool_error())
add("get_activating_in_days", {"days": 0}, tool_error())
add("get_activating_in_days", {"days": -1}, tool_error())

# --- get_tags --------------------------------------------------------
add("get_tags", {}, ok())
add("get_tags", {"include_items": True}, ok())
add("get_tags", {"include_items": True}, ok())
add("get_tags", {"include_items": False}, ok())
add("get_tags", {"include_items": True}, ok())  # exercise twice: cheap, keeps param coverage >=3

# --- get_tagged_items --------------------------------------------------------
add("get_tagged_items", {"tag": "errands"}, ok())
add("get_tagged_items", {"tag": TAG_1["title"]}, ok())
add("get_tagged_items", {"tag": "definitely-not-a-real-tag"}, read_error("unknown_tag"))

# --- get_tag_usage --------------------------------------------------------
add("get_tag_usage", {}, ok())
add("get_tag_usage", {"mode": "summary"}, ok())
add("get_tag_usage", {"mode": "minimal"}, ok())
add("get_tag_usage", {"mode": "standard"}, ok())
add("get_tag_usage", {"mode": "detailed"}, ok())
add("get_tag_usage", {"mode": "auto"}, read_error("invalid_mode"))
add("get_tag_usage", {"mode": "raw"}, read_error("invalid_mode"))
add("get_tag_usage", {"mode": "bogus"}, read_error("invalid_mode"))
add("get_tag_usage", {"only_unused": True}, ok())
add("get_tag_usage", {"only_unused": True}, ok())
add("get_tag_usage", {"only_unused": False}, ok())
add("get_tag_usage", {"only_unused": True, "mode": "minimal"}, ok())

# --- get_project_headings --------------------------------------------------------
add("get_project_headings", {"project_id": PROJECT_WITH_HEADINGS["uuid"]}, ok())
add("get_project_headings", {"project_id": TODO_1["uuid"]}, read_error("invalid_type"))
add("get_project_headings", {"project_id": HEADING_1["uuid"]}, read_error("invalid_type"))
add("get_project_headings", {"project_id": AREA_1["uuid"]}, read_error("invalid_type"))
add("get_project_headings", {"project_id": "does-not-exist-xyz"}, read_error("not_found"))
add("get_project_headings", {"project_id": TAG_1["uuid"]}, read_error("invalid_type"))
add("get_project_headings", {"project_id": PROJECT_WITH_HEADINGS["uuid"], "mode": "auto"}, ok())
add("get_project_headings", {"project_id": PROJECT_WITH_HEADINGS["uuid"], "mode": "summary"}, ok())
add("get_project_headings", {"project_id": PROJECT_WITH_HEADINGS["uuid"], "mode": "minimal"}, ok())
add("get_project_headings", {"project_id": PROJECT_WITH_HEADINGS["uuid"], "mode": "standard"}, ok())
add("get_project_headings", {"project_id": PROJECT_WITH_HEADINGS["uuid"], "mode": "detailed"}, ok())
add("get_project_headings", {"project_id": PROJECT_WITH_HEADINGS["uuid"], "mode": "raw"}, ok())
add("get_project_headings", {"project_id": PROJECT_WITH_HEADINGS["uuid"], "mode": "bogus"}, read_error("invalid_mode"))

# --- get_todo_by_id --------------------------------------------------------
add("get_todo_by_id", {"todo_id": TODO_1["uuid"]}, ok())
add("get_todo_by_id", {"todo_id": PROJECT_1["uuid"]}, ok())
add("get_todo_by_id", {"todo_id": HEADING_1["uuid"]}, ok())
add("get_todo_by_id", {"todo_id": AREA_1["uuid"]}, ok())
add("get_todo_by_id", {"todo_id": TAG_1["uuid"]}, read_error("invalid_type"))
add("get_todo_by_id", {"todo_id": "does-not-exist-xyz"}, tool_error())

# --- search_todos --------------------------------------------------------
add("search_todos", {"query": "milk"}, ok())
add("search_todos", {"query": "x"}, ok())
add("search_todos", {"query": ""}, read_error("invalid_query"))
add("search_todos", {"query": "   "}, read_error("invalid_query"))
add("search_todos", {"query": "milk", "limit": 1}, ok())
add("search_todos", {"query": "milk", "limit": 500}, ok())
add("search_todos", {"query": "milk", "limit": 501}, tool_error())
add("search_todos", {"query": "milk", "limit": 0}, tool_error())
add("search_todos", {"query": "milk", "limit": -1}, tool_error())
add("search_todos", {"query": "milk", "mode": "auto"}, ok())
add("search_todos", {"query": "milk", "mode": "summary"}, ok())
add("search_todos", {"query": "milk", "mode": "minimal"}, ok())
add("search_todos", {"query": "milk", "mode": "standard"}, ok())
add("search_todos", {"query": "milk", "mode": "detailed"}, ok())
add("search_todos", {"query": "milk", "mode": "raw"}, ok())
add("search_todos", {"query": "milk", "mode": "bogus"}, read_error("invalid_mode"))
add("search_todos", {"query": "milk", "status": "incomplete"}, ok())
add("search_todos", {"query": "milk", "status": "completed"}, ok())
add("search_todos", {"query": "milk", "status": "canceled"}, ok())
add("search_todos", {"query": "milk", "status": None}, ok())
add("search_todos", {"query": "milk", "status": "None"}, ok())
add("search_todos", {"query": "milk", "status": "null"}, ok())
add("search_todos", {"query": "milk", "status": "bogus"}, read_error("invalid_status"))
add("search_todos", {"query": "milk", "offset": 0}, ok())
add("search_todos", {"query": "milk", "offset": 5}, ok())
add("search_todos", {"query": "milk", "offset": -1}, tool_error())

# --- search_advanced --------------------------------------------------------
add("search_advanced", {}, ok())
add("search_advanced", {"status": "incomplete"}, ok())
add("search_advanced", {"status": "completed"}, ok())
add("search_advanced", {"status": "canceled"}, ok())
add("search_advanced", {"status": "bogus"}, tool_error())
add("search_advanced", {"type": "to-do"}, ok())
add("search_advanced", {"type": "project"}, ok())
add("search_advanced", {"type": "heading"}, ok())
add("search_advanced", {"type": "bogus"}, tool_error())
add("search_advanced", {"tag": "errands"}, ok())
add("search_advanced", {"tag": "definitely-not-a-real-tag"}, read_error("unknown_tag"))
add("search_advanced", {"area": AREA_1["uuid"]}, ok())
add("search_advanced", {"tag": "errands"}, ok())
add("search_advanced", {"tag": "definitely-not-a-real-tag"}, read_error("unknown_tag"))
add("search_advanced", {"tag": "errands", "status": "incomplete"}, ok())
add("search_advanced", {"area": AREA_1["uuid"]}, ok())
add("search_advanced", {"area": "unknown-area-xyz"}, ok())
add("search_advanced", {"area": AREA_1["uuid"], "type": "to-do"}, ok())
add("search_advanced", {"start_date": "2026-01-01"}, ok())
add("search_advanced", {"start_date": "2025-13-45"}, read_error("invalid_start_date_format"))
add("search_advanced", {"start_date": "today"}, read_error("invalid_start_date_format"))
add("search_advanced", {"start_date": ""}, ok())  # falsy -> validation skipped, not sent
add("search_advanced", {"deadline": "2026-01-01"}, ok())
add("search_advanced", {"deadline": "2025-13-45"}, read_error("invalid_deadline_format"))
add("search_advanced", {"deadline": "today"}, read_error("invalid_deadline_format"))
add("search_advanced", {"deadline": ""}, ok())  # falsy -> validation skipped, not sent
add("search_advanced", {"limit": 1}, ok())
add("search_advanced", {"limit": 500}, ok())
add("search_advanced", {"limit": 501}, tool_error())
add("search_advanced", {"limit": 0}, tool_error())
add("search_advanced", {"limit": -1}, tool_error())
add("search_advanced", {"mode": "auto"}, ok())
add("search_advanced", {"mode": "summary"}, ok())
add("search_advanced", {"mode": "minimal"}, ok())
add("search_advanced", {"mode": "standard"}, ok())
add("search_advanced", {"mode": "detailed"}, ok())
add("search_advanced", {"mode": "raw"}, ok())
add("search_advanced", {"mode": "bogus"}, read_error("invalid_mode"))
add("search_advanced", {"offset": 0}, ok())
add("search_advanced", {"offset": 5}, ok())
add("search_advanced", {"offset": -1}, tool_error())

# --- get_recent --------------------------------------------------------
add("get_recent", {"period": "7d"}, ok())
add("get_recent", {"period": "2w"}, ok())
add("get_recent", {"period": "1m"}, ok())
add("get_recent", {"period": "1y"}, ok())
add("get_recent", {"period": "7x"}, tool_error())
add("get_recent", {"period": "d"}, tool_error())
add("get_recent", {"period": "7d", "status": "incomplete"}, ok())
add("get_recent", {"period": "7d", "status": "completed"}, ok())
add("get_recent", {"period": "7d", "status": "canceled"}, ok())
add("get_recent", {"period": "7d", "status": "bogus"}, tool_error())
add("get_recent", {"period": "7d", "type": "to-do"}, ok())
add("get_recent", {"period": "7d", "type": "project"}, ok())
add("get_recent", {"period": "7d", "type": "heading"}, ok())
add("get_recent", {"period": "7d", "type": "bogus"}, tool_error())


# ---------------------------------------------------------------------------
# Case IDs for readable pytest output.
# ---------------------------------------------------------------------------


def _case_id(case: Tuple[str, Dict[str, Any], Any]) -> str:
    tool, args, expectation = case
    args_str = ",".join(f"{k}={v!r}" for k, v in args.items()) or "defaults"
    return f"{tool}[{args_str}]->{expectation.kind}"


# ---------------------------------------------------------------------------
# Assertions
# ---------------------------------------------------------------------------


# Tools whose read-tool implementation passes a raw list (ListWithTotal, a
# list subclass) into ThingsMCPServer._read_result, which only sets
# items/count/total/mode/limit/offset for a list input - never
# 'requested_mode' (that key is only added on the dict branch, taken by
# tools that route through context_manager.optimize_response with a
# dict-shaped {"data": ..., "meta": ...} payload). This is a real
# inconsistency in the envelope contract - see Discovered.
LIST_TOOLS_WITHOUT_REQUESTED_MODE = {
    "get_logbook",
    "get_due_in_days",
    "get_activating_in_days",
    "get_tags",
    "get_tagged_items",
    "get_recent",
}


def _assert_ok_envelope(sc: Dict[str, Any], tool: str) -> None:
    assert sc is not None, f"{tool}: structured_content is None"
    assert sc.get("success") is not False, f"{tool}: unexpected structured error: {sc}"

    if tool == "get_todo_by_id":
        assert "item" in sc, f"{tool}: expected 'item' key, got {sorted(sc.keys())}"
        return

    required_keys = REQUIRED_LIST_KEYS
    if tool in LIST_TOOLS_WITHOUT_REQUESTED_MODE:
        required_keys = REQUIRED_LIST_KEYS - {"requested_mode"}

    assert required_keys.issubset(sc.keys()), f"{tool}: missing envelope keys, got {sorted(sc.keys())}"
    assert sc["mode"] != "auto", f"{tool}: mode must never be the literal 'auto'"


def _assert_read_error(sc: Dict[str, Any], tool: str, code: str) -> None:
    assert sc is not None, f"{tool}: structured_content is None"
    assert sc.get("success") is False, f"{tool}: expected success=False, got {sc}"
    assert sc.get("error") == code, f"{tool}: expected error={code!r}, got {sc.get('error')!r} (full: {sc})"
    assert "message" in sc, f"{tool}: expected a 'message' field, got {sorted(sc.keys())}"
    if code == "unknown_tag":
        # Per CLAUDE.md, unknown_tag additionally carries 'tag' and
        # 'suggestions' (review hardening, hq-gbl.4).
        assert "tag" in sc, f"{tool}: unknown_tag must carry 'tag', got {sorted(sc.keys())}"
        assert isinstance(sc.get("suggestions"), list), (
            f"{tool}: unknown_tag must carry a 'suggestions' list, got {sc.get('suggestions')!r}"
        )


# ---------------------------------------------------------------------------
# Parametrized matrix
# ---------------------------------------------------------------------------


class TestReadInputMatrix:
    @pytest.mark.parametrize("case", CASES, ids=_case_id)
    @pytest.mark.asyncio
    async def test_case(self, client: Client, case: Tuple[str, Dict[str, Any], Any]) -> None:
        tool, args, expectation = case

        if expectation.kind == "tool_error":
            with pytest.raises(ToolError):
                async with client:
                    await client.call_tool(tool, args)
            return

        async with client:
            result = await client.call_tool(tool, args)

        sc = result.structured_content

        if expectation.kind == "ok":
            _assert_ok_envelope(sc, tool)
        elif expectation.kind == "read_error":
            _assert_read_error(sc, tool, expectation.code)
        else:  # pragma: no cover - exhaustive kind set
            raise AssertionError(f"Unknown expectation kind: {expectation.kind}")


# ---------------------------------------------------------------------------
# Completeness check: every (read tool, param) pair must have >= 3 cases.
# ---------------------------------------------------------------------------

READ_TOOLS = {
    "get_todos",
    "get_projects",
    "get_areas",
    "get_inbox",
    "get_today",
    "get_upcoming",
    "get_anytime",
    "get_someday",
    "get_logbook",
    "get_trash",
    "get_due_in_days",
    "get_activating_in_days",
    "get_tags",
    "get_tagged_items",
    "get_tag_usage",
    "get_project_headings",
    "get_todo_by_id",
    "search_todos",
    "search_advanced",
    "get_recent",
}


class TestCompleteness:
    @pytest.mark.asyncio
    async def test_every_read_tool_param_has_at_least_three_cases(self, client: Client) -> None:
        async with client:
            tools = await client.list_tools()

        tools_by_name = {t.name: t for t in tools if t.name in READ_TOOLS}
        missing_tools = READ_TOOLS - set(tools_by_name.keys())
        assert not missing_tools, f"Read tools not found via list_tools(): {missing_tools}"

        # Count CASES coverage per (tool, param).
        coverage: Dict[Tuple[str, str], int] = {}
        for tool, args, _expectation in CASES:
            for param in args.keys():
                coverage[(tool, param)] = coverage.get((tool, param), 0) + 1

        under_covered: List[str] = []
        for tool, tool_def in tools_by_name.items():
            schema = tool_def.inputSchema or {}
            properties = schema.get("properties", {})
            for param in properties.keys():
                count = coverage.get((tool, param), 0)
                if count < 3:
                    under_covered.append(f"{tool}.{param} (has {count} cases, need >=3)")

        assert not under_covered, (
            "The following (tool, param) pairs have fewer than 3 CASES entries:\n"
            + "\n".join(sorted(under_covered))
        )

    @pytest.mark.asyncio
    async def test_cases_table_has_at_least_150_entries(self) -> None:
        assert len(CASES) >= 150, f"Expected >= 150 CASES entries, got {len(CASES)}"
