"""
Unit tests for tag_creation_policy enforcement on add_project/update_project.

These tests mock the AppleScript manager entirely - no real AppleScript is
executed and Things 3 is never touched. They verify that WriteOperations
validates and filters tags via a policy-aware TagValidationService BEFORE
sending the write to AppleScript, mirroring add_todo's behaviour.
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
    """Attach a mocked policy-aware TagValidationService to things_tools.write_ops."""
    mock_service = Mock(spec=TagValidationService)
    mock_service.validate_and_filter_tags = AsyncMock(return_value=result)
    things_tools.write_ops.tag_validation_service = mock_service
    return mock_service


class TestAddProjectTagPolicy:
    """Test that add_project honours a configured tag_creation_policy."""

    @pytest.mark.asyncio
    async def test_add_project_filters_unknown_tags(self, things_tools, mock_applescript_manager):
        """filter_unknown-style policy: only the valid tag reaches AppleScript."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "PROJECT-ID-1",
        }
        result_obj = TagValidationResult(
            valid_tags=["work"],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=["Filtered unknown tags: bogus. Only existing tags will be applied."],
            errors=[]
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.add_project(title="My Project", tags=["work", "bogus"])

        assert result["success"] is True
        assert result["tag_info"]["existing"] == ["work"]
        assert result["tag_info"]["filtered"] == ["bogus"]

        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert "tag names of newProject" in script
        assert '"work"' in script
        assert "bogus" not in script

    @pytest.mark.asyncio
    async def test_add_project_reject_unknown_aborts_without_applescript(self, things_tools, mock_applescript_manager):
        """fail_on_unknown policy: operation is rejected before AppleScript runs."""
        result_obj = TagValidationResult(
            valid_tags=[],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=[],
            errors=["Operation rejected due to unknown tags: bogus. Please create these tags first or change tag policy to allow/filter."]
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.add_project(title="Rejected Project", tags=["bogus"])

        assert result["success"] is False
        assert result["tag_info"]["errors"]

        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_project_all_tags_filtered_proceeds_without_tags(self, things_tools, mock_applescript_manager):
        """When every requested tag is filtered out, project is still created without a tag statement."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "PROJECT-ID-2",
        }
        result_obj = TagValidationResult(
            valid_tags=[],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=["Filtered unknown tags: bogus. Only existing tags will be applied."],
            errors=[]
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.add_project(title="No Valid Tags Project", tags=["bogus"])

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert "tag names of newProject" not in script

    @pytest.mark.asyncio
    async def test_add_project_without_tag_service_is_unfiltered(self, things_tools, mock_applescript_manager):
        """No tag_validation_service configured: tags pass through unfiltered (backward compatible)."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "PROJECT-ID-3",
        }

        result = await things_tools.add_project(title="Plain Project", tags=["anything"])

        assert result["success"] is True
        assert "tag_info" not in result
        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert '"anything"' in script


class TestUpdateProjectTagPolicy:
    """Test that update_project honours a configured tag_creation_policy."""

    @pytest.mark.asyncio
    async def test_update_project_filters_unknown_tags(self, things_tools, mock_applescript_manager):
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "updated",
        }
        result_obj = TagValidationResult(
            valid_tags=["review"],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=["Filtered unknown tags: bogus. Only existing tags will be applied."],
            errors=[]
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.update_project(project_id="PROJ-1", tags=["review", "bogus"])

        assert result["success"] is True
        assert result["tag_info"]["existing"] == ["review"]

        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert "tag names of targetProject" in script
        assert '"review"' in script
        assert "bogus" not in script

    @pytest.mark.asyncio
    async def test_update_project_reject_unknown_aborts_without_applescript(self, things_tools, mock_applescript_manager):
        result_obj = TagValidationResult(
            valid_tags=[],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=[],
            errors=["Operation rejected due to unknown tags: bogus. Please create these tags first or change tag policy to allow/filter."]
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.update_project(project_id="PROJ-1", tags=["bogus"])

        assert result["success"] is False
        assert result["tag_info"]["errors"]

        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_project_all_tags_filtered_skips_tag_statement(self, things_tools, mock_applescript_manager):
        """When every requested tag is filtered out, existing tags are left unchanged (no clearing)."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "updated",
        }
        result_obj = TagValidationResult(
            valid_tags=[],
            filtered_tags=["bogus"],
            created_tags=[],
            warnings=["Filtered unknown tags: bogus. Only existing tags will be applied."],
            errors=[]
        )
        _install_mock_tag_service(things_tools, result_obj)

        result = await things_tools.update_project(project_id="PROJ-1", tags=["bogus"])

        assert result["success"] is True
        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert "tag names of targetProject" not in script
