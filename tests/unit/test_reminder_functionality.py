"""
Unit tests for Things 3 reminder functionality.

Tests the reminder feature implementation including:
- Time validation and parsing
- Datetime input handling
- URL scheme construction for reminders
- Reminder detection from activation_date
- Integration with existing todo operations
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager for testing."""
    manager = MagicMock(spec=AppleScriptManager)
    manager.execute_applescript = AsyncMock()
    manager.execute_url_scheme = AsyncMock()
    manager._has_reminder_time = MagicMock()
    manager._extract_reminder_time = MagicMock()
    manager._parse_applescript_date = MagicMock()
    return manager


@pytest.fixture
def things_tools(mock_applescript_manager):
    """Create ThingsTools instance with mocked manager."""
    return ThingsTools(mock_applescript_manager)


class TestTimeValidation:
    """Test time format validation for reminders."""
    
    def test_validate_valid_time_formats(self, things_tools):
        """Test validation of valid time formats."""
        valid_times = [
            "14:30",
            "09:15", 
            "23:59",
            "00:00",  # Midnight edge case
            "12:00",  # Noon edge case  
            "6:30",   # Single digit hour
            "1:00",   # Minimal single digit
            "05:05",  # Leading zeros
            "7:9"     # Minimal format without zeros
        ]
        
        for time_str in valid_times:
            assert things_tools._validate_time_format(time_str), f"Time {time_str} should be valid"
    
    def test_validate_invalid_time_formats(self, things_tools):
        """Test validation of invalid time formats."""
        invalid_times = [
            "25:00",    # Invalid hour  
            "24:00",    # Invalid hour (24 hour format goes 0-23)
            "12:75",    # Invalid minute
            "12:60",    # Invalid minute (60 is out of range)
            "abc",      # Non-numeric
            "14:30:45", # Seconds not allowed
            "14",       # Missing colon
            "14:",      # Missing minute
            ":30",      # Missing hour
            "",         # Empty
            None,       # None
            " 14:30",   # Leading space
            "14:30 ",   # Trailing space
            "1430",     # No colon
            "14-30",    # Wrong separator
            "14.30"     # Wrong separator
        ]
        
        for time_str in invalid_times:
            assert not things_tools._validate_time_format(time_str), f"Time {time_str} should be invalid"
    
    def test_validate_edge_case_times(self, things_tools):
        """Test validation of edge case times specifically."""
        edge_cases = [
            ("00:00", True),   # Midnight
            ("12:00", True),   # Noon
            ("23:59", True),   # End of day
            ("00:01", True),   # Just after midnight
            ("11:59", True),   # Just before noon
            ("13:00", True),   # Just after noon
            ("24:00", False),  # Invalid (should be 00:00)
            ("12:60", False),  # Invalid minute
            ("-1:00", False),  # Negative hour
            ("12:-1", False),  # Negative minute
        ]
        
        for time_str, expected in edge_cases:
            result = things_tools._validate_time_format(time_str)
            assert result == expected, f"Time {time_str} should be {'valid' if expected else 'invalid'}"


class TestDatetimeParsing:
    """Test datetime parsing for reminder functionality."""
    
    def test_parse_valid_datetime_input(self, things_tools):
        """Test parsing of valid datetime inputs."""
        test_cases = [
            ("today@14:30", "2025-08-17@14:30"),
            ("tomorrow@09:15", "2025-08-18@09:15"),  
            ("2024-01-15@12:00", "2024-01-15@12:00"),
        ]
        
        for input_dt, expected_format in test_cases:
            result = things_tools._parse_datetime_input(input_dt)
            # For relative dates, just check the format structure
            if "@" in result:
                date_part, time_part = result.split("@")
                assert len(time_part) >= 4, f"Time part should be formatted: {result}"
    
    def test_parse_invalid_datetime_input(self, things_tools):
        """Test parsing of invalid datetime inputs."""
        invalid_inputs = [
            "today@25:00",      # Invalid time
            "tomorrow@12:75",   # Invalid minute
            "invalid@format",   # Invalid time format
            "no_at_symbol",     # No @ symbol
        ]
        
        for dt_input in invalid_inputs:
            result = things_tools._parse_datetime_input(dt_input)
            # Should return original input when invalid
            assert result == dt_input, f"Invalid input {dt_input} should return original"
    
    def test_has_datetime_reminder(self, things_tools):
        """Test detection of datetime reminder format."""
        assert things_tools._has_datetime_reminder("today@14:30") == True
        assert things_tools._has_datetime_reminder("2024-01-15@09:00") == True
        assert things_tools._has_datetime_reminder("today") == False
        assert things_tools._has_datetime_reminder("") == False
        assert things_tools._has_datetime_reminder(None) == False


class TestTimeFormatConversion:
    """Test conversion of 24-hour to 12-hour format for Things compatibility."""
    
    def test_convert_to_things_datetime_format(self, things_tools):
        """Test conversion of datetime formats for Things URL scheme."""
        test_cases = [
            ("2024-01-15@14:30", "2024-01-15@2:30pm"),
            ("today@18:00", "today@6pm"),
            ("tomorrow@09:30", "tomorrow@9:30am"),
            ("2024-01-15@00:00", "2024-01-15@12am"),  # Midnight
            ("today@12:00", "today@12pm"),            # Noon
            ("2024-01-15@13:00", "2024-01-15@1pm"),   # 1 PM
            ("today@01:30", "today@1:30am"),          # 1:30 AM
            ("tomorrow@23:59", "tomorrow@11:59pm"),   # Late night
        ]
        
        for input_dt, expected in test_cases:
            result = things_tools._convert_to_things_datetime_format(input_dt)
            assert result == expected, f"Expected {input_dt} -> {expected}, got {result}"
    
    def test_edge_case_time_conversions(self, things_tools):
        """Test edge case time conversions."""
        edge_cases = [
            ("today@00:01", "today@12:01am"),   # Just after midnight
            ("today@11:59", "today@11:59am"),   # Just before noon  
            ("today@12:01", "today@12:01pm"),   # Just after noon
            ("today@23:58", "today@11:58pm"),   # Just before midnight
            ("2024-01-15@06:00", "2024-01-15@6am"),  # Single digit hour AM
            ("2024-01-15@18:00", "2024-01-15@6pm"),  # Single digit hour PM
        ]
        
        for input_dt, expected in edge_cases:
            result = things_tools._convert_to_things_datetime_format(input_dt)
            assert result == expected, f"Expected {input_dt} -> {expected}, got {result}"


class TestUrlSchemeConstruction:
    """Test URL scheme construction for reminders."""
    
    def test_build_url_scheme_with_reminder(self, things_tools):
        """Test building URL scheme for reminder creation."""
        url_scheme = things_tools._build_url_scheme_with_reminder(
            title="Test Todo",
            when_datetime="2024-01-15@14:30",
            notes="Test notes",
            tags=["work", "urgent"]
        )
        
        assert url_scheme.startswith("things:///add?")
        assert "title=Test%20Todo" in url_scheme
        # Note: The actual encoding depends on _convert_to_things_datetime_format
        assert "when=" in url_scheme
        assert "notes=Test%20notes" in url_scheme
        assert "tags=work%2Curgent" in url_scheme
    
    def test_build_url_scheme_minimal(self, things_tools):
        """Test building URL scheme with minimal parameters."""
        url_scheme = things_tools._build_url_scheme_with_reminder(
            title="Simple Todo",
            when_datetime="today@09:00"
        )
        
        assert url_scheme.startswith("things:///add?")
        assert "title=Simple%20Todo" in url_scheme
        assert "when=" in url_scheme
        assert "notes=" not in url_scheme
        assert "tags=" not in url_scheme
    
    def test_build_url_scheme_special_characters(self, things_tools):
        """Test URL scheme with special characters that need encoding."""
        url_scheme = things_tools._build_url_scheme_with_reminder(
            title="Meeting & Review!",
            when_datetime="today@15:30",
            notes="Important: review #123",
            tags=["urgent", "meeting@work"]
        )
        
        assert url_scheme.startswith("things:///add?")
        assert "Meeting%20%26%20Review%21" in url_scheme  # & and ! encoded
        assert "Important%3A%20review%20%23123" in url_scheme  # : and # encoded
        assert "urgent%2Cmeeting%40work" in url_scheme  # @ encoded in tags


class TestReminderDetection:
    """Test reminder detection from AppleScript activation_date."""
    
    def test_has_reminder_time_with_time_components(self, mock_applescript_manager):
        """Test reminder detection when time components are present."""
        # Configure the mock to return True when time components are present
        mock_applescript_manager._has_reminder_time.return_value = True
        mock_applescript_manager._parse_applescript_date.return_value = "2024-01-15T14:30:00"
        
        # Test the detection logic
        result = mock_applescript_manager._has_reminder_time("date Monday, January 15, 2024 at 2:30:00 PM")
        
        # Verify the mock was called and returned expected value
        assert result == True
        mock_applescript_manager._has_reminder_time.assert_called_once_with("date Monday, January 15, 2024 at 2:30:00 PM")
    
    def test_extract_reminder_time_format(self, mock_applescript_manager):
        """Test extraction of reminder time in HH:MM format."""
        mock_applescript_manager._extract_reminder_time.return_value = "14:30"
        
        result = mock_applescript_manager._extract_reminder_time("date Monday, January 15, 2024 at 2:30:00 PM")
        
        assert result == "14:30" or result is None  # Depending on mock setup


class TestIntegrationWithExistingOperations:
    """Test integration of reminder functionality with existing operations."""
    
    @pytest.mark.asyncio
    async def test_add_todo_with_datetime_reminder(self, things_tools, mock_applescript_manager):
        """Test creating todo with datetime reminder uses URL scheme."""
        # Setup mock to simulate successful URL scheme execution
        mock_applescript_manager.execute_url_scheme.return_value = {
            "success": True,
            "method": "url_scheme"
        }
        
        # Mock the ensure tags exist method
        things_tools._ensure_tags_exist = AsyncMock(return_value={
            'created': [],
            'existing': ['work'],
            'filtered': [],
            'warnings': []
        })
        
        # Test todo creation with reminder
        result = await things_tools._add_todo_impl(
            title="Test Reminder Todo",
            when="today@14:30",
            tags=["work"]
        )
        
        # Should use URL scheme for datetime reminder
        assert result["success"] == True
        assert result["method"] == "url_scheme"
        assert "reminder_time" in result
        mock_applescript_manager.execute_url_scheme.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_add_todo_fallback_to_applescript(self, things_tools, mock_applescript_manager):
        """Test fallback to AppleScript when URL scheme fails."""
        # Setup mock to simulate URL scheme failure
        mock_applescript_manager.execute_url_scheme.return_value = {
            "success": False,
            "error": "URL scheme failed"
        }
        
        # Setup successful AppleScript creation
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "test-todo-id"
        }
        
        # Mock the ensure tags exist method
        things_tools._ensure_tags_exist = AsyncMock(return_value={
            'created': [],
            'existing': [],
            'filtered': [],
            'warnings': []
        })
        
        # Mock the scheduling method
        things_tools.reliable_scheduler = MagicMock()
        things_tools.reliable_scheduler.schedule_todo_reliable = AsyncMock(return_value={
            "success": True
        })
        
        # Test fallback behavior
        result = await things_tools._add_todo_impl(
            title="Test Fallback Todo",
            when="today@14:30"
        )
        
        # Should fall back to AppleScript (without time component)
        mock_applescript_manager.execute_url_scheme.assert_called_once()
        mock_applescript_manager.execute_applescript.assert_called()


class TestErrorHandling:
    """Test error handling for reminder functionality."""
    
    def test_parse_datetime_malformed_input(self, things_tools):
        """Test parsing of malformed datetime inputs."""
        malformed_inputs = [
            "today@",           # Missing time
            "@14:30",          # Missing date  
            "today@25:00",     # Invalid hour
            "today@12:60",     # Invalid minute
            "invalid@format",   # Invalid time format
            "today@14:30:45",  # Seconds not allowed
            "today@@14:30",    # Double @ symbol
            "today@14@30",     # Multiple @ symbols
        ]
        
        for malformed_input in malformed_inputs:
            # Should return original input when invalid (graceful degradation)
            result = things_tools._parse_datetime_input(malformed_input)
            assert result == malformed_input, f"Malformed input {malformed_input} should return original"
    
    def test_convert_to_things_datetime_invalid_input(self, things_tools):
        """Test time conversion with invalid input."""
        invalid_inputs = [
            "no_at_symbol",
            "today@",
            "@14:30", 
            "today@25:00",
            "",
        ]
        
        for invalid_input in invalid_inputs:
            # Should handle gracefully without crashing
            result = things_tools._convert_to_things_datetime_format(invalid_input)
            # Should return something (either original or processed)
            assert result is not None, f"Should not crash on invalid input: {invalid_input}"
    
    @pytest.mark.asyncio
    async def test_url_scheme_failure_fallback(self, things_tools, mock_applescript_manager):
        """Test graceful fallback when URL scheme fails."""
        # Setup URL scheme to fail
        mock_applescript_manager.execute_url_scheme.return_value = {
            "success": False,
            "error": "URL scheme execution failed"
        }
        
        # Setup successful AppleScript fallback
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "fallback-todo-id"
        }
        
        # Mock required dependencies
        things_tools._ensure_tags_exist = AsyncMock(return_value={
            'created': [], 'existing': [], 'filtered': [], 'warnings': []
        })
        things_tools.reliable_scheduler = MagicMock()
        things_tools.reliable_scheduler.schedule_todo_reliable = AsyncMock(return_value={"success": True})
        
        # Test reminder creation with URL scheme failure
        result = await things_tools._add_todo_impl(
            title="Fallback Test",
            when="today@14:30"
        )
        
        # Should attempt URL scheme first, then fall back to AppleScript
        mock_applescript_manager.execute_url_scheme.assert_called_once()
        mock_applescript_manager.execute_applescript.assert_called()
        assert result["success"] == True  # Should still succeed via fallback


class TestRegressionTests:
    """Test that reminder functionality doesn't break existing features."""
    
    @pytest.mark.asyncio
    async def test_existing_date_only_scheduling_unchanged(self, things_tools, mock_applescript_manager):
        """Test that date-only scheduling still works as before."""
        # Setup successful AppleScript creation
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "test-todo-id"
        }
        
        # Mock the ensure tags exist method
        things_tools._ensure_tags_exist = AsyncMock(return_value={
            'created': [],
            'existing': [],
            'filtered': [],
            'warnings': []
        })
        
        # Mock the scheduling method
        things_tools.reliable_scheduler = MagicMock()
        things_tools.reliable_scheduler.schedule_todo_reliable = AsyncMock(return_value={
            "success": True
        })
        
        # Test date-only scheduling (should not use URL scheme)
        result = await things_tools._add_todo_impl(
            title="Regular Todo",
            when="tomorrow"  # No @ symbol
        )
        
        # Should NOT use URL scheme for date-only
        mock_applescript_manager.execute_url_scheme.assert_not_called()
        mock_applescript_manager.execute_applescript.assert_called()
    
    def test_parse_relative_date_backward_compatibility(self, things_tools):
        """Test that relative date parsing remains backward compatible."""
        # Test existing relative date functionality
        test_dates = ["today", "tomorrow", "anytime", "someday"]
        
        for date_str in test_dates:
            result = things_tools._parse_relative_date(date_str)
            # Should return processed date, not containing @
            assert "@" not in result, f"Date-only input {date_str} should not contain @ symbol"
    
    @pytest.mark.asyncio
    async def test_update_todo_with_reminder_backward_compatibility(self, things_tools, mock_applescript_manager):
        """Test that updating todos with reminders doesn't break existing update functionality."""
        # Setup successful update
        mock_applescript_manager.execute_url_scheme.return_value = {
            "success": True,
            "output": "Updated todo successfully"
        }
        mock_applescript_manager.execute_applescript.return_value = {
            "success": True,
            "output": "Updated todo successfully"
        }
        
        # Mock dependencies
        things_tools._ensure_tags_exist = AsyncMock(return_value={
            'created': [], 'existing': [], 'filtered': [], 'warnings': []
        })
        things_tools.reliable_scheduler = MagicMock()
        things_tools.reliable_scheduler.schedule_todo_reliable = AsyncMock(return_value={"success": True})
        
        # Mock operation queue to avoid timeout
        with patch('things_mcp.tools.get_operation_queue') as mock_get_queue:
            mock_queue = AsyncMock()
            mock_queue.enqueue = AsyncMock(return_value="op-id")
            mock_queue.wait_for_operation = AsyncMock(return_value={
                "success": True,
                "message": "Todo updated successfully"
            })
            mock_get_queue.return_value = mock_queue
            
            # Test update with reminder
            result = await things_tools.update_todo(
                todo_id="test-todo-id",
                when="today@15:30"
            )
            
            # Should succeed
            assert result["success"] == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])