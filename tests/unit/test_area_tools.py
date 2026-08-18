"""
Unit tests for Area management tools: add_area and update_area.

These tests mock the AppleScript manager entirely - no real AppleScript is
executed and Things 3 is never touched.
"""

import pytest
from unittest.mock import AsyncMock, Mock

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


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


class TestAddArea:
    """Test creating a new area."""

    @pytest.mark.asyncio
    async def test_add_area_success_returns_id(self, things_tools, mock_applescript_manager):
        """Test add_area returns the new area's id on success."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "AREA-ID-123",
        }

        result = await things_tools.add_area(title="Side Projects")

        assert result["success"] is True
        assert result["area_id"] == "AREA-ID-123"
        assert result["title"] == "Side Projects"
        assert "message" in result

        # Confirm the AppleScript targets area creation
        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert "make new area" in script
        assert '"Side Projects"' in script

    @pytest.mark.asyncio
    async def test_add_area_with_tags(self, things_tools, mock_applescript_manager):
        """Test add_area applies tags via 'tag names of newArea'."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "AREA-ID-456",
        }

        result = await things_tools.add_area(title="Work Stuff", tags=["urgent", "work"])

        assert result["success"] is True
        assert result["area_id"] == "AREA-ID-456"

        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert "tag names of newArea" in script
        assert "urgent, work" in script

    @pytest.mark.asyncio
    async def test_add_area_empty_title_validation(self, things_tools, mock_applescript_manager):
        """Test add_area rejects an empty/whitespace title without calling AppleScript."""
        result = await things_tools.add_area(title="   ")

        assert result["success"] is False
        assert "error" in result

        # Should never reach AppleScript execution
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_area_escapes_quotes_and_backslashes(self, things_tools, mock_applescript_manager):
        """Test titles containing quotes/backslashes are escaped in generated AppleScript."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "AREA-ID-789",
        }

        title = 'My "Special" Area\\Path'
        result = await things_tools.add_area(title=title)

        assert result["success"] is True

        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        # Backslashes must be doubled and quotes escaped
        assert '\\"Special\\"' in script
        assert 'Area\\\\Path' in script


class TestUpdateArea:
    """Test updating an existing area."""

    @pytest.mark.asyncio
    async def test_update_area_rename_only(self, things_tools, mock_applescript_manager):
        """Test update_area with only a new title."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "updated",
        }

        result = await things_tools.update_area(area_id="AREA-1", title="Renamed Area")

        assert result["success"] is True

        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert "set name of targetArea to" in script
        assert '"Renamed Area"' in script
        assert "tag names of targetArea" not in script

    @pytest.mark.asyncio
    async def test_update_area_tags_only(self, things_tools, mock_applescript_manager):
        """Test update_area with only tags provided."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "updated",
        }

        result = await things_tools.update_area(area_id="AREA-1", tags=["review", "later"])

        assert result["success"] is True

        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert "set tag names of targetArea to" in script
        assert "review, later" in script
        assert "set name of targetArea" not in script

    @pytest.mark.asyncio
    async def test_update_area_not_found(self, things_tools, mock_applescript_manager):
        """Test update_area surfaces a not-found error for unknown ids."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "error: Can't get area id \"BOGUS-ID\".",
        }

        result = await things_tools.update_area(area_id="BOGUS-ID", title="New Name")

        assert result["success"] is False
        assert "Area not found" in result["error"]
        assert "BOGUS-ID" in result["error"]

    @pytest.mark.asyncio
    async def test_update_area_nothing_to_update(self, things_tools, mock_applescript_manager):
        """Test update_area with no fields provided returns a validation-style failure."""
        result = await things_tools.update_area(area_id="AREA-1")

        assert result["success"] is False
        assert "error" in result

        # Should never reach AppleScript execution
        mock_applescript_manager.execute_applescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_area_escapes_quotes_and_backslashes(self, things_tools, mock_applescript_manager):
        """Test new titles containing quotes/backslashes are escaped in generated AppleScript."""
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "updated",
        }

        title = 'Weird "Title"\\Name'
        result = await things_tools.update_area(area_id="AREA-1", title=title)

        assert result["success"] is True

        script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert '\\"Title\\"' in script
        assert 'Weird \\"Title\\"\\\\Name' in script
