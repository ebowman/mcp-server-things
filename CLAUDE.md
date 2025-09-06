# Things 3 MCP Server - AI Assistant Instructions

## Project Overview

**Things 3 MCP Server** - A Model Context Protocol server that enables AI assistants to interact with Things 3 via AppleScript on macOS.

### ✨ Latest Features
- **📅 Reminder Support** - Create and detect todos with specific reminder times
- **⏰ Datetime Scheduling** - Use format `when="today@14:30"` for timed reminders  
- **🔍 Reminder Detection** - Read existing reminders from todos automatically
- **📱 URL Scheme Integration** - Creates system notifications for reminders

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

### Reminder Functionality

The MCP server now supports creating todos with specific time reminders using the `@HH:MM` format in the `when` parameter.

#### Usage Examples:

**Basic Reminder Creation:**
```python
# Create a reminder for today at 6 PM
await tools.add_todo(
    title="Team meeting",
    when="today@18:00"
)

# Create a reminder for tomorrow at 9:30 AM
await tools.add_todo(
    title="Doctor appointment", 
    when="tomorrow@09:30",
    notes="Bring insurance card"
)

# Create a reminder for a specific date and time
await tools.add_todo(
    title="Christmas shopping",
    when="2024-12-20@14:00",
    tags=["personal", "shopping"]
)
```

**Edge Cases Supported:**
- Midnight: `"today@00:00"` or `"today@12:00am"`
- Noon: `"today@12:00"` or `"today@12:00pm"`
- Single-digit hours: `"today@9:30"` or `"today@09:30"`

**Implementation Details:**
- Uses Things URL scheme for reliable reminder creation
- Converts 24-hour format to 12-hour format automatically
- Falls back to AppleScript method if URL scheme fails
- Validates time format before processing
- Gracefully handles malformed input by returning original values

### Common Issues & Solutions

1. **Date scheduling failures**: Use URL scheme method as primary, AppleScript as fallback
2. **Large data timeouts**: Implement pagination and limits (default 100 items)
3. **Circular references**: Sanitize before JSON serialization
4. **Permission errors**: System Settings → Privacy & Security → Automation

### API Coverage Status
- **Implemented**: 25+ operations (40% of AppleScript API) 
- **New**: Reminder functionality with datetime scheduling
- **Roadmap**: See `docs/ROADMAP.md` for missing features
- **Priority**: Focus on daily workflow operations

## 📅 Reminder Functionality Usage Guide

### Creating Todos with Reminders

Use the datetime format `YYYY-MM-DD@HH:MM` or relative dates with time:

```python
# Create todo with specific reminder time
await add_todo(
    title="Call dentist", 
    when="today@14:30",  # 2:30 PM today
    tags=["personal"]
)

# Create todo with natural language + time
await add_todo(
    title="Team meeting prep",
    when="tomorrow@09:00",  # 9:00 AM tomorrow
    notes="Prepare quarterly review slides"
)
```

### Reading Todos with Reminders

All todo retrieval functions now include reminder information:

```python
todos = await get_todos()
for todo in todos:
    if todo.has_reminder:
        print(f"{todo.title} - Reminder at {todo.reminder_time}")
        print(f"Activation date: {todo.activation_date}")
```

### Reminder Field Reference

**New Fields in Todo/Project Models:**
- `has_reminder: bool` - True if reminder time is set
- `reminder_time: str` - Time in "HH:MM" format (e.g., "14:30")  
- `activation_date: datetime` - Full datetime when todo becomes active

### Requirements for Reminders

1. **Things 3 Configuration**: Enable URL schemes in Things 3 settings
2. **Auth Token**: Configure auth token for system notifications
3. **macOS**: Reminder notifications work through macOS notification center

### Backward Compatibility

- Existing date-only scheduling works unchanged (`when="today"`)
- New datetime format is additive (`when="today@14:30"`) 
- All existing APIs return reminder fields (False/None if no reminder)

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