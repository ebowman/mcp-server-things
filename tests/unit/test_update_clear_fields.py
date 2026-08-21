"""
Unit tests for the update_* clear-field contract (hq-nxu.9).

Contract:
- A field omitted (or explicitly None) from update_todo/update_project/
  update_area/bulk_update_todos leaves the existing value unchanged.
- notes='' and deadline='' clear those fields (todo + project).
- tags='' clears all tags (todo + project + area).
- title='' is rejected with a structured validation error - titles cannot
  be cleared.
- when='' is rejected with a structured validation error directing callers
  to use when='anytime'/when='someday' to unschedule instead.

These tests mock AppleScript execution entirely (no real Things 3 calls)
and assert on the exact AppleScript statements emitted, mirroring the
existing test_update_project_status.py pattern.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.scheduling.todo_operations import TodoOperations
from things_mcp.tools_helpers.bulk_operations import BulkOperations


@pytest.fixture(autouse=True)
def _things_get_resolves_as_todo():
    """hq-wbm: update_todo/bulk_update_todos now pre-check the primary
    todo_id via things.get() before any write. This file's todo_id values
    ("TODO-1" etc.) are fake ids never present in the real Things database,
    so without this patch every call here would (correctly, per the new
    behavior) return NOT_FOUND instead of exercising the clear-field
    AppleScript emission this file is actually testing. Patch all three
    module-local things.get() proxies (todo_operations, bulk_operations,
    write_operations) to always resolve as a to-do."""
    with patch(
        "things_mcp.scheduling.todo_operations.things.get",
        return_value={"type": "to-do"},
    ), patch(
        "things_mcp.tools_helpers.bulk_operations.things.get",
        return_value={"type": "to-do"},
    ), patch(
        "things_mcp.tools_helpers.write_operations.things.get",
        return_value={"type": "to-do"},
    ):
        yield


@pytest.fixture
def mock_applescript_manager():
    """Mock AppleScript manager that captures the script and reports success."""
    manager = Mock(spec=AppleScriptManager)
    manager.execute_applescript = AsyncMock(return_value={
        "success": True,
        "output": "updated",
    })
    return manager


@pytest.fixture
def things_tools(mock_applescript_manager):
    """ThingsTools instance (full write-operations stack) with mocked AppleScript."""
    return ThingsTools(mock_applescript_manager)


@pytest.fixture
def todo_operations(mock_applescript_manager):
    """Bare TodoOperations instance (bypasses ParameterValidator) for script-shape tests."""
    return TodoOperations(mock_applescript_manager, Mock())


@pytest.fixture
def bulk_operations(mock_applescript_manager):
    """Bare BulkOperations instance for bulk script-shape tests."""
    return BulkOperations(mock_applescript_manager, Mock())


def _script(mock_applescript_manager) -> str:
    mock_applescript_manager.execute_applescript.assert_called_once()
    args, kwargs = mock_applescript_manager.execute_applescript.call_args
    return args[0] if args else kwargs["script"]


class TestUpdateTodoClearFields:
    """update_todo(): notes='', deadline='', tags='' clear; title='' rejected."""

    @pytest.mark.asyncio
    async def test_notes_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", notes="")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert 'set notes of targetTodo to ""' in script

    @pytest.mark.asyncio
    async def test_notes_none_leaves_unchanged(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", title="New Title")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "set notes of targetTodo" not in script

    @pytest.mark.asyncio
    async def test_deadline_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", deadline="")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "delete due date of targetTodo" in script

    @pytest.mark.asyncio
    async def test_deadline_none_leaves_unchanged(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", title="New Title")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "set due date of targetTodo" not in script

    @pytest.mark.asyncio
    async def test_tags_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", tags=[])

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert 'set tag names of targetTodo to ""' in script

    @pytest.mark.asyncio
    async def test_tags_none_leaves_unchanged(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", title="New Title")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "set tag names of targetTodo" not in script

    @pytest.mark.asyncio
    async def test_title_empty_string_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", title="")

        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"
        assert result["field"] == "title"
        assert "cannot be empty" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_title_whitespace_only_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", title="   ")

        assert result["success"] is False
        assert result["field"] == "title"
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_empty_string_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_todo(todo_id="TODO-1", when="")

        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"
        assert result["field"] == "when"
        assert "anytime" in result["message"]
        assert "someday" in result["message"]
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_notes_and_deadline_clear_together(self, things_tools, mock_applescript_manager):
        """Multiple clear requests in one call each emit their own clear statement."""
        result = await things_tools.update_todo(todo_id="TODO-1", notes="", deadline="")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert 'set notes of targetTodo to ""' in script
        assert "delete due date of targetTodo" in script


class TestUpdateProjectClearFields:
    """update_project(): notes='', deadline='', tags='' clear; title='' rejected."""

    @pytest.mark.asyncio
    async def test_notes_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_project(project_id="PROJ-1", notes="")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert 'set notes of targetProject to ""' in script

    @pytest.mark.asyncio
    async def test_deadline_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_project(project_id="PROJ-1", deadline="")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "delete due date of targetProject" in script

    @pytest.mark.asyncio
    async def test_tags_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_project(project_id="PROJ-1", tags=[])

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert 'set tag names of targetProject to ""' in script

    @pytest.mark.asyncio
    async def test_title_empty_string_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_project(project_id="PROJ-1", title="")

        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"
        assert result["field"] == "title"
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_empty_string_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_project(project_id="PROJ-1", when="")

        assert result["success"] is False
        assert result["field"] == "when"
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_fields_not_provided_leave_unchanged(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_project(project_id="PROJ-1", title="New Title")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "set notes of targetProject" not in script
        assert "set due date of targetProject" not in script
        assert "set tag names of targetProject" not in script


class TestUpdateAreaClearFields:
    """update_area(): tags='' clears; title='' rejected."""

    @pytest.mark.asyncio
    async def test_tags_empty_list_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_area(area_id="AREA-1", tags=[])

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert 'set tag names of targetArea to ""' in script

    @pytest.mark.asyncio
    async def test_tags_none_leaves_unchanged(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_area(area_id="AREA-1", title="Renamed")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "set tag names of targetArea" not in script

    @pytest.mark.asyncio
    async def test_title_empty_string_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_area(area_id="AREA-1", title="")

        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"
        assert result["field"] == "title"
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_title_whitespace_only_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.update_area(area_id="AREA-1", title="   ")

        assert result["success"] is False
        assert result["field"] == "title"
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_tags_empty_list_alone_is_something_to_update(self, things_tools, mock_applescript_manager):
        """tags=[] (explicit clear) must not trip the 'nothing to update' guard."""
        result = await things_tools.update_area(area_id="AREA-1", tags=[])

        assert result["success"] is True
        mock_applescript_manager.execute_applescript.assert_called_once()

    @pytest.mark.asyncio
    async def test_nothing_provided_still_rejected(self, things_tools, mock_applescript_manager):
        """Omitting both title and tags entirely is still 'nothing to update'."""
        result = await things_tools.update_area(area_id="AREA-1")

        assert result["success"] is False
        mock_applescript_manager.execute_applescript.assert_not_called()


class TestBulkUpdateTodosClearFields:
    """bulk_update_todos(): notes='', deadline='', tags='' clear across all todos; title='' rejected."""

    @pytest.mark.asyncio
    async def test_notes_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.bulk_update_todos(todo_ids=["T1", "T2"], notes="")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert script.count('set notes of targetTodo to ""') == 2

    @pytest.mark.asyncio
    async def test_deadline_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.bulk_update_todos(todo_ids=["T1", "T2"], deadline="")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert script.count("delete due date of targetTodo") == 2

    @pytest.mark.asyncio
    async def test_tags_empty_string_clears(self, things_tools, mock_applescript_manager):
        result = await things_tools.bulk_update_todos(todo_ids=["T1", "T2"], tags="")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert script.count('set tag names of targetTodo to ""') == 2

    @pytest.mark.asyncio
    async def test_title_empty_string_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.bulk_update_todos(todo_ids=["T1", "T2"], title="")

        assert result["success"] is False
        assert result["error"] == "VALIDATION_ERROR"
        assert result["field"] == "title"
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_when_empty_string_rejected(self, things_tools, mock_applescript_manager):
        result = await things_tools.bulk_update_todos(todo_ids=["T1", "T2"], when="")

        assert result["success"] is False
        assert result["field"] == "when"
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_fields_not_provided_leave_unchanged(self, things_tools, mock_applescript_manager):
        result = await things_tools.bulk_update_todos(todo_ids=["T1"], title="New Title")

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "set notes of targetTodo" not in script
        assert "set due date of targetTodo" not in script
        assert "set tag names of targetTodo" not in script


class TestAllFilteredTagsIsNoOpNotClear:
    """When tag policy filters every requested tag, the result is a no-op
    (existing tags preserved), never confused with an explicit tags='' clear.
    """

    @pytest.mark.asyncio
    async def test_update_todo_all_filtered_skips_tag_statement(self, things_tools, mock_applescript_manager):
        from things_mcp.services.tag_service import TagValidationService, TagValidationResult

        mock_service = Mock(spec=TagValidationService)
        mock_service.validate_and_filter_tags = AsyncMock(return_value=TagValidationResult(
            valid_tags=[],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=["Filtered unknown tags: bogus."],
            errors=[]
        ))
        things_tools.write_ops.tag_validation_service = mock_service

        result = await things_tools.update_todo(todo_id="TODO-1", tags=["bogus"])

        assert result["success"] is True
        script = _script(mock_applescript_manager)
        assert "set tag names of targetTodo" not in script
