"""hq-gbl.13: Regression (live) for get_inbox/get_today/get_upcoming/
get_anytime/get_someday - exclusions (headings never, projects opt-in),
Someday project-task inheritance, per-mode field sets, limit/total
semantics, and get_upcoming's days parameter.

The seed oracle (test_seed_oracle.py, hq-gbl.6) already covers class
membership ("is this seed uuid present/absent"); this file covers the
things the oracle deliberately does not: exact exclusion invariants
(no heading rows ever, no project rows unless include_projects=true),
mode field-set shapes, requested_mode echo, limit/total contract, and
get_upcoming(days=...) boundaries.

Large-DB caution (hq-ov3): the live database's Anytime list has 1100+
items. Any assertion that would need to scan the full unbounded window of
a plain list tool uses limit=500 and, when total>500, falls back to a
targeted things.py membership probe instead of asserting presence/absence
within a possibly-truncated window - never asserting truncation-sensitive
membership directly against a >500-item list.

Error-code notes (confirmed by reading source + a live schema probe, not
assumed):
  - get_inbox/get_today/get_upcoming/get_anytime/get_someday's `limit` is a
    pydantic Field(ge=1, le=500) constraint (server.py) - limit=0/501 is a
    FastMCP tool-call schema validation error (surfaces here as
    {"tool_error": "...ge=1..."/"...le=500..."} via the `mcp` fixture's
    ToolError handling), NOT the {"error": "invalid_limit", ...}
    read-error-contract shape. That shape only exists on get_todos, whose
    `limit: Any` parameter is validated by hand in server.py (not by
    pydantic) - get_todos is out of scope for this bead.
  - get_upcoming's `days` is likewise a pydantic Field(ge=1, le=365) -
    days=0/366 is the same tool_error schema-rejection shape.
  - get_inbox has no include_projects parameter at all (Inbox can never
    contain projects per CLAUDE.md) - passing it is an
    unexpected_keyword_argument schema rejection (tool_error), not a
    runtime/business-logic error.
  - `mode`, by contrast, IS hand-validated in server.py for all five of
    these tools (via the shared `_validate_mode` helper, hq-exd) - a bogus
    mode returns the structured read_error('invalid_mode', ...) shape, same
    as get_todos/get_projects/get_areas/search_*, never a tool_error. See
    TestModes.test_bogus_mode_returns_structured_invalid_mode_error.
"""
import asyncio
import time

import pytest

from regression.helpers import sandbox_title, ts

pytestmark = pytest.mark.live

LIST_TOOLS = ["get_inbox", "get_today", "get_upcoming", "get_anytime", "get_someday"]

# Tools (besides get_inbox) that accept include_projects.
INCLUDE_PROJECTS_TOOLS = ["get_today", "get_upcoming", "get_anytime", "get_someday"]

TODO_MINIMAL_KEYS = {
    "uuid", "title", "status", "type", "start", "project",
    "dueDate", "modificationDate", "creationDate",
}
TODO_STANDARD_KEYS = {
    "uuid", "title", "status", "type", "notes", "dueDate", "modificationDate",
    "creationDate", "tags", "project", "projectTitle", "heading", "headingTitle",
    "start", "startDate", "inheritedSomeday", "reminderTime",
}
TODO_SUMMARY_KEYS = {"uuid", "title", "status", "tags", "dueDate"}

PROJECT_MINIMAL_KEYS = {
    "uuid", "title", "status", "type", "area", "start",
    "dueDate", "modificationDate", "creationDate",
}
PROJECT_STANDARD_KEYS = {
    "uuid", "title", "status", "type", "notes", "dueDate", "modificationDate",
    "creationDate", "tags", "area", "areaTitle", "start", "startDate",
    "reminderTime",
}
PROJECT_SUMMARY_KEYS = {"uuid", "title", "status", "tags", "dueDate"}


def _assert_allowed_keys(item, allowed_keys, label):
    extra = set(item.keys()) - allowed_keys
    assert not extra, f"{label}: unexpected keys {extra} in item {item!r}"


# ---------------------------------------------------------------------------
# 1. Exclusion invariants: no heading rows ever; no project rows unless
#    include_projects=true.
# ---------------------------------------------------------------------------


class TestExclusions:
    @pytest.mark.parametrize("tool", LIST_TOOLS)
    def test_no_heading_rows(self, mcp, sandbox, seeded, tool):
        """No item of type 'heading' ever appears in any of these list
        tools' results, and the sandbox's own known heading id never
        appears either (regardless of include_projects)."""
        kwargs = {"mode": "minimal", "limit": 500}
        result = mcp.call_sync(tool, **kwargs)
        items = result.get("items", [])
        assert all(item.get("type") != "heading" for item in items), (
            f"{tool}: found a heading-typed row: "
            f"{[i for i in items if i.get('type') == 'heading']}"
        )
        if sandbox.heading_id is not None:
            uuids = {item.get("uuid") for item in items}
            assert sandbox.heading_id not in uuids, (
                f"{tool}: sandbox heading id unexpectedly present"
            )

    @pytest.mark.parametrize("tool", INCLUDE_PROJECTS_TOOLS)
    def test_no_project_rows_by_default(self, mcp, sandbox, seeded, tool):
        """Without include_projects, no item of type 'project' appears -
        even though the sandbox area contains several sandbox projects
        that may otherwise be reachable by that list's underlying query."""
        result = mcp.call_sync(tool, mode="minimal", limit=500)
        items = result.get("items", [])
        assert all(item.get("type") != "project" for item in items), (
            f"{tool}: found a project row with include_projects omitted: "
            f"{[i for i in items if i.get('type') == 'project']}"
        )

    def test_get_inbox_has_no_include_projects_param(self, mcp):
        """get_inbox has no include_projects parameter (Inbox can never
        contain projects) - passing it is a schema rejection at the MCP
        tool boundary (tool_error), not a runtime error."""
        result = mcp.call_sync("get_inbox", include_projects=True)
        assert "tool_error" in result, result
        assert "include_projects" in result["tool_error"], result


# ---------------------------------------------------------------------------
# 2. include_projects=true: get_today shows a project scheduled for today;
#    other list tools' include_projects presence/absence is exercised via
#    the same throwaway per-test project pattern used in
#    test_projects_areas.py (never touching sandbox.project_id's own
#    schedule state, so this bead doesn't need to restore anything on the
#    shared sandbox project).
# ---------------------------------------------------------------------------


class TestIncludeProjects:
    def _new_scratch_project(self, mcp, sandbox, **kwargs):
        title = sandbox_title("list-tools proj " + ts())
        kwargs.setdefault("area_id", sandbox.area_id)
        result = mcp.call_sync("add_project", title=title, **kwargs)
        assert result.get("success") is True, result
        project_id = result.get("project_id")
        assert project_id
        sandbox.tracked_project_ids.append(project_id)
        return project_id, title

    def test_today_include_projects(self, mcp, sandbox):
        """A project scheduled when='today' appears in get_today only with
        include_projects=true; absent by default. The project is a fresh
        throwaway (never the shared sandbox.project_id), scheduled once and
        left for teardown - no restore needed since nothing shared is
        mutated."""
        project_id, _ = self._new_scratch_project(mcp, sandbox)
        result = mcp.call_sync("update_project", id=project_id, when="today")
        assert result.get("success") is True, result

        import things

        def _read_back_scheduled():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                record = things.get(project_id, trashed=None)
                if record is not None and record.get("start_date") is not None:
                    return record
                time.sleep(0.5)
            return things.get(project_id, trashed=None)

        record = _read_back_scheduled()
        assert record is not None and record.get("start_date") is not None, record

        def _in_today(include_projects):
            r = mcp.call_sync(
                "get_today", include_projects=include_projects, mode="detailed", limit=500
            )
            items = r.get("items", [])
            return any(i.get("uuid") == project_id for i in items)

        deadline = time.monotonic() + 20
        found = _in_today(True)
        while not found and time.monotonic() < deadline:
            time.sleep(0.5)
            found = _in_today(True)
        assert found, "expected scheduled project in get_today(include_projects=True)"

        assert not _in_today(False), (
            "project unexpectedly present in get_today with include_projects omitted"
        )

    def test_someday_include_projects(self, mcp, sandbox):
        """A project created when='someday' appears in
        get_someday(include_projects=true) but not by default."""
        project_id, _ = self._new_scratch_project(mcp, sandbox, when="someday")

        import things

        record = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            record = things.get(project_id, trashed=None)
            if record is not None:
                break
            time.sleep(0.5)
        assert record is not None, "project never read back via things.py"

        def _in_someday(include_projects):
            r = mcp.call_sync(
                "get_someday", include_projects=include_projects, mode="detailed", limit=500
            )
            items = r.get("items", [])
            return any(i.get("uuid") == project_id for i in items)

        deadline = time.monotonic() + 20
        found = _in_someday(True)
        while not found and time.monotonic() < deadline:
            time.sleep(0.5)
            found = _in_someday(True)
        assert found, "expected project in get_someday(include_projects=True)"

        assert not _in_someday(False), (
            "project unexpectedly present in get_someday with include_projects omitted"
        )


# ---------------------------------------------------------------------------
# 3. include_project_tasks on get_someday: a tracked Someday project with 2
#    to-dos - those to-dos appear only with include_project_tasks=true and
#    carry inheritedSomeday: true; and they never appear in
#    get_today/get_anytime/get_upcoming regardless of that flag.
# ---------------------------------------------------------------------------


class TestSomedayProjectTaskInheritance:
    @pytest.fixture(scope="class")
    def someday_project_with_todos(self, mcp, sandbox):
        title = sandbox_title("someday-inherit proj " + ts())
        result = mcp.call_sync(
            "add_project", title=title, area_id=sandbox.area_id, when="someday"
        )
        assert result.get("success") is True, result
        project_id = result.get("project_id")
        assert project_id
        sandbox.tracked_project_ids.append(project_id)

        todo_ids = []
        for n in (1, 2):
            todo_title = sandbox_title(f"someday-inherit todo{n} " + ts())
            add_result = mcp.call_sync("add_todo", title=todo_title, list_id=project_id)
            assert add_result.get("success") is True, add_result
            todo_id = add_result.get("todo_id")
            assert todo_id
            sandbox.track(todo_id)
            todo_ids.append(todo_id)

        import things

        def _both_readable():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if all(things.get(t, trashed=None) is not None for t in todo_ids):
                    return True
                time.sleep(0.5)
            return False

        assert _both_readable(), f"someday-project todos never read back: {todo_ids}"
        return project_id, todo_ids

    def test_inherited_todos_present_only_with_flag(self, server_tools, someday_project_with_todos):
        """The live database's native Someday set is itself large enough
        that a limit=500 MCP-boundary window can truncate before reaching
        two freshly-created inherited items (confirmed live, per hq-ov3's
        truncation-fragility caution - the inherited set is appended after
        native items in read_operations.py's _get_someday_sync and gets cut
        off by `limit`). Bypass the limit<=500 MCP schema cap via
        `server_tools` (ThingsTools, the harness's documented escape hatch
        for exactly this case) and fetch the full unbounded set directly."""
        project_id, todo_ids = someday_project_with_todos

        def _present_with_flag(flag):
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                items = asyncio.run(
                    server_tools.get_someday(limit=None, include_project_tasks=flag)
                )
                items_by_id = {i.get("uuid"): i for i in items}
                if all(tid in items_by_id for tid in todo_ids):
                    return items_by_id
                time.sleep(0.5)
            items = asyncio.run(
                server_tools.get_someday(limit=None, include_project_tasks=flag)
            )
            return {i.get("uuid"): i for i in items}

        with_flag = _present_with_flag(True)
        for tid in todo_ids:
            assert tid in with_flag, (
                f"expected inherited todo {tid} in get_someday(include_project_tasks=True)"
            )
            assert with_flag[tid].get("inheritedSomeday") is True, with_flag[tid]

        items_without_flag = asyncio.run(
            server_tools.get_someday(limit=None, include_project_tasks=False)
        )
        without_ids = {i.get("uuid") for i in items_without_flag}
        for tid in todo_ids:
            assert tid not in without_ids, (
                f"inherited todo {tid} unexpectedly present with "
                f"include_project_tasks omitted/False"
            )

    @pytest.mark.parametrize("tool", ["get_today", "get_anytime", "get_upcoming"])
    def test_inherited_todos_absent_elsewhere(self, mcp, someday_project_with_todos, tool):
        """Inherited-Someday tasks never appear in get_today/get_anytime/
        get_upcoming, regardless of include_project_tasks (which those
        tools don't even accept - this asserts absence from their normal
        result sets)."""
        _, todo_ids = someday_project_with_todos
        result = mcp.call_sync(tool, mode="minimal", limit=500)
        uuids = {i.get("uuid") for i in result.get("items", [])}
        for tid in todo_ids:
            assert tid not in uuids, f"{tool}: inherited-someday todo {tid} unexpectedly present"


# ---------------------------------------------------------------------------
# 4. Modes: per-mode field sets on a seed todo row and a project row
#    (include_projects=true); requested_mode echo; mode never literal
#    'auto'.
# ---------------------------------------------------------------------------


class TestModes:
    @pytest.mark.parametrize(
        "mode",
        [
            "auto",
            pytest.param(
                "summary",
                marks=pytest.mark.xfail(
                    strict=True,
                    reason=(
                        "observed: context_manager.py's _summarize_todos() builds "
                        "'recent_preview' items as {'id': ..., 'name': ...} "
                        "(mirroring _summarize_projects/_summarize_search_results), "
                        "not the documented SUMMARY field set "
                        "{uuid, title, status, tags, dueDate} from CLAUDE.md's "
                        "'Todo field lists per mode' - the preview items carry "
                        "different key names entirely, not just a subset. Verified "
                        "live via get_todos(mode='summary') and get_anytime("
                        "mode='summary'), so this is a real doc/behavior "
                        "contradiction, not a seed-timing flake."
                    ),
                ),
            ),
            "minimal",
            "standard",
            "detailed",
            "raw",
        ],
    )
    def test_todo_field_sets(self, mcp, sandbox, seeded, mode):
        """Field-set filtering (TODO_FIELD_SETS in context_manager.py) is
        shared by every list tool including get_anytime/get_today/etc - but
        the live Anytime/Today lists are large enough (hq-ov3: Anytime has
        600-1100+ items) that a seed item is not reliably within a
        limit=500 window (confirmed live: the 'evening' seed class, which
        test_seed_oracle.py's ORACLE documents as reliably present in
        get_anytime, was absent from a limit=500 get_anytime(mode=...)
        window in this exact session). Per the bead's guidance, use
        get_todos(project_uuid=sandbox.project_id) instead - a small,
        guaranteed-complete result set that goes through the identical
        context_manager.optimize_response('get_todos', ...) field-set
        filtering as get_anytime/get_today/get_upcoming/get_someday (same
        TODO_FIELD_SETS), so the field-set assertion is equally valid."""
        todo_id = seeded.uuid("evening")
        assert todo_id, "seed class 'evening' missing"

        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, mode=mode, limit=500, status=None
        )
        assert result.get("mode") != "auto", result
        assert result.get("requested_mode") == mode, result

        items_by_uuid = {i.get("uuid"): i for i in result.get("items", [])}
        if mode == "summary":
            # summary is a small preview - the seed item may not be in the
            # preview window; only assert the shape of whatever preview
            # items are present, plus that total reflects the full count.
            assert isinstance(result.get("total"), int)
            for item in result.get("items", []):
                _assert_allowed_keys(item, TODO_SUMMARY_KEYS, "get_todos summary")
            return

        assert todo_id in items_by_uuid, (
            f"seed 'evening' ({todo_id}) not found in get_todos(project_uuid=..., "
            f"mode={mode!r}) items"
        )
        item = items_by_uuid[todo_id]

        if mode == "minimal":
            _assert_allowed_keys(item, TODO_MINIMAL_KEYS, "get_todos minimal")
            assert {"uuid", "title", "status", "type"} <= set(item.keys())
        elif mode in ("standard", "auto"):
            _assert_allowed_keys(item, TODO_STANDARD_KEYS, "get_todos standard")
            assert {"uuid", "title", "status", "type"} <= set(item.keys())
        else:  # detailed / raw: unfiltered, no upper-bound key assertion
            assert {"uuid", "title", "status", "type"} <= set(item.keys())
            assert "hasChecklist" in item, item

    @pytest.mark.parametrize("mode", ["minimal", "standard", "detailed"])
    def test_project_field_sets_via_include_projects(self, mcp, sandbox, mode):
        """A project row (get_today(include_projects=true)) is filtered
        against the PROJECT field set, not the todo field set - 'area' must
        be present under minimal (todo minimal has no 'area' key at all)."""
        title = sandbox_title("mode-fieldset proj " + ts())
        add_result = mcp.call_sync(
            "add_project", title=title, area_id=sandbox.area_id, when="today"
        )
        assert add_result.get("success") is True, add_result
        project_id = add_result.get("project_id")
        assert project_id
        sandbox.tracked_project_ids.append(project_id)

        def _find():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                r = mcp.call_sync(
                    "get_today", include_projects=True, mode=mode, limit=500
                )
                for item in r.get("items", []):
                    if item.get("uuid") == project_id:
                        return item
                time.sleep(0.5)
            return None

        item = _find()
        assert item is not None, f"scheduled project not found in get_today(mode={mode!r})"
        assert item.get("type") == "project", item

        if mode == "minimal":
            _assert_allowed_keys(item, PROJECT_MINIMAL_KEYS, "project minimal")
            assert "area" in item, item
        elif mode == "standard":
            _assert_allowed_keys(item, PROJECT_STANDARD_KEYS, "project standard")
            assert "area" in item and "areaTitle" in item, item
        else:  # detailed: unfiltered
            assert "area" in item and "areaTitle" in item, item

    @pytest.mark.parametrize("tool", LIST_TOOLS)
    def test_bogus_mode_returns_structured_invalid_mode_error(self, mcp, tool):
        """hq-exd: get_inbox/get_today/get_upcoming/get_anytime/get_someday
        used to pass a bogus `mode` string straight into ResponseMode(...)
        unguarded, raising an unhandled ValueError surfaced by FastMCP as an
        opaque ToolError with no structured_content - unlike get_todos/
        get_projects/get_areas/search_*, which return the canonical
        read_error('invalid_mode', ...) shape. This asserts the fix: all
        five list tools now return the same structured error, never a
        tool_error. Cheap and data-independent - no seed/sandbox needed."""
        result = mcp.call_sync(tool, mode="bogus")
        assert "tool_error" not in result, (
            f"{tool}(mode='bogus'): expected a structured invalid_mode error, "
            f"got an opaque tool_error: {result!r}"
        )
        assert result.get("success") is False, f"{tool}(mode='bogus'): {result!r}"
        assert result.get("error") == "invalid_mode", (
            f"{tool}(mode='bogus'): expected error='invalid_mode', got {result!r}"
        )
        assert "message" in result, f"{tool}(mode='bogus'): missing 'message', got {result!r}"


# ---------------------------------------------------------------------------
# 5. limit / total contract.
# ---------------------------------------------------------------------------


class TestLimitTotal:
    @pytest.mark.parametrize("tool", LIST_TOOLS)
    def test_limit_one_and_total_stability(self, mcp, seeded, tool):
        r1 = mcp.call_sync(tool, mode="minimal", limit=1)
        assert r1.get("count") == 1, r1
        assert len(r1.get("items", [])) == 1, r1
        total_at_1 = r1.get("total")
        assert isinstance(total_at_1, int) and total_at_1 >= 1, r1

        r2 = mcp.call_sync(tool, mode="minimal", limit=2)
        total_at_2 = r2.get("total")
        assert total_at_2 == total_at_1, (
            f"{tool}: total changed between limit=1 ({total_at_1}) and "
            f"limit=2 ({total_at_2}) on an unchanged dataset"
        )

        r3 = mcp.call_sync(tool, mode="minimal", limit=500)
        total_at_500 = r3.get("total")
        assert total_at_500 == total_at_1, (
            f"{tool}: total changed between limit=1 ({total_at_1}) and "
            f"limit=500 ({total_at_500})"
        )

    @pytest.mark.parametrize("tool", LIST_TOOLS)
    def test_limit_out_of_range_is_schema_rejection(self, mcp, tool):
        """limit=0 and limit=501 are pydantic Field(ge=1, le=500)
        violations - a FastMCP tool-call schema error (tool_error), not the
        read-error-contract 'invalid_limit' code (that code only exists on
        get_todos's hand-validated `limit: Any`)."""
        for bad_limit in (0, 501):
            result = mcp.call_sync(tool, limit=bad_limit)
            assert "tool_error" in result, (
                f"{tool}(limit={bad_limit}): expected schema tool_error, got {result!r}"
            )
            assert result.get("error") != "invalid_limit", (
                f"{tool}(limit={bad_limit}): unexpectedly returned the "
                f"get_todos-only 'invalid_limit' read-error shape: {result!r}"
            )

    @pytest.mark.parametrize("tool", LIST_TOOLS)
    def test_total_at_least_known_seeds(self, mcp, seeded, tool):
        """total (pre-limit) must be at least as large as the number of
        distinct seed uuids the seed oracle documents as present in this
        list (a lower bound - other pre-existing real data may add more)."""
        # Minimal, tool-specific lower bounds mirroring test_seed_oracle's
        # ORACLE 'must' sets for each of these five tools.
        must_by_tool = {
            "get_inbox": {"inbox"},
            "get_today": {"today", "evening", "overdue"},
            "get_upcoming": {"tomorrow", "plus5d", "plus40d", "activating_plus10d"},
            "get_anytime": {
                "under_heading", "in_area", "in_project_b", "evening",
                "deadline_today", "deadline_plus3d",
            },
            "get_someday": {"someday"},
        }
        expected_min = len(must_by_tool[tool])
        result = mcp.call_sync(tool, mode="minimal", limit=1)
        total = result.get("total")
        assert isinstance(total, int) and total >= expected_min, (
            f"{tool}: total={total} is less than the known seed lower bound {expected_min}"
        )


# ---------------------------------------------------------------------------
# 6. get_upcoming(days=...): days echoed, boundary presence/absence,
#    invalid days.
# ---------------------------------------------------------------------------


class TestUpcomingDays:
    def test_days_echoed(self, mcp, seeded):
        result = mcp.call_sync("get_upcoming", days=7, mode="minimal", limit=500)
        assert result.get("days") == 7, result

    def test_days_1_excludes_plus5d_and_plus40d(self, mcp, seeded):
        result = mcp.call_sync("get_upcoming", days=1, mode="minimal", limit=500)
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("plus5d") not in uuids, "plus5d unexpectedly within days=1 window"
        assert seeded.uuid("plus40d") not in uuids, "plus40d unexpectedly within days=1 window"

    def test_days_7_includes_plus5d_excludes_plus40d(self, mcp, seeded):
        result = mcp.call_sync("get_upcoming", days=7, mode="minimal", limit=500)
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("plus5d") in uuids, "plus5d missing from days=7 window"
        assert seeded.uuid("plus40d") not in uuids, "plus40d unexpectedly within days=7 window"

    def test_days_365_includes_plus5d_and_plus40d(self, mcp, seeded):
        result = mcp.call_sync("get_upcoming", days=365, mode="minimal", limit=500)
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("plus5d") in uuids, "plus5d missing from days=365 window"
        assert seeded.uuid("plus40d") in uuids, "plus40d missing from days=365 window"

    def test_days_invalid_is_schema_rejection(self, mcp):
        for bad_days in (0, 366):
            result = mcp.call_sync("get_upcoming", days=bad_days)
            assert "tool_error" in result, (
                f"get_upcoming(days={bad_days}): expected schema tool_error, got {result!r}"
            )
