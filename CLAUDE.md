# Things 3 MCP Server - AI Assistant Instructions

## Project Overview

**Things 3 MCP Server** - A Model Context Protocol server that enables AI assistants to interact with Things 3 via AppleScript on macOS.

### ✨ Latest Features (v1.2.2)
- **🏷️ Tag Management** - Fixed tag concatenation in all tag operations (add_tags, remove_tags, bulk_update_todos)
- **⚡ Bulk Operations** - Fixed multi-field updates; tags now work correctly in batch operations
- **📅 Date Scheduling** - Reliable scheduling with `today`, `tomorrow`, `someday`, or specific dates (YYYY-MM-DD)
- **✅ Validation** - Parameter validation prevents common errors and edge cases
- **📊 Context Optimization** - Response modes provide 5-12x better performance than documented

### Architecture
- **Framework**: FastMCP 2.0 (Python 3.8+)
- **Integration**: AppleScript via subprocess calls
- **Testing**: pytest with mocked AppleScript operations  
- **Platform**: macOS 12.0+ with Things 3 installed

## Development Guidelines

### Code Style
- Keep it simple and maintainable - no over-engineering
- Follow existing patterns in the codebase
- Add type hints to all new functions
- Document with clear docstrings (Google style)

### Testing Requirements
```bash
# Run tests before committing
pytest                          # Run all tests
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests
pytest --cov=src/things_mcp     # With coverage
```

### File Organization
```
src/things_mcp/     # Source code
tests/              # Test files  
docs/               # Documentation
```

### AppleScript Integration

When working with AppleScript:
1. **Escape quotes properly** - Use `_escape_applescript_string()` 
2. **Handle errors gracefully** - AppleScript can fail silently
3. **Test with real Things 3** - Mock tests don't catch all issues
4. **Check permissions** - Automation access must be granted

Example pattern:
```python
script = f'''
tell application "Things3"
    set newTodo to make new to do with properties {{name:"{escaped_title}"}}
    return id of newTodo
end tell
'''
result = self.applescript_manager.execute_script(script)
```

### Common Issues & Solutions

1. **Tag must exist first**: AI cannot create tags automatically - use `get_tags()` to check available tags
2. **Large data timeouts**: Use response modes (summary, minimal) and pagination
3. **Date formats**: Always use ISO 8601 format (YYYY-MM-DD) for best reliability
4. **Permission errors**: System Settings → Privacy & Security → Automation → Enable Things 3 access

### API Coverage Status
- **Implemented**: 25+ operations (40% of AppleScript API)
- **Tested**: All features verified with comprehensive integration tests
- **Roadmap**: See `docs/ROADMAP.md` for future features
- **Priority**: Focus on daily workflow operations

## 🐛 Recent Bug Fixes (v1.2.2+)

### Fixed: Tag Removal String Parsing

**Issue**: `remove_tags()` was treating tag strings as character arrays, removing individual characters instead of complete tag names.

```python
# ❌ BEFORE (Broken)
remove_tags(todo_id="123", tags="test,Work")
# Would try to remove: ['t','e','s','t',',','W','o','r','k']

# ✅ AFTER (Fixed)
remove_tags(todo_id="123", tags="test,Work")
# Correctly removes: ['test', 'Work']
```

**Correct Usage:**
```python
# Single tag
remove_tags(todo_id="abc123", tags="urgent")

# Multiple tags (comma-separated, no spaces)
remove_tags(todo_id="abc123", tags="test,High,Work")

# Tag names are case-sensitive
remove_tags(todo_id="abc123", tags="Work")  # Removes "Work"
remove_tags(todo_id="abc123", tags="work")  # Removes "work" (different tag)
```

**Notes:**
- Tag names are case-sensitive in Things 3
- Non-existent tags are silently filtered (no error)
- Use comma separation without spaces: `"tag1,tag2,tag3"`

### Fixed: Bulk Update Multi-Field Support

**Issue**: `bulk_update_todos()` was only applying the last field in multi-field updates due to script execution order.

```python
# ❌ BEFORE (Broken - only deadline applied)
bulk_update_todos(
    todo_ids="1,2,3",
    tags="urgent,work",
    deadline="2025-12-31"
)

# ✅ AFTER (Fixed - all fields applied)
bulk_update_todos(
    todo_ids="1,2,3",
    tags="urgent,work",
    deadline="2025-12-31"
)
```

**Correct Usage:**

```python
# Single field updates (always worked)
bulk_update_todos(todo_ids="1,2,3", completed="true")
bulk_update_todos(todo_ids="1,2,3", tags="urgent")
bulk_update_todos(todo_ids="1,2,3", when="today")

# Multi-field updates (now fixed)
bulk_update_todos(
    todo_ids="abc,def,ghi",
    tags="urgent,work",
    when="today",
    notes="Updated via bulk operation"
)

bulk_update_todos(
    todo_ids="1,2,3",
    tags="test,review",
    deadline="2025-12-31",
    notes="Q4 deliverables"
)

# Complete status change with metadata
bulk_update_todos(
    todo_ids="task1,task2",
    completed="true",
    notes="Completed in sprint review"
)
```

**Supported Fields:**
- `title` - Update todo title
- `notes` - Update todo notes
- `when` - Update scheduling (e.g., `"today"`, `"tomorrow"`, `"2025-12-31"`)
- `deadline` - Update deadline date
- `tags` - Replace tags (comma-separated)
- `completed` - Mark as complete (`"true"`) or incomplete (`"false"`)
- `canceled` - Mark as canceled (`"true"`) or active (`"false"`)

**Performance:**
- Processes updates sequentially per todo
- Each todo gets all specified fields updated
- Use for 2-50 todos (for larger batches, consider chunking)

### Testing Notes

Both bugs were discovered through comprehensive edge case testing:
- String parsing validation for tag operations
- Multi-field combination testing for bulk updates
- Integration tests with real Things 3 database

**Regression Prevention:**
- Added unit tests for tag string parsing
- Added integration tests for multi-field bulk updates
- Validated with multiple tag/field combinations

## 🏷️ Tag Management

### Working with Tags

**Important**: Tags must be created in Things 3 before they can be used via the API. The AI assistant cannot create tags programmatically.

```python
# Get all available tags
tags = get_tags()  # Returns count-only by default
tags = get_tags(include_items=true)  # Returns full item lists

# Get todos with a specific tag
work_todos = get_tagged_items(tag="Work")
urgent_todos = get_tagged_items(tag="urgent")
```

### Adding Tags

```python
# Single tag
add_tags(todo_id="abc123", tags="urgent")

# Multiple tags (comma-separated, no spaces)
add_tags(todo_id="abc123", tags="work,urgent,review")

# When creating todos
add_todo(
    title="Review proposal",
    tags="work,urgent,review",  # Comma-separated
    when="today"
)

# Bulk update with tags
bulk_update_todos(
    todo_ids="id1,id2,id3",
    tags="urgent,Q4"  # Replaces existing tags
)
```

### Removing Tags

```python
# Remove single tag
remove_tags(todo_id="abc123", tags="urgent")

# Remove multiple tags (comma-separated, no spaces)
remove_tags(todo_id="abc123", tags="urgent,review,old-tag")

# Tag names are case-sensitive
remove_tags(todo_id="abc123", tags="Work")   # Removes "Work"
remove_tags(todo_id="abc123", tags="work")   # Removes "work" (different tag)
```

### Tag Best Practices

1. **Check Available Tags First**:
   ```python
   # See what tags exist
   tags = get_tags()
   # If tag doesn't exist, ask user to create it in Things 3
   ```

2. **Format Requirements**:
   - Use comma separation: `"tag1,tag2,tag3"`
   - No spaces after commas: `"work,urgent"` not `"work, urgent"`
   - Case-sensitive: `"Work"` ≠ `"work"`

3. **Tag Filtering**:
   - Non-existent tags are silently filtered (no error)
   - Only existing tags will be added/removed
   - Use `get_tags()` to validate tags exist

4. **Tag Search**:
   ```python
   # Search by tag
   search_advanced(tag="urgent", status="incomplete")

   # Get all items with specific tag
   get_tagged_items(tag="work")
   ```

## 🔧 Tool Usage Best Practices

### Response Mode Selection

When working with retrieval tools (`get_todos`, `search_todos`, list tools), use the `mode` parameter for optimal context usage:

**Available Modes:**
- `auto` - Automatically selects optimal mode based on data size (recommended for unknown datasets)
- `summary` - Returns count and preview only (best for large collections)
- `minimal` - Returns essential fields only (IDs, titles, status)
- `standard` - Returns common fields (default for most operations)
- `detailed` - Returns all fields (use only when needed)
- `raw` - Returns unfiltered data

**Workflow Examples:**

1. **Daily Review**
   ```
   get_today(mode='standard', limit=20)
   ```

2. **Project Analysis**
   ```
   # First get overview
   get_todos(project_uuid='...', mode='summary')
   # Then drill down to specifics
   get_todos(project_uuid='...', mode='detailed', limit=10)
   ```

3. **Bulk Operations**
   ```
   # Get IDs efficiently
   search_todos(query='overdue', mode='minimal', limit=100)
   # Perform bulk update
   bulk_update_todos(todo_ids='...', completed='true')
   ```

### Context Budget Guidelines

- **Standard mode**: ~1KB per item
- **Minimal mode**: ~50 bytes per item
- **Summary mode**: Fixed ~200 bytes total
- For 100+ items, always start with `mode='summary'` or `mode='minimal'`

### Performance Tips

1. **Use specific list tools** instead of filtering `get_todos`:
   - `get_today()` is faster than `get_todos()` with date filtering
   - `get_tagged_items(tag='work')` is faster than searching

2. **Batch operations** when possible:
   - Use `bulk_update_todos` for multiple todos (supports multi-field updates)
   - Use `bulk_move_records` instead of multiple `move_record` calls
   - Optimal batch size: 2-50 todos per operation

3. **Multi-field bulk updates** (efficient for large updates):
   ```python
   # Update multiple fields in one operation
   bulk_update_todos(
       todo_ids="id1,id2,id3,id4,id5",
       tags="urgent,Q4",
       when="today",
       notes="Updated in batch review"
   )
   ```

## 📁 Hierarchical Organization (Projects & Areas)

### Organizational Structure

Things 3 supports a 4-level hierarchy:
```
Areas (Life/Work Domains)
└── Projects (Time-bound outcomes)
    └── Todos (Action items)
        └── Checklist Items (Sub-tasks)
```

### Working with Areas

Areas represent life domains (Work, Personal, Learning, etc.):

```python
# Get all areas
areas = get_areas(mode='summary')  # Quick overview
areas = get_areas(mode='standard')  # Full list
areas = get_areas(include_items=true, mode='detailed')  # With projects and todos

# Create project in specific area
add_project(
    title="New Project",
    area_id="abc123",  # Recommended - more reliable
    deadline="2025-12-31"
)

# Or use area name
add_project(
    title="New Project",
    area_title="Personal",  # Convenient but requires unique names
    deadline="2025-12-31"
)
```

### Working with Projects

Projects are time-bound outcomes with associated tasks:

```python
# Create project
project_id = add_project(
    title="Website Redesign",
    area_title="Work",
    deadline="2025-12-31",
    tags="high-priority,design",
    notes="Complete redesign of company website"
)

# Add todos to project (must be done separately)
add_todo(title="Research competitors", list_id=project_id, heading="Research")
add_todo(title="Create wireframes", list_id=project_id, heading="Design")
add_todo(title="Implement homepage", list_id=project_id, heading="Development")

# Update project
update_project(
    id=project_id,
    deadline="2026-01-15",
    tags="urgent,design,review-needed"
)

# Get projects
get_projects(mode='summary')  # Count and preview
get_projects(mode='minimal')  # IDs and names only
get_projects(mode='standard')  # Full details
```

### Moving Todos Between Projects

```python
# Move single todo
move_record(
    todo_id="todo123",
    destination_list="project:project456"
)

# Move multiple todos (bulk operation - much faster)
bulk_move_records(
    todo_ids="todo1,todo2,todo3",
    destination="project:project456",
    preserve_scheduling=true
)
```

### Destination Formats

| Target | Format | Example |
|--------|--------|---------|
| Inbox | `"inbox"` | `move_record(todo_id="123", destination_list="inbox")` |
| Today | `"today"` | `move_record(todo_id="123", destination_list="today")` |
| Anytime | `"anytime"` | `move_record(todo_id="123", destination_list="anytime")` |
| Someday | `"someday"` | `move_record(todo_id="123", destination_list="someday")` |
| Project | `"project:{id}"` | `move_record(todo_id="123", destination_list="project:xyz")` |

### Known Limitations

1. **Project todos parameter not functional**: The `todos` parameter in `add_project()` doesn't create child todos. Create project first, then add todos separately with `list_id` parameter.

2. **Project content queries limited**: `get_todos(project_uuid=...)` has known issues. Use `search_todos()` or `search_advanced()` to find project tasks.

3. **Todo properties don't show project**: Queried todos may not include their parent project reference in properties.

**Workarounds:**
- Create projects then add todos individually with `list_id`
- Use `search_todos()` to find project-related tasks
- Use tags or notes to track project relationships if needed

### Hierarchical Best Practices

1. Use areas for life domains (Work, Personal, Learning)
2. Use projects for time-bound outcomes with clear deadlines
3. Use headings within projects to organize phases
4. Start with `mode='summary'` for large project lists
5. Use `area_id` instead of `area_title` for reliability
6. Batch todo moves with `bulk_move_records()`
7. Create tags in Things 3 before using in API

**For Complete Details:** See `PROJECTS_AREAS_TEST_REPORT.md` and `HIERARCHY_QUICK_REFERENCE.md`

### Error Prevention

1. **Tags must exist** - AI cannot create tags automatically
   - Use `get_tags()` to see available tags
   - Ask user to create new tags if needed
   - Tag names are case-sensitive: `"Work"` ≠ `"work"`
   - Use comma-separated format: `"tag1,tag2"` not `"tag1, tag2"`

2. **Date formats** - Use consistent formats:
   - Dates: `YYYY-MM-DD` or `'today'`, `'tomorrow'`, `'someday'`

3. **Limits** - Respect parameter limits:
   - Search results: max 500
   - Logbook: max 100
   - Date ranges: max 365 days
   - Bulk operations: optimal 2-50 todos

4. **Bulk operations** - Multi-field updates:
   - All specified fields are applied to each todo
   - Fields: title, notes, when, deadline, tags, completed, canceled
   - Format IDs as comma-separated: `"id1,id2,id3"`

## ⚠️ Common Pitfalls & Solutions

### 1. Tag String Formatting

**Problem**: Spaces in comma-separated tags
```python
# ❌ WRONG - includes spaces
add_tags(todo_id="123", tags="work, urgent, review")

# ✅ CORRECT - no spaces
add_tags(todo_id="123", tags="work,urgent,review")
```

### 2. Tag Case Sensitivity

**Problem**: Inconsistent tag capitalization
```python
# These are THREE DIFFERENT tags in Things 3:
add_tags(todo_id="123", tags="Work")   # Tag: "Work"
add_tags(todo_id="123", tags="work")   # Tag: "work"
add_tags(todo_id="123", tags="WORK")   # Tag: "WORK"

# ✅ SOLUTION: Use consistent capitalization
# Check existing tags first:
tags = get_tags()
# Then use exact match
add_tags(todo_id="123", tags="Work")
```

### 3. Non-Existent Tags

**Problem**: Trying to use tags that don't exist
```python
# ❌ Tag doesn't exist - silently ignored
add_todo(title="Task", tags="nonexistent-tag")

# ✅ CORRECT: Check tags first, create if needed
tags = get_tags()
# If tag missing, ask user:
# "The tag 'project-x' doesn't exist. Please create it in Things 3 first."
```

### 4. Bulk Update Field Ordering

**Problem**: Assuming field order matters (it doesn't)
```python
# ✅ Both work identically - all fields applied
bulk_update_todos(todo_ids="1,2,3", tags="urgent", when="today")
bulk_update_todos(todo_ids="1,2,3", when="today", tags="urgent")

# All specified fields are applied to each todo
```

### 5. Multi-Field vs Single-Field Updates

**Problem**: Using single updates when bulk would be faster
```python
# ❌ SLOW - multiple API calls
for todo_id in ["1", "2", "3"]:
    update_todo(id=todo_id, tags="urgent")
    update_todo(id=todo_id, when="today")

# ✅ FAST - single bulk operation
bulk_update_todos(
    todo_ids="1,2,3",
    tags="urgent",
    when="today"
)
```

### 6. Project Todo Creation

**Problem**: Expecting `todos` parameter to work in `add_project()`
```python
# ❌ DOESN'T WORK - todos parameter is non-functional
add_project(
    title="My Project",
    todos="Task 1\nTask 2\nTask 3"  # Won't create todos
)

# ✅ CORRECT: Create project then add todos separately
project_id = add_project(title="My Project", deadline="2025-12-31")
add_todo(title="Task 1", list_id=project_id)
add_todo(title="Task 2", list_id=project_id)
add_todo(title="Task 3", list_id=project_id)
```

### 7. Large Dataset Queries

**Problem**: Retrieving too much data at once
```python
# ❌ BAD - retrieves all todos with full details
all_todos = get_todos(mode='detailed')  # Could be 1000+ items

# ✅ GOOD - use summary first, then drill down
summary = get_todos(mode='summary')  # Just count and preview
# Then get specific subset:
today = get_today(mode='standard', limit=20)
```

### Commit Guidelines
- Make frequent, small commits
- Use clear commit messages
- Run tests before committing
- Update documentation for API changes

## Important Reminders
- Never hardcode authentication tokens
- Keep root directory clean (use appropriate subdirectories)
- Prefer editing existing files over creating new ones
- Test with actual Things 3 before marking features complete
- When we add new capabilities, we need to always be sure to "advertise them" to the AI using the MCP server