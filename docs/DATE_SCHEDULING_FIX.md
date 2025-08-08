# Date Scheduling Bug Fix

## Problem
When scheduling todos with specific dates like "2025-09-15", the date was being set incorrectly to "2036-03-17" - an offset of approximately 11 years (3,836 days).

## Root Cause
The bug was caused by using numeric month values in AppleScript date construction, which triggers month overflow issues when the current date has more days than the target month.

### Bug Mechanism
When the AppleScript runs on a date like August 31st:
```applescript
set targetDate to current date        -- e.g., August 31, 2025
set month of targetDate to 9          -- Tries to create "September 31"
```

Since September only has 30 days, AppleScript's internal date arithmetic "corrects" this invalid date with unpredictable overflow behavior, resulting in dates years in the future.

## Solution
Replace numeric month values with AppleScript month constants and set properties in a safe order:

### Before (BUGGY):
```applescript
set targetDate to current date
set year of targetDate to 2025
set month of targetDate to 9          -- Numeric month causes overflow
set day of targetDate to 15
```

### After (FIXED):
```applescript
set targetDate to current date
set time of targetDate to 0           -- Reset time first
set day of targetDate to 1            -- Set to safe day to avoid overflow
set year of targetDate to 2025
set month of targetDate to September  -- Use month constant
set day of targetDate to 15           -- Set actual day last
```

## Files Modified

1. **`src/things_mcp/pure_applescript_scheduler.py`** (line 132-163)
   - Fixed `_schedule_specific_date_objects` method
   - Added month name mapping and safe date construction

2. **`src/things_mcp/reliable_scheduling.py`** (line 235-266)
   - Fixed `_schedule_specific_date_applescript` method
   - Added month name mapping and safe date construction

3. **`src/things_mcp/tools.py`** (line 451-469)
   - Fixed date scheduling in `_schedule_todo` method
   - Added month name mapping for specific date handling

## Technical Details

### Month Name Mapping
```python
month_names = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}
month_constant = month_names[target_date.month]
```

### Safe Property Setting Order
1. Reset time to 0 first (clears hours/minutes/seconds)
2. Set day to 1 (safe value that exists in all months)
3. Set year to target year
4. Set month using AppleScript constant
5. Set day to actual target day

## Testing Results

✅ **All test cases pass correctly:**
- 2025-09-15 → Correctly scheduled for September 15, 2025
- 2025-12-31 → Correctly scheduled for December 31, 2025
- 2025-01-01 → Correctly scheduled for January 1, 2025
- 2025-02-28 → Correctly scheduled for February 28, 2025
- 2025-08-31 → Correctly scheduled for August 31, 2025

## Key Learnings

1. **AppleScript Date Arithmetic**: AppleScript's date object has complex overflow behavior when setting invalid intermediate dates
2. **Month Constants vs Numbers**: Always use AppleScript month constants (January, February, etc.) instead of numeric values
3. **Property Setting Order**: The order of setting date properties matters to avoid intermediate invalid states
4. **Edge Case Testing**: Always test date operations on month boundaries (28th, 29th, 30th, 31st)

## Prevention

To prevent similar issues in the future:
1. Always use AppleScript month constants, never numeric values
2. Set date properties in a safe order (time → day=1 → year → month → actual day)
3. Test date operations with edge cases like month ends
4. Consider using date string construction (`date "September 15, 2025"`) for simpler cases

## Verification

The fix has been verified with multiple test scenarios and all dates are now scheduled correctly without the 11-year offset bug.