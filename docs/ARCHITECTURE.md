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

## Checklist Item Support via URL Scheme

### The Problem

The Things 3 AppleScript API has another critical limitation: **it cannot create or manage checklist items**. While AppleScript can:
- ✅ Create todos with all standard properties
- ✅ Set title, notes, tags, deadlines, etc.
- ✅ Return the created todo's ID

It cannot:
- ❌ Create checklist items within a todo
- ❌ Add items to an existing checklist
- ❌ Modify or remove checklist items

The AppleScript dictionary has no `checklist item` class, making it impossible to work with checklists programmatically via AppleScript.

### The Solution

We use the **Things URL scheme exclusively** for all checklist operations:

#### 1. Creating Todos with Checklists → URL Scheme

```python
# Create todo with checklist items
await add_todo(
    title="Grocery Shopping",
    checklist_items="Milk\nBread\nEggs\nButter",
    when="today"
)
```

**Method**: Things URL scheme (`things:///add?checklist-items=...`)
**Advantages**:
- Only way to create checklists programmatically
- Supports up to 100 checklist items per todo
- Newline-separated format is simple and reliable

**Limitations**:
- Cannot retrieve todo ID immediately (must search by title afterward)
- Requires brief wait for Things to process the URL
- Less efficient than direct AppleScript

#### 2. Managing Existing Checklists → URL Scheme

```python
# Add items to existing checklist
await add_checklist_items(todo_id="abc123", items=["New item 1", "New item 2"])

# Prepend items to beginning
await prepend_checklist_items(todo_id="abc123", items=["Urgent item"])

# Replace all checklist items
await replace_checklist_items(todo_id="abc123", items=["Item 1", "Item 2"])
```

**Method**: Things URL scheme (`things:///update?id=...&append-checklist-items=...`)
**URL Parameters**:
- `append-checklist-items` - Add items to end of checklist
- `prepend-checklist-items` - Add items to beginning
- `checklist-items` - Replace all items (or clear with empty string)

### Smart Hybrid Decision

The `add_todo()` function automatically chooses the optimal method:

```python
if checklist_items:
    # Use URL scheme (only way to create checklists)
    return await self._add_todo_with_checklist(...)
else:
    # Use AppleScript (faster, returns ID immediately)
    return await self._add_todo_applescript(...)
```

### Trade-offs

| Aspect | With Checklists | Without Checklists |
|--------|----------------|-------------------|
| **Creation method** | URL Scheme | AppleScript |
| **Returns todo ID** | ⚠️ Via search | ✅ Immediate |
| **Supports checklists** | ✅ Yes (only way) | N/A |
| **Performance** | ⚠️ Slower | ✅ Fast |
| **Maximum items** | ⚠️ 100 items | N/A |

### Why This Matters

Without URL scheme support for checklists, users would have to:
1. Create todos programmatically via AppleScript
2. Manually add all checklist items in the Things UI

By using the URL scheme for checklist operations, we provide:
- Full programmatic control over checklists
- Ability to create complex todos with sub-tasks in one operation
- Tools to manage existing checklists (add/prepend/replace)

This is the **only** way to work with checklists programmatically in Things 3.

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