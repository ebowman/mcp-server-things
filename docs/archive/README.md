# Things 3 MCP Server

A Model Context Protocol (MCP) server for integrating with Things 3 on macOS using FastMCP 2.0.

## Features

- **Core Todo Operations**: Create, read, update, delete todos
- **Project Management**: Create and manage projects
- **Area Management**: Access and organize areas
- **List Access**: Inbox, Today, Upcoming, Anytime, Someday, Logbook, Trash
- **Search**: Basic and advanced search capabilities
- **Tags**: Tag management and filtering
- **Health Monitoring**: Server health checks and connectivity testing

## Requirements

- macOS with Things 3 installed
- Python 3.8+
- AppleScript support (built into macOS)
- FastMCP 2.0+

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd things-applescript-mcp
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure Things 3 is installed and running on your Mac.

## Usage

### Command Line

Start the server:
```bash
python -m src.things_mcp
```

With debug logging:
```bash
python -m src.things_mcp --debug
```

With custom timeout:
```bash
python -m src.things_mcp --timeout 60
```

### Health Check

Check system health:
```bash
python -m src.things_mcp --health-check
```

Test AppleScript connectivity:
```bash
python -m src.things_mcp --test-applescript
```

### As a Module

```python
from src.things_mcp.simple_server import ThingsMCPServer

server = ThingsMCPServer()
server.run()
```

## Available Tools

### Todo Management
- `get_todos(project_uuid?, include_items?)` - Get todos, optionally filtered by project
- `add_todo(title, notes?, tags?, when?, deadline?, ...)` - Create a new todo
- `update_todo(id, title?, notes?, tags?, ...)` - Update an existing todo
- `get_todo_by_id(todo_id)` - Get a specific todo
- `delete_todo(todo_id)` - Delete a todo

### Project Management
- `get_projects(include_items?)` - Get all projects
- `add_project(title, notes?, tags?, ...)` - Create a new project
- `update_project(id, title?, notes?, ...)` - Update a project

### Area Management
- `get_areas(include_items?)` - Get all areas

### List Access
- `get_inbox()` - Get inbox todos
- `get_today()` - Get today's todos
- `get_upcoming()` - Get upcoming todos
- `get_anytime()` - Get anytime todos
- `get_someday()` - Get someday todos
- `get_logbook(limit?, period?)` - Get completed todos
- `get_trash()` - Get trashed todos

### Search & Tags
- `get_tags(include_items?)` - Get all tags
- `get_tagged_items(tag)` - Get items with specific tag
- `search_todos(query)` - Search todos by text
- `search_advanced(status?, type?, tag?, ...)` - Advanced search
- `get_recent(period)` - Get recently created items

### Navigation
- `show_item(id, query?, filter_tags?)` - Show item in Things
- `search_items(query)` - Search and show in Things

### System
- `health_check()` - Check server and Things 3 connectivity

## Configuration

### Environment Variables
- `THINGS_MCP_TIMEOUT` - AppleScript timeout (default: 30 seconds)
- `THINGS_MCP_RETRY_COUNT` - Retry count for failed operations (default: 3)

### Command Line Options
- `--debug` - Enable debug logging
- `--timeout N` - Set AppleScript timeout in seconds
- `--retry-count N` - Set retry count for failed operations
- `--health-check` - Perform health check and exit
- `--test-applescript` - Test AppleScript connectivity and exit
- `--version` - Show version information

## Examples

### Adding a Todo
```python
# Using MCP tool
result = add_todo(
    title="Review project proposal",
    notes="Check budget and timeline sections",
    tags=["work", "urgent"],
    when="today",
    deadline="2023-12-31"
)
```

### Creating a Project
```python
result = add_project(
    title="Website Redesign",
    notes="Complete overhaul of company website",
    area_title="Work",
    todos=["Research competitors", "Create wireframes", "Design mockups"]
)
```

### Searching Todos
```python
# Basic search
results = search_todos("meeting")

# Advanced search
results = search_advanced(
    status="incomplete",
    tag="work",
    deadline="2023-12-31"
)
```

## Error Handling

The server includes comprehensive error handling:

- **AppleScript Errors**: Automatic retry with exponential backoff
- **Things 3 Connectivity**: Health checks and graceful degradation
- **Timeout Handling**: Configurable timeouts for long-running operations
- **Validation**: Input validation for all parameters
- **Logging**: Structured logging for debugging and monitoring

## Architecture

```
src/things_mcp/
├── simple_server.py      # Main FastMCP server
├── applescript_manager.py # AppleScript execution
├── tools.py              # Core tool implementations
├── models.py             # Data models
├── main.py               # CLI entry point
└── __main__.py           # Module entry point
```

## Development

### Running Tests
```bash
python -m pytest tests/
```

### Code Formatting
```bash
black src/ tests/
isort src/ tests/
```

### Type Checking
```bash
mypy src/
```

## Troubleshooting

### Things 3 Not Found
- Ensure Things 3 is installed and running
- Check that AppleScript has necessary permissions
- Run health check: `python -m src.things_mcp --health-check`

### AppleScript Errors
- Increase timeout: `--timeout 60`
- Check macOS security settings for AppleScript
- Test connectivity: `--test-applescript`

### Performance Issues
- Enable caching (default enabled)
- Reduce retry count for faster failures
- Use specific project UUIDs when possible

## License

[License information]

## Contributing

[Contributing guidelines]