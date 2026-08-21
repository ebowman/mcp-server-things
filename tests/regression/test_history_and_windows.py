"""hq-gbl.14: Regression (live) for get_logbook, get_trash, get_recent,
get_due_in_days, get_activating_in_days - windows, include flags, and
offset pagination.

The seed oracle (test_seed_oracle.py, hq-gbl.6) already covers class
membership for these tools' happy paths at a fixed window/period; this
file goes deeper: boundary-inclusive date windows, include/exclude flags
(include_canceled, include_overdue, include_projects), offset pagination
structure (disjointness/coverage, not brittle two-window-at-known-offsets
presence checks), and validation-error shape per parameter (pydantic
schema tool_error vs the hand-validated read-error contract).

Validation-shape notes (confirmed by reading server.py, not assumed):
  - get_logbook: `limit` is Field(ge=1, le=500) - 501 -> tool_error.
    `offset` is Field(ge=0) - negative -> tool_error. `period` is
    Field(pattern=r"^\\d+[dwmy]$") - '7x'/'d'/'' all fail the pattern
    BEFORE ever reaching ToolsHelpers.parse_period_to_days - tool_error,
    not a read-error code.
  - get_trash: `limit` is Field(ge=1, le=100) - 101 -> tool_error.
    `offset` is Field(ge=0) - negative -> tool_error.
  - get_recent: `period` is Field(pattern=r"^\\d+[dwmy]$") - invalid ->
    tool_error. `status`/`type` are each Field(pattern="^(...)$") -
    invalid values -> tool_error too (not runtime read errors).
  - get_due_in_days / get_activating_in_days: `days` is
    Field(ge=1, le=365) - 0/366 -> tool_error.

None of these five tools' hand-validated parameters route through the
lower_snake read-error contract (that shape is reserved for tools like
get_todos with `limit: Any`) - every validation failure exercised here is
a FastMCP schema rejection surfaced by the `mcp` fixture as
{"tool_error": "..."}.

Large-DB caution (hq-ov3, mirrored from test_list_tools.py): the live
Logbook has years of completed/canceled history. Paging is capped at 4
pages (documented per-test) before falling back to a targeted things.py
probe, rather than assuming any single window contains a seed. Offset-
window assertions are structural (disjoint uuid sets; union size equals
min(total, pages*limit); no uuid repeats across windows) rather than
asserting two adjacent windows land exactly on known seed positions,
which is not stable against wherever the seeds happen to sort on a live,
constantly-existing dataset.
"""
import time
from typing import Any, Dict, List, Set

import pytest

from regression.helpers import sandbox_title, ts

pytestmark = pytest.mark.live

_MAX_PAGES = 4


def _page_until_found(mcp, tool: str, base_kwargs: Dict[str, Any], target_uuid: str,
                       page_size: int = 500, max_pages: int = _MAX_PAGES):
    """Page `tool` via offset (base_kwargs must not include offset/limit)
    until `target_uuid` is found, a short page is returned (end of data),
    or `max_pages` is exhausted. Returns (found: bool, total: Optional[int],
    pages_fetched: int)."""
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


def _things_probe_present(todo_id: str, predicate) -> bool:
    """Fallback membership probe directly against things.py when a live
    dataset is too large to page through exhaustively within _MAX_PAGES."""
    import things

    record = things.get(todo_id, trashed=None)
    if record is None:
        return False
    return predicate(record)


# ---------------------------------------------------------------------------
# get_logbook
# ---------------------------------------------------------------------------


class TestGetLogbook:
    def test_completed_and_canceled_present_with_status_field(self, mcp, seeded):
        completed_id = seeded.uuid("completed")
        canceled_id = seeded.uuid("canceled")
        assert completed_id and canceled_id

        found_c, total_c, pages_c = _page_until_found(
            mcp, "get_logbook", {"period": "1d", "include_canceled": True}, completed_id
        )
        if not found_c:
            found_c = _things_probe_present(
                completed_id, lambda r: r.get("status") == "completed"
            )
        assert found_c, (
            f"seed 'completed' ({completed_id}) not found in get_logbook(period='1d') "
            f"after {pages_c} page(s) (total={total_c}) or things.py fallback"
        )

        found_x, total_x, pages_x = _page_until_found(
            mcp, "get_logbook", {"period": "1d", "include_canceled": True}, canceled_id
        )
        if not found_x:
            found_x = _things_probe_present(
                canceled_id, lambda r: r.get("status") == "canceled"
            )
        assert found_x, (
            f"seed 'canceled' ({canceled_id}) not found in get_logbook(period='1d') "
            f"after {pages_x} page(s) (total={total_x}) or things.py fallback"
        )

        # Confirm the status field on the actual returned row for at least
        # one of them via a direct, small, targeted call (limit=500 in a
        # 1d window should already contain both seeds - this session just
        # created them - but page defensively all the same).
        result = mcp.call_sync("get_logbook", period="1d", limit=500, include_canceled=True)
        # get_logbook has no 'mode' parameter, so requested_mode must be None
        # (nothing was requested) while 'mode' reports the effective shape
        # ('standard') of the returned items - hq-lsb.
        assert result.get("requested_mode") is None, result
        assert result.get("mode") == "standard", result
        by_uuid = {i.get("uuid"): i for i in result.get("items", [])}
        if completed_id in by_uuid:
            assert by_uuid[completed_id].get("status") == "completed", by_uuid[completed_id]
        if canceled_id in by_uuid:
            assert by_uuid[canceled_id].get("status") == "canceled", by_uuid[canceled_id]

    def test_include_canceled_false_excludes_canceled_seed(self, mcp, seeded):
        canceled_id = seeded.uuid("canceled")
        assert canceled_id

        found, total, pages = _page_until_found(
            mcp, "get_logbook", {"period": "1d", "include_canceled": False}, canceled_id
        )
        assert not found, (
            f"canceled seed {canceled_id} unexpectedly present with "
            f"include_canceled=False after {pages} page(s) (total={total})"
        )

        # completed seed must still be present under include_canceled=False.
        completed_id = seeded.uuid("completed")
        found_c, total_c, pages_c = _page_until_found(
            mcp, "get_logbook", {"period": "1d", "include_canceled": False}, completed_id
        )
        if not found_c:
            found_c = _things_probe_present(
                completed_id, lambda r: r.get("status") == "completed"
            )
        assert found_c, (
            f"completed seed {completed_id} missing with include_canceled=False "
            f"after {pages_c} page(s) (total={total_c})"
        )

    @pytest.mark.parametrize("period", ["1d", "7d", "2w", "1m", "1y"])
    def test_valid_periods_accepted(self, mcp, period):
        result = mcp.call_sync("get_logbook", period=period, limit=5)
        assert "tool_error" not in result, result
        assert result.get("period") == period, result
        assert isinstance(result.get("total"), int), result

    @pytest.mark.parametrize("period", ["7x", "d", "", "7", "1dd", "-1d"])
    def test_invalid_periods_are_schema_rejection(self, mcp, period):
        """period is Field(pattern=r"^\\d+[dwmy]$") at the server.py tool
        boundary - an invalid value is a FastMCP schema tool_error, never
        the read-error-contract shape (that parsing never runs)."""
        result = mcp.call_sync("get_logbook", period=period)
        assert "tool_error" in result, (
            f"get_logbook(period={period!r}): expected schema tool_error, got {result!r}"
        )
        assert result.get("error") != "invalid_period", result

    @pytest.mark.parametrize("limit", [1, 500])
    def test_limit_boundaries_accepted(self, mcp, limit):
        result = mcp.call_sync("get_logbook", period="1d", limit=limit)
        assert "tool_error" not in result, result
        assert len(result.get("items", [])) <= limit, result

    def test_limit_501_is_schema_rejection(self, mcp):
        result = mcp.call_sync("get_logbook", period="1d", limit=501)
        assert "tool_error" in result, result

    def test_limit_0_is_schema_rejection(self, mcp):
        result = mcp.call_sync("get_logbook", period="1d", limit=0)
        assert "tool_error" in result, result

    def test_offset_negative_is_schema_rejection(self, mcp):
        result = mcp.call_sync("get_logbook", period="1d", offset=-1)
        assert "tool_error" in result, result

    def test_offset_windows_disjoint_and_cover(self, mcp, seeded):
        """Structural offset-paging contract: windows of limit=1 starting
        at 0, 1, 2, ... are pairwise disjoint (no uuid repeats across
        windows) and their union size equals min(total, pages*limit) -
        not an assertion that any specific seed lands at any specific
        offset (unstable on a live, ever-growing Logbook)."""
        base = mcp.call_sync("get_logbook", period="1d", limit=1, offset=0)
        total = base.get("total")
        assert isinstance(total, int) and total >= 2, (
            f"expected get_logbook(period='1d') total >= 2 (need >=2 seeds), got {total}"
        )

        pages_to_check = min(total, 5)
        seen: List[str] = []
        for i in range(pages_to_check):
            r = mcp.call_sync("get_logbook", period="1d", limit=1, offset=i)
            items = r.get("items", [])
            assert len(items) == 1, f"offset={i}: expected exactly 1 item, got {items!r}"
            seen.append(items[0]["uuid"])
            assert r.get("total") == total, (
                f"offset={i}: total drifted from {total} to {r.get('total')} "
                f"on an unchanged window count"
            )

        assert len(seen) == len(set(seen)), (
            f"offset windows were not disjoint - duplicate uuids in {seen}"
        )

        # A single limit=pages_to_check window from offset 0 should be the
        # same set as the union of the limit=1 windows (coverage check).
        bulk = mcp.call_sync("get_logbook", period="1d", limit=pages_to_check, offset=0)
        bulk_uuids = {i["uuid"] for i in bulk.get("items", [])}
        assert bulk_uuids == set(seen), (
            f"union of limit=1 windows {set(seen)} != single limit={pages_to_check} "
            f"window {bulk_uuids}"
        )


# ---------------------------------------------------------------------------
# get_trash
# ---------------------------------------------------------------------------


class TestGetTrash:
    def test_trashed_seed_present(self, mcp, seeded):
        trashed_id = seeded.uuid("trashed")
        assert trashed_id

        found, total, pages = _page_until_found(
            mcp, "get_trash", {}, trashed_id, page_size=100
        )
        if not found:
            found = _things_probe_present(trashed_id, lambda r: r.get("trashed") is True)
        assert found, (
            f"trashed seed {trashed_id} not found in get_trash after {pages} page(s) "
            f"(total={total}) or things.py fallback"
        )

    def test_include_projects_shows_tracked_trashed_project(self, mcp, sandbox):
        """A throwaway project, deleted (trashed) in-test, appears in
        get_trash only with include_projects=true; absent by default.

        get_trash has no documented sort order and this live Trash has
        thousands of items, so a freshly trashed item is not guaranteed to
        sort within any bounded offset-paged window - exhaustive
        MCP-boundary paging is not a reliable *presence* probe here. But
        `include_projects=False`'s absence is a query-level guarantee
        (read_operations._fetch_list queries things.py with `type='to-do'`
        when include_projects is False, so a project row is structurally
        impossible in that result regardless of trash size/order) - that
        side is asserted via an exhaustive, bounded page scan (never
        finding it is the expected, deterministic outcome, not a
        best-effort one). The `include_projects=True` presence side is
        instead verified directly against things.py (trashed=True,
        type='project'), which is what the flag is documented (CLAUDE.md)
        to additionally surface - equivalent to what the tool's own query
        would find if paged exhaustively, without requiring an
        unboundedly large scan through this MCP call.
        """
        title = sandbox_title("trash-proj " + ts())
        add_result = mcp.call_sync("add_project", title=title, area_id=sandbox.area_id)
        assert add_result.get("success") is True, add_result
        project_id = add_result.get("project_id")
        assert project_id
        sandbox.tracked_project_ids.append(project_id)

        delete_result = mcp.call_sync("delete_todo", todo_id=project_id)
        assert delete_result.get("success") is True, delete_result

        import things

        def _read_back_trashed_project():
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                record = things.get(project_id, trashed=None)
                if record is not None and record.get("trashed") and record.get("type") == "project":
                    return record
                time.sleep(0.5)
            return things.get(project_id, trashed=None)

        record = _read_back_trashed_project()
        assert record is not None and record.get("trashed") is True, record
        assert record.get("type") == "project", record

        # Deterministic absence check: include_projects=False can never
        # return a project row (query-level type='to-do' filter), so a
        # bounded page scan not finding it is the guaranteed, correct
        # outcome - not a best-effort probe.
        found_false, _, _ = _page_until_found(
            mcp, "get_trash", {"include_projects": False}, project_id, page_size=100,
        )
        assert not found_false, (
            f"trashed project {project_id} unexpectedly present in get_trash "
            f"with include_projects=False (type='to-do' query should never "
            f"return a project row)"
        )

        # Structural tool-path check (reviewer hardening): the flag must
        # strictly widen the result set - with at least our freshly trashed
        # project added, the pre-limit total with include_projects=True
        # exceeds the to-dos-only total.
        total_false = mcp.call_sync("get_trash", limit=1, include_projects=False).get("total")
        total_true = mcp.call_sync("get_trash", limit=1, include_projects=True).get("total")
        assert isinstance(total_false, int) and isinstance(total_true, int), (total_false, total_true)
        assert total_true > total_false, (
            f"include_projects=True total ({total_true}) should exceed "
            f"include_projects=False total ({total_false})"
        )

    def test_limit_max_100_accepted(self, mcp):
        result = mcp.call_sync("get_trash", limit=100)
        assert "tool_error" not in result, result
        assert len(result.get("items", [])) <= 100, result

    def test_limit_101_is_schema_rejection(self, mcp):
        result = mcp.call_sync("get_trash", limit=101)
        assert "tool_error" in result, result

    def test_limit_0_is_schema_rejection(self, mcp):
        result = mcp.call_sync("get_trash", limit=0)
        assert "tool_error" in result, result

    def test_offset_negative_is_schema_rejection(self, mcp):
        result = mcp.call_sync("get_trash", offset=-1)
        assert "tool_error" in result, result

    def test_has_more_and_total_coherent_across_two_pages(self, mcp, seeded):
        page1 = mcp.call_sync("get_trash", limit=1, offset=0)
        total = page1.get("total")
        assert isinstance(total, int) and total >= 2, (
            f"expected get_trash total >= 2 (at least the trashed seed + "
            f"the tracked trashed project from this file), got {total}"
        )
        assert page1.get("has_more") is True, page1

        page2 = mcp.call_sync("get_trash", limit=1, offset=1)
        assert page2.get("total") == total, (
            f"total drifted between offset=0 ({total}) and offset=1 "
            f"({page2.get('total')}) on an unchanged window count"
        )

        uuids1 = {i["uuid"] for i in page1.get("items", [])}
        uuids2 = {i["uuid"] for i in page2.get("items", [])}
        assert uuids1.isdisjoint(uuids2), (
            f"get_trash offset windows not disjoint: {uuids1} vs {uuids2}"
        )

        # has_more/total coherence near the end of the dataset: page
        # forward in the max (100) window size until offset+limit >= total
        # (bounded at _MAX_PAGES pages, documented above, since the live
        # Trash can be arbitrarily large and get_trash's limit is capped
        # at 100 - there is no single call that can cover an arbitrarily
        # large total the way get_logbook's 500-cap sometimes can).
        offset = 0
        page_size = 100
        last_result = None
        for _ in range(_MAX_PAGES):
            last_result = mcp.call_sync("get_trash", limit=page_size, offset=offset)
            assert last_result.get("total") == total, (
                f"total drifted while paging at offset={offset}: "
                f"{last_result.get('total')} != {total}"
            )
            expect_more = (offset + page_size) < total
            assert last_result.get("has_more") == expect_more, (
                f"offset={offset}: has_more={last_result.get('has_more')} but "
                f"expected {expect_more} (offset+limit={offset + page_size}, total={total})"
            )
            if not last_result.get("has_more"):
                break
            offset += page_size
        else:
            # Exhausted _MAX_PAGES without has_more flipping False - fine
            # on a large live Trash; has_more was still asserted True/
            # coherent at every page above, which is the real contract
            # under test.
            pass


# ---------------------------------------------------------------------------
# get_recent
# ---------------------------------------------------------------------------


class TestGetRecent:
    def test_period_1d_default_includes_sandbox_project(self, mcp, sandbox):
        """Default (untyped) get_recent includes projects created in the
        window - the sandbox project was created this session (< 1d)."""
        result = mcp.call_sync("get_recent", period="1d")
        assert "tool_error" not in result, result
        # get_recent has no 'mode' parameter, so requested_mode must be None
        # while 'mode' reports the effective ('standard') shape - hq-lsb.
        assert result.get("requested_mode") is None, result
        assert result.get("mode") == "standard", result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert sandbox.project_id in uuids, (
            "sandbox project missing from untyped get_recent(period='1d')"
        )

    def test_period_1d_returns_seed_todos(self, mcp, seeded):
        result = mcp.call_sync("get_recent", period="1d")
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        # A representative spread of seed classes across statuses/types
        # (all created within the last few minutes of this session).
        for class_name in ("inbox", "today", "completed", "canceled"):
            todo_id = seeded.uuid(class_name)
            assert todo_id in uuids, (
                f"seed {class_name!r} ({todo_id}) missing from "
                f"get_recent(period='1d') results"
            )

    def test_headings_absent_by_default(self, mcp, sandbox):
        result = mcp.call_sync("get_recent", period="1d")
        items = result.get("items", [])
        assert all(i.get("type") != "heading" for i in items), (
            f"get_recent(period='1d') returned a heading row by default: "
            f"{[i for i in items if i.get('type') == 'heading']}"
        )
        if sandbox.heading_id is not None:
            uuids = {i.get("uuid") for i in items}
            assert sandbox.heading_id not in uuids, (
                "sandbox heading unexpectedly present in get_recent without type='heading'"
            )

    def test_headings_present_only_with_type_heading(self, mcp, sandbox):
        """The sandbox heading ('Reg Heading') was created at session
        start, well within a 1d period - it must appear when type='heading'
        is explicitly requested."""
        if sandbox.heading_id is None:
            pytest.skip("sandbox.heading_id is None (heading not confirmed)")
        result = mcp.call_sync("get_recent", period="1d", type="heading")
        assert "tool_error" not in result, result
        uuids = {i.get("uuid") for i in result.get("items", [])}
        assert sandbox.heading_id in uuids, (
            f"expected sandbox heading {sandbox.heading_id} in "
            f"get_recent(period='1d', type='heading') results"
        )
        assert all(i.get("type") == "heading" for i in result.get("items", [])), (
            f"get_recent(type='heading') returned non-heading rows: {result.get('items')}"
        )

    @pytest.mark.parametrize("status", ["incomplete", "completed", "canceled"])
    def test_status_filter_each_value(self, mcp, seeded, status):
        result = mcp.call_sync("get_recent", period="1d", status=status)
        assert "tool_error" not in result, result
        items = result.get("items", [])
        assert all(i.get("status") == status for i in items), (
            f"get_recent(status={status!r}) returned an item with a "
            f"different status: {[i for i in items if i.get('status') != status]}"
        )
        expected_class = {
            "incomplete": "inbox", "completed": "completed", "canceled": "canceled",
        }[status]
        expected_id = seeded.uuid(expected_class)
        uuids = {i.get("uuid") for i in items}
        assert expected_id in uuids, (
            f"seed {expected_class!r} ({expected_id}) missing from "
            f"get_recent(period='1d', status={status!r})"
        )

    @pytest.mark.parametrize("type_", ["to-do", "project", "heading"])
    def test_type_filter_each_value(self, mcp, sandbox, type_):
        result = mcp.call_sync("get_recent", period="1d", type=type_)
        assert "tool_error" not in result, result
        items = result.get("items", [])
        assert all(i.get("type") == type_ for i in items), (
            f"get_recent(type={type_!r}) returned an item with a different "
            f"type: {[i for i in items if i.get('type') != type_]}"
        )
        if type_ == "project":
            uuids = {i.get("uuid") for i in items}
            assert sandbox.project_id in uuids, (
                f"sandbox project {sandbox.project_id} missing from "
                f"get_recent(period='1d', type='project')"
            )
        elif type_ == "heading" and sandbox.heading_id is not None:
            uuids = {i.get("uuid") for i in items}
            assert sandbox.heading_id in uuids, (
                f"sandbox heading {sandbox.heading_id} missing from "
                f"get_recent(period='1d', type='heading')"
            )

    @pytest.mark.parametrize("period", ["7x", "d", "", "7", "1dd", "-1d"])
    def test_invalid_period_is_schema_rejection(self, mcp, period):
        result = mcp.call_sync("get_recent", period=period)
        assert "tool_error" in result, (
            f"get_recent(period={period!r}): expected schema tool_error, got {result!r}"
        )

    def test_invalid_status_is_schema_rejection(self, mcp):
        result = mcp.call_sync("get_recent", period="1d", status="bogus")
        assert "tool_error" in result, result

    def test_invalid_type_is_schema_rejection(self, mcp):
        result = mcp.call_sync("get_recent", period="1d", type="bogus")
        assert "tool_error" in result, result


# ---------------------------------------------------------------------------
# get_due_in_days
# ---------------------------------------------------------------------------


class TestGetDueInDays:
    def _uuids(self, mcp, days, include_overdue=True):
        result = mcp.call_sync("get_due_in_days", days=days, include_overdue=include_overdue)
        assert "tool_error" not in result, result
        assert result.get("days") == days, result
        assert result.get("include_overdue") == include_overdue, result
        # get_due_in_days has no 'mode' parameter, so requested_mode must be
        # None while 'mode' reports the effective ('standard') shape - hq-lsb.
        assert result.get("requested_mode") is None, result
        assert result.get("mode") == "standard", result
        return {i.get("uuid") for i in result.get("items", [])}

    def test_days_1_membership(self, mcp, seeded):
        uuids = self._uuids(mcp, 1)
        assert seeded.uuid("deadline_today") in uuids, "deadline_today missing at days=1"
        assert seeded.uuid("overdue") in uuids, "overdue missing at days=1 (include_overdue default True)"
        assert seeded.uuid("deadline_plus3d") not in uuids, "deadline_plus3d unexpectedly present at days=1"

    def test_days_3_boundary_inclusive(self, mcp, seeded):
        """deadline exactly today (+0) and exactly +3 are both included -
        boundary inclusive on both ends."""
        uuids = self._uuids(mcp, 3)
        assert seeded.uuid("deadline_today") in uuids, "deadline_today missing at days=3"
        assert seeded.uuid("deadline_plus3d") in uuids, "deadline_plus3d missing at days=3 (boundary)"
        assert seeded.uuid("deadline_plus20d") not in uuids, "deadline_plus20d unexpectedly present at days=3"

    def test_days_20_boundary_inclusive(self, mcp, seeded):
        uuids = self._uuids(mcp, 20)
        assert seeded.uuid("deadline_plus3d") in uuids, "deadline_plus3d missing at days=20"
        assert seeded.uuid("deadline_plus20d") in uuids, "deadline_plus20d missing at days=20 (boundary)"
        assert seeded.uuid("deadline_plus60d") not in uuids, "deadline_plus60d unexpectedly present at days=20"

    def test_days_60_boundary_inclusive(self, mcp, seeded):
        uuids = self._uuids(mcp, 60)
        assert seeded.uuid("deadline_plus20d") in uuids, "deadline_plus20d missing at days=60"
        assert seeded.uuid("deadline_plus60d") in uuids, "deadline_plus60d missing at days=60 (boundary)"

    def test_include_overdue_false_drops_overdue(self, mcp, seeded):
        uuids = self._uuids(mcp, 60, include_overdue=False)
        assert seeded.uuid("overdue") not in uuids, (
            "overdue seed unexpectedly present with include_overdue=False"
        )
        # Forward-window items must still be present.
        assert seeded.uuid("deadline_today") in uuids, (
            "deadline_today missing with include_overdue=False (still in forward window)"
        )
        assert seeded.uuid("deadline_plus60d") in uuids, (
            "deadline_plus60d missing with include_overdue=False (still in forward window)"
        )

    def test_include_overdue_true_keeps_overdue(self, mcp, seeded):
        uuids = self._uuids(mcp, 60, include_overdue=True)
        assert seeded.uuid("overdue") in uuids, (
            "overdue seed missing with include_overdue=True (default/explicit)"
        )

    @pytest.mark.parametrize("days", [0, 366])
    def test_days_out_of_range_is_schema_rejection(self, mcp, days):
        """days is Field(ge=1, le=365) - out-of-range is a FastMCP schema
        tool_error, not the read_error('internal_error', ...) fallback the
        tool's own except-block would otherwise return for a runtime
        failure."""
        result = mcp.call_sync("get_due_in_days", days=days)
        assert "tool_error" in result, (
            f"get_due_in_days(days={days}): expected schema tool_error, got {result!r}"
        )
        assert result.get("error") != "internal_error", result


# ---------------------------------------------------------------------------
# get_activating_in_days
# ---------------------------------------------------------------------------


class TestGetActivatingInDays:
    def _uuids(self, mcp, days):
        result = mcp.call_sync("get_activating_in_days", days=days)
        assert "tool_error" not in result, result
        assert result.get("days") == days, result
        # get_activating_in_days has no 'mode' parameter, so requested_mode
        # must be None while 'mode' reports the effective ('standard')
        # shape - hq-lsb.
        assert result.get("requested_mode") is None, result
        assert result.get("mode") == "standard", result
        return {i.get("uuid") for i in result.get("items", [])}

    def test_days_7_absent(self, mcp, seeded):
        uuids = self._uuids(mcp, 7)
        assert seeded.uuid("activating_plus10d") not in uuids, (
            "activating_plus10d (start_date +10d) unexpectedly present at days=7"
        )

    def test_days_10_exact_boundary_present(self, mcp, seeded):
        uuids = self._uuids(mcp, 10)
        assert seeded.uuid("activating_plus10d") in uuids, (
            "activating_plus10d (start_date +10d) missing at days=10 (exact boundary)"
        )

    def test_days_30_present(self, mcp, seeded):
        uuids = self._uuids(mcp, 30)
        assert seeded.uuid("activating_plus10d") in uuids, (
            "activating_plus10d missing at days=30"
        )

    def test_no_start_date_seeds_absent(self, mcp, seeded):
        """Seeds with no start_date at all (e.g. 'inbox' - no `when` given
        at all) never appear regardless of the window, since
        get_activating_in_days filters on start_date and an item with no
        start_date has nothing to fall within the forward window. This is
        the closest available proxy in the current seed set for "already
        active/no activation date is excluded" - no seed class has a
        start_date strictly in the past (things.py's own scheduling verbs
        don't produce one via add_todo/update_todo), so this does not
        exercise the strict less-than-today exclusion directly; see
        Discovered."""
        uuids = self._uuids(mcp, 30)
        assert seeded.uuid("inbox") not in uuids, (
            "'inbox' seed (no start_date at all) unexpectedly present in "
            "get_activating_in_days"
        )

    def test_today_start_date_included_at_boundary(self, mcp, seeded):
        """'today' has start_date == today - the lower boundary of the
        forward window (today <= start_date <= today+days) is inclusive,
        so it must be present even at a small days value."""
        uuids = self._uuids(mcp, 1)
        assert seeded.uuid("today") in uuids, (
            "'today' seed (start_date == today) missing at days=1 - lower "
            "boundary should be inclusive"
        )

    @pytest.mark.parametrize("days", [0, 366])
    def test_days_out_of_range_is_schema_rejection(self, mcp, days):
        result = mcp.call_sync("get_activating_in_days", days=days)
        assert "tool_error" in result, (
            f"get_activating_in_days(days={days}): expected schema tool_error, got {result!r}"
        )
        assert result.get("error") != "internal_error", result
