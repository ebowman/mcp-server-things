"""hq-gbl.5: Input-space matrix for every WRITE tool at the MCP boundary.

Table-driven coverage of every declared parameter across value classes
(omitted / '' / whitespace-only / typical / special characters / invalid)
for every write tool listed in the bead: add_todo, update_todo,
bulk_update_todos, delete_todo, add_project, update_project, add_area,
update_area, add_tags, remove_tags, create_tag, move_record,
bulk_move_records, add_checklist_items, prepend_checklist_items,
replace_checklist_items.

Mocking strategy: reuse test_parameter_reach.py's
RecordingAppleScriptManager (patch targets, things.py lookup patches,
server construction) verbatim - it already solves script/URL capture and
things.py patching for every write path. Every call is driven through a
real ThingsMCPServer + in-memory fastmcp.Client(server.mcp), exercising
the real validation logic in server.py/tools_helpers/*.

Each CASES entry is (tool, args, expectation):
    - ok(route=..., contains=[...], url_contains={...})
        -> call succeeds (structured_content.success is not False); the
           call must have used the given capture route ('applescript',
           'url_add', 'url_update', or 'url_json'), and every string in
           `contains` must appear verbatim in the captured script text (for
           AppleScript-route cases) or in the JSON-encoded captured URL
           params (for URL-route cases). `url_contains`, if given, maps a
           URL param key to a required substring of its value.
    - write_error(code, no_capture=True/False)
        -> structured {"success": False, "error": code, ...} (UPPER_SNAKE,
           or the documented lower_snake exceptions for delete_todo). When
           no_capture is True (the default for auth-gate/pre-write
           validation errors), asserts NO AppleScript/URL call was made.
    - tool_error() -> pydantic rejects the input before the tool body runs
        (fastmcp raises ToolError).

A completeness check (TestCompleteness) at the bottom introspects every
write tool's declared parameters via Client.list_tools() and fails if any
(tool, param) pair has fewer than 3 CASES entries.

Known, deliberately-NOT-fixed bugs encoded as observed behavior (not
xfail - the live suite owns xfails per GBL_COMMON.md; comments cite the
owning bead):
  - hq-z5d: move_record destination handling for 'someday'/'anytime'
    fallback quirks are exercised as observed, not asserted as "correct".
  - hq-exe: add_checklist_items/prepend/replace enforce no cap on item
    count - 101 items is accepted (ok), not rejected.
  - hq-r87: a whitespace-only tag name (e.g. "  spacey  ") is accepted
    as a distinct tag after stripping - not rejected.
  - hq-nb1: the granular TagCreationPolicy env knobs
    (filter_silent/filter_warn) are dead - THINGS_MCP_AI_CAN_CREATE_TAGS
    only toggles the ALLOW_ALL/FAIL_ON_UNKNOWN 2-state switch. This file
    covers those two reachable states only; FILTER_SILENT/FILTER_WARN are
    exercised by constructing ThingsMCPConfig(tag_creation_policy=...)
    directly (bypassing the dead env path) where the bead explicitly
    contemplates that construction pattern.
  - hq-rmh: add_project/update_project/add_area area_title is emitted
    into the script unconditionally with no existence pre-check or
    rollback - an unknown area_title still produces a normal
    'set area of ... to area "<title>"' script from this server's
    perspective (Things itself would fail at runtime, out of scope for a
    mocked AppleScript manager).
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple
from unittest.mock import patch

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from things_mcp.config import ThingsMCPConfig, TagCreationPolicy
from things_mcp.server import ThingsMCPServer
from things_mcp.services.applescript_manager import AUTH_REQUIRING_ACTIONS, AUTH_TOKEN_HINT
from things_mcp.tools import ThingsTools

# ---------------------------------------------------------------------------
# Reuse test_parameter_reach.py's capture pattern verbatim (patch targets,
# recording fake, things.py lookup patches, server construction).
# ---------------------------------------------------------------------------

THINGS_GET_PATCH = "things_mcp.scheduling.todo_operations.things.get"
THINGS_PROJECTS_PATCH = "things_mcp.scheduling.todo_operations.things.projects"
THINGS_AREAS_PATCH = "things_mcp.scheduling.todo_operations.things.areas"
THINGS_TASKS_PATCH = "things_mcp.scheduling.todo_operations.things.tasks"
WRITE_OPS_THINGS_GET_PATCH = "things_mcp.tools_helpers.write_operations.things.get"

SENTINEL_LIST_TITLE = "SENTINELlisttitleXYZ"
RESOLVED_LIST_TITLE_PROJECT_ID = "RESOLVEDPROJECTID"
AMBIGUOUS_LIST_TITLE = "AMBIGUOUStitleXYZ"
UNKNOWN_LIST_TITLE = "UNKNOWNtitleDoesNotExistXYZ"


class RecordingAppleScriptManager:
    """Records every execute_applescript script and execute_url_scheme call.

    Copied (with minor extensions for delete_todo type-resolution and a
    configurable auth_token) from tests/unit/test_parameter_reach.py's
    RecordingAppleScriptManager - see that file's docstring for design
    rationale. Extended here with per-id current-location/type responses
    needed by move_record/delete_todo matrix cases.
    """

    def __init__(self, auth_token: Optional[str] = "SENTINELauthtokenABC") -> None:
        self.auth_token = auth_token
        self.execution_calls: List[str] = []
        self.url_scheme_calls: List[Tuple[str, Dict[str, Any]]] = []
        self._title_lookup_counts: Dict[str, int] = {}
        self.current_tags_by_todo_id: Dict[str, str] = {}
        # id -> "EXISTS" | "NOT_FOUND" for ValidationService.validate_todo_id
        # style existence checks embedded in some scripts; unused ids default
        # to EXISTS so a happy-path write proceeds without extra wiring.
        # Delimited-string response for TagValidationService._get_existing_tags
        # ("repeat with theTag in tags"). Defaults to "" (no existing tags in
        # Things) - override via a `seed` callback to pre-seed known tags so
        # a case can exercise the ALLOW_ALL "already-known" path without
        # tripping the existing/created double-count bug (see Discovered).
        self.existing_tags_output: str = ""

    async def execute_applescript(self, script: str, cache_key: Optional[str] = None) -> Dict[str, Any]:
        self.execution_calls.append(script)

        if "make new to do with properties" in script:
            return {"success": True, "output": "NEWTODOID"}
        if "make new project with properties" in script:
            return {"success": True, "output": "NEWPROJECTID"}
        if "make new area with properties" in script:
            return {"success": True, "output": "NEWAREAID"}
        if "make new tag with properties" in script:
            return {"success": True, "output": "CREATED"}

        if "to dos whose name is" in script:
            title_key = script.split("to dos whose name is", 1)[1][:120]
            count = self._title_lookup_counts.get(title_key, 0)
            self._title_lookup_counts[title_key] = count + 1
            if count == 0:
                return {"success": True, "output": ""}
            return {"success": True, "output": f"NEWURLTODOID{count}"}

        # --- add_project via URL scheme (##heading payload): pre/post-create
        # id lookup by title, same before/after snapshot pattern as to-dos
        # above but keyed on "projects whose name is".
        if "projects whose name is" in script:
            title_key = script.split("projects whose name is", 1)[1][:120]
            count = self._title_lookup_counts.get(title_key, 0)
            self._title_lookup_counts[title_key] = count + 1
            if count == 0:
                return {"success": True, "output": ""}
            return {"success": True, "output": f"NEWURLPROJECTID{count}"}

        if "return tag names of targetTodo" in script:
            todo_id = self._extract_to_do_id(script)
            output = self.current_tags_by_todo_id.get(todo_id, "")
            return {"success": True, "output": output}

        if "repeat with theTag in tags" in script:
            return {"success": True, "output": self.existing_tags_output}

        if "todoInfo" in script and "getCurrentLocation" in script:
            return {
                "success": True,
                "output": "id123, Some title, some notes, open, inbox",
            }

        if "move theTodo to list" in script or "set project of theTodo to" in script or "set area of theTodo to" in script:
            return {"success": True, "output": "MOVED to destination"}

        if "successCount" in script:
            return {"success": True, "output": "successCount:2, errors:{}"}

        if 'return "updated"' in script:
            return {"success": True, "output": "updated"}

        if "delete targetTodo" in script:
            return {"success": True, "output": "deleted"}

        if "scheduled_relative" in script or "targetDate" in script:
            return {"success": True, "output": "scheduled_relative"}

        return {"success": True, "output": "mock_output"}

    async def execute_url_scheme(self, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Faithfully emulate the real AppleScriptManager.execute_url_scheme
        # auth gate (services/applescript_manager.py) - 'update'/
        # 'update-project' actions are refused (and NOT recorded as a
        # capture) when no auth token is configured, so auth-gate CASES
        # entries can assert no_capture=True.
        if action in AUTH_REQUIRING_ACTIONS and not self.auth_token:
            return {
                "success": False,
                "error": "AUTH_TOKEN_NOT_CONFIGURED",
                "message": "Things URL-scheme auth token not configured",
                "hint": AUTH_TOKEN_HINT,
            }
        self.url_scheme_calls.append((action, dict(parameters or {})))
        return {"success": True, "url": f"things:///{action}", "message": f"Successfully executed {action} action"}

    @staticmethod
    def _extract_to_do_id(script: str) -> Optional[str]:
        match = re.search(r'to do id "([^"]*)"', script)
        return match.group(1) if match else None

    def all_scripts_text(self) -> str:
        return "\n".join(self.execution_calls)

    def all_url_params(self) -> List[Dict[str, Any]]:
        return [params for _action, params in self.url_scheme_calls]

    def any_capture(self) -> bool:
        return bool(self.execution_calls) or bool(self.url_scheme_calls)


# ---------------------------------------------------------------------------
# things.py lookup patching (id -> type), used to distinguish
# project/area/heading/tag/unknown resolution for delete_todo and
# list_id/list_title resolution for add_todo/update_todo/add_project/
# update_project.
# ---------------------------------------------------------------------------

# Ids that things.get() (todo_operations' proxy) should resolve as an area,
# so list_id="AREATARGET1" resolves to an area rather than the default
# project fallback used by every other sentinel id.
AREA_TARGET_ID = "AREATARGETID1"
COMPLETED_PROJECT_ID = "COMPLETEDPROJECTID1"
CANCELED_HEADING_TITLE = "Canceled Heading"
# things.get() resolves cleanly but finds nothing for this id -
# _resolve_list_id's "definitively unknown" branch (NOT_FOUND).
UNKNOWN_LIST_ID = "UNKNOWNLISTIDDOESNOTEXIST"
# things.get() itself raises for this id (simulating an unreadable Things
# database / missing Full Disk Access) - _resolve_list_id's fallback branch,
# which treats list_id as a project id and proceeds via AppleScript rather
# than refusing the write (CLAUDE.md "list_id fallback when the Things
# database is unreadable").
RAISING_LIST_ID = "RAISINGLISTIDCAUSESLOOKUPERROR"


class _SimulatedThingsLookupError(Exception):
    """Raised by _todo_ops_things_get for RAISING_LIST_ID to simulate an
    unreadable Things database / missing Full Disk Access."""


def _todo_ops_things_get(uuid: str, **kwargs: Any) -> Dict[str, Any]:
    if uuid == AREA_TARGET_ID:
        return {"type": "area", "uuid": uuid}
    if uuid == COMPLETED_PROJECT_ID:
        return {"type": "project", "uuid": uuid, "status": "completed"}
    if uuid == UNKNOWN_LIST_ID:
        return None
    if uuid == RAISING_LIST_ID:
        raise _SimulatedThingsLookupError("simulated things.py lookup failure")
    return {"type": "project", "uuid": uuid}


def _write_ops_things_get(uuid: str, **kwargs: Any) -> Optional[Dict[str, Any]]:
    """Backs delete_todo()'s _resolve_delete_item_type() and any other
    write_operations.things.get() call, keyed by distinctive sentinel ids
    so a single patch can serve todo/project/heading/area/tag/unknown
    delete_todo cases."""
    mapping = {
        "DELTARGET-TODO": {"type": "to-do"},
        "DELTARGET-PROJECT": {"type": "project"},
        "DELTARGET-HEADING": {"type": "heading"},
        "DELTARGET-AREA": {"type": "area"},
        "DELTARGET-TAG": {"type": "tag"},
    }
    if uuid in mapping:
        return mapping[uuid]
    if uuid == "DELTARGET-UNKNOWN":
        return None
    # Default fallback for any other id used incidentally by non-delete
    # cases sharing this patch target (e.g. plain to-do writes).
    return {"type": "to-do"}


def _patched_things_lookups():
    """Patch context managers for things.py lookups, extending
    test_parameter_reach.py's `_patched_things_lookups` with an area-typed
    sentinel id and a completed-project sentinel id (both routed through
    `_todo_ops_things_get`), plus a real router for delete_todo's separate
    write_operations proxy."""
    return [
        patch(THINGS_GET_PATCH, side_effect=_todo_ops_things_get),
        patch(
            THINGS_PROJECTS_PATCH,
            return_value=[
                {"uuid": RESOLVED_LIST_TITLE_PROJECT_ID, "title": SENTINEL_LIST_TITLE},
                {"uuid": "AMBIGUOUS-PROJECT-1", "title": AMBIGUOUS_LIST_TITLE},
                {"uuid": "AMBIGUOUS-PROJECT-2", "title": AMBIGUOUS_LIST_TITLE},
            ],
        ),
        patch(THINGS_AREAS_PATCH, return_value=[]),
        patch(THINGS_TASKS_PATCH, return_value=[]),
        patch(WRITE_OPS_THINGS_GET_PATCH, side_effect=_write_ops_things_get),
    ]


def _make_server(auth_token: Optional[str] = "SENTINELauthtokenABC", tag_policy: Optional[TagCreationPolicy] = None) -> Tuple[ThingsMCPServer, RecordingAppleScriptManager]:
    """Build a real ThingsMCPServer wired to a RecordingAppleScriptManager.

    ai_can_create_tags=True by default (ALLOW_ALL) so ordinary write cases
    aren't incidentally blocked by tag policy - tag-policy-specific CASES
    below construct their own server with a different config. `tag_policy`,
    if given, constructs ThingsMCPConfig(tag_creation_policy=...) directly
    (hq-nb1: the granular FILTER_SILENT/FILTER_WARN env knobs are dead, so
    this is the only way to reach those states in-process).
    """
    server = ThingsMCPServer()
    fake = RecordingAppleScriptManager(auth_token=auth_token)
    if tag_policy is not None:
        # ThingsMCPConfig's ai_can_create_tags/tag_creation_policy
        # field_validators are coupled by construction-time cross-field
        # logic (ai_can_create_tags declared first): passing
        # tag_creation_policy=X at construction, however it's combined with
        # ai_can_create_tags, only ever lands on ALLOW_ALL (if
        # ai_can_create_tags=True) or FILTER_WARN (if False/omitted) -
        # FAIL_ON_UNKNOWN/FILTER_SILENT are unreachable via the constructor
        # at all (a real config-coupling gap beyond hq-nb1's dead-env-knob
        # note - filed separately, see Discovered). Constructing with
        # ai_can_create_tags=True and then overwriting tag_creation_policy
        # via plain attribute assignment (pydantic v2 does not re-run
        # field_validators on assignment) is the only way to reach every
        # policy state directly.
        config = ThingsMCPConfig(ai_can_create_tags=True)
        config.tag_creation_policy = tag_policy
        config.ai_can_create_tags = (tag_policy == TagCreationPolicy.ALLOW_ALL)
    else:
        config = ThingsMCPConfig(ai_can_create_tags=True)
    server.tools = ThingsTools(fake, config)
    server.config.ai_can_create_tags = config.ai_can_create_tags
    return server, fake


async def _call_tool(server: ThingsMCPServer, tool_name: str, kwargs: Dict[str, Any]):
    client = Client(server.mcp)
    async with client:
        return await client.call_tool(tool_name, kwargs)


def run_tool(
    tool_name: str,
    kwargs: Dict[str, Any],
    auth_token: Optional[str] = "SENTINELauthtokenABC",
    tag_policy: Optional[TagCreationPolicy] = None,
    seed: Optional[Callable[[RecordingAppleScriptManager], None]] = None,
) -> Tuple[Any, RecordingAppleScriptManager]:
    server, fake = _make_server(auth_token=auth_token, tag_policy=tag_policy)
    if seed:
        seed(fake)
    patches = _patched_things_lookups()
    for p in patches:
        p.start()
    try:
        result = asyncio.run(_call_tool(server, tool_name, kwargs))
    finally:
        for p in patches:
            p.stop()
    return result, fake


# ---------------------------------------------------------------------------
# Expectation markers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ok:
    kind: str = "ok"
    route: Optional[str] = None  # 'applescript' | 'url_add' | 'url_update' | 'url_json'
    contains: Tuple[str, ...] = ()
    url_contains: Optional[Dict[str, str]] = None


@dataclass(frozen=True)
class WriteErrorExpectation:
    kind: str = "write_error"
    code: str = ""
    no_capture: bool = True


@dataclass(frozen=True)
class ToolErrorExpectation:
    kind: str = "tool_error"


def ok(route: Optional[str] = None, contains: Tuple[str, ...] = (), url_contains: Optional[Dict[str, str]] = None) -> Ok:
    return Ok(route=route, contains=contains, url_contains=url_contains)


def write_error(code: str, no_capture: bool = True) -> WriteErrorExpectation:
    return WriteErrorExpectation(code=code, no_capture=no_capture)


def tool_error() -> ToolErrorExpectation:
    return ToolErrorExpectation()


# ---------------------------------------------------------------------------
# CASES table: (tool, args, expectation, options)
#
# options may include:
#   auth_token: override the fake manager's auth token (e.g. None to
#       simulate no configured token, for the auth-gate cases).
#   tag_policy: TagCreationPolicy to construct the server config with
#       directly (bypassing ai_can_create_tags).
#   seed: seed callback passed to run_tool.
# ---------------------------------------------------------------------------

CASES: List[Tuple[str, Dict[str, Any], Any, Dict[str, Any]]] = []


def add(tool: str, args: Dict[str, Any], expectation: Any, **options: Any) -> None:
    CASES.append((tool, args, expectation, options))


LONG_2000 = "x" * 2000
SPECIAL_CHARS = 'he said "hi" \\ back\\slash, comma, tab\tend'
NEWLINE_TEXT = "line one\nline two\nline three"
UNICODE_EMOJI = "héllo wörld 🎉 日本語"


# ===========================================================================
# add_todo
# ===========================================================================

add("add_todo", {"title": "Basic todo"}, ok(route="applescript", contains=["name:\"Basic todo\""]))
add("add_todo", {"title": "  "}, ok(route="applescript"))  # min_length=1 does not strip whitespace; "  " passes pydantic and is sent through as-is
add("add_todo", {"title": SPECIAL_CHARS}, ok(route="applescript", contains=['he said \\"hi\\" \\\\ back\\\\slash, comma']))
add("add_todo", {"title": NEWLINE_TEXT}, ok(route="applescript", contains=["line one\\nline two\\nline three"]))
add("add_todo", {"title": UNICODE_EMOJI}, ok(route="applescript", contains=[UNICODE_EMOJI]))
add("add_todo", {"title": LONG_2000}, ok(route="applescript", contains=[LONG_2000]))

add("add_todo", {"title": "T", "notes": None}, ok(route="applescript"))
add("add_todo", {"title": "T", "notes": ""}, ok(route="applescript"))
add("add_todo", {"title": "T", "notes": "   "}, ok(route="applescript"))
add("add_todo", {"title": "T", "notes": "Some notes"}, ok(route="applescript", contains=["Some notes"]))
add("add_todo", {"title": "T", "notes": SPECIAL_CHARS}, ok(route="applescript", contains=['he said \\"hi\\"']))
add("add_todo", {"title": "T", "notes": NEWLINE_TEXT}, ok(route="applescript", contains=["line one\\nline two"]))

add("add_todo", {"title": "T", "tags": None}, ok(route="applescript"))
add("add_todo", {"title": "T", "tags": ""}, ok(route="applescript"))
add("add_todo", {"title": "T", "tags": " , "}, ok(route="applescript"))
add("add_todo", {"title": "T", "tags": "a,b"}, ok(route="applescript", contains=["tag names of newTodo to \"a, b\""]))
add("add_todo", {"title": "T", "tags": "a, b"}, ok(route="applescript", contains=["tag names of newTodo to \"a, b\""]))  # stripped: space after comma has no effect on output

for w, exp in [
    ("today", ok(route="applescript")),
    ("tomorrow", ok(route="applescript")),
    ("yesterday", ok(route="applescript")),  # observed: accepted as a relative date, not rejected
    ("someday", ok(route="applescript")),
    ("anytime", ok(route="applescript")),
    ("evening", ok(route="url_add")),
    ("tonight", ok(route="url_add")),
    ("2031-01-15", ok(route="applescript")),
    ("2031-01-15@14:30", ok(route="applescript")),
    ("bogus", write_error("INVALID_WHEN")),
    ("", ok(route="applescript")),  # falsy -> no when applied at all, still AppleScript create
    (" ", write_error("VALIDATION_ERROR")),
]:
    add("add_todo", {"title": "T", "when": w}, exp)

for d, exp in [
    ("2031-01-15", ok(route="applescript", contains=["due date of newTodo"])),
    ("today", write_error("INVALID_DEADLINE")),
    ("bogus", write_error("INVALID_DEADLINE")),
    ("", ok(route="applescript")),
]:
    add("add_todo", {"title": "T", "deadline": d}, exp)

add("add_todo", {"title": "T", "list_id": None}, ok(route="applescript"))
add("add_todo", {"title": "T", "list_id": ""}, ok(route="applescript"))
add("add_todo", {"title": "T", "list_id": "PROJ123"}, ok(route="applescript", contains=["project id \"PROJ123\""]))
add("add_todo", {"title": "T", "list_id": AREA_TARGET_ID}, ok(route="applescript", contains=[f'area id "{AREA_TARGET_ID}"']))
# things.get() resolves cleanly but reports nothing -> definitively unknown
# list_id, rejected before any write (_resolve_list_id's NOT_FOUND branch).
add("add_todo", {"title": "T", "list_id": UNKNOWN_LIST_ID}, write_error("NOT_FOUND"))
# things.get() itself raises (simulated unreadable Things DB) -> falls back
# to treating list_id as a project id via AppleScript rather than refusing
# the write (CLAUDE.md "list_id fallback when the Things database is
# unreadable").
add(
    "add_todo",
    {"title": "T", "list_id": RAISING_LIST_ID},
    ok(route="applescript", contains=[f'project id "{RAISING_LIST_ID}"']),
)
# A list_id resolving to a completed project is rejected before any write
# (adding into it would reopen the project) - see CLAUDE.md's
# TARGET_COMPLETED guard.
add("add_todo", {"title": "T", "list_id": COMPLETED_PROJECT_ID}, write_error("TARGET_COMPLETED"))

add("add_todo", {"title": "T", "list_title": None}, ok(route="applescript"))
add("add_todo", {"title": "T", "list_title": ""}, ok(route="applescript"))
add("add_todo", {"title": "T", "list_title": SENTINEL_LIST_TITLE}, ok(route="applescript", contains=[RESOLVED_LIST_TITLE_PROJECT_ID]))
add("add_todo", {"title": "T", "list_title": AMBIGUOUS_LIST_TITLE}, write_error("AMBIGUOUS_TARGET"))
add("add_todo", {"title": "T", "list_title": UNKNOWN_LIST_TITLE}, write_error("NOT_FOUND"))

add("add_todo", {"title": "T", "heading": None}, ok(route="applescript"))
add("add_todo", {"title": "T", "heading": "SomeHeading", "list_id": "PROJ123"}, ok(route="url_add", url_contains={"heading": "SomeHeading"}))
add("add_todo", {"title": "T", "heading": "SomeHeading"}, write_error("VALIDATION_ERROR"))  # no list_id/list_title -> requires a target project

add("add_todo", {"title": "T", "checklist_items": []}, ok(route="applescript"))
add("add_todo", {"title": "T", "checklist_items": ["one"]}, ok(route="url_add", url_contains={"checklist-items": "one"}))
add("add_todo", {"title": "T", "checklist_items": [f"item{i}" for i in range(100)]}, ok(route="url_add"))
add("add_todo", {"title": "T", "checklist_items": [f"item{i}" for i in range(101)]}, ok(route="url_add"))  # hq-exe: no cap enforced


# ===========================================================================
# update_todo
# ===========================================================================

add("update_todo", {"id": "TODOID1"}, ok(route="applescript", contains=['to do id "TODOID1"']))
add("update_todo", {"id": ""}, write_error("VALIDATION_ERROR"))
add("update_todo", {"id": "   "}, write_error("VALIDATION_ERROR"))
add("update_todo", {"id": SPECIAL_CHARS}, ok(route="applescript"))

add("update_todo", {"id": "TODOID1", "title": None}, ok(route="applescript"))
add("update_todo", {"id": "TODOID1", "title": ""}, write_error("VALIDATION_ERROR"))
add("update_todo", {"id": "TODOID1", "title": "   "}, write_error("VALIDATION_ERROR"))
add("update_todo", {"id": "TODOID1", "title": "New Title"}, ok(route="applescript", contains=["name of targetTodo to \"New Title\""]))
add("update_todo", {"id": "TODOID1", "title": SPECIAL_CHARS}, ok(route="applescript", contains=['name of targetTodo to "he said \\"hi\\"']))
add("update_todo", {"id": "TODOID1", "title": UNICODE_EMOJI}, ok(route="applescript", contains=[UNICODE_EMOJI]))

add("update_todo", {"id": "TODOID1", "notes": None}, ok(route="applescript"))
add("update_todo", {"id": "TODOID1", "notes": ""}, ok(route="applescript", contains=['notes of targetTodo to ""']))
add("update_todo", {"id": "TODOID1", "notes": "   "}, ok(route="applescript", contains=['notes of targetTodo to ""']))  # whitespace-only treated as explicit clear (CLAUDE.md)
add("update_todo", {"id": "TODOID1", "notes": NEWLINE_TEXT}, ok(route="applescript", contains=["line one\\nline two\\nline three"]))
add("update_todo", {"id": "TODOID1", "notes": LONG_2000}, ok(route="applescript", contains=[LONG_2000]))

add("update_todo", {"id": "TODOID1", "tags": None}, ok(route="applescript"))
add("update_todo", {"id": "TODOID1", "tags": ""}, ok(route="applescript", contains=['tag names of targetTodo to ""']))
add("update_todo", {"id": "TODOID1", "tags": " , "}, ok(route="applescript", contains=['tag names of targetTodo to ""']))
add("update_todo", {"id": "TODOID1", "tags": "a,b"}, ok(route="applescript", contains=['tag names of targetTodo to "a, b"']))
add("update_todo", {"id": "TODOID1", "tags": "a, b"}, ok(route="applescript", contains=['tag names of targetTodo to "a, b"']))

for w, exp in [
    ("today", ok(route="applescript")),
    ("tomorrow", ok(route="applescript")),
    ("yesterday", ok(route="applescript")),  # observed: accepted as a relative date, not rejected
    ("someday", ok(route="applescript")),
    ("anytime", ok(route="applescript")),
    ("evening", ok(route="url_update")),
    ("tonight", ok(route="url_update")),
    ("2031-02-15", ok(route="applescript")),
    ("2031-02-15@09:00", ok(route="applescript")),
    ("bogus", write_error("INVALID_WHEN")),
    ("", write_error("VALIDATION_ERROR")),
    (" ", write_error("VALIDATION_ERROR")),
]:
    add("update_todo", {"id": "TODOID1", "when": w}, exp)

for d, exp in [
    ("2031-02-15", ok(route="applescript", contains=["due date of targetTodo"])),
    ("today", write_error("INVALID_DEADLINE")),
    ("bogus", write_error("INVALID_DEADLINE")),
    ("", ok(route="applescript", contains=["due date of targetTodo"])),
]:
    add("update_todo", {"id": "TODOID1", "deadline": d}, exp)

# completed / canceled full 3x3
for completed, canceled, expect_marker in [
    ("true", "true", "status of targetTodo to canceled"),
    ("true", "false", "status of targetTodo to completed"),
    ("true", None, "status of targetTodo to completed"),
    ("false", "true", "status of targetTodo to canceled"),
    ("false", "false", "status of targetTodo to open"),
    ("false", None, "status of targetTodo to open"),
    (None, "true", "status of targetTodo to canceled"),
    (None, "false", "status of targetTodo to open"),
]:
    args = {"id": "TODOID1"}
    if completed is not None:
        args["completed"] = completed
    if canceled is not None:
        args["canceled"] = canceled
    add("update_todo", args, ok(route="applescript", contains=[expect_marker]))
add("update_todo", {"id": "TODOID1"}, ok(route="applescript"))  # both omitted -> unchanged, still a valid no-status-change update

for bad in ["True", "FALSE", "yes", "1"]:
    if bad in ("True", "FALSE"):
        add("update_todo", {"id": "TODOID1", "completed": bad}, ok(route="applescript"))
    else:
        add("update_todo", {"id": "TODOID1", "completed": bad}, write_error("VALIDATION_ERROR"))
for bad in ["yes", "1"]:
    add("update_todo", {"id": "TODOID1", "canceled": bad}, write_error("VALIDATION_ERROR"))
add("update_todo", {"id": "TODOID1", "completed": True}, tool_error())  # JSON bool rejected by pydantic (Optional[str])

add("update_todo", {"id": "TODOID1", "heading": "H", "list_id": "PROJHEAD1"}, ok(route="url_update", url_contains={"heading": "H"}))
add("update_todo", {"id": "TODOID1", "heading": "H"}, ok(route="url_update", url_contains={"heading": "H"}))  # falls back to current-project resolution
add("update_todo", {"id": "TODOID1", "heading": ""}, write_error("INVALID_HEADING"))
add("update_todo", {"id": "TODOID1", "heading": "   "}, write_error("INVALID_HEADING"))

add("update_todo", {"id": "TODOID1", "list_id": None}, ok(route="applescript"))
add("update_todo", {"id": "TODOID1", "list_id": "PROJ456"}, ok(route="applescript", contains=['project id "PROJ456"']))
add("update_todo", {"id": "TODOID1", "list_id": AREA_TARGET_ID}, ok(route="applescript", contains=[f'area id "{AREA_TARGET_ID}"']))
# things.get() resolves cleanly but reports nothing -> definitively unknown
# list_id, rejected before any write (_resolve_list_id's NOT_FOUND branch,
# shared with add_todo).
add("update_todo", {"id": "TODOID1", "list_id": UNKNOWN_LIST_ID}, write_error("NOT_FOUND"))
# things.get() itself raises (simulated unreadable Things DB) -> falls back
# to treating list_id as a project id via AppleScript, same fallback as
# add_todo (CLAUDE.md "list_id fallback when the Things database is
# unreadable").
add(
    "update_todo",
    {"id": "TODOID1", "list_id": RAISING_LIST_ID},
    ok(route="applescript", contains=[f'project id "{RAISING_LIST_ID}"']),
)
# A list_id resolving to a completed project is rejected before any write
# (moving into it would reopen the project).
add("update_todo", {"id": "TODOID1", "list_id": COMPLETED_PROJECT_ID}, write_error("TARGET_COMPLETED"))
# Heading-into-completed-project variant: list_id (via heading path) also
# resolves to a completed project -> TARGET_COMPLETED before any write,
# same guard as the non-heading move above but reached through
# _check_project_target_not_completed inside the heading branch.
add(
    "update_todo",
    {"id": "TODOID1", "heading": "H", "list_id": COMPLETED_PROJECT_ID},
    write_error("TARGET_COMPLETED"),
)

add("update_todo", {"id": "TODOID1", "list_title": None}, ok(route="applescript"))
add("update_todo", {"id": "TODOID1", "list_title": SENTINEL_LIST_TITLE}, ok(route="applescript", contains=[RESOLVED_LIST_TITLE_PROJECT_ID]))
add("update_todo", {"id": "TODOID1", "list_title": AMBIGUOUS_LIST_TITLE}, write_error("AMBIGUOUS_TARGET"))
add("update_todo", {"id": "TODOID1", "list_title": UNKNOWN_LIST_TITLE}, write_error("NOT_FOUND"))

# auth gate: heading/evening require the URL-scheme auth token
add("update_todo", {"id": "TODOID1", "heading": "H", "list_id": "PROJHEAD1"}, write_error("AUTH_TOKEN_NOT_CONFIGURED"), auth_token=None)
add("update_todo", {"id": "TODOID1", "when": "evening"}, write_error("AUTH_TOKEN_NOT_CONFIGURED"), auth_token=None)
add("update_todo", {"id": "TODOID1", "when": "tonight"}, write_error("AUTH_TOKEN_NOT_CONFIGURED"), auth_token=None)
# no-partial-update-on-failed-gate: title in the same call must not apply either
add(
    "update_todo",
    {"id": "TODOID1", "heading": "H", "list_id": "PROJHEAD1", "title": "Should Not Apply"},
    write_error("AUTH_TOKEN_NOT_CONFIGURED"),
    auth_token=None,
)


# ===========================================================================
# bulk_update_todos
# ===========================================================================

add("bulk_update_todos", {"todo_ids": "T1,T2,T3"}, ok(route="applescript", contains=["T1", "T2", "T3"]))
add("bulk_update_todos", {"todo_ids": ""}, write_error("NO_TODO_IDS"))
add("bulk_update_todos", {"todo_ids": ",,"}, write_error("NO_TODO_IDS"))
add("bulk_update_todos", {"todo_ids": "a"}, ok(route="applescript", contains=["a"]))
add("bulk_update_todos", {"todo_ids": "a,b,c"}, ok(route="applescript", contains=["a", "b", "c"]))

add("bulk_update_todos", {"todo_ids": "T1,T2", "title": None}, ok(route="applescript"))
add("bulk_update_todos", {"todo_ids": "T1,T2", "title": ""}, write_error("VALIDATION_ERROR"))
add("bulk_update_todos", {"todo_ids": "T1,T2", "title": "   "}, write_error("VALIDATION_ERROR"))
add("bulk_update_todos", {"todo_ids": "T1,T2", "title": "Bulk Title"}, ok(route="applescript", contains=["name of targetTodo to \"Bulk Title\""]))

add("bulk_update_todos", {"todo_ids": "T1,T2", "notes": None}, ok(route="applescript"))
add("bulk_update_todos", {"todo_ids": "T1,T2", "notes": ""}, ok(route="applescript", contains=['notes of targetTodo to ""']))
add("bulk_update_todos", {"todo_ids": "T1,T2", "notes": "   "}, ok(route="applescript", contains=['notes of targetTodo to ""']))
add("bulk_update_todos", {"todo_ids": "T1,T2", "notes": NEWLINE_TEXT}, ok(route="applescript", contains=["line one\\nline two"]))

add("bulk_update_todos", {"todo_ids": "T1,T2", "tags": None}, ok(route="applescript"))
add("bulk_update_todos", {"todo_ids": "T1,T2", "tags": ""}, ok(route="applescript", contains=['tag names of targetTodo to ""']))
add("bulk_update_todos", {"todo_ids": "T1,T2", "tags": " , "}, ok(route="applescript", contains=['tag names of targetTodo to ""']))
# Tags pre-seeded as already-existing (via seed) so the ALLOW_ALL policy's
# existing+created double-count bug (see Discovered) doesn't trigger -
# this case asserts the plain pass-through property/value, not the bug.
add(
    "bulk_update_todos",
    {"todo_ids": "T1,T2", "tags": "a,b"},
    ok(route="applescript", contains=['tag names of targetTodo to "a, b"']),
    seed=lambda fake: setattr(fake, "existing_tags_output", "a|DELIMITER|b"),
)

for w, exp in [
    ("today", ok(route="applescript")),
    ("tomorrow", ok(route="applescript")),
    ("someday", ok(route="applescript")),
    ("anytime", ok(route="applescript")),
    ("evening", ok(route="url_update")),
    ("tonight", ok(route="url_update")),
    ("2031-03-15", ok(route="applescript")),
    ("bogus", write_error("INVALID_WHEN")),
    ("", write_error("VALIDATION_ERROR")),
    (" ", write_error("VALIDATION_ERROR")),
]:
    add("bulk_update_todos", {"todo_ids": "T1,T2", "when": w}, exp)

for d, exp in [
    ("2031-03-15", ok(route="applescript", contains=["due date of targetTodo"])),
    ("today", write_error("INVALID_DEADLINE")),
    ("", ok(route="applescript", contains=["due date of targetTodo"])),
]:
    add("bulk_update_todos", {"todo_ids": "T1,T2", "deadline": d}, exp)

for completed, canceled, expect_marker in [
    ("true", "true", "status of targetTodo to canceled"),
    ("true", "false", "status of targetTodo to completed"),
    ("false", "true", "status of targetTodo to canceled"),
    ("false", "false", "status of targetTodo to open"),
]:
    add(
        "bulk_update_todos",
        {"todo_ids": "T1,T2", "completed": completed, "canceled": canceled},
        ok(route="applescript", contains=[expect_marker]),
    )
add("bulk_update_todos", {"todo_ids": "T1,T2", "completed": "True"}, ok(route="applescript"))
add("bulk_update_todos", {"todo_ids": "T1,T2", "completed": "yes"}, write_error("VALIDATION_ERROR"))
add("bulk_update_todos", {"todo_ids": "T1,T2", "canceled": "1"}, write_error("VALIDATION_ERROR"))
add("bulk_update_todos", {"todo_ids": "T1,T2", "completed": True}, tool_error())

add("bulk_update_todos", {"todo_ids": "T1,T2", "when": "evening"}, write_error("AUTH_TOKEN_NOT_CONFIGURED"), auth_token=None)


# ===========================================================================
# delete_todo
# ===========================================================================

add("delete_todo", {"todo_id": "DELTARGET-TODO"}, ok(route="applescript", contains=['to do id "DELTARGET-TODO"']))
add("delete_todo", {"todo_id": "DELTARGET-PROJECT"}, ok(route="applescript", contains=['project id "DELTARGET-PROJECT"']))
add("delete_todo", {"todo_id": "DELTARGET-HEADING"}, write_error("not_deletable"))
add("delete_todo", {"todo_id": "DELTARGET-AREA"}, write_error("not_deletable"))
add("delete_todo", {"todo_id": "DELTARGET-TAG"}, write_error("not_deletable"))
add("delete_todo", {"todo_id": "DELTARGET-UNKNOWN"}, write_error("not_found"))
add("delete_todo", {"todo_id": ""}, write_error("VALIDATION_ERROR"))
add("delete_todo", {"todo_id": "   "}, write_error("VALIDATION_ERROR"))


# ===========================================================================
# add_project
# ===========================================================================

add("add_project", {"title": "Proj title"}, ok(route="applescript", contains=["name:\"Proj title\""]))
add("add_project", {"title": SPECIAL_CHARS}, ok(route="applescript", contains=['he said \\"hi\\"']))
add("add_project", {"title": NEWLINE_TEXT}, ok(route="applescript", contains=["line one\\nline two"]))
add("add_project", {"title": UNICODE_EMOJI}, ok(route="applescript", contains=[UNICODE_EMOJI]))
add("add_project", {"title": LONG_2000}, ok(route="applescript", contains=[LONG_2000]))

add("add_project", {"title": "P", "notes": None}, ok(route="applescript"))
add("add_project", {"title": "P", "notes": ""}, ok(route="applescript"))
add("add_project", {"title": "P", "notes": "   "}, ok(route="applescript"))
add("add_project", {"title": "P", "notes": "Proj notes"}, ok(route="applescript", contains=["Proj notes"]))

add("add_project", {"title": "P", "tags": None}, ok(route="applescript"))
add("add_project", {"title": "P", "tags": ""}, ok(route="applescript"))
add("add_project", {"title": "P", "tags": "a,b"}, ok(route="applescript", contains=["tag names of newProject to \"a, b\""]))

for w, exp in [
    ("today", ok(route="applescript")),
    ("someday", ok(route="applescript")),
    ("anytime", ok(route="applescript")),
    ("2031-04-15", ok(route="applescript")),
    ("bogus", write_error("INVALID_WHEN")),
    ("", ok(route="applescript")),
]:
    add("add_project", {"title": "P", "when": w}, exp)

for d, exp in [
    ("2031-04-15", ok(route="applescript", contains=["due date of newProject"])),
    ("today", write_error("INVALID_DEADLINE")),
    ("", ok(route="applescript")),
]:
    add("add_project", {"title": "P", "deadline": d}, exp)

add("add_project", {"title": "P", "area_id": None}, ok(route="applescript"))
add("add_project", {"title": "P", "area_id": "AREAID1"}, ok(route="applescript", contains=['area id "AREAID1"']))
add("add_project", {"title": "P", "area_id": ""}, ok(route="applescript"))
add("add_project", {"title": "P", "area_title": None}, ok(route="applescript"))
add("add_project", {"title": "P", "area_title": "Some Area"}, ok(route="applescript", contains=['area "Some Area"']))
add("add_project", {"title": "P", "area_title": "DoesNotExistArea"}, ok(route="applescript", contains=['area "DoesNotExistArea"']))  # hq-rmh: emitted as-is, no rollback

add("add_project", {"title": "P", "todos": None}, ok(route="applescript"))
add("add_project", {"title": "P", "todos": ""}, ok(route="applescript"))
add("add_project", {"title": "P", "todos": "Task 1\nTask 2"}, ok(route="applescript", contains=["Task 1", "Task 2"]))
add("add_project", {"title": "P", "todos": "##Phase 1\nTask A"}, ok(route="url_json", url_contains={"data": "Phase 1"}))


# ===========================================================================
# update_project
# ===========================================================================

add("update_project", {"id": "PROJECTID1"}, ok(route="applescript", contains=['project id "PROJECTID1"']))
add("update_project", {"id": ""}, write_error("VALIDATION_ERROR"))
add("update_project", {"id": "   "}, write_error("VALIDATION_ERROR"))

add("update_project", {"id": "PROJECTID1", "title": None}, ok(route="applescript"))
add("update_project", {"id": "PROJECTID1", "title": ""}, write_error("VALIDATION_ERROR"))
add("update_project", {"id": "PROJECTID1", "title": "   "}, write_error("VALIDATION_ERROR"))
add("update_project", {"id": "PROJECTID1", "title": "New Proj Title"}, ok(route="applescript", contains=["name of targetProject to \"New Proj Title\""]))
add("update_project", {"id": "PROJECTID1", "title": SPECIAL_CHARS}, ok(route="applescript", contains=['he said \\"hi\\"']))

add("update_project", {"id": "PROJECTID1", "notes": None}, ok(route="applescript"))
add("update_project", {"id": "PROJECTID1", "notes": ""}, ok(route="applescript", contains=['notes of targetProject to ""']))
add("update_project", {"id": "PROJECTID1", "notes": "   "}, ok(route="applescript", contains=['notes of targetProject to ""']))
add("update_project", {"id": "PROJECTID1", "notes": NEWLINE_TEXT}, ok(route="applescript", contains=["line one\\nline two"]))

add("update_project", {"id": "PROJECTID1", "tags": None}, ok(route="applescript"))
add("update_project", {"id": "PROJECTID1", "tags": ""}, ok(route="applescript", contains=['tag names of targetProject to ""']))
add("update_project", {"id": "PROJECTID1", "tags": "a,b"}, ok(route="applescript", contains=['tag names of targetProject to "a, b"']))

for w, exp in [
    ("today", ok(route="applescript")),
    ("someday", ok(route="applescript")),
    ("anytime", ok(route="applescript")),
    ("evening", write_error("UNSUPPORTED_FOR_PROJECTS")),  # projects don't support Evening
    ("2031-05-15", ok(route="applescript")),
    ("bogus", write_error("INVALID_WHEN")),
    ("", write_error("VALIDATION_ERROR")),
]:
    add("update_project", {"id": "PROJECTID1", "when": w}, exp)

for d, exp in [
    ("2031-05-15", ok(route="applescript", contains=["due date of targetProject"])),
    ("today", write_error("INVALID_DEADLINE")),
    ("", ok(route="applescript", contains=["due date of targetProject"])),
]:
    add("update_project", {"id": "PROJECTID1", "deadline": d}, exp)

add("update_project", {"id": "PROJECTID1", "area_id": None}, ok(route="applescript"))
add("update_project", {"id": "PROJECTID1", "area_id": "AREAID2"}, ok(route="applescript", contains=['area id "AREAID2"']))
add("update_project", {"id": "PROJECTID1", "area_id": ""}, ok(route="applescript"))
add("update_project", {"id": "PROJECTID1", "area_title": None}, ok(route="applescript"))
add("update_project", {"id": "PROJECTID1", "area_title": "Some Area"}, ok(route="applescript", contains=['area "Some Area"']))
add("update_project", {"id": "PROJECTID1", "area_title": "DoesNotExistArea"}, ok(route="applescript", contains=['area "DoesNotExistArea"']))  # hq-rmh

for completed, canceled, expect_marker in [
    ("true", "true", "status of targetProject to canceled"),
    ("true", "false", "status of targetProject to completed"),
    ("false", "true", "status of targetProject to canceled"),
    ("false", "false", "status of targetProject to open"),
]:
    add(
        "update_project",
        {"id": "PROJECTID1", "completed": completed, "canceled": canceled},
        ok(route="applescript", contains=[expect_marker]),
    )
add("update_project", {"id": "PROJECTID1", "completed": "True"}, ok(route="applescript"))
add("update_project", {"id": "PROJECTID1", "completed": "yes"}, write_error("VALIDATION_ERROR"))
add("update_project", {"id": "PROJECTID1", "canceled": "1"}, write_error("VALIDATION_ERROR"))
add("update_project", {"id": "PROJECTID1", "completed": True}, tool_error())


# ===========================================================================
# add_area
# ===========================================================================

add("add_area", {"title": "Area title"}, ok(route="applescript", contains=["name:\"Area title\""]))
add("add_area", {"title": SPECIAL_CHARS}, ok(route="applescript", contains=['he said \\"hi\\"']))
add("add_area", {"title": NEWLINE_TEXT}, ok(route="applescript", contains=["line one\\nline two"]))
add("add_area", {"title": UNICODE_EMOJI}, ok(route="applescript", contains=[UNICODE_EMOJI]))
add("add_area", {"title": LONG_2000}, ok(route="applescript", contains=[LONG_2000]))

add("add_area", {"title": "A", "tags": None}, ok(route="applescript"))
add("add_area", {"title": "A", "tags": ""}, ok(route="applescript"))
add("add_area", {"title": "A", "tags": " , "}, ok(route="applescript"))
add("add_area", {"title": "A", "tags": "a,b"}, ok(route="applescript", contains=["tag names of newArea to \"a, b\""]))


# ===========================================================================
# update_area
# ===========================================================================

add("update_area", {"id": "AREAID1"}, write_error("NO_FIELDS_PROVIDED"))
add("update_area", {"id": ""}, write_error("VALIDATION_ERROR"))
add("update_area", {"id": "   "}, write_error("VALIDATION_ERROR"))
add("update_area", {"id": "AREAID1", "title": "New Area Title"}, ok(route="applescript", contains=['area id "AREAID1"', "name of targetArea to \"New Area Title\""]))

add("update_area", {"id": "AREAID1", "title": None}, write_error("NO_FIELDS_PROVIDED"))
add("update_area", {"id": "AREAID1", "title": ""}, write_error("VALIDATION_ERROR"))
add("update_area", {"id": "AREAID1", "title": "   "}, write_error("VALIDATION_ERROR"))
add("update_area", {"id": "AREAID1", "title": SPECIAL_CHARS}, ok(route="applescript", contains=['he said \\"hi\\"']))

add("update_area", {"id": "AREAID1", "tags": None}, write_error("NO_FIELDS_PROVIDED"))
add("update_area", {"id": "AREAID1", "tags": ""}, ok(route="applescript", contains=['tag names of targetArea to ""']))
add("update_area", {"id": "AREAID1", "tags": " , "}, ok(route="applescript", contains=['tag names of targetArea to ""']))
add("update_area", {"id": "AREAID1", "tags": "a,b"}, ok(route="applescript", contains=['tag names of targetArea to "a, b"']))


# ===========================================================================
# add_tags / remove_tags
# ===========================================================================

# NOTE (Discovered): neither add_tags nor remove_tags validates todo_id
# for non-empty/non-whitespace at the server layer (unlike update_todo/
# delete_todo/move_record, which all call
# ParameterValidator.validate_non_empty_string on their id parameter) - an
# empty or whitespace-only todo_id is sent straight through as
# `to do id ""` / `to do id "   "` and Things' AppleScript error handling
# (mocked here as unconditional success) determines the outcome, not this
# server. Cases below assert the OBSERVED behavior (success, since the fake
# manager never simulates an AppleScript-level failure for a bad id).
add("add_tags", {"todo_id": "TODOID1", "tags": "urgent"}, ok(route="applescript", contains=["tag names of targetTodo to"]))
add("add_tags", {"todo_id": "", "tags": "urgent"}, ok(route="applescript", contains=['to do id ""']))
add("add_tags", {"todo_id": "   ", "tags": "urgent"}, ok(route="applescript", contains=['to do id "   "']))
add("add_tags", {"todo_id": SPECIAL_CHARS, "tags": "urgent"}, ok(route="applescript"))

add("add_tags", {"todo_id": "TODOID1", "tags": ""}, write_error("NO_VALID_TAGS"))
add("add_tags", {"todo_id": "TODOID1", "tags": " , "}, write_error("NO_VALID_TAGS"))
add("add_tags", {"todo_id": "TODOID1", "tags": "a,b"}, ok(route="applescript", contains=["set tag names of targetTodo to"]))
add("add_tags", {"todo_id": "TODOID1", "tags": "a, b"}, ok(route="applescript", contains=["set tag names of targetTodo to"]))

add("remove_tags", {"todo_id": "RTID1", "tags": "urgent"}, ok(route="applescript", contains=["set tag names of targetTodo to"]))
add("remove_tags", {"todo_id": "", "tags": "urgent"}, ok(route="applescript", contains=['to do id ""']))
add("remove_tags", {"todo_id": "   ", "tags": "urgent"}, ok(route="applescript", contains=['to do id "   "']))
# tags='' / ' , ' parse to an empty list, current tags is also empty (no
# seed) -> a no-op removal (0 removed, nothing not_present) rather than a
# validation error - remove_tags applies no non-empty-tags precondition
# the way add_tags' NO_VALID_TAGS check does (see class docstring on
# remove_tags: "does NOT apply the configured tag_creation_policy").
add("remove_tags", {"todo_id": "RTID1", "tags": ""}, ok(route="applescript", contains=['tag names of targetTodo to ""']))
add("remove_tags", {"todo_id": "RTID1", "tags": " , "}, ok(route="applescript", contains=['tag names of targetTodo to ""']))
add("remove_tags", {"todo_id": "RTID1", "tags": "a,b"}, ok(route="applescript", contains=["set tag names of targetTodo to"]))


# ===========================================================================
# tag policy: default (FAIL_ON_UNKNOWN via ai_can_create_tags=False),
# ALLOW_ALL (via config directly, matching the default constructor param
# path add_tags/add_todo use), and the two granular states hq-nb1 makes
# unreachable via env - covered by constructing ThingsMCPConfig directly.
# ===========================================================================

add(
    "add_tags",
    {"todo_id": "TODOID1", "tags": "unknowntag"},
    # FAIL_ON_UNKNOWN rejects at the policy layer itself (TAG_VALIDATION_FAILED,
    # distinct from add_tags' own NO_VALID_TAGS check below) - a read-only
    # existing-tags lookup capture happens before the reject, but no mutation.
    write_error("TAG_VALIDATION_FAILED", no_capture=False),
    tag_policy=TagCreationPolicy.FAIL_ON_UNKNOWN,
)
add(
    "add_tags",
    {"todo_id": "TODOID1", "tags": "anytag"},
    ok(route="applescript", contains=["set tag names of targetTodo to"]),
    tag_policy=TagCreationPolicy.ALLOW_ALL,
)
add(
    "add_tags",
    {"todo_id": "TODOID1", "tags": "unknowntag"},
    # FILTER_SILENT/FILTER_WARN filter unknown tags to an empty valid set
    # without erroring at the policy layer - add_tags' own "nothing left to
    # apply" check then reports NO_VALID_TAGS. A read-only existing-tags
    # lookup capture happens before this check, but no mutation.
    write_error("NO_VALID_TAGS", no_capture=False),
    tag_policy=TagCreationPolicy.FILTER_SILENT,
)
add(
    "add_tags",
    {"todo_id": "TODOID1", "tags": "unknowntag"},
    write_error("NO_VALID_TAGS", no_capture=False),
    tag_policy=TagCreationPolicy.FILTER_WARN,
)
# hq-r87: a whitespace-only tag name is accepted (stripped, not rejected)
add(
    "add_tags",
    {"todo_id": "TODOID1", "tags": "  spacey  ,urgent"},
    ok(route="applescript", contains=["set tag names of targetTodo to"]),
    tag_policy=TagCreationPolicy.ALLOW_ALL,
)


# ===========================================================================
# create_tag
# ===========================================================================

add("create_tag", {"tag_name": "newtag"}, ok(route="applescript", contains=["make new tag with properties"]), tag_policy=TagCreationPolicy.ALLOW_ALL)
add("create_tag", {"tag_name": "newtag"}, write_error("TAG_CREATION_RESTRICTED"), tag_policy=TagCreationPolicy.FAIL_ON_UNKNOWN)
add("create_tag", {"tag_name": SPECIAL_CHARS}, ok(route="applescript", contains=['he said \\"hi\\"']), tag_policy=TagCreationPolicy.ALLOW_ALL)
# tag_name has no minLength in the schema - '' and whitespace-only both
# pass pydantic and reach the AppleScript create path unchanged (observed;
# not one of the bead's cited bugs, filed separately - see Discovered).
add("create_tag", {"tag_name": ""}, ok(route="applescript"), tag_policy=TagCreationPolicy.ALLOW_ALL)
add("create_tag", {"tag_name": "   "}, ok(route="applescript"), tag_policy=TagCreationPolicy.ALLOW_ALL)


# ===========================================================================
# move_record
# ===========================================================================

for dest, exp in [
    ("inbox", ok(route="applescript", contains=['move theTodo to list "inbox"'])),
    ("today", ok(route="applescript", contains=['move theTodo to list "today"'])),
    ("upcoming", ok(route="applescript", contains=['move theTodo to list "upcoming"'])),
    ("anytime", ok(route="applescript", contains=['move theTodo to list "anytime"'])),
    ("someday", ok(route="applescript", contains=['move theTodo to list "someday"'])),
    # hq-z5d: 'logbook'/'trash' pass _validate_destination's valid_lists
    # check but are not in _execute_move's built-in-list branch, so they
    # fall through to INVALID_DESTINATION - observed, not "correct".
    ("logbook", write_error("INVALID_DESTINATION", no_capture=False)),
    ("trash", write_error("INVALID_DESTINATION", no_capture=False)),
    ("project:PROJ123", ok(route="applescript", contains=['project id "PROJ123"'])),
    ("area:AREA123", ok(route="applescript", contains=['area id "AREA123"'])),
    ("project:", write_error("VALIDATION_ERROR")),
    ("bogus", write_error("VALIDATION_ERROR")),
]:
    add("move_record", {"todo_id": "TODOID1", "destination_list": dest}, exp)

add("move_record", {"todo_id": "", "destination_list": "today"}, write_error("VALIDATION_ERROR"))
# move_record's own todo_id validation only rejects a falsy (empty) string,
# not a whitespace-only one - "   " passes _validate_move_inputs and
# proceeds to the (mocked) AppleScript move (observed; distinct from
# update_todo/delete_todo, which reject whitespace-only ids too).
add("move_record", {"todo_id": "   ", "destination_list": "today"}, ok(route="applescript"))
add("move_record", {"todo_id": SPECIAL_CHARS, "destination_list": "today"}, ok(route="applescript"))


# ===========================================================================
# bulk_move_records
# ===========================================================================

add("bulk_move_records", {"todo_ids": "T1,T2,T3", "destination": "today"}, ok(route="applescript", contains=["T1", "T2", "T3"]))
add("bulk_move_records", {"todo_ids": "", "destination": "today"}, write_error("NO_TODO_IDS"))
add("bulk_move_records", {"todo_ids": ",,", "destination": "today"}, write_error("NO_TODO_IDS"))
add("bulk_move_records", {"todo_ids": "a", "destination": "today"}, ok(route="applescript", contains=["a"]))
add("bulk_move_records", {"todo_ids": "a,b,c", "destination": "today"}, ok(route="applescript", contains=["a", "b", "c"]))

for dest, exp in [
    ("inbox", ok(route="applescript")),
    ("today", ok(route="applescript")),
    ("upcoming", ok(route="applescript")),
    ("anytime", ok(route="applescript")),
    ("someday", ok(route="applescript")),
    # 'logbook'/'trash' pass bulk_move's own destination validation (its
    # valid_lists includes them) but fail per-todo inside _execute_move
    # (same INVALID_DESTINATION gap as move_record, hq-z5d-adjacent) - the
    # overall call still reports success=False, but via the bulk
    # successful/failed-moves envelope, not the top-level pre-write
    # validation error shape, and a script/URL call for the (failed)
    # attempt IS made per todo.
    ("logbook", write_error("INVALID_DESTINATION", no_capture=False)),
    ("trash", write_error("INVALID_DESTINATION", no_capture=False)),
    ("project:PROJ123", ok(route="applescript", contains=["PROJ123"])),
    ("area:AREA123", ok(route="applescript", contains=["AREA123"])),
    ("project:", write_error("INVALID_DESTINATION")),
    ("bogus", write_error("INVALID_DESTINATION")),
]:
    add("bulk_move_records", {"todo_ids": "T1,T2", "destination": dest}, exp)

add("bulk_move_records", {"todo_ids": "T1,T2", "destination": "today", "max_concurrent": 0}, tool_error())
add("bulk_move_records", {"todo_ids": "T1,T2", "destination": "today", "max_concurrent": 1}, ok(route="applescript"))
add("bulk_move_records", {"todo_ids": "T1,T2", "destination": "today", "max_concurrent": 10}, ok(route="applescript"))
add("bulk_move_records", {"todo_ids": "T1,T2", "destination": "today", "max_concurrent": 11}, tool_error())


# ===========================================================================
# add_checklist_items / prepend_checklist_items / replace_checklist_items
# ===========================================================================

for tool, url_key in [
    ("add_checklist_items", "append-checklist-items"),
    ("prepend_checklist_items", "prepend-checklist-items"),
    ("replace_checklist_items", "checklist-items"),
]:
    add(tool, {"todo_id": "TODOID1", "items": ["one"]}, ok(route="url_update", url_contains={url_key: "one"}))
    add(tool, {"todo_id": "TODOID1", "items": ["a", "b", "c"]}, ok(route="url_update", url_contains={url_key: "a"}))
    add(tool, {"todo_id": "TODOID1", "items": [f"item{i}" for i in range(100)]}, ok(route="url_update"))
    add(tool, {"todo_id": "TODOID1", "items": [f"item{i}" for i in range(101)]}, ok(route="url_update"))  # hq-exe: no cap enforced
    add(tool, {"todo_id": "TODOID1", "items": [SPECIAL_CHARS]}, ok(route="url_update"))
    add(tool, {"todo_id": "TODOID1", "items": [UNICODE_EMOJI]}, ok(route="url_update"))
    add(tool, {"todo_id": "TODOID1", "items": [NEWLINE_TEXT]}, ok(route="url_update"))
    add(tool, {"todo_id": "TODOID1", "items": ["one"]}, write_error("AUTH_TOKEN_NOT_CONFIGURED"), auth_token=None)

add("add_checklist_items", {"todo_id": "TODOID1", "items": []}, write_error("NO_CHECKLIST_ITEMS"))
add("prepend_checklist_items", {"todo_id": "TODOID1", "items": []}, write_error("NO_CHECKLIST_ITEMS"))
# replace_checklist_items([]) is documented to CLEAR the checklist, not an
# error - the empty-list guard only applies to add/prepend.
add("replace_checklist_items", {"todo_id": "TODOID1", "items": []}, ok(route="url_update", url_contains={"checklist-items": ""}))


# ---------------------------------------------------------------------------
# Case IDs for readable pytest output.
# ---------------------------------------------------------------------------


def _case_id(case: Tuple[str, Dict[str, Any], Any, Dict[str, Any]]) -> str:
    tool, args, expectation, _options = case
    args_str = ",".join(f"{k}={v!r}" for k, v in args.items() if not isinstance(v, list) or len(v) <= 3) or "defaults"
    return f"{tool}[{args_str}]->{expectation.kind}"


# ---------------------------------------------------------------------------
# Route detection + assertions
# ---------------------------------------------------------------------------


def _detect_route(fake: RecordingAppleScriptManager) -> Optional[str]:
    """Classify which capture bucket a call landed in. Prefers URL-scheme
    detection (action name) since a single call may also incidentally emit
    an AppleScript execution for an unrelated pre-check."""
    if fake.url_scheme_calls:
        action = fake.url_scheme_calls[-1][0]
        if action == "add":
            return "url_add"
        if action == "update":
            return "url_update"
        if action == "json":
            return "url_json"
    if fake.execution_calls:
        return "applescript"
    return None


def _assert_ok(sc: Dict[str, Any], fake: RecordingAppleScriptManager, tool: str, expectation: Ok) -> None:
    assert sc is not None, f"{tool}: structured_content is None"
    assert sc.get("success") is not False, f"{tool}: unexpected structured error: {sc}"

    if expectation.route is not None:
        route = _detect_route(fake)
        assert route == expectation.route, (
            f"{tool}: expected route={expectation.route!r}, got {route!r}. "
            f"scripts={fake.execution_calls!r} url_calls={fake.url_scheme_calls!r}"
        )

    if expectation.contains:
        haystack = fake.all_scripts_text() + "\n" + json.dumps(fake.all_url_params())
        for needle in expectation.contains:
            assert needle in haystack, (
                f"{tool}: expected {needle!r} in captured output.\n"
                f"scripts={fake.execution_calls!r}\nurl_calls={fake.url_scheme_calls!r}"
            )

    if expectation.url_contains:
        for key, needle in expectation.url_contains.items():
            found = any(key in params and needle in str(params[key]) for params in fake.all_url_params())
            assert found, (
                f"{tool}: expected url param {key!r} to contain {needle!r}. "
                f"url_calls={fake.url_scheme_calls!r}"
            )


def _assert_write_error(sc: Dict[str, Any], fake: RecordingAppleScriptManager, tool: str, expectation: WriteErrorExpectation) -> None:
    assert sc is not None, f"{tool}: structured_content is None"
    assert sc.get("success") is False, f"{tool}: expected success=False, got {sc}"

    # bulk_move_records reports a per-todo failure inside 'failed_moves'
    # rather than a top-level 'error' key when the overall call still
    # returns a structured (non-raising) envelope for a per-item
    # INVALID_DESTINATION - check both shapes.
    top_level_code = sc.get("error")
    if top_level_code is None and isinstance(sc.get("failed_moves"), list) and sc["failed_moves"]:
        top_level_code = sc["failed_moves"][0].get("error")
    assert top_level_code == expectation.code, (
        f"{tool}: expected error={expectation.code!r}, got {top_level_code!r} (full: {sc})"
    )
    assert "message" in sc, f"{tool}: expected a 'message' field, got {sorted(sc.keys())}"
    if expectation.code == "AUTH_TOKEN_NOT_CONFIGURED":
        assert "hint" in sc, f"{tool}: AUTH_TOKEN_NOT_CONFIGURED must carry 'hint', got {sorted(sc.keys())}"
    if expectation.no_capture:
        assert not fake.any_capture(), (
            f"{tool}: expected NO AppleScript/URL call for a {expectation.code} error, "
            f"but got scripts={fake.execution_calls!r} url_calls={fake.url_scheme_calls!r}"
        )


# ---------------------------------------------------------------------------
# Parametrized matrix
# ---------------------------------------------------------------------------


class TestWriteInputMatrix:
    @pytest.mark.parametrize("case", CASES, ids=_case_id)
    def test_case(self, case: Tuple[str, Dict[str, Any], Any, Dict[str, Any]]) -> None:
        tool, args, expectation, options = case

        if expectation.kind == "tool_error":
            server, fake = _make_server(
                auth_token=options.get("auth_token", "SENTINELauthtokenABC"),
                tag_policy=options.get("tag_policy"),
            )
            patches = _patched_things_lookups()
            for p in patches:
                p.start()
            try:
                with pytest.raises(ToolError):
                    asyncio.run(_call_tool(server, tool, args))
            finally:
                for p in patches:
                    p.stop()
            return

        result, fake = run_tool(
            tool,
            args,
            auth_token=options.get("auth_token", "SENTINELauthtokenABC"),
            tag_policy=options.get("tag_policy"),
            seed=options.get("seed"),
        )
        sc = result.structured_content

        if expectation.kind == "ok":
            _assert_ok(sc, fake, tool, expectation)
        elif expectation.kind == "write_error":
            _assert_write_error(sc, fake, tool, expectation)
        else:  # pragma: no cover - exhaustive kind set
            raise AssertionError(f"Unknown expectation kind: {expectation.kind}")


# ---------------------------------------------------------------------------
# Completeness check: every (write tool, param) pair must have >= 3 cases.
# ---------------------------------------------------------------------------

WRITE_TOOLS = {
    "add_todo",
    "update_todo",
    "bulk_update_todos",
    "delete_todo",
    "add_project",
    "update_project",
    "add_area",
    "update_area",
    "add_tags",
    "remove_tags",
    "create_tag",
    "move_record",
    "bulk_move_records",
    "add_checklist_items",
    "prepend_checklist_items",
    "replace_checklist_items",
}


class TestCompleteness:
    @pytest.mark.asyncio
    async def test_every_write_tool_param_has_at_least_three_cases(self) -> None:
        server, _fake = _make_server()
        client = Client(server.mcp)
        async with client:
            tools = await client.list_tools()

        tools_by_name = {t.name: t for t in tools if t.name in WRITE_TOOLS}
        missing_tools = WRITE_TOOLS - set(tools_by_name.keys())
        assert not missing_tools, f"Write tools not found via list_tools(): {missing_tools}"

        coverage: Dict[Tuple[str, str], int] = {}
        for tool, args, _expectation, _options in CASES:
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

    def test_cases_table_has_at_least_200_entries(self) -> None:
        assert len(CASES) >= 200, f"Expected >= 200 CASES entries, got {len(CASES)}"
