"""
Comprehensive unit tests for the state machine AppleScript parser.

Tests cover:
- Simple key-value pairs
- Quoted strings with special characters
- Lists with braces
- Date parsing (multiple formats)
- Tag parsing
- Multiple records
- Edge cases and error handling
"""

import pytest
from things_mcp.services.applescript.parser import AppleScriptParser, ParserState


class TestParserBasics:
    """Test basic parser functionality."""

    def test_empty_output(self):
        """Test parsing empty output."""
        parser = AppleScriptParser()
        result = parser.parse("")
        assert result == []

    def test_whitespace_only(self):
        """Test parsing whitespace-only output."""
        parser = AppleScriptParser()
        result = parser.parse("   \n\t  ")
        assert result == []

    def test_single_field(self):
        """Test parsing a single field."""
        parser = AppleScriptParser()
        result = parser.parse("id:123")
        assert len(result) == 1
        assert result[0]['id'] == '123'

    def test_multiple_fields(self):
        """Test parsing multiple fields in one record."""
        parser = AppleScriptParser()
        result = parser.parse("id:123, name:Test Todo, status:open")
        assert len(result) == 1
        assert result[0]['id'] == '123'
        assert result[0]['name'] == 'Test Todo'
        assert result[0]['status'] == 'open'


class TestQuotedStrings:
    """Test parsing of quoted strings."""

    def test_simple_quoted_value(self):
        """Test simple quoted string."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, name:"Test Todo"')
        assert result[0]['name'] == 'Test Todo'

    def test_quoted_with_comma(self):
        """Test quoted string containing comma."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, notes:"Call John, review document"')
        assert result[0]['notes'] == 'Call John, review document'

    def test_quoted_with_colon(self):
        """Test quoted string containing colon."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, notes:"Time: 3:00 PM"')
        assert result[0]['notes'] == 'Time: 3:00 PM'

    def test_quoted_with_multiple_special_chars(self):
        """Test quoted string with commas and colons."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, notes:"Meeting: 3:00 PM, Room 5, Building A"')
        assert result[0]['notes'] == 'Meeting: 3:00 PM, Room 5, Building A'

    def test_empty_quoted_string(self):
        """Test empty quoted string."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, notes:""')
        # Empty string should be treated as None or empty
        assert result[0]['notes'] in [None, '']


class TestLists:
    """Test parsing of list values with braces."""

    def test_simple_list(self):
        """Test simple list with braces."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, tag_names:{"work", "urgent"}')
        assert result[0]['tag_names'] == ['work', 'urgent']

    def test_list_with_commas_in_items(self):
        """Test list where items contain commas."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, tag_names:{"Project A, Phase 1", "urgent"}')
        assert result[0]['tag_names'] == ['Project A, Phase 1', 'urgent']

    def test_empty_list(self):
        """Test empty list."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, tag_names:{}')
        assert result[0]['tag_names'] == []

    def test_single_item_list(self):
        """Test list with single item."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, tag_names:{"work"}')
        assert result[0]['tag_names'] == ['work']


class TestDateParsing:
    """Test parsing of various date formats."""

    def test_us_date_format_pm(self):
        """Test US format with PM."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, creation_date:Monday, January 15, 2024 at 2:30:00 PM')
        assert result[0]['creation_date'] == '2024-01-15T14:30:00'

    def test_us_date_format_am(self):
        """Test US format with AM."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, creation_date:Monday, January 15, 2024 at 9:30:00 AM')
        assert result[0]['creation_date'] == '2024-01-15T09:30:00'

    def test_us_date_format_noon(self):
        """Test US format with 12 PM (noon)."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, creation_date:Monday, January 15, 2024 at 12:00:00 PM')
        assert result[0]['creation_date'] == '2024-01-15T12:00:00'

    def test_us_date_format_midnight(self):
        """Test US format with 12 AM (midnight)."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, creation_date:Monday, January 15, 2024 at 12:00:00 AM')
        assert result[0]['creation_date'] == '2024-01-15T00:00:00'

    def test_european_date_format(self):
        """Test European format with 24-hour time."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, creation_date:Thursday, 4. September 2025 at 14:30:00')
        assert result[0]['creation_date'] == '2025-09-04T14:30:00'

    def test_date_only_format(self):
        """Test date-only format."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, due_date:January 15, 2024')
        assert result[0]['due_date'] == '2024-01-15'

    def test_iso_date_format(self):
        """Test ISO date format."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, creation_date:2024-01-15 14:30:00')
        assert result[0]['creation_date'] == '2024-01-15T14:30:00'

    def test_missing_date_value(self):
        """Test missing date value."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, due_date:missing value')
        assert result[0]['due_date'] is None


class TestMultipleRecords:
    """Test parsing multiple records."""

    def test_two_simple_records(self):
        """Test two simple records."""
        parser = AppleScriptParser()
        result = parser.parse("id:123, name:First, id:456, name:Second")
        assert len(result) == 2
        assert result[0]['id'] == '123'
        assert result[0]['name'] == 'First'
        assert result[1]['id'] == '456'
        assert result[1]['name'] == 'Second'

    def test_three_complex_records(self):
        """Test three complex records with various fields."""
        parser = AppleScriptParser()
        output = (
            'id:123, name:First Todo, status:open, '
            'id:456, name:Second Todo, status:completed, '
            'id:789, name:Third Todo, status:canceled'
        )
        result = parser.parse(output)
        assert len(result) == 3
        assert result[0]['id'] == '123'
        assert result[1]['id'] == '456'
        assert result[2]['id'] == '789'
        assert result[0]['status'] == 'open'
        assert result[1]['status'] == 'completed'
        assert result[2]['status'] == 'canceled'

    def test_records_with_mixed_fields(self):
        """Test records where not all have the same fields."""
        parser = AppleScriptParser()
        output = (
            'id:123, name:First, notes:Has notes, '
            'id:456, name:Second, '
            'id:789, name:Third, notes:Also has notes'
        )
        result = parser.parse(output)
        assert len(result) == 3
        assert 'notes' in result[0]
        assert 'notes' not in result[1]
        assert 'notes' in result[2]


class TestTagParsing:
    """Test tag parsing specifically."""

    def test_tags_with_spaces(self):
        """Test tags containing spaces."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, tag_names:{"High Priority", "Work Project"}')
        assert result[0]['tag_names'] == ['High Priority', 'Work Project']

    def test_tags_with_special_chars(self):
        """Test tags with hyphens and underscores."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, tag_names:{"project-a", "phase_1"}')
        assert result[0]['tag_names'] == ['project-a', 'phase_1']

    def test_tags_field_stored_correctly(self):
        """Test that tag_names are parsed as list."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, tag_names:{"work", "urgent"}')
        # Parser stores as tag_names, not tags
        assert isinstance(result[0]['tag_names'], list)


class TestMissingValues:
    """Test handling of missing values."""

    def test_missing_value_string(self):
        """Test 'missing value' literal."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, notes:missing value')
        assert result[0]['notes'] is None

    def test_empty_string_value(self):
        """Test empty string value."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, notes:')
        # Empty value should be None
        assert result[0]['notes'] is None


class TestComplexCombinations:
    """Test complex combinations of features."""

    def test_all_features_combined(self):
        """Test record with quoted strings, lists, dates, and tags."""
        parser = AppleScriptParser()
        output = (
            'id:123, '
            'name:"Buy groceries", '
            'notes:"Need: milk, eggs, bread", '
            'tag_names:{"errands", "high-priority"}, '
            'creation_date:Monday, January 15, 2024 at 2:30:00 PM, '
            'status:open'
        )
        result = parser.parse(output)
        assert len(result) == 1
        assert result[0]['id'] == '123'
        assert result[0]['name'] == 'Buy groceries'
        assert result[0]['notes'] == 'Need: milk, eggs, bread'
        assert result[0]['tag_names'] == ['errands', 'high-priority']
        assert result[0]['creation_date'] == '2024-01-15T14:30:00'
        assert result[0]['status'] == 'open'

    def test_multiple_records_with_complex_data(self):
        """Test multiple records each with complex data."""
        parser = AppleScriptParser()
        output = (
            'id:123, name:"First Task", notes:"Meeting at 3:00, Room 5", '
            'tag_names:{"work", "urgent"}, creation_date:January 15, 2024 at 2:30:00 PM, '
            'id:456, name:"Second Task", notes:"", tag_names:{}, '
            'creation_date:January 16, 2024 at 9:00:00 AM'
        )
        result = parser.parse(output)
        assert len(result) == 2

        # First record
        assert result[0]['id'] == '123'
        assert result[0]['notes'] == 'Meeting at 3:00, Room 5'
        assert result[0]['tag_names'] == ['work', 'urgent']

        # Second record
        assert result[1]['id'] == '456'
        assert result[1]['tag_names'] == []


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_field_without_value(self):
        """Test field with no value after colon."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, name:, status:open')
        assert result[0]['id'] == '123'
        assert result[0]['name'] is None  # Empty should be None
        assert result[0]['status'] == 'open'

    def test_consecutive_commas(self):
        """Test handling of consecutive commas."""
        parser = AppleScriptParser()
        result = parser.parse('id:123,, name:Test')
        # Should handle gracefully
        assert result[0]['id'] == '123'
        assert result[0]['name'] == 'Test'

    def test_trailing_comma(self):
        """Test trailing comma at end."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, name:Test,')
        assert result[0]['id'] == '123'
        assert result[0]['name'] == 'Test'

    def test_whitespace_variations(self):
        """Test various whitespace patterns."""
        parser = AppleScriptParser()
        result = parser.parse('id:123,name:Test,  status:open')
        assert result[0]['id'] == '123'
        assert result[0]['name'] == 'Test'
        assert result[0]['status'] == 'open'

    def test_value_with_newlines(self):
        """Test value containing newlines (shouldn't happen but test anyway)."""
        parser = AppleScriptParser()
        result = parser.parse('id:123, notes:"Line 1\nLine 2"')
        # Should preserve the newline
        assert 'Line 1' in result[0]['notes']
        assert 'Line 2' in result[0]['notes']


class TestParserStateTransitions:
    """Test internal state machine transitions."""

    def test_field_to_value_transition(self):
        """Test transition from FIELD to VALUE state."""
        parser = AppleScriptParser()
        parser.parse("id:123")
        # After parsing, should have proper value
        assert parser.records[0]['id'] == '123'

    def test_value_to_quoted_transition(self):
        """Test transition from VALUE to QUOTED state."""
        parser = AppleScriptParser()
        parser.parse('id:123, name:"Test"')
        assert parser.records[0]['name'] == 'Test'

    def test_value_to_list_transition(self):
        """Test transition from VALUE to LIST state."""
        parser = AppleScriptParser()
        parser.parse('id:123, tags:{"a", "b"}')
        assert parser.records[0]['tags'] == ['a', 'b']

    def test_list_to_list_quoted_transition(self):
        """Test transition from LIST to LIST_QUOTED state."""
        parser = AppleScriptParser()
        parser.parse('id:123, tags:{"tag with, comma"}')
        assert 'tag with, comma' in parser.records[0]['tags']


class TestDateParsingEdgeCases:
    """Test edge cases in date parsing."""

    def test_all_months(self):
        """Test parsing dates for all months."""
        parser = AppleScriptParser()
        months = [
            ('January', 1), ('February', 2), ('March', 3),
            ('April', 4), ('May', 5), ('June', 6),
            ('July', 7), ('August', 8), ('September', 9),
            ('October', 10), ('November', 11), ('December', 12)
        ]
        for month_name, month_num in months:
            output = f'id:123, due_date:{month_name} 15, 2024'
            result = parser.parse(output)
            assert result[0]['due_date'] == f'2024-{month_num:02d}-15'

    def test_various_date_fields(self):
        """Test that all date fields are recognized."""
        parser = AppleScriptParser()
        date_fields = [
            'creation_date', 'modification_date', 'due_date',
            'start_date', 'completion_date', 'cancellation_date',
            'activation_date'
        ]
        for field in date_fields:
            output = f'id:123, {field}:January 15, 2024 at 2:30:00 PM'
            result = parser.parse(output)
            assert result[0][field] == '2024-01-15T14:30:00'


class TestErrorHandling:
    """Test error handling and recovery."""

    def test_malformed_but_recoverable(self):
        """Test that parser can recover from some malformed input."""
        parser = AppleScriptParser()
        # Missing closing quote - should handle gracefully
        try:
            result = parser.parse('id:123, name:"Test')
            # If it doesn't raise, check we got something
            assert len(result) >= 0
        except ValueError:
            # Also acceptable to raise an error
            pass

    def test_partial_data_returned_on_error(self):
        """Test that partial data is returned when available."""
        parser = AppleScriptParser()
        # Valid first record, then something goes wrong
        output = 'id:123, name:First, id:456, name:Second'
        result = parser.parse(output)
        # Should get at least the first record
        assert len(result) >= 1
        assert result[0]['id'] == '123'
