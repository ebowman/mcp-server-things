"""hq-4w4: trashed targets are rejected before any Things URL-scheme update."""

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from things_mcp.config import ThingsMCPConfig
from things_mcp.tools import ThingsTools
from things_mcp.tools_helpers.url_target_check import check_url_scheme_target

TODO = {"uuid": "t1", "type": "to-do"}
TRASHED = {"uuid": "t1", "type": "to-do", "trashed": True}


class FakeThings:
    def __init__(self, records=None, raises=False):
        self.records = records or {}
        self.raises = raises

    def get(self, item_id, *a, **k):
        if self.raises:
            raise RuntimeError("db unreadable")
        return self.records.get(item_id)


class TestHelper:
    def test_ok(self):
        assert check_url_scheme_target("t1", "to-do", FakeThings({"t1": TODO})) is None

    def test_not_found(self):
        r = check_url_scheme_target("t1", "to-do", FakeThings())
        assert r["success"] is False and r["error"] == "NOT_FOUND"

    def test_empty_id(self):
        for bad in ("", "  ", None):
            r = check_url_scheme_target(bad, "to-do", FakeThings())
            assert r["error"] == "VALIDATION_ERROR" and r["field"] == "id"

    def test_wrong_type(self):
        r = check_url_scheme_target("p1", "to-do", FakeThings({"p1": {"type": "project"}}))
        assert r["error"] == "VALIDATION_ERROR" and "update_project" in r["message"]
        r = check_url_scheme_target("t1", "project", FakeThings({"t1": TODO}))
        assert r["error"] == "VALIDATION_ERROR"

    def test_trashed(self):
        r = check_url_scheme_target("t1", "to-do", FakeThings({"t1": TRASHED}))
        assert r["error"] == "NOT_FOUND" and r["trashed"] is True
        assert "in the Trash" in r["message"] and "trashedViaParent" not in r

    def test_trashed_project(self):
        r = check_url_scheme_target(
            "p1", "project", FakeThings({"p1": {"type": "project", "trashed": True}}))
        assert r["error"] == "NOT_FOUND" and r["trashed"] is True

    def test_trashed_via_parent_project(self):
        things = FakeThings({
            "t1": {"type": "to-do", "project": "p1"},
            "p1": {"type": "project", "trashed": True},
        })
        r = check_url_scheme_target("t1", "to-do", things)
        assert r["error"] == "NOT_FOUND" and r["trashed"] and r["trashedViaParent"]

    def test_trashed_via_heading_parent(self):
        things = FakeThings({
            "t1": {"type": "to-do", "heading": "h1"},
            "h1": {"type": "heading", "project": "p1"},
            "p1": {"type": "project", "trashed": True},
        })
        r = check_url_scheme_target("t1", "to-do", things)
        assert r["trashedViaParent"] is True

    def test_live_parent_ok(self):
        things = FakeThings({
            "t1": {"type": "to-do", "project": "p1"},
            "p1": {"type": "project"},
        })
        assert check_url_scheme_target("t1", "to-do", things) is None

    def test_lookup_raises_proceeds(self):
        assert check_url_scheme_target("t1", "to-do", FakeThings(raises=True)) is None


def _tools():
    mgr = MagicMock()
    mgr.auth_token = "tok"
    mgr.execute_applescript = AsyncMock(return_value={"success": True, "output": "updated"})
    mgr.execute_url_scheme = AsyncMock(return_value={"success": True})
    return ThingsTools(mgr, config=ThingsMCPConfig()), mgr


def _patch_things(records):
    fake = FakeThings(records)
    stack = ExitStack()
    for mod in ("scheduling.todo_operations", "tools_helpers.bulk_operations"):
        stack.enter_context(patch(f"things_mcp.{mod}.things.get", side_effect=fake.get))
    return stack


def _assert_nothing_written(mgr):
    mgr.execute_url_scheme.assert_not_called()
    mgr.execute_applescript.assert_not_called()


class TestUpdateTodoTrashed:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kwargs", [
        {"when": "evening"},
        {"when": "2030-01-01@09:30"},
        {"heading": "Research"},
        {"title": "New", "when": "evening"},  # mixed: nothing applied
    ])
    async def test_url_paths_reject_trashed(self, kwargs):
        tools, mgr = _tools()
        with _patch_things({"t1": TRASHED}):
            r = await tools.update_todo("t1", **kwargs)
        assert r["success"] is False and r["error"] == "NOT_FOUND" and r["trashed"] is True
        _assert_nothing_written(mgr)

    @pytest.mark.asyncio
    async def test_trashed_via_parent(self):
        tools, mgr = _tools()
        with _patch_things({"t1": {"type": "to-do", "project": "p1"},
                            "p1": {"type": "project", "trashed": True}}):
            r = await tools.update_todo("t1", when="evening")
        assert r["error"] == "NOT_FOUND" and r["trashedViaParent"] is True
        _assert_nothing_written(mgr)

    @pytest.mark.asyncio
    async def test_pure_applescript_on_trashed_unchanged(self):
        tools, mgr = _tools()
        with _patch_things({"t1": TRASHED}):
            await tools.update_todo("t1", title="Renamed")
        mgr.execute_applescript.assert_called()
        mgr.execute_url_scheme.assert_not_called()


class TestChecklistTrashed:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("method", [
        "add_checklist_items", "prepend_checklist_items", "replace_checklist_items"])
    async def test_reject_trashed(self, method):
        tools, mgr = _tools()
        with _patch_things({"t1": TRASHED}):
            r = await getattr(tools, method)(todo_id="t1", items=["a"])
        assert r["error"] == "NOT_FOUND" and r["trashed"] is True
        _assert_nothing_written(mgr)

    @pytest.mark.asyncio
    async def test_ok_proceeds(self):
        tools, mgr = _tools()
        with _patch_things({"t1": TODO}):
            r = await tools.add_checklist_items(todo_id="t1", items=["a"])
        assert r["success"] is True
        mgr.execute_url_scheme.assert_called_once()


class TestUpdateProjectTrashed:
    @pytest.mark.asyncio
    async def test_time_when_rejects_trashed(self):
        tools, mgr = _tools()
        with _patch_things({"p1": {"uuid": "p1", "type": "project", "trashed": True}}):
            r = await tools.update_project("p1", title="X", when="2030-01-01@09:30")
        assert r["error"] == "NOT_FOUND" and r["trashed"] is True
        _assert_nothing_written(mgr)


class TestBulkTrashed:
    @pytest.mark.asyncio
    async def test_one_trashed_one_ok_evening(self):
        tools, mgr = _tools()
        mgr.execute_applescript = AsyncMock(
            return_value={"success": True, "output": "successCount:1, errors:{}"})
        with _patch_things({"ok": {"type": "to-do"}, "gone": TRASHED}):
            r = await tools.bulk_update_todos(todo_ids=["ok", "gone"], when="evening")
        assert r["not_found"] == ["gone"]
        assert r["updated_count"] == 1 and r["failed_count"] == 1
        urls = [c.args for c in mgr.execute_url_scheme.call_args_list]
        assert urls == [("update", {"id": "ok", "when": "evening"})]

    @pytest.mark.asyncio
    async def test_all_trashed_writes_nothing(self):
        tools, mgr = _tools()
        with _patch_things({"gone": TRASHED}):
            r = await tools.bulk_update_todos(todo_ids=["gone"], when="evening")
        assert r["error"] == "NOT_FOUND" and r["not_found"] == ["gone"]
        _assert_nothing_written(mgr)

    @pytest.mark.asyncio
    async def test_pure_applescript_batch_unchanged(self):
        tools, mgr = _tools()
        mgr.execute_applescript = AsyncMock(
            return_value={"success": True, "output": "successCount:1, errors:{}"})
        with _patch_things({"gone": TRASHED}):
            r = await tools.bulk_update_todos(todo_ids=["gone"], title="X")
        assert r["success"] is True and r.get("not_found") in (None, [])
        mgr.execute_applescript.assert_called()


TRASHED_PROJECT = {"uuid": "p1", "type": "project", "trashed": True}


class TestTrashedDestinations:
    @pytest.mark.asyncio
    async def test_add_todo_trashed_list_id(self):
        tools, mgr = _tools()
        with _patch_things({"p1": TRASHED_PROJECT}):
            r = await tools.add_todo(title="X", list_id="p1")
        assert r["error"] == "NOT_FOUND" and r["trashed"] is True
        _assert_nothing_written(mgr)

    @pytest.mark.asyncio
    async def test_update_todo_trashed_list_id(self):
        tools, mgr = _tools()
        with _patch_things({"t1": TODO, "p1": TRASHED_PROJECT}):
            r = await tools.update_todo("t1", list_id="p1", title="X")
        assert r["error"] == "NOT_FOUND" and r["trashed"] is True
        _assert_nothing_written(mgr)

    @pytest.mark.asyncio
    async def test_update_todo_heading_trashed_list_id(self):
        tools, mgr = _tools()
        with _patch_things({"t1": TODO, "p1": TRASHED_PROJECT}):
            r = await tools.update_todo("t1", heading="H", list_id="p1")
        assert r["error"] == "NOT_FOUND" and r["trashed"] is True
        _assert_nothing_written(mgr)


class TestHelperAndChecklistExtras:
    def test_parent_lookup_raising_proceeds(self):
        class Flaky(FakeThings):
            def get(self, item_id, *a, **k):
                if item_id == "p1":
                    raise RuntimeError("boom")
                return super().get(item_id)
        things = Flaky({"t1": {"type": "to-do", "project": "p1"}})
        assert check_url_scheme_target("t1", "to-do", things) is None

    @pytest.mark.asyncio
    async def test_checklist_with_project_id(self):
        tools, mgr = _tools()
        with _patch_things({"p1": {"uuid": "p1", "type": "project"}}):
            r = await tools.add_checklist_items(todo_id="p1", items=["a"])
        assert r["error"] == "VALIDATION_ERROR"
        mgr.execute_url_scheme.assert_not_called()
