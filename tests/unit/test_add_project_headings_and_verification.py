"""
Unit tests for hq-f0w.41: add_project todo-count verification (AppleScript
path) and '##' heading support (URL-scheme 'json' action path).

Background: add_project's AppleScript path (_build_create_project_script)
has no heading concept - a '##Heading' line was previously created as a
literal to-do titled '##Heading'. Live verification for this bead (see
report) confirmed the documented `add-project` `to-dos` URL-scheme param
also does NOT turn '##' lines into headings; only `things:///json` (with
`items: [{"type": "heading", ...}, {"type": "to-do", ...}]`) creates real
headings. add_project now:
  - routes to _add_project_via_url_scheme (things:///json) whenever the
    todos payload contains at least one '##' line, creating real headings.
    After the id-lookup poll confirms the new project id, todos_created/
    headings_created are verified via things.py (things.todos(project=id),
    things.tasks(type='heading', project=id, status=None)) rather than
    just echoing the requested counts, with a warning if fewer than
    requested were actually created (review round 2) - things.py failures
    fall back to the requested count rather than failing the create.
  - otherwise uses the AppleScript path as before, verifying the number
    of to-dos actually created (via a "count of to dos of newProject"
    appended to the AppleScript's return value) against the number
    requested, reporting `todos_created` and a warning if fewer than
    requested were created.

These tests mock the AppleScript manager and the `things` proxy entirely -
no real AppleScript or Things 3 interaction occurs.
"""

import json

import pytest
from unittest.mock import AsyncMock, Mock, patch

from things_mcp.scheduling.todo_operations import TodoOperations


def make_applescript_manager(execute_applescript_return=None, execute_applescript_side_effect=None,
                              execute_url_scheme_return=None):
    manager = Mock()
    if execute_applescript_side_effect is not None:
        manager.execute_applescript = AsyncMock(side_effect=execute_applescript_side_effect)
    else:
        manager.execute_applescript = AsyncMock(return_value=execute_applescript_return)
    manager.execute_url_scheme = AsyncMock(
        return_value=execute_url_scheme_return or {"success": True, "url": "things:///json", "message": "ok"}
    )
    return manager


def ids_result(ids):
    return {"success": True, "output": "\n".join(ids)}


def patch_things_counts(todos=None, headings=None):
    """Patch things.todos/things.tasks (as used by
    _add_project_via_url_scheme's post-create verification) to return the
    given number of fake items. None means "not expected to be called for
    this count" but is still safely patched to an empty list so an
    unexpected call doesn't hit the real things.py proxy."""
    todo_rows = [{"uuid": f"todo-{i}"} for i in range(todos or 0)]
    heading_rows = [{"uuid": f"heading-{i}"} for i in range(headings or 0)]
    return patch.multiple(
        "things_mcp.scheduling.todo_operations.things",
        todos=Mock(return_value=todo_rows),
        tasks=Mock(return_value=heading_rows),
    )


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch):
    """Shrink the poll interval/deadline so URL-scheme lookup tests run fast."""
    monkeypatch.setattr(TodoOperations, "_URL_SCHEME_LOOKUP_POLL_INTERVAL_SECS", 0.01)
    monkeypatch.setattr(TodoOperations, "_URL_SCHEME_LOOKUP_DEADLINE_SECS", 0.05)


# ---------------------------------------------------------------------------
# AppleScript path: todo-count verification
# ---------------------------------------------------------------------------

class TestAppleScriptPathCountVerification:
    @pytest.mark.asyncio
    async def test_all_requested_todos_created_reports_count_no_warning(self):
        manager = make_applescript_manager(
            execute_applescript_return={"success": True, "output": "PROJECT-1\n3"}
        )
        ops = TodoOperations(manager, Mock())

        result = await ops.add_project("My Project", todos="Line A\nLine B\nLine C")

        assert result["success"] is True
        assert result["project_id"] == "PROJECT-1"
        assert result["todos_created"] == 3
        assert "warnings" not in result

    @pytest.mark.asyncio
    async def test_fewer_todos_created_than_requested_warns(self):
        # Only 1 of 2 requested to-dos actually landed - the historical
        # "dropped line" symptom from the bead description.
        manager = make_applescript_manager(
            execute_applescript_return={"success": True, "output": "PROJECT-2\n1"}
        )
        ops = TodoOperations(manager, Mock())

        result = await ops.add_project("My Project", todos="Line A\nLine B")

        assert result["success"] is True
        assert result["project_id"] == "PROJECT-2"
        assert result["todos_created"] == 1
        assert "warnings" in result
        assert "Requested 2" in result["warnings"][0]
        assert "1 were created" in result["warnings"][0]

    @pytest.mark.asyncio
    async def test_no_todos_requested_no_todos_created_key(self):
        manager = make_applescript_manager(
            execute_applescript_return={"success": True, "output": "PROJECT-3\n0"}
        )
        ops = TodoOperations(manager, Mock())

        result = await ops.add_project("My Project")

        assert result["success"] is True
        assert result["project_id"] == "PROJECT-3"
        assert "todos_created" not in result

    @pytest.mark.asyncio
    async def test_malformed_count_line_falls_back_to_requested_len(self):
        """If the count line is missing/unparseable, fall back to the
        requested count rather than crashing or silently omitting it."""
        manager = make_applescript_manager(
            execute_applescript_return={"success": True, "output": "PROJECT-4\nnot-a-number"}
        )
        ops = TodoOperations(manager, Mock())

        result = await ops.add_project("My Project", todos="Line A\nLine B")

        assert result["success"] is True
        assert result["todos_created"] == 2
        assert "warnings" not in result

    @pytest.mark.asyncio
    async def test_scheduling_still_applied_alongside_count_verification(self):
        manager = make_applescript_manager(
            execute_applescript_return={"success": True, "output": "PROJECT-5\n1"}
        )
        scheduler = Mock()
        scheduler.schedule_todo_reliable = AsyncMock(return_value={"success": True})
        ops = TodoOperations(manager, scheduler)

        result = await ops.add_project("My Project", todos="Line A", when="today")

        assert result["success"] is True
        assert result["todos_created"] == 1
        assert result["message"] == "Project created and scheduled successfully"
        assert result["scheduling"] == {"success": True}


# ---------------------------------------------------------------------------
# '##' heading lines route to the URL-scheme ('json' action) path
# ---------------------------------------------------------------------------

class TestHeadingLinesRouteToUrlScheme:
    @pytest.mark.asyncio
    async def test_heading_line_routes_to_json_action_not_applescript_create(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),              # pre-create snapshot
                ids_result(["NEW-PROJECT"]),  # first poll: found
            ]
        )
        ops = TodoOperations(manager, Mock())

        with patch_things_counts(todos=1, headings=1):
            result = await ops.add_project(
                "My Project", todos="##Heading 1\nTodo under heading"
            )

        assert result["success"] is True
        assert result["project_id"] == "NEW-PROJECT"
        assert result["headings_created"] == 1
        assert result["todos_created"] == 1
        assert "warnings" not in result

        # The 'json' URL-scheme action was used, not a 'make new project'
        # AppleScript create.
        manager.execute_url_scheme.assert_awaited_once()
        action, params = manager.execute_url_scheme.call_args.args
        assert action == "json"
        payload = json.loads(params["data"])
        assert payload[0]["type"] == "project"
        items = payload[0]["attributes"]["items"]
        assert items[0] == {"type": "heading", "attributes": {"title": "Heading 1"}}
        assert items[1] == {"type": "to-do", "attributes": {"title": "Todo under heading"}}

        # No 'make new project'/'make new to do' AppleScript create call -
        # only the id-lookup polling calls hit execute_applescript.
        for call in manager.execute_applescript.await_args_list:
            script = call.args[0]
            assert "make new project" not in script
            assert "make new to do" not in script

    @pytest.mark.asyncio
    async def test_no_heading_line_uses_applescript_path_not_url_scheme(self):
        manager = make_applescript_manager(
            execute_applescript_return={"success": True, "output": "PROJECT-X\n1"}
        )
        ops = TodoOperations(manager, Mock())

        result = await ops.add_project("My Project", todos="Just a todo, no heading")

        assert result["success"] is True
        assert result["project_id"] == "PROJECT-X"
        manager.execute_url_scheme.assert_not_awaited()
        manager.execute_applescript.assert_awaited_once()
        assert "make new project" in manager.execute_applescript.call_args.args[0]

    @pytest.mark.asyncio
    async def test_multiple_headings_and_interleaved_todos_all_forwarded(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),
                ids_result(["NEW-PROJECT"]),
            ]
        )
        ops = TodoOperations(manager, Mock())

        todos = "Preamble todo\n##Phase 1\nTask 1a\nTask 1b\n##Phase 2\nTask 2"
        with patch_things_counts(todos=4, headings=2):
            result = await ops.add_project("My Project", todos=todos)

        assert result["success"] is True
        assert result["headings_created"] == 2
        assert result["todos_created"] == 4

        action, params = manager.execute_url_scheme.call_args.args
        payload = json.loads(params["data"])
        items = payload[0]["attributes"]["items"]
        assert [i["type"] for i in items] == [
            "to-do", "heading", "to-do", "to-do", "heading", "to-do"
        ]
        assert items[1]["attributes"]["title"] == "Phase 1"
        assert items[4]["attributes"]["title"] == "Phase 2"

    @pytest.mark.asyncio
    async def test_empty_heading_title_rejected_with_structured_error(self):
        manager = make_applescript_manager()
        ops = TodoOperations(manager, Mock())

        result = await ops.add_project("My Project", todos="##\nSome todo")

        assert result["success"] is False
        assert "error" in result
        assert "heading" in result["error"].lower()
        manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notes_tags_deadline_area_forwarded_in_json_payload(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),
                ids_result(["NEW-PROJECT"]),
            ]
        )
        ops = TodoOperations(manager, Mock())

        with patch_things_counts(todos=1, headings=1):
            result = await ops.add_project(
                "My Project",
                todos="##Heading 1\nTodo",
                notes="Some notes",
                tags=["urgent"],
                deadline="2026-12-31",
                area_id="AREA-1",
            )

        assert result["success"] is True
        action, params = manager.execute_url_scheme.call_args.args
        attrs = json.loads(params["data"])[0]["attributes"]
        assert attrs["notes"] == "Some notes"
        assert attrs["tags"] == ["urgent"]
        assert attrs["deadline"] == "2026-12-31"
        assert attrs["area-id"] == "AREA-1"

    @pytest.mark.asyncio
    async def test_area_title_used_when_no_area_id(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),
                ids_result(["NEW-PROJECT"]),
            ]
        )
        ops = TodoOperations(manager, Mock())

        with patch_things_counts(todos=1, headings=1):
            await ops.add_project(
                "My Project", todos="##Heading 1\nTodo", area_title="Personal"
            )

        action, params = manager.execute_url_scheme.call_args.args
        attrs = json.loads(params["data"])[0]["attributes"]
        assert attrs["area"] == "Personal"
        assert "area-id" not in attrs

    @pytest.mark.asyncio
    async def test_json_action_failure_returns_structured_error(self):
        manager = make_applescript_manager(
            execute_applescript_return=ids_result([]),  # pre-create snapshot lookup
            execute_url_scheme_return={"success": False, "error": "boom"}
        )
        ops = TodoOperations(manager, Mock())

        result = await ops.add_project("My Project", todos="##Heading 1\nTodo")

        assert result["success"] is False
        assert result["error"] == "boom"

    @pytest.mark.asyncio
    async def test_lookup_timeout_returns_structured_error_not_success(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),  # snapshot
                ids_result([]),  # poll: never appears within the deadline
                ids_result([]),
                ids_result([]),
                ids_result([]),
                ids_result([]),
            ]
        )
        ops = TodoOperations(manager, Mock())

        result = await ops.add_project("My Project", todos="##Heading 1\nTodo")

        assert result["success"] is False
        assert "could not be confirmed" in result["error"]

    @pytest.mark.asyncio
    async def test_when_scheduled_after_url_scheme_create(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),
                ids_result(["NEW-PROJECT"]),
            ]
        )
        scheduler = Mock()
        scheduler.schedule_todo_reliable = AsyncMock(return_value={"success": True})
        ops = TodoOperations(manager, scheduler)

        with patch_things_counts(todos=1, headings=1):
            result = await ops.add_project(
                "My Project", todos="##Heading 1\nTodo", when="today"
            )

        assert result["success"] is True
        assert result["message"] == "Project created and scheduled successfully"
        scheduler.schedule_todo_reliable.assert_awaited_once_with("NEW-PROJECT", "today")


class TestUrlSchemePathCountVerification:
    """Review round 2 (hq-f0w.41): headings_created/todos_created on the
    URL-scheme path are verified via things.py after the id-lookup poll,
    not just echoed from the requested counts."""

    @pytest.mark.asyncio
    async def test_fewer_todos_and_headings_created_than_requested_warns(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),
                ids_result(["NEW-PROJECT"]),
            ]
        )
        ops = TodoOperations(manager, Mock())

        todos = "##Phase 1\nTask 1a\nTask 1b\n##Phase 2\nTask 2"
        # Requested: 2 headings, 3 todos. things.py reports only 1 heading
        # and 2 todos actually landed.
        with patch_things_counts(todos=2, headings=1):
            result = await ops.add_project("My Project", todos=todos)

        assert result["success"] is True
        assert result["todos_created"] == 2
        assert result["headings_created"] == 1
        assert "warnings" in result
        joined = " ".join(result["warnings"])
        assert "Requested 3 to-dos but only 2" in joined
        assert "Requested 2 headings but only 1" in joined

    @pytest.mark.asyncio
    async def test_things_lookup_failure_falls_back_to_requested_counts(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),
                ids_result(["NEW-PROJECT"]),
            ]
        )
        ops = TodoOperations(manager, Mock())

        with patch(
            "things_mcp.scheduling.todo_operations.things.todos",
            side_effect=RuntimeError("things.py unavailable"),
        ), patch(
            "things_mcp.scheduling.todo_operations.things.tasks",
            side_effect=RuntimeError("things.py unavailable"),
        ):
            result = await ops.add_project(
                "My Project", todos="##Heading 1\nTodo A\nTodo B"
            )

        assert result["success"] is True
        # Falls back to the requested counts (2 todos, 1 heading) rather
        # than raising or omitting the keys.
        assert result["todos_created"] == 2
        assert result["headings_created"] == 1
        assert "warnings" not in result

    @pytest.mark.asyncio
    async def test_verification_queries_use_confirmed_project_id(self):
        manager = make_applescript_manager(
            execute_applescript_side_effect=[
                ids_result([]),
                ids_result(["NEW-PROJECT"]),
            ]
        )
        ops = TodoOperations(manager, Mock())

        with patch(
            "things_mcp.scheduling.todo_operations.things.todos",
            return_value=[{"uuid": "t1"}],
        ) as mock_todos, patch(
            "things_mcp.scheduling.todo_operations.things.tasks",
            return_value=[{"uuid": "h1"}],
        ) as mock_tasks:
            result = await ops.add_project(
                "My Project", todos="##Heading 1\nTodo"
            )

        assert result["success"] is True
        mock_todos.assert_called_once_with(project="NEW-PROJECT")
        mock_tasks.assert_called_once_with(type='heading', project="NEW-PROJECT", status=None)
