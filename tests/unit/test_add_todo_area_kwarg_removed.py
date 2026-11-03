"""hq-x1e: TodoOperations.add_todo no longer honours an unresolved ``area=`` name kwarg.

The only way to target an area is list_id/list_title, which are pre-resolved
via things.py before any write.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from things_mcp.pure_applescript_scheduler import PureAppleScriptScheduler
from things_mcp.services.applescript_manager import AppleScriptManager

AREA_UUID = "AREAUUID123"


@pytest.fixture
def manager():
    m = MagicMock(spec=AppleScriptManager)
    m.execute_applescript = AsyncMock(return_value={"success": True, "output": "new-id"})
    m.execute_url_scheme = AsyncMock()
    return m


@pytest.fixture
def scheduler(manager):
    return PureAppleScriptScheduler(manager)


def _scripts(manager):
    return [c.args[0] for c in manager.execute_applescript.await_args_list]


@pytest.mark.asyncio
async def test_area_name_kwarg_is_ignored(scheduler, manager):
    with patch("things_mcp.scheduling.todo_operations.things.get", return_value=None), \
         patch("things_mcp.scheduling.todo_operations.things.tasks", return_value=[]):
        await scheduler.add_todo(title="T", area="Some Area")
    scripts = _scripts(manager)
    assert scripts, "expected a create script to run"
    for script in scripts:
        assert "set area of newTodo" not in script
        assert "Some Area" not in script


@pytest.mark.asyncio
async def test_list_id_area_still_resolved(scheduler, manager):
    with patch("things_mcp.scheduling.todo_operations.things.get",
               return_value={"type": "area", "uuid": AREA_UUID, "title": "Some Area"}), \
         patch("things_mcp.scheduling.todo_operations.things.tasks", return_value=[]):
        result = await scheduler.add_todo(title="T", list_id=AREA_UUID)
    assert result["success"] is True
    assert any(f'set area of newTodo to area id "{AREA_UUID}"' in s for s in _scripts(manager))
