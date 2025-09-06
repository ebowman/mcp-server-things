# Things 3 MCP Server

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![macOS](https://img.shields.io/badge/macOS-12+-green.svg)](https://www.apple.com/macos/)

A Model Context Protocol (MCP) server that connects Claude and other AI assistants to Things 3 for natural language task management.

## Installation

### From Source

1. Clone the repository:
```bash
git clone https://github.com/ebowman/mcp-server-things.git
cd mcp-server-things
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Install in development mode:
```bash
pip install -e .
```

### Claude Desktop Configuration

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "things": {
      "command": "/path/to/mcp-server-things/venv/bin/python",
      "args": ["-m", "things_mcp"],
      "env": {
        "PYTHONPATH": "/path/to/mcp-server-things/src",
        "THINGS_MCP_LOG_LEVEL": "INFO",
        "THINGS_MCP_APPLESCRIPT_TIMEOUT": "30"
      }
    }
  }
}
```

**Note:** 
- Replace `/path/to/mcp-server-things` with your actual installation path
- Use the full path to the Python executable in your virtual environment
- See Configuration section below for environment variable options

![Demo showing Claude creating tasks in Things 3](demo.gif)
*Creating tasks with natural language through Claude*

## Features

### Core Todo Operations
- **Create**: Add todos with full metadata (tags, deadlines, projects, notes, reminders)
- **Read**: Get todos by ID, project, or built-in lists (Today, Inbox, Upcoming, etc.)
- **Update**: Modify existing todos with partial updates
- **Delete**: Remove todos safely
- **Search**: Find todos by title, notes, or advanced filters

### Project & Area Management
- Get all projects and areas with optional task inclusion
- Create new projects with initial todos
- Update project metadata and status
- Organize todos within project hierarchies

### Built-in List Access
- **Inbox**: Capture new items
- **Today**: Items scheduled for today
- **Upcoming**: Future scheduled items
- **Anytime**: Items without specific dates
- **Someday**: Items for future consideration
- **Logbook**: Completed items history
- **Trash**: Deleted items

### Advanced Features
- **Reminder Support**: Create todos with specific reminder times (e.g., "today@14:30")
- **Tag Management**: Full tag support with AI creation control
- **Date-Range Queries**: Get todos due/activating within specific timeframes
- **URL Schemes**: Native Things 3 URL scheme integration
- **Health Monitoring**: System health checks and queue status monitoring
- **Error Handling**: Robust error handling with configurable retries
- **Logging**: Structured logging with configurable levels
- **Concurrency Support**: Multi-client safe operation with operation queuing
- **Input Validation**: Configurable limits for titles, notes, and tags

## Requirements

- **macOS**: This server requires macOS (tested on macOS 12+)
- **Things 3**: Things 3 must be installed and accessible
- **Python**: Python 3.8 or higher
- **Permissions**: AppleScript permissions for Things 3 access

## Quick Start

Once installed, Claude (or other MCP clients) can automatically discover and use all available tools. No additional setup required.

## Configuration

The server can be configured using environment variables. A complete example configuration is provided in `.env.example`.

### Using .env.example

1. **Review the example configuration:**
   ```bash
   cat .env.example
   ```

2. **Create your own .env file (optional):**
   ```bash
   cp .env.example .env
   # Edit .env to customize settings
   ```

3. **Key Configuration Options:**

   ```bash
   # Server identification
   THINGS_MCP_SERVER_NAME=things3-mcp-server
   THINGS_MCP_SERVER_VERSION=1.0.0
   
   # AppleScript execution
   THINGS_MCP_APPLESCRIPT_TIMEOUT=30.0       # Timeout in seconds (1-300)
   THINGS_MCP_APPLESCRIPT_RETRY_COUNT=3      # Retry attempts (0-10)
   
   # Tag management - Control AI tag creation
   THINGS_MCP_AI_CAN_CREATE_TAGS=false       # false = AI can only use existing tags
   THINGS_MCP_TAG_VALIDATION_CASE_SENSITIVE=false
   
   # Logging
   THINGS_MCP_LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR, CRITICAL
   THINGS_MCP_ENABLE_DEBUG_LOGGING=false
   
   # Validation limits
   THINGS_MCP_MAX_TITLE_LENGTH=500
   THINGS_MCP_MAX_NOTES_LENGTH=10000
   THINGS_MCP_MAX_TAGS_PER_ITEM=20
   THINGS_MCP_SEARCH_RESULTS_LIMIT=100
   ```

### Environment Variable Loading

The server automatically loads environment variables in this order:
1. System environment variables
2. `.env` file in the project root (if using python-dotenv)
3. Variables specified in Claude Desktop config

### Claude Desktop Environment Variables

You can set environment variables directly in your Claude Desktop configuration:

```json
{
  "mcpServers": {
    "things": {
      "env": {
        "THINGS_MCP_LOG_LEVEL": "DEBUG",
        "THINGS_MCP_AI_CAN_CREATE_TAGS": "true",
        "THINGS_MCP_APPLESCRIPT_TIMEOUT": "60"
      }
    }
  }
}
```

## Available MCP Tools

### Todo Management
- `get_todos(project_uuid?, include_items?)` - List todos
- `add_todo(title, ...)` - Create new todo with optional reminder time
- `update_todo(id, ...)` - Update existing todo
- `get_todo_by_id(todo_id)` - Get specific todo
- `delete_todo(todo_id)` - Delete todo

### Project Management
- `get_projects(include_items?)` - List projects
- `add_project(title, ...)` - Create new project
- `update_project(id, ...)` - Update existing project

### Area Management
- `get_areas(include_items?)` - List areas

### List Access
- `get_inbox()` - Get Inbox todos
- `get_today()` - Get Today's todos
- `get_upcoming()` - Get upcoming todos
- `get_anytime()` - Get Anytime todos
- `get_someday()` - Get Someday todos
- `get_logbook(limit?, period?)` - Get completed todos
- `get_trash()` - Get trashed todos

### Date-Range Queries
- `get_due_in_days(days)` - Get todos due within specified days
- `get_activating_in_days(days)` - Get todos activating within days
- `get_upcoming_in_days(days)` - Get todos due or activating within days

### Search & Tags
- `search_todos(query)` - Basic search
- `search_advanced(...)` - Advanced search with filters
- `get_tags(include_items?)` - List tags
- `create_tag(name)` - Create a new tag
- `get_tagged_items(tag)` - Get items with specific tag
- `add_tags(todo_id, tags)` - Add tags to a todo
- `remove_tags(todo_id, tags)` - Remove tags from a todo
- `get_recent(period)` - Get recently created items

### Bulk Operations
- `move_record(record_id, to_parent_uuid)` - Move single record
- `bulk_move_records(record_ids, to_parent_uuid)` - Move multiple records

### System & Utilities
- `health_check()` - Check server and Things 3 status
- `queue_status()` - Check operation queue status and statistics
- `get_server_capabilities()` - Get server features and configuration
- `get_usage_recommendations()` - Get usage tips and best practices
- `context_stats()` - Get context-aware response statistics


## Troubleshooting

### Common Issues

#### Permission Denied Errors
```bash
# Grant AppleScript permissions to your terminal/IDE
# System Preferences > Security & Privacy > Privacy > Automation
# Enable access for your terminal application to control Things 3
```

#### Things 3 Not Found
```bash
# Verify Things 3 is installed and running
python -m things_mcp.main --health-check

# Check if Things 3 is in Applications folder
ls /Applications/ | grep -i things
```

#### Connection Timeouts
```bash
# Increase timeout value via environment variable
export THINGS_MCP_APPLESCRIPT_TIMEOUT=60

# Or in your .env file
THINGS_MCP_APPLESCRIPT_TIMEOUT=60
```

### Debug Mode

```bash
# Enable debug logging
python -m things_mcp.main --debug

# Check logs
tail -f things_mcp.log
```

### Health Diagnostics

```bash
# Comprehensive health check
python -m things_mcp.main --health-check

# Test specific components
python -m things_mcp.main --test-applescript
```

## Performance

- **Startup Time**: Less than 2 seconds
- **Response Time**: Less than 500ms for most operations
- **Memory Usage**: 15MB baseline, 50MB under concurrent load
- **Concurrent Requests**: Serialized write operations to prevent conflicts
- **Throughput**: Multiple operations per second depending on complexity
- **Queue Processing**: Less than 50ms latency for operation enqueuing

## Security

- No network access required (local AppleScript only)
- No data stored outside of Things 3
- Minimal system permissions needed
- Secure AppleScript execution with timeouts
- Input validation on all parameters

## Contributing

Contributions are welcome! Please follow these guidelines:

- Set up a virtual environment and install dependencies
- Follow existing code style and patterns
- Add tests for new features
- Submit pull requests with clear descriptions

## Documentation

- [Troubleshooting Guide](docs/TROUBLESHOOTING.md) - Common issues and solutions
- [Development Roadmap](docs/ROADMAP.md) - Implementation status and missing features

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/ebowman/mcp-server-things/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ebowman/mcp-server-things/discussions)
- **Email**: ebowman@boboco.ie

## Roadmap

### Phase 1: Core Stability (Current)
- Complete MCP tool implementation (Completed)
- Robust error handling and logging (Completed)
- Comprehensive testing suite (Completed)
- Documentation and examples (Completed)

### Phase 2: Enhanced Features
- Multi-client concurrency support with operation queuing (Completed)
- Configurable tag creation policies (Completed)
- Reminder support with datetime scheduling (Completed)
- Date-range query tools (Completed)
- Bulk move operations (Completed)
- Real-time sync with Things 3 changes (Planned)
- Advanced natural language processing (Planned)
- Integration with calendar and email (Planned)

### Phase 3: Advanced Integration
- Multi-user support (Planned)
- API rate limiting (Planned)
- Webhook support (Planned)
- Analytics and reporting (Planned)

---

Built for the Things 3 and MCP community.