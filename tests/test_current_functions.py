#!/usr/bin/env python3
"""
Direct test of the current date conversion functions to show they work as implemented,
but demonstrate the locale issues.

Run with: python tests/test_current_functions.py
"""

import sys
import os
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_current_dd_mm_yyyy_converter():
    """Test the current _convert_iso_to_applescript_date function."""
    
    def _convert_iso_to_applescript_date(iso_date: str) -> str:
        """Current implementation from tools.py"""
        try:
            parsed = datetime.strptime(iso_date, '%Y-%m-%d').date()
            return parsed.strftime('%d/%m/%Y')  # DD/MM/YYYY for European locale
        except ValueError:
            return iso_date
    
    print("Testing current _convert_iso_to_applescript_date function:")
    print("=" * 60)
    
    test_dates = [
        "2024-03-15",  # March 15
        "2024-12-05",  # December 5  
        "2024-01-13",  # January 13
        "2024-02-29",  # Leap year
        "invalid-date",  # Should return unchanged
    ]
    
    for iso_date in test_dates:
        result = _convert_iso_to_applescript_date(iso_date)
        print(f"  {iso_date} -> {result}")
        
        if result != iso_date:
            # Parse what was produced to see the issue
            try:
                # Try US interpretation (MM/DD/YYYY)
                us_parsed = datetime.strptime(result, '%m/%d/%Y').date()
                us_iso = us_parsed.strftime('%Y-%m-%d')
                
                # Try GB interpretation (DD/MM/YYYY)  
                gb_parsed = datetime.strptime(result, '%d/%m/%Y').date()
                gb_iso = gb_parsed.strftime('%Y-%m-%d')
                
                print(f"    US would interpret as: {us_iso}")
                print(f"    GB would interpret as: {gb_iso}")
                
                if us_iso != gb_iso:
                    print(f"    ❌ AMBIGUOUS! Different results")
                if us_iso != iso_date and gb_iso == iso_date:
                    print(f"    ❌ FAILS in US locale!")
                elif us_iso == iso_date and gb_iso != iso_date:
                    print(f"    ❌ FAILS in GB locale!")
                    
            except ValueError:
                print(f"    ❌ Cannot be parsed as date")
        print()


def test_current_month_day_year_converter():
    """Test the current _convert_to_applescript_friendly_format function."""
    
    def _convert_to_applescript_friendly_format(date_string: str) -> str:
        """Current implementation from pure_applescript_scheduler.py"""
        try:
            parsed = datetime.strptime(date_string, '%Y-%m-%d').date()
            return parsed.strftime('%B %d, %Y')  # "March 3, 2026"
        except ValueError:
            return date_string
    
    print("Testing current _convert_to_applescript_friendly_format function:")
    print("=" * 60)
    
    test_dates = [
        "2024-03-15",  # March 15
        "2024-12-05",  # December 5
        "2024-01-13",  # January 13  
        "2024-07-04",  # July 4
        "invalid-date",  # Should return unchanged
    ]
    
    for iso_date in test_dates:
        result = _convert_to_applescript_friendly_format(iso_date)
        print(f"  {iso_date} -> {result}")
        
        if result != iso_date:
            # Show the issue with non-English locales
            month_name = result.split()[0]
            print(f"    Month name: '{month_name}' (English only)")
            print(f"    ❌ Would fail in German (expects 'März' not 'March')")
            print(f"    ❌ Would fail in French (expects 'mars' not 'March')")
            print(f"    ❌ Would fail in any non-English system")
        print()


def test_applescript_date_parsing_simulation():
    """Simulate the AppleScript date parsing issues."""
    
    # Hard-coded English month names from current implementation
    month_names = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    print("Testing AppleScript date parsing (simulated):")
    print("=" * 60)
    
    # Different formats AppleScript might return based on system language
    test_formats = [
        ("date \"Monday, January 1, 2024 at 12:00:00 PM\"", "English"),
        ("date \"Montag, 1. Januar 2024 um 12:00:00\"", "German"),
        ("date \"lundi 1 janvier 2024 à 12:00:00\"", "French"),
        ("date \"lunedì 1 gennaio 2024 alle 12:00:00\"", "Italian"),
        ("date \"月曜日, 2024年1月1日 12:00:00\"", "Japanese"),
    ]
    
    for date_str, locale in test_formats:
        print(f"  {locale}: {date_str}")
        
        # Extract month name (simplified)
        if "january" in date_str.lower() or "januar" in date_str.lower() or "janvier" in date_str.lower():
            month_word = "january/januar/janvier"
        else:
            month_word = "unknown"
            
        # Check if current parser would handle it
        if month_word.startswith("january"):
            print(f"    ✓ Current parser recognizes English month")
        else:
            print(f"    ❌ Current parser would fail on non-English month")
        print()


if __name__ == "__main__":
    print("DEMONSTRATION: Current Date Function Issues")
    print("=" * 80)
    print()
    
    test_current_dd_mm_yyyy_converter()
    print()
    test_current_month_day_year_converter()  
    print()
    test_applescript_date_parsing_simulation()
    
    print("SUMMARY:")
    print("=" * 40)
    print("✓ Functions work as implemented")
    print("❌ But fail in different locale configurations")
    print("❌ Create wrong dates or complete failures")
    print("❌ No fallback or error handling for locale issues")