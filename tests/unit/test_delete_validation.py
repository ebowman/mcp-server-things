"""Test delete_todo parameter validation.

This test verifies that delete_todo properly validates the todo_id parameter
before attempting to execute AppleScript, preventing cryptic errors like:
"Can't get to do id 'None'"
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


GET_PATCH = "things_mcp.tools_helpers.write_operations.things.get"


@pytest.fixture(autouse=True)
def mock_things_get():
    """Patch things.get() for every test in this module (hermetic by default).

    Without this, delete_todo()'s type-resolution step
    (_resolve_delete_item_type) calls the real things.get() against
    whatever Things 3 database happens to be configured on the machine
    running the suite - tests would then depend on developer-machine state
    instead of being self-contained. Default behaviour mirrors a
    to-do id (things.get(id, trashed=None) resolves to a 'to-do' row),
    matching pre-hq-f0w.40 delete_todo's assumption; individual tests
    override this via their own `with patch(GET_PATCH, ...)` block, which
    takes precedence for the duration of that `with`.
    """
    with patch(GET_PATCH, return_value={'uuid': 'mock-id', 'type': 'to-do'}) as mock_get:
        yield mock_get


@pytest.fixture
def mock_applescript():
    """Create a mock AppleScript manager."""
    mock = MagicMock(spec=AppleScriptManager)
    mock.execute_applescript = AsyncMock(return_value={
        'success': True,
        'output': 'deleted'
    })
    return mock


@pytest.fixture
def tools(mock_applescript):
    """Create ThingsTools with mocked AppleScript."""
    return ThingsTools(mock_applescript)


@pytest.mark.asyncio
class TestDeleteValidation:
    """Test delete_todo parameter validation."""

    async def test_delete_with_none_fails(self, tools):
        """Test that delete_todo rejects None as todo_id."""
        result = await tools.delete_todo(None)

        assert result['success'] is False
        assert 'required' in result['error'].lower()
        assert 'todo_id' in result['error'].lower()

    async def test_delete_with_empty_string_fails(self, tools):
        """Test that delete_todo rejects empty string as todo_id."""
        result = await tools.delete_todo('')

        assert result['success'] is False
        assert 'empty' in result['error'].lower() or 'required' in result['error'].lower()
        assert 'todo_id' in result['error'].lower()

    async def test_delete_with_whitespace_only_fails(self, tools):
        """Test that delete_todo rejects whitespace-only todo_id."""
        result = await tools.delete_todo('   ')

        assert result['success'] is False
        assert 'empty' in result['error'].lower() or 'required' in result['error'].lower()

    async def test_delete_with_valid_id_succeeds(self, tools, mock_applescript):
        """Test that delete_todo works with valid todo_id."""
        result = await tools.delete_todo('ValidTodoID123')

        assert result['success'] is True
        assert 'successfully' in result['message'].lower()

        # Verify AppleScript was called
        mock_applescript.execute_applescript.assert_called_once()

        # Verify the script contains the todo ID
        call_args = mock_applescript.execute_applescript.call_args
        script = call_args[0][0]
        assert 'ValidTodoID123' in script
        assert 'delete' in script.lower()

    async def test_delete_error_handling(self, tools, mock_applescript):
        """Test that delete_todo handles AppleScript errors gracefully."""
        # Mock an AppleScript error on every attempt (to-do delete, and the
        # move-to-Trash last resort) so the overall call still fails.
        mock_applescript.execute_applescript = AsyncMock(return_value={
            'success': False,
            'error': 'Can\'t get to do id "NonexistentID"'
        })

        result = await tools.delete_todo('NonexistentID')

        assert result['success'] is False
        assert 'error' in result or 'message' in result


@pytest.mark.asyncio
class TestDeleteTodoTypeDispatch:
    """Test delete_todo's type-aware script selection (hq-f0w.40).

    Things' AppleScript dictionary does not treat a project as a to-do
    subtype for `delete`: `delete (to do id "<project-uuid>")` reliably
    errors even though reads on that id resolve fine - only `delete
    (project id "<project-uuid>")` works for projects. delete_todo()
    resolves the id's type via things.get() first to pick the right
    script, with fallbacks for when things.py can't resolve it.
    """

    async def test_project_id_uses_project_id_script(self, tools, mock_applescript):
        """A project id should emit `delete (project id ...)`, not `to do id`."""
        with patch(GET_PATCH, return_value={'uuid': 'ProjID1', 'type': 'project'}):
            result = await tools.delete_todo('ProjID1')

        assert result['success'] is True
        assert 'successfully' in result['message'].lower()
        assert result['message'] == 'Project deleted successfully'

        mock_applescript.execute_applescript.assert_called_once()
        script = mock_applescript.execute_applescript.call_args[0][0]
        assert 'project id "ProjID1"' in script
        assert 'to do id' not in script

    async def test_todo_id_uses_to_do_id_script(self, tools, mock_applescript):
        """A to-do id should emit `delete (to do id ...)`."""
        with patch(GET_PATCH, return_value={'uuid': 'TodoID1', 'type': 'to-do'}):
            result = await tools.delete_todo('TodoID1')

        assert result['success'] is True
        assert result['message'] == 'Todo deleted successfully'
        mock_applescript.execute_applescript.assert_called_once()
        script = mock_applescript.execute_applescript.call_args[0][0]
        assert 'to do id "TodoID1"' in script
        assert 'project id' not in script

    async def test_heading_id_returns_structured_error_without_applescript_call(self, tools, mock_applescript):
        """Headings cannot be deleted via AppleScript - reject before calling it."""
        with patch(GET_PATCH, return_value={'uuid': 'HeadingID1', 'type': 'heading'}):
            result = await tools.delete_todo('HeadingID1')

        assert result['success'] is False
        assert result['error'] == 'not_deletable'
        assert 'heading' in result['message'].lower()
        mock_applescript.execute_applescript.assert_not_called()

    async def test_area_id_returns_structured_error_without_applescript_call(self, tools, mock_applescript):
        """Areas cannot be deleted via AppleScript - reject before calling it."""
        with patch(GET_PATCH, return_value={'uuid': 'AreaID1', 'type': 'area'}):
            result = await tools.delete_todo('AreaID1')

        assert result['success'] is False
        assert result['error'] == 'not_deletable'
        assert 'area' in result['message'].lower()
        mock_applescript.execute_applescript.assert_not_called()

    async def test_tag_id_returns_structured_error_without_applescript_call(self, tools, mock_applescript):
        """Tags cannot be deleted via delete_todo() - reject before calling AppleScript."""
        with patch(GET_PATCH, return_value={'uuid': 'TagID1', 'type': 'tag'}):
            result = await tools.delete_todo('TagID1')

        assert result['success'] is False
        assert result['error'] == 'not_deletable'
        assert 'tag' in result['message'].lower()
        mock_applescript.execute_applescript.assert_not_called()

    async def test_nonexistent_id_returns_not_found_without_applescript_call(self, tools, mock_applescript):
        """When things.get() resolves cleanly but finds nothing, fail fast with not_found.

        A genuinely nonexistent id is NOT the same as things.py being
        unavailable - no AppleScript call (blind or otherwise) should be
        attempted for it.
        """
        with patch(GET_PATCH, return_value=None):
            result = await tools.delete_todo('DoesNotExist1')

        assert result['success'] is False
        assert result['error'] == 'not_found'
        assert 'DoesNotExist1' in result['message']
        mock_applescript.execute_applescript.assert_not_called()

    async def test_trashed_kwarg_type_error_retries_without_kwargs_and_resolves_area(self, tools, mock_applescript):
        """things.get(id, trashed=None) raising TypeError must retry bare and still classify.

        things.py 1.0.1's things.get(uuid, **kwargs) forwards **kwargs to
        areas()/tags() after tasks() rules an id out via ValueError.
        `trashed` is accepted by tasks() but not by
        Database.get_areas(), so `things.get(id, trashed=None)` raises
        TypeError for every non-task id (area, tag, nonexistent) - not just
        when things.py is genuinely unavailable. This must be treated as
        "retry without kwargs", not as "things.py unavailable" (which
        would incorrectly trigger the blind to-do/project fallback instead
        of correctly classifying the id and returning not_deletable).
        """
        def get_side_effect(uuid, **kwargs):
            if 'trashed' in kwargs:
                raise TypeError("get_areas() got an unexpected keyword argument 'trashed'")
            return {'uuid': uuid, 'type': 'area'}

        with patch(GET_PATCH, side_effect=get_side_effect):
            result = await tools.delete_todo('RealAreaID1')

        assert result['success'] is False
        assert result['error'] == 'not_deletable'
        assert 'area' in result['message'].lower()
        mock_applescript.execute_applescript.assert_not_called()

    async def test_trashed_kwarg_type_error_retry_resolves_tag(self, tools, mock_applescript):
        """Same TypeError-retry path, but the retry resolves a tag id."""
        def get_side_effect(uuid, **kwargs):
            if 'trashed' in kwargs:
                raise TypeError("got an unexpected keyword argument 'trashed'")
            return {'uuid': uuid, 'type': 'tag'}

        with patch(GET_PATCH, side_effect=get_side_effect):
            result = await tools.delete_todo('RealTagID1')

        assert result['success'] is False
        assert result['error'] == 'not_deletable'
        assert 'tag' in result['message'].lower()
        mock_applescript.execute_applescript.assert_not_called()

    async def test_trashed_kwarg_type_error_retry_resolves_nonexistent(self, tools, mock_applescript):
        """TypeError-retry path where the bare retry also finds nothing -> not_found, zero AppleScript calls."""
        def get_side_effect(uuid, **kwargs):
            if 'trashed' in kwargs:
                raise TypeError("got an unexpected keyword argument 'trashed'")
            return None

        with patch(GET_PATCH, side_effect=get_side_effect):
            result = await tools.delete_todo('BogusID1')

        assert result['success'] is False
        assert result['error'] == 'not_found'
        mock_applescript.execute_applescript.assert_not_called()

    async def test_things_get_unavailable_falls_back_to_blind_attempts(self, tools, mock_applescript):
        """When things.get() itself raises (things.py unavailable), fall back blind."""
        mock_applescript.execute_applescript = AsyncMock(side_effect=[
            {'success': False, 'error': 'Can\'t get to do id "Broken1"'},
            {'success': True, 'output': 'deleted'},
        ])

        with patch(GET_PATCH, side_effect=RuntimeError("things.py import failed")):
            result = await tools.delete_todo('Broken1')

        assert result['success'] is True
        assert mock_applescript.execute_applescript.call_count == 2

    async def test_delete_and_project_id_both_fail_falls_back_to_move_to_trash(self, tools, mock_applescript):
        """When both `delete` forms fail, fall back to `move ... to list "Trash"`."""
        mock_applescript.execute_applescript = AsyncMock(side_effect=[
            {'success': False, 'error': 'Can\'t get to do id "Orphan1"'},
            {'success': False, 'error': 'Can\'t get project id "Orphan1"'},
            {'success': True, 'output': 'trashed'},
        ])

        with patch(GET_PATCH, side_effect=RuntimeError("things.py import failed")):
            result = await tools.delete_todo('Orphan1')

        assert result['success'] is True
        assert 'trash' in result['message'].lower()
        assert mock_applescript.execute_applescript.call_count == 3
        move_script = mock_applescript.execute_applescript.call_args_list[2][0][0]
        assert 'move' in move_script.lower()
        assert 'to list "Trash"' in move_script

    async def test_delete_and_move_to_trash_all_fail_returns_structured_error(self, tools, mock_applescript):
        """When delete AND move-to-Trash all fail, return a structured error."""
        mock_applescript.execute_applescript = AsyncMock(side_effect=[
            {'success': False, 'error': 'Can\'t get to do id "Gone1"'},
            {'success': False, 'error': 'Can\'t get project id "Gone1"'},
            {'success': False, 'error': 'Can\'t get to do id "Gone1"'},
        ])

        with patch(GET_PATCH, side_effect=RuntimeError("things.py import failed")):
            result = await tools.delete_todo('Gone1')

        assert result['success'] is False
        assert result['error']
        assert mock_applescript.execute_applescript.call_count == 3
