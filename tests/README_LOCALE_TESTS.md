# Locale-Dependent Date Handling Tests

This directory contains tests that demonstrate the locale-dependent issues in the current date handling implementation.

## Test Files

### `test_date_locale_issues.py`
**Purpose**: Comprehensive demonstration of locale-related date problems

**What it tests**:
1. **DD/MM/YYYY Format Issues**: Shows how DD/MM/YYYY format fails in US locale
2. **Month Name Issues**: Demonstrates English month names failing in non-English locales
3. **AppleScript Parsing Issues**: Shows AppleScript date format variations by system language
4. **Ambiguous Dates**: Demonstrates dates that are interpreted differently by different locales
5. **Current Implementation Assumptions**: Documents what the code assumes vs. reality

**Key Findings**:
- ❌ `15/03/2024` fails completely in US locale (expects MM/DD)  
- ❌ `05/12/2024` becomes wrong date in US (May 12 instead of December 5)
- ❌ "March 15, 2024" fails completely in German/French locales
- ❌ AppleScript returns different date formats based on system language

### `test_current_functions.py`
**Purpose**: Direct testing of the current date conversion functions

**What it tests**:
- `_convert_iso_to_applescript_date()` function behavior
- `_convert_to_applescript_friendly_format()` function behavior  
- Simulated AppleScript date parsing scenarios

**Key Findings**:
- ✅ Functions work as implemented
- ❌ But create completely wrong dates in US locale
- ❌ Fail entirely in non-English system locales
- ❌ No error handling or fallback mechanisms

## Running the Tests

```bash
# Run comprehensive locale issues demonstration
python3 tests/test_date_locale_issues.py

# Run direct function testing  
python3 tests/test_current_functions.py
```

## Example Issues Demonstrated

### Issue 1: Wrong Dates in US Locale
```
Input:  2024-12-05 (December 5, 2024)
Output: 05/12/2024  
US interpretation: May 12, 2024  ❌ WRONG DATE!
```

### Issue 2: Complete Failure in German Locale
```
Input:  2024-03-15 (March 15, 2024)
Output: "March 15, 2024"
German system: Expects "März" not "March" ❌ COMPLETE FAILURE!
```

### Issue 3: AppleScript Language Variations
```
English: "Monday, January 1, 2024 at 12:00:00 PM"      ✅ Works
German:  "Montag, 1. Januar 2024 um 12:00:00"         ❌ Fails  
French:  "lundi 1 janvier 2024 à 12:00:00"            ❌ Fails
```

## Impact on Users

### US Users (en_US locale)
- Dates get scheduled for wrong months
- December 5th becomes May 12th  
- Any date >12 fails completely (e.g., 15/03/2024)

### European Users (en_GB locale)  
- DD/MM/YYYY format works correctly
- But English month names still required

### Non-English Users (de_DE, fr_FR, etc.)
- Complete failure for month names
- AppleScript returns localized dates that can't be parsed
- System completely unusable for date operations

## Test Results Summary

| Locale | DD/MM/YYYY | Month Names | AppleScript | Overall |
|--------|------------|-------------|-------------|---------|
| en_US  | ❌ Wrong    | ✅ Works    | ✅ Works    | ❌ Broken |
| en_GB  | ✅ Works    | ✅ Works    | ✅ Works    | ✅ Works  |
| de_DE  | ❌ Format   | ❌ Language | ❌ Language | ❌ Broken |
| fr_FR  | ❌ Format   | ❌ Language | ❌ Language | ❌ Broken |

**Result**: Only works reliably in British English locale

## Next Steps

These tests clearly demonstrate the need for:
1. Locale-aware date conversion
2. System locale detection
3. AppleScript's native date handling
4. Comprehensive fallback strategies
5. Proper error handling for locale mismatches

The tests serve as a baseline to verify that any fixes address these real-world scenarios.