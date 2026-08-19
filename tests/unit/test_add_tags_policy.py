"""
Unit tests for add_tags tag_creation_policy enforcement and tag dedupe.

These tests mock the AppleScript manager and tag validation service entirely
- no real AppleScript is executed and Things 3 is never touched.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.services.tag_service import TagValidationService, TagValidationResult


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager."""
    manager = Mock(spec=AppleScriptManager)
    manager.execute_applescript = AsyncMock()
    return manager


@pytest.fixture
def things_tools(mock_applescript_manager):
    """Create ThingsTools instance with mocked AppleScript."""
    return ThingsTools(mock_applescript_manager)


def _install_mock_tag_service(things_tools, result: TagValidationResult):
    """Attach a mocked policy-aware TagValidationService to things_tools.write_ops.

    Returns the mock service so tests can assert on how it was called.
    """
    mock_service = Mock(spec=TagValidationService)
    mock_service.validate_and_filter_tags = AsyncMock(return_value=result)
    things_tools.write_ops.tag_validation_service = mock_service
    return mock_service


class TestAddTagsPolicy:
    """Test that add_tags honours a configured tag_creation_policy via TagValidationService."""

    @pytest.mark.asyncio
    async def test_add_tags_reject_unknown_aborts_without_applescript(
        self, things_tools, mock_applescript_manager
    ):
        """fail_on_unknown policy: add_tags aborts before any AppleScript call, like add_todo.

        Regression case: the service still populates valid_tags with the known tag
        ("work") even while rejecting the request via errors (tag_service.py puts
        known tags in valid_tags unconditionally, then appends to errors when
        unknown tags are present under fail_on_unknown - see tag_service.py:190,231).
        The pre-fix add_tags computed valid_tags = existing + created without ever
        checking errors, so it would still write ["work"] to AppleScript and report
        success. This must abort with no AppleScript call at all.
        """
        result_obj = TagValidationResult(
            valid_tags=["work"],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=[],
            errors=[
                "Operation rejected due to unknown tags: bogus. Please create these tags "
                "first or change tag policy to allow/filter."
            ],
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.add_tags(todo_id="abc123", tags=["work", "bogus"])

        assert result["success"] is False
        assert "tag_info" in result
        assert result["tag_info"]["errors"]
        assert "message" in result
        assert "error" in result

        # No AppleScript call at all - not even the "get current tags" lookup.
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_tags_reject_all_filtered_aborts_without_applescript(
        self, things_tools, mock_applescript_manager
    ):
        """fail_on_unknown policy, all-filtered variant: valid_tags=[] and errors set."""
        result_obj = TagValidationResult(
            valid_tags=[],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=[],
            errors=[
                "Operation rejected due to unknown tags: bogus. Please create these tags "
                "first or change tag policy to allow/filter."
            ],
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.add_tags(todo_id="abc123", tags=["bogus"])

        assert result["success"] is False
        assert "tag_info" in result
        assert result["tag_info"]["errors"]

        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_tags_filters_unknown_tags(self, things_tools, mock_applescript_manager):
        """filter policy: only the valid tag(s) reach the generated AppleScript."""
        mock_applescript_manager.execute_applescript.side_effect = [
            {"success": True, "output": ""},  # current tag lookup
            {"success": True, "output": "tags_added"},  # set tag names
        ]
        result_obj = TagValidationResult(
            valid_tags=["work"],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=["Filtered unknown tags: bogus. Only existing tags will be applied."],
            errors=[],
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.add_tags(todo_id="abc123", tags=["work", "bogus"])

        assert result["success"] is True
        assert result["tag_info"]["existing"] == ["work"]
        assert result["tag_info"]["filtered"] == ["bogus"]

        # Second call is the write; inspect the generated script.
        script = mock_applescript_manager.execute_applescript.call_args_list[1][0][0]
        assert '"work"' in script
        assert "bogus" not in script


class TestPrepareTagsDedupe:
    """Test that _prepare_tags dedupes valid_tags (existing + created) order-preservingly."""

    @pytest.mark.asyncio
    async def test_prepare_tags_dedupes_created_tag_already_in_valid_tags(self, things_tools):
        """TagValidationService already folds created tags into valid_tags; _prepare_tags
        must not duplicate them."""
        result_obj = TagValidationResult(
            valid_tags=["a", "new"],
            filtered_tags=[],
            created_tags=["new"],
            warnings=["Created new tags: new"],
            errors=[],
        )
        _install_mock_tag_service(things_tools, result_obj)

        error_response, valid_tags, tag_info = await things_tools.write_ops._prepare_tags(
            ["a", "new"]
        )

        assert error_response is None
        assert valid_tags == ["a", "new"]
        assert valid_tags.count("new") == 1

    @pytest.mark.asyncio
    async def test_add_area_no_duplicate_tag_names_in_script(
        self, things_tools, mock_applescript_manager
    ):
        """End-to-end: add_area's generated 'tag names of newArea' script contains the
        auto-created tag exactly once, not twice."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "AREA-ID-DEDUPE",
        }
        result_obj = TagValidationResult(
            valid_tags=["a", "new"],
            filtered_tags=[],
            created_tags=["new"],
            warnings=["Created new tags: new"],
            errors=[],
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.add_area(title="Dedupe Area", tags=["a", "new"])

        assert result["success"] is True

        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        tag_names_line = next(
            line for line in script.splitlines() if "tag names of newArea to" in line
        )
        assert tag_names_line.strip().endswith('"a, new"')
