"""Unit tests for hq-nxu.13: update_todo(list_id=...) / update_todo(list_title=...)
without heading moves a to-do to a project or area via AppleScript, using
`project id "..."` / `area id "..."` (consistent with add_todo), resolved
via the same _resolve_list_id/_resolve_list_title helpers as add_todo.

Covers:
- list_id resolving to a project emits `set project of targetTodo to project id "..."`.
- list_id resolving to an area emits `set area of targetTodo to area id "..."`.
- list_title resolves to a project/area the same way and is used when list_id
  is absent.
- list_id takes precedence over list_title when both are given.
- Unknown list_id / unknown or ambiguous list_title returns a structured
  error before any AppleScript write.
- list_id/list_title combined with other AppleScript-only fields (title) are
  applied in the same script/write.
- list_id/list_title with heading unchanged: list_id is consumed by the
  URL-scheme heading path instead, and no separate AppleScript move happens.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from things_mcp.scheduling.todo_operations import TodoOperations
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    manager = MagicMock(spec=AppleScriptManager)
    manager.auth_token = "test-token-xyz"
    manager.execute_applescript = AsyncMock(return_value={"success": True, "output": "updated"})
    manager.execute_url_scheme = AsyncMock(return_value={
        "success": True,
        "url": "things:///update?id=abc123",
        "message": "Successfully executed update action",
    })
    return manager


@pytest.fixture
def ops(mock_applescript_manager):
    return TodoOperations(mock_applescript_manager, Mock())


class TestUpdateTodoMoveByListId:
    @pytest.mark.asyncio
    async def test_list_id_project_emits_project_id_script(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project"}):
            result = await ops.update_todo("abc123", list_id="PROJECT1")

        assert result["success"] is True
        mock_applescript_manager.execute_applescript.assert_awaited_once()
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'set project of targetTodo to project id "PROJECT1"' in script
        # No URL scheme call - this is a plain AppleScript move, no heading.
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_id_area_emits_area_id_script(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "area"}):
            result = await ops.update_todo("abc123", list_id="AREA1")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'set area of targetTodo to area id "AREA1"' in script
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_list_id_returns_structured_error_no_write(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get", return_value=None):
            result = await ops.update_todo("abc123", list_id="BOGUS")

        assert result["success"] is False
        assert "does not match any known project or area" in result["error"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_id_wrong_type_returns_structured_error(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "to-do"}):
            result = await ops.update_todo("abc123", list_id="SOME_TODO")

        assert result["success"] is False
        assert "not a project or area" in result["error"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_id_combined_with_title_applied_in_same_script(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project"}):
            result = await ops.update_todo("abc123", list_id="PROJECT1", title="New Title")

        assert result["success"] is True
        mock_applescript_manager.execute_applescript.assert_awaited_once()
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'set project of targetTodo to project id "PROJECT1"' in script
        assert "New Title" in script


class TestUpdateTodoMoveByListTitle:
    @pytest.mark.asyncio
    async def test_list_title_resolves_to_project(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects",
                   return_value=[{"uuid": "P1", "title": "Work"}]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await ops.update_todo("abc123", list_title="Work")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'set project of targetTodo to project id "P1"' in script

    @pytest.mark.asyncio
    async def test_list_title_resolves_to_area(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.areas",
                   return_value=[{"uuid": "A1", "title": "Personal"}]):
            result = await ops.update_todo("abc123", list_title="Personal")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'set area of targetTodo to area id "A1"' in script

    @pytest.mark.asyncio
    async def test_unknown_list_title_returns_structured_error(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await ops.update_todo("abc123", list_title="Nonexistent")

        assert result["success"] is False
        assert "does not match any project or area" in result["error"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ambiguous_list_title_returns_structured_error(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects",
                   return_value=[{"uuid": "P1", "title": "Dup"}]), \
             patch("things_mcp.scheduling.todo_operations.things.areas",
                   return_value=[{"uuid": "A1", "title": "Dup"}]):
            result = await ops.update_todo("abc123", list_title="Dup")

        assert result["success"] is False
        assert "ambiguous" in result["error"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_id_takes_precedence_over_list_title(self, ops, mock_applescript_manager):
        """When both list_id and list_title are given, list_id wins and
        list_title's own resolution (projects()/areas()) is never consulted."""
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project"}) as mock_get, \
             patch("things_mcp.scheduling.todo_operations.things.projects") as mock_projects, \
             patch("things_mcp.scheduling.todo_operations.things.areas") as mock_areas:
            result = await ops.update_todo("abc123", list_id="PROJECT1", list_title="Ignored Title")

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'set project of targetTodo to project id "PROJECT1"' in script
        mock_projects.assert_not_called()
        mock_areas.assert_not_called()


class TestUpdateTodoMoveWithHeadingUnaffected:
    """When heading is also given, list_id is consumed by the existing
    URL-scheme heading path instead of triggering a separate AppleScript
    project/area resolution - list_title must NOT be consulted at all in
    that case (heading has no list_title support, only list_id)."""

    @pytest.mark.asyncio
    async def test_heading_with_list_id_does_not_trigger_applescript_move(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project"}), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   return_value=[{"title": "Phase 1"}]):
            result = await ops.update_todo("abc123", heading="Phase 1", list_id="PROJECT99")

        assert result["success"] is True
        # No AppleScript write at all - heading is the only "field" and
        # list_id is consumed entirely by the URL-scheme call.
        mock_applescript_manager.execute_applescript.assert_not_awaited()
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["list-id"] == "PROJECT99"

    @pytest.mark.asyncio
    async def test_heading_with_list_title_resolves_and_included_in_url(self, ops, mock_applescript_manager):
        """list_title (when list_id is not also given) is resolved via
        _resolve_list_title the same way as the non-heading move path, and
        the resolved id is sent as 'list-id' on the URL-scheme call
        alongside 'heading' - it must NOT be silently dropped."""
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "to-do", "project": "PROJECT1"}), \
             patch("things_mcp.scheduling.todo_operations.things.tasks",
                   return_value=[{"title": "Research"}]), \
             patch("things_mcp.scheduling.todo_operations.things.projects",
                   return_value=[{"uuid": "P1", "title": "Work"}]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await ops.update_todo("abc123", heading="Research", list_title="Work")

        assert result["success"] is True
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["list-id"] == "P1"
        assert params["heading"] == "Research"

    @pytest.mark.asyncio
    async def test_heading_with_unknown_list_title_returns_structured_error(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await ops.update_todo("abc123", heading="Research", list_title="Nonexistent")

        assert result["success"] is False
        assert "does not match any project or area" in result["error"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heading_with_unknown_list_id_returns_structured_error(self, ops, mock_applescript_manager):
        """Gap 3 fix: an unknown list_id on the heading path is now
        pre-checked via _resolve_list_id (same as the non-heading move
        path) instead of being silently sent to Things as-is."""
        with patch("things_mcp.scheduling.todo_operations.things.get", return_value=None):
            result = await ops.update_todo("abc123", heading="Research", list_id="BOGUS")

        assert result["success"] is False
        assert "does not match any known project or area" in result["error"]
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()
        mock_applescript_manager.execute_applescript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heading_with_unknown_list_id_and_title_no_partial_write(self, ops, mock_applescript_manager):
        """Regression test for the review-2 gap: when heading + an unknown
        list_id are combined with another AppleScript-only field (title),
        the structured error must be returned BEFORE any write - the title
        must NOT be applied via AppleScript first. Previously the list_id
        pre-check for the heading path lived inside the `if not
        skip_applescript:` URL block, which runs AFTER the AppleScript
        write, so the title got applied and then the error was returned."""
        with patch("things_mcp.scheduling.todo_operations.things.get", return_value=None):
            result = await ops.update_todo(
                "abc123", heading="Research", list_id="BOGUS", title="New"
            )

        assert result["success"] is False
        assert "does not match any known project or area" in result["error"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heading_with_unknown_list_title_and_title_no_partial_write(self, ops, mock_applescript_manager):
        """Same regression as above, via list_title instead of list_id:
        heading + an unknown list_title + title must return the structured
        error before any AppleScript write or URL-scheme call."""
        with patch("things_mcp.scheduling.todo_operations.things.projects", return_value=[]), \
             patch("things_mcp.scheduling.todo_operations.things.areas", return_value=[]):
            result = await ops.update_todo(
                "abc123", heading="Research", list_title="Nonexistent", title="New"
            )

        assert result["success"] is False
        assert "does not match any project or area" in result["error"]
        mock_applescript_manager.execute_applescript.assert_not_awaited()
        mock_applescript_manager.execute_url_scheme.assert_not_awaited()


class TestUpdateTodoEveningWithListIdNoDoubleMove:
    """Gap 1 fix: when='evening' + list_id with NO heading must move via
    AppleScript exactly once - not again via the URL-scheme 'list-id'
    param, which previously double-applied the same move."""

    @pytest.mark.asyncio
    async def test_evening_with_list_id_moves_via_applescript_only(self, ops, mock_applescript_manager):
        with patch("things_mcp.scheduling.todo_operations.things.get",
                   return_value={"type": "project"}):
            result = await ops.update_todo("abc123", when="evening", list_id="PROJECT1")

        assert result["success"] is True

        # The AppleScript move happened (project id set).
        mock_applescript_manager.execute_applescript.assert_awaited_once()
        script = mock_applescript_manager.execute_applescript.await_args.args[0]
        assert 'set project of targetTodo to project id "PROJECT1"' in script

        # The URL-scheme call (for when=evening) happened, but must NOT
        # carry 'list-id' - that would double-apply the same move.
        mock_applescript_manager.execute_url_scheme.assert_awaited_once()
        _, params = mock_applescript_manager.execute_url_scheme.await_args.args
        assert params["when"] == "evening"
        assert "list-id" not in params
