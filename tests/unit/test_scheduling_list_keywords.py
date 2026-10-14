"""hq-bz2: someday/anytime must not run the failing date strategies first."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from things_mcp.scheduling.strategies import SchedulingStrategies


@pytest.mark.parametrize("when,lst", [("someday", "Someday"), ("anytime", "Anytime")])
def test_list_keyword_goes_straight_to_list_move(when, lst):
    am = MagicMock()
    am.execute_applescript = AsyncMock(return_value={"success": True, "output": "moved_to_list"})
    result = asyncio.run(SchedulingStrategies(am).schedule_todo_reliable("abc", when))
    assert result["success"] is True
    assert result["method"] == "list_fallback"
    assert am.execute_applescript.await_count == 1
    assert f'list "{lst}"' in am.execute_applescript.await_args.args[0]
