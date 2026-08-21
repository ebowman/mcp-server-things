"""Parameter-reach test generator for every write MCP tool (hq-f0w.9).

Why (failure class 4 - declared parameter never asserted to reach the
backend): add_todo(heading=...) was declared in server.py but silently
dropped on the AppleScript path and no test passed heading as an argument
and then checked it actually reached Things. This file closes that gap
generically: for every mutating (write) tool registered on the FastMCP
server, and for every parameter FastMCP reports for that tool, a unique
sentinel value is sent through the real ThingsMCPServer -> ThingsTools ->
AppleScriptManager stack (with a recording fake in place of
AppleScriptManager) and the test asserts the sentinel (or, for
booleans/enums, the corresponding AppleScript property / URL-scheme key)
appears in at least one captured AppleScript script string or URL-scheme
call. things.py (list_id/list_title resolution) is patched with canned
data so every path is reachable without a live Things 3 database.

Design (data-driven, per the bead's "no silent passes" requirement):
  - MUTATING_TOOLS enumerates every tool this file has explicitly
    classified as a write tool needing parameter-reach coverage. Any
    OTHER tool registered on the server that isn't in MUTATING_TOOLS and
    isn't in READ_TOOLS fails test_every_registered_tool_is_classified
    with "classify this tool as read or write" - this is what makes the
    generator data-driven: a newly added tool cannot silently escape
    coverage.
  - For each mutating tool, BASE_KWARGS supplies the minimal valid
    arguments needed to reach a real write attempt (e.g. add_todo needs
    title; update_todo needs id).
  - PARAM_ASSERTIONS[(tool, param)] is an optional override describing
    exactly how to build the sentinel value and how to detect it in the
    captured calls, for parameters that aren't a plain pass-through
    string (booleans, enums, ints). Parameters without an override use
    the DEFAULT_STRING_HANDLER (unique alphanumeric sentinel string,
    looked for verbatim in any captured script or URL params).
  - IGNORED lists parameters that legitimately never reach Things
    (mode/limit-style plumbing, or ones covered by a dedicated
    xfail-with-bead-reference below), each with a one-line reason.

Any real dropped-parameter bug found while writing this file is NOT fixed
here (out of this bead's scope) - it is recorded in DROPPED_PARAMS below,
each wired to a strict xfail plus a bead id filed as follow-up work.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest
from _pytest.mark.structures import ParameterSet
from fastmcp import Client

from things_mcp.config import ThingsMCPConfig
from things_mcp.server import ThingsMCPServer
from things_mcp.tools import ThingsTools

THINGS_GET_PATCH = "things_mcp.scheduling.todo_operations.things.get"
THINGS_PROJECTS_PATCH = "things_mcp.scheduling.todo_operations.things.projects"
THINGS_AREAS_PATCH = "things_mcp.scheduling.todo_operations.things.areas"
THINGS_TASKS_PATCH = "things_mcp.scheduling.todo_operations.things.tasks"
# write_operations.py holds its own separate LazyThingsProxy instance (not
# the same object as todo_operations.things above) - delete_todo()'s
# type-resolution things.get() call (hq-f0w.40) needs its own patch so it
# doesn't fall through to the real things.py package against a sentinel id
# that doesn't exist in the developer's database.
WRITE_OPS_THINGS_GET_PATCH = "things_mcp.tools_helpers.write_operations.things.get"

# A list_title sentinel that things.projects()/things.areas() are patched to
# resolve unambiguously to project uuid RESOLVEDPROJECTID (see
# _patched_things_lookups below). Used by any test that exercises
# list_title-based tools/params.
SENTINEL_LIST_TITLE = "SENTINELlisttitleXYZ"
RESOLVED_LIST_TITLE_PROJECT_ID = "RESOLVEDPROJECTID"


# ===========================================================================
# Recording fake AppleScriptManager
# ===========================================================================


class RecordingAppleScriptManager:
    """Records every execute_applescript script and execute_url_scheme call.

    Returns context-sensitive canned success responses so every write path
    under test (create/update/move/tag/checklist) completes its own
    internal follow-up reads (e.g. "what are this todo's current tags?")
    without needing a live Things 3 database. Response selection is based
    on distinctive substrings in the emitted AppleScript, matched in the
    order below (first match wins).
    """

    def __init__(self) -> None:
        # A non-empty auth token is required for every URL-scheme 'update'
        # action (AUTH_REQUIRING_ACTIONS) - heading/evening/checklist-item
        # mutation tools are otherwise gated closed before they ever build a
        # script. This sentinel is alphanumeric so it would itself survive
        # appearing in a captured call, but no test asserts on it.
        self.auth_token = "SENTINELauthtokenABC"
        self.execution_calls: List[str] = []
        self.url_scheme_calls: List[Tuple[str, Dict[str, Any]]] = []
        # Per-title call counters for the create-via-URL-scheme snapshot/poll
        # id lookup (_find_todo_ids_by_title): first call (pre-create
        # snapshot) returns no matches, every subsequent call for the same
        # title returns one fabricated new id, so add_todo(heading=...) /
        # add_todo(checklist_items=...) / add_todo(when='evening') resolve
        # immediately instead of polling for the full 3s deadline.
        self._title_lookup_counts: Dict[str, int] = {}
        # Per-todo-id canned response for the "get current tags" read that
        # add_tags/remove_tags issue before rewriting a todo's tags (keyed
        # by the literal todo id embedded in `to do id "..."`). Lets a test
        # seed a todo with pre-existing tags (e.g. remove_tags needs a real
        # "keepme, <sentinel>" starting set to prove the sentinel tag - and
        # only the sentinel tag - was actually removed). Defaults to "" (no
        # existing tags) for any todo id not present here.
        self.current_tags_by_todo_id: Dict[str, str] = {}

    async def execute_applescript(self, script: str, cache_key: Optional[str] = None) -> Dict[str, Any]:
        self.execution_calls.append(script)

        # --- add_todo/add_project/add_area creation ---
        if "make new to do with properties" in script:
            return {"success": True, "output": "NEWTODOID"}
        if "make new project with properties" in script:
            return {"success": True, "output": "NEWPROJECTID"}
        if "make new area with properties" in script:
            return {"success": True, "output": "NEWAREAID"}
        if "make new tag with properties" in script:
            return {"success": True, "output": "CREATED"}

        # --- add_todo via URL scheme: pre/post-create id lookup by title ---
        if "to dos whose name is" in script:
            # Extract the quoted title so different titles get independent
            # snapshot/poll sequences.
            title_key = script.split("to dos whose name is", 1)[1][:120]
            count = self._title_lookup_counts.get(title_key, 0)
            self._title_lookup_counts[title_key] = count + 1
            if count == 0:
                return {"success": True, "output": ""}
            return {"success": True, "output": f"NEWURLTODOID{count}"}

        # --- add_tags/remove_tags: read current tags before rewriting ---
        if "return tag names of targetTodo" in script:
            todo_id = self._extract_to_do_id(script)
            output = self.current_tags_by_todo_id.get(todo_id, "")
            return {"success": True, "output": output}

        # --- get_tag_usage-style / TagValidationService._get_existing_tags ---
        if "repeat with theTag in tags" in script:
            return {"success": True, "output": ""}

        # --- move_operations: fetch todo info before moving ---
        if "todoInfo" in script and "getCurrentLocation" in script:
            return {
                "success": True,
                "output": "id123, Some title, some notes, open, inbox",
            }

        # --- move_operations: execute the actual move ---
        if "move theTodo to list" in script or "set project of theTodo to" in script or "set area of theTodo to" in script:
            return {"success": True, "output": "MOVED to destination"}

        # --- bulk_update_todos ---
        if "successCount" in script:
            return {"success": True, "output": "successCount:2, errors:{}"}

        # --- update_todo/update_project/update_area (generic "updated" tail) ---
        if 'return "updated"' in script:
            return {"success": True, "output": "updated"}

        # --- delete_todo ---
        if "delete targetTodo" in script:
            return {"success": True, "output": "deleted"}

        # Fallback: generic success (used by scheduling strategies'
        # relative-date/date-object/list-fallback scripts, which only
        # check for success and a specific marker substring - none of the
        # scheduling strategies are exercised as the FIRST strategy for
        # 'today'/'tomorrow'/ISO dates without also matching one of the
        # specific branches above, but a defensive fallback keeps any
        # unmatched script from erroring the whole call).
        if "scheduled_relative" in script or "targetDate" in script:
            return {"success": True, "output": "scheduled_relative"}

        return {"success": True, "output": "mock_output"}

    async def execute_url_scheme(self, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.url_scheme_calls.append((action, dict(parameters or {})))
        return {"success": True, "url": f"things:///{action}", "message": f"Successfully executed {action} action"}

    @staticmethod
    def _extract_to_do_id(script: str) -> Optional[str]:
        """Extract the id from a `to do id "..."` clause in `script`, or
        None if no such clause is present."""
        match = re.search(r'to do id "([^"]*)"', script)
        return match.group(1) if match else None

    # -- helpers for assertions --

    def all_scripts_text(self) -> str:
        return "\n".join(self.execution_calls)

    def all_url_params(self) -> List[Dict[str, Any]]:
        return [params for _action, params in self.url_scheme_calls]


def _patched_things_lookups():
    """Return the patch context managers needed to resolve list_id/list_title
    sentinels used across BASE_KWARGS/PARAM_ASSERTIONS.

    - things.get(<any id>) always resolves as a project (covers list_id
      sentinels used as plain pass-through project ids).
    - things.projects() contains one project titled SENTINEL_LIST_TITLE
      with uuid RESOLVED_LIST_TITLE_PROJECT_ID, so list_title params
      resolve unambiguously.
    - things.areas() is empty (no ambiguity with the project match above).
    - things.tasks(type='heading', ...) is empty - heading-exists checks
      degrade to a (harmless, ignored) warning rather than blocking the
      write.
    - write_operations.things.get(<any id>) always resolves as a to-do
      (separate LazyThingsProxy instance from the one above) - covers
      delete_todo()'s own type-resolution things.get() call (hq-f0w.40),
      keeping delete_todo(todo_id=<sentinel>) on its `to do id` script path
      instead of hitting the real, unpatched things.py package.
    """
    return [
        patch(THINGS_GET_PATCH, return_value={"type": "project"}),
        patch(
            THINGS_PROJECTS_PATCH,
            return_value=[{"uuid": RESOLVED_LIST_TITLE_PROJECT_ID, "title": SENTINEL_LIST_TITLE}],
        ),
        patch(THINGS_AREAS_PATCH, return_value=[]),
        patch(THINGS_TASKS_PATCH, return_value=[]),
        patch(WRITE_OPS_THINGS_GET_PATCH, return_value={"type": "to-do"}),
    ]


def _make_server() -> Tuple[ThingsMCPServer, RecordingAppleScriptManager]:
    """Build a real ThingsMCPServer wired to a RecordingAppleScriptManager.

    ai_can_create_tags=True (-> ALLOW_ALL tag policy) so any tag sentinel
    is auto-created and passed straight through to the emitted
    AppleScript/URL params instead of being filtered/rejected by the
    default FAIL_ON_UNKNOWN policy - tag-policy filtering itself is
    covered elsewhere (tag_service tests); this file is about parameter
    reach, not policy semantics.
    """
    server = ThingsMCPServer()
    fake = RecordingAppleScriptManager()
    config = ThingsMCPConfig(ai_can_create_tags=True)
    server.tools = ThingsTools(fake, config)
    # create_tag's AI-gate check (server.py) reads self.config directly
    # (the ThingsMCPServer-level config), not self.tools.config - update it
    # too so create_tag(tag_name=...) isn't rejected before ever building
    # an AppleScript script.
    server.config.ai_can_create_tags = True
    return server, fake


async def _call_tool(server: ThingsMCPServer, tool_name: str, kwargs: Dict[str, Any]):
    client = Client(server.mcp)
    async with client:
        return await client.call_tool(tool_name, kwargs)


def run_tool(
    tool_name: str,
    kwargs: Dict[str, Any],
    seed: Optional[Callable[[RecordingAppleScriptManager], None]] = None,
    extra_things_patches: Optional[List[Any]] = None,
) -> Tuple[Any, RecordingAppleScriptManager]:
    """Call `tool_name` with `kwargs` against a fresh server+fake, with
    things.py lookups patched. `seed`, if given, is called with the fresh
    fake manager before the tool call (e.g. to pre-populate
    current_tags_by_todo_id for a remove_tags test). `extra_things_patches`,
    if given, is a list of already-constructed `unittest.mock.patch(...)`
    context managers started AFTER (so they take precedence over) the
    default `_patched_things_lookups()` set - e.g. to make a specific
    area_id/area_title sentinel resolve as a real area for hq-rmh's
    _resolve_area pre-check. Returns (call_tool_result, fake_manager)."""
    server, fake = _make_server()
    if seed:
        seed(fake)
    patches = _patched_things_lookups() + list(extra_things_patches or [])
    for p in patches:
        p.start()
    try:
        result = asyncio.run(_call_tool(server, tool_name, kwargs))
    finally:
        for p in patches:
            p.stop()
    return result, fake


# ===========================================================================
# Tool classification
# ===========================================================================

# Every write (mutating) tool registered in server.py. A tool present on the
# live server but absent from both this set and READ_TOOLS fails
# test_every_registered_tool_is_classified.
MUTATING_TOOLS = {
    "add_todo",
    "update_todo",
    "delete_todo",
    "add_project",
    "update_project",
    "add_area",
    "update_area",
    "add_tags",
    "remove_tags",
    "create_tag",
    "bulk_update_todos",
    "move_record",
    "bulk_move_records",
    "add_checklist_items",
    "prepend_checklist_items",
    "replace_checklist_items",
}

# Every read/utility (non-mutating) tool registered in server.py, listed
# explicitly so an unclassified new tool cannot silently pass by omission.
READ_TOOLS = {
    "get_todos",
    "get_todo_by_id",
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
    "get_project_headings",
    "get_tag_usage",
    "search_todos",
    "search_advanced",
    "get_recent",
    "health_check",
    "queue_status",
    "context_stats",
    "get_server_capabilities",
    "get_usage_recommendations",
}


# ===========================================================================
# Base (minimal valid) kwargs per mutating tool
# ===========================================================================

BASE_KWARGS: Dict[str, Dict[str, Any]] = {
    "add_todo": {"title": "Base todo title"},
    "update_todo": {"id": "TODOID1"},
    "delete_todo": {"todo_id": "TODOID1"},
    "add_project": {"title": "Base project title"},
    "update_project": {"id": "PROJECTID1"},
    "add_area": {"title": "Base area title"},
    "update_area": {"id": "AREAID1"},
    "add_tags": {"todo_id": "TODOID1", "tags": "basetag"},
    # remove_tags gets its own todo id (rather than sharing TODOID1)
    # so RecordingAppleScriptManager.current_tags_by_todo_id can seed a
    # real starting tag set for it (see PARAM_ASSERTIONS below) without
    # affecting any other tool's fake responses for TODOID1.
    "remove_tags": {"todo_id": "REMOVETAGSTODOID", "tags": "basetag"},
    "create_tag": {"tag_name": "basetag"},
    "bulk_update_todos": {"todo_ids": "TODOID1,TODOID2"},
    "move_record": {"todo_id": "TODOID1", "destination_list": "today"},
    "bulk_move_records": {"todo_ids": "TODOID1,TODOID2", "destination": "today"},
    "add_checklist_items": {"todo_id": "TODOID1", "items": ["base item"]},
    "prepend_checklist_items": {"todo_id": "TODOID1", "items": ["base item"]},
    "replace_checklist_items": {"todo_id": "TODOID1", "items": ["base item"]},
}


# ===========================================================================
# IGNORED: parameters that by design never reach Things
# ===========================================================================

IGNORED: Dict[Tuple[str, str], str] = {
    ("bulk_move_records", "max_concurrent"): (
        "controls asyncio.Semaphore concurrency for bulk_move's internal "
        "fan-out (move_operations.py bulk_move); it is client-side "
        "orchestration and is never sent to Things in any script or URL."
    ),
}


# ===========================================================================
# DROPPED_PARAMS: real bugs found while writing this file (out of scope to
# fix here - filed as follow-up beads and marked xfail(strict=True) below).
# ===========================================================================

# Populated only if a genuine drop is found (see bottom of file for the
# xfail wiring). Kept as a module-level constant so it's visible in one
# place even if empty.
DROPPED_PARAMS: Dict[Tuple[str, str], str] = {}


# ===========================================================================
# Per-parameter sentinel + assertion overrides
# ===========================================================================
#
# Each override is a dict with:
#   build(sentinel) -> value to pass for this param (defaults to the raw
#       sentinel string if 'build' is omitted)
#   check(fake, needle) -> bool: whether the sentinel (or the property/key
#       it maps to) was observed in the captured calls. Defaults to a
#       plain substring search across every captured script and every
#       captured URL-scheme parameter value if 'check' is omitted.
#   extra_kwargs: dict merged into BASE_KWARGS for this one call (e.g.
#       heading needs a list_id target to not short-circuit with a
#       structured pre-write error).


def _default_check(fake: RecordingAppleScriptManager, needle: str) -> bool:
    if needle in fake.all_scripts_text():
        return True
    for params in fake.all_url_params():
        for v in params.values():
            if needle in str(v):
                return True
    return False


def _property_check(*substrings: str):
    """For boolean/enum-style params with no free-text value of their own
    (e.g. completed='true' -> 'status of targetTodo to completed'): assert
    the AppleScript property/branch the value maps to is present. Used only
    where the sentinel itself is not expected to appear verbatim."""

    def _check(fake: RecordingAppleScriptManager, _needle: str) -> bool:
        text = fake.all_scripts_text()
        return any(s in text for s in substrings)

    return _check


def _property_value_check(*property_markers: str):
    """For plain string-value params (title/notes/tags/deadline dates/ids):
    assert that a script containing one of `property_markers` ALSO contains
    the sentinel value itself, not merely that the property marker text
    exists anywhere. This is stronger than _property_check and catches a
    parameter whose *value* is dropped/mangled even if the property
    assignment line itself is still emitted unconditionally."""

    def _check(fake: RecordingAppleScriptManager, needle: str) -> bool:
        for script in fake.execution_calls:
            if any(marker in script for marker in property_markers) and needle in script:
                return True
        return False

    return _check


def _url_key_check(key: str, value_substring: Optional[str] = None):
    def _check(fake: RecordingAppleScriptManager, needle: str) -> bool:
        expected = value_substring if value_substring is not None else needle
        for params in fake.all_url_params():
            if key in params and expected in str(params[key]):
                return True
        return False

    return _check


PARAM_ASSERTIONS: Dict[Tuple[str, str], Dict[str, Any]] = {
    # --- add_todo ---
    ("add_todo", "heading"): {
        "extra_kwargs": {"list_id": "PROJHEADTARGET"},
        "check": _url_key_check("heading"),
    },
    ("add_todo", "list_id"): {
        # No heading/checklist/when='evening' in this call, so add_todo
        # takes the plain AppleScript path (project_id resolved via
        # things.get -> `project id "..."`), not the URL scheme.
        "check": _property_value_check("project id"),
    },
    ("add_todo", "list_title"): {
        # list_title is resolved to RESOLVED_LIST_TITLE_PROJECT_ID before
        # reaching AppleScript, so the sentinel itself never appears -
        # assert the *resolved id* appears in a `project id` assignment
        # instead (still fails if the resolution/plumbing is dropped).
        "build": lambda _s: SENTINEL_LIST_TITLE,
        "check": lambda fake, _needle: any(
            "project id" in s and RESOLVED_LIST_TITLE_PROJECT_ID in s for s in fake.execution_calls
        ),
    },
    ("add_todo", "checklist_items"): {
        "build": lambda s: [s],
        "check": _url_key_check("checklist-items"),
    },
    ("add_todo", "when"): {
        # 'when' is consumed by schedule_todo_reliable, not embedded
        # verbatim as a string - ISO dates are decomposed into targetDate
        # year/month/day AppleScript statements (see strategies.py
        # _schedule_specific_date_objects), so the needle targets the
        # exploded year assignment for this call's distinctive date,
        # scoped to a script that also issued the schedule command.
        "build": lambda _s: "2031-02-14",
        "needle": "year of targetDate to 2031",
        "check": _property_value_check("schedule theTodo"),
    },
    ("add_todo", "deadline"): {
        # ISO deadline dates are decomposed into year/month/day AppleScript
        # statements, not embedded verbatim - the needle targets the
        # exploded year assignment for this call's distinctive date.
        "build": lambda _s: "2031-03-17",
        "needle": "year of deadlineDate to 2031",
        "check": _property_value_check("due date of newTodo"),
    },
    ("add_todo", "tags"): {
        "check": _property_value_check("tag names of newTodo"),
    },

    # --- update_todo ---
    ("update_todo", "title"): {
        "check": _property_value_check("name of targetTodo"),
    },
    ("update_todo", "notes"): {
        "check": _property_value_check("notes of targetTodo"),
    },
    ("update_todo", "tags"): {
        "check": _property_value_check("tag names of targetTodo"),
    },
    ("update_todo", "when"): {
        "build": lambda _s: "2031-04-18",
        "needle": "year of targetDate to 2031",
        "check": _property_value_check("schedule theTodo"),
    },
    ("update_todo", "deadline"): {
        "build": lambda _s: "2031-05-19",
        "needle": "year of deadlineDate to 2031",
        "check": _property_value_check("due date of targetTodo"),
    },
    ("update_todo", "completed"): {
        "build": lambda _s: "true",
        "check": _property_check("status of targetTodo to completed"),
    },
    ("update_todo", "canceled"): {
        "build": lambda _s: "true",
        "check": _property_check("status of targetTodo to canceled"),
    },
    ("update_todo", "heading"): {
        "extra_kwargs": {"list_id": "PROJHEADTARGET2"},
        "check": _url_key_check("heading"),
    },
    ("update_todo", "list_id"): {
        # No heading in this call (BASE_KWARGS alone, no extra_kwargs), so
        # update_todo takes the plain AppleScript project-move path
        # (`project id "..."`), not the URL-scheme list-id path that
        # list_id+heading together would use.
        "check": _property_value_check("project id"),
    },
    ("update_todo", "list_title"): {
        "build": lambda _s: SENTINEL_LIST_TITLE,
        "check": lambda fake, _needle: any(
            "project id" in s and RESOLVED_LIST_TITLE_PROJECT_ID in s for s in fake.execution_calls
        ),
    },

    # --- bulk_update_todos ---
    ("bulk_update_todos", "title"): {
        "check": _property_value_check("name of targetTodo to"),
    },
    ("bulk_update_todos", "notes"): {
        "check": _property_value_check("notes of targetTodo to"),
    },
    ("bulk_update_todos", "tags"): {
        "check": _property_value_check("tag names of targetTodo to"),
    },
    ("bulk_update_todos", "when"): {
        # Bulk 'when' is applied per-todo via schedule_todo_reliable
        # after the main bulk AppleScript write - same exploded-date
        # scheduling assertion as add_todo/update_todo's when.
        "build": lambda _s: "2031-06-20",
        "needle": "year of targetDate to 2031",
        "check": _property_value_check("schedule theTodo"),
    },
    ("bulk_update_todos", "deadline"): {
        "build": lambda _s: "2031-07-21",
        "needle": "year of deadlineDate to 2031",
        "check": _property_value_check("due date of targetTodo"),
    },
    ("bulk_update_todos", "completed"): {
        "build": lambda _s: "true",
        "check": _property_check("status of targetTodo to completed"),
    },
    ("bulk_update_todos", "canceled"): {
        "build": lambda _s: "true",
        "check": _property_check("status of targetTodo to canceled"),
    },

    # --- add_project ---
    ("add_project", "when"): {
        "build": lambda _s: "2031-08-22",
        "needle": "year of targetDate to 2031",
        "check": _property_value_check("schedule theTodo"),
    },
    ("add_project", "deadline"): {
        "build": lambda _s: "2031-09-23",
        "needle": "year of deadlineDate to 2031",
        "check": _property_value_check("due date of newProject"),
    },
    ("add_project", "tags"): {
        "check": _property_value_check("tag names of newProject"),
    },
    ("add_project", "area_id"): {
        # hq-rmh: area_id is now pre-resolved via things.py (_resolve_area)
        # before the write - the sentinel must resolve as a real area or
        # the call is rejected with NOT_FOUND before any AppleScript is
        # emitted at all.
        "things_patches": lambda sentinel: [
            patch(THINGS_GET_PATCH, return_value={"type": "area", "uuid": sentinel}),
        ],
        "check": _property_value_check("area id"),
    },
    ("add_project", "area_title"): {
        # hq-rmh: area_title is now pre-resolved via things.py
        # (_resolve_area) to its concrete area_id before the write, so the
        # emitted script uses 'area id "<uuid>"', not 'area "<title>"' -
        # assert the resolved uuid (not the raw title sentinel) reaches
        # the script.
        "needle": "RESOLVEDADDPROJECTAREATITLEID",
        "things_patches": lambda sentinel: [
            patch(
                THINGS_AREAS_PATCH,
                return_value=[{"uuid": "RESOLVEDADDPROJECTAREATITLEID", "title": sentinel}],
            ),
        ],
        "check": _property_value_check("area id"),
    },
    ("add_project", "todos"): {
        "build": lambda s: f"{s}\nSecond todo",
        "check": _property_value_check("make new to do in newProject"),
    },

    # --- update_project ---
    ("update_project", "title"): {
        "check": _property_value_check("name of targetProject"),
    },
    ("update_project", "notes"): {
        "check": _property_value_check("notes of targetProject"),
    },
    ("update_project", "when"): {
        "build": lambda _s: "2031-11-25",
        "needle": "year of targetDate to 2031",
        "check": _property_value_check("schedule theTodo"),
    },
    ("update_project", "tags"): {
        "check": _property_value_check("tag names of targetProject"),
    },
    ("update_project", "deadline"): {
        "build": lambda _s: "2031-10-24",
        "needle": "year of deadlineDate to 2031",
        "check": _property_value_check("due date of targetProject"),
    },
    ("update_project", "area_id"): {
        # hq-rmh: area_id is now pre-resolved via things.py (_resolve_area)
        # before the write - see add_project's area_id entry above.
        "things_patches": lambda sentinel: [
            patch(THINGS_GET_PATCH, return_value={"type": "area", "uuid": sentinel}),
        ],
        "check": _property_value_check("area id"),
    },
    ("update_project", "area_title"): {
        # hq-rmh: area_title is now pre-resolved via things.py
        # (_resolve_area) to its concrete area_id before the write - see
        # add_project's area_title entry above.
        "needle": "RESOLVEDUPDATEPROJECTAREATITLEID",
        "things_patches": lambda sentinel: [
            patch(
                THINGS_AREAS_PATCH,
                return_value=[{"uuid": "RESOLVEDUPDATEPROJECTAREATITLEID", "title": sentinel}],
            ),
        ],
        "check": _property_value_check("area id"),
    },
    ("update_project", "completed"): {
        "build": lambda _s: "true",
        "check": _property_check("status of targetProject to completed"),
    },
    ("update_project", "canceled"): {
        "build": lambda _s: "true",
        "check": _property_check("status of targetProject to canceled"),
    },

    # --- add_area ---
    ("add_area", "tags"): {
        "check": _property_value_check("tag names of newArea"),
    },

    # --- update_area ---
    ("update_area", "id"): {
        # update_area(title=None, tags=None) is a no-op "nothing to update"
        # short-circuit before any AppleScript write - supply a title so
        # the `id` sentinel actually reaches the `area id "..."` script.
        "extra_kwargs": {"title": "some new title"},
        "check": _property_value_check("area id"),
    },
    ("update_area", "title"): {
        "check": _property_value_check("name of targetArea"),
    },
    ("update_area", "tags"): {
        "check": _property_value_check("tag names of targetArea"),
    },

    # --- add_tags / remove_tags ---
    ("add_tags", "tags"): {
        "check": _property_value_check("set tag names of targetTodo to"),
    },
    ("remove_tags", "tags"): {
        # Seed REMOVETAGSTODOID's current tags to "keepme, <sentinel>" so
        # a correctly-functioning remove_tags(tags=sentinel) must emit
        # `set tag names of targetTodo to "keepme"` - keepme (untouched)
        # present AND the sentinel (removed) absent. This is a real
        # before/after check: if the tags param were dropped (e.g. the
        # kwarg silently became []), the write would instead re-set both
        # "keepme, <sentinel>" unchanged, which the "sentinel absent"
        # half of this check catches.
        "seed": lambda sentinel: (
            lambda fake: fake.current_tags_by_todo_id.__setitem__(
                "REMOVETAGSTODOID", f"keepme, {sentinel}"
            )
        ),
        "check": lambda fake, needle: any(
            "targetTodo" in s
            and 'tag names of targetTodo to "keepme"' in s
            and needle not in s
            for s in fake.execution_calls
        ),
    },

    # --- create_tag ---
    ("create_tag", "tag_name"): {
        "check": _property_value_check("make new tag with properties"),
    },

    # --- move_record ---
    ("move_record", "destination_list"): {
        "build": lambda _s: "project:SENTINELMOVEDEST",
        "needle": "SENTINELMOVEDEST",
        "check": _property_value_check("project id"),
    },

    # --- bulk_move_records ---
    ("bulk_move_records", "destination"): {
        "build": lambda _s: "project:SENTINELBULKMOVEDEST",
        "needle": "SENTINELBULKMOVEDEST",
        "check": _property_value_check("project id"),
    },

    # --- checklist tools ---
    ("add_checklist_items", "items"): {
        "build": lambda s: [s],
        "check": _url_key_check("append-checklist-items"),
    },
    ("prepend_checklist_items", "items"): {
        "build": lambda s: [s],
        "check": _url_key_check("prepend-checklist-items"),
    },
    ("replace_checklist_items", "items"): {
        "build": lambda s: [s],
        "check": _url_key_check("checklist-items"),
    },
}


# ===========================================================================
# IGNORED (continued): parameters that are plumbing-only, not backend-bound
# ===========================================================================

IGNORED.update(
    {
        # No further plumbing-only params identified beyond bulk_move_records's
        # max_concurrent (see IGNORED above) - every other declared parameter
        # on every mutating tool has a PARAM_ASSERTIONS entry or falls through
        # to the default alphanumeric-sentinel string check.
    }
)


# ===========================================================================
# Sentinel generation
# ===========================================================================


def _sentinel_for(tool: str, param: str) -> str:
    """Build a unique, alphanumeric-only sentinel for (tool, param).

    Alphanumeric-only so the sentinel survives both AppleScript string
    escaping (escape_string_inner only touches backslashes/quotes/control
    chars - alphanumerics pass through unchanged) and URL percent-encoding
    (urllib.parse.quote never encodes [A-Za-z0-9]).
    """
    return f"SENTINEL{tool.upper().replace('_', '')}{param.upper().replace('_', '')}X"


def _collect_tool_params() -> Dict[str, List[Tuple[str, dict]]]:
    """Return {tool_name: [(param_name, json_schema_property), ...]} for
    every tool currently registered on a fresh ThingsMCPServer, via the
    same FastMCP tool registry access as test_manifest_tools_sync.py."""
    server, _fake = _make_server()
    tools = asyncio.run(server.mcp.list_tools())
    result: Dict[str, List[Tuple[str, dict]]] = {}
    for t in tools:
        props = (t.parameters or {}).get("properties", {})
        result[t.name] = list(props.items())
    return result


_TOOL_PARAMS = _collect_tool_params()
_REGISTERED_TOOL_NAMES = set(_TOOL_PARAMS.keys())


def _build_param_cases() -> List[Any]:
    """(tool, param) pytest.param cases to exercise: every param of every
    mutating tool, minus IGNORED. Entries also present in DROPPED_PARAMS
    are KEPT (not skipped) but wrapped in
    pytest.param(..., marks=xfail(strict=True)) so a genuinely dropped
    parameter still runs and is visibly xfailing (and would loudly flip to
    an unexpected PASS - caught by strict=True - the moment it's fixed),
    rather than silently vanishing from the collected test list."""
    cases: List[Any] = []
    for tool in sorted(MUTATING_TOOLS):
        for param, _schema in _TOOL_PARAMS.get(tool, []):
            if (tool, param) in IGNORED:
                continue
            if (tool, param) in DROPPED_PARAMS:
                cases.append(
                    pytest.param(
                        tool,
                        param,
                        marks=pytest.mark.xfail(
                            reason=DROPPED_PARAMS[(tool, param)], strict=True
                        ),
                    )
                )
                continue
            cases.append((tool, param))
    return cases


PARAM_CASES = _build_param_cases()


def _param_case_id(case: Any) -> str:
    """ids= callback for PARAM_CASES entries, which are a mix of plain
    (tool, param) tuples and pytest.param(...) ParameterSet objects (for
    DROPPED_PARAMS entries) - ParameterSet.values holds the same
    (tool, param) tuple."""
    tool, param = case.values if isinstance(case, ParameterSet) else case
    return f"{tool}.{param}"


# ===========================================================================
# Tests
# ===========================================================================


def test_every_registered_tool_is_classified():
    """A tool registered on the live server must be classified as either a
    read tool or a write (mutating) tool in this file. This is what makes
    the generator data-driven: a newly added tool that is neither listed
    fails loudly instead of silently getting zero parameter-reach coverage.
    """
    unclassified = _REGISTERED_TOOL_NAMES - MUTATING_TOOLS - READ_TOOLS
    assert not unclassified, (
        f"classify this tool as read or write: {sorted(unclassified)} - "
        "add to MUTATING_TOOLS (with BASE_KWARGS + param coverage) or "
        "READ_TOOLS in tests/unit/test_parameter_reach.py"
    )

    # Also guard the reverse: every tool this file claims is mutating/read
    # must actually still be registered (catches stale entries after a
    # rename/removal).
    stale_mutating = MUTATING_TOOLS - _REGISTERED_TOOL_NAMES
    stale_read = READ_TOOLS - _REGISTERED_TOOL_NAMES
    assert not stale_mutating, f"MUTATING_TOOLS lists tools no longer registered: {sorted(stale_mutating)}"
    assert not stale_read, f"READ_TOOLS lists tools no longer registered: {sorted(stale_read)}"


def test_every_mutating_tool_has_base_kwargs():
    """Every tool in MUTATING_TOOLS must have a BASE_KWARGS entry, or every
    per-parameter call below would fail for an unrelated reason (missing
    required args) instead of testing the parameter in question."""
    missing = MUTATING_TOOLS - set(BASE_KWARGS.keys())
    assert not missing, f"BASE_KWARGS missing entries for: {sorted(missing)}"


@pytest.mark.parametrize("tool,param", PARAM_CASES, ids=[_param_case_id(c) for c in PARAM_CASES])
def test_parameter_reaches_backend(tool: str, param: str):
    """For (tool, param): call `tool` with BASE_KWARGS plus a unique
    sentinel value for `param`, and assert the sentinel (or its mapped
    AppleScript property / URL-scheme key) appears in at least one
    captured AppleScript script or URL-scheme call.
    """
    sentinel = _sentinel_for(tool, param)
    override = PARAM_ASSERTIONS.get((tool, param), {})

    build = override.get("build")
    value = build(sentinel) if build else sentinel
    # 'needle' overrides what the check function searches for, for cases
    # where 'build' transforms the sentinel into something else entirely
    # (e.g. move_record wraps it as "project:<needle>") - defaults to the
    # raw sentinel when the built value still contains it verbatim.
    needle = override.get("needle", sentinel)

    kwargs = dict(BASE_KWARGS[tool])
    kwargs.update(override.get("extra_kwargs", {}))
    kwargs[param] = value

    seed = override.get("seed")
    things_patches_builder = override.get("things_patches")
    extra_things_patches = things_patches_builder(sentinel) if things_patches_builder else None
    _result, fake = run_tool(
        tool, kwargs, seed=seed(sentinel) if seed else None,
        extra_things_patches=extra_things_patches,
    )

    check = override.get("check") or (lambda f, n: _default_check(f, n))
    assert check(fake, needle), (
        f"{tool}({param}={value!r}) did not reach any captured AppleScript "
        f"script or URL-scheme call.\n"
        f"Captured scripts:\n{fake.all_scripts_text()}\n"
        f"Captured URL calls: {fake.url_scheme_calls}"
    )

