"""hq-gbl.15: Regression (live) for search_todos, search_advanced, get_todos,
get_tagged_items - status/type/tag/area/date filters and offset pagination.

The seed oracle (test_seed_oracle.py, hq-gbl.6) already covers coarse
tool-vs-class membership; this file goes deeper on these four tools:
query validation, status/type/tag/area/date filters, exact field-set/error
shapes, and structural offset-pagination (disjoint windows, stable
pre-limit total).

Validation-shape notes (confirmed by reading server.py, not assumed):
  - search_todos: `query` is `str` (required, no pydantic pattern) - an
    empty/whitespace-only query is hand-validated in server.py and returns
    the lower_snake read-error contract `invalid_query` (NOT a schema
    tool_error). `limit`/`offset` ARE pydantic Field(...) constraints
    (limit: ge=1,le=500; offset: ge=0) - out-of-range is a schema
    tool_error. `status` is hand-validated (`invalid_status` read-error).
  - search_advanced: `status`/`type` are pydantic Field(pattern=...) -
    an invalid value is a schema tool_error, never a read-error code.
    `start_date`/`deadline` are hand-validated against `%Y-%m-%d` in
    server.py - a bad format returns `invalid_start_date_format` /
    `invalid_deadline_format` (each carrying an `example` key), not a
    schema tool_error. `limit`/`offset` are pydantic constraints (schema
    tool_error out of range). `tag` unknown -> `unknown_tag` read-error
    (raised from things.py, not schema-validated).
  - get_todos: `mode`/`status`/`limit` are ALL hand-validated in server.py
    (`limit: Any` is deliberately untyped so out-of-range/non-numeric
    values reach the hand validator instead of pydantic) - every one of
    invalid_mode/invalid_status/invalid_limit is a read-error dict, never
    a schema tool_error. `status` also accepts the literal strings
    `'None'`/`'null'` (MCP client string coercion) as equivalent to `None`.
  - get_tagged_items: `tag` is a required str with no format constraint -
    an unknown tag is the `unknown_tag` read-error (same shape as
    search_advanced's).

search_advanced start_date/deadline semantics (confirmed by reading
_search_advanced_sync in read_operations.py): the filter value is passed
straight through to `things.tasks(start_date=..., deadline=...)` -
things.py's own exact-value match against that field (not a range), so
`deadline='YYYY-MM-DD'` only matches todos whose deadline is exactly that
date, and `start_date='YYYY-MM-DD'` only matches todos whose start_date
(the `when` date) is exactly that date - not "on or before"/"on or after".

search_advanced area filter: the Field description says "Filter by area
UUID" and _search_advanced_sync passes `area` straight through to
things.tasks(area=...) with no title-resolution step of its own - so this
suite uses `sandbox.area_id`, not `sandbox.area_title`, as the primary
case; sandbox.area_title is exercised separately to record actual
behavior (things.py itself may or may not accept a title - documented via
assertion, not assumed).
"""
import time
from typing import Any, Dict, List, Set

import pytest

from regression.helpers import assert_read_error, sandbox_title, ts

pytestmark = pytest.mark.live

_MAX_PAGES = 4


def _page_until_found(mcp, tool: str, base_kwargs: Dict[str, Any], target_uuid: str,
                       page_size: int = 500, max_pages: int = _MAX_PAGES):
    """Page `tool` via offset (base_kwargs must not include offset/limit)
    until `target_uuid` is found, a short page is returned (end of data),
    or `max_pages` is exhausted. Returns (found, total, pages_fetched)."""
    found = False
    total = None
    pages = 0
    offset = 0
    while pages < max_pages:
        result = mcp.call_sync(tool, limit=page_size, offset=offset, **base_kwargs)
        pages += 1
        items = result.get("items", [])
        if total is None:
            total = result.get("total")
        uuids = {i.get("uuid") for i in items}
        if target_uuid in uuids:
            found = True
            break
        if len(items) < page_size:
            break
        offset += page_size
    return found, total, pages


# ---------------------------------------------------------------------------
# search_todos
# ---------------------------------------------------------------------------


class TestSearchTodos:
    def test_prefix_query_matches_incomplete_seeds_not_completed(self, mcp, seeded):
        """Query = the shared seed title prefix ('hq-gbl-reg seed') is
        well-scoped on this DB (every seed title carries it). Default
        status='incomplete' means completed/canceled/trashed seeds must be
        absent even though their titles match the query."""
        result = mcp.call_sync(
            "search_todos", query="hq-gbl-reg seed", mode="minimal", limit=500,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}

        # A representative incomplete seed must be present.
        assert seeded.uuid("inbox") in uuids, (
            f"expected incomplete seed 'inbox' in default search_todos results: {result}"
        )
        assert seeded.uuid("today") in uuids

        # Completed/canceled/trashed seeds must NOT appear under the
        # default status='incomplete' filter, even though their titles
        # match the query.
        for class_name in ("completed", "canceled", "trashed"):
            todo_id = seeded.uuid(class_name)
            assert todo_id not in uuids, (
                f"seed {class_name!r} ({todo_id}) unexpectedly present in "
                f"default (status='incomplete') search_todos results"
            )

    @pytest.mark.parametrize("status", ["completed", "canceled"])
    def test_status_filter_each_explicit_value(self, mcp, seeded, status):
        result = mcp.call_sync(
            "search_todos", query="hq-gbl-reg seed", mode="minimal", limit=500, status=status,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        expected_id = seeded.uuid(status)
        assert expected_id in uuids, (
            f"seed {status!r} ({expected_id}) missing from search_todos(status={status!r})"
        )
        # The other explicit-status seed must be absent.
        other = "canceled" if status == "completed" else "completed"
        other_id = seeded.uuid(other)
        assert other_id not in uuids, (
            f"seed {other!r} ({other_id}) unexpectedly present in "
            f"search_todos(status={status!r})"
        )

    @pytest.mark.parametrize("status_value", [None, "None", "null"])
    def test_status_none_variants_include_all_statuses(self, mcp, seeded, status_value):
        """status=None (and the string coercions 'None'/'null') searches
        ALL statuses - completed and canceled seeds must both appear.
        Trashed is still excluded (things.todos() always excludes trashed
        regardless of status)."""
        result = mcp.call_sync(
            "search_todos", query="hq-gbl-reg seed", mode="minimal", limit=500,
            status=status_value,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("completed") in uuids, (
            f"completed seed missing from search_todos(status={status_value!r})"
        )
        assert seeded.uuid("canceled") in uuids, (
            f"canceled seed missing from search_todos(status={status_value!r})"
        )
        assert seeded.uuid("inbox") in uuids
        assert seeded.uuid("trashed") not in uuids, (
            f"trashed seed unexpectedly present in search_todos(status={status_value!r}) "
            f"- things.todos() always excludes trashed regardless of status"
        )

    @pytest.mark.parametrize("query", ["", "   "])
    def test_empty_or_whitespace_query_is_invalid_query(self, mcp, query):
        result = mcp.call_sync("search_todos", query=query)
        assert_read_error(result, "invalid_query")

    def test_special_character_query_matches_notes(self, mcp, seeded):
        """The multiline-notes seed's NOTES contain a quote, a comma, a
        backslash, and an emoji (regression.seed.MULTILINE_NOTES). A
        distinctive substring unique to those notes ('backslash') must
        match via notes, not title, proving notes-matching (the seed's
        title itself never contains that word)."""
        notes = seeded.notes.get("with_multiline_notes")
        assert notes, "seeded.notes['with_multiline_notes'] missing"
        assert "backslash" in notes
        title = seeded.titles["with_multiline_notes"]
        assert "backslash" not in title.lower(), (
            "test assumption violated: the seed title itself contains "
            "'backslash', so a match wouldn't prove notes-matching"
        )

        result = mcp.call_sync(
            "search_todos", query="backslash", mode="minimal", limit=500, status=None,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("with_multiline_notes") in uuids, (
            f"multiline-notes seed not matched by notes-substring query 'backslash': {result}"
        )

        # A comma+quote-bearing substring also matches (exercises the
        # AppleScript-escaper-adjacent characters without being the emoji
        # itself, which is harder to embed literally in a query string).
        result2 = mcp.call_sync(
            "search_todos", query='quoted", with a comma', mode="minimal", limit=500,
            status=None,
        )
        assert "tool_error" not in result2, result2
        uuids2 = {i.get("uuid") for i in result2.get("items", [])}
        assert seeded.uuid("with_multiline_notes") in uuids2, (
            f"multiline-notes seed not matched by quote/comma-bearing query: {result2}"
        )

    def test_limit_offset_windows_disjoint_and_complete(self, mcp, seeded):
        base = mcp.call_sync(
            "search_todos", query="hq-gbl-reg seed", mode="minimal", limit=1, offset=0,
            status=None,
        )
        total = base.get("total")
        assert isinstance(total, int) and total >= 5, (
            f"expected search_todos(query='hq-gbl-reg seed', status=None) total >= 5, got {total}"
        )

        pages_to_check = min(total, 10)
        seen: List[str] = []
        for i in range(pages_to_check):
            r = mcp.call_sync(
                "search_todos", query="hq-gbl-reg seed", mode="minimal", limit=1, offset=i,
                status=None,
            )
            items = r.get("items", [])
            assert len(items) == 1, f"offset={i}: expected exactly 1 item, got {items!r}"
            seen.append(items[0]["uuid"])
            assert r.get("total") == total, (
                f"offset={i}: total drifted from {total} to {r.get('total')}"
            )

        assert len(seen) == len(set(seen)), (
            f"offset windows were not disjoint - duplicate uuids in {seen}"
        )

        bulk = mcp.call_sync(
            "search_todos", query="hq-gbl-reg seed", mode="minimal", limit=pages_to_check,
            offset=0, status=None,
        )
        bulk_uuids = {i["uuid"] for i in bulk.get("items", [])}
        assert bulk_uuids == set(seen), (
            f"union of limit=1 windows {set(seen)} != single limit={pages_to_check} "
            f"window {bulk_uuids}"
        )

    def test_mode_field_sets(self, mcp, seeded):
        todo_id = seeded.uuid("inbox")
        for mode, allowed in (
            ("minimal", {"uuid", "title", "status", "type", "start", "project",
                          "dueDate", "modificationDate", "creationDate"}),
            ("standard", {"uuid", "title", "status", "type", "notes", "dueDate",
                          "modificationDate", "creationDate", "tags", "project",
                          "projectTitle", "heading", "headingTitle", "start",
                          "startDate", "inheritedSomeday", "reminderTime"}),
        ):
            result = mcp.call_sync(
                "search_todos", query="hq-gbl-reg seed", mode=mode, limit=500,
            )
            assert "tool_error" not in result, result
            assert result.get("mode") == mode, result
            by_uuid = {i.get("uuid"): i for i in result.get("items", [])}
            assert todo_id in by_uuid, f"seed 'inbox' missing under mode={mode!r}"
            item = by_uuid[todo_id]
            extra = set(item.keys()) - allowed
            assert not extra, f"search_todos mode={mode!r}: unexpected keys {extra} in {item!r}"

    def test_invalid_mode_is_read_error(self, mcp):
        result = mcp.call_sync("search_todos", query="hq-gbl-reg", mode="bogus")
        assert_read_error(result, "invalid_mode")

    def test_invalid_status_is_read_error(self, mcp):
        result = mcp.call_sync("search_todos", query="hq-gbl-reg", status="bogus")
        assert_read_error(result, "invalid_status")

    @pytest.mark.parametrize("limit", [0, 501])
    def test_limit_out_of_range_is_schema_rejection(self, mcp, limit):
        """limit is a pydantic Field(ge=1, le=500) on search_todos - out of
        range is a FastMCP schema tool_error, not a read-error code."""
        result = mcp.call_sync("search_todos", query="hq-gbl-reg", limit=limit)
        assert "tool_error" in result, (
            f"search_todos(limit={limit}): expected schema tool_error, got {result!r}"
        )

    def test_offset_negative_is_schema_rejection(self, mcp):
        result = mcp.call_sync("search_todos", query="hq-gbl-reg", offset=-1)
        assert "tool_error" in result, result


# ---------------------------------------------------------------------------
# search_advanced
# ---------------------------------------------------------------------------


class TestSearchAdvanced:
    def test_no_status_filter_returns_all_statuses(self, mcp, sandbox):
        """No explicit `status` filter searches ALL statuses (search_advanced's
        own documented default, unlike search_todos/get_todos). Scoped via
        `area` + `type='project'` (targeted, not a full-DB scan) rather
        than `area` alone: things.tasks(area=...) matches only tasks
        DIRECTLY assigned to that area (its own `area` DB column, confirmed
        by reading things/api.py's `tasks()` docstring and database.py's
        `make_filter("TASK.area", area)`) - it does not cascade into a
        project's own to-dos, so the seed to-dos (all filed inside
        sandbox.project_id) are unreachable via `area` alone. And
        `type` must be given explicitly: read_operations.py's
        _search_advanced_sync only adds 'type' to its things.py query when
        `todo_type` is truthy, so with no `type` filter at all it always
        calls things.todos() (to-do only) - a bare `area` filter can never
        surface a project row regardless of status. sandbox.done_project_id
        (directly in the area, marked completed by conftest.py's sandbox
        fixture) is the only directly-area-scoped item with a non-default
        status, so it's the proof used here."""
        result = mcp.call_sync(
            "search_advanced", area=sandbox.area_id, type="project", limit=500,
        )
        assert "tool_error" not in result, result
        items = result.get("items", [])
        statuses = {i.get("status") for i in items}
        assert "completed" in statuses, (
            f"expected a completed project with no status filter (default=ALL): {statuses}"
        )
        uuids = {i.get("uuid") for i in items}
        assert sandbox.done_project_id in uuids, (
            f"completed sandbox project missing from unfiltered-status "
            f"search_advanced(area=..., type='project'): {result}"
        )

    @pytest.mark.parametrize("status", ["incomplete", "completed", "canceled"])
    def test_status_filter_each_value(self, mcp, seeded, sandbox, status):
        result = mcp.call_sync(
            "search_advanced", area=sandbox.area_id, status=status, limit=500,
        )
        assert "tool_error" not in result, result
        items = result.get("items", [])
        assert all(i.get("status") == status for i in items), (
            f"search_advanced(status={status!r}) returned a different status: "
            f"{[i for i in items if i.get('status') != status]}"
        )

    def test_type_todo(self, mcp, sandbox, seeded):
        result = mcp.call_sync(
            "search_advanced", area=sandbox.area_id, type="to-do", status=None, limit=500,
        )
        assert "tool_error" not in result, result
        items = result.get("items", [])
        assert all(i.get("type") == "to-do" for i in items), items
        uuids = {i.get("uuid") for i in items}
        assert seeded.uuid("in_area") in uuids

    def test_type_project(self, mcp, sandbox):
        """search_advanced(type='project') within the sandbox area must
        include the sandbox's own project(s) and every item must carry
        area/areaTitle (dispatched via convert_project, not convert_todo -
        CLAUDE.md 'Project field lists per mode' / hq-f0w.37)."""
        result = mcp.call_sync(
            "search_advanced", area=sandbox.area_id, type="project", status=None,
            mode="detailed", limit=500,
        )
        assert "tool_error" not in result, result
        items = result.get("items", [])
        assert all(i.get("type") == "project" for i in items), items
        uuids = {i.get("uuid") for i in items}
        assert sandbox.project_id in uuids, (
            f"sandbox project missing from search_advanced(area=..., type='project'): {result}"
        )
        for item in items:
            assert "area" in item and "areaTitle" in item, item

    def test_type_heading_returns_sandbox_heading(self, mcp, sandbox):
        """type='heading' returns the sandbox project's own heading. Assert
        the heading row's actual shape: read_operations.py's convert_item()
        dispatches on raw_item['type'] - only 'project' rows go through
        convert_project; everything else (including 'heading') falls
        through to convert_todo. A heading row is therefore expected to
        carry the TODO field set (e.g. 'project'/'projectTitle'), NOT an
        'area'/'areaTitle' pair - assert the actual observed keys and note
        any drift from that expectation rather than assuming either shape
        blindly.

        `area` cannot scope this query down to the sandbox: things.tasks(
        area=...) only matches tasks DIRECTLY assigned to that area (its
        own `area` DB column), and a heading's `area` is never set (it
        belongs to a project, not directly to an area) - confirmed live:
        search_advanced(area=sandbox.area_id, type='heading') returns zero
        rows even though the sandbox heading exists. search_advanced has
        no `project` filter parameter to scope by instead, so this pages
        the type='heading' result set via offset (672 headings observed
        live - comfortably within _MAX_PAGES * 500) rather than filtering
        by area."""
        if sandbox.heading_id is None:
            pytest.skip("sandbox.heading_id is None (heading not confirmed)")
        # Page via mode='minimal' to locate WHICH offset window the sandbox
        # heading sorts into. Even mode='minimal' can truncate a 500-item
        # page below `limit` once its estimated size exceeds the context
        # budget (observed live: 406/500 on page 1 of a 672-heading result
        # set) - so "returned fewer than `limit` items" does NOT mean "no
        # more data" the way it does for a small/non-truncating dataset.
        # Advance `offset` by the nominal page_size (the pre-mode-filtering
        # windowing step - `matches[offset:][:limit]` in
        # _search_advanced_sync - happens BEFORE mode-based truncation, so
        # each successive `offset` step still reaches new underlying items
        # even when a prior page came back short) and stop only once
        # `offset` has reached the pre-limit `total` (from the first
        # response) or `_MAX_PAGES` is exhausted.
        found_offset = None
        page_size = 500
        offset = 0
        total = None
        for _ in range(_MAX_PAGES):
            page = mcp.call_sync(
                "search_advanced", type="heading", status=None, mode="minimal",
                limit=page_size, offset=offset,
            )
            if total is None:
                total = page.get("total")
            uuids_on_page = {i.get("uuid") for i in page.get("items", [])}
            if sandbox.heading_id in uuids_on_page:
                found_offset = offset
                break
            offset += page_size
            if isinstance(total, int) and offset >= total:
                break
        assert found_offset is not None, (
            f"sandbox heading {sandbox.heading_id} not found in "
            f"search_advanced(type='heading', mode='minimal') within {_MAX_PAGES} pages "
            f"(total={total})"
        )

        # Re-fetch the same underlying window in mode='detailed', but at a
        # smaller limit (100, confirmed live to fit under the context
        # budget with zero truncation at this dataset size, unlike
        # limit=500 which truncates ~450/500) sub-scanned across the
        # [found_offset, found_offset+page_size) minimal-mode window, since
        # the underlying `matches[offset:][:limit]` windowing is identical
        # across modes - only the post-slice mode-based truncation differs.
        heading_item = None
        for sub_offset in range(found_offset, found_offset + page_size, 100):
            detailed_page = mcp.call_sync(
                "search_advanced", type="heading", status=None, mode="detailed",
                limit=100, offset=sub_offset,
            )
            by_uuid = {i.get("uuid"): i for i in detailed_page.get("items", [])}
            if sandbox.heading_id in by_uuid:
                heading_item = by_uuid[sandbox.heading_id]
                break
        assert heading_item is not None, (
            f"sandbox heading {sandbox.heading_id} present at offset={found_offset} "
            f"under mode='minimal' but not found under mode='detailed' (limit=100 "
            f"sub-scan) across the same underlying window"
        )
        assert heading_item.get("type") == "heading", heading_item
        # Confirmed dispatch: convert_item() only special-cases type=='project';
        # a heading row goes through convert_todo, so it carries the todo-shaped
        # 'project'/'projectTitle' keys (pointing at its own parent project),
        # not area/areaTitle.
        assert heading_item.get("title") == sandbox.heading_title, heading_item
        assert "area" not in heading_item and "areaTitle" not in heading_item, (
            f"heading row unexpectedly carries area/areaTitle (would indicate "
            f"convert_item() dispatch changed to route headings through "
            f"convert_project): {heading_item!r}"
        )
        assert heading_item.get("project") == sandbox.project_id, heading_item

    def test_tag_filter_sandbox_tag(self, mcp, sandbox, seeded):
        result = mcp.call_sync(
            "search_advanced", tag=sandbox.tag_name, status=None, limit=500,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("with_tag") in uuids, (
            f"'with_tag' seed missing from search_advanced(tag=sandbox tag): {result}"
        )

    def test_area_filter_by_id(self, mcp, sandbox, seeded):
        """area is documented (Field description) as an area UUID; the
        implementation passes it straight through to things.tasks(area=...)
        with no title-resolution of its own."""
        result = mcp.call_sync(
            "search_advanced", area=sandbox.area_id, status=None, limit=500,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("in_area") in uuids, (
            f"'in_area' seed missing from search_advanced(area=sandbox.area_id): {result}"
        )
        # An item filed in a different sandbox project (project_b, not the
        # area itself) must NOT appear via the area filter.
        assert seeded.uuid("in_project_b") not in uuids, (
            f"'in_project_b' seed unexpectedly present via area filter: {result}"
        )

    def test_area_filter_by_title_observed_behavior(self, mcp, sandbox, seeded):
        """Record actual behavior of passing the area TITLE instead of its
        id - things.py's own area matching may or may not accept a title
        string. Assert whatever is actually observed rather than assuming;
        if title-matching turns out to also work, this documents that as a
        (currently undocumented) bonus, not a contract violation."""
        result = mcp.call_sync(
            "search_advanced", area=sandbox.area_title, status=None, limit=500,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        in_area_id = seeded.uuid("in_area")
        # Whichever way things.py resolves a title-shaped `area` value
        # (matches nothing -> empty; matches by title -> same set as the
        # id-based filter), the response itself must still be a well-formed
        # items list, not a tool/read error.
        assert isinstance(uuids, set)
        if in_area_id in uuids:
            # Title-matching happens to work - fine, just note it's not the
            # documented contract (Field description says UUID).
            pass

    def test_combined_tag_and_status_filter(self, mcp, sandbox, seeded):
        """Combined filters: tag + status together further narrow results
        (the 'with_tag' seed is 'incomplete')."""
        result = mcp.call_sync(
            "search_advanced", tag=sandbox.tag_name, status="incomplete", limit=500,
        )
        assert "tool_error" not in result, result
        items = result.get("items", [])
        assert all(i.get("status") == "incomplete" for i in items), items
        uuids = {i.get("uuid") for i in items}
        assert seeded.uuid("with_tag") in uuids, result

        # The same tag with a status the tagged seed does NOT have returns
        # it absent (still a well-formed, non-error result).
        result2 = mcp.call_sync(
            "search_advanced", tag=sandbox.tag_name, status="completed", limit=500,
        )
        assert "tool_error" not in result2, result2
        uuids2 = {i.get("uuid") for i in result2.get("items", [])}
        assert seeded.uuid("with_tag") not in uuids2, result2

    def test_combined_area_and_type_filter(self, mcp, sandbox):
        """Combined filters: area + type='project' together - only project
        rows within the sandbox area."""
        result = mcp.call_sync(
            "search_advanced", area=sandbox.area_id, type="project", status=None, limit=500,
        )
        assert "tool_error" not in result, result
        items = result.get("items", [])
        assert all(i.get("type") == "project" for i in items), items
        uuids = {i.get("uuid") for i in items}
        assert sandbox.project_id in uuids
        assert sandbox.project_b_id in uuids
        assert sandbox.done_project_id in uuids

    def test_start_date_exact_match_semantics(self, mcp, seeded):
        """start_date is an EXACT-value match against things.py's
        start_date field (confirmed by reading _search_advanced_sync: the
        value is passed straight through to things.tasks(start_date=...)),
        not a range. The 'tomorrow' seed (when=tomorrow) has start_date ==
        today+1; querying that exact date must return it, while querying
        today (a different exact date) must not."""
        tomorrow_iso = seeded.dates["tomorrow"].strftime("%Y-%m-%d")
        today_iso = seeded.dates["today"].strftime("%Y-%m-%d")

        result = mcp.call_sync(
            "search_advanced", start_date=tomorrow_iso, status=None, limit=500,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("tomorrow") in uuids, (
            f"'tomorrow' seed (start_date=={tomorrow_iso}) missing from "
            f"search_advanced(start_date={tomorrow_iso!r}): {result}"
        )

        # Cross-check against a things.py-computed expectation directly.
        # Must use type='to-do' to match search_advanced's own actual
        # routing: read_operations.py's _search_advanced_sync only adds
        # 'type' to its things.py query when an explicit `type` filter was
        # given - with no `type` filter (as here) it always calls
        # things.todos() (to-do only), so a project that happens to share
        # the same start_date (e.g. another regression file's scratch
        # someday-project fixture, confirmed live to cause exactly this
        # false mismatch) must be excluded from the expectation too.
        import things
        expected = {
            t["uuid"] for t in things.tasks(
                type="to-do", start_date=tomorrow_iso, status=None,
            ) or []
        }
        assert uuids == expected, (
            f"search_advanced(start_date={tomorrow_iso!r}) uuids {uuids} != "
            f"things.tasks(type='to-do', start_date=...) computed expectation {expected}"
        )

        result_today = mcp.call_sync(
            "search_advanced", start_date=today_iso, status=None, limit=500,
        )
        assert "tool_error" not in result_today, result_today
        uuids_today = {i.get("uuid") for i in result_today.get("items", [])}
        assert seeded.uuid("tomorrow") not in uuids_today, (
            f"'tomorrow' seed unexpectedly present under start_date={today_iso!r} "
            f"(exact-match semantics expected, not a range): {result_today}"
        )

    def test_deadline_exact_match_semantics(self, mcp, seeded):
        """deadline is likewise an EXACT-value match, not a range - the
        'deadline_plus3d' seed (deadline==today+3) must appear at that
        exact date and be absent at a neighboring date."""
        plus3d_iso = seeded.dates["deadline_plus3d"].strftime("%Y-%m-%d")
        today_iso = seeded.dates["deadline_today"].strftime("%Y-%m-%d")

        result = mcp.call_sync(
            "search_advanced", deadline=plus3d_iso, status=None, limit=500,
        )
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert seeded.uuid("deadline_plus3d") in uuids, (
            f"'deadline_plus3d' seed missing from search_advanced(deadline={plus3d_iso!r}): {result}"
        )

        # Same type='to-do' scoping caveat as test_start_date_exact_match_semantics
        # above - search_advanced with no explicit `type` filter always
        # routes through things.todos() (to-do only).
        import things
        expected = {
            t["uuid"] for t in things.tasks(
                type="to-do", deadline=plus3d_iso, status=None,
            ) or []
        }
        assert uuids == expected, (
            f"search_advanced(deadline={plus3d_iso!r}) uuids {uuids} != "
            f"things.tasks(type='to-do', deadline=...) computed expectation {expected}"
        )

        result_today = mcp.call_sync(
            "search_advanced", deadline=today_iso, status=None, limit=500,
        )
        assert "tool_error" not in result_today, result_today
        uuids_today = {i.get("uuid") for i in result_today.get("items", [])}
        assert seeded.uuid("deadline_plus3d") not in uuids_today, (
            f"'deadline_plus3d' seed unexpectedly present under deadline={today_iso!r} "
            f"(exact-match semantics expected, not a range): {result_today}"
        )
        assert seeded.uuid("deadline_today") in uuids_today, (
            f"'deadline_today' seed missing from search_advanced(deadline={today_iso!r}): "
            f"{result_today}"
        )

    @pytest.mark.parametrize("bad_start_date", ["12/25/2024", "2024-13-01", "not-a-date", "2024/12/25"])
    def test_invalid_start_date_format(self, mcp, bad_start_date):
        result = mcp.call_sync("search_advanced", start_date=bad_start_date)
        assert_read_error(result, "invalid_start_date_format")
        assert "example" in result, result

    @pytest.mark.parametrize("bad_deadline", ["12/25/2024", "2024-13-01", "not-a-date", "2024/12/25"])
    def test_invalid_deadline_format(self, mcp, bad_deadline):
        result = mcp.call_sync("search_advanced", deadline=bad_deadline)
        assert_read_error(result, "invalid_deadline_format")
        assert "example" in result, result

    def test_unknown_tag_error_shape(self, mcp, sandbox):
        bogus_tag = sandbox.tag_name.upper() + "-nonexistent-xyz"
        result = mcp.call_sync("search_advanced", tag=bogus_tag)
        assert_read_error(result, "unknown_tag")
        assert result.get("tag") == bogus_tag, result
        assert isinstance(result.get("suggestions"), list), result

    def test_unknown_tag_wrong_case_suggests_real_tag(self, mcp, sandbox):
        """A wrong-case variant of a real (sandbox) tag returns unknown_tag
        with the correctly-cased tag as a suggestion."""
        wrong_case = sandbox.tag_name.upper()
        if wrong_case == sandbox.tag_name:
            pytest.skip("sandbox tag name has no lowercase characters to invert")
        result = mcp.call_sync("search_advanced", tag=wrong_case)
        assert_read_error(result, "unknown_tag")
        assert sandbox.tag_name in result.get("suggestions", []), result

    def test_invalid_status_is_schema_rejection(self, mcp):
        """status is Field(pattern=...) on search_advanced - invalid is a
        schema tool_error, not the read-error-contract shape."""
        result = mcp.call_sync("search_advanced", status="bogus")
        assert "tool_error" in result, result

    def test_invalid_type_is_schema_rejection(self, mcp):
        result = mcp.call_sync("search_advanced", type="bogus")
        assert "tool_error" in result, result

    def test_limit_offset_windows_disjoint_and_stable_total(self, mcp, sandbox, seeded):
        """`area` alone only yields 1 directly-area-scoped to-do (the
        'in_area' seed - confirmed above: things.tasks(area=...) matches
        only tasks directly assigned to that area, and search_advanced
        with no explicit `type` filter always routes through
        things.todos() - see read_operations.py's _search_advanced_sync,
        which only adds 'type' to query_params when `todo_type` is truthy
        - so it can never return the sandbox's projects either). Use
        tag=sandbox.tag_name combined with status=None isn't broad enough
        (also 1 item) - use the unfiltered `type='to-do'` result set
        instead (thousands of items live), which is still a well-formed,
        deterministic dataset for the STRUCTURAL pagination contract under
        test here (disjoint windows, stable total) - membership isn't the
        point of this test, offset/limit/total coherence is."""
        base = mcp.call_sync(
            "search_advanced", type="to-do", status=None, limit=1, offset=0,
        )
        total = base.get("total")
        assert isinstance(total, int) and total >= 5, (
            f"expected search_advanced(type='to-do', status=None) total >= 5, got {total}"
        )

        pages_to_check = min(total, 10)
        seen: List[str] = []
        for i in range(pages_to_check):
            r = mcp.call_sync(
                "search_advanced", type="to-do", status=None, limit=1, offset=i,
            )
            items = r.get("items", [])
            assert len(items) == 1, f"offset={i}: expected exactly 1 item, got {items!r}"
            seen.append(items[0]["uuid"])
            assert r.get("total") == total, (
                f"offset={i}: total drifted from {total} to {r.get('total')}"
            )

        assert len(seen) == len(set(seen)), (
            f"offset windows were not disjoint - duplicate uuids in {seen}"
        )

        bulk = mcp.call_sync(
            "search_advanced", type="to-do", status=None, limit=pages_to_check, offset=0,
        )
        bulk_uuids = {i["uuid"] for i in bulk.get("items", [])}
        assert bulk_uuids == set(seen), (
            f"union of limit=1 windows {set(seen)} != single limit={pages_to_check} "
            f"window {bulk_uuids}"
        )

    @pytest.mark.parametrize("limit", [0, 501])
    def test_limit_out_of_range_is_schema_rejection(self, mcp, limit):
        result = mcp.call_sync("search_advanced", limit=limit)
        assert "tool_error" in result, (
            f"search_advanced(limit={limit}): expected schema tool_error, got {result!r}"
        )

    def test_offset_negative_is_schema_rejection(self, mcp):
        result = mcp.call_sync("search_advanced", offset=-1)
        assert "tool_error" in result, result


# ---------------------------------------------------------------------------
# get_todos
# ---------------------------------------------------------------------------


class TestGetTodos:
    # Seed classes filed directly (or under-heading) in sandbox.project_id
    # via list_id=sandbox.project_id in seed.py, keyed by their expected
    # status (see seed.py for which classes get flipped to completed/
    # canceled after creation).
    _INCOMPLETE_IN_PROJECT = {
        "today", "evening", "tomorrow", "plus5d", "plus40d",
        "anytime_in_project", "under_heading",
        "deadline_today", "deadline_plus3d", "deadline_plus20d",
        "deadline_plus60d", "overdue", "with_tag", "with_checklist",
        "with_multiline_notes", "activating_plus10d",
    }

    def _expected_uuids_for_status(self, sandbox, status):
        """Compute the expected uuid set directly from things.py, scoped to
        this session's seed titles (prefix), tolerating other files'
        leftovers in the shared sandbox project."""
        import things

        kwargs = {"project": sandbox.project_id}
        if status is None:
            todos = []
            for s in ("incomplete", "completed", "canceled"):
                todos.extend(things.todos(status=s, **kwargs) or [])
        else:
            todos = things.todos(status=status, **kwargs) or []
        return {
            t["uuid"] for t in todos
            if t.get("title", "").startswith("hq-gbl-reg seed")
        }

    @pytest.mark.parametrize("status", ["incomplete", "completed", "canceled", None])
    def test_status_each_value_matches_things_py_expectation(self, mcp, sandbox, seeded, status):
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status=status,
            mode="minimal", limit=500,
        )
        assert "tool_error" not in result, result
        items = result.get("items", [])
        uuids = {
            i["uuid"] for i in items
            if i.get("title", "").startswith("hq-gbl-reg seed")
        }
        expected = self._expected_uuids_for_status(sandbox, status)
        assert uuids == expected, (
            f"get_todos(project_uuid=..., status={status!r}): got {uuids}, "
            f"expected (computed from things.py) {expected}"
        )

        # No project rows ever, regardless of status.
        assert all(i.get("type") != "project" for i in items), (
            f"get_todos returned a project row: "
            f"{[i for i in items if i.get('type') == 'project']}"
        )

    def test_status_incomplete_matches_seed_set_exactly(self, mcp, sandbox, seeded):
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status="incomplete",
            mode="minimal", limit=500,
        )
        assert "tool_error" not in result, result
        uuids = {i["uuid"] for i in result.get("items", [])}
        expected_ids = {seeded.uuid(c) for c in self._INCOMPLETE_IN_PROJECT}
        expected_ids.discard(None)
        missing = expected_ids - uuids
        assert not missing, f"expected incomplete seeds missing from get_todos: {missing}"
        # completed/canceled seeds must be absent.
        assert seeded.uuid("completed") not in uuids
        assert seeded.uuid("canceled") not in uuids

    def test_include_items_attaches_checklist_for_with_checklist_seed(self, mcp, sandbox, seeded):
        from regression.seed import CHECKLIST_ITEMS

        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status="incomplete",
            include_items=True, mode="detailed", limit=500,
        )
        assert "tool_error" not in result, result
        by_uuid = {i["uuid"]: i for i in result.get("items", [])}
        checklist_id = seeded.uuid("with_checklist")
        assert checklist_id in by_uuid, "with_checklist seed missing"
        item = by_uuid[checklist_id]
        assert "checklist" in item, item
        checklist = item["checklist"]
        assert isinstance(checklist, list) and len(checklist) == len(CHECKLIST_ITEMS), checklist
        titles = {c["title"] for c in checklist}
        assert titles == set(CHECKLIST_ITEMS), checklist

        # A seed with no checklist gets an empty (or absent-then-normalized)
        # checklist, never a populated one.
        no_checklist_id = seeded.uuid("today")
        if no_checklist_id in by_uuid:
            other_checklist = by_uuid[no_checklist_id].get("checklist", [])
            assert other_checklist == [], other_checklist

    def test_include_items_false_omits_checklist(self, mcp, sandbox, seeded):
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status="incomplete",
            include_items=False, mode="detailed", limit=500,
        )
        assert "tool_error" not in result, result
        by_uuid = {i["uuid"]: i for i in result.get("items", [])}
        checklist_id = seeded.uuid("with_checklist")
        assert checklist_id in by_uuid
        assert "checklist" not in by_uuid[checklist_id], by_uuid[checklist_id]

    def test_under_heading_seed_carries_project_backfilled(self, mcp, sandbox, seeded):
        """A to-do filed under a heading (CLAUDE.md: things.py never stamps
        project/project_title directly on a heading-child row) must still
        report project/projectTitle, backfilled via
        _fill_project_from_heading."""
        under_heading_id = seeded.uuid("under_heading")
        if under_heading_id is None:
            pytest.skip(seeded.skipped.get("under_heading", "under_heading seed not created"))

        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status="incomplete",
            mode="standard", limit=500,
        )
        assert "tool_error" not in result, result
        by_uuid = {i["uuid"]: i for i in result.get("items", [])}
        assert under_heading_id in by_uuid, "under_heading seed missing"
        item = by_uuid[under_heading_id]
        assert item.get("project") == sandbox.project_id, item
        assert item.get("projectTitle") == sandbox.project_title, item
        assert item.get("heading") == sandbox.heading_id, item
        assert item.get("headingTitle") == sandbox.heading_title, item

    def test_project_rows_never_returned_any_status(self, mcp, sandbox):
        """Even with status=None (the widest filter), get_todos never
        returns a project row - things.todos() is always type='to-do'
        under the hood."""
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status=None,
            mode="minimal", limit=500,
        )
        assert "tool_error" not in result, result
        items = result.get("items", [])
        assert all(i.get("type") == "to-do" for i in items), (
            f"get_todos returned a non-to-do row: "
            f"{[i for i in items if i.get('type') != 'to-do']}"
        )

    def test_limit_1_and_total(self, mcp, sandbox, seeded):
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status="incomplete",
            mode="minimal", limit=1,
        )
        assert "tool_error" not in result, result
        assert len(result.get("items", [])) == 1, result
        total_at_1 = result.get("total")
        assert isinstance(total_at_1, int) and total_at_1 >= len(self._INCOMPLETE_IN_PROJECT), (
            f"total={total_at_1} is less than known incomplete-in-project seed count "
            f"{len(self._INCOMPLETE_IN_PROJECT)}"
        )

        result_500 = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status="incomplete",
            mode="minimal", limit=500,
        )
        assert result_500.get("total") == total_at_1, (
            f"total changed between limit=1 ({total_at_1}) and limit=500 "
            f"({result_500.get('total')}) on an unchanged dataset"
        )

    def test_invalid_limit_is_read_error(self, mcp, sandbox):
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, limit=501,
        )
        assert_read_error(result, "invalid_limit")
        result0 = mcp.call_sync("get_todos", project_uuid=sandbox.project_id, limit=0)
        assert_read_error(result0, "invalid_limit")
        result_bad = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, limit="not-a-number",
        )
        assert_read_error(result_bad, "invalid_limit")

    def test_invalid_mode_is_read_error(self, mcp, sandbox):
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, mode="bogus",
        )
        assert_read_error(result, "invalid_mode")

    def test_invalid_status_is_read_error(self, mcp, sandbox):
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status="bogus",
        )
        assert_read_error(result, "invalid_status")

    @pytest.mark.parametrize("status_value", ["None", "null"])
    def test_status_string_none_variants_normalize_to_all(self, mcp, sandbox, seeded, status_value):
        result = mcp.call_sync(
            "get_todos", project_uuid=sandbox.project_id, status=status_value,
            mode="minimal", limit=500,
        )
        assert "tool_error" not in result, result
        uuids = {i["uuid"] for i in result.get("items", [])}
        assert seeded.uuid("completed") in uuids, (
            f"completed seed missing from get_todos(status={status_value!r}) - "
            f"expected normalization to status=None (all statuses)"
        )
        assert seeded.uuid("canceled") in uuids


# ---------------------------------------------------------------------------
# get_tagged_items
# ---------------------------------------------------------------------------


class TestGetTaggedItems:
    def test_exact_seed_set(self, mcp, sandbox, seeded):
        """The 'with_tag' seed must be present. NOT asserted as the exact
        set: the shared sandbox tag (sandbox.tag_name) is also applied to
        throwaway to-dos by other regression files in this same session
        (test_tags.py, test_update_todo.py, test_bulk_and_move.py all call
        add_tags/update_todo/bulk_update_todos with tags=sandbox.tag_name)
        - when run as part of the full `tests/regression` suite (not this
        file in isolation), get_tagged_items(tag=sandbox.tag_name) reflects
        whatever the current cross-file tag state is, which can include
        more than just this seed."""
        result = mcp.call_sync("get_tagged_items", tag=sandbox.tag_name)
        assert "tool_error" not in result, result
        assert result.get("tag") == sandbox.tag_name, result
        uuids = {i["uuid"] for i in result.get("items", [])}
        assert seeded.uuid("with_tag") in uuids, (
            f"expected get_tagged_items(tag=sandbox tag) to include the "
            f"'with_tag' seed, got {uuids}"
        )
        # Every returned item must itself carry the sandbox tag (a
        # structural guarantee independent of what else tagged it).
        for item in result.get("items", []):
            assert sandbox.tag_name in (item.get("tags") or []), item

    def test_unknown_tag_error_shape(self, mcp, sandbox):
        bogus_tag = sandbox.tag_name + "-nonexistent-xyz"
        result = mcp.call_sync("get_tagged_items", tag=bogus_tag)
        assert_read_error(result, "unknown_tag")
        assert result.get("tag") == bogus_tag, result
        assert isinstance(result.get("suggestions"), list), result

    def test_unknown_tag_wrong_case_suggests_real_tag(self, mcp, sandbox):
        wrong_case = sandbox.tag_name.upper()
        if wrong_case == sandbox.tag_name:
            pytest.skip("sandbox tag name has no lowercase characters to invert")
        result = mcp.call_sync("get_tagged_items", tag=wrong_case)
        assert_read_error(result, "unknown_tag")
        assert sandbox.tag_name in result.get("suggestions", []), result
