# Hybrid Approach: things.py + AppleScript

## Overview

This document outlines a hybrid approach using [things.py](https://github.com/thingsapi/things.py) for read operations and AppleScript for write operations, providing optimal performance and reliability.

## Why Hybrid?

### Current Issues with Pure AppleScript
1. **Performance**: AppleScript is slow for large data reads (10-100x slower)
2. **Timeouts**: Large tag/todo lists cause timeouts
3. **Parsing Complexity**: Complex string parsing for structured data
4. **Lock Contention**: Single AppleScript lock causes bottlenecks

### Benefits of things.py
1. **Direct SQLite Access**: Reads directly from Things database
2. **No Timeouts**: Database queries are fast and reliable
3. **Structured Data**: Returns proper Python objects, no parsing needed
4. **Parallel Reads**: No lock contention for read operations
5. **Built-in Filtering**: SQL-based filtering is very efficient

### Limitations of things.py
- **Read-Only**: Cannot create, update, or delete items
- **No Real-time Updates**: Reads from database, not live app state
- **Limited Interaction**: Only basic URL scheme support

## Operation Mapping

### ✅ Use things.py (Fast Reads)

| MCP Operation | things.py Method | Performance Gain |
|--------------|------------------|------------------|
| `get_todos()` | `things.todos()` | 10-50x faster |
| `get_projects()` | `things.projects()` | 10-30x faster |
| `get_areas()` | `things.areas()` | 5-20x faster |
| `get_tags()` | `things.tags()` | **50-100x faster** |
| `get_inbox()` | `things.inbox()` | 10x faster |
| `get_today()` | `things.today()` | 10x faster |
| `get_upcoming()` | `things.upcoming()` | 10x faster |
| `get_anytime()` | `things.anytime()` | 10x faster |
| `get_someday()` | `things.someday()` | 10x faster |
| `get_logbook()` | `things.logbook()` | 20-50x faster |
| `get_trash()` | `things.trash()` | 10x faster |
| `search_todos()` | `things.search()` | 20x faster |
| `get_todo_by_id()` | `things.get()` | 5x faster |

### ❌ Use AppleScript (Writes & Complex Operations)

| MCP Operation | Why AppleScript? |
|--------------|-----------------|
| `add_todo()` | Write operation |
| `update_todo()` | Write operation |
| `delete_todo()` | Write operation |
| `add_project()` | Write operation |
| `update_project()` | Write operation |
| `move_todo()` | Complex manipulation |
| `add_tags()` | Write operation |
| `complete_todo()` | Can use things.py URL scheme, but AppleScript is more reliable |

## Implementation Strategy

### Phase 1: Core Read Operations
1. Install things.py as dependency
2. Replace `get_tags()` with things.py (biggest performance win)
3. Replace list operations (inbox, today, etc.)
4. Add fallback to AppleScript if things.py fails

### Phase 2: Search and Filtering
1. Replace `search_todos()` with things.py
2. Implement `search_advanced()` using SQL filters
3. Add date-based queries using database

### Phase 3: Optimization
1. Remove AppleScript caching for read operations (not needed)
2. Parallel read operations (no lock needed)
3. Batch operations for better performance

## Code Example

```python
# Before (AppleScript) - SLOW
async def get_tags(self, include_items: bool = False):
    script = '''
    tell application "Things3"
        -- Complex AppleScript to get tags and count items
        -- This can take 30-60 seconds for many tags
    end tell
    '''
    result = await self.applescript.execute_applescript(script)
    # Complex parsing of string output
    return parsed_tags

# After (things.py) - FAST
async def get_tags(self, include_items: bool = False):
    tags = things.tags(include_items=include_items)
    result = []
    for tag in tags:
        tag_dict = {
            'id': tag['uuid'],
            'name': tag['title'],
            'item_count': len(tag.get('items', []))  # Instant count!
        }
        result.append(tag_dict)
    return result  # Returns in <100ms instead of 30s
```

## Performance Comparison

| Operation | AppleScript Time | things.py Time | Improvement |
|-----------|-----------------|----------------|-------------|
| Get 50 tags with counts | 30-60s | 0.1s | 300-600x |
| Get 1000 todos | 5-10s | 0.2s | 25-50x |
| Search todos | 2-5s | 0.1s | 20-50x |
| Get today's todos | 1-2s | 0.05s | 20-40x |

## Migration Path

1. **Install things.py**:
   ```bash
   pip install things.py
   ```

2. **Create hybrid_tools.py**: 
   - Implements both approaches
   - Automatic fallback to AppleScript
   - Same API as current tools

3. **Gradual Migration**:
   - Start with read operations
   - Keep write operations in AppleScript
   - Test thoroughly with fallbacks

4. **Monitor Performance**:
   - Log performance metrics
   - Track fallback frequency
   - Optimize based on usage

## Considerations

### Pros
- **Massive performance improvement** for reads
- **No timeout issues** for large datasets
- **Cleaner code** with structured data
- **Better scalability** for large Things databases
- **Graceful fallback** maintains compatibility

### Cons
- **Additional dependency** (things.py)
- **Database location** must be accessible
- **Read-only limitation** for things.py
- **Potential sync lag** between database and app

## Recommendation

Implement the hybrid approach starting with the most problematic operations:
1. `get_tags()` - Currently timing out
2. Search operations - Currently slow
3. List operations - Frequently used

This will provide immediate performance benefits while maintaining full functionality through AppleScript for write operations.