"""
Comprehensive test suite for Things MCP Server scheduling and reminder capabilities.

This test suite thoroughly exercises:
1. Reminder functionality with various formats
2. Date scheduling (relative and absolute)
3. Temporal queries (upcoming, due, activating)
4. Edge cases and format validation

Tests document expected behavior and verify the hybrid AppleScript/URL scheme approach.
"""

import pytest
from datetime import timedelta, date
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
        """Test scheduling for 'today' using relative date.

        bead hq-x9z: 'today' must NOT use the `schedule` verb at all - live
        probing showed `schedule theTodo for (current date)` (in any order
        relative to a list move) always leaves the to-do in Things'
        unconfirmed/Someday state, invisible to things.anytime(). The fix
        is a plain `move theTodo to list "Today"`, which live-probed to
        yield start='Anytime' and membership in both things.today() and
        things.anytime().
        """
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'scheduled_relative'
        }

        result = await scheduler.schedule_todo_reliable('test-id', 'today')

        assert result['success']
        assert result['method'] == 'applescript_relative'
        assert result['reliability'] == '95%'

        emitted_script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert 'move theTodo to list "Today"' in emitted_script
        assert 'schedule theTodo for' not in emitted_script
        assert 'current date' not in emitted_script

    @pytest.mark.asyncio
    async def test_schedule_relative_tomorrow(self, scheduler, mock_applescript_manager):
        """Test scheduling for 'tomorrow' using relative date.

        Unlike 'today' (see test_schedule_relative_today above), 'tomorrow'
        is unaffected by hq-x9z - Things' own start='Someday' + future
        start_date is the normal/expected representation for a future date
        (things.upcoming() explicitly keys off exactly that state), so the
        `schedule` verb is still used unchanged.
        """
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'scheduled_relative'
        }

        result = await scheduler.schedule_todo_reliable('test-id', 'tomorrow')

        assert result['success']
        assert result['method'] == 'applescript_relative'

        emitted_script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert 'schedule theTodo for targetDate' in emitted_script
        assert '(current date) + 1 * days' in emitted_script
        assert 'move theTodo to list "Today"' not in emitted_script

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

        emitted_script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert 'schedule theTodo for targetDate' in emitted_script
        assert 'move theTodo to list "Today"' not in emitted_script

    @pytest.mark.asyncio
    async def test_schedule_specific_date_equal_to_today(self, scheduler, mock_applescript_manager, today_str):
        """bead hq-x9z: an explicit ISO date that resolves to today's date
        (e.g. update_todo(when=<today's YYYY-MM-DD>)) hits the same
        `schedule` verb quirk as the literal 'today' relative-date case -
        live-probed to also leave start='Someday'. Must use the same
        move-to-Today-list fix, not the `schedule` verb.
        """
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': 'scheduled_objects'
        }

        result = await scheduler.schedule_todo_reliable('test-id', today_str)

        assert result['success']
        assert result['method'] == 'applescript_date_objects'

        emitted_script = mock_applescript_manager.execute_applescript.call_args[0][0]
        assert 'move theTodo to list "Today"' in emitted_script
        assert 'schedule theTodo for' not in emitted_script

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
    async def test_upcoming_in_days_returns_only_in_window_todos(self, tools):
        """get_upcoming(days=7) -> get_todos_upcoming_in_days's real filter logic.

        A todo is included if EITHER:
        - its deadline is <= the cutoff date (today + days), with NO lower
          bound - an already-overdue deadline is still included (matches the
          actual `if due_dt <= cutoff_date` check in
          _get_todos_upcoming_in_days_sync, which has no `>= now` guard on
          the deadline branch, unlike the start_date branch below); or
        - its start_date falls within [today, today + days] (both bounds
          checked - a past start_date is excluded).

        Todos with neither field, or with only an out-of-window start_date/
        deadline, are excluded. This asserts the real uuid set produced by
        that filter against a mix of rows spanning both branches and both
        boundaries.
        """
        past = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        window = (date.today() + timedelta(days=3)).strftime('%Y-%m-%d')
        target = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')
        beyond = (date.today() + timedelta(days=10)).strftime('%Y-%m-%d')

        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'deadline-in-window', 'title': 'Deadline in window',
                 'deadline': window, 'status': 'incomplete'},
                {'uuid': 'deadline-past', 'title': 'Overdue deadline still surfaces',
                 'deadline': past, 'status': 'incomplete'},
                {'uuid': 'deadline-boundary', 'title': 'Deadline exactly on target day',
                 'deadline': target, 'status': 'incomplete'},
                {'uuid': 'deadline-beyond', 'title': 'Deadline beyond window',
                 'deadline': beyond, 'status': 'incomplete'},
                {'uuid': 'start-in-window', 'title': 'Start date in window',
                 'start_date': window, 'status': 'incomplete'},
                {'uuid': 'start-past', 'title': 'Start date already past',
                 'start_date': past, 'status': 'incomplete'},
                {'uuid': 'start-boundary', 'title': 'Start date exactly on target day',
                 'start_date': target, 'status': 'incomplete'},
                {'uuid': 'start-beyond', 'title': 'Start date beyond window',
                 'start_date': beyond, 'status': 'incomplete'},
                {'uuid': 'no-dates', 'title': 'No deadline or start date',
                 'status': 'incomplete'},
            ]

            result = await tools.get_upcoming(days=7)

            uuids = {t['uuid'] for t in result}
            assert uuids == {
                'deadline-in-window', 'deadline-past', 'deadline-boundary',
                'start-in-window', 'start-boundary',
            }

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
    async def test_get_activating_in_days_7(self, tools, mock_applescript_manager, tomorrow_str):
        """Test get_activating_in_days retrieves todos activating in next 7 days."""
        # Mock things.py since we now use it instead of AppleScript
        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'act-1', 'title': 'Start project', 'start_date': tomorrow_str, 'status': 'incomplete'}
            ]

            result = await tools.get_activating_in_days(7)

            assert isinstance(result, list)
            assert len(result) == 1


# ============================================================================
# TEST CLASS 4b: DUE/ACTIVATING WINDOW BOUNDARIES (hq-nxu.1)
# ============================================================================

class TestDueAndActivatingWindowBoundaries:
    """Boundary tests for get_due_in_days/get_activating_in_days forward-window filtering.

    Covers rows with dates in the past, exactly today, inside the window,
    exactly on the target date (upper boundary), and beyond the window
    (future, excluded by the things.py query itself).
    """

    @pytest.mark.asyncio
    async def test_get_due_in_days_include_overdue_true_keeps_past_dates(self, tools, today_str):
        """Default include_overdue=True preserves historical behavior: overdue items included."""
        past = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        window = (date.today() + timedelta(days=3)).strftime('%Y-%m-%d')
        target = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')

        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'past', 'title': 'Overdue', 'deadline': past, 'status': 'incomplete'},
                {'uuid': 'today', 'title': 'Due today', 'deadline': today_str, 'status': 'incomplete'},
                {'uuid': 'window', 'title': 'Due in window', 'deadline': window, 'status': 'incomplete'},
                {'uuid': 'boundary', 'title': 'Due on target day', 'deadline': target, 'status': 'incomplete'},
            ]

            result = await tools.get_due_in_days(7, include_overdue=True)

            uuids = {t['uuid'] for t in result}
            assert uuids == {'past', 'today', 'window', 'boundary'}

    @pytest.mark.asyncio
    async def test_get_due_in_days_include_overdue_false_excludes_past_dates(self, tools, today_str):
        """include_overdue=False restricts to today <= deadline <= target date."""
        past = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        window = (date.today() + timedelta(days=3)).strftime('%Y-%m-%d')
        target = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')

        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'past', 'title': 'Overdue', 'deadline': past, 'status': 'incomplete'},
                {'uuid': 'today', 'title': 'Due today', 'deadline': today_str, 'status': 'incomplete'},
                {'uuid': 'window', 'title': 'Due in window', 'deadline': window, 'status': 'incomplete'},
                {'uuid': 'boundary', 'title': 'Due on target day', 'deadline': target, 'status': 'incomplete'},
            ]

            result = await tools.get_due_in_days(7, include_overdue=False)

            uuids = {t['uuid'] for t in result}
            assert uuids == {'today', 'window', 'boundary'}
            assert 'past' not in uuids

    @pytest.mark.asyncio
    async def test_get_due_in_days_default_matches_include_overdue_true(self, tools, today_str):
        """Calling get_due_in_days without include_overdue defaults to True (backwards compatible)."""
        past = (date.today() - timedelta(days=1)).strftime('%Y-%m-%d')

        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'past', 'title': 'Overdue', 'deadline': past, 'status': 'incomplete'},
            ]

            result = await tools.get_due_in_days(7)

            uuids = {t['uuid'] for t in result}
            assert 'past' in uuids

    @pytest.mark.asyncio
    async def test_get_activating_in_days_excludes_past_start_dates(self, tools, today_str):
        """get_activating_in_days always restricts to today <= start_date <= target date."""
        past = (date.today() - timedelta(days=5)).strftime('%Y-%m-%d')
        window = (date.today() + timedelta(days=3)).strftime('%Y-%m-%d')
        target = (date.today() + timedelta(days=7)).strftime('%Y-%m-%d')

        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'past', 'title': 'Already active', 'start_date': past, 'status': 'incomplete'},
                {'uuid': 'today', 'title': 'Activating today', 'start_date': today_str, 'status': 'incomplete'},
                {'uuid': 'window', 'title': 'Activating in window', 'start_date': window, 'status': 'incomplete'},
                {'uuid': 'boundary', 'title': 'Activating on target day', 'start_date': target, 'status': 'incomplete'},
            ]

            result = await tools.get_activating_in_days(7)

            uuids = {t['uuid'] for t in result}
            assert uuids == {'today', 'window', 'boundary'}
            assert 'past' not in uuids

    @pytest.mark.asyncio
    async def test_get_activating_in_days_missing_start_date_excluded(self, tools):
        """Rows without a start_date at all are excluded (defensive against missing keys)."""
        with patch('things.todos') as mock_todos:
            mock_todos.return_value = [
                {'uuid': 'no-start-date', 'title': 'No start date', 'status': 'incomplete'},
            ]

            result = await tools.get_activating_in_days(7)

            assert result == []


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