"""
Unit tests for update_project status handling (hq-f0w.11).

Regression coverage for two bugs:
  - C3: update_project(canceled=...) was silently dropped - canceled was never
    read from kwargs and no AppleScript status statement was emitted for it.
  - C4: update_project(completed=...) emitted `set completion date of
    targetProject to ...` instead of `set status of targetProject to
    completed/open`, which does not reliably move a project to the Logbook.

These tests render the AppleScript produced by
TodoOperations.update_project() and assert on the exact status statements,
mirroring the todo path's precedence (_build_update_script): canceled wins
when both completed and canceled are given, and completed=False reopens.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from things_mcp.scheduling.todo_operations import TodoOperations


@pytest.fixture
def mock_applescript_manager():
    """Mock AppleScript manager that captures the script and reports success."""
    manager = Mock()
    manager.execute_applescript = AsyncMock(return_value={
        "success": True,
        "output": "updated",
    })
    return manager


@pytest.fixture
def todo_operations(mock_applescript_manager):
    """TodoOperations instance with a mocked AppleScript manager.

    The scheduler is unused by update_project, so a bare Mock suffices.
    """
    return TodoOperations(mock_applescript_manager, Mock())


def _rendered_script(mock_applescript_manager) -> str:
    """Return the AppleScript string passed to execute_applescript."""
    mock_applescript_manager.execute_applescript.assert_called_once()
    args, kwargs = mock_applescript_manager.execute_applescript.call_args
    return args[0] if args else kwargs["script"]


class TestUpdateProjectCompletedStatus:
    """C4: completed should map to `set status of targetProject to ...`."""

    @pytest.mark.asyncio
    async def test_completed_true_sets_status_completed(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_project("PROJ-1", completed=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject to completed" in script
        assert "completion date" not in script

    @pytest.mark.asyncio
    async def test_completed_false_sets_status_open(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_project("PROJ-1", completed=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject to open" in script
        assert "completion date" not in script

    @pytest.mark.asyncio
    async def test_completed_none_emits_no_status_statement(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_project("PROJ-1", title="New Title")

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject" not in script
        assert "completion date" not in script


class TestUpdateProjectCanceledStatus:
    """C3: canceled must be read from kwargs and forwarded to the script."""

    @pytest.mark.asyncio
    async def test_canceled_true_sets_status_canceled(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_project("PROJ-1", canceled=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject to canceled" in script
        assert "completion date" not in script

    @pytest.mark.asyncio
    async def test_canceled_false_alone_sets_status_open(self, todo_operations, mock_applescript_manager):
        """canceled=False with no completed given reopens the project.

        This is required by the bead's done-criteria:
        update_project(canceled='false') -> things.get(uuid)['status'] == 'incomplete'.
        As of hq-f0w.22, the todo path's _build_update_script uses this same
        semantics (canceled=False alone reopens); update_todo, bulk_update_todos
        and update_project now share one status-precedence table (see CLAUDE.md).
        """
        result = await todo_operations.update_project("PROJ-1", canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject to open" in script
        assert "completion date" not in script


class TestUpdateProjectStatusPrecedence:
    """canceled takes precedence over completed when both are given."""

    @pytest.mark.asyncio
    async def test_canceled_true_wins_over_completed_true(self, todo_operations, mock_applescript_manager):
        result = await todo_operations.update_project("PROJ-1", completed=True, canceled=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject to canceled" in script
        assert script.count("set status of targetProject to completed") == 0

    @pytest.mark.asyncio
    async def test_canceled_true_wins_over_completed_false(self, todo_operations, mock_applescript_manager):
        """Edge case from the bead: completed='false' and canceled='true' together."""
        result = await todo_operations.update_project("PROJ-1", completed=False, canceled=True)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject to canceled" in script
        assert script.count("set status of targetProject to open") == 0
        assert script.count("set status of targetProject to completed") == 0

    @pytest.mark.asyncio
    async def test_completed_true_wins_over_canceled_false(self, todo_operations, mock_applescript_manager):
        """completed=True, canceled=False -> completed (canceled=False is only
        the reopen signal when completed is NOT given; here completed decides).
        This is the same cell hq-f0w.22 review gap 1 found broken in
        bulk_update_todos - locked in here for update_project too."""
        result = await todo_operations.update_project("PROJ-1", completed=True, canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject to completed" in script
        assert script.count("set status of targetProject to open") == 0

    @pytest.mark.asyncio
    async def test_completed_false_and_canceled_false_sets_status_open(self, todo_operations, mock_applescript_manager):
        """completed=False, canceled=False -> open (both agree on reopening)."""
        result = await todo_operations.update_project("PROJ-1", completed=False, canceled=False)

        assert result["success"] is True
        script = _rendered_script(mock_applescript_manager)

        assert "set status of targetProject to open" in script
        assert script.count("set status of targetProject to canceled") == 0


class TestUpdateProjectForwardsCanceledFromToolsChain(object):
    """Confirm the canceled sentinel reaches the rendered script through the
    ThingsTools -> WriteOperations -> PureAppleScriptScheduler -> TodoOperations
    delegation chain (not just when TodoOperations is called directly)."""

    @pytest.mark.asyncio
    async def test_things_tools_update_project_forwards_canceled(self):
        from things_mcp.tools import ThingsTools

        mock_manager = Mock()
        mock_manager.execute_applescript = AsyncMock(return_value={
            "success": True,
            "output": "updated",
        })

        tools = ThingsTools(mock_manager)

        result = await tools.update_project(project_id="PROJ-1", canceled=True)

        assert result["success"] is True
        mock_manager.execute_applescript.assert_called_once()
        args, kwargs = mock_manager.execute_applescript.call_args
        script = args[0] if args else kwargs["script"]

        assert "set status of targetProject to canceled" in script
