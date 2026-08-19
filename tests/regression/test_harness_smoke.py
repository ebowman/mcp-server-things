"""Smoke test for the tests/regression harness itself (hq-gbl.2, step 7).

Verifies: the sandbox fixture actually produced a usable area/project/
heading/tag, that calls go through the real MCP tool boundary and return
sane structured_content, and that a to-do created (and tracked) mid-test is
proven trashed by the sandbox's own teardown.
"""
import asyncio

import pytest

from regression.helpers import sandbox_title

# Applied per-item in conftest.py's pytest_collection_modifyitems (a bare
# module-level `pytestmark` in a conftest.py has no collection effect on
# sibling test modules - verified: `-m "not live" --collect-only` still
# collected all items with only the conftest-level pytestmark). Setting it
# here, directly in the test module, DOES work and is the belt-and-braces
# half of that fix.
pytestmark = pytest.mark.live


class TestSandboxFixture:
    def test_sandbox_area_and_projects_exist(self, sandbox):
        assert sandbox.area_id
        assert sandbox.area_title
        assert sandbox.project_id
        assert sandbox.project_title
        assert sandbox.project_b_id
        assert sandbox.done_project_id

    def test_sandbox_heading_present(self, sandbox):
        # heading_title is None only if the ##Heading json-action path
        # regressed and no real heading was created - fail loudly rather
        # than silently skipping, since this harness's own setup should be
        # reliable on a healthy Things 3 install.
        assert sandbox.heading_title == "Reg Heading", (
            "Sandbox project's seeded heading was not confirmed via things.py "
            "- see add_project's ##Heading json-action path"
        )

    def test_sandbox_tag_resolved(self, sandbox):
        assert sandbox.tag_name
        assert sandbox.tag_id, (
            f"Sandbox tag {sandbox.tag_name!r} (created via "
            f"{sandbox.tag_created_via}) did not resolve to a uuid via things.tags()"
        )


class TestMCPBoundary:
    @pytest.mark.asyncio
    async def test_get_todo_by_id_resolves_sandbox_project(self, mcp, sandbox):
        result = await mcp.call("get_todo_by_id", todo_id=sandbox.project_id)
        assert "item" in result, f"expected item envelope, got {result!r}"
        item = result["item"]
        assert item["type"] == "project"
        assert item["uuid"] == sandbox.project_id
        assert item["title"] == sandbox.project_title

    @pytest.mark.asyncio
    async def test_write_then_read_back_roundtrip(self, mcp, sandbox):
        """Add a to-do to the sandbox project, then confirm via
        get_todo_by_id (MCP boundary) that the write landed - exercising
        the same URL-scheme/things.py lag this harness's read_back() is
        built for. The created to-do is tracked so the sandbox's teardown
        (see TestTeardownProvenTrashed below) sweeps and trashes it too."""
        title = sandbox_title("roundtrip todo")
        add_result = await mcp.call(
            "add_todo",
            title=title,
            list_id=sandbox.project_id,
        )
        assert add_result.get("success") is True, f"add_todo failed: {add_result}"
        todo_id = add_result.get("todo_id")
        assert todo_id, f"add_todo response missing todo_id: {add_result}"
        sandbox.track(todo_id)

        # Poll get_todo_by_id through the MCP boundary rather than things.py
        # directly, to exercise the real client-visible read path.
        item = None
        for _ in range(40):  # ~20s at 0.5s interval
            read_result = await mcp.call("get_todo_by_id", todo_id=todo_id)
            if "item" in read_result and read_result["item"].get("title") == title:
                item = read_result["item"]
                break
            await asyncio.sleep(0.5)

        assert item is not None, f"todo {todo_id} ({title!r}) never read back via get_todo_by_id"
        assert item["type"] == "to-do"
        assert item["title"] == title


class TestTeardownProvenTrashed:
    """A deliberately-created extra to-do, tracked here and proven trashed
    by the sandbox's own session-scoped teardown.

    The `sandbox` fixture's finalizer (registered in conftest.py) sweeps
    every child of every sandbox project PLUS every explicitly-tracked id,
    trashes them all, and then raises AssertionError listing any leftover
    (still-active, non-trashed) id - so if this to-do were NOT actually
    trashed by teardown, the whole session's `sandbox` fixture teardown
    would fail and every test collected in this session would be reported
    as an error. We CAN assert "trashed" directly from inside a normal test
    here only for the pre-teardown state (confirmed below); the actual
    trashing only happens once the session's teardown finalizers run
    (after all tests complete), so this test documents and relies on that
    existing session-teardown assertion as the proof of the trashing itself
    - its own job is to guarantee the id actually reaches
    `sandbox.tracked_todo_ids` before teardown runs.
    """

    def test_extra_todo_created_and_tracked(self, mcp, sandbox):
        import things

        title = sandbox_title("extra teardown-proof todo")
        result = mcp.call_sync("add_todo", title=title, list_id=sandbox.project_id)
        assert result.get("success"), f"failed to create extra teardown-proof todo: {result}"
        todo_id = result.get("todo_id")
        assert todo_id
        sandbox.track(todo_id)

        # Confirm it's live (not trashed) right now, before teardown runs.
        record = things.get(todo_id, trashed=None)
        assert record is not None
        assert not record.get("trashed")
        assert todo_id in sandbox.tracked_todo_ids
