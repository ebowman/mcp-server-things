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

### Status Filtering

The `get_todos()` function supports filtering by completion status:

```python
# Get incomplete todos (default behavior)
get_todos(project_uuid="abc123")
get_todos(project_uuid="abc123", status="incomplete")

# Get ALL todos (completed + incomplete + canceled)
get_todos(project_uuid="abc123", status=None)

# Get only completed todos
get_todos(project_uuid="abc123", status="completed")

# Get only canceled todos
get_todos(project_uuid="abc123", status="canceled")

# Works without project filter too
get_todos(status="completed")  # All completed todos
get_todos(status=None)  # All todos regardless of status
```

**Status Parameter Options:**
- `'incomplete'` (default) - Only active, uncompleted todos
- `'completed'` - Only completed todos
- `'canceled'` - Only canceled todos
- `None` - All todos regardless of status

This feature is useful for:
- Reviewing completed work in a project
- Analyzing canceled todos
- Getting complete project history
- Status-based reporting and analytics

### Known Limitations

1. **Checklist Items Not Supported**: ⚠️ **Checklist items CANNOT be created via AppleScript** - This is a Things 3 AppleScript API limitation, not a bug. The `checklist_items` parameter is accepted for API consistency but checklist items will not be created. Only the todo itself is created.

**Root Cause:**
- Things 3 AppleScript dictionary has no checklist/check list item class
- Checklist items can only be created via URL scheme (explicitly excluded per project constraints)
- The parameter validation accepts it but AppleScript silently ignores it

**Alternative:**
- Manually add checklist items in Things 3 after todo creation
- Use notes field to list items as text (e.g., "- [ ] Item 1\n- [ ] Item 2")

2. **Project include_items context explosion**: ⚠️ **NEVER use `get_projects(include_items=true)`** - generates 252K+ tokens for 73 projects, exceeding context limits. Always use `get_projects(mode='summary')` first, then query specific projects.

**Workarounds:**
- Use `get_projects(mode='minimal')` to get IDs, then query specific projects
- Never use `include_items=true` - causes context overflow

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

### 6. Project Creation with Initial Todos

**Best Practice**: Use the `todos` parameter for efficient project creation with initial tasks
```python
# ✅ RECOMMENDED: Create project with todos in one call
project_id = add_project(
    title="My Project",
    deadline="2025-12-31",
    todos="Task 1\nTask 2\nTask 3"  # Creates all 3 todos!
)

# ✅ ALTERNATIVE: Add todos separately (useful for dynamic lists)
project_id = add_project(title="My Project", deadline="2025-12-31")
add_todo(title="Task 1", list_id=project_id)
add_todo(title="Task 2", list_id=project_id)
add_todo(title="Task 3", list_id=project_id)
```

**Note**: The `todos` parameter accepts newline-separated todo titles and creates them atomically with the project.

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

## Release Process

When creating a new release, follow these steps to ensure version consistency across all files:

### 1. Update Version Numbers

**Critical Files (MUST update):**

```bash
# 1. Update package version
# File: pyproject.toml (line 7)
version = "X.Y.Z"

# 2. Update runtime version
# File: src/things_mcp/__init__.py (line 3)
__version__ = "X.Y.Z"

# 3. Update CHANGELOG
# File: CHANGELOG.md (top of file)
## [X.Y.Z] - YYYY-MM-DD

### Fixed
- Bug fix description

### Added
- New feature description

### Changed
- Change description
```

### 2. Commit and Tag

```bash
# Run tests first
pytest

# Commit changes
git add pyproject.toml src/things_mcp/__init__.py CHANGELOG.md
git commit -m "Release vX.Y.Z - Brief description"

# Push to GitHub
git push origin main

# Create and push tag
git tag vX.Y.Z
git push origin vX.Y.Z
```

### 3. Create GitHub Release

```bash
# Create release with notes from CHANGELOG
gh release create vX.Y.Z \
  --title "vX.Y.Z - Release Title" \
  --notes "$(sed -n '/## \[X.Y.Z\]/,/## \[/p' CHANGELOG.md | head -n -1)"
```

### 4. Publish to PyPI

```bash
# Build distribution packages
python -m build

# Upload to PyPI
python -m twine upload dist/mcp_server_things-X.Y.Z*
```

### Version Consistency Notes

- **pyproject.toml** - Package version for pip/PyPI
- **src/things_mcp/__init__.py** - Runtime version (used by server.py)
- **CHANGELOG.md** - Version history with dates
- Version is automatically synced: `__version__` is imported by server.py and reported via `get_server_capabilities()`
- No need to update version in documentation examples (README.md, CONTRIBUTING.md) - those are placeholders

### Release Checklist

- [ ] All tests pass (`pytest`)
- [ ] Version updated in `pyproject.toml`
- [ ] Version updated in `src/things_mcp/__init__.py`
- [ ] CHANGELOG.md updated with date and changes
- [ ] Committed with descriptive message
- [ ] Pushed to GitHub
- [ ] Git tag created and pushed
- [ ] GitHub release created
- [ ] Published to PyPI
- [ ] Verify version reporting: AI should report correct version when queried

## Code Quality Improvements

### Active Refactoring Plan

**Status:** Planning Phase
**Document:** `docs/REFACTORING_PLAN.md`

A comprehensive 10-week, 8-phase refactoring plan has been created to improve code quality:

**Current Issues:**
- 5 bare `except:` blocks hiding errors
- 19 functions >100 lines (largest: 214 lines)
- 4 files >1,300 lines (largest: 1,657 lines)
- 31 duplicate AppleScript invocations
- Complex 193-line string parser

**Target Improvements:**
- Zero bare except blocks (specific exception types + logging)
- All functions <100 lines (target: 80)
- All files <1,000 lines (target: 500)
- Consolidated AppleScript patterns via templates
- State machine-based parser

**Phased Approach:**
1. **Phase 1 (Week 1):** Fix bare except blocks - LOW RISK
2. **Phase 2 (Weeks 2-3):** Parser refactoring - HIGH RISK, feature-flagged
3. **Phase 3 (Weeks 4-5):** Function decomposition - MEDIUM RISK
4. **Phase 4 (Week 6):** File organization - MEDIUM RISK
5. **Phase 5 (Week 7):** Consolidate AppleScript patterns - LOW RISK
6. **Phase 6 (Week 8):** Error handling improvements - LOW RISK
7. **Phase 7 (Week 9):** Documentation - LOW RISK
8. **Phase 8 (Week 10):** Performance testing - LOW RISK

**Constraints:**
- ✅ 100% backwards compatibility (no breaking changes)
- ✅ All 330+ tests must continue to pass
- ✅ No performance regressions >10%
- ✅ Incremental commits (each passes tests)

**For Swarm Implementation:**
- See `docs/REFACTORING_PLAN.md` for detailed task breakdown
- Each phase has specific deliverables and validation steps
- Parallel execution possible for Phase 1, 3, 4 tasks
- Feature flags for high-risk changes (Phase 2)

When implementing refactoring tasks, always:
1. Read the detailed task specification in REFACTORING_PLAN.md
2. Run tests before making changes
3. Make minimal, focused changes
4. Run full test suite after changes
5. Commit only if all tests pass

## Important Reminders
- Never hardcode authentication tokens
- Keep root directory clean (use appropriate subdirectories)
- Prefer editing existing files over creating new ones
- Test with actual Things 3 before marking features complete
- When we add new capabilities, we need to always be sure to "advertise them" to the AI using the MCP server