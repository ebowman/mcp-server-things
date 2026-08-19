"""hq-nxu.8: get_todos(project_uuid=...) and get_todos() must return the
same schema (key set), because both now go through the single things.py
path in ReadOperations._get_todos_sync/convert_todo.

Historically, the project_uuid branch used AppleScript
(convert_applescript_todo's key set: creationDate/modificationDate/
activationDate/dueDate/hasReminder/reminderTime) while the unscoped branch
used things.py (convert_todo's key set: start/startDate/project/
projectTitle/heading/headingTitle/hasChecklist/...) - two different
schemas for the same tool, chosen by whether project_uuid happened to be
passed. Measurement (see read_operations.py's get_todos docstring) showed
no meaningful AppleScript-vs-things.py database sync lag, so the
AppleScript branch was removed; this test pins down that both call shapes
now emit identical key sets.
"""

from unittest.mock import Mock, patch

import pytest

from things_mcp.tools import ThingsTools
from fixtures.things_realistic import make_todo


@pytest.fixture
def mock_things():
    """Mock the things module used by read_operations.py."""
    with patch('things_mcp.tools_helpers.read_operations.things') as mock:
        yield mock


@pytest.fixture
def mock_applescript_manager():
    manager = Mock()
    manager.execute_script = Mock(return_value="success")
    return manager


@pytest.fixture
def tools(mock_things, mock_applescript_manager):
    return ThingsTools(mock_applescript_manager)


class TestGetTodosSchemaParity:
    @pytest.mark.asyncio
    async def test_project_scoped_and_unscoped_return_identical_key_sets(
        self, tools, mock_things, mock_applescript_manager
    ):
        """A todo returned via project_uuid= and the same todo returned via
        an unscoped call must produce the exact same converted key set."""
        row = make_todo(
            uuid="todo-1",
            title="Shared Todo",
            heading="heading-1",
            heading_title="Review",
            project="project-1",
            project_title="My Project",
            tags=["work"],
        )
        mock_things.todos.return_value = [row]

        project_result = await tools.get_todos(project_uuid="project-1", status="incomplete")
        unscoped_result = await tools.get_todos(status="incomplete")

        # Neither path should have touched the AppleScript manager's
        # (now-removed) get_todos method.
        mock_applescript_manager.get_todos.assert_not_called()

        assert len(project_result) == 1
        assert len(unscoped_result) == 1
        assert set(project_result[0].keys()) == set(unscoped_result[0].keys())
        assert project_result[0] == unscoped_result[0]

    @pytest.mark.asyncio
    async def test_project_scoped_call_passes_project_and_status_through(
        self, tools, mock_things
    ):
        """get_todos(project_uuid=..., status=...) must forward both kwargs
        to things.todos() in one call (no separate AppleScript round-trip,
        no client-side status re-filtering needed)."""
        mock_things.todos.return_value = [
            make_todo(uuid="todo-1", title="Done", status="completed"),
        ]

        result = await tools.get_todos(project_uuid="project-9", status="completed")

        mock_things.todos.assert_called_once_with(status="completed", project="project-9")
        assert len(result) == 1
        assert result[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_project_scoped_default_status_incomplete(self, tools, mock_things):
        """Default status='incomplete' applies identically whether or not
        project_uuid is given."""
        mock_things.todos.return_value = [
            make_todo(uuid="todo-1", title="Open", status="incomplete"),
        ]

        result = await tools.get_todos(project_uuid="project-9")

        mock_things.todos.assert_called_once_with(status="incomplete", project="project-9")
        assert len(result) == 1
