# Things 3 MCP Server - AI Assistant Instructions

## Project Overview

**Things 3 MCP Server** - A Model Context Protocol server that enables AI assistants to interact with Things 3 via AppleScript on macOS.

### ✨ Latest Features (v1.5.0)
- **🩺 Boot Diagnostics** - stderr boot-phase markers, a startup watchdog, and a bounded lazy import of `things` to make cold-start hangs diagnosable (see below)
- **🏷️ Tag Management** - Fixed tag concatenation in all tag operations (add_tags, remove_tags, bulk_update_todos)
- **⚡ Bulk Operations** - Fixed multi-field updates; tags now work correctly in batch operations
- **📅 Date Scheduling** - Reliable scheduling with `today`, `tomorrow`, `someday`, or specific dates (YYYY-MM-DD)
- **✅ Validation** - Parameter validation prevents common errors and edge cases
- **📊 Context Optimization** - Response modes provide 5-12x better performance than documented

### Architecture
- **Framework**: FastMCP 3.x (Python 3.8+)
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

### Boot Diagnostics (v1.5.0+)

The server emits timestamped `things-mcp boot: <ts> +<elapsed>s <phase>` marker
lines to stderr at each boot phase, and arms a one-shot watchdog
(`THINGS_MCP_BOOT_WATCHDOG_SECS`, default 25s, `<= 0` disables) that dumps all
thread stacks to stderr if boot stalls past the deadline - one benign dump on
a healthy long-running server is expected. The third-party `things` package
import is lazy and timeout-bounded (`THINGS_MCP_THINGS_IMPORT_TIMEOUT_SECS`,
default 10s, `<= 0` is unbounded) since it performs an unbounded filesystem
glob at import time; a stall raises `ThingsImportTimeoutError` with a boot
marker instead of hanging silently. See README "Boot diagnostics" for the
diagnosis recipe.

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

The configured `tag_creation_policy` (allow_all / filter_silent / filter_warn / fail_on_unknown) applies uniformly to todos, projects, and areas - tags are validated and filtered before any write, not just for todos.

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

### Tag Usage Report (Cleanup)

`get_tag_usage()` reports open/total/area item counts per tag in a single pass over
todos, projects, and areas, sorted by usage (highest first) — useful for weekly-review
tag cleanup:

```python
# Full usage report, sorted by open_count desc, then total_count desc, then title
get_tag_usage()

# Only tags with zero items anywhere (open, completed/canceled, or areas) - cleanup candidates
get_tag_usage(only_unused=True)

# Response modes: 'summary' (counts + top 5), 'minimal' (title+open_count),
# 'standard'/'detailed' (full rows: title, uuid, open_count, total_count, area_count)
get_tag_usage(mode="summary")
```

**Caveats:**
- **Title collisions**: Usage is keyed by tag *title*, not uuid. If two distinct tags
  share the exact same title (e.g. a parent tag and a same-named child tag), their
  counts are merged into a single row and the reported `uuid` is whichever tag was
  returned last for that title — it cannot be used to disambiguate the merged tags.
- **Area tags**: Tags applied only to Areas are counted via `area_count` and included
  in `total_count`, so an area-only tag will not show up as unused. Areas have no
  open/closed state, so area usage never contributes to `open_count`.

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

### Structured Output

All read tools (`get_today`, `get_inbox`, `get_upcoming`, `get_anytime`, `get_someday`, `get_logbook`, `get_trash`, `get_todos`, `get_projects`, `get_areas`, `get_tags`, `get_tagged_items`, `get_recent`, `search_todos`, `search_advanced`, `get_todo_by_id`, `get_due_in_days`, `get_activating_in_days`, `get_tag_usage`) return both human-readable text and machine-readable `structured_content` (via FastMCP 3.x's automatic dict serialization). MCP clients that support structured output can read `structured_content` directly instead of re-parsing the text.

The structured shape is consistent across list-returning tools:
```json
{"items": [...], "count": 3, "total": 42, "mode": "standard", "limit": 20, "offset": null}
```
- `items` - the item dicts for the effective response `mode` (see Response Mode Selection below)
- `count` - `len(items)`
- `total` - total items available before any `limit` was applied (falls back to `count` when the true pre-limit total isn't tracked separately, e.g. `get_tag_usage`)
- `mode` / `limit` / `offset` - echoed back from the effective request; when the caller passes `mode='auto'` (or omits `mode`), `mode` reports the concrete mode AUTO selection actually resolved to (e.g. `"minimal"`), never the literal string `"auto"` - the originally-requested value (`"auto"` or `None`) is preserved separately in `requested_mode`

Single-item lookups (`get_todo_by_id`) use `{"item": {...}}` instead.

**The `mode` parameter shapes structured output exactly as it shapes text** - under `mode='summary'`, `items` is a small preview (not the full list), matching the context-explosion protection already documented below; `minimal` returns minimal fields; `standard`/`detailed` return the fields described in the Context Budget Guidelines below. Because `items` is only a preview under `mode='summary'`, `count` in that mode is the number of preview items returned (not the full dataset size) - the full pre-limit dataset size is always in `total`.

### Someday: opt-in project-task inheritance

`get_someday(include_project_tasks?)` defaults to `include_project_tasks=false` and returns only items whose own start state is Someday (`things.someday()`). Things 3 also lets tasks inherit "Someday" from a parent project even when things.py reports their own start state as Anytime/other; on databases with many Someday projects this inherited set can be very large (in practice, many times larger than the native set) and, under response-mode truncation, would crowd out the native items. Pass `include_project_tasks=true` to also include those inherited tasks - each is marked `inheritedSomeday: true` in the response so callers can distinguish them. This only affects `get_someday`; `get_today`, `get_anytime`, and `get_upcoming` always exclude tasks that belong to a Someday project (matching Things UI behavior) regardless of this flag.

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

# Create a new area
new_area = add_area(title="Side Projects")
add_area(title="Side Projects", tags="work,priority")  # tags must already exist in Things 3

# Rename an area and/or update its tags
update_area(id=new_area["area_id"], title="Side Hustles")
update_area(id=new_area["area_id"], tags="work,priority")  # replaces existing tags

# Note: there is no delete_area tool - deleting an area also deletes its
# projects, so area deletion is intentionally not exposed via this API.
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

### Checklist Support ✅

**Checklist items are now fully supported** via the Things 3 URL scheme API. The server automatically uses the URL scheme when checklist items are provided.

#### Creating Todos with Checklists

```python
# Create todo with checklist items
add_todo(
    title="Grocery Shopping",
    notes="Weekly shopping list",
    checklist_items=["Milk", "Bread", "Eggs", "Butter"],  # List of strings
    when="today"
)

# With project and tags
add_todo(
    title="Release v2.0",
    checklist_items=["Run tests", "Update docs", "Create changelog", "Tag release"],
    list_id="project123",
    tags="work,release",
    deadline="2025-12-31"
)
```

#### Managing Checklist Items

```python
# Add items to existing todo (appends to end)
add_checklist_items(
    todo_id="abc123",
    items=["New item 1", "New item 2"]
)

# Prepend items to beginning
prepend_checklist_items(
    todo_id="abc123",
    items=["Urgent item", "High priority"]
)

# Replace all checklist items
replace_checklist_items(
    todo_id="abc123",
    items=["Item 1", "Item 2", "Item 3"]
)

# Clear all checklist items
replace_checklist_items(
    todo_id="abc123",
    items=[]  # Empty list clears checklist
)
```

**Format Requirements:**
- Items are passed as a list of strings: `["item1", "item2", "item3"]`
- Maximum 100 checklist items per todo
- Items can be marked complete/incomplete in Things 3 UI

**Implementation Details:**
- Checklists use Things URL scheme API (not AppleScript)
- URL scheme is automatically used when `checklist_items` parameter is provided
- Todo ID is retrieved after creation by searching for the newly created todo
- Non-checklist todos still use faster AppleScript approach

### Known Limitations

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

Publishing is **automated by CI**. Creating a GitHub Release triggers
`.github/workflows/publish.yml`, which runs the test gate, builds the package,
publishes to PyPI via trusted publishing, and then **verifies** the version is
live on PyPI (failing loudly if it isn't). Do not run `twine upload` manually
unless trusted publishing is broken (see break-glass below).

### 1. Bump the version (single source of truth)

The version lives in **one** place — `src/things_mcp/__init__.py`. `pyproject.toml`
reads it dynamically (`[tool.setuptools.dynamic] version = {attr = "things_mcp.__version__"}`),
and `server.py` / `--version` import the same `__version__`.

```bash
# File: src/things_mcp/__init__.py
__version__ = "X.Y.Z"
```

Then add the matching section to `CHANGELOG.md` (top of file):

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Fixed
- Bug fix description
```

### 2. Commit and tag

```bash
pytest tests/unit                       # gate also runs in CI
git add src/things_mcp/__init__.py CHANGELOG.md
git commit -m "Release vX.Y.Z - Brief description"
git push origin main

git tag vX.Y.Z
git push origin vX.Y.Z
```

### 3. Create the GitHub Release (this publishes to PyPI)

```bash
gh release create vX.Y.Z \
  --title "vX.Y.Z - Release Title" \
  --notes "$(sed -n '/## \[X.Y.Z\]/,/## \[/p' CHANGELOG.md | head -n -1)"
```

CI then runs `test → build → publish-to-pypi → verify-pypi`. Watch it:

```bash
gh run watch "$(gh run list --workflow=publish.yml --limit 1 --json databaseId --jq '.[0].databaseId')" --exit-status
```

If `publish-to-pypi` fails with `403 ... OIDC scoped token is not valid for
project`, a trusted publisher for this repo+workflow is registered on the wrong
PyPI project. Fix it under the `mcp-server-things` project's Publishing settings
(repo `ebowman/mcp-server-things`, workflow `publish.yml`, environment `pypi`)
and remove any stray publisher on other projects, then re-run the workflow.

### 4. Build and attach the .mcpb bundle

```bash
scripts/build_mcpb.sh
gh release upload vX.Y.Z dist/mcp-server-things-X.Y.Z.mcpb
```

### Break-glass: manual upload

Only if CI publishing is broken and the release must ship:

```bash
python -m build
python -m twine check dist/mcp_server_things-X.Y.Z*
python -m twine upload dist/mcp_server_things-X.Y.Z*   # uses ~/.pypirc token
```

### Release Checklist

- [ ] Version bumped in `src/things_mcp/__init__.py` (only here)
- [ ] CHANGELOG.md updated with date and changes
- [ ] `pytest tests/unit` passes
- [ ] Committed, pushed to `main`, tag pushed
- [ ] GitHub Release created
- [ ] CI `publish.yml` green through `verify-pypi` (confirms PyPI is live)
- [ ] Built .mcpb (`scripts/build_mcpb.sh`) and attached `dist/*.mcpb` to the GitHub release
- [ ] manifest tools list is generated — run `scripts/gen_manifest_tools.py --write` after adding/removing tools
- [ ] AI reports the correct version when queried (`--version` / `get_server_capabilities`)

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
<!-- The section below is machine-managed by domestique: https://github.com/ebowman/domestique -->
<!-- BEGIN domestique (managed) -->
# Orchestration policy

This session is the **orchestrator**. Your job is planning, delegation, and review — not implementation.

## Roles
- **You (main session, planning model):** decompose work, hold the plan, delegate implementation and review, adjudicate the results, decide what's next. Write code yourself only for trivial one-line edits.
- **`implementer` subagent (Sonnet):** executes one bounded task at a time in its own context and reports back a summary.
- **`reviewer` subagent (Opus):** independently verifies a completed task in a fresh context — inspects the real diff, reads the changed files, runs the tests — and reports a pass/fail verdict against the bead's done-criteria. A stronger, non-peer check than the implementer. Does not fix anything; reviewing is its only job.

## Work tracking: beads
- The plan of record lives in beads (`bd`), not in markdown TODO lists.
- Decompose a goal into an epic + bounded tasks with dependencies using `/decompose`.
- Select the next unit of work with `bd ready` — it returns only unblocked, actionable tasks.
- Record durable insight with `bd remember "<insight>"`. Do not create MEMORY.md files.

## Writing briefs
Plans, bead descriptions, and delegation briefs are executed by a separate model with no access to your reasoning. When you write them:
- Write numbered steps; each step names an action, a target file/symbol, and an acceptance criterion.
- Spell out edge cases and error handling — do not leave them implicit.
- Flag ambiguities explicitly rather than resolving them silently.

## Delegation loop
1. `bd ready` → pick the highest-priority unblocked task.
2. Delegate it to the `implementer` subagent with a precise brief and the bead id.
3. When the implementer returns, delegate verification to the `reviewer` subagent with the same bead id and its done-criteria. The reviewer inspects the real diff, reads the changed files, and runs the tests in a fresh context — judging the work against the done-criteria, not against the implementer's summary — and returns a pass/fail verdict.
4. Adjudicate. Weigh the reviewer's verdict against the implementer's summary: if they agree the work is done, close the bead and commit its changes (one commit, bead id in the message); if the reviewer reports gaps, reopen the bead or file a follow-up and route the fix back to the implementer. Read the diff yourself only when the two reports conflict or the verdict is ambiguous — delegating the review is the point.
5. **Stop and report to the human before dispatching the next task.** Do not drain the queue unattended unless explicitly told to.

## Unattended epic mode (/goal)
- The default remains **stop-and-report between beads** (rule 5 of the Delegation loop above). Nothing changes that by itself.
- A `/goal <epic-id>` invocation is the **only** thing that authorizes continuous, unattended dispatch across an epic's beads. That authorization is scoped to the named epic, expires the instant the epic completes or any stop condition fires, and never carries over to another epic or a later session.
- Unattended runs happen on a **dedicated epic branch** and never commit to the default branch — the human reviews and merges that branch by hand; the loop never merges or pushes.
- The core invariants still hold even while unattended: **one bead in flight at a time, one commit per bead, and never close a bead the reviewer didn't pass.**
- For the full loop mechanics and the complete list of stop conditions, see `.claude/commands/goal.md` — they are not restated here.

## Discipline
- One task in flight at a time. Bounded WIP.
- Subagents return summaries, never full file dumps. Your context is the constraint — keep it lean, don't re-read large outputs.
- Do not spawn agent teams for this sequential pipeline. Subagents only.
- At session end ("land the plane"): file any loose discovered work as beads, then sync (`bd sync --flush-only` and commit `.beads/`).
<!-- END domestique -->
