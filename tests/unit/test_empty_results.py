"""
Unit tests for empty result handling in time-based query functions.

Tests verify that functions return consistent empty responses instead of silent failures.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from things_mcp.pure_applescript_scheduler import PureAppleScriptScheduler


@pytest.fixture
def mock_applescript():
    """Create a mock AppleScript manager."""
    mock = MagicMock()
    mock.execute_applescript = AsyncMock()
    return mock


@pytest.fixture
def scheduler(mock_applescript):
    """Create a PureAppleScriptScheduler with mocked AppleScript manager."""
    return PureAppleScriptScheduler(mock_applescript)


class TestEmptyResultHandling:
    """Test that time-based queries return consistent empty results."""

    @pytest.mark.asyncio
    async def test_get_todos_due_in_days_empty_result(self, scheduler, mock_applescript):
        """Test get_todos_due_in_days returns empty array when no results."""
        # Mock AppleScript to return an empty list
        mock_applescript.execute_applescript.return_value = {
            "success": True,
            "output": []
        }

        result = await scheduler.get_todos_due_in_days(7)

        assert result == [], f"Expected empty list, got: {result}"
        assert isinstance(result, list), "Result should be a list"

    @pytest.mark.asyncio
    async def test_get_todos_due_in_days_with_results(self, scheduler, mock_applescript):
        """Test get_todos_due_in_days returns data when results exist."""
        # Mock AppleScript to return a todo
        mock_applescript.execute_applescript.return_value = {
            "success": True,
            "output": ["ID:123|TITLE:Test Todo|DEADLINE:Monday, January 1, 2024 at 12:00:00 AM"]
        }

        result = await scheduler.get_todos_due_in_days(7)

        assert isinstance(result, list), "Result should be a list"
        assert len(result) > 0, "Result should contain items"
        assert result[0]['id'] == '123'

    @pytest.mark.asyncio
    async def test_get_todos_activating_in_days_empty_result(self, scheduler, mock_applescript):
        """Test get_todos_activating_in_days returns empty array when no results."""
        # Mock AppleScript to return an empty list
        mock_applescript.execute_applescript.return_value = {
            "success": True,
            "output": []
        }

        result = await scheduler.get_todos_activating_in_days(14)

        assert result == [], f"Expected empty list, got: {result}"
        assert isinstance(result, list), "Result should be a list"

    @pytest.mark.asyncio
    async def test_get_todos_activating_in_days_with_results(self, scheduler, mock_applescript):
        """Test get_todos_activating_in_days returns data when results exist."""
        # Mock AppleScript to return a todo
        mock_applescript.execute_applescript.return_value = {
            "success": True,
            "output": ["ID:456|TITLE:Scheduled Todo|ACTIVATION:Monday, January 15, 2024 at 12:00:00 AM"]
        }

        result = await scheduler.get_todos_activating_in_days(14)

        assert isinstance(result, list), "Result should be a list"
        assert len(result) > 0, "Result should contain items"
        assert result[0]['id'] == '456'

    @pytest.mark.asyncio
    async def test_get_recent_empty_result(self, scheduler, mock_applescript):
        """Test get_recent returns empty array when no results."""
        # Mock AppleScript to return an empty list
        mock_applescript.execute_applescript.return_value = {
            "success": True,
            "output": []
        }

        result = await scheduler.get_recent('7d')

        assert result == [], f"Expected empty list, got: {result}"
        assert isinstance(result, list), "Result should be a list"

    @pytest.mark.asyncio
    async def test_get_recent_with_results(self, scheduler, mock_applescript):
        """Test get_recent returns data when results exist."""
        # Mock AppleScript to return a completed todo
        mock_applescript.execute_applescript.return_value = {
            "success": True,
            "output": ["ID:789|TITLE:Completed Todo|COMPLETED:Monday, December 25, 2024 at 12:00:00 AM"]
        }

        result = await scheduler.get_recent('7d')

        assert isinstance(result, list), "Result should be a list"
        assert len(result) > 0, "Result should contain items"
        assert result[0]['id'] == '789'

    @pytest.mark.asyncio
    async def test_get_todos_due_in_days_error_handling(self, scheduler, mock_applescript):
        """Test get_todos_due_in_days handles errors gracefully."""
        # Mock AppleScript to return an error
        mock_applescript.execute_applescript.return_value = {
            "success": False,
            "output": "error: Something went wrong"
        }

        result = await scheduler.get_todos_due_in_days(30)

        assert result == [], f"Expected empty list on error, got: {result}"
        assert isinstance(result, list), "Result should be a list even on error"

    @pytest.mark.asyncio
    async def test_get_todos_activating_in_days_error_handling(self, scheduler, mock_applescript):
        """Test get_todos_activating_in_days handles errors gracefully."""
        # Mock AppleScript to return an error
        mock_applescript.execute_applescript.return_value = {
            "success": False,
            "output": "error: Something went wrong"
        }

        result = await scheduler.get_todos_activating_in_days(30)

        assert result == [], f"Expected empty list on error, got: {result}"
        assert isinstance(result, list), "Result should be a list even on error"

    @pytest.mark.asyncio
    async def test_get_recent_error_handling(self, scheduler, mock_applescript):
        """Test get_recent handles errors gracefully."""
        # Mock AppleScript to return an error
        mock_applescript.execute_applescript.return_value = {
            "success": False,
            "output": "error: Something went wrong"
        }

        result = await scheduler.get_recent('7d')

        assert result == [], f"Expected empty list on error, got: {result}"
        assert isinstance(result, list), "Result should be a list even on error"

    @pytest.mark.asyncio
    async def test_non_list_output_handling(self, scheduler, mock_applescript):
        """Test that non-list outputs are handled gracefully."""
        # Mock AppleScript to return a non-list output
        mock_applescript.execute_applescript.return_value = {
            "success": True,
            "output": "Not a list"
        }

        result = await scheduler.get_todos_due_in_days(7)

        assert result == [], f"Expected empty list for non-list output, got: {result}"
        assert isinstance(result, list), "Result should be a list"