"""bulk_update_todos must return a structured VALIDATION_ERROR when the tag policy rejects (hq-1rm).

All external calls are mocked; Things 3 is never touched.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.services.tag_service import TagValidationResult, TagValidationService
from things_mcp.tools import ThingsTools


@pytest.mark.asyncio
async def test_bulk_update_fail_on_unknown_returns_validation_error():
    manager = Mock(spec=AppleScriptManager)
    manager.execute_applescript = AsyncMock()
    tools = ThingsTools(manager)

    service = Mock(spec=TagValidationService)
    service.validate_and_filter_tags = AsyncMock(return_value=TagValidationResult(
        valid_tags=[],
        filtered_tags=["bogus"],
        created_tags=[],
        warnings=[],
        errors=["Operation rejected due to unknown tags: bogus."],
    ))
    tools.bulk_ops.tag_validation_service = service

    result = await tools.bulk_update_todos(todo_ids=["t1", "t2"], tags="bogus")

    assert result["success"] is False
    assert result["error"] == "VALIDATION_ERROR"
    assert result["field"] == "tags"
    assert "unknown tags: bogus" in result["message"]
    manager.execute_applescript.assert_not_called()
