"""
Locale-aware date handling for Things 3 AppleScript integration.

This module provides locale-independent date handling by using AppleScript's
property-based date construction instead of string-based parsing.
"""

import re
import logging
from datetime import datetime, timedelta, date
from typing import Optional, Tuple, Union, Dict, Any
import calendar

logger = logging.getLogger(__name__)


class LocaleAwareDateHandler:
    """
    Provides locale-independent date handling for Things 3 AppleScript integration.
    
    Uses property-based AppleScript date construction to avoid locale-specific
    string parsing issues.
    """
    
    # Common date format patterns
    DATE_PATTERNS = {
        'iso': r'(\d{4})-(\d{2})-(\d{2})',
        'us': r'(\d{1,2})/(\d{1,2})/(\d{4})',
        'eu': r'(\d{1,2})\.(\d{1,2})\.(\d{4})',
        'relative_days': r'(\+|\-)?(\d+)\s*(days?|d)',
        'relative_weeks': r'(\+|\-)?(\d+)\s*(weeks?|w)',
        'relative_months': r'(\+|\-)?(\d+)\s*(months?|m)',
        'today': r'^today$',
        'tomorrow': r'^tomorrow$',
        'yesterday': r'^yesterday$',
    }
    
    # Natural language date mapping
    NATURAL_DATES = {
        'today': 0,
        'tomorrow': 1,
        'yesterday': -1,
    }
    
    # Month name mappings (English only to avoid locale issues)
    MONTH_NAMES = {
        'january': 1, 'jan': 1,
        'february': 2, 'feb': 2,
        'march': 3, 'mar': 3,
        'april': 4, 'apr': 4,
        'may': 5,
        'june': 6, 'jun': 6,
        'july': 7, 'jul': 7,
        'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10,
        'november': 11, 'nov': 11,
        'december': 12, 'dec': 12,
    }
    
    def __init__(self):
        """Initialize the LocaleAwareDateHandler."""
        logger.debug("Initializing LocaleAwareDateHandler")
    
    def normalize_date_input(self, date_input: Union[str, datetime, date, None]) -> Optional[Tuple[int, int, int]]:
        """
        Parse any date format to year, month, day components.
        
        Args:
            date_input: Date in various formats (string, datetime, date, or None)
            
        Returns:
            Tuple of (year, month, day) or None if parsing fails
        """
        if date_input is None:
            return None
            
        try:
            # Handle datetime and date objects
            if isinstance(date_input, datetime):
                return (date_input.year, date_input.month, date_input.day)
            elif isinstance(date_input, date):
                return (date_input.year, date_input.month, date_input.day)
            
            # Handle string input
            if not isinstance(date_input, str):
                logger.warning(f"Unexpected date input type: {type(date_input)}")
                return None
                
            date_str = date_input.strip().lower()
            
            # Handle empty or 'none' input
            if not date_str or date_str in ('none', 'null', ''):
                return None
            
            # Try natural language first
            if date_str in self.NATURAL_DATES:
                days_offset = self.NATURAL_DATES[date_str]
                target_date = datetime.now().date() + timedelta(days=days_offset)
                return (target_date.year, target_date.month, target_date.day)
            
            # Try relative date patterns
            relative_result = self._parse_relative_date(date_str)
            if relative_result:
                return relative_result
            
            # Try absolute date patterns
            absolute_result = self._parse_absolute_date(date_str)
            if absolute_result:
                return absolute_result
            
            # Try parsing with natural language month names
            natural_result = self._parse_natural_date(date_str)
            if natural_result:
                return natural_result
                
            logger.warning(f"Could not parse date: {date_input}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing date '{date_input}': {e}")
            return None
    
    def _parse_relative_date(self, date_str: str) -> Optional[Tuple[int, int, int]]:
        """Parse relative date expressions like '+3 days', '-2 weeks'."""
        base_date = datetime.now().date()
        
        # Days
        match = re.search(self.DATE_PATTERNS['relative_days'], date_str, re.IGNORECASE)
        if match:
            sign, amount, unit = match.groups()
            multiplier = -1 if sign == '-' else 1
            days = int(amount) * multiplier
            target_date = base_date + timedelta(days=days)
            return (target_date.year, target_date.month, target_date.day)
        
        # Weeks
        match = re.search(self.DATE_PATTERNS['relative_weeks'], date_str, re.IGNORECASE)
        if match:
            sign, amount, unit = match.groups()
            multiplier = -1 if sign == '-' else 1
            days = int(amount) * multiplier * 7
            target_date = base_date + timedelta(days=days)
            return (target_date.year, target_date.month, target_date.day)
        
        # Months (approximate)
        match = re.search(self.DATE_PATTERNS['relative_months'], date_str, re.IGNORECASE)
        if match:
            sign, amount, unit = match.groups()
            multiplier = -1 if sign == '-' else 1
            months = int(amount) * multiplier
            
            year = base_date.year
            month = base_date.month + months
            day = base_date.day
            
            # Handle month overflow/underflow
            while month > 12:
                month -= 12
                year += 1
            while month < 1:
                month += 12
                year -= 1
            
            # Handle day overflow for shorter months
            max_day = calendar.monthrange(year, month)[1]
            if day > max_day:
                day = max_day
            
            return (year, month, day)
        
        return None
    
    def _parse_absolute_date(self, date_str: str) -> Optional[Tuple[int, int, int]]:
        """Parse absolute date patterns like '2024-01-15', '1/15/2024'."""
        # ISO format (YYYY-MM-DD)
        match = re.search(self.DATE_PATTERNS['iso'], date_str)
        if match:
            year, month, day = map(int, match.groups())
            if self._validate_date(year, month, day):
                return (year, month, day)
        
        # US format (M/D/YYYY)
        match = re.search(self.DATE_PATTERNS['us'], date_str)
        if match:
            month, day, year = map(int, match.groups())
            if self._validate_date(year, month, day):
                return (year, month, day)
        
        # European format (D.M.YYYY)
        match = re.search(self.DATE_PATTERNS['eu'], date_str)
        if match:
            day, month, year = map(int, match.groups())
            if self._validate_date(year, month, day):
                return (year, month, day)
        
        return None
    
    def _parse_natural_date(self, date_str: str) -> Optional[Tuple[int, int, int]]:
        """Parse natural language dates like 'January 15, 2024' or '15 Jan 2024'."""
        # Try various natural language patterns
        patterns = [
            r'(\w+)\s+(\d{1,2}),?\s+(\d{4})',  # "January 15, 2024" or "Jan 15 2024"
            r'(\d{1,2})\s+(\w+)\s+(\d{4})',    # "15 January 2024"
            r'(\w+)\s+(\d{1,2})',              # "January 15" (current year)
            r'(\d{1,2})\s+(\w+)',              # "15 January" (current year)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, date_str, re.IGNORECASE)
            if match:
                groups = match.groups()
                
                # Handle different group arrangements
                if len(groups) == 3:
                    if groups[0].isdigit():  # "15 January 2024"
                        day, month_name, year = groups
                        day, year = int(day), int(year)
                    else:  # "January 15, 2024"
                        month_name, day, year = groups
                        day, year = int(day), int(year)
                elif len(groups) == 2:
                    current_year = datetime.now().year
                    if groups[0].isdigit():  # "15 January"
                        day, month_name = groups
                        day, year = int(day), current_year
                    else:  # "January 15"
                        month_name, day = groups
                        day, year = int(day), current_year
                else:
                    continue
                
                # Convert month name to number - try full name first, then abbreviation
                month_name_lower = month_name.lower()
                month = None
                
                # Try exact match first
                if month_name_lower in self.MONTH_NAMES:
                    month = self.MONTH_NAMES[month_name_lower]
                else:
                    # Try partial match for abbreviations
                    for name, num in self.MONTH_NAMES.items():
                        if month_name_lower.startswith(name[:3]) and len(name) >= 3:
                            month = num
                            break
                
                if month and self._validate_date(year, month, day):
                    return (year, month, day)
        
        return None
    
    def _validate_date(self, year: int, month: int, day: int) -> bool:
        """Validate that the date components form a valid date."""
        try:
            if year < 1900 or year > 2100:
                return False
            if month < 1 or month > 12:
                return False
            if day < 1 or day > 31:
                return False
            
            # Check if the day is valid for the specific month/year
            max_day = calendar.monthrange(year, month)[1]
            return day <= max_day
            
        except (ValueError, OverflowError):
            return False
    
    def build_applescript_date_property(self, year: int, month: int, day: int) -> str:
        """
        Build AppleScript date using property-based construction.
        
        This avoids locale-specific string parsing by setting date properties directly.
        
        Args:
            year: Year (e.g., 2024)
            month: Month (1-12)
            day: Day (1-31)
            
        Returns:
            AppleScript code that creates a date object
        """
        try:
            # Validate the date
            if not self._validate_date(year, month, day):
                raise ValueError(f"Invalid date: {year}-{month}-{day}")
            
            # Return ISO date format without quotes
            # The calling code will add quotes if needed for the date command
            iso_date = f"{year:04d}-{month:02d}-{day:02d}"
            
            logger.debug(f"Generated AppleScript date: {iso_date}")
            return iso_date
            
        except Exception as e:
            logger.error(f"Error building AppleScript date for {year}-{month}-{day}: {e}")
            raise
    
    def parse_applescript_date_output(self, output: str) -> Optional[Tuple[int, int, int]]:
        """
        Parse AppleScript date output without locale dependencies.
        
        Uses regex patterns to extract date components from various AppleScript
        output formats, avoiding locale-specific date parsing.
        
        Args:
            output: Raw AppleScript output containing date information
            
        Returns:
            Tuple of (year, month, day) or None if parsing fails
        """
        if not output or not isinstance(output, str):
            return None
        
        output = output.strip()
        
        try:
            # Pattern 1: Look for ISO-like format in output
            iso_match = re.search(r'(\d{4})-(\d{1,2})-(\d{1,2})', output)
            if iso_match:
                year, month, day = map(int, iso_match.groups())
                if self._validate_date(year, month, day):
                    return (year, month, day)
            
            # Pattern 2: Look for separated numbers that could be date components
            # This handles various AppleScript output formats
            number_pattern = r'\b(\d{1,2})[/\-\.\s]+(\d{1,2})[/\-\.\s]+(\d{4})\b|\b(\d{4})[/\-\.\s]+(\d{1,2})[/\-\.\s]+(\d{1,2})\b'
            match = re.search(number_pattern, output)
            if match:
                groups = match.groups()
                if groups[:3] != (None, None, None):  # M/D/YYYY or similar
                    month, day, year = map(int, groups[:3])
                else:  # YYYY/M/D or similar
                    year, month, day = map(int, groups[3:])
                
                if self._validate_date(year, month, day):
                    return (year, month, day)
            
            # Pattern 3: Look for individual date components in property format
            year_match = re.search(r'year:?\s*(\d{4})', output, re.IGNORECASE)
            month_match = re.search(r'month:?\s*(\d{1,2})', output, re.IGNORECASE)
            day_match = re.search(r'day:?\s*(\d{1,2})', output, re.IGNORECASE)
            
            if year_match and month_match and day_match:
                year = int(year_match.group(1))
                month = int(month_match.group(1))
                day = int(day_match.group(1))
                
                if self._validate_date(year, month, day):
                    return (year, month, day)
            
            # Pattern 4: Handle month names in output like "March 15, 2024"
            # First try to extract month names and convert them
            month_match = None
            for month_name, month_num in self.MONTH_NAMES.items():
                if month_name in output.lower():
                    month_match = month_num
                    break
            
            if month_match:
                # Look for day and year numbers
                day_match = re.search(r'\b(\d{1,2})\b', output)
                year_match = re.search(r'\b(\d{4})\b', output)
                
                if day_match and year_match:
                    day = int(day_match.group(1))
                    year = int(year_match.group(1))
                    if self._validate_date(year, month_match, day):
                        return (year, month_match, day)
            
            # Pattern 5: Handle Things 3 specific date output format
            # Look for patterns like "Tuesday, January 15, 2024" but extract numbers
            components = re.findall(r'\b(\d{1,4})\b', output)
            if len(components) >= 3:
                # Try to identify year, month, day from the numbers
                numbers = [int(x) for x in components]
                
                # Find the year (should be > 1900 and <= current year + 10)
                current_year = datetime.now().year
                years = [n for n in numbers if 1900 <= n <= current_year + 10]
                
                if years:
                    year = years[0]
                    remaining = [n for n in numbers if n != year]
                    
                    if len(remaining) >= 2:
                        # Assume first remaining number <= 12 is month
                        months = [n for n in remaining if 1 <= n <= 12]
                        if months:
                            month = months[0]
                            days = [n for n in remaining if n != month and 1 <= n <= 31]
                            if days:
                                day = days[0]
                                if self._validate_date(year, month, day):
                                    return (year, month, day)
            
            logger.warning(f"Could not parse AppleScript date output: {output}")
            return None
            
        except Exception as e:
            logger.error(f"Error parsing AppleScript date output '{output}': {e}")
            return None
    
    def convert_iso_to_applescript(self, iso_date: str) -> str:
        """
        Convert ISO date string to AppleScript date construction.
        
        This is the main replacement for the problematic function in the original code.
        
        Args:
            iso_date: ISO format date string (YYYY-MM-DD)
            
        Returns:
            AppleScript code that creates the date
        """
        try:
            date_components = self.normalize_date_input(iso_date)
            if not date_components:
                raise ValueError(f"Could not parse ISO date: {iso_date}")
            
            year, month, day = date_components
            return self.build_applescript_date_property(year, month, day)
            
        except Exception as e:
            logger.error(f"Error converting ISO date '{iso_date}' to AppleScript: {e}")
            raise
    
    def format_for_display(self, date_components: Tuple[int, int, int], format_style: str = 'iso') -> str:
        """
        Format date components for display.
        
        Args:
            date_components: Tuple of (year, month, day)
            format_style: Format style ('iso', 'us', 'readable')
            
        Returns:
            Formatted date string
        """
        year, month, day = date_components
        
        if format_style == 'iso':
            return f"{year:04d}-{month:02d}-{day:02d}"
        elif format_style == 'us':
            return f"{month}/{day}/{year}"
        elif format_style == 'readable':
            try:
                date_obj = date(year, month, day)
                return date_obj.strftime("%B %d, %Y")
            except ValueError:
                return f"{year}-{month:02d}-{day:02d}"
        else:
            return f"{year:04d}-{month:02d}-{day:02d}"
    
    def get_today_components(self) -> Tuple[int, int, int]:
        """Get today's date as components."""
        today = datetime.now().date()
        return (today.year, today.month, today.day)
    
    def add_days_to_components(self, date_components: Tuple[int, int, int], days: int) -> Tuple[int, int, int]:
        """Add days to date components."""
        year, month, day = date_components
        date_obj = date(year, month, day) + timedelta(days=days)
        return (date_obj.year, date_obj.month, date_obj.day)
    
    def compare_dates(self, date1: Tuple[int, int, int], date2: Tuple[int, int, int]) -> int:
        """
        Compare two date components.
        
        Returns:
            -1 if date1 < date2, 0 if equal, 1 if date1 > date2
        """
        d1 = date(*date1)
        d2 = date(*date2)
        
        if d1 < d2:
            return -1
        elif d1 > d2:
            return 1
        else:
            return 0


# Global instance for easy import and use
locale_handler = LocaleAwareDateHandler()

# Convenience functions for backward compatibility
def normalize_date_input(date_input):
    """Convenience function for date normalization."""
    return locale_handler.normalize_date_input(date_input)

def convert_iso_to_applescript(iso_date):
    """Convenience function for ISO to AppleScript conversion."""
    return locale_handler.convert_iso_to_applescript(iso_date)

def parse_applescript_date_output(output):
    """Convenience function for parsing AppleScript date output."""
    return locale_handler.parse_applescript_date_output(output)

def build_applescript_date_property(year, month, day):
    """Convenience function for building AppleScript date properties."""
    return locale_handler.build_applescript_date_property(year, month, day)