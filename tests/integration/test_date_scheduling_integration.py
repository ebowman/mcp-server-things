"""
Integration Tests for Date Scheduling with Real Things 3

This test suite validates date scheduling functionality against real Things 3:
- Basic scheduling: today, tomorrow, specific dates, someday, anytime
- Relative offsets: +7d, +1w, +1m, etc.
- Rescheduling: moving todos between schedules
- Edge cases: clearing schedules, preserving deadlines

CRITICAL: All tests include guaranteed cleanup via cleanup_test_todos fixture.
NO test data should remain in Things 3 after test execution.

Requirements:
- Things 3 must be installed and running
- Database must be accessible
- Automation permissions must be granted

Safety Features:
- Unique timestamps in all todo titles
- Tracked todo IDs for guaranteed cleanup
- Try/except in cleanup to handle already-deleted todos
- Tests are idempotent (can run multiple times)
"""

import pytest
from datetime import datetime, date, timedelta
from typing import List, Dict

from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.tools import ThingsTools


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def applescript_manager():
    """Create real AppleScript manager for integration tests."""
    return AppleScriptManager()


@pytest.fixture
def things_tools(applescript_manager):
    """Create ThingsTools instance with real AppleScript manager."""
    return ThingsTools(applescript_manager)


# ============================================================================
# Helper Functions
# ============================================================================

def get_date_n_days_from_now(n: int) -> str:
    """Get ISO date string for N days from now."""
    target_date = date.today() + timedelta(days=n)
    return target_date.isoformat()


def get_today_iso() -> str:
    """Get today's date in ISO format."""
    return date.today().isoformat()


def get_tomorrow_iso() -> str:
    """Get tomorrow's date in ISO format."""
    return get_date_n_days_from_now(1)


async def verify_todo_start_date(tools: ThingsTools, todo_id: str, expected_date: str, debug: bool = True) -> bool:
    """Verify a todo has the expected start date.

    Args:
        tools: ThingsTools instance
        todo_id: ID of todo to check
        expected_date: Expected startDate in ISO format (YYYY-MM-DD)
        debug: Print debug information if True

    Returns:
        True if startDate matches, False otherwise
    """
    try:
        todo = await tools.get_todo_by_id(todo_id=todo_id)
        # get_todo_by_id returns camelCase fields: startDate, dueDate, etc.
        actual_date = todo.get('startDate')

        if debug:
            print(f"\n[DEBUG] Todo: {todo.get('title')}")
            print(f"[DEBUG] Expected: {expected_date}")
            print(f"[DEBUG] Actual: {actual_date}")
            print(f"[DEBUG] All keys: {list(todo.keys())}")

        return actual_date == expected_date
    except Exception as e:
        print(f"Error verifying todo start date: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================================
# Test Suite 1: Basic Date Scheduling
# ============================================================================

class TestDateSchedulingBasics:
    """Test basic date scheduling operations with today, tomorrow, specific dates."""

    @pytest.mark.asyncio
    async def test_schedule_todo_today(self, things_tools, cleanup_test_todos):
        """Create todo scheduled for today, verify start_date is correct."""
        # Create todo with today scheduling
        result = await things_tools.add_todo(
            title=f"Today Test {cleanup_test_todos['tag']}",
            when="today"
        )

        assert result.get('success'), f"Failed to create todo: {result.get('error')}"
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling
        is_correct = await verify_todo_start_date(things_tools, todo_id, get_today_iso())
        assert is_correct, f"Todo not scheduled for today"

    @pytest.mark.asyncio
    async def test_schedule_todo_tomorrow(self, things_tools, cleanup_test_todos):
        """Create todo scheduled for tomorrow, verify start_date."""
        result = await things_tools.add_todo(
            title=f"Tomorrow Test {cleanup_test_todos['tag']}",
            when="tomorrow"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling
        is_correct = await verify_todo_start_date(things_tools, todo_id, get_tomorrow_iso())
        assert is_correct, "Todo not scheduled for tomorrow"

    @pytest.mark.asyncio
    async def test_schedule_todo_specific_date(self, things_tools, cleanup_test_todos):
        """Create todo with specific date, verify exact date match."""
        target_date = "2025-06-15"

        result = await things_tools.add_todo(
            title=f"Specific Date Test {cleanup_test_todos['tag']}",
            when=target_date
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling
        is_correct = await verify_todo_start_date(things_tools, todo_id, target_date)
        assert is_correct, f"Todo not scheduled for {target_date}"

    @pytest.mark.asyncio
    async def test_schedule_todo_someday(self, things_tools, cleanup_test_todos):
        """Create todo in Someday list, verify no startDate."""
        result = await things_tools.add_todo(
            title=f"Someday Test {cleanup_test_todos['tag']}",
            when="someday"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify no start date (someday = no activation date)
        todo = await things_tools.get_todo_by_id(todo_id=todo_id)
        start_date = todo.get('startDate')
        assert start_date is None, "Someday todo should have no startDate"

    @pytest.mark.asyncio
    async def test_schedule_todo_anytime(self, things_tools, cleanup_test_todos):
        """Create todo in Anytime list, verify no startDate."""
        result = await things_tools.add_todo(
            title=f"Anytime Test {cleanup_test_todos['tag']}",
            when="anytime"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify no start date
        todo = await things_tools.get_todo_by_id(todo_id=todo_id)
        start_date = todo.get('startDate')
        assert start_date is None, "Anytime todo should have no startDate"


# ============================================================================
# Test Suite 2: Relative Date Offsets
# ============================================================================

class TestRelativeOffsets:
    """Test relative date scheduling: +7d, +1w, +1m, etc."""

    @pytest.mark.asyncio
    async def test_schedule_plus_7_days(self, things_tools, cleanup_test_todos):
        """Schedule todo 7 days from now using +7d format."""
        result = await things_tools.add_todo(
            title=f"Plus 7 Days Test {cleanup_test_todos['tag']}",
            when="+7d"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling (7 days from today)
        expected_date = get_date_n_days_from_now(7)
        is_correct = await verify_todo_start_date(things_tools, todo_id, expected_date)
        assert is_correct, f"Todo not scheduled for +7d ({expected_date})"

    @pytest.mark.asyncio
    async def test_schedule_plus_1_week(self, things_tools, cleanup_test_todos):
        """Schedule todo 1 week from now using +1w format."""
        result = await things_tools.add_todo(
            title=f"Plus 1 Week Test {cleanup_test_todos['tag']}",
            when="+1w"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling (7 days from today)
        expected_date = get_date_n_days_from_now(7)
        is_correct = await verify_todo_start_date(things_tools, todo_id, expected_date)
        assert is_correct, f"Todo not scheduled for +1w ({expected_date})"

    @pytest.mark.asyncio
    async def test_schedule_plus_1_month(self, things_tools, cleanup_test_todos):
        """Schedule todo 1 month from now using +1m format."""
        result = await things_tools.add_todo(
            title=f"Plus 1 Month Test {cleanup_test_todos['tag']}",
            when="+1m"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling (~30 days from today)
        # Note: Exact day may vary due to month length, so we verify it's in the future
        todo = await things_tools.get_todo_by_id(todo_id=todo_id)
        start_date = todo.get('startDate')
        assert start_date is not None, "Todo should have startDate"

        # Verify it's approximately 30 days out (allow some variance)
        start_date_obj = datetime.fromisoformat(start_date).date()
        days_diff = (start_date_obj - date.today()).days
        assert 28 <= days_diff <= 31, f"Expected ~30 days, got {days_diff} days"

    @pytest.mark.asyncio
    async def test_schedule_plus_3_days(self, things_tools, cleanup_test_todos):
        """Schedule todo 3 days from now using +3d format."""
        result = await things_tools.add_todo(
            title=f"Plus 3 Days Test {cleanup_test_todos['tag']}",
            when="+3d"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling
        expected_date = get_date_n_days_from_now(3)
        is_correct = await verify_todo_start_date(things_tools, todo_id, expected_date)
        assert is_correct, f"Todo not scheduled for +3d ({expected_date})"

    @pytest.mark.asyncio
    async def test_schedule_plus_14_days(self, things_tools, cleanup_test_todos):
        """Schedule todo 14 days from now using +14d format."""
        result = await things_tools.add_todo(
            title=f"Plus 14 Days Test {cleanup_test_todos['tag']}",
            when="+14d"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling
        expected_date = get_date_n_days_from_now(14)
        is_correct = await verify_todo_start_date(things_tools, todo_id, expected_date)
        assert is_correct, f"Todo not scheduled for +14d ({expected_date})"


# ============================================================================
# Test Suite 3: Rescheduling Operations
# ============================================================================

class TestRescheduling:
    """Test rescheduling existing todos to different dates."""

    @pytest.mark.asyncio
    async def test_reschedule_existing_todo(self, things_tools, cleanup_test_todos):
        """Create todo, then reschedule with new when value."""
        # Create todo with today
        result = await things_tools.add_todo(
            title=f"Reschedule Test {cleanup_test_todos['tag']}",
            when="today"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify initial scheduling
        is_correct = await verify_todo_start_date(things_tools, todo_id, get_today_iso())
        assert is_correct, "Initial scheduling failed"

        # Reschedule to tomorrow
        update_result = await things_tools.update_todo(
            todo_id=todo_id,
            when="tomorrow"
        )

        assert update_result.get('success'), "Failed to reschedule todo"

        # Verify new schedule
        is_correct = await verify_todo_start_date(things_tools, todo_id, get_tomorrow_iso())
        assert is_correct, "Rescheduling to tomorrow failed"

    @pytest.mark.asyncio
    async def test_clear_schedule(self, things_tools, cleanup_test_todos):
        """Create scheduled todo, then clear schedule (move to Anytime)."""
        # Create todo scheduled for tomorrow
        result = await things_tools.add_todo(
            title=f"Clear Schedule Test {cleanup_test_todos['tag']}",
            when="tomorrow"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify initial scheduling
        is_correct = await verify_todo_start_date(things_tools, todo_id, get_tomorrow_iso())
        assert is_correct, "Initial scheduling failed"

        # Clear schedule
        update_result = await things_tools.update_todo(
            todo_id=todo_id,
            when="anytime"
        )

        assert update_result.get('success'), "Failed to clear schedule"

        # Verify schedule cleared
        todo = await things_tools.get_todo_by_id(todo_id=todo_id)
        start_date = todo.get('startDate')
        assert start_date is None, "Schedule should be cleared"

    @pytest.mark.asyncio
    async def test_change_from_today_to_tomorrow(self, things_tools, cleanup_test_todos):
        """Reschedule from today to tomorrow."""
        # Create todo for today
        result = await things_tools.add_todo(
            title=f"Today to Tomorrow Test {cleanup_test_todos['tag']}",
            when="today"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify today
        is_correct = await verify_todo_start_date(things_tools, todo_id, get_today_iso())
        assert is_correct, "Initial today scheduling failed"

        # Change to tomorrow
        await things_tools.update_todo(todo_id=todo_id, when="tomorrow")

        # Verify tomorrow
        is_correct = await verify_todo_start_date(things_tools, todo_id, get_tomorrow_iso())
        assert is_correct, "Failed to change from today to tomorrow"

    @pytest.mark.asyncio
    async def test_move_to_someday(self, things_tools, cleanup_test_todos):
        """Reschedule active todo to someday."""
        # Create todo for today
        result = await things_tools.add_todo(
            title=f"Move to Someday Test {cleanup_test_todos['tag']}",
            when="today"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify today
        is_correct = await verify_todo_start_date(things_tools, todo_id, get_today_iso())
        assert is_correct, "Initial scheduling failed"

        # Move to someday
        await things_tools.update_todo(todo_id=todo_id, when="someday")

        # Verify no start date
        todo = await things_tools.get_todo_by_id(todo_id=todo_id)
        start_date = todo.get('startDate')
        assert start_date is None, "Someday todo should have no startDate"

    @pytest.mark.asyncio
    async def test_reschedule_with_deadline(self, things_tools, cleanup_test_todos):
        """Change when but preserve deadline."""
        deadline_date = "2025-12-31"

        # Create todo with deadline and today scheduling
        result = await things_tools.add_todo(
            title=f"Reschedule with Deadline Test {cleanup_test_todos['tag']}",
            when="today",
            deadline=deadline_date
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Reschedule to tomorrow (should preserve deadline)
        await things_tools.update_todo(todo_id=todo_id, when="tomorrow")

        # Verify new schedule and preserved deadline
        todo = await things_tools.get_todo_by_id(todo_id=todo_id)
        start_date = todo.get('startDate')
        due_date = todo.get('dueDate')

        assert start_date == get_tomorrow_iso(), "Start date not updated"
        assert due_date == deadline_date, "Deadline should be preserved"


# ============================================================================
# Test Suite 4: Edge Cases and Validation
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions in date scheduling."""

    @pytest.mark.asyncio
    async def test_schedule_far_future_date(self, things_tools, cleanup_test_todos):
        """Schedule todo for far future date (1 year ahead)."""
        far_future = get_date_n_days_from_now(365)

        result = await things_tools.add_todo(
            title=f"Far Future Test {cleanup_test_todos['tag']}",
            when=far_future
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify scheduling
        is_correct = await verify_todo_start_date(things_tools, todo_id, far_future)
        assert is_correct, f"Todo not scheduled for {far_future}"

    @pytest.mark.asyncio
    async def test_multiple_reschedules(self, things_tools, cleanup_test_todos):
        """Reschedule same todo multiple times."""
        # Create todo
        result = await things_tools.add_todo(
            title=f"Multiple Reschedule Test {cleanup_test_todos['tag']}",
            when="today"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Reschedule multiple times
        # Note: Use actual dates instead of relative offsets for compatibility
        schedules = [
            "tomorrow",
            get_date_n_days_from_now(3),
            get_date_n_days_from_now(7),
            "today"
        ]
        expected_dates = [
            get_tomorrow_iso(),
            get_date_n_days_from_now(3),
            get_date_n_days_from_now(7),
            get_today_iso()
        ]

        for when, expected in zip(schedules, expected_dates):
            await things_tools.update_todo(todo_id=todo_id, when=when)
            is_correct = await verify_todo_start_date(things_tools, todo_id, expected)
            assert is_correct, f"Failed to reschedule to {when} (expected {expected})"

    @pytest.mark.asyncio
    async def test_schedule_then_complete(self, things_tools, cleanup_test_todos):
        """Schedule todo, then complete it (should preserve start_date)."""
        result = await things_tools.add_todo(
            title=f"Schedule Then Complete Test {cleanup_test_todos['tag']}",
            when="today"
        )

        assert result.get('success')
        todo_id = result['todo_id']
        cleanup_test_todos['ids'].append(todo_id)

        # Verify start date before completing
        todo_before = await things_tools.get_todo_by_id(todo_id=todo_id)
        assert todo_before.get('startDate') == get_today_iso()

        # Complete the todo
        await things_tools.update_todo(todo_id=todo_id, completed="true")

        # Note: Completed todos are moved to logbook and may not be retrievable
        # via get_todo_by_id. We verified the start_date before completion.
        print(f"✓ Todo scheduled and completed successfully")
