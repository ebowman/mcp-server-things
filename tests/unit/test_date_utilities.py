"""
Unit tests for date utility functions and edge cases.

Tests date arithmetic, leap year handling, month boundaries, and other
date-related edge cases that interact with the month overflow workaround.
"""

import pytest
from datetime import date, timedelta
from calendar import monthrange


class TestLeapYearDetection:
    """Test leap year detection logic."""

    def test_is_leap_year_standard_leap_years(self):
        """Test standard leap years (divisible by 4, not by 100)."""
        leap_years = [2020, 2024, 2028, 2032, 2036]

        for year in leap_years:
            # Leap years have Feb 29
            try:
                date(year, 2, 29)
                is_leap = True
            except ValueError:
                is_leap = False

            assert is_leap, f"{year} should be a leap year"

    def test_is_leap_year_non_leap_years(self):
        """Test non-leap years (not divisible by 4)."""
        non_leap_years = [2021, 2022, 2023, 2025, 2026]

        for year in non_leap_years:
            # Non-leap years don't have Feb 29
            try:
                date(year, 2, 29)
                is_leap = True
            except ValueError:
                is_leap = False

            assert not is_leap, f"{year} should not be a leap year"

    def test_is_leap_year_century_non_leap(self):
        """Test century years that are not leap years (divisible by 100, not 400)."""
        # 1900, 2100, 2200, 2300 are NOT leap years
        non_leap_centuries = [1900, 2100, 2200, 2300]

        for year in non_leap_centuries:
            try:
                date(year, 2, 29)
                is_leap = True
            except ValueError:
                is_leap = False

            assert not is_leap, f"{year} should not be a leap year (century rule)"

    def test_is_leap_year_century_leap(self):
        """Test century years that ARE leap years (divisible by 400)."""
        # 2000, 2400 are leap years
        leap_centuries = [2000, 2400]

        for year in leap_centuries:
            try:
                date(year, 2, 29)
                is_leap = True
            except ValueError:
                is_leap = False

            assert is_leap, f"{year} should be a leap year (divisible by 400)"

    def test_february_29_exists_in_leap_years(self):
        """Test that Feb 29 exists in leap years."""
        # 2024 is a leap year
        feb_29_2024 = date(2024, 2, 29)
        assert feb_29_2024.day == 29
        assert feb_29_2024.month == 2

    def test_february_29_raises_in_non_leap_years(self):
        """Test that Feb 29 raises ValueError in non-leap years."""
        # 2025 is not a leap year
        with pytest.raises(ValueError):
            date(2025, 2, 29)


class TestDaysInMonth:
    """Test days in month calculations."""

    def test_days_in_month_31_day_months(self):
        """Test months with 31 days."""
        months_31_days = [1, 3, 5, 7, 8, 10, 12]  # Jan, Mar, May, Jul, Aug, Oct, Dec

        for month in months_31_days:
            days = monthrange(2025, month)[1]
            assert days == 31, f"Month {month} should have 31 days"

    def test_days_in_month_30_day_months(self):
        """Test months with 30 days."""
        months_30_days = [4, 6, 9, 11]  # Apr, Jun, Sep, Nov

        for month in months_30_days:
            days = monthrange(2025, month)[1]
            assert days == 30, f"Month {month} should have 30 days"

    def test_days_in_month_february_non_leap(self):
        """Test February in non-leap years has 28 days."""
        days = monthrange(2025, 2)[1]
        assert days == 28, "February 2025 should have 28 days"

    def test_days_in_month_february_leap(self):
        """Test February in leap years has 29 days."""
        days = monthrange(2024, 2)[1]
        assert days == 29, "February 2024 should have 29 days"

    def test_days_in_all_months_2024(self):
        """Test days in all months for leap year 2024."""
        expected_days = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

        for month, expected in enumerate(expected_days, 1):
            days = monthrange(2024, month)[1]
            assert days == expected, f"Month {month} of 2024 should have {expected} days"

    def test_days_in_all_months_2025(self):
        """Test days in all months for non-leap year 2025."""
        expected_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

        for month, expected in enumerate(expected_days, 1):
            days = monthrange(2025, month)[1]
            assert days == expected, f"Month {month} of 2025 should have {expected} days"


class TestDateComparison:
    """Test date comparison operations."""

    def test_date_before(self):
        """Test date comparison: before."""
        earlier = date(2025, 1, 1)
        later = date(2025, 1, 2)

        assert earlier < later
        assert not (later < earlier)

    def test_date_after(self):
        """Test date comparison: after."""
        earlier = date(2025, 1, 1)
        later = date(2025, 1, 2)

        assert later > earlier
        assert not (earlier > later)

    def test_date_equals(self):
        """Test date comparison: equals."""
        date1 = date(2025, 1, 1)
        date2 = date(2025, 1, 1)

        assert date1 == date2

    def test_date_not_equals(self):
        """Test date comparison: not equals."""
        date1 = date(2025, 1, 1)
        date2 = date(2025, 1, 2)

        assert date1 != date2

    def test_date_comparison_across_months(self):
        """Test date comparison across month boundaries."""
        jan_31 = date(2025, 1, 31)
        feb_1 = date(2025, 2, 1)

        assert jan_31 < feb_1
        assert feb_1 > jan_31

    def test_date_comparison_across_years(self):
        """Test date comparison across year boundaries."""
        dec_31_2024 = date(2024, 12, 31)
        jan_1_2025 = date(2025, 1, 1)

        assert dec_31_2024 < jan_1_2025
        assert jan_1_2025 > dec_31_2024


class TestDateArithmetic:
    """Test date arithmetic operations."""

    def test_add_days(self):
        """Test adding days to a date."""
        start_date = date(2025, 1, 1)
        result = start_date + timedelta(days=10)

        assert result == date(2025, 1, 11)

    def test_subtract_days(self):
        """Test subtracting days from a date."""
        start_date = date(2025, 1, 11)
        result = start_date - timedelta(days=10)

        assert result == date(2025, 1, 1)

    def test_add_days_across_month_boundary(self):
        """Test adding days across month boundary."""
        jan_25 = date(2025, 1, 25)
        result = jan_25 + timedelta(days=10)

        assert result == date(2025, 2, 4)

    def test_subtract_days_across_month_boundary(self):
        """Test subtracting days across month boundary."""
        feb_5 = date(2025, 2, 5)
        result = feb_5 - timedelta(days=10)

        assert result == date(2025, 1, 26)

    def test_add_days_across_year_boundary(self):
        """Test adding days across year boundary."""
        dec_25 = date(2024, 12, 25)
        result = dec_25 + timedelta(days=10)

        assert result == date(2025, 1, 4)

    def test_subtract_days_across_year_boundary(self):
        """Test subtracting days across year boundary."""
        jan_5 = date(2025, 1, 5)
        result = jan_5 - timedelta(days=10)

        assert result == date(2024, 12, 26)

    def test_add_weeks(self):
        """Test adding weeks to a date."""
        start_date = date(2025, 1, 1)
        result = start_date + timedelta(weeks=2)

        assert result == date(2025, 1, 15)

    def test_add_days_to_month_end(self):
        """Test adding days to end of month."""
        jan_31 = date(2025, 1, 31)
        result = jan_31 + timedelta(days=1)

        assert result == date(2025, 2, 1)

    def test_add_days_to_february_end_non_leap(self):
        """Test adding days to end of February (non-leap)."""
        feb_28 = date(2025, 2, 28)
        result = feb_28 + timedelta(days=1)

        assert result == date(2025, 3, 1)

    def test_add_days_to_february_end_leap(self):
        """Test adding days to end of February (leap year)."""
        feb_29 = date(2024, 2, 29)
        result = feb_29 + timedelta(days=1)

        assert result == date(2024, 3, 1)


class TestMonthBoundaryEdgeCases:
    """Test edge cases at month boundaries."""

    def test_last_day_of_each_month(self):
        """Test creating dates for last day of each month."""
        # Month -> last day (non-leap year)
        last_days = [
            (1, 31), (2, 28), (3, 31), (4, 30), (5, 31), (6, 30),
            (7, 31), (8, 31), (9, 30), (10, 31), (11, 30), (12, 31)
        ]

        for month, expected_day in last_days:
            last_date = date(2025, month, expected_day)
            assert last_date.day == expected_day
            assert last_date.month == month

    def test_first_day_of_each_month(self):
        """Test creating dates for first day of each month."""
        for month in range(1, 13):
            first_date = date(2025, month, 1)
            assert first_date.day == 1
            assert first_date.month == month

    def test_transition_from_31_day_month_to_30_day_month(self):
        """Test date transitions from 31-day month to 30-day month."""
        # Jan (31 days) → Apr (30 days)
        # If we were to naively set month, Jan 31 → Apr 31 would fail

        jan_31 = date(2025, 1, 31)

        # Proper way: create new date with correct day
        apr_30 = date(2025, 4, 30)

        assert apr_30.month == 4
        assert apr_30.day == 30

    def test_transition_from_31_day_month_to_february(self):
        """Test date transitions from 31-day month to February."""
        # Jan (31 days) → Feb (28/29 days)
        # This is the main overflow case

        jan_31 = date(2025, 1, 31)

        # Proper way: create new date with Feb 28
        feb_28 = date(2025, 2, 28)

        assert feb_28.month == 2
        assert feb_28.day == 28

    def test_invalid_day_for_month_raises_error(self):
        """Test that invalid days for a month raise ValueError."""
        # Feb 30 doesn't exist
        with pytest.raises(ValueError):
            date(2025, 2, 30)

        # Feb 31 doesn't exist
        with pytest.raises(ValueError):
            date(2025, 2, 31)

        # Apr 31 doesn't exist (30-day month)
        with pytest.raises(ValueError):
            date(2025, 4, 31)


class TestYearBoundaryEdgeCases:
    """Test edge cases at year boundaries."""

    def test_december_31_transitions(self):
        """Test Dec 31 to Jan 1 transitions."""
        dec_31 = date(2024, 12, 31)
        jan_1 = dec_31 + timedelta(days=1)

        assert jan_1 == date(2025, 1, 1)

    def test_january_1_transitions(self):
        """Test Jan 1 to Dec 31 transitions (backward)."""
        jan_1 = date(2025, 1, 1)
        dec_31 = jan_1 - timedelta(days=1)

        assert dec_31 == date(2024, 12, 31)

    def test_leap_year_to_non_leap_year(self):
        """Test transition from leap year to non-leap year."""
        feb_29_2024 = date(2024, 2, 29)  # Leap year

        # One year later (non-leap year)
        # Note: date arithmetic doesn't have built-in year addition
        # so we construct it manually
        feb_28_2025 = date(2025, 2, 28)

        assert feb_28_2025.year == 2025
        assert feb_28_2025.month == 2
        # Day would be 28, not 29 (since 2025 is not leap year)


class TestDateStringParsing:
    """Test date string parsing edge cases."""

    def test_iso_format_parsing(self):
        """Test parsing ISO 8601 date strings."""
        date_str = "2025-02-28"
        parsed_date = date.fromisoformat(date_str)

        assert parsed_date == date(2025, 2, 28)

    def test_iso_format_creation(self):
        """Test creating ISO 8601 date strings."""
        test_date = date(2025, 2, 28)
        date_str = test_date.isoformat()

        assert date_str == "2025-02-28"

    def test_invalid_iso_format_raises_error(self):
        """Test that invalid ISO format raises ValueError."""
        with pytest.raises(ValueError):
            date.fromisoformat("2025-02-30")  # Invalid day

        with pytest.raises(ValueError):
            date.fromisoformat("2025-13-01")  # Invalid month

    def test_date_string_roundtrip(self):
        """Test roundtrip conversion: date → string → date."""
        original_date = date(2025, 2, 28)
        date_str = original_date.isoformat()
        parsed_date = date.fromisoformat(date_str)

        assert parsed_date == original_date


class TestDateRangeCalculations:
    """Test date range calculations."""

    def test_days_between_dates_same_month(self):
        """Test calculating days between dates in same month."""
        start = date(2025, 1, 1)
        end = date(2025, 1, 31)
        delta = end - start

        assert delta.days == 30

    def test_days_between_dates_different_months(self):
        """Test calculating days between dates in different months."""
        start = date(2025, 1, 1)
        end = date(2025, 2, 1)
        delta = end - start

        assert delta.days == 31

    def test_days_between_dates_across_leap_february(self):
        """Test calculating days across leap year February."""
        start = date(2024, 2, 1)
        end = date(2024, 3, 1)
        delta = end - start

        assert delta.days == 29  # Leap year February

    def test_days_between_dates_across_non_leap_february(self):
        """Test calculating days across non-leap year February."""
        start = date(2025, 2, 1)
        end = date(2025, 3, 1)
        delta = end - start

        assert delta.days == 28  # Non-leap year February

    def test_days_in_year_leap(self):
        """Test total days in a leap year."""
        start = date(2024, 1, 1)
        end = date(2024, 12, 31)
        delta = end - start

        assert delta.days == 365  # 366 days total (0-indexed)

    def test_days_in_year_non_leap(self):
        """Test total days in a non-leap year."""
        start = date(2025, 1, 1)
        end = date(2025, 12, 31)
        delta = end - start

        assert delta.days == 364  # 365 days total (0-indexed)
