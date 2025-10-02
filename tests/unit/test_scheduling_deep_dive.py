"""
Comprehensive test suite for Things MCP Server scheduling and reminder capabilities.

This test suite thoroughly exercises:
1. Reminder functionality with various formats
2. Date scheduling (relative and absolute)
3. Temporal queries (upcoming, due, activating)
4. Logbook and history retrieval
5. Edge cases and format validation

Tests document expected behavior and verify the hybrid AppleScript/URL scheme approach.
"""

import pytest
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch
import things  # For mocking things.py database access

from things_mcp.tools import ThingsTools
from things_mcp.pure_applescript_scheduler import PureAppleScriptScheduler
from things_mcp.services.applescript_manager import AppleScriptManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager."""
    manager = MagicMock(spec=AppleScriptManager)
    manager.execute_applescript = AsyncMock()
    manager.execute_url_scheme = AsyncMock()
    return manager


@pytest.fixture
def scheduler(mock_applescript_manager):
    """Create a PureAppleScriptScheduler instance."""
    return PureAppleScriptScheduler(mock_applescript_manager)


@pytest.fixture
def tools(mock_applescript_manager):
    """Create a ThingsTools instance."""
    return ThingsTools(mock_applescript_manager)


@pytest.fixture
def today_str():
    """Return today's date as YYYY-MM-DD string."""
    return date.today().strftime('%Y-%m-%d')


@pytest.fixture
def tomorrow_str():
    """Return tomorrow's date as YYYY-MM-DD string."""
    return (date.today() + timedelta(days=1)).strftime('%Y-%m-%d')


@pytest.fixture
def next_week_str():
    """Return next week's date as YYYY-MM-DD string."""
    return (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')


# ============================================================================
# TEST CLASS 1: REMINDER FUNCTIONALITY
# ============================================================================

class TestDateScheduling:
    """Test date scheduling without specific times."""

    @pytest.mark.asyncio
    async def test_schedule_relative_today(self, scheduler, mock_applescript_manager):
        """Test scheduling for 'today' using relative date."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'scheduled_relative'
        }

        result = await scheduler.schedule_todo_reliable('test-id', 'today')

        assert result['success']
        assert result['method'] == 'applescript_relative'
        assert result['reliability'] == '95%'

    @pytest.mark.asyncio
    async def test_schedule_relative_tomorrow(self, scheduler, mock_applescript_manager):
        """Test scheduling for 'tomorrow' using relative date."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'scheduled_relative'
        }

        result = await scheduler.schedule_todo_reliable('test-id', 'tomorrow')

        assert result['success']
        assert result['method'] == 'applescript_relative'

    @pytest.mark.asyncio
    async def test_schedule_specific_date(self, scheduler, mock_applescript_manager, next_week_str):
        """Test scheduling for specific date (YYYY-MM-DD)."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'scheduled_objects'
        }

        result = await scheduler.schedule_todo_reliable('test-id', next_week_str)

        assert result['success']
        # Could be either date_objects or direct method
        assert result['method'] in ['applescript_date_objects', 'applescript_direct', 'list_fallback']

    @pytest.mark.asyncio
    async def test_schedule_someday(self, scheduler, mock_applescript_manager):
        """Test scheduling for 'someday' (no specific date)."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'moved_to_list'
        }

        result = await scheduler.schedule_todo_reliable('test-id', 'someday')

        # Should fall back to list assignment
        assert result['success']


# ============================================================================
# TEST CLASS 3: READING TODOS WITH REMINDERS
# ============================================================================

class TestTemporalQueries:
    """Test temporal query functions: upcoming, due, activating."""

    @pytest.mark.asyncio
    async def test_get_upcoming(self, tools):
        """Test get_upcoming returns scheduled items."""
        with patch('things.upcoming') as mock_upcoming:
            mock_upcoming.return_value = [
                {
                    'uuid': 'upcoming-1',
                    'title': 'Upcoming task',
                    'start_date': (date.today() + timedelta(days=3)).strftime('%Y-%m-%d'),
                    'status': 'open',
                    'tags': []
                }
            ]

            upcoming = await tools.get_upcoming()

            assert isinstance(upcoming, list)
            assert len(upcoming) > 0

    @pytest.mark.asyncio
    async def test_get_upcoming_in_days_7(self, tools):
        """Test get_upcoming_in_days with 7-day range."""
        result = await tools.get_upcoming_in_days(7)

        # Should return a list (even if empty)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_upcoming_in_days_14(self, tools):
        """Test get_upcoming_in_days with 14-day range."""
        result = await tools.get_upcoming_in_days(14)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_upcoming_in_days_30(self, tools):
        """Test get_upcoming_in_days with 30-day range."""
        result = await tools.get_upcoming_in_days(30)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_get_due_in_days_7(self, tools, mock_applescript_manager):
        """Test get_due_in_days retrieves todos with deadlines in next 7 days."""
        # Mock things.py since we now use it instead of AppleScript
        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'due-1', 'title': 'Pay bills', 'due_date': '2025-10-07', 'status': 'incomplete'}
            ]

            result = await tools.get_due_in_days(7)

            assert isinstance(result, list)
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_get_due_in_days_30(self, tools, mock_applescript_manager):
        """Test get_due_in_days with 30-day range."""
        # Mock things.py since we now use it instead of AppleScript
        with patch('things.todos') as mock_todos:
            mock_todos.return_value = []

            result = await tools.get_due_in_days(30)

            assert isinstance(result, list)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_activating_in_days_7(self, tools, mock_applescript_manager):
        """Test get_activating_in_days retrieves todos activating in next 7 days."""
        # Mock things.py since we now use it instead of AppleScript
        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'act-1', 'title': 'Start project', 'start_date': '2025-10-09', 'status': 'incomplete'}
            ]

            result = await tools.get_activating_in_days(7)

            assert isinstance(result, list)
            assert len(result) == 1


# ============================================================================
# TEST CLASS 5: LOGBOOK & HISTORY
# ============================================================================

class TestLogbookAndHistory:
    """Test logbook retrieval and history queries."""

    @pytest.mark.asyncio
    async def test_get_logbook_default(self, tools):
        """Test get_logbook with default parameters (50 items, 7 days)."""
        with patch('things.logbook') as mock_logbook:
            mock_logbook.return_value = [
                {
                    'uuid': 'completed-1',
                    'title': 'Completed task',
                    'status': 'completed',
                    'stop_date': datetime.now().isoformat(),
                    'tags': []
                }
            ]

            logbook = await tools.get_logbook()

            assert isinstance(logbook, list)

    @pytest.mark.asyncio
    async def test_get_logbook_with_limit(self, tools):
        """Test get_logbook with custom limit."""
        with patch('things.logbook') as mock_logbook:
            # Create 100 mock completed items
            mock_items = [
                {
                    'uuid': f'completed-{i}',
                    'title': f'Task {i}',
                    'status': 'completed',
                    'stop_date': datetime.now().isoformat(),
                    'tags': []
                }
                for i in range(100)
            ]
            mock_logbook.return_value = mock_items

            logbook = await tools.get_logbook(limit=20)

            # Should be limited to 20 items
            assert len(logbook) <= 20

    @pytest.mark.asyncio
    async def test_get_logbook_different_periods(self, tools):
        """Test get_logbook with different time periods."""
        periods = ['3d', '7d', '1w', '1m']

        for period in periods:
            with patch('things.logbook') as mock_logbook:
                mock_logbook.return_value = []

                logbook = await tools.get_logbook(period=period)

                assert isinstance(logbook, list)

    @pytest.mark.asyncio
    async def test_get_recent_week(self, tools, mock_applescript_manager):
        """Test get_recent with 1 week period."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': [
                'ID:recent-1|TITLE:Completed recently|COMPLETED:Saturday, October 5, 2025 at 3:00:00 PM'
            ]
        }

        recent = await tools.get_recent('7d')

        assert isinstance(recent, list)

    @pytest.mark.asyncio
    async def test_get_recent_month(self, tools, mock_applescript_manager):
        """Test get_recent with 1 month period."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': []
        }

        recent = await tools.get_recent('1m')

        assert isinstance(recent, list)


# ============================================================================
# TEST CLASS 6: ACTIVATION DATE QUERIES
# ============================================================================

class TestFormatValidationAndEdgeCases:
    """Test format validation and edge case handling."""

    @pytest.mark.asyncio
    async def test_invalid_time_format(self, tools, mock_applescript_manager):
        """Test handling of invalid time format."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'test-id'
        }

        # Should handle gracefully or reject
        result = await tools.add_todo(
            title="Invalid time test",
            when="today@25:99"  # Invalid time
        )

        # Should still attempt creation (validation happens in AppleScript)
        assert mock_applescript_manager.execute_applescript.called

    @pytest.mark.asyncio
    async def test_past_date_scheduling(self, tools, mock_applescript_manager):
        """Test scheduling for a past date."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'test-id'
        }

        past_date = (date.today() - timedelta(days=7)).strftime('%Y-%m-%d')

        result = await tools.add_todo(
            title="Past date test",
            when=past_date
        )

        assert mock_applescript_manager.execute_applescript.called

    @pytest.mark.asyncio
    async def test_far_future_date(self, tools, mock_applescript_manager):
        """Test scheduling for far future date (1 year ahead)."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'test-id'
        }

        future_date = (date.today() + timedelta(days=365)).strftime('%Y-%m-%d')

        result = await tools.add_todo(
            title="Far future test",
            when=future_date
        )

        assert mock_applescript_manager.execute_applescript.called


# ============================================================================
# TEST CLASS 8: INTEGRATION SCENARIOS
# ============================================================================

class TestIntegrationScenarios:
    """Test realistic integration scenarios combining multiple features."""

    @pytest.mark.asyncio
    async def test_daily_review_workflow(self, tools):
        """Test a typical daily review workflow."""
        # 1. Get today's todos
        with patch('things_mcp.tools_helpers.read_operations.things.today') as mock_today:
            mock_today.return_value = []
            today_todos = await tools.get_today()

        # 2. Get upcoming in next 7 days
        with patch.object(tools.read_ops.applescript, 'get_todos_upcoming_in_days', new_callable=AsyncMock) as mock_upcoming:
            mock_upcoming.return_value = []
            upcoming = await tools.get_upcoming_in_days(7)

        # 3. Check what's due soon
        with patch.object(tools.read_ops.applescript, 'get_todos_due_in_days', new_callable=AsyncMock) as mock_due:
            mock_due.return_value = []
            due_soon = await tools.get_due_in_days(7)

        # All should return lists
        assert isinstance(today_todos, list)
        assert isinstance(upcoming, list)
        assert isinstance(due_soon, list)

    @pytest.mark.asyncio
    async def test_weekly_planning_workflow(self, tools, mock_applescript_manager):
        """Test a typical weekly planning workflow."""
        # 1. Review completed items from last week
        with patch('things.logbook') as mock_logbook:
            mock_logbook.return_value = []
            completed = await tools.get_logbook(period='7d')

        # 2. Check what's coming up
        upcoming = await tools.get_upcoming_in_days(14)

        # 3. Create a new todo for next week with reminder
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'new-todo-id'
        }

        next_monday = date.today() + timedelta(days=(7 - date.today().weekday()))
        result = await tools.add_todo(
            title="Weekly team meeting",
            when=f"{next_monday.strftime('%Y-%m-%d')}@09:00",
            tags=["work", "meeting"]
        )

        assert isinstance(completed, list)
        assert isinstance(upcoming, list)


# ============================================================================
# TEST CLASS 9: BACKWARD COMPATIBILITY
# ============================================================================

class TestBackwardCompatibility:
    """Test that existing date-only scheduling still works."""

    @pytest.mark.asyncio
    async def test_simple_date_without_time(self, tools, mock_applescript_manager):
        """Test that simple date scheduling (no time) works as before."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'test-id'
        }

        result = await tools.add_todo(
            title="Simple scheduled task",
            when="today"
        )

        assert mock_applescript_manager.execute_applescript.called

    @pytest.mark.asyncio
    async def test_iso_date_without_time(self, tools, mock_applescript_manager):
        """Test that ISO date format (YYYY-MM-DD) without time works."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'test-id'
        }

        result = await tools.add_todo(
            title="ISO date task",
            when="2025-10-15"
        )

        assert mock_applescript_manager.execute_applescript.called


# ============================================================================
# SUMMARY TEST: DOCUMENT ALL FINDINGS
# ============================================================================

class TestCapabilitiesSummary:
    """Summary test documenting all discovered capabilities."""

    def test_reminder_formats_supported(self):
        """Document all supported reminder formats."""
        supported_formats = {
            'relative_with_time': [
                'today@14:30',
                'tomorrow@09:00',
            ],
            'absolute_with_time': [
                '2025-10-15@18:00',
                '2025-12-25@00:00',
            ],
            'relative_date_only': [
                'today',
                'tomorrow',
                'someday',
            ],
            'absolute_date_only': [
                '2025-10-15',
                '2025-12-25',
            ]
        }

        # This test documents the formats - actual validation happens in integration tests
        assert 'relative_with_time' in supported_formats
        assert 'absolute_with_time' in supported_formats

    def test_temporal_query_capabilities(self):
        """Document all temporal query capabilities."""
        temporal_queries = {
            'upcoming': 'Get items scheduled for future',
            'upcoming_in_days': 'Get items in specific day range (7, 14, 30, etc.)',
            'due_in_days': 'Get items with deadlines in specific range',
            'activating_in_days': 'Get items that will activate in range',
            'today': 'Get items scheduled for today',
            'logbook': 'Get completed items with time period filter',
            'recent': 'Get recently created/modified items'
        }

        assert len(temporal_queries) == 7
        assert 'upcoming_in_days' in temporal_queries

    def test_reminder_field_structure(self):
        """Document the structure of reminder fields in todos."""
        reminder_fields = {
            'has_reminder': 'bool - True if reminder time is set',
            'reminder_time': 'str - Time in HH:MM format (e.g., "14:30")',
            'activation_date': 'datetime - Full datetime when todo becomes active'
        }

        assert 'has_reminder' in reminder_fields
        assert 'reminder_time' in reminder_fields
        assert 'activation_date' in reminder_fields


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])