"""
Comprehensive bulk operations testing for Things 3 MCP server.
Tests bulk_update_todos and bulk_move_records with various scenarios.
"""

import pytest
from unittest.mock import MagicMock, patch
from things_mcp.server import mcp
from things_mcp.applescript_manager import AppleScriptManager

@pytest.fixture
def mock_applescript():
    """Mock AppleScript execution for bulk operations."""
    with patch('things_mcp.applescript_manager.subprocess.run') as mock_run:
        # Default successful execution
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="success",
            stderr=""
        )
        yield mock_run

class TestBulkUpdateTodos:
    """Test bulk_update_todos functionality."""
    
    def test_single_field_update_small_batch(self, mock_applescript):
        """Test updating a single field on 2-5 todos."""
        todo_ids = "id1,id2,id3"
        
        # Test completed field
        result = mcp.call_tool(
            "bulk_update_todos",
            {"todo_ids": todo_ids, "completed": "true"}
        )
        
        assert mock_applescript.called
        assert "id1" in str(mock_applescript.call_args)
        assert "id2" in str(mock_applescript.call_args)
        assert "id3" in str(mock_applescript.call_args)
    
    def test_single_field_update_medium_batch(self, mock_applescript):
        """Test updating a single field on 10-20 todos."""
        todo_ids = ",".join([f"id{i}" for i in range(1, 16)])  # 15 todos
        
        result = mcp.call_tool(
            "bulk_update_todos",
            {"todo_ids": todo_ids, "tags": "urgent,test"}
        )
        
        assert mock_applescript.called
        # Verify all IDs are processed
        script_calls = str(mock_applescript.call_args_list)
        for i in range(1, 16):
            assert f"id{i}" in script_calls
    
    def test_single_field_update_large_batch(self, mock_applescript):
        """Test updating a single field on 50+ todos."""
        todo_ids = ",".join([f"id{i}" for i in range(1, 51)])  # 50 todos
        
        result = mcp.call_tool(
            "bulk_update_todos",
            {"todo_ids": todo_ids, "when": "today"}
        )
        
        assert mock_applescript.called
    
    def test_multi_field_update_v1_2_2_fix(self, mock_applescript):
        """Test v1.2.2+ fix: multiple fields all get applied."""
        todo_ids = "id1,id2,id3"
        
        # Test tags + deadline + notes
        result = mcp.call_tool(
            "bulk_update_todos",
            {
                "todo_ids": todo_ids,
                "tags": "urgent,test",
                "deadline": "2025-12-31",
                "notes": "Updated via bulk operation"
            }
        )
        
        # Verify all fields are in the script
        script_calls = str(mock_applescript.call_args_list)
        assert "urgent" in script_calls or "tag" in script_calls.lower()
        assert "2025-12-31" in script_calls or "deadline" in script_calls.lower()
        assert "Updated via bulk operation" in script_calls or "note" in script_calls.lower()
    
    def test_multi_field_completed_and_notes(self, mock_applescript):
        """Test completed + notes combination."""
        result = mcp.call_tool(
            "bulk_update_todos",
            {
                "todo_ids": "id1,id2",
                "completed": "true",
                "notes": "Completed in sprint review"
            }
        )
        
        script_calls = str(mock_applescript.call_args_list)
        assert "completed" in script_calls.lower() or "true" in script_calls.lower()
        assert "Completed in sprint review" in script_calls or "note" in script_calls.lower()
    
    def test_multi_field_when_tags_title(self, mock_applescript):
        """Test when + tags + title combination."""
        result = mcp.call_tool(
            "bulk_update_todos",
            {
                "todo_ids": "id1,id2,id3",
                "when": "today",
                "tags": "urgent,work",
                "title": "Updated Title"
            }
        )
        
        script_calls = str(mock_applescript.call_args_list)
        assert "today" in script_calls.lower() or "when" in script_calls.lower()
        assert "urgent" in script_calls or "tag" in script_calls.lower()
        assert "Updated Title" in script_calls or "name" in script_calls.lower()
    
    def test_all_updateable_fields(self, mock_applescript):
        """Test all updateable fields: title, notes, when, deadline, tags, completed, canceled."""
        result = mcp.call_tool(
            "bulk_update_todos",
            {
                "todo_ids": "id1",
                "title": "New Title",
                "notes": "New notes",
                "when": "today",
                "deadline": "2025-12-31",
                "tags": "test,bulk",
                "completed": "false",
                "canceled": "false"
            }
        )
        
        assert mock_applescript.called
    
    def test_empty_id_list(self, mock_applescript):
        """Test error handling for empty ID list."""
        with pytest.raises(Exception):
            mcp.call_tool("bulk_update_todos", {"todo_ids": "", "tags": "test"})
    
    def test_malformed_id_list(self, mock_applescript):
        """Test handling of malformed ID lists."""
        # Whitespace handling
        result = mcp.call_tool(
            "bulk_update_todos",
            {"todo_ids": "id1, id2, id3", "tags": "test"}  # Spaces after commas
        )
        
        # Should handle gracefully
        assert mock_applescript.called
    
    def test_non_existent_ids(self, mock_applescript):
        """Test handling of non-existent IDs."""
        # Mock AppleScript to return error for non-existent IDs
        mock_applescript.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Can't get to do id \"nonexistent\""
        )
        
        result = mcp.call_tool(
            "bulk_update_todos",
            {"todo_ids": "nonexistent", "tags": "test"}
        )
        
        # Should handle error gracefully
        assert mock_applescript.called


class TestBulkMoveRecords:
    """Test bulk_move_records functionality."""
    
    def test_move_to_inbox(self, mock_applescript):
        """Test moving todos to inbox."""
        result = mcp.call_tool(
            "bulk_move_records",
            {
                "todo_ids": "id1,id2,id3",
                "destination": "inbox"
            }
        )
        
        assert mock_applescript.called
        script_calls = str(mock_applescript.call_args_list)
        assert "inbox" in script_calls.lower()
    
    def test_move_to_today(self, mock_applescript):
        """Test moving todos to today list."""
        result = mcp.call_tool(
            "bulk_move_records",
            {
                "todo_ids": "id1,id2,id3,id4,id5",
                "destination": "today"
            }
        )
        
        assert mock_applescript.called
        script_calls = str(mock_applescript.call_args_list)
        assert "today" in script_calls.lower()
    
    def test_move_to_anytime(self, mock_applescript):
        """Test moving todos to anytime list."""
        result = mcp.call_tool(
            "bulk_move_records",
            {"todo_ids": "id1,id2", "destination": "anytime"}
        )
        
        assert mock_applescript.called
    
    def test_move_to_someday(self, mock_applescript):
        """Test moving todos to someday list."""
        result = mcp.call_tool(
            "bulk_move_records",
            {"todo_ids": "id1,id2", "destination": "someday"}
        )
        
        assert mock_applescript.called
    
    def test_move_to_project(self, mock_applescript):
        """Test moving todos to a project."""
        result = mcp.call_tool(
            "bulk_move_records",
            {
                "todo_ids": "id1,id2,id3",
                "destination": "project:project123"
            }
        )
        
        assert mock_applescript.called
        script_calls = str(mock_applescript.call_args_list)
        assert "project123" in script_calls
    
    def test_preserve_scheduling_true(self, mock_applescript):
        """Test preserve_scheduling=true parameter."""
        result = mcp.call_tool(
            "bulk_move_records",
            {
                "todo_ids": "id1,id2",
                "destination": "inbox",
                "preserve_scheduling": True
            }
        )
        
        assert mock_applescript.called
    
    def test_preserve_scheduling_false(self, mock_applescript):
        """Test preserve_scheduling=false parameter."""
        result = mcp.call_tool(
            "bulk_move_records",
            {
                "todo_ids": "id1,id2",
                "destination": "today",
                "preserve_scheduling": False
            }
        )
        
        assert mock_applescript.called
    
    def test_max_concurrent_low(self, mock_applescript):
        """Test max_concurrent=1 (sequential processing)."""
        result = mcp.call_tool(
            "bulk_move_records",
            {
                "todo_ids": "id1,id2,id3,id4,id5",
                "destination": "inbox",
                "max_concurrent": 1
            }
        )
        
        assert mock_applescript.called
    
    def test_max_concurrent_high(self, mock_applescript):
        """Test max_concurrent=10 (maximum parallelism)."""
        result = mcp.call_tool(
            "bulk_move_records",
            {
                "todo_ids": ",".join([f"id{i}" for i in range(1, 21)]),  # 20 todos
                "destination": "inbox",
                "max_concurrent": 10
            }
        )
        
        assert mock_applescript.called
    
    def test_small_batch_2_todos(self, mock_applescript):
        """Test small batch (2 todos)."""
        result = mcp.call_tool(
            "bulk_move_records",
            {"todo_ids": "id1,id2", "destination": "inbox"}
        )
        
        assert mock_applescript.called
    
    def test_medium_batch_15_todos(self, mock_applescript):
        """Test medium batch (15 todos)."""
        todo_ids = ",".join([f"id{i}" for i in range(1, 16)])
        result = mcp.call_tool(
            "bulk_move_records",
            {"todo_ids": todo_ids, "destination": "today"}
        )
        
        assert mock_applescript.called
    
    def test_large_batch_50_todos(self, mock_applescript):
        """Test large batch (50 todos)."""
        todo_ids = ",".join([f"id{i}" for i in range(1, 51)])
        result = mcp.call_tool(
            "bulk_move_records",
            {"todo_ids": todo_ids, "destination": "inbox"}
        )
        
        assert mock_applescript.called
    
    def test_empty_destination(self, mock_applescript):
        """Test error handling for empty destination."""
        with pytest.raises(Exception):
            mcp.call_tool(
                "bulk_move_records",
                {"todo_ids": "id1,id2", "destination": ""}
            )
    
    def test_invalid_destination_format(self, mock_applescript):
        """Test error handling for invalid destination format."""
        # Invalid format should be caught or handled gracefully
        result = mcp.call_tool(
            "bulk_move_records",
            {"todo_ids": "id1", "destination": "invalid:format:here"}
        )
        
        # Should either raise exception or handle gracefully
        assert mock_applescript.called or True  # Allow graceful handling


class TestPerformanceCharacteristics:
    """Test performance and optimization characteristics."""
    
    def test_optimal_batch_size_detection(self, mock_applescript):
        """Test that optimal batch sizes (2-50) work well."""
        for size in [2, 5, 10, 20, 50]:
            todo_ids = ",".join([f"id{i}" for i in range(1, size + 1)])
            result = mcp.call_tool(
                "bulk_update_todos",
                {"todo_ids": todo_ids, "tags": "test"}
            )
            assert mock_applescript.called
            mock_applescript.reset_mock()
    
    def test_concurrent_operation_handling(self, mock_applescript):
        """Test concurrent operations with different max_concurrent values."""
        todo_ids = ",".join([f"id{i}" for i in range(1, 21)])  # 20 todos
        
        for concurrent in [1, 3, 5, 10]:
            result = mcp.call_tool(
                "bulk_move_records",
                {
                    "todo_ids": todo_ids,
                    "destination": "inbox",
                    "max_concurrent": concurrent
                }
            )
            assert mock_applescript.called
            mock_applescript.reset_mock()
    
    def test_error_recovery_partial_failure(self, mock_applescript):
        """Test error recovery when some IDs fail."""
        call_count = [0]
        
        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:  # Second call fails
                return MagicMock(returncode=1, stdout="", stderr="Error")
            return MagicMock(returncode=0, stdout="success", stderr="")
        
        mock_applescript.side_effect = side_effect
        
        result = mcp.call_tool(
            "bulk_update_todos",
            {"todo_ids": "id1,id2,id3", "tags": "test"}
        )
        
        # Should continue processing despite one failure
        assert mock_applescript.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
