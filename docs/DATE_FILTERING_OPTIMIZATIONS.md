# Date Filtering Optimizations

This document describes the comprehensive date filtering optimizations implemented in the Things 3 MCP server to maximize performance by leveraging native AppleScript date operations.

## Overview

The optimizations replace Python-side date parsing and filtering with native AppleScript date arithmetic and filtering, resulting in significantly improved performance and reduced memory usage.

## Key Improvements

### 1. Native AppleScript Date Comparisons

**Before:**
- Python datetime parsing and manipulation
- Fetching all items and filtering in Python
- Multiple round trips between AppleScript and Python

**After:**
- Native AppleScript date arithmetic: `(current date) + 1 * days`
- AppleScript 'whose' clause filtering at the database level
- Single AppleScript execution with built-in filtering

### 2. Optimized Methods

#### `get_logbook(period: str)` Method

**Previous Implementation:**
```python
return await self._get_list_todos("logbook", limit=limit)
```
- Ignored the `period` parameter completely
- Retrieved all logbook entries up to limit
- No date filtering

**New Implementation:**
```applescript
set cutoffDate to (current date) - ({days} * days)
set recentCompleted to (to dos of logbookList whose completion date > cutoffDate)
```
- Uses native AppleScript date arithmetic
- Period-aware filtering (1d, 3d, 1w, 2w, 1m, etc.)
- Filters at the AppleScript level before data transfer

#### `search_advanced()` Method

**Previous Implementation:**
```python
if deadline:
    conditions.append(f'due date is not missing value')
    # Note: More complex date comparisons would need date parsing
```
- Only checked for existence of due dates
- No actual date value comparison
- Incomplete implementation

**New Implementation:**
```python
if deadline:
    deadline_condition = self._build_native_date_condition(deadline, "due date")
    conditions.append(deadline_condition)
```
- Full date value comparison support
- Handles relative dates (today, tomorrow, this week)
- Supports absolute dates (YYYY-MM-DD format)
- Native AppleScript date comparisons

### 3. New Helper Method: `_build_native_date_condition()`

This centralized method creates efficient AppleScript date conditions for any date field:

```python
def _build_native_date_condition(self, date_input: str, field_name: str) -> str:
    """Build a native AppleScript date condition for efficient filtering."""
```

**Supported Date Formats:**
- **Relative dates**: today, tomorrow, yesterday
- **Week ranges**: this week, next week, past week
- **Month ranges**: this month, past month
- **Absolute dates**: YYYY-MM-DD format
- **Fallback**: existence check for invalid formats

**Generated AppleScript Examples:**
```applescript
# today
due date = (current date)

# tomorrow  
due date = ((current date) + 1 * days)

# this week (range)
due date ≥ (current date) and due date ≤ ((current date) + 7 * days)

# absolute date
due date = date "15/01/2025"
```

## Performance Benefits

### 1. Reduced Data Transfer
- Only matching items are returned from AppleScript
- No need to fetch all items and filter in Python
- Smaller memory footprint

### 2. Native Database Optimization
- Things 3 uses its internal database indices for filtering
- AppleScript 'whose' clauses are highly optimized
- Leverages the app's built-in performance features

### 3. Single Round-Trip Execution
- All filtering logic runs in a single AppleScript execution
- Eliminates multiple Python ↔ AppleScript calls
- Reduces overhead and latency

## Code Examples

### Before: Python-Side Filtering
```python
# Inefficient: Get all items, filter in Python
all_todos = await get_all_todos()
filtered = [todo for todo in all_todos 
           if todo.completion_date > cutoff_date]
```

### After: Native AppleScript Filtering
```applescript
-- Efficient: Filter at the database level
set cutoffDate to (current date) - (7 * days)
set filtered to (to dos whose completion date > cutoffDate)
```

## Usage Examples

### Logbook with Period Filtering
```python
# Get completed todos from the last week
recent_completed = await tools.get_logbook(limit=20, period="1w")

# Get completed todos from the last month  
monthly_completed = await tools.get_logbook(limit=50, period="1m")
```

### Advanced Search with Date Filters
```python
# Find todos due today
today_todos = await tools.search_advanced(
    status="incomplete", 
    deadline="today", 
    limit=10
)

# Find todos starting next week
upcoming_todos = await tools.search_advanced(
    start_date="next week",
    limit=20  
)

# Find todos due on specific date
specific_todos = await tools.search_advanced(
    deadline="2025-06-15",
    limit=15
)
```

## Technical Implementation Details

### Date Arithmetic Patterns
```applescript
# Current date
(current date)

# Relative dates with arithmetic
(current date) + 1 * days    -- tomorrow
(current date) - 7 * days    -- week ago

# Range comparisons
activation date ≥ (current date) and activation date ≤ ((current date) + 7 * days)
```

### European Date Format Support
```python
# Converts YYYY-MM-DD to DD/MM/YYYY for AppleScript
parsed_date = datetime.strptime(date_input, '%Y-%m-%d')
applescript_date = parsed_date.strftime('%d/%m/%Y')
return f'{field_name} = date "{applescript_date}"'
```

## Testing

The optimizations include comprehensive test coverage:

```python
# Performance benchmark tests
await tools.get_logbook(limit=20, period="1w")  # Native period filtering
await tools.search_advanced(deadline="today")    # Native date comparison

# Condition generation tests  
condition = tools._build_native_date_condition("tomorrow", "due date")
# Returns: due date = ((current date) + 1 * days)
```

## Compatibility

- **Maintains exact same API**: All method signatures unchanged
- **Backward compatible**: Existing code continues to work
- **Graceful fallback**: Falls back to basic operations on errors
- **Robust error handling**: Invalid dates default to existence checks

## Summary

These optimizations transform the date filtering operations from Python-heavy, multi-round-trip operations to efficient, single-execution native AppleScript operations. This results in:

- **Faster execution** through native database operations
- **Lower memory usage** by filtering before data transfer  
- **Better scalability** with large datasets
- **Maintained compatibility** with existing code

The improvements are particularly noticeable when working with large numbers of todos or when performing frequent date-based queries.