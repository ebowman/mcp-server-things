# Bulk Operations Quick Reference Guide

## Overview

The Things MCP Server provides powerful bulk operation capabilities that can process multiple todos in a single operation, achieving **up to 4.90x performance improvement** over individual operations.

## Available Operations

### 1. bulk_update_todos()

Update multiple todos with the same changes in a single operation.

**Performance**: ~17 todos/second (vs 3-4 for individual updates)

**Parameters**:
- `todo_ids` (required): List of todo IDs to update
- `completed`: Mark as complete ("true"/"false")
- `canceled`: Mark as canceled ("true"/"false")
- `title`: New title for all todos
- `notes`: New notes for all todos
- `when`: Schedule date ("today", "tomorrow", "YYYY-MM-DD")
- `deadline`: Deadline date ("YYYY-MM-DD")
- `tags`: List of tags to apply

**Returns**:
```python
{
    "success": True/False,
    "message": "Bulk update completed: X/Y todos updated",
    "updated_count": 8,
    "failed_count": 2,
    "total_requested": 10,
    "tag_info": {...}  # If tags were used
}
```

**Examples**:

```python
# Mark 10 todos as complete
result = await tools.bulk_update_todos(
    todo_ids=["id1", "id2", "id3", ...],
    completed="true"
)

# Set deadline for multiple todos
result = await tools.bulk_update_todos(
    todo_ids=my_todo_list,
    deadline="2025-12-31",
    notes="Q4 deliverable"
)

# Schedule and tag multiple todos
result = await tools.bulk_update_todos(
    todo_ids=urgent_todos,
    when="today",
    tags=["urgent", "followup"]
)
```

---

### 2. bulk_move_records()

Move multiple todos to the same destination with concurrent execution.

**Performance**: ~2-3 todos/second with concurrency

**Parameters**:
- `todo_ids` (required): List of todo IDs to move
- `destination` (required): Target location
  - Lists: "inbox", "today", "anytime", "someday", "upcoming"
  - Projects: "project:PROJECT-UUID"
  - Areas: "area:AREA-UUID"
- `preserve_scheduling`: Keep existing schedule (default: True)
- `max_concurrent`: Concurrent operations (default: 5, range: 1-10)

**Returns**:
```python
{
    "success": True/False,
    "message": "Bulk move completed: X successful, Y failed",
    "destination": "today",
    "total_requested": 10,
    "total_successful": 9,
    "total_failed": 1,
    "successful_moves": [{...}, ...],
    "failed_moves": [{...}, ...],
    "preserve_scheduling": True,
    "completed_at": "2025-09-30T10:30:00"
}
```

**Examples**:

```python
# Move todos to Today
result = await tools.move_operations.bulk_move(
    todo_ids=["id1", "id2", "id3"],
    destination="today"
)

# Move to a project
result = await tools.move_operations.bulk_move(
    todo_ids=backlog_items,
    destination="project:ABC-123-DEF",
    preserve_scheduling=True
)

# Move with high concurrency
result = await tools.move_operations.bulk_move(
    todo_ids=large_batch,
    destination="someday",
    max_concurrent=7
)
```

---

## Performance Comparison

### Real-World Test Results (10 todos)

| Method | Time | Avg/Todo | Rate | Speedup |
|--------|------|----------|------|---------|
| Individual updates | 2.771s | 0.277s | 3.61/s | 1.00x |
| **Bulk update** | **0.565s** | **0.057s** | **17.69/s** | **4.90x** |

**Efficiency Gain**: 79.6% time savings

### Scaling Characteristics

| Batch Size | Bulk Update | Individual | Time Saved |
|------------|-------------|------------|------------|
| 3 todos | 0.312s | 0.808s | 61% |
| 5 todos | 0.373s | 1.385s | 73% |
| 10 todos | 0.565s | 2.771s | 80% |
| 20 todos | 0.897s | 5.540s | 84% |

**Key Finding**: Efficiency gains increase with batch size.

---

## Decision Matrix

### When to Use Bulk Operations

```
┌─────────────────────────────────────────────────────────┐
│ Number of Todos to Process                              │
├─────────────────────────────────────────────────────────┤
│ 1-2 todos      → Use individual operations              │
│ 3-5 todos      → Bulk operations recommended            │
│ 6-20 todos     → Bulk operations highly recommended     │
│ 20+ todos      → Bulk operations essential              │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│ Operation Type                                          │
├─────────────────────────────────────────────────────────┤
│ Same updates    → Use bulk_update_todos                 │
│ Different updates → Use individual update_todo          │
│ Same destination → Use bulk_move_records                │
│ Different destinations → Use individual move_record     │
└─────────────────────────────────────────────────────────┘
```

---

## Best Practices

### ✅ DO

1. **Use bulk operations for 3+ items with same changes**
   ```python
   # Good: One bulk operation
   await bulk_update_todos(todo_ids, completed="true")
   ```

2. **Check both success and partial failures**
   ```python
   result = await bulk_update_todos(todo_ids, notes="Updated")
   if result["success"]:
       print(f"✓ Updated {result['updated_count']} todos")
   if result["failed_count"] > 0:
       print(f"⚠ Failed: {result['failed_count']} todos")
   ```

3. **Adjust max_concurrent based on batch size**
   ```python
   # Small batch
   await bulk_move(small_list, "today", max_concurrent=3)

   # Large batch
   await bulk_move(large_list, "today", max_concurrent=7)
   ```

4. **Use preserve_scheduling by default**
   ```python
   await bulk_move(todos, "today", preserve_scheduling=True)
   ```

5. **Batch similar operations together**
   ```python
   # Good: Single bulk operation
   await bulk_update_todos(all_todos, deadline="2025-12-31")

   # Bad: Multiple individual operations
   for todo_id in all_todos:
       await update_todo(todo_id, deadline="2025-12-31")
   ```

### ❌ DON'T

1. **Don't use bulk operations for different updates**
   ```python
   # Bad: Each todo needs different update
   for i, todo_id in enumerate(todo_ids):
       # Can't use bulk_update here
       await update_todo(todo_id, title=f"Task {i}")
   ```

2. **Don't mix bulk and individual operations unnecessarily**
   ```python
   # Bad: Mixing approaches
   await update_todo(todo1, completed="true")
   await bulk_update_todos([todo2, todo3], completed="true")
   await update_todo(todo4, completed="true")

   # Good: Use bulk for all
   await bulk_update_todos([todo1, todo2, todo3, todo4],
                          completed="true")
   ```

3. **Don't ignore partial failures**
   ```python
   # Bad: Ignoring failures
   result = await bulk_update_todos(todos, completed="true")

   # Good: Check for failures
   if result["failed_count"] > 0:
       logger.warning(f"Some todos failed: {result['failed_moves']}")
   ```

4. **Don't use excessively high concurrency**
   ```python
   # Bad: Too high, may cause issues
   await bulk_move(todos, "today", max_concurrent=20)

   # Good: Reasonable limit
   await bulk_move(todos, "today", max_concurrent=5)
   ```

---

## Error Handling

### Common Errors

**1. No Valid IDs**
```python
result = await bulk_update_todos([], completed="true")
# Returns: {"success": False, "error": "No todo IDs provided"}
```

**2. Invalid Destination**
```python
result = await bulk_move(todos, "invalid_list")
# Returns: {"success": False, "error": "INVALID_DESTINATION"}
```

**3. Partial Failure**
```python
result = await bulk_update_todos(
    ["valid-id", "invalid-id", "valid-id-2"],
    completed="true"
)
# Returns: {
#     "success": True,  # Some succeeded
#     "updated_count": 2,
#     "failed_count": 1
# }
```

### Error Handling Pattern

```python
try:
    result = await bulk_update_todos(todo_ids, completed="true")

    if result["success"]:
        print(f"✓ Successfully updated {result['updated_count']} todos")
    else:
        print(f"✗ Bulk operation failed: {result.get('error')}")

    # Always check for partial failures
    if result.get("failed_count", 0) > 0:
        print(f"⚠ Warning: {result['failed_count']} todos failed to update")
        # Optionally retry failed items

except Exception as e:
    logger.error(f"Unexpected error in bulk operation: {e}")
    # Handle exception
```

---

## Advanced Usage

### Pagination for Large Batches

```python
async def bulk_update_with_pagination(all_todo_ids, **kwargs):
    """Update large number of todos with pagination."""
    batch_size = 50
    results = []

    for i in range(0, len(all_todo_ids), batch_size):
        batch = all_todo_ids[i:i + batch_size]
        result = await bulk_update_todos(batch, **kwargs)
        results.append(result)

        # Brief pause between batches
        await asyncio.sleep(0.5)

    # Aggregate results
    total_updated = sum(r["updated_count"] for r in results)
    total_failed = sum(r["failed_count"] for r in results)

    return {
        "success": total_failed == 0,
        "total_updated": total_updated,
        "total_failed": total_failed,
        "batch_count": len(results)
    }
```

### Conditional Bulk Operations

```python
async def complete_overdue_todos(tools):
    """Complete all overdue todos in bulk."""
    # Get overdue todos
    overdue = await tools.get_due_in_days(-30)  # 30 days overdue

    # Filter for incomplete
    incomplete_ids = [
        todo["id"] for todo in overdue
        if todo["status"] != "completed"
    ]

    # Bulk complete
    if len(incomplete_ids) >= 3:
        return await tools.bulk_update_todos(
            todo_ids=incomplete_ids,
            completed="true",
            notes="Auto-completed: overdue"
        )
    else:
        # Use individual for small batches
        results = []
        for todo_id in incomplete_ids:
            result = await tools.update_todo(
                todo_id,
                completed="true"
            )
            results.append(result)
        return results
```

### Progress Tracking

```python
async def bulk_move_with_progress(tools, todo_ids, destination):
    """Bulk move with progress tracking."""
    batch_size = 10
    total = len(todo_ids)
    completed = 0

    for i in range(0, total, batch_size):
        batch = todo_ids[i:i + batch_size]

        result = await tools.move_operations.bulk_move(
            todo_ids=batch,
            destination=destination
        )

        completed += result["total_successful"]
        progress = (completed / total) * 100

        print(f"Progress: {completed}/{total} ({progress:.1f}%)")

    return completed
```

---

## Performance Tips

### 1. Optimize Batch Size

```python
# Too small: Overhead dominates
for todo in todos:
    await update_todo(todo, ...)  # Slow

# Too large: May timeout
await bulk_update_todos(todos[:1000], ...)  # Risky

# Just right: 10-50 items
await bulk_update_todos(todos[:25], ...)  # Optimal
```

### 2. Use Appropriate Concurrency

```python
# For bulk_move_records:
small_batch  (≤5):  max_concurrent=3
medium_batch (6-20): max_concurrent=5  # Default
large_batch  (20+):  max_concurrent=7
```

### 3. Combine Related Operations

```python
# Inefficient: Multiple bulk operations
await bulk_update_todos(todos, completed="true")
await bulk_update_todos(todos, notes="Done")

# Efficient: Single bulk operation
await bulk_update_todos(
    todo_ids=todos,
    completed="true",
    notes="Done"
)
```

---

## Troubleshooting

### Issue: Bulk update fails for scheduling

**Symptom**: `when="today"` fails in bulk_update
**Solution**: Use individual updates for complex scheduling
```python
# Workaround for scheduling issues
for todo_id in critical_todos:
    await update_todo(todo_id, when="today@14:30")
```

### Issue: Project moves have low success rate

**Symptom**: Only some todos moved to project
**Solution**: Verify project exists and retry failed items
```python
result = await bulk_move(todos, f"project:{project_id}")

if result["failed_moves"]:
    # Retry failed moves
    failed_ids = [m["id"] for m in result["failed_moves"]]
    await asyncio.sleep(1)
    retry_result = await bulk_move(failed_ids, f"project:{project_id}")
```

### Issue: Tags not being applied

**Symptom**: Tag validation filters out tags
**Solution**: Ensure tags exist before bulk operation
```python
# Check available tags first
existing_tags = await tools.get_tags()
tag_names = [t["name"] for t in existing_tags]

# Filter to existing tags only
valid_tags = [tag for tag in my_tags if tag in tag_names]

await bulk_update_todos(todos, tags=valid_tags)
```

---

## API Reference

### bulk_update_todos()

```python
async def bulk_update_todos(
    self,
    todo_ids: List[str],      # Required: IDs to update
    **kwargs                  # Optional update parameters
) -> Dict[str, Any]:
    """
    Update multiple todos with same changes.

    Args:
        todo_ids: List of todo IDs
        completed: "true"/"false"
        canceled: "true"/"false"
        title: New title
        notes: New notes
        when: Schedule date
        deadline: Deadline date
        tags: List of tags

    Returns:
        {
            "success": bool,
            "message": str,
            "updated_count": int,
            "failed_count": int,
            "total_requested": int
        }
    """
```

### bulk_move_records()

```python
async def bulk_move(
    self,
    todo_ids: List[str],           # Required: IDs to move
    destination: str,              # Required: Target location
    preserve_scheduling: bool = True,
    max_concurrent: int = 5
) -> Dict[str, Any]:
    """
    Move multiple todos to same destination.

    Args:
        todo_ids: List of todo IDs
        destination: Target (list, project:ID, area:ID)
        preserve_scheduling: Keep schedule
        max_concurrent: Concurrent ops (1-10)

    Returns:
        {
            "success": bool,
            "message": str,
            "total_successful": int,
            "total_failed": int,
            "successful_moves": List[Dict],
            "failed_moves": List[Dict]
        }
    """
```

---

## See Also

- [BULK_OPERATIONS_TEST_REPORT.md](../BULK_OPERATIONS_TEST_REPORT.md) - Detailed test results
- [CLAUDE.md](../CLAUDE.md) - AI assistant instructions
- [README.md](../README.md) - General documentation

---

## Quick Reference Card

```
╔════════════════════════════════════════════════════════════╗
║ BULK OPERATIONS QUICK REFERENCE                           ║
╠════════════════════════════════════════════════════════════╣
║ BULK UPDATE (4.90x faster)                                ║
║ await bulk_update_todos(ids, completed="true")            ║
║                                                            ║
║ BULK MOVE (concurrent execution)                          ║
║ await bulk_move(ids, "today", max_concurrent=5)           ║
║                                                            ║
║ PERFORMANCE                                                ║
║ • Individual: ~3-4 todos/second                           ║
║ • Bulk update: ~17 todos/second                           ║
║ • Bulk move: ~2-3 todos/second                            ║
║                                                            ║
║ BEST PRACTICES                                             ║
║ • Use bulk for 3+ items with same changes                 ║
║ • Check updated_count AND failed_count                    ║
║ • Use preserve_scheduling=True by default                 ║
║ • Batch size: 10-50 items optimal                         ║
║                                                            ║
║ COMMON DESTINATIONS                                        ║
║ • Lists: "inbox", "today", "anytime", "someday"           ║
║ • Projects: "project:UUID"                                ║
║ • Areas: "area:UUID"                                      ║
╚════════════════════════════════════════════════════════════╝
```