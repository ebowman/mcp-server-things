"""
Integration tests comparing old (legacy) and new (state machine) parsers.

These tests ensure that both parsers produce identical output for various
AppleScript output formats, validating that the new parser is a drop-in
replacement for the old one.
"""

import pytest
from things_mcp.services.applescript_manager import AppleScriptManager
from things_mcp.config import ThingsMCPConfig


class TestParserComparison:
    """Compare output from old and new parsers."""

    @pytest.fixture
    def legacy_manager(self):
        """Create manager with legacy parser."""
        config = ThingsMCPConfig()
        config.use_new_applescript_parser = False
        return AppleScriptManager(config=config)

    @pytest.fixture
    def new_manager(self):
        """Create manager with new parser."""
        config = ThingsMCPConfig()
        config.use_new_applescript_parser = True
        return AppleScriptManager(config=config)

    def test_simple_record_parsing(self, legacy_manager, new_manager):
        """Test simple record with basic fields."""
        output = "id:123, name:Test Todo, status:open"

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        assert legacy_result[0]['id'] == new_result[0]['id'] == '123'
        assert legacy_result[0]['name'] == new_result[0]['name'] == 'Test Todo'
        assert legacy_result[0]['status'] == new_result[0]['status'] == 'open'

    def test_quoted_values_with_commas(self, legacy_manager, new_manager):
        """Test quoted values containing commas."""
        output = 'id:123, name:"Buy milk, eggs, bread", status:open'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        assert legacy_result[0]['name'] == new_result[0]['name'] == 'Buy milk, eggs, bread'

    def test_quoted_values_with_colons(self, legacy_manager, new_manager):
        """Test quoted values containing colons."""
        output = 'id:123, notes:"Meeting at 3:00 PM in Room 5"'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        assert legacy_result[0]['notes'] == new_result[0]['notes'] == 'Meeting at 3:00 PM in Room 5'

    def test_simple_tags_list(self, legacy_manager, new_manager):
        """Test simple tag list."""
        output = 'id:123, name:Task, tag_names:{"work", "urgent"}'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        assert 'tags' in legacy_result[0] and 'tags' in new_result[0]
        assert set(legacy_result[0]['tags']) == set(new_result[0]['tags']) == {'work', 'urgent'}

    def test_tags_with_spaces(self, legacy_manager, new_manager):
        """Test tags containing spaces."""
        output = 'id:123, name:Task, tag_names:{"High Priority", "Work Project"}'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        assert set(legacy_result[0]['tags']) == set(new_result[0]['tags']) == {'High Priority', 'Work Project'}

    def test_empty_tags_list(self, legacy_manager, new_manager):
        """Test empty tag list."""
        output = 'id:123, name:Task, tag_names:{}'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        assert legacy_result[0]['tags'] == new_result[0]['tags'] == []

    def test_us_date_format(self, legacy_manager, new_manager):
        """Test US date format parsing."""
        output = 'id:123, name:Task, creation_date:Monday, January 15, 2024 at 2:30:00 PM'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        # Both should parse to same ISO format
        assert legacy_result[0]['creation_date'] == new_result[0]['creation_date']
        # Verify it's a valid ISO date
        assert '2024-01-15' in legacy_result[0]['creation_date']

    def test_european_date_format(self, legacy_manager, new_manager):
        """Test European date format parsing."""
        output = 'id:123, name:Task, creation_date:Thursday, 4. September 2025 at 14:30:00'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        # Both should parse to same ISO format
        assert legacy_result[0]['creation_date'] == new_result[0]['creation_date']
        # Verify it's a valid ISO date
        assert '2025-09-04' in legacy_result[0]['creation_date']

    def test_multiple_records(self, legacy_manager, new_manager):
        """Test parsing multiple records."""
        output = (
            'id:123, name:First, status:open, '
            'id:456, name:Second, status:completed'
        )

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 2

        # First record
        assert legacy_result[0]['id'] == new_result[0]['id'] == '123'
        assert legacy_result[0]['name'] == new_result[0]['name'] == 'First'
        assert legacy_result[0]['status'] == new_result[0]['status'] == 'open'

        # Second record
        assert legacy_result[1]['id'] == new_result[1]['id'] == '456'
        assert legacy_result[1]['name'] == new_result[1]['name'] == 'Second'
        assert legacy_result[1]['status'] == new_result[1]['status'] == 'completed'

    def test_complex_record_with_all_features(self, legacy_manager, new_manager):
        """Test complex record with quotes, tags, dates, and multiple fields."""
        output = (
            'id:123, '
            'name:"Buy groceries", '
            'notes:"Need: milk, eggs, bread", '
            'tag_names:{"errands", "high-priority"}, '
            'creation_date:Monday, January 15, 2024 at 2:30:00 PM, '
            'status:open'
        )

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1

        # Verify all fields match
        assert legacy_result[0]['id'] == new_result[0]['id']
        assert legacy_result[0]['name'] == new_result[0]['name']
        assert legacy_result[0]['notes'] == new_result[0]['notes']
        assert set(legacy_result[0]['tags']) == set(new_result[0]['tags'])
        assert legacy_result[0]['creation_date'] == new_result[0]['creation_date']
        assert legacy_result[0]['status'] == new_result[0]['status']

    def test_missing_values(self, legacy_manager, new_manager):
        """Test handling of missing values."""
        output = 'id:123, name:Task, notes:missing value, due_date:missing value'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1
        assert legacy_result[0]['notes'] == new_result[0]['notes'] is None
        assert legacy_result[0]['due_date'] == new_result[0]['due_date'] is None

    def test_empty_output(self, legacy_manager, new_manager):
        """Test handling of empty output."""
        output = ""

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert legacy_result == new_result == []

    def test_multiple_complex_records(self, legacy_manager, new_manager):
        """Test multiple complex records with various features."""
        output = (
            'id:123, name:"First Task", notes:"Meeting at 3:00, Room 5", '
            'tag_names:{"work", "urgent"}, creation_date:January 15, 2024 at 2:30:00 PM, '
            'id:456, name:"Second Task", notes:"Follow up", tag_names:{"personal"}, '
            'creation_date:January 16, 2024 at 9:00:00 AM'
        )

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 2

        # Compare all fields in both records
        for i in range(2):
            assert legacy_result[i]['id'] == new_result[i]['id']
            assert legacy_result[i]['name'] == new_result[i]['name']
            assert legacy_result[i]['notes'] == new_result[i]['notes']
            assert set(legacy_result[i]['tags']) == set(new_result[i]['tags'])
            assert legacy_result[i]['creation_date'] == new_result[i]['creation_date']

    def test_various_date_fields(self, legacy_manager, new_manager):
        """Test that all date fields are parsed consistently."""
        # Note: completion_date and cancellation_date are NOT in the legacy parser's
        # protected date field list, so they have bugs (§COMMA§ placeholders remain).
        # The new parser fixes this by correctly handling ALL date fields.
        working_date_fields = [
            'creation_date', 'modification_date', 'due_date', 'start_date'
        ]

        for field in working_date_fields:
            output = f'id:123, name:Task, {field}:Monday, January 15, 2024 at 2:30:00 PM'

            legacy_result = legacy_manager._parse_applescript_list(output)
            new_result = new_manager._parse_applescript_list(output)

            assert len(legacy_result) == len(new_result) == 1
            assert legacy_result[0][field] == new_result[0][field]
            # Verify date was actually parsed
            assert '2024-01-15' in legacy_result[0][field]

    def test_new_parser_fixes_completion_date_bug(self, legacy_manager, new_manager):
        """Test that new parser correctly handles completion_date (legacy parser bug)."""
        output = 'id:123, name:Task, completion_date:Monday, January 15, 2024 at 2:30:00 PM'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1

        # Legacy parser has a bug - leaves §COMMA§ placeholders
        assert '§COMMA§' in legacy_result[0]['completion_date']

        # New parser correctly parses the date
        assert '2024-01-15' in new_result[0]['completion_date']
        assert '§COMMA§' not in new_result[0]['completion_date']

    def test_new_parser_fixes_cancellation_date_bug(self, legacy_manager, new_manager):
        """Test that new parser correctly handles cancellation_date (legacy parser bug)."""
        output = 'id:123, name:Task, cancellation_date:Monday, January 15, 2024 at 2:30:00 PM'

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        assert len(legacy_result) == len(new_result) == 1

        # Legacy parser has a bug - leaves §COMMA§ placeholders
        assert '§COMMA§' in legacy_result[0]['cancellation_date']

        # New parser correctly parses the date
        assert '2024-01-15' in new_result[0]['cancellation_date']
        assert '§COMMA§' not in new_result[0]['cancellation_date']


class TestParserPerformance:
    """Basic performance comparison tests."""

    @pytest.fixture
    def legacy_manager(self):
        """Create manager with legacy parser."""
        config = ThingsMCPConfig()
        config.use_new_applescript_parser = False
        return AppleScriptManager(config=config)

    @pytest.fixture
    def new_manager(self):
        """Create manager with new parser."""
        config = ThingsMCPConfig()
        config.use_new_applescript_parser = True
        return AppleScriptManager(config=config)

    def test_large_output_parsing(self, legacy_manager, new_manager):
        """Test parsing a large output with many records."""
        # Create 50 records
        records = []
        for i in range(50):
            records.append(
                f'id:{i}, name:"Task {i}", '
                f'notes:"Description for task {i}", '
                f'tag_names:{{"work", "project-{i % 10}"}}, '
                f'status:open'
            )
        output = ', '.join(records)

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        # Verify count
        assert len(legacy_result) == len(new_result) == 50

        # Spot check a few records
        for i in [0, 25, 49]:
            assert legacy_result[i]['id'] == new_result[i]['id'] == str(i)
            assert f'Task {i}' in legacy_result[i]['name']
            assert f'Task {i}' in new_result[i]['name']


class TestParserErrorHandling:
    """Test error handling and edge cases."""

    @pytest.fixture
    def legacy_manager(self):
        """Create manager with legacy parser."""
        config = ThingsMCPConfig()
        config.use_new_applescript_parser = False
        return AppleScriptManager(config=config)

    @pytest.fixture
    def new_manager(self):
        """Create manager with new parser."""
        config = ThingsMCPConfig()
        config.use_new_applescript_parser = True
        return AppleScriptManager(config=config)

    def test_malformed_but_parseable(self, legacy_manager, new_manager):
        """Test handling of slightly malformed but parseable input."""
        # Extra commas, extra whitespace
        output = 'id:123,, name:Task,  status:open  '

        legacy_result = legacy_manager._parse_applescript_list(output)
        new_result = new_manager._parse_applescript_list(output)

        # Both should handle gracefully
        assert len(legacy_result) >= 1
        assert len(new_result) >= 1
        assert legacy_result[0]['id'] == new_result[0]['id']
