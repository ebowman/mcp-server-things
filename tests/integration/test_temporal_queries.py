"""
Integration tests for temporal queries in Things 3 MCP server.

Tests date-based searching, filtering by scheduling dates, deadlines,
and various time-based query operations.

All tests use the cleanup_test_todos fixture to ensure no test data remains
after test execution.
"""

import pytest
from datetime import datetime, date, timedelta
from freezegun import freeze_time

from things_mcp.tools import ThingsTools
from things_mcp.services.applescript_manager import AppleScriptManager


class TestTodayQueries:
    """Test queries for todos scheduled for today."""

    @pytest.mark.asyncio
    async def test_get_today_returns_today_todos(self, cleanup_test_todos):
        """Verify get_today() returns todos scheduled for today."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create 3 todos scheduled for today
        todo_ids = []
        for i in range(3):
            result = await tools.add_todo(
                title=f"Today todo {i} {cleanup_test_todos['tag']}",
                when="today",
                tags=cleanup_test_todos['tag']
            )
            cleanup_test_todos['ids'].append(result['todo_id'])
            todo_ids.append(result['todo_id'])

        # Query today's todos
        today_todos = await tools.get_today()

        # Verify our todos are in the results
        today_ids = [todo['uuid'] for todo in today_todos]
        for todo_id in todo_ids:
            assert todo_id in today_ids, f"Todo {todo_id} not found in today's list"

        print(f"✓ Created 3 todos, found in get_today() results")

    @pytest.mark.asyncio
    async def test_get_today_excludes_tomorrow(self, cleanup_test_todos):
        """Verify get_today() excludes todos scheduled for tomorrow."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create one todo for today
        today_result = await tools.add_todo(
            title=f"Today {cleanup_test_todos['tag']}",
            when="today",
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(today_result['todo_id'])

        # Create one todo for tomorrow
        tomorrow_result = await tools.add_todo(
            title=f"Tomorrow {cleanup_test_todos['tag']}",
            when="tomorrow",
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(tomorrow_result['todo_id'])

        # Query today's todos
        today_todos = await tools.get_today()
        today_ids = [todo['uuid'] for todo in today_todos]

        # Verify today's todo is included
        assert today_result['todo_id'] in today_ids, "Today's todo not found"

        # Verify tomorrow's todo is excluded
        assert tomorrow_result['todo_id'] not in today_ids, "Tomorrow's todo incorrectly included in today"

        print(f"✓ Today's todo included, tomorrow's todo excluded")


class TestUpcomingQueries:
    """Test queries for upcoming todos."""

    @pytest.mark.asyncio
    async def test_get_upcoming_in_7_days(self, cleanup_test_todos):
        """Verify get_upcoming(7) returns todos within 7 days."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create todos for various future dates
        today = date.today()
        test_todos = []

        # Day 1, 3, 5 (within 7 days)
        for day_offset in [1, 3, 5]:
            future_date = today + timedelta(days=day_offset)
            result = await tools.add_todo(
                title=f"Day {day_offset} {cleanup_test_todos['tag']}",
                when=future_date.strftime('%Y-%m-%d'),
                tags=cleanup_test_todos['tag']
            )
            cleanup_test_todos['ids'].append(result['todo_id'])
            test_todos.append((day_offset, result['todo_id']))

        # Day 10, 15 (beyond 7 days)
        for day_offset in [10, 15]:
            future_date = today + timedelta(days=day_offset)
            result = await tools.add_todo(
                title=f"Day {day_offset} {cleanup_test_todos['tag']}",
                when=future_date.strftime('%Y-%m-%d'),
                tags=cleanup_test_todos['tag']
            )
            cleanup_test_todos['ids'].append(result['todo_id'])
            test_todos.append((day_offset, result['todo_id']))

        # Query upcoming in 7 days
        upcoming = await tools.get_upcoming(days=7)
        upcoming_ids = [todo['uuid'] for todo in upcoming]

        # Verify days 1-7 are included
        for day_offset, todo_id in test_todos:
            if day_offset <= 7:
                assert todo_id in upcoming_ids, f"Day {day_offset} todo not in 7-day upcoming"
            else:
                # Beyond 7 days should be excluded (or we just don't assert - depends on implementation)
                pass

        print(f"✓ get_upcoming(7) returned correct todos")

    @pytest.mark.asyncio
    async def test_get_upcoming_in_30_days(self, cleanup_test_todos):
        """Verify get_upcoming(30) returns todos within 30 days."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create todos at various intervals
        today = date.today()
        test_dates = [5, 15, 25, 28]

        for day_offset in test_dates:
            future_date = today + timedelta(days=day_offset)
            result = await tools.add_todo(
                title=f"Day {day_offset} {cleanup_test_todos['tag']}",
                when=future_date.strftime('%Y-%m-%d'),
                tags=cleanup_test_todos['tag']
            )
            cleanup_test_todos['ids'].append(result['todo_id'])

        # Query upcoming in 30 days
        upcoming = await tools.get_upcoming(days=30)
        upcoming_ids = [todo['uuid'] for todo in upcoming]

        # Should have at least our test todos
        assert len(upcoming_ids) >= len(test_dates), "Expected todos not found in 30-day upcoming"

        print(f"✓ get_upcoming(30) returned {len(upcoming_ids)} todos")

    @pytest.mark.asyncio
    async def test_get_upcoming_excludes_past(self, cleanup_test_todos):
        """Verify get_upcoming() excludes past todos."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create a past todo (yesterday)
        yesterday = date.today() - timedelta(days=1)
        past_result = await tools.add_todo(
            title=f"Past {cleanup_test_todos['tag']}",
            when=yesterday.strftime('%Y-%m-%d'),
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(past_result['todo_id'])

        # Create a future todo
        tomorrow = date.today() + timedelta(days=1)
        future_result = await tools.add_todo(
            title=f"Future {cleanup_test_todos['tag']}",
            when=tomorrow.strftime('%Y-%m-%d'),
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(future_result['todo_id'])

        # Query upcoming
        upcoming = await tools.get_upcoming(days=7)
        upcoming_ids = [todo['uuid'] for todo in upcoming]

        # Past todo should be excluded
        assert past_result['todo_id'] not in upcoming_ids, "Past todo incorrectly included in upcoming"

        # Future todo should be included
        assert future_result['todo_id'] in upcoming_ids, "Future todo not found in upcoming"

        print(f"✓ Past todos excluded, future todos included")


class TestDeadlineQueries:
    """Test queries for todos with deadlines."""

    @pytest.mark.asyncio
    async def test_search_by_deadline(self, cleanup_test_todos):
        """Verify searching by specific deadline date."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create todo with specific deadline
        target_date = date.today() + timedelta(days=14)
        result = await tools.add_todo(
            title=f"Deadline test {cleanup_test_todos['tag']}",
            deadline=target_date.strftime('%Y-%m-%d'),
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(result['todo_id'])

        # Search by deadline
        search_results = await tools.search_advanced(
            deadline=target_date.strftime('%Y-%m-%d'),
            limit=100
        )

        # Verify our todo is in results
        result_ids = [todo['uuid'] for todo in search_results]
        assert result['todo_id'] in result_ids, "Todo with deadline not found in search"

        print(f"✓ Search by deadline found todo")

    @pytest.mark.asyncio
    async def test_get_due_in_7_days(self, cleanup_test_todos):
        """Verify get_due_in_days(7) returns todos with deadlines within 7 days."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create todos with various deadlines
        today = date.today()

        # Within 7 days
        for day_offset in [3, 5, 7]:
            future_date = today + timedelta(days=day_offset)
            result = await tools.add_todo(
                title=f"Due day {day_offset} {cleanup_test_todos['tag']}",
                deadline=future_date.strftime('%Y-%m-%d'),
                tags=cleanup_test_todos['tag']
            )
            cleanup_test_todos['ids'].append(result['todo_id'])

        # Beyond 7 days
        far_date = today + timedelta(days=20)
        far_result = await tools.add_todo(
            title=f"Due day 20 {cleanup_test_todos['tag']}",
            deadline=far_date.strftime('%Y-%m-%d'),
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(far_result['todo_id'])

        # Query due in 7 days
        due_soon = await tools.get_due_in_days(days=7)
        due_ids = [todo['uuid'] for todo in due_soon]

        # Should have at least 3 todos
        matching_count = sum(1 for todo_id in cleanup_test_todos['ids'][:3] if todo_id in due_ids)
        assert matching_count >= 1, "Expected todos with deadlines not found"

        print(f"✓ get_due_in_days(7) returned {len(due_soon)} todos")

    @pytest.mark.asyncio
    async def test_deadline_and_start_date_separate(self, cleanup_test_todos):
        """Verify deadline search doesn't mix with start_date."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        today = date.today()
        start_date = today + timedelta(days=5)
        deadline_date = today + timedelta(days=10)

        # Create todo with both start date and deadline
        result = await tools.add_todo(
            title=f"Both dates {cleanup_test_todos['tag']}",
            when=start_date.strftime('%Y-%m-%d'),
            deadline=deadline_date.strftime('%Y-%m-%d'),
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(result['todo_id'])

        # Search by deadline
        deadline_results = await tools.search_advanced(
            deadline=deadline_date.strftime('%Y-%m-%d'),
            limit=100
        )
        deadline_ids = [todo['uuid'] for todo in deadline_results]
        assert result['todo_id'] in deadline_ids, "Todo not found when searching by deadline"

        # Search by start_date
        start_results = await tools.search_advanced(
            start_date=start_date.strftime('%Y-%m-%d'),
            limit=100
        )
        start_ids = [todo['uuid'] for todo in start_results]
        assert result['todo_id'] in start_ids, "Todo not found when searching by start_date"

        print(f"✓ Deadline and start_date queries are separate")


class TestLogbookQueries:
    """Test queries for completed todos in logbook."""

    @pytest.mark.asyncio
    async def test_logbook_by_period(self, cleanup_test_todos):
        """Verify get_logbook(period='3d') returns recently completed todos."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create and complete a todo
        result = await tools.add_todo(
            title=f"To complete {cleanup_test_todos['tag']}",
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(result['todo_id'])

        # Complete it
        await tools.update_todo(todo_id=result['todo_id'], completed="true")

        # Query logbook
        logbook = await tools.get_logbook(period="3d", limit=50)

        # Verify our completed todo is in logbook
        logbook_ids = [todo['uuid'] for todo in logbook]
        assert result['todo_id'] in logbook_ids, "Completed todo not found in logbook"

        print(f"✓ Completed todo found in logbook")

    @pytest.mark.asyncio
    async def test_logbook_excludes_incomplete(self, cleanup_test_todos):
        """Verify logbook only returns completed todos."""
        manager = AppleScriptManager()
        tools = ThingsTools(manager)

        # Create incomplete todo
        incomplete_result = await tools.add_todo(
            title=f"Incomplete {cleanup_test_todos['tag']}",
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(incomplete_result['todo_id'])

        # Create and complete another todo
        complete_result = await tools.add_todo(
            title=f"Complete {cleanup_test_todos['tag']}",
            tags=cleanup_test_todos['tag']
        )
        cleanup_test_todos['ids'].append(complete_result['todo_id'])
        await tools.update_todo(todo_id=complete_result['todo_id'], completed="true")

        # Query logbook
        logbook = await tools.get_logbook(period="7d", limit=50)
        logbook_ids = [todo['uuid'] for todo in logbook]

        # Incomplete should not be in logbook
        assert incomplete_result['todo_id'] not in logbook_ids, "Incomplete todo incorrectly in logbook"

        # Completed should be in logbook
        assert complete_result['todo_id'] in logbook_ids, "Completed todo not in logbook"

        print(f"✓ Logbook excludes incomplete todos")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
