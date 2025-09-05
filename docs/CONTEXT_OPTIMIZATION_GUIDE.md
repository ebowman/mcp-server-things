# 🔍 Context Optimization Guide

## Overview

The Things MCP Server includes sophisticated **context-aware response management** designed to prevent AI context exhaustion while maintaining full API functionality. This guide explains how to effectively use these features.

## 🎯 Key Features

### 1. Progressive Disclosure Modes

The server offers 6 response modes optimized for different use cases:

| Mode | Size per Item | Use Case | Context Budget |
|------|---------------|----------|----------------|
| `summary` | ~50 bytes | Overview, counts, insights | 2KB total |
| `minimal` | ~200 bytes | IDs + essential fields | 10-20KB |
| `standard` | ~1KB | Daily workflow (default) | 50KB |
| `detailed` | ~1.2KB | Complete field data | 60-80KB |
| `raw` | Variable | Original unoptimized | Unlimited |
| `auto` | Dynamic | **Intelligent selection** | Optimal |

### 2. Smart Default System

The server automatically applies intelligent defaults:

- **Default mode**: `auto` (dynamically selects optimal mode)
- **Default limits**: Method-specific (e.g., 50 for get_todos)  
- **Default include_items**: `false` (excludes checklist items)
- **Context budget**: 100KB total, 80KB max response

### 3. Relevance Ranking

Items are automatically prioritized by:
1. **Overdue items** (highest priority)
2. **Today's scheduled items** 
3. **Items with reminders**
4. **Recently modified items**
5. **Open/incomplete status**

## 📊 Usage Patterns

### Discovery Workflow (Recommended)

```python
# 1. Start with server capabilities
capabilities = await get_server_capabilities()

# 2. Use auto mode for unknown datasets  
todos = await get_todos(mode="auto")

# 3. Based on results, drill down as needed
if todos["meta"]["mode"] == "summary":
    # Large dataset detected, use insights to guide next steps
    detailed_todos = await get_todos(mode="standard", limit=20)
```

### Large Dataset Exploration

```python
# Step 1: Get overview with summary mode
overview = await get_todos(mode="summary")
print(f"Found {overview['count']} items")
print(f"Status breakdown: {overview['status_breakdown']}")

# Step 2: Get essential data for bulk operations
essential = await get_todos(mode="minimal", limit=100)

# Step 3: Get detailed data for specific items only
important_ids = [item['id'] for item in essential['data'][:10]]
# Use get_todo_by_id() for individual detailed views
```

### Daily Workflow Optimization

```python
# Morning review (optimized)
today = await get_today()  # Small dataset, uses standard mode
projects = await get_projects(mode="summary")  # Quick overview
inbox = await get_inbox()  # Standard mode for active management

# Bulk organization (optimized)
all_todos = await get_todos(mode="minimal")  # Get IDs and essential fields
# Use bulk_move_records() with the minimal data
```

## ⚡ Performance Tips

### 1. Mode Selection Guidelines

- **Unknown dataset size**: Use `mode="auto"` 
- **Large collections (>50 items)**: Start with `mode="summary"`
- **Bulk operations**: Use `mode="minimal"` to get IDs
- **Daily workflow**: `mode="standard"` provides good balance
- **Analysis work**: Request `mode="detailed"` only when needed

### 2. Limit Usage

```python
# Good: Use limits for large datasets
large_dataset = await get_todos(mode="standard", limit=30)

# Better: Let auto mode handle sizing
smart_dataset = await get_todos(mode="auto")

# Best: Get recommendations first
recommendations = await get_usage_recommendations("get_todos")
optimal_limit = recommendations["suggested_limit"]
```

### 3. Context Monitoring

```python
# Check context usage
stats = await context_stats()
print(f"Available context: {stats['available_for_response_kb']}KB")

# Get intelligent recommendations
recommendations = await get_usage_recommendations()
```

## 🔄 Advanced Workflows

### Progressive Data Loading

```python
async def explore_todos_progressively():
    # Step 1: Get overview
    summary = await get_todos(mode="summary")
    
    if summary["count"] < 20:
        # Small dataset - get full details
        return await get_todos(mode="detailed")
    
    elif summary["count"] < 100:
        # Medium dataset - use standard mode with limits
        return await get_todos(mode="standard", limit=50)
    
    else:
        # Large dataset - progressive disclosure
        print(f"Large dataset detected: {summary['count']} items")
        print(f"Status breakdown: {summary['status_breakdown']}")
        
        # Get high-priority items first
        priority_items = await get_todos(mode="standard", limit=20)
        
        # Use summary insights to guide further queries
        return priority_items
```

### Bulk Operation Optimization

```python
async def optimize_bulk_move():
    # Get minimal data for ID collection
    minimal_data = await get_todos(mode="minimal", project_uuid="project-123")
    
    # Extract IDs for bulk operation
    todo_ids = [item['id'] for item in minimal_data['data']]
    
    # Perform bulk move efficiently
    result = await bulk_move_records(
        todo_ids=",".join(todo_ids),
        destination="today",
        max_concurrent=5
    )
    
    return result
```

## 🎛️ Configuration Options

### Context Budget Tuning

The default context budget can be understood as:

- **Total Budget**: 100KB (safe for most AI contexts)
- **Response Budget**: 80KB (20% reserved for reasoning)
- **Warning Threshold**: 60KB
- **Pagination Trigger**: 80KB

### Response Mode Behavior

| Mode | Field Filtering | Size Limit | Pagination |
|------|----------------|------------|-----------|
| `summary` | Aggressive | 2KB | No |
| `minimal` | High | 20KB | Yes |
| `standard` | Moderate | 50KB | Yes |
| `detailed` | Light | 80KB | Yes |
| `raw` | None | Unlimited | No |
| `auto` | Dynamic | Dynamic | Yes |

## 🚨 Troubleshooting

### Context Exhaustion Prevention

If you encounter truncated responses:

1. **Check context stats**: `await context_stats()`
2. **Use more restrictive mode**: Switch from `standard` to `minimal`
3. **Add limits**: Use `limit` parameter to control size
4. **Progressive loading**: Start with `summary`, drill down as needed

### Performance Issues

For slow responses:

1. **Use minimal mode** for bulk operations
2. **Add reasonable limits** (e.g., limit=50)  
3. **Disable checklist items**: `include_items=false`
4. **Check server status**: `await health_check()`

### Large Dataset Handling

For datasets with 100+ items:

```python
# ❌ Avoid: Loading everything at once
all_data = await get_todos(mode="detailed")  # May cause context exhaustion

# ✅ Recommended: Progressive approach
summary = await get_todos(mode="summary")
essential = await get_todos(mode="minimal", limit=50)
# Then get detailed data only for specific items
```

## 📈 Optimization Examples

### Before vs After

**Before (Context-Unsafe)**:
```python
# Risky - could exhaust context
todos = await get_todos()  # No optimization
projects = await get_projects(include_items=True)  # Large response
```

**After (Context-Optimized)**:
```python
# Safe - context-aware
todos = await get_todos(mode="auto")  # Intelligent sizing
projects = await get_projects(mode="summary")  # Quick overview
detailed_projects = await get_projects(mode="standard", limit=10)  # Targeted detail
```

### Real-World Scenario

**Task Management Dashboard**:
```python
async def build_dashboard():
    # Quick overview for cards/widgets
    stats = {
        "today": await get_today(),  # Small, uses standard
        "upcoming": await get_upcoming(mode="minimal"),  # Just counts
        "projects": await get_projects(mode="summary"),  # Overview
        "overdue": await get_todos(mode="minimal", limit=10)  # Top issues
    }
    
    # User can drill down for details as needed
    return stats
```

## 🎯 Best Practices Summary

1. **Start with `mode="auto"`** for unknown datasets
2. **Use `mode="summary"`** to explore large collections  
3. **Use `mode="minimal"`** for bulk operations
4. **Monitor context usage** with `context_stats()`
5. **Get personalized recommendations** with `get_usage_recommendations()`
6. **Use progressive disclosure patterns** for large datasets
7. **Test with real data** to understand your usage patterns

## 🔗 Related Tools

- **`get_server_capabilities()`**: Discover all optimization features
- **`get_usage_recommendations()`**: Get personalized suggestions
- **`context_stats()`**: Monitor context usage
- **`health_check()`**: Verify server status
- **`queue_status()`**: Monitor bulk operations

The context optimization system is designed to be transparent and helpful. When in doubt, use `mode="auto"` and let the system choose the optimal approach for your data!