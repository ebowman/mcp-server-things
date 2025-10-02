"""Scheduling helper utilities."""

import logging
from typing import Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SchedulingHelpers:
    """Utility methods for scheduling operations."""

    @staticmethod
    def convert_to_applescript_friendly_format(date_string: str) -> str:
        """
        Convert ISO date (YYYY-MM-DD) to AppleScript-friendly format.

        Args:
            date_string: ISO format date string

        Returns:
            AppleScript-friendly date string
        """
        try:
            parsed = datetime.strptime(date_string, '%Y-%m-%d')
            # Use MM/DD/YYYY for US locale compatibility
            return parsed.strftime('%m/%d/%Y')
        except ValueError:
            logger.warning(f"Could not parse date: {date_string}")
            return date_string

    @staticmethod
    def determine_target_list(when_date: str) -> str:
        """
        Determine appropriate Things list based on date string.

        Args:
            when_date: Date string (ISO or relative)

        Returns:
            Target list name
        """
        when_lower = when_date.lower().strip()

        # Handle relative dates
        if when_lower in ["today", "tonight"]:
            return "Today"
        elif when_lower == "tomorrow":
            return "Today"  # Tomorrow items should still appear in Today once activated
        elif when_lower in ["someday", "anytime"]:
            return "Someday"

        # Handle ISO dates
        try:
            target_date = datetime.strptime(when_date, '%Y-%m-%d').date()
            today = datetime.now().date()

            if target_date <= today:
                return "Today"
            elif target_date <= today + timedelta(days=7):
                return "Today"
            else:
                return "Upcoming"
        except ValueError:
            logger.warning(f"Could not parse date for list determination: {when_date}")
            return "Today"

    @staticmethod
    def parse_period_to_days(period: str) -> int:
        """
        Parse period string to number of days.

        Supported formats: '7d', '2w', '1m', '1y'

        Args:
            period: Period string

        Returns:
            Number of days

        Raises:
            ValueError: If period format is invalid
        """
        import re

        match = re.match(r'^(\d+)([dwmy])$', period.lower())
        if not match:
            raise ValueError(f"Invalid period format: {period}. Use format like '7d', '2w', '1m', '1y'")

        value, unit = match.groups()
        value = int(value)

        # Convert to days
        if unit == 'd':
            return value
        elif unit == 'w':
            return value * 7
        elif unit == 'm':
            return value * 30  # Approximate
        elif unit == 'y':
            return value * 365  # Approximate
        else:
            raise ValueError(f"Unknown period unit: {unit}")
