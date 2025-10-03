"""
Test data fixtures for locale-aware date handling tests.

This module contains comprehensive test data for validating date parsing,
formatting, and conversion functionality.
"""

from datetime import datetime, date, timedelta
from typing import List, Tuple, Dict, Any


# ISO Date Formats
ISO_DATES_VALID = [
    ("2025-01-15", (2025, 1, 15)),
    ("2025-12-31", (2025, 12, 31)),
    ("2025-02-28", (2025, 2, 28)),
    ("2024-02-29", (2024, 2, 29)),  # Leap year
    ("2000-02-29", (2000, 2, 29)),  # Leap year
    ("1900-01-01", (1900, 1, 1)),   # Boundary year
    ("2099-12-31", (2099, 12, 31)), # Boundary year
    ("2025-06-15", (2025, 6, 15)),
    ("2025-07-04", (2025, 7, 4)),
    ("2025-11-23", (2025, 11, 23)),
]

ISO_DATES_INVALID = [
    "2025-13-01",      # Invalid month (13)
    "2025-02-30",      # Invalid day for February
    "2025-04-31",      # Invalid day for April (only 30 days)
    "2025-00-15",      # Invalid month (0)
    "2025-01-00",      # Invalid day (0)
    "2025-01-32",      # Invalid day (32)
    "2023-02-29",      # Not a leap year
    "25-01-15",        # Wrong year format
    "2025-1-15",       # Missing zero padding (should still be handled)
    "abcd-01-15",      # Non-numeric year
    "2025-ab-15",      # Non-numeric month
    "2025-01-xy",      # Non-numeric day
    "",                # Empty string
    "not-a-date",      # Complete garbage
]

# Natural Language Keywords
NATURAL_LANGUAGE_DATES = [
    ("today", 0),
    ("tomorrow", 1),
    ("yesterday", -1),
    ("Today", 0),          # Case variation
    ("TOMORROW", 1),       # Case variation
    ("YeStErDaY", -1),     # Case variation
]

# Things 3 specific keywords
THINGS_KEYWORDS = [
    "someday",
    "anytime",
    "evening",
    "Someday",
    "ANYTIME",
]

# Relative Date Offsets
RELATIVE_OFFSETS_DAYS = [
    ("+1d", 1),
    ("+7d", 7),
    ("+30d", 30),
    ("-1d", -1),
    ("-7d", -7),
    ("+1 day", 1),
    ("+5 days", 5),
    ("-3 days", -3),
    ("+0d", 0),
    ("1d", 1),  # Implicit positive
]

RELATIVE_OFFSETS_WEEKS = [
    ("+1w", 7),
    ("+4w", 28),
    ("-1w", -7),
    ("+1 week", 7),
    ("+2 weeks", 14),
    ("-2 weeks", -14),
    ("1w", 7),  # Implicit positive
]

RELATIVE_OFFSETS_MONTHS = [
    ("+1m", 1),
    ("+6m", 6),
    ("+12m", 12),
    ("-1m", -1),
    ("-6m", -6),
    ("+1 month", 1),
    ("+3 months", 3),
    ("-2 months", -2),
    ("1m", 1),  # Implicit positive
]

RELATIVE_OFFSETS_INVALID = [
    "+d",       # Missing amount
    "+1x",      # Invalid unit
    "++1d",     # Double sign
    "+1.5d",    # Decimal not supported
    "1 d",      # Space in wrong place
    "d+1",      # Reversed order
]

# Month Names
MONTH_NAMES_FULL = [
    ("january", 1),
    ("february", 2),
    ("march", 3),
    ("april", 4),
    ("may", 5),
    ("june", 6),
    ("july", 7),
    ("august", 8),
    ("september", 9),
    ("october", 10),
    ("november", 11),
    ("december", 12),
]

MONTH_NAMES_ABBREVIATED = [
    ("jan", 1),
    ("feb", 2),
    ("mar", 3),
    ("apr", 4),
    ("may", 5),
    ("jun", 6),
    ("jul", 7),
    ("aug", 8),
    ("sep", 9),
    ("sept", 9),  # Alternative abbreviation
    ("oct", 10),
    ("nov", 11),
    ("dec", 12),
]

MONTH_NAMES_CASE_VARIATIONS = [
    ("JANUARY", 1),
    ("January", 1),
    ("JaNuArY", 1),
    ("DECEMBER", 12),
    ("December", 12),
    ("DeCeMbEr", 12),
]

# Natural Language Date Patterns
NATURAL_DATES_VALID = [
    ("January 15, 2025", (2025, 1, 15)),
    ("Jan 15 2025", (2025, 1, 15)),
    ("15 January 2025", (2025, 1, 15)),
    ("15 Jan 2025", (2025, 1, 15)),
    ("March 31, 2025", (2025, 3, 31)),
    ("December 25, 2024", (2024, 12, 25)),
    ("Feb 29, 2024", (2024, 2, 29)),  # Leap year
]

# AppleScript Output Samples
APPLESCRIPT_OUTPUTS = [
    ('date "Wednesday, January 15, 2025 at 12:00:00 AM"', (2025, 1, 15)),
    ('date "Tuesday, December 31, 2024 at 11:59:59 PM"', (2024, 12, 31)),
    ('date "Thursday, February 29, 2024 at 3:30:00 PM"', (2024, 2, 29)),
    ("2025-01-15", (2025, 1, 15)),  # ISO format
    ("01/15/2025", (2025, 1, 15)),  # US format
    ("15.01.2025", (2025, 1, 15)),  # EU format
    ("year: 2025 month: 1 day: 15", (2025, 1, 15)),  # Property format
    ("January 15, 2025", (2025, 1, 15)),  # Natural language
]

APPLESCRIPT_OUTPUTS_INVALID = [
    "missing value",
    "",
    "   ",
    None,
    "invalid date string",
    "date \"not a real date\"",
]

# Edge Cases
EDGE_CASES_DATES = [
    # Leap years
    ("2024-02-29", (2024, 2, 29), True),   # Valid leap year
    ("2023-02-29", None, False),            # Invalid - not a leap year
    ("2000-02-29", (2000, 2, 29), True),   # Valid - divisible by 400
    ("1900-02-29", None, False),            # Invalid - not divisible by 400

    # Month boundaries
    ("2025-01-31", (2025, 1, 31), True),   # January has 31 days
    ("2025-02-28", (2025, 2, 28), True),   # February has 28 days
    ("2025-03-31", (2025, 3, 31), True),   # March has 31 days
    ("2025-04-30", (2025, 4, 30), True),   # April has 30 days
    ("2025-04-31", None, False),            # April doesn't have 31 days

    # Year boundaries
    ("1900-01-01", (1900, 1, 1), True),    # Minimum year
    ("2099-12-31", (2099, 12, 31), True),  # Maximum year
    ("1899-12-31", None, False),            # Before minimum
    ("2100-01-01", None, False),            # After maximum
]

# Month Overflow Cases (for relative month arithmetic)
MONTH_OVERFLOW_CASES = [
    # Starting from Jan 31, adding 1 month should give Feb 28/29 (last day of Feb)
    ((2025, 1, 31), 1, (2025, 2, 28)),
    ((2024, 1, 31), 1, (2024, 2, 29)),  # Leap year

    # Starting from Aug 31, adding 1 month should give Sep 30 (last day of Sep)
    ((2025, 8, 31), 1, (2025, 9, 30)),

    # Year rollover
    ((2025, 12, 15), 1, (2026, 1, 15)),
    ((2025, 1, 15), -1, (2024, 12, 15)),

    # Multiple month overflow
    ((2025, 1, 31), 3, (2025, 4, 30)),  # Jan 31 + 3 months = Apr 30
    ((2025, 10, 31), 4, (2026, 2, 28)), # Oct 31 + 4 months = Feb 28
]

# US Date Formats
US_DATES_VALID = [
    ("1/15/2025", (2025, 1, 15)),
    ("12/31/2025", (2025, 12, 31)),
    ("2/29/2024", (2024, 2, 29)),
    ("06/15/2025", (2025, 6, 15)),
]

# European Date Formats
EU_DATES_VALID = [
    ("15.1.2025", (2025, 1, 15)),
    ("31.12.2025", (2025, 12, 31)),
    ("29.2.2024", (2024, 2, 29)),
    ("15.06.2025", (2025, 6, 15)),
]

# Timezone Handling (should be stripped/ignored)
DATES_WITH_TIMEZONES = [
    ("2025-01-15T14:30:00Z", (2025, 1, 15)),
    ("2025-01-15T14:30:00-08:00", (2025, 1, 15)),
    ("2025-01-15T14:30:00+05:30", (2025, 1, 15)),
]

# Empty/Null Cases
EMPTY_NULL_CASES = [
    None,
    "",
    "   ",
    "none",
    "null",
    "None",
    "NULL",
]

# Ambiguous Dates (could be interpreted multiple ways)
AMBIGUOUS_DATES = [
    "01-02-2025",  # Could be Jan 2 or Feb 1
    "03/04/2025",  # Could be Mar 4 or Apr 3
    "12/12/2025",  # Month and day are same
]


def get_current_date_components() -> Tuple[int, int, int]:
    """Get current date as components tuple."""
    today = datetime.now().date()
    return (today.year, today.month, today.day)


def calculate_relative_date(days_offset: int) -> Tuple[int, int, int]:
    """Calculate date components for relative offset from today."""
    target = datetime.now().date() + timedelta(days=days_offset)
    return (target.year, target.month, target.day)


def is_leap_year(year: int) -> bool:
    """Check if year is a leap year."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)
