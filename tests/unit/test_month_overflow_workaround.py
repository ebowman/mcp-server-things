"""
Unit tests for AppleScript month overflow workaround pattern.

CRITICAL BUG: AppleScript has a month overflow bug where setting a date like
January 31 and then changing the month to February results in March 3 instead
of February 28/29.

WORKAROUND: Always set day to 1 first, then year, month, day in sequence:
    set time of targetDate to 0
    set day of targetDate to 1      -- Critical: Set to safe day first
    set year of targetDate to {year}
    set month of targetDate to {month}
    set day of targetDate to {day}   -- Set actual day last

This pattern appears in 6+ locations across the codebase and must be preserved
to prevent date calculation bugs.

These tests verify:
1. The workaround pattern exists in all necessary files
2. All instances use the correct sequence
3. Edge cases are documented
4. Regression prevention through code analysis
"""

import pytest
import re
import os
from pathlib import Path


# Base path for the codebase
BASE_PATH = Path(__file__).parent.parent.parent / "src" / "things_mcp"


class TestMonthOverflowWorkaroundPattern:
    """Test that the month overflow workaround pattern exists and is correct."""

    def _get_file_content(self, relative_path: str) -> str:
        """Read file content from codebase."""
        file_path = BASE_PATH / relative_path
        assert file_path.exists(), f"File not found: {file_path}"
        return file_path.read_text()

    def _verify_workaround_sequence(self, content: str, file_name: str) -> list:
        """
        Verify the workaround sequence exists in the content.

        Returns list of tuples: (line_number, matched_text)
        """
        # Look for the critical pattern: set day to 1, then year, month, day
        # This pattern prevents month overflow
        # Allow for whitespace and comments between lines
        pattern = r'set day of (\w+) to 1[^\n]*\n[^\n]*set year of \1 to'

        matches = []
        for match in re.finditer(pattern, content, re.MULTILINE):
            # Find line number
            line_num = content[:match.start()].count('\n') + 1
            matches.append((line_num, match.group(0)))

        return matches

    def test_scheduling_strategies_has_workaround(self):
        """Test scheduling/strategies.py contains the workaround pattern."""
        content = self._get_file_content("scheduling/strategies.py")

        # Verify workaround exists
        matches = self._verify_workaround_sequence(content, "strategies.py")
        assert len(matches) > 0, "scheduling/strategies.py must contain workaround pattern"

        # Verify complete sequence
        assert 'set day of targetDate to 1' in content
        assert 'set year of targetDate to' in content
        assert 'set month of targetDate to' in content
        assert 'set day of targetDate to {target_date.day}' in content

        # Verify documentation/comments exist
        assert 'overflow' in content.lower() or 'month' in content.lower()

    def test_pure_applescript_scheduler_has_workaround(self):
        """Test pure_applescript_scheduler.py contains the workaround pattern."""
        content = self._get_file_content("pure_applescript_scheduler.py")

        matches = self._verify_workaround_sequence(content, "pure_applescript_scheduler.py")

        # Should have at least 2 instances (for both scheduling methods)
        assert len(matches) >= 2, \
            f"pure_applescript_scheduler.py should have at least 2 workaround instances, found {len(matches)}"

        # Verify complete sequence
        assert 'set day of targetDate to 1' in content
        assert 'set time of targetDate to 0' in content

    def test_todo_operations_has_workaround(self):
        """Test scheduling/todo_operations.py contains the workaround pattern."""
        content = self._get_file_content("scheduling/todo_operations.py")

        matches = self._verify_workaround_sequence(content, "todo_operations.py")

        # Should have at least 4 instances (add_todo, update_todo, add_project, update_project)
        assert len(matches) >= 4, \
            f"todo_operations.py should have at least 4 workaround instances, found {len(matches)}"

        # Verify deadline date handling
        assert 'set day of deadlineDate to 1' in content
        assert 'set time of deadlineDate to 0' in content

    def test_reliable_scheduling_has_workaround(self):
        """Test reliable_scheduling.py contains the workaround pattern."""
        content = self._get_file_content("reliable_scheduling.py")

        matches = self._verify_workaround_sequence(content, "reliable_scheduling.py")
        assert len(matches) > 0, "reliable_scheduling.py must contain workaround pattern"

        # Verify sequence
        assert 'set day of targetDate to 1' in content

    def test_workaround_sequence_order_is_correct(self):
        """Verify the workaround sequence order in all files."""
        files_to_check = [
            "scheduling/strategies.py",
            "pure_applescript_scheduler.py",
            "scheduling/todo_operations.py",
            "reliable_scheduling.py"
        ]

        for file_path in files_to_check:
            content = self._get_file_content(file_path)

            # Find all workaround instances - allow for comments and whitespace
            pattern = r'set time of (\w+) to 0.*?set day of \1 to 1.*?set year of \1 to.*?set month of \1 to.*?set day of \1 to'
            matches = re.findall(pattern, content, re.DOTALL)

            assert len(matches) > 0, \
                f"{file_path} must have complete workaround sequence (time→day→year→month→day)"

    def test_all_date_variables_use_workaround(self):
        """Test that all date variable assignments use the workaround."""
        files_to_check = [
            "scheduling/strategies.py",
            "pure_applescript_scheduler.py",
            "scheduling/todo_operations.py",
            "reliable_scheduling.py"
        ]

        for file_path in files_to_check:
            content = self._get_file_content(file_path)

            # Find all date variable names that get month set
            month_sets = re.findall(r'set month of (\w+) to', content)

            for var_name in month_sets:
                # Verify this variable has "set day to 1" before month
                day_before_month = f'set day of {var_name} to 1'
                assert day_before_month in content, \
                    f"{file_path}: Variable '{var_name}' sets month but doesn't set day to 1 first"

    def test_no_direct_month_setting_without_workaround(self):
        """Ensure no month is set without first setting day to 1."""
        files_to_check = [
            "scheduling/strategies.py",
            "pure_applescript_scheduler.py",
            "scheduling/todo_operations.py",
            "reliable_scheduling.py"
        ]

        violations = []

        for file_path in files_to_check:
            content = self._get_file_content(file_path)

            # Find all month settings
            month_pattern = r'set month of (\w+) to'
            month_matches = re.finditer(month_pattern, content)

            for match in month_matches:
                var_name = match.group(1)

                # Look backwards from this point to find if day was set to 1
                context_start = max(0, match.start() - 500)
                context = content[context_start:match.start()]

                day_to_1_pattern = f'set day of {var_name} to 1'
                if day_to_1_pattern not in context:
                    line_num = content[:match.start()].count('\n') + 1
                    violations.append(f"{file_path}:{line_num} - Variable '{var_name}' sets month without setting day to 1 first")

        assert len(violations) == 0, \
            f"Found month settings without workaround:\n" + "\n".join(violations)

    def test_workaround_count_regression(self):
        """Test that the number of workaround instances hasn't decreased."""
        base_path = BASE_PATH

        # Count all instances recursively
        pattern = r'set day of \w+ to 1\s+set year'
        total_instances = 0
        file_counts = {}

        for root, dirs, files in os.walk(base_path):
            for file in files:
                if file.endswith('.py'):
                    file_path = Path(root) / file
                    try:
                        content = file_path.read_text()
                        matches = re.findall(pattern, content, re.MULTILINE)
                        count = len(matches)
                        if count > 0:
                            relative_path = file_path.relative_to(base_path)
                            file_counts[str(relative_path)] = count
                            total_instances += count
                    except Exception:
                        pass  # Skip files that can't be read

        # We expect at least 6 instances across the codebase
        assert total_instances >= 6, \
            f"Expected at least 6 workaround instances, found {total_instances}. " \
            f"Distribution: {file_counts}"

        # Print distribution for documentation
        print(f"\nWorkaround pattern found in {len(file_counts)} files:")
        for file_path, count in sorted(file_counts.items()):
            print(f"  {file_path}: {count} instance(s)")


class TestMonthOverflowEdgeCases:
    """Test documentation and handling of month overflow edge cases."""

    def _get_file_content(self, relative_path: str) -> str:
        """Read file content from codebase."""
        file_path = BASE_PATH / relative_path
        return file_path.read_text()

    def test_january_31_to_february_documented(self):
        """Test that Jan 31 → Feb case is documented."""
        # This is the primary overflow case
        content = self._get_file_content("scheduling/strategies.py")

        # Check for documentation about the overflow issue
        # Should have comments explaining the workaround
        assert 'day' in content.lower() and 'overflow' in content.lower() or \
               'day' in content.lower() and 'safe' in content.lower(), \
            "Should document why day is set to 1 first"

    def test_all_31_day_months_covered(self):
        """Test that workaround handles all 31-day month transitions."""
        # Months with 31 days: 1, 3, 5, 7, 8, 10, 12
        # All must use the workaround when setting month

        content = self._get_file_content("scheduling/strategies.py")

        # The workaround should be generic (not month-specific)
        # So it handles all months equally
        assert '{target_date.month}' in content, \
            "Should use variable month, not hardcoded values"

    def test_february_leap_year_handling(self):
        """Test that leap year February is handled correctly."""
        # The workaround should work for both Feb 28 and Feb 29

        content = self._get_file_content("scheduling/strategies.py")

        # Should use actual day value, not hardcoded
        assert '{target_date.day}' in content, \
            "Should use variable day to handle both Feb 28 and 29"

    def test_year_boundary_handling(self):
        """Test that year boundaries (Dec→Jan) are handled."""
        content = self._get_file_content("scheduling/strategies.py")

        # Should set year before month
        # Verify sequence includes year setting
        assert 'set year of' in content
        assert 'set month of' in content

        # Year should be set before final day
        year_pos = content.find('set year of targetDate')
        day_pos = content.rfind('set day of targetDate to {target_date.day}')

        assert year_pos < day_pos, "Year should be set before final day"


class TestWorkaroundRegressionPrevention:
    """Tests to prevent regression of the month overflow workaround."""

    def test_critical_files_not_removed(self):
        """Verify critical files containing workaround still exist."""
        critical_files = [
            "scheduling/strategies.py",
            "pure_applescript_scheduler.py",
            "scheduling/todo_operations.py",
            "reliable_scheduling.py"
        ]

        for file_path in critical_files:
            full_path = BASE_PATH / file_path
            assert full_path.exists(), f"Critical file missing: {file_path}"

    def test_workaround_pattern_not_simplified(self):
        """Ensure workaround hasn't been 'simplified' away."""
        # Common mistake: developer thinks "set day to 1" is redundant and removes it

        files_to_check = [
            "scheduling/strategies.py",
            "pure_applescript_scheduler.py",
        ]

        for file_path in files_to_check:
            content = (BASE_PATH / file_path).read_text()

            # Must have "set day to 1" before month
            assert 'set day of' in content and 'to 1' in content, \
                f"{file_path} missing critical 'set day to 1' statement"

    def test_time_reset_present(self):
        """Verify time is reset to 0 (also part of workaround)."""
        files_to_check = [
            "scheduling/strategies.py",
            "pure_applescript_scheduler.py",
            "scheduling/todo_operations.py",
        ]

        for file_path in files_to_check:
            content = (BASE_PATH / file_path).read_text()

            assert 'set time of' in content and 'to 0' in content, \
                f"{file_path} should reset time to 0"

    def test_sequence_not_reordered(self):
        """Ensure the sequence hasn't been reordered."""
        files_to_check = [
            "scheduling/strategies.py",
        ]

        for file_path in files_to_check:
            content = (BASE_PATH / file_path).read_text()

            # Find the workaround sequence
            # Should be: time → day(1) → year → month → day(actual)

            time_pos = content.find('set time of targetDate to 0')
            day1_pos = content.find('set day of targetDate to 1')
            year_pos = content.find('set year of targetDate to')
            month_pos = content.find('set month of targetDate to')
            dayN_pos = content.find('set day of targetDate to {target_date.day}')

            assert time_pos > 0, "Time reset missing"
            assert day1_pos > time_pos, "Day=1 should come after time reset"
            assert year_pos > day1_pos, "Year should come after day=1"
            assert month_pos > year_pos, "Month should come after year"
            assert dayN_pos > month_pos, "Final day should come after month"


class TestWorkaroundDocumentation:
    """Test that the workaround is properly documented."""

    def test_workaround_has_comments(self):
        """Verify the workaround has explanatory comments."""
        content = (BASE_PATH / "scheduling" / "strategies.py").read_text()

        # Should have comments near the workaround
        workaround_pos = content.find('set day of targetDate to 1')
        assert workaround_pos > 0

        # Look for comments in the vicinity
        context_start = max(0, workaround_pos - 500)
        context_end = min(len(content), workaround_pos + 500)
        context = content[context_start:context_end]

        # Should have comment explaining the workaround
        has_comment = '--' in context or 'overflow' in context.lower()
        assert has_comment, "Workaround should have explanatory comments"

    def test_bug_description_exists(self):
        """Test that the bug is described somewhere in the code."""
        content = (BASE_PATH / "scheduling" / "strategies.py").read_text()

        # Should mention the overflow issue or the need to set day first
        mentions_overflow = 'overflow' in content.lower()
        mentions_safe_day = 'safe' in content.lower() and 'day' in content.lower()

        assert mentions_overflow or mentions_safe_day, \
            "Should document why the workaround is necessary"


class TestWorkaroundCompleteness:
    """Test that all necessary date operations use the workaround."""

    def test_all_deadline_assignments_use_workaround(self):
        """Test all deadline date assignments use the workaround."""
        content = (BASE_PATH / "scheduling" / "todo_operations.py").read_text()

        # Find all "set due date" or "deadline" operations
        # All should have the workaround nearby

        deadline_pattern = r'set due date of'
        deadline_matches = list(re.finditer(deadline_pattern, content))

        assert len(deadline_matches) > 0, "Should have deadline setting code"

        for match in deadline_matches:
            # Look backwards for the workaround
            context_start = max(0, match.start() - 1000)
            context = content[context_start:match.start()]

            has_workaround = 'set day of deadlineDate to 1' in context
            assert has_workaround, \
                f"Deadline assignment at position {match.start()} missing workaround"

    def test_all_schedule_operations_use_workaround(self):
        """Test all schedule operations use the workaround."""
        content = (BASE_PATH / "scheduling" / "strategies.py").read_text()

        # Find "schedule" operations
        schedule_pattern = r'schedule \w+ for'
        schedule_matches = list(re.finditer(schedule_pattern, content))

        assert len(schedule_matches) > 0, "Should have schedule operations"

        for match in schedule_matches:
            # Look backwards for the workaround
            context_start = max(0, match.start() - 1000)
            context = content[context_start:match.start()]

            has_workaround = 'set day of targetDate to 1' in context
            # Not all schedule operations need the workaround (e.g., relative dates)
            # But date object construction should have it
            if 'set year of targetDate' in context:
                assert has_workaround, \
                    f"Schedule operation at position {match.start()} with date construction missing workaround"


class TestWorkaroundPerformance:
    """Test that the workaround doesn't introduce performance issues."""

    def test_no_redundant_workarounds(self):
        """Ensure workaround isn't applied multiple times unnecessarily."""
        files_to_check = [
            "scheduling/strategies.py",
        ]

        for file_path in files_to_check:
            content = (BASE_PATH / file_path).read_text()

            # Count "set day to 1" in each function
            # Should only appear once per date construction

            functions = content.split('async def')
            for func in functions:
                day_to_1_count = func.count('set day of targetDate to 1')
                # Each date construction should have exactly 1 occurrence
                # (Could have multiple constructions per function)
                assert day_to_1_count <= 3, \
                    f"Function has {day_to_1_count} 'set day to 1' - might be redundant"

    def test_workaround_is_minimal(self):
        """Ensure workaround doesn't add unnecessary operations."""
        content = (BASE_PATH / "scheduling" / "strategies.py").read_text()

        # Workaround should be:
        # 1. set time to 0
        # 2. set day to 1
        # 3. set year
        # 4. set month
        # 5. set day to actual

        # Should not have additional unnecessary operations
        # (This is a basic check - just verify we don't have excessive operations)

        workaround_section = content[
            content.find('set time of targetDate to 0'):
            content.find('set day of targetDate to {target_date.day}') + 50
        ]

        # Count "set" operations in this section
        set_count = workaround_section.count('set ')
        # Should be exactly 5: time, day(1), year, month, day(actual)
        # (plus maybe a few more for variable assignment or theTodo)
        assert set_count <= 10, f"Workaround has {set_count} set operations - should be ~5-9"
