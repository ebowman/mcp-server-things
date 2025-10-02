"""Test status filter functionality for search_advanced.

This test verifies the fix for the critical bug where search_advanced(status='completed')
was returning 'open' status todos instead of completed todos.

Root Cause:
- The 'status' parameter was not being mapped to AppleScript status values
- The old code used 'completion date' checks instead of the actual 'status' property
- AppleScript status values are: open, completed, canceled (not incomplete)

Fix Applied:
- Map 'status' parameter directly to AppleScript status property checks
- Include Logbook list when searching for completed/canceled todos
- Return status information in results for verification
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from things_mcp.pure_applescript_scheduler import PureAppleScriptScheduler


@pytest.fixture
def mock_applescript_manager():
    """Create a mock AppleScript manager."""
    manager = Mock()
    manager.execute_applescript = AsyncMock()
    return manager


@pytest.fixture
def scheduler(mock_applescript_manager):
    """Create PureAppleScriptScheduler instance with mocked dependencies."""
    return PureAppleScriptScheduler(mock_applescript_manager)


class TestSearchAdvancedStatusFilter:
    """Test status filtering in search_advanced."""

    @pytest.mark.asyncio
    async def test_search_advanced_completed_status(self, scheduler, mock_applescript_manager):
        """Test that status='completed' filters for completed todos correctly."""
        # Mock AppleScript response with completed todos
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': [
                'ID:todo1|TITLE:Completed Task 1|STATUS:completed',
                'ID:todo2|TITLE:Completed Task 2|STATUS:completed'
            ]
        }

        result = await scheduler.search_advanced(status='completed')

        # Verify results
        assert len(result) == 2
        assert all(todo['status'] == 'completed' for todo in result)
        assert result[0]['title'] == 'Completed Task 1'
        assert result[1]['title'] == 'Completed Task 2'

        # Verify the AppleScript includes status filter
        call_args = mock_applescript_manager.execute_applescript.call_args
        script = call_args[0][0]
        assert 'status of aTodo is not equal to completed' in script
        # Verify Logbook is included when searching for completed todos
        assert 'list "Logbook"' in script

    @pytest.mark.asyncio
    async def test_search_advanced_incomplete_status(self, scheduler, mock_applescript_manager):
        """Test that status='incomplete' filters for open todos correctly."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': [
                'ID:todo1|TITLE:Open Task 1|STATUS:open',
                'ID:todo2|TITLE:Open Task 2|STATUS:open'
            ]
        }

        result = await scheduler.search_advanced(status='incomplete')

        assert len(result) == 2
        assert all(todo['status'] == 'open' for todo in result)

        # Verify the AppleScript includes correct status filter for 'incomplete'
        call_args = mock_applescript_manager.execute_applescript.call_args
        script = call_args[0][0]
        assert 'status of aTodo is not equal to open' in script

    @pytest.mark.asyncio
    async def test_search_advanced_canceled_status(self, scheduler, mock_applescript_manager):
        """Test that status='canceled' filters for canceled todos correctly."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': [
                'ID:todo1|TITLE:Canceled Task 1|STATUS:canceled'
            ]
        }

        result = await scheduler.search_advanced(status='canceled')

        assert len(result) == 1
        assert result[0]['status'] == 'canceled'

        # Verify the AppleScript includes status filter
        call_args = mock_applescript_manager.execute_applescript.call_args
        script = call_args[0][0]
        assert 'status of aTodo is not equal to canceled' in script
        # Verify Logbook is included when searching for canceled todos
        assert 'list "Logbook"' in script

    @pytest.mark.asyncio
    async def test_search_advanced_no_status_filter(self, scheduler, mock_applescript_manager):
        """Test that no status parameter returns all todos."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': [
                'ID:todo1|TITLE:Open Task|STATUS:open',
                'ID:todo2|TITLE:Completed Task|STATUS:completed',
                'ID:todo3|TITLE:Canceled Task|STATUS:canceled'
            ]
        }

        result = await scheduler.search_advanced()

        assert len(result) == 3
        statuses = {todo['status'] for todo in result}
        assert statuses == {'open', 'completed', 'canceled'}

        # Verify no status filter is in the script
        call_args = mock_applescript_manager.execute_applescript.call_args
        script = call_args[0][0]
        assert 'status of aTodo is not equal to' not in script

    @pytest.mark.asyncio
    async def test_search_advanced_status_with_query(self, scheduler, mock_applescript_manager):
        """Test combining status filter with text query."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': [
                'ID:todo1|TITLE:Complete project report|STATUS:completed'
            ]
        }

        result = await scheduler.search_advanced(query='report', status='completed')

        assert len(result) == 1
        assert result[0]['status'] == 'completed'
        assert 'report' in result[0]['title'].lower()

        # Verify both filters are in the script
        call_args = mock_applescript_manager.execute_applescript.call_args
        script = call_args[0][0]
        assert 'report' in script.lower()
        assert 'status of aTodo is not equal to completed' in script

    @pytest.mark.asyncio
    async def test_search_advanced_open_status_synonym(self, scheduler, mock_applescript_manager):
        """Test that 'open' is treated as synonym for 'incomplete'."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': ['ID:todo1|TITLE:Open Task|STATUS:open']
        }

        result = await scheduler.search_advanced(status='open')

        assert len(result) == 1
        assert result[0]['status'] == 'open'

        # Verify the filter uses 'open' in AppleScript
        call_args = mock_applescript_manager.execute_applescript.call_args
        script = call_args[0][0]
        assert 'status of aTodo is not equal to open' in script

    @pytest.mark.asyncio
    async def test_parse_todo_info_with_status(self, scheduler):
        """Test that _parse_todo_info correctly extracts status."""
        info_string = "ID:abc123|TITLE:Test Todo|STATUS:completed|NOTES:Test notes"

        result = scheduler.search_ops._parse_todo_info(info_string)

        assert result['id'] == 'abc123'
        assert result['title'] == 'Test Todo'
        assert result['status'] == 'completed'
        assert result['notes'] == 'Test notes'

    @pytest.mark.asyncio
    async def test_parse_todo_info_default_status(self, scheduler):
        """Test that _parse_todo_info defaults to 'open' status if not provided."""
        info_string = "ID:abc123|TITLE:Test Todo"

        result = scheduler.search_ops._parse_todo_info(info_string)

        assert result['status'] == 'open'  # Default when status not in response

    @pytest.mark.asyncio
    async def test_applescript_includes_logbook_for_completed(self, scheduler, mock_applescript_manager):
        """Test that Logbook list is included when searching for completed todos."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': []
        }

        await scheduler.search_advanced(status='completed')

        call_args = mock_applescript_manager.execute_applescript.call_args
        script = call_args[0][0]

        # Verify Logbook is included
        assert 'list "Logbook"' in script
        # Verify standard lists are also included
        assert 'list "Today"' in script
        assert 'list "Inbox"' in script

    @pytest.mark.asyncio
    async def test_applescript_excludes_logbook_for_incomplete(self, scheduler, mock_applescript_manager):
        """Test that Logbook list is NOT included when searching for incomplete todos."""
        mock_applescript_manager.execute_applescript.return_value = {
            'success': True,
            'output': []
        }

        await scheduler.search_advanced(status='incomplete')

        call_args = mock_applescript_manager.execute_applescript.call_args
        script = call_args[0][0]

        # Verify Logbook is NOT included for incomplete searches
        # It should only appear once in the overall script structure, not added dynamically
        logbook_count = script.count('list "Logbook"')
        assert logbook_count == 0, "Logbook should not be included when searching for incomplete todos"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
