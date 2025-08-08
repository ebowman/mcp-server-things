#!/usr/bin/env python3
"""
Test file demonstrating locale-dependent date handling issues in Things 3 MCP server.

This test file shows the problems with the current date handling implementation:
1. DD/MM/YYYY format fails in US locale
2. "Month Day, Year" format fails in European locale  
3. Hardcoded English month names issue
4. Inconsistent date parsing behavior

Run with: python tests/test_date_locale_issues.py
"""

import sys
import os
from datetime import datetime
from typing import Dict, Any

# Add the src directory to the path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

try:
    from things_mcp.tools import ThingsTool
    from things_mcp.pure_applescript_scheduler import PureAppleScriptScheduler
except ImportError as e:
    print(f"Warning: Could not import Things MCP modules: {e}")
    print("Creating mock implementations for demonstration...")
    
    class MockThingsTool:
        def _convert_iso_to_applescript_date(self, iso_date: str) -> str:
            """Convert ISO date (YYYY-MM-DD) to AppleScript-compatible DD/MM/YYYY format."""
            try:
                parsed = datetime.strptime(iso_date, '%Y-%m-%d').date()
                return parsed.strftime('%d/%m/%Y')  # DD/MM/YYYY for European locale
            except ValueError:
                # Return original if not in expected format
                return iso_date
    
    class MockPureAppleScriptScheduler:
        def _convert_to_applescript_friendly_format(self, date_string: str) -> str:
            """Convert date string to AppleScript-friendly format."""
            try:
                # Parse ISO format and convert to natural language format
                parsed = datetime.strptime(date_string, '%Y-%m-%d').date()
                return parsed.strftime('%B %d, %Y')  # "March 3, 2026"
            except ValueError:
                # If not ISO format, return as-is
                return date_string
    
    ThingsTool = MockThingsTool
    PureAppleScriptScheduler = MockPureAppleScriptScheduler


class LocaleBehaviorSimulator:
    """Simulates how different locales would interpret date strings."""
    
    def __init__(self, locale_name: str, date_format: str, month_names: Dict[str, int]):
        self.locale_name = locale_name
        self.date_format = date_format  # e.g., '%d/%m/%Y' or '%m/%d/%Y'
        self.month_names = month_names
    
    def interpret_date_format(self, date_str: str) -> Dict[str, Any]:
        """Simulate how this locale would interpret a date string."""
        try:
            parsed = datetime.strptime(date_str, self.date_format)
            return {
                "success": True,
                "interpreted_as": parsed.strftime('%Y-%m-%d'),
                "locale": self.locale_name
            }
        except ValueError:
            return {
                "success": False,
                "error": f"Could not parse '{date_str}' as {self.date_format}",
                "locale": self.locale_name
            }
    
    def interpret_month_name(self, month_str: str) -> Dict[str, Any]:
        """Simulate how this locale would interpret a month name."""
        month_lower = month_str.lower()
        if month_lower in self.month_names:
            return {
                "success": True,
                "month_number": self.month_names[month_lower],
                "locale": self.locale_name
            }
        else:
            return {
                "success": False,
                "error": f"Unknown month name '{month_str}' in {self.locale_name}",
                "locale": self.locale_name,
                "available_months": list(self.month_names.keys())
            }


def create_locale_simulators():
    """Create simulators for different locales."""
    
    english_months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    german_months = {
        'januar': 1, 'februar': 2, 'märz': 3, 'april': 4,
        'mai': 5, 'juni': 6, 'juli': 7, 'august': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'dezember': 12
    }
    
    french_months = {
        'janvier': 1, 'février': 2, 'mars': 3, 'avril': 4,
        'mai': 5, 'juin': 6, 'juillet': 7, 'août': 8,
        'septembre': 9, 'octobre': 10, 'novembre': 11, 'décembre': 12
    }
    
    return {
        'en_US': LocaleBehaviorSimulator('en_US (US English)', '%m/%d/%Y', english_months),
        'en_GB': LocaleBehaviorSimulator('en_GB (British English)', '%d/%m/%Y', english_months),
        'de_DE': LocaleBehaviorSimulator('de_DE (German)', '%d.%m.%Y', german_months),
        'fr_FR': LocaleBehaviorSimulator('fr_FR (French)', '%d/%m/%Y', french_months),
    }


def test_dd_mm_yyyy_format_issues():
    """Test Issue 1: DD/MM/YYYY format fails in US locale."""
    print("\n" + "="*80)
    print("TEST 1: DD/MM/YYYY Format Issues")
    print("="*80)
    
    things_tool = ThingsTool()
    
    # Test dates that would be problematic
    test_dates = [
        "2024-03-15",  # March 15, 2024
        "2024-12-05",  # December 5, 2024
        "2024-01-13",  # January 13, 2024
    ]
    
    locales = create_locale_simulators()
    
    for iso_date in test_dates:
        converted = things_tool._convert_iso_to_applescript_date(iso_date)
        print(f"\nISO Date: {iso_date}")
        print(f"Current conversion: {converted} (DD/MM/YYYY format)")
        
        print("  Locale interpretation:")
        for locale_name, simulator in locales.items():
            result = simulator.interpret_date_format(converted)
            if result["success"]:
                print(f"    {locale_name}: ✓ Interpreted as {result['interpreted_as']}")
                if result['interpreted_as'] != iso_date:
                    print(f"      ❌ WRONG! Expected {iso_date}")
            else:
                print(f"    {locale_name}: ❌ {result['error']}")


def test_month_day_year_format_issues():
    """Test Issue 2: "Month Day, Year" format fails in non-English locales."""
    print("\n" + "="*80)
    print("TEST 2: Month Day, Year Format Issues")
    print("="*80)
    
    scheduler = PureAppleScriptScheduler()
    
    # Test dates
    test_dates = [
        "2024-03-15",  # March 15, 2024
        "2024-12-05",  # December 5, 2024
        "2024-01-13",  # January 13, 2024
    ]
    
    locales = create_locale_simulators()
    
    for iso_date in test_dates:
        converted = scheduler._convert_to_applescript_friendly_format(iso_date)
        print(f"\nISO Date: {iso_date}")
        print(f"Current conversion: {converted} (Month Day, Year format)")
        
        # Extract month name for testing
        month_name = converted.split()[0]  # e.g., "March" from "March 15, 2024"
        
        print("  Locale month name recognition:")
        for locale_name, simulator in locales.items():
            result = simulator.interpret_month_name(month_name)
            if result["success"]:
                print(f"    {locale_name}: ✓ Recognized '{month_name}' as month {result['month_number']}")
            else:
                print(f"    {locale_name}: ❌ {result['error']}")


def test_applescript_date_parsing_issues():
    """Test Issue 3: AppleScript date parsing inconsistencies."""
    print("\n" + "="*80)
    print("TEST 3: AppleScript Date Parsing Issues")
    print("="*80)
    
    # Simulate different AppleScript date formats that might be returned
    applescript_date_formats = [
        "date \"Monday, January 1, 2024 at 12:00:00 PM\"",
        "date \"Montag, 1. Januar 2024 um 12:00:00\"",  # German
        "date \"lundi 1 janvier 2024 à 12:00:00\"",     # French
        "1/1/2024",  # US format  
        "1/1/24",    # US short format
        "01/01/2024",  # US with leading zeros
        "1.1.2024",  # German format
        "1/1/2024 12:00",  # With time
    ]
    
    print("Current _parse_applescript_date function would handle these formats:")
    
    # We can't easily test the actual function without mocking, but we can show the issue
    for date_format in applescript_date_formats:
        print(f"\nAppleScript format: {date_format}")
        
        if "Monday" in date_format or "January" in date_format:
            print("  ✓ Would likely parse correctly (English format)")
        elif "Montag" in date_format or "Januar" in date_format:
            print("  ❌ Would fail (German day/month names)")
        elif "lundi" in date_format or "janvier" in date_format:
            print("  ❌ Would fail (French day/month names)")
        elif "/" in date_format and not "date" in date_format:
            print("  ❓ Ambiguous - could be DD/MM or MM/DD depending on locale")
        elif "." in date_format:
            print("  ❌ Would fail (German date separator)")
        else:
            print("  ❓ Unknown format handling")


def test_edge_cases_and_ambiguities():
    """Test Issue 4: Edge cases and ambiguous dates."""
    print("\n" + "="*80)
    print("TEST 4: Edge Cases and Ambiguous Dates")
    print("="*80)
    
    things_tool = ThingsTool()
    locales = create_locale_simulators()
    
    # These dates are ambiguous between DD/MM and MM/DD formats
    ambiguous_dates = [
        ("2024-01-02", "Could be Jan 2 or Feb 1"),
        ("2024-03-04", "Could be Mar 4 or Apr 3"), 
        ("2024-05-06", "Could be May 6 or Jun 5"),
        ("2024-11-12", "Could be Nov 12 or Dec 11"),
    ]
    
    print("Ambiguous date conversions (DD/MM vs MM/DD):")
    
    for iso_date, description in ambiguous_dates:
        converted = things_tool._convert_iso_to_applescript_date(iso_date)
        print(f"\nISO: {iso_date} ({description})")
        print(f"Converted to: {converted}")
        
        # Show how different locales would interpret this
        us_result = locales['en_US'].interpret_date_format(converted)
        gb_result = locales['en_GB'].interpret_date_format(converted)
        
        print(f"  US interpretation: {us_result.get('interpreted_as', 'FAILED')}")
        print(f"  GB interpretation: {gb_result.get('interpreted_as', 'FAILED')}")
        
        if (us_result.get('success') and gb_result.get('success') and 
            us_result['interpreted_as'] != gb_result['interpreted_as']):
            print("  ❌ AMBIGUITY: Different locales interpret differently!")


def test_current_implementation_assumptions():
    """Test the assumptions made by the current implementation."""
    print("\n" + "="*80)
    print("TEST 5: Current Implementation Assumptions")
    print("="*80)
    
    print("Current implementation assumes:")
    print("1. DD/MM/YYYY format is universally understood")
    print("2. English month names work in all locales") 
    print("3. AppleScript returns consistent date formats")
    print("4. System locale doesn't affect date interpretation")
    print()
    
    print("Reality check:")
    print("❌ DD/MM/YYYY is interpreted as MM/DD/YYYY in US locale")
    print("❌ English month names fail in non-English locales")
    print("❌ AppleScript date format varies by system language")
    print("❌ System locale significantly affects date parsing")
    print()
    
    print("Impact:")
    print("- Scheduling for March 5th might create February 3rd todo (in US)")
    print("- 'January 15, 2024' fails completely in German macOS")
    print("- Date parsing from Things 3 fails for non-English users")
    print("- Inconsistent behavior across different system configurations")


def run_all_tests():
    """Run all locale-related date tests."""
    print("THINGS 3 MCP SERVER - LOCALE-DEPENDENT DATE ISSUES DEMONSTRATION")
    print("================================================================")
    print()
    print("This test demonstrates current issues with date handling that")
    print("would cause failures in different locale configurations.")
    print()
    print("IMPORTANT: These tests show problems in the CURRENT implementation.")
    print("They are designed to FAIL to demonstrate the issues.")
    
    try:
        test_dd_mm_yyyy_format_issues()
        test_month_day_year_format_issues()
        test_applescript_date_parsing_issues()
        test_edge_cases_and_ambiguities()
        test_current_implementation_assumptions()
        
        print("\n" + "="*80)
        print("SUMMARY OF DEMONSTRATED ISSUES")
        print("="*80)
        print()
        print("1. ❌ DD/MM/YYYY format breaks in US locale (MM/DD expected)")
        print("2. ❌ English month names break in non-English locales")
        print("3. ❌ AppleScript date parsing assumes English format")
        print("4. ❌ Ambiguous date interpretations cause wrong dates")
        print("5. ❌ No locale detection or adaptation mechanism")
        print()
        print("NEXT STEPS:")
        print("- Implement locale-aware date conversion")
        print("- Add system locale detection")
        print("- Use AppleScript's native date handling")
        print("- Add comprehensive date format testing")
        print("- Implement fallback strategies for edge cases")
        
    except Exception as e:
        print(f"\n❌ Test execution failed: {e}")
        print("\nThis might indicate import issues or missing dependencies.")
        print("The tests are designed to run standalone to demonstrate issues.")


if __name__ == "__main__":
    run_all_tests()