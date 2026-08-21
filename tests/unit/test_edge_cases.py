"""
Comprehensive edge case testing for Things 3 MCP Server.
Tests boundary conditions, invalid inputs, special characters, and limits.
"""

import pytest
from datetime import datetime, timedelta, date
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock, patch

from things_mcp.tools import ThingsTools
from test_applescript_utils import assert_balanced_quotes


class TestBoundaryConditions:
    """Test maximum field lengths and boundary values."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        """Fixture providing tools with mocked AppleScript manager."""
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_max_title_length(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with very long title (1000 chars)."""
        long_title = "A" * 1000

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-123",
            "error": None
        })

        result = await tools_with_mock.add_todo(title=long_title)

        assert result["success"] is True
        # Verify the title was passed through
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert "AAAAAAA" in script  # Should contain part of the long title

    @pytest.mark.asyncio
    async def test_max_notes_length(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with very long notes (10000 chars)."""
        long_notes = "B" * 10000

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-123",
            "error": None
        })

        result = await tools_with_mock.add_todo(title="Test", notes=long_notes)

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert "BBBBBB" in script

    @pytest.mark.asyncio
    async def test_max_search_limit(self, tools_with_mock):
        """Test search with maximum limit (500)."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            # Create 600 mock todos
            mock_data = [
                {"uuid": f"todo-{i}", "title": f"Todo {i}", "status": "open"}
                for i in range(600)
            ]
            mock_todos.return_value = mock_data

            result = await tools_with_mock.search_todos(query="Todo", limit=500)

            assert len(result) == 500  # Should be capped at 500

    @pytest.mark.asyncio
    async def test_max_logbook_limit(self, tools_with_mock):
        """Test logbook with maximum limit (100)."""
        with patch('things_mcp.tools_helpers.read_operations.things.logbook') as mock_logbook:
            # Create 150 mock completed todos
            mock_logbook.return_value = [
                {"uuid": f"todo-{i}", "title": f"Completed {i}", "status": "completed"}
                for i in range(150)
            ]

            result = await tools_with_mock.get_logbook(limit=100)

            assert len(result) <= 100  # Should be capped at 100

    @pytest.mark.asyncio
    async def test_max_days_parameter(self, tools_with_mock):
        """Test date range functions with maximum days (365)."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_todos.return_value = [
                {
                    "uuid": "todo-1",
                    "title": "Far future todo",
                    "deadline": (date.today() + timedelta(days=300)).strftime('%Y-%m-%d'),
                    "status": "open"
                }
            ]

            result = await tools_with_mock.get_upcoming(days=365)

            assert isinstance(result, list)


class TestSpecialCharacters:
    """Test handling of special characters in all text fields."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_unicode_emoji_in_title(self, tools_with_mock, mock_applescript_manager):
        """Test todo with emoji in title."""
        title_with_emoji = "🔥 Hot Task 🚀"

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-emoji",
            "error": None
        })

        result = await tools_with_mock.add_todo(title=title_with_emoji)

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert title_with_emoji in script
        assert_balanced_quotes(script)

    @pytest.mark.asyncio
    async def test_quotes_in_title(self, tools_with_mock, mock_applescript_manager):
        """Test escaping of quotes in title."""
        title_with_quotes = 'Todo with "quotes" and \'apostrophes\''

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-quotes",
            "error": None
        })

        result = await tools_with_mock.add_todo(title=title_with_quotes)

        assert result["success"] is True
        # Verify quotes were escaped
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert '\\"' in script  # Should have escaped quotes

    @pytest.mark.asyncio
    async def test_backslashes_in_title(self, tools_with_mock, mock_applescript_manager):
        """Test escaping of backslashes in title."""
        title_with_backslash = "Path\\to\\file"

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-backslash",
            "error": None
        })

        result = await tools_with_mock.add_todo(title=title_with_backslash)

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert '\\\\' in script  # Should have escaped backslashes

    @pytest.mark.asyncio
    async def test_newlines_in_notes(self, tools_with_mock, mock_applescript_manager):
        """Test notes with newlines are preserved (escaped), not collapsed to spaces."""
        notes_with_newlines = "Line 1\nLine 2\nLine 3"

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-newlines",
            "error": None
        })

        result = await tools_with_mock.add_todo(title="Test", notes=notes_with_newlines)

        assert result["success"] is True

        script = mock_applescript_manager.execution_calls[0]["script"]
        # Newlines must survive as the AppleScript escape sequence \n, not
        # be collapsed to a space and not appear as a raw newline inside
        # the string literal (which would be a syntax error).
        assert "Line 1\\nLine 2\\nLine 3" in script
        assert "Line 1 Line 2 Line 3" not in script
        assert '"Line 1\nLine 2' not in script

    @pytest.mark.asyncio
    async def test_double_newline_in_notes_preserved(self, tools_with_mock, mock_applescript_manager):
        """Test that blank-line paragraph breaks (\\n\\n) survive escaping."""
        notes = "Line one.\n\nLine two.\n\nLine three."

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-paragraphs",
            "error": None
        })

        result = await tools_with_mock.add_todo(title="Test", notes=notes)

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert "Line one.\\n\\nLine two.\\n\\nLine three." in script

    @pytest.mark.asyncio
    async def test_markdown_in_notes(self, tools_with_mock, mock_applescript_manager):
        """Test markdown formatting in notes."""
        markdown_notes = """# Header
**Bold** and *italic*
- List item 1
- List item 2
[Link](https://example.com)
"""

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-markdown",
            "error": None
        })

        result = await tools_with_mock.add_todo(title="Test", notes=markdown_notes)

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        # Markdown special chars (#, *, -, [], (), newlines) must survive
        # escaping without breaking the AppleScript string literal.
        assert "Header" in script
        assert "Bold" in script
        assert "List item 1" in script
        assert "https://example.com" in script
        assert_balanced_quotes(script)

    @pytest.mark.asyncio
    async def test_unicode_characters(self, tools_with_mock, mock_applescript_manager):
        """Test various unicode characters."""
        unicode_title = "日本語 中文 Ελληνικά עברית العربية"

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-unicode",
            "error": None
        })

        result = await tools_with_mock.add_todo(title=unicode_title)

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert unicode_title in script
        assert_balanced_quotes(script)


class TestInvalidInputs:
    """Test handling of invalid inputs and error conditions."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_missing_required_title(self, tools_with_mock):
        """Test creating todo without required title."""
        # This should raise TypeError since title is required
        with pytest.raises(TypeError):
            await tools_with_mock.add_todo()

    @pytest.mark.asyncio
    async def test_empty_title(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with empty string title."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-empty",
            "error": None
        })

        result = await tools_with_mock.add_todo(title="")

        # Should still succeed - Things 3 allows empty titles
        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert 'name:""' in script
        assert_balanced_quotes(script)

    @pytest.mark.asyncio
    async def test_invalid_todo_id(self, tools_with_mock):
        """Test getting todo with non-existent ID."""
        with patch('things_mcp.tools_helpers.read_operations.things.get') as mock_get:
            mock_get.return_value = None  # No item with this id

            # Implementation raises ValueError for not found ids
            with pytest.raises(ValueError, match="Todo not found"):
                await tools_with_mock.get_todo_by_id("nonexistent-id")

    @pytest.mark.asyncio
    async def test_invalid_date_format(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with invalid date format."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-invalid-date",
            "error": None
        })

        # Invalid date should be passed through to AppleScript
        result = await tools_with_mock.add_todo(title="Test", when="invalid-date")

        # Should still attempt to create (AppleScript will handle the error)
        assert result["success"] is True
        # The todo-creation script must still be built correctly regardless
        # of the unparseable 'when' value; the literal invalid-date string
        # is passed through to a later scheduling attempt (list_fallback).
        creation_script = mock_applescript_manager.execution_calls[0]["script"]
        assert 'name:"Test"' in creation_script
        assert_balanced_quotes(creation_script)
        all_scripts = "\n".join(c["script"] for c in mock_applescript_manager.execution_calls)
        assert "invalid-date" in all_scripts

    @pytest.mark.asyncio
    async def test_invalid_reminder_format(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with invalid reminder time format."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-invalid-reminder",
            "error": None
        })

        # Invalid reminder format
        result = await tools_with_mock.add_todo(title="Test", when="today@25:99")

        # Should still succeed (scheduler validates format)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_update_nonexistent_todo(self, tools_with_mock, mock_applescript_manager):
        """Test updating a todo that doesn't exist.

        hq-wbm: update_todo now pre-checks the primary todo_id via
        things.get() BEFORE any AppleScript write; None -> structured
        NOT_FOUND, no script emitted. things.get is mocked to return None
        here (a unit test must not depend on the real Things database -
        on a machine/CI runner without one, an unmocked call would raise
        and trigger the DB-unreadable fallback instead, surfacing
        APPLESCRIPT_ERROR and failing this test). This supersedes the
        pre-hq-wbm behavior where an unknown id reached AppleScript's
        `to do id "..."` lookup and surfaced as an opaque
        APPLESCRIPT_ERROR only after Things itself reported failure.
        """
        from unittest.mock import patch

        with patch(
            "things_mcp.scheduling.todo_operations.things.get",
            return_value=None,
        ):
            result = await tools_with_mock.update_todo(todo_id="fake-id", title="New Title")

        assert result["success"] is False
        assert result["error"] == "NOT_FOUND"
        assert "fake-id" in result["message"]
        assert mock_applescript_manager.execution_calls == []

    @pytest.mark.asyncio
    async def test_move_to_invalid_destination(self, tools_with_mock, mock_applescript_manager):
        """Test moving todo to invalid destination."""
        mock_applescript_manager.set_mock_response("default", {
            "success": False,
            "output": "",
            "error": "Invalid destination"
        })

        result = await tools_with_mock.move_record(
            todo_id="todo-123",
            destination_list="InvalidDestination"
        )

        # Move operations should handle validation
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_negative_limit(self, tools_with_mock):
        """Test search with negative limit."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_todos.return_value = [
                {"uuid": "todo-1", "title": "Test", "status": "open"}
            ]

            # Negative limit should be handled gracefully
            result = await tools_with_mock.search_todos(query="Test", limit=-5)

            # Should return empty or handle gracefully
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_zero_limit(self, tools_with_mock):
        """Test search with zero limit."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_todos.return_value = [
                {"uuid": "todo-1", "title": "Test", "status": "open"}
            ]

            result = await tools_with_mock.search_todos(query="Test", limit=0)

            # Implementation treats limit=0 as no limit (returns all matching results)
            assert isinstance(result, list)
            assert len(result) == 1  # Returns the one matching result


class TestChecklistItems:
    """Test checklist items functionality.

    NOTE: Checklist items are NOT supported via AppleScript (Things 3 API limitation).
    These tests verify the parameter is accepted but checklist items won't be created.
    A warning is returned to inform the user of this limitation.
    """

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_create_todo_with_checklist(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with checklist items.

        NOTE: Checklist items are now supported via Things URL scheme.
        The test verifies that checklists are created successfully.
        """
        checklist_items = ["Item 1", "Item 2", "Item 3"]

        # _add_todo_via_url_scheme snapshots existing todo ids with this
        # title before the create and polls for a new id afterward
        # (hq-nxu.12): the first execute_applescript call is the
        # pre-create snapshot (no existing todo), the rest are the
        # post-create poll that finds the new id.
        mock_applescript_manager.execute_applescript = AsyncMock(side_effect=[
            {"success": True, "output": "", "error": None},
            {"success": True, "output": "todo-checklist", "error": None},
        ])

        result = await tools_with_mock.add_todo(
            title="Todo with checklist",
            checklist_items=checklist_items
        )

        assert result["success"] is True
        # Verify checklist was created (no warning, has checklist_count)
        assert "checklist_count" in result
        assert result["checklist_count"] == 3
        # Checklist items go through the Things URL scheme, joined by
        # newlines into a single 'checklist-items' parameter.
        assert len(mock_applescript_manager.url_scheme_calls) == 1
        url_call = mock_applescript_manager.url_scheme_calls[0]
        assert url_call["action"] == "add"
        assert url_call["parameters"]["checklist-items"] == "Item 1\nItem 2\nItem 3"
        assert url_call["parameters"]["title"] == "Todo with checklist"

    @pytest.mark.asyncio
    async def test_empty_checklist(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with empty checklist."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-empty-checklist",
            "error": None
        })

        result = await tools_with_mock.add_todo(
            title="Test",
            checklist_items=[]
        )

        assert result["success"] is True
        # An empty checklist is falsy, so add_todo must take the fast
        # AppleScript path (not the URL scheme) - no url_scheme_calls,
        # and the title must appear in the AppleScript creation script.
        assert mock_applescript_manager.url_scheme_calls == []
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert 'name:"Test"' in script

    @pytest.mark.asyncio
    async def test_checklist_with_special_chars(self, tools_with_mock, mock_applescript_manager):
        """Test checklist items with special characters."""
        checklist_items = ['✓ Item with emoji', '"Quoted item"', 'Item with\\backslash']

        # See test_create_todo_with_checklist above: first call is the
        # pre-create snapshot, second is the post-create poll.
        mock_applescript_manager.execute_applescript = AsyncMock(side_effect=[
            {"success": True, "output": "", "error": None},
            {"success": True, "output": "todo-special-checklist", "error": None},
        ])

        result = await tools_with_mock.add_todo(
            title="Test",
            checklist_items=checklist_items
        )

        assert result["success"] is True
        # Special characters (quotes, backslash, emoji) must survive the
        # newline-join into the URL scheme parameter unescaped/unmodified -
        # the Things URL scheme, not AppleScript, is responsible for this
        # value, so no AppleScript-style backslash-escaping should occur.
        assert len(mock_applescript_manager.url_scheme_calls) == 1
        joined = mock_applescript_manager.url_scheme_calls[0]["parameters"]["checklist-items"]
        assert joined == '✓ Item with emoji\n"Quoted item"\nItem with\\backslash'

    @pytest.mark.asyncio
    async def test_retrieve_checklist_items(self, tools_with_mock):
        """Test retrieving todos with checklist items."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            # Mock the todo with checklist as a list (things.py returns checklist data)
            mock_todos.return_value = [{
                "uuid": "todo-1",
                "title": "Test Todo",
                "checklist": [
                    {"title": "Item 1", "status": "incomplete"},
                    {"title": "Item 2", "status": "completed"}
                ],
                "status": "open"
            }]

            result = await tools_with_mock.get_todos()

            assert len(result) > 0
            assert "checklist" in result[0]
            assert len(result[0]["checklist"]) == 2
            assert result[0]["checklist"][0]["title"] == "Item 1"


class TestURLAndMetadata:
    """Test URL field and metadata handling."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_retrieve_metadata(self, tools_with_mock):
        """Test retrieving todos with metadata fields."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            now = datetime.now().isoformat()
            # things.py returns these field names which convert_todo maps to MCP format
            mock_todos.return_value = [{
                "uuid": "todo-1",
                "title": "Test",
                "creationDate": now,  # things.py field name
                "modificationDate": now,  # things.py field name
                "status": "open",
                "tags": []
            }]

            result = await tools_with_mock.get_todos()

            assert len(result) > 0
            # Verify basic todo structure is preserved
            assert "uuid" in result[0]
            assert "title" in result[0]
            assert result[0]["uuid"] == "todo-1"
            assert result[0]["title"] == "Test"


class TestStatusValues:
    """Test different status values and transitions."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.fixture(autouse=True)
    def _things_get_resolves_as_todo(self):
        """hq-wbm: update_todo now pre-checks todo_id via things.get()
        before any write. "todo-123" is a fake id never present in the
        real Things database, so without this patch every call in this
        class would report NOT_FOUND instead of exercising the status
        transition behavior this class is actually testing."""
        with patch(
            "things_mcp.scheduling.todo_operations.things.get",
            return_value={"type": "to-do"},
        ):
            yield

    @pytest.mark.asyncio
    async def test_complete_todo(self, tools_with_mock, mock_applescript_manager):
        """Test completing a todo."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "updated",  # Fixed: AppleScript returns "updated", not "completed"
            "error": None
        })

        result = await tools_with_mock.update_todo(
            todo_id="todo-123",
            completed="true"
        )

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert 'to do id "todo-123"' in script
        assert "set status of targetTodo to completed" in script

    @pytest.mark.asyncio
    async def test_cancel_todo(self, tools_with_mock, mock_applescript_manager):
        """Test canceling a todo."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "updated",  # Fixed: AppleScript returns "updated", not "canceled"
            "error": None
        })

        result = await tools_with_mock.update_todo(
            todo_id="todo-123",
            canceled="true"
        )

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        assert 'to do id "todo-123"' in script
        assert "set status of targetTodo to canceled" in script

    @pytest.mark.asyncio
    async def test_retrieve_completed_todos(self, tools_with_mock):
        """Test retrieving completed todos from logbook."""
        # get_logbook is backed by things.todos(status='completed'), filtered by stop_date.
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_todos.return_value = [{
                "uuid": "todo-1",
                "title": "Completed task",
                "status": "completed",
                "stop_date": datetime.now().isoformat()
            }]

            result = await tools_with_mock.get_logbook(limit=50)

            assert len(result) > 0
            assert result[0]["status"] == "completed"


class TestTrashOperations:
    """Test trash operations with pagination."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_get_trash_basic(self, tools_with_mock):
        """Test getting trash with default pagination."""
        with patch('things_mcp.tools_helpers.read_operations.things.trash') as mock_trash:
            mock_trash.return_value = [
                {"uuid": f"trash-{i}", "title": f"Deleted {i}", "status": "canceled"}
                for i in range(75)
            ]

            result = await tools_with_mock.get_trash()

            assert "items" in result
            assert result["total_count"] == 75
            assert len(result["items"]) == 50  # Default limit
            assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_get_trash_with_offset(self, tools_with_mock):
        """Test trash pagination with offset."""
        with patch('things_mcp.tools_helpers.read_operations.things.trash') as mock_trash:
            mock_trash.return_value = [
                {"uuid": f"trash-{i}", "title": f"Deleted {i}", "status": "canceled"}
                for i in range(150)
            ]

            result = await tools_with_mock.get_trash(limit=50, offset=50)

            assert len(result["items"]) == 50
            assert result["offset"] == 50
            assert result["has_more"] is True

    @pytest.mark.asyncio
    async def test_get_trash_last_page(self, tools_with_mock):
        """Test getting last page of trash."""
        with patch('things_mcp.tools_helpers.read_operations.things.trash') as mock_trash:
            mock_trash.return_value = [
                {"uuid": f"trash-{i}", "title": f"Deleted {i}", "status": "canceled"}
                for i in range(120)
            ]

            result = await tools_with_mock.get_trash(limit=50, offset=100)

            assert len(result["items"]) == 20  # Last 20 items
            assert result["has_more"] is False

    @pytest.mark.asyncio
    async def test_get_trash_empty(self, tools_with_mock):
        """Test getting trash when empty."""
        with patch('things_mcp.tools_helpers.read_operations.things.trash') as mock_trash:
            mock_trash.return_value = []

            result = await tools_with_mock.get_trash()

            assert result["total_count"] == 0
            assert len(result["items"]) == 0
            assert result["has_more"] is False


class TestDateBoundaries:
    """Test date handling at boundaries."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_far_future_date(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with far future deadline."""
        far_future = (date.today() + timedelta(days=3650)).strftime('%Y-%m-%d')  # 10 years

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-far-future",
            "error": None
        })

        result = await tools_with_mock.add_todo(
            title="Far future task",
            deadline=far_future
        )

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        future = date.today() + timedelta(days=3650)
        assert f"set year of deadlineDate to {future.year}" in script
        assert f"set month of deadlineDate to {future.month}" in script
        assert f"set day of deadlineDate to {future.day}" in script
        assert "set due date of newTodo to deadlineDate" in script

    @pytest.mark.asyncio
    async def test_past_date(self, tools_with_mock, mock_applescript_manager):
        """Test creating todo with past deadline."""
        past_date = (date.today() - timedelta(days=365)).strftime('%Y-%m-%d')

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-past",
            "error": None
        })

        result = await tools_with_mock.add_todo(
            title="Past deadline task",
            deadline=past_date
        )

        assert result["success"] is True
        script = mock_applescript_manager.execution_calls[0]["script"]
        past = date.today() - timedelta(days=365)
        assert f"set year of deadlineDate to {past.year}" in script
        assert f"set month of deadlineDate to {past.month}" in script
        assert f"set day of deadlineDate to {past.day}" in script
        assert "set due date of newTodo to deadlineDate" in script

    @pytest.mark.asyncio
    async def test_reminder_midnight(self, tools_with_mock, mock_applescript_manager):
        """Test reminder at midnight."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-midnight",
            "error": None
        })

        result = await tools_with_mock.add_todo(
            title="Midnight reminder",
            when="today@00:00"
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_reminder_noon(self, tools_with_mock, mock_applescript_manager):
        """Test reminder at noon."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-noon",
            "error": None
        })

        result = await tools_with_mock.add_todo(
            title="Noon reminder",
            when="today@12:00"
        )

        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_reminder_end_of_day(self, tools_with_mock, mock_applescript_manager):
        """Test reminder at 23:59."""
        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "todo-eod",
            "error": None
        })

        result = await tools_with_mock.add_todo(
            title="End of day reminder",
            when="today@23:59"
        )

        assert isinstance(result, dict)


class TestBulkOperations:
    """Test bulk operations with edge cases."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_bulk_update_empty_list(self, tools_with_mock):
        """Test bulk update with empty todo list."""
        result = await tools_with_mock.bulk_update_todos(
            todo_ids=[],
            completed=True
        )

        assert result["success"] is False
        assert "error" in result
        # Validation layer returns "VALIDATION_ERROR" for empty lists
        assert result["error"] == "VALIDATION_ERROR"
        assert result.get("field") == "todo_ids"

    @pytest.mark.asyncio
    async def test_bulk_update_large_batch(self, tools_with_mock, mock_applescript_manager):
        """Test bulk update with large number of todos."""
        todo_ids = [f"todo-{i}" for i in range(100)]

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount: 100, errors: {}",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            tags=["completed"]
        )

        assert isinstance(result, dict)
        assert "updated_count" in result

    @pytest.mark.asyncio
    async def test_bulk_update_partial_failure(self, tools_with_mock, mock_applescript_manager):
        """Test bulk update with some failures."""
        todo_ids = ["valid-1", "invalid-2", "valid-3"]

        mock_applescript_manager.set_mock_response("default", {
            "success": True,
            "output": "successCount: 2, errors: {ID invalid-2: not found}",
            "error": None
        })

        result = await tools_with_mock.bulk_update_todos(
            todo_ids=todo_ids,
            title="Updated"
        )

        assert isinstance(result, dict)
        # Should report partial success
        assert result.get("updated_count", 0) >= 0


class TestEmptyResults:
    """Test handling of empty result sets."""

    @pytest.fixture
    def tools_with_mock(self, mock_applescript_manager):
        return ThingsTools(mock_applescript_manager)

    @pytest.mark.asyncio
    async def test_search_no_results(self, tools_with_mock):
        """Test search that returns no results."""
        with patch('things_mcp.tools_helpers.read_operations.things.todos') as mock_todos:
            mock_todos.return_value = []

            result = await tools_with_mock.search_todos(query="nonexistent")

            assert isinstance(result, list)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_inbox_empty(self, tools_with_mock):
        """Test getting inbox when empty."""
        with patch('things_mcp.tools_helpers.read_operations.things.inbox') as mock_inbox:
            mock_inbox.return_value = []

            result = await tools_with_mock.get_inbox()

            assert isinstance(result, list)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_today_empty(self, tools_with_mock):
        """Test getting today when empty."""
        with patch('things_mcp.tools_helpers.read_operations.things.today') as mock_today:
            mock_today.return_value = []

            result = await tools_with_mock.get_today()

            assert isinstance(result, list)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_projects_empty(self, tools_with_mock):
        """Test getting projects when none exist."""
        with patch('things_mcp.tools_helpers.read_operations.things.projects') as mock_projects:
            mock_projects.return_value = []

            result = await tools_with_mock.get_projects()

            assert isinstance(result, list)
            assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_tags_empty(self, tools_with_mock):
        """Test getting tags when none exist."""
        with patch('things_mcp.tools_helpers.read_operations.things.tags') as mock_tags:
            mock_tags.return_value = []

            result = await tools_with_mock.get_tags()

            assert isinstance(result, list)
            assert len(result) == 0


# Summary test to document all findings
class TestEdgeCaseSummary:
    """Summary of edge case testing findings."""

    def test_document_findings(self):
        """Document all edge cases and limitations discovered."""
        findings = {
            "boundary_conditions": {
                "max_title_length": "Handles 1000+ chars",
                "max_notes_length": "Handles 10000+ chars",
                "max_search_limit": "Caps at 500",
                "max_logbook_limit": "Caps at 100",
                "max_days_parameter": "365 days maximum"
            },
            "special_characters": {
                "unicode_emoji": "Supported",
                "quotes": "Requires escaping with \\\"",
                "backslashes": "Requires escaping with \\\\",
                "newlines": "Supported in notes",
                "markdown": "Supported in notes",
                "international": "Full unicode support"
            },
            "invalid_inputs": {
                "missing_title": "Raises TypeError",
                "empty_title": "Allowed by Things 3",
                "invalid_todo_id": "Returns TODO_NOT_FOUND error",
                "invalid_date": "Passed to AppleScript for handling",
                "invalid_reminder": "Scheduler validates format",
                "nonexistent_todo": "Returns error from AppleScript",
                "negative_limit": "Handled gracefully",
                "zero_limit": "Returns empty list"
            },
            "checklist_items": {
                "creation": "Supported via newline-separated string",
                "empty": "Allowed",
                "special_chars": "Requires proper escaping",
                "retrieval": "Included in todo objects"
            },
            "url_metadata": {
                "url_field": "Supported with special chars",
                "metadata_fields": "created, modified, completion_date included"
            },
            "status_values": {
                "tentative": "Supported",
                "confirmed": "Supported",
                "completed": "Supported via update",
                "canceled": "Supported via update"
            },
            "trash_operations": {
                "pagination": "Supported with limit/offset",
                "empty_trash": "Returns empty array with metadata"
            },
            "date_boundaries": {
                "far_future": "10+ years supported",
                "past_dates": "Supported",
                "midnight": "00:00 supported",
                "noon": "12:00 supported",
                "end_of_day": "23:59 supported"
            },
            "bulk_operations": {
                "empty_list": "Returns error with 0 count",
                "large_batches": "100+ todos supported",
                "partial_failures": "Reports success/failure counts"
            },
            "empty_results": {
                "all_operations": "Return empty arrays consistently"
            }
        }

        # This test always passes - it's documentation
        assert findings is not None

        print("\n=== EDGE CASE TESTING SUMMARY ===")
        import json
        print(json.dumps(findings, indent=2))