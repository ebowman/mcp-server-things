# Things 3 MCP Server - Architecture Documentation

## Overview

This document explains key architectural decisions in the Things 3 MCP Server implementation, particularly the hybrid approach used for todo creation.

## The Hybrid AppleScript/URL Scheme Approach

### The Problem

The Things 3 AppleScript API has a critical limitation: **it cannot set reminder times for todos**. While AppleScript can:
- ✅ Set when a todo appears in Today/Upcoming (the date)
- ✅ Set all other properties (title, notes, tags, projects, etc.)
- ✅ Return the created todo's ID

It cannot:
- ❌ Set a specific reminder/notification time (e.g., "remind me at 2:30 PM")

This is a fundamental gap in the AppleScript API that prevents creating todos with time-based reminders programmatically.

### The Solution

We implement a **hybrid approach** that uses different methods based on whether a reminder time is needed:

#### 1. Regular Todos (Date Only) → AppleScript

When creating todos without specific reminder times:
```python
# Examples:
await add_todo(title="Review code", when="today")
await add_todo(title="Team meeting", when="tomorrow")
await add_todo(title="Project deadline", when="2024-12-25")
```

**Method**: Direct AppleScript execution
**Advantages**:
- Returns actual todo ID from Things
- Full control over all properties
- Synchronous confirmation of creation
- Better error handling

#### 2. Todos with Reminders → URL Scheme

When creating todos with specific reminder times:
```python
# Examples:
await add_todo(title="Review code", when="today@14:30")
await add_todo(title="Team meeting", when="tomorrow@09:00")
await add_todo(title="Project deadline", when="2024-12-25@18:00")
```

**Method**: Things URL scheme (`things:///add?...`)
**Advantages**:
- Supports full Quick Entry syntax including reminders
- Uses Things' natural language parser
- Only way to set reminder times programmatically

**Limitations**:
- Returns placeholder ID (`"created_via_url_scheme"`) instead of actual todo ID
- Less granular error handling
- Requires Things to be the active application momentarily

### Implementation Details

The decision logic is in `tools.py`:

```python
# Check if the 'when' parameter contains a time component
if when and self._has_datetime_reminder(when):
    # Use URL scheme for reminders
    url_scheme = self._build_url_scheme_with_reminder(title, parsed_when, notes, tags)
    result = await self.applescript.execute_url_scheme(action="add", parameters={"url_override": url_scheme})
else:
    # Use AppleScript for regular todos
    # ... standard AppleScript todo creation ...
```

### URL Scheme Format

The URL scheme for creating a todo with reminder looks like:
```
things:///add?title=Meeting&when=today@2:30pm&notes=Bring%20laptop&tags=work,urgent
```

The `@` symbol in the `when` parameter triggers Things' reminder parser.

### Trade-offs

| Aspect | AppleScript | URL Scheme |
|--------|------------|------------|
| **Can set reminder times** | ❌ No | ✅ Yes |
| **Returns todo ID** | ✅ Yes | ❌ No (placeholder) |
| **Error handling** | ✅ Detailed | ⚠️ Limited |
| **Performance** | ✅ Direct | ⚠️ Opens Things UI |
| **Batch operations** | ✅ Efficient | ❌ One at a time |

### Why This Matters

Without this hybrid approach, users would have to choose between:
1. Having programmatic todo creation WITHOUT reminders (AppleScript only)
2. Manually setting reminders in Things after creation

By combining both methods intelligently, we provide the best possible experience:
- Full reminder support when needed
- Optimal performance and ID tracking when reminders aren't needed

### Future Considerations

If Things 3 ever adds reminder support to their AppleScript API, we could:
1. Deprecate the URL scheme path
2. Unify all creation through AppleScript
3. Always return actual todo IDs

Until then, this hybrid approach represents the best possible solution given the API constraints.

## Other Architectural Decisions

### Operation Queue System

All write operations (create, update, delete) go through a centralized operation queue to:
- Prevent race conditions
- Ensure data consistency
- Provide retry logic
- Enable operation tracking

### Tag Validation Service

Tags can be configured to either:
- Allow AI to create new tags freely
- Restrict AI to existing tags only (human-controlled taxonomy)

This is controlled by the `THINGS_MCP_AI_CAN_CREATE_TAGS` environment variable.

### Caching Strategy

Read operations are cached for 30 seconds to:
- Reduce AppleScript execution overhead
- Improve response times for repeated queries
- Minimize Things 3 CPU usage

## Performance Considerations

### AppleScript Timeouts

- Default: 30 seconds
- Maximum: 300 seconds (5 minutes)
- Configurable via `THINGS_MCP_APPLESCRIPT_TIMEOUT`

### Batch Operations

Where possible, operations are batched:
- Tag creation/validation
- Multiple todo retrieval
- Project hierarchy traversal

### Large Dataset Handling

- Default limits on result sets (100-500 items)
- Pagination support for logbook queries
- Streaming for large exports

## Security Considerations

### Input Sanitization

All user input is sanitized before AppleScript execution:
- Quote escaping
- Special character handling
- Injection prevention

### Permission Model

- Read-only operations: No special permissions
- Write operations: Require AppleScript automation access
- System operations: Additional confirmation required

## Error Handling

### Retry Strategy

1. **Immediate retry**: For transient failures
2. **Exponential backoff**: For rate limiting
3. **Fallback methods**: URL scheme → AppleScript
4. **Graceful degradation**: Return partial results when possible

### Error Categories

- **Recoverable**: Retry with backoff
- **User errors**: Return helpful messages
- **System errors**: Log and escalate
- **API limitations**: Document and work around

---

*This architecture ensures the Things 3 MCP Server provides the most complete functionality possible despite API limitations, while maintaining reliability and performance.*