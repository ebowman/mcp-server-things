# 🤖 AI Assistant Guidelines

## Overview

This guide provides behavioral guidelines for AI assistants using the Things MCP Server. Following these patterns ensures optimal performance, prevents errors, and creates a better user experience.

## 🎯 Core Principles

### 1. Context-First Approach
- **Always** start with `get_server_capabilities()` to understand available features
- Use `mode="auto"` as your default for unknown datasets
- Monitor context usage with `context_stats()` when handling large data
- Apply progressive disclosure patterns for exploration

### 2. User-Centric Design  
- Ask for confirmation before bulk operations affecting >10 items
- Provide clear explanations of what actions will be taken
- Offer alternatives when primary actions fail
- Respect user preferences and existing organization systems

### 3. Error Prevention
- Validate inputs before operations
- Check system health before bulk operations
- Use existing tags rather than creating new ones automatically
- Provide recovery suggestions for failed operations

## 🏷️ Tag Management Policies

### Tag Creation Rules (CRITICAL)

**❌ DO NOT**: Create tags automatically
**✅ DO**: Ask users before creating tags

```python
# ❌ Wrong - Automatic tag creation
await add_todo(title="Meeting", tags=["urgent", "new-project"])  # May create unwanted tags

# ✅ Correct - Check existing tags first
existing_tags = await get_tags()
tag_names = [tag['name'] for tag in existing_tags]

if "urgent" not in tag_names:
    # Ask user for permission
    print("The tag 'urgent' doesn't exist. Would you like me to create it?")
    # Wait for user confirmation before proceeding
```

### Tag Workflow Pattern

1. **Discovery**: Use `get_tags()` to see available tags
2. **Validation**: Check if needed tags exist
3. **User Consultation**: Ask before creating new tags
4. **Graceful Fallback**: Use similar existing tags if creation declined

```python
async def smart_tag_workflow(todo_title: str, desired_tags: List[str]) -> Dict:
    # Step 1: Get existing tags
    existing_tags = await get_tags()
    existing_names = [tag['name'].lower() for tag in existing_tags]
    
    # Step 2: Validate tags
    valid_tags = []
    missing_tags = []
    
    for tag in desired_tags:
        if tag.lower() in existing_names:
            valid_tags.append(tag)
        else:
            missing_tags.append(tag)
    
    # Step 3: Handle missing tags
    if missing_tags:
        print(f"These tags don't exist: {missing_tags}")
        print(f"Available similar tags: {existing_names[:5]}")
        print("Would you like me to:")
        print("1. Use only existing tags")
        print("2. Ask user to create missing tags")
        print("3. Suggest similar alternatives")
    
    # Step 4: Create todo with valid tags only
    return await add_todo(title=todo_title, tags=",".join(valid_tags))
```

## 📊 Data Exploration Patterns

### Discovery Workflow

```python
async def explore_user_data():
    """Recommended pattern for understanding user's Things data."""
    
    # Step 1: Get server capabilities
    capabilities = await get_server_capabilities()
    print(f"Server features: {capabilities['features'].keys()}")
    
    # Step 2: Quick overview
    today_items = await get_today()
    projects = await get_projects(mode="summary")
    inbox_count = len(await get_inbox())
    
    # Step 3: Present overview
    print(f"Today: {len(today_items)} items")
    print(f"Projects: {projects['count']} total")
    print(f"Inbox: {inbox_count} items")
    
    # Step 4: Ask what user wants to focus on
    print("What would you like to work on?")
    print("1. Today's tasks")
    print("2. Project overview") 
    print("3. Inbox processing")
    print("4. Specific search")
```

### Progressive Data Loading

```python
async def handle_large_dataset(method_name: str, **params):
    """Pattern for safely handling potentially large datasets."""
    
    # Step 1: Get intelligent recommendations
    recommendations = await get_usage_recommendations(method_name)
    
    # Step 2: Start with summary if dataset might be large
    if method_name == "get_todos":
        summary = await get_todos(mode="summary", **params)
        
        if summary["count"] > 50:
            print(f"Found {summary['count']} todos")
            print(f"Status: {summary['status_breakdown']}")
            print("This is a large dataset. How would you like to proceed?")
            print("1. Show top 20 priority items")
            print("2. Filter by project/area")
            print("3. Show recent activity only")
            return summary
    
    # Step 3: For smaller datasets, get full data
    return await globals()[method_name](mode="auto", **params)
```

## 🔄 Bulk Operations Best Practices

### Pre-Operation Validation

```python
async def safe_bulk_move(todo_ids: List[str], destination: str):
    """Safe bulk move with validation and progress tracking."""
    
    # Step 1: Validate inputs
    if len(todo_ids) > 100:
        print(f"Moving {len(todo_ids)} items is a large operation.")
        print("Would you like to proceed? (This may take several minutes)")
        # Wait for confirmation
    
    # Step 2: Health check
    health = await health_check()
    if not health["things_running"]:
        return {"error": "Things 3 is not running. Please start it first."}
    
    # Step 3: Sample validation
    try:
        sample_todo = await get_todo_by_id(todo_ids[0])
        print(f"Moving items like: '{sample_todo['name']}'")
    except Exception:
        return {"error": "Some todo IDs may be invalid. Please verify."}
    
    # Step 4: Execute with progress monitoring
    result = await bulk_move_records(
        todo_ids=",".join(todo_ids),
        destination=destination,
        max_concurrent=5  # Conservative for reliability
    )
    
    # Step 5: Report results
    if result["success"]:
        print(f"Successfully moved {result['successful']} items")
        if result["failed"]:
            print(f"Failed to move {len(result['failed'])} items")
    
    return result
```

## ⚡ Performance Optimization

### Context-Aware Requests

```python
# ❌ Context-unsafe pattern
todos = await get_todos()  # Unknown size, may exhaust context
projects = await get_projects(include_items=True)  # Large response

# ✅ Context-safe pattern  
todos = await get_todos(mode="auto")  # Intelligent sizing
project_overview = await get_projects(mode="summary")  # Quick insights

# Get detailed data only when needed
if user_wants_project_details:
    detailed_projects = await get_projects(mode="standard", limit=10)
```

### Response Mode Selection

| Scenario | Recommended Mode | Reasoning |
|----------|------------------|-----------|
| Initial exploration | `auto` | Let system choose optimal |
| Large dataset overview | `summary` | Quick insights, minimal context |
| Daily workflow | `standard` | Good balance of detail/efficiency |
| Bulk operations | `minimal` | IDs + essential fields only |
| Detailed analysis | `detailed` | Full data when specifically needed |
| Debugging/development | `raw` | All original data |

## 🚨 Error Handling Patterns

### Structured Error Recovery

```python
async def robust_todo_creation(title: str, **kwargs):
    """Create todo with comprehensive error handling."""
    
    try:
        result = await add_todo(title=title, **kwargs)
        
        if not result.get("success", True):
            # Handle structured errors
            error_code = result.get("error_code")
            
            if error_code == "TAG_CREATION_RESTRICTED":
                # Offer alternatives
                recovery_actions = result.get("recovery_actions", [])
                for action in recovery_actions:
                    if action["action"] == "use_existing":
                        print(f"Available tags: {result.get('alternatives', [])}")
                        return await add_todo(title=title, tags=None)  # Without tags
            
        return result
        
    except Exception as e:
        # Fallback error handling
        print(f"Unexpected error: {e}")
        
        # Try basic operation
        try:
            return await add_todo(title=title)  # Minimal version
        except Exception:
            return {"error": "Unable to create todo. Please check Things 3 connection."}
```

### Health Check Integration

```python
async def ensure_healthy_operation():
    """Check system health before operations."""
    
    health = await health_check()
    
    if not health["things_running"]:
        return {
            "ready": False,
            "message": "Please start Things 3 application",
            "actions": ["Open Things 3", "Check system permissions"]
        }
    
    # Check queue status for bulk operations
    queue = await queue_status()
    if queue["queue_status"]["active_operations"] > 10:
        return {
            "ready": False,
            "message": "Server is busy with other operations",
            "actions": ["Wait a moment", "Try again in 30 seconds"]
        }
    
    return {"ready": True}
```

## 🎯 User Experience Guidelines

### Conversation Patterns

#### Information Gathering
```python
# Good: Progressive disclosure
print("I can help you manage your Things data. What would you like to do?")
print("1. Review today's tasks")
print("2. Organize projects") 
print("3. Process inbox")
print("4. Search for specific items")

# Better: Context-aware suggestions
capabilities = await get_server_capabilities()
recent_items = await get_recent("1d")

print("Based on your recent activity, you might want to:")
print(f"• Review {len(recent_items)} items created today")
print("• Check today's schedule") 
print("• Organize by project or tag")
```

#### Action Confirmation
```python
# For significant operations
if len(items_to_move) > 5:
    print(f"This will move {len(items_to_move)} items to '{destination}'")
    print("Recent items to be moved:")
    for item in items_to_move[:3]:
        print(f"  • {item['name']}")
    print("Continue? (yes/no)")
```

### Progress Communication

```python
async def communicative_bulk_operation():
    """Bulk operation with user communication."""
    
    print("Starting bulk operation...")
    
    # Step 1: Preparation
    print("📋 Gathering todo information...")
    todos = await get_todos(mode="minimal")
    
    # Step 2: Validation  
    print("✅ Validating operation...")
    # ... validation logic
    
    # Step 3: Execution with progress
    print(f"🔄 Processing {len(todos)} items...")
    result = await bulk_move_records(
        todo_ids=extract_ids(todos),
        destination="today"
    )
    
    # Step 4: Results
    if result["success"]:
        print(f"✅ Successfully processed {result['successful']} items")
    else:
        print(f"⚠️ Completed with {len(result['failed'])} issues")
    
    return result
```

## 🔍 Debugging and Troubleshooting

### Diagnostic Patterns

```python
async def diagnose_issue():
    """Comprehensive system diagnosis."""
    
    print("🔍 Running system diagnostics...")
    
    # Check basic connectivity
    health = await health_check()
    print(f"Things 3 running: {health['things_running']}")
    
    # Check context status
    stats = await context_stats()
    print(f"Context available: {stats['available_for_response_kb']}KB")
    
    # Check queue status
    queue = await queue_status()
    print(f"Active operations: {queue['queue_status']['active_operations']}")
    
    # Get capabilities
    capabilities = await get_server_capabilities()
    print(f"Server healthy: {capabilities['current_status']['server_healthy']}")
    
    # Provide recommendations
    recommendations = await get_usage_recommendations()
    print("💡 Recommendations:")
    for tip in recommendations.get("general", {}).get("performance_tips", []):
        print(f"  • {tip}")
```

## 📝 Code Examples

### Complete Workflow Example

```python
async def smart_todo_management_session():
    """Example of a complete, intelligent todo management session."""
    
    # Step 1: System check
    print("🚀 Starting Things session...")
    health_check_result = await ensure_healthy_operation()
    if not health_check_result["ready"]:
        print(f"⚠️ {health_check_result['message']}")
        return
    
    # Step 2: Discover capabilities
    capabilities = await get_server_capabilities()
    print(f"✅ Connected to {capabilities['server_info']['name']}")
    
    # Step 3: Quick overview
    today = await get_today()
    projects = await get_projects(mode="summary") 
    
    print(f"📅 Today: {len(today)} items")
    print(f"📁 Projects: {projects['count']} active")
    
    # Step 4: Interactive workflow
    print("\nWhat would you like to focus on?")
    # ... user interaction logic
    
    # Step 5: Context-aware operations based on user choice
    # ... implement user's requested actions with error handling
    
    print("✅ Session complete!")
```

## 🎯 Key Takeaways

1. **Always check existing tags before creating new ones**
2. **Use `mode="auto"` as your default starting point**
3. **Implement progressive disclosure for large datasets**
4. **Provide clear communication during bulk operations**
5. **Check system health before significant operations**
6. **Use structured error handling with recovery suggestions**
7. **Monitor context usage for optimal performance**
8. **Ask users for confirmation on significant changes**

Following these guidelines will create a robust, user-friendly experience that maximizes the power of the Things MCP Server while respecting user preferences and system constraints.