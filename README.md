# Things 3 MCP Server

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![macOS](https://img.shields.io/badge/macOS-12+-green.svg)](https://www.apple.com/macos/)

A Model Context Protocol (MCP) server that connects Claude and other AI assistants to Things 3 for natural language task management.

## Installation

> **Automation permission note:** Unlike servers that rely solely on the Things
> URL scheme, this server drives Things 3 via AppleScript for most write
> operations. The first time it does so, macOS will prompt you to grant your
> MCP client (e.g. Claude Desktop) **Automation** access to Things 3 (System
> Settings → Privacy & Security → Automation). This is a one-time prompt but
> is required regardless of which installation option below you choose.

### Option 0: One-click .mcpb (Claude Desktop)

1. Download the latest `.mcpb` file from the [releases page](https://github.com/ebowman/mcp-server-things/releases)
2. Double-click the `.mcpb` file to install it into Claude Desktop
3. Approve the Automation permission prompt for Things 3 the first time the server writes a todo
4. Done — no virtual environment or `PYTHONPATH` configuration required

The bundle launches the server via `uvx`, so [uv](https://docs.astral.sh/uv/) must be installed and on `PATH` (`brew install uv`). Note: the .mcpb/uvx path works from the next PyPI release onward — the currently published wheel predates the console-script fix that makes `uvx mcp-server-things` resolve correctly.

### Option 1: uvx (Any MCP Client)

With [uv](https://docs.astral.sh/uv/) installed (`brew install uv`), the package can be run directly without a manual virtual environment:

```bash
uvx mcp-server-things
```

Configure your MCP client to use `uvx` with `mcp-server-things` as the argument, e.g. for Claude Desktop:

```json
{
  "mcpServers": {
    "things": {
      "command": "uvx",
      "args": ["mcp-server-things"]
    }
  }
}
```

### Option 2: From PyPI

1. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

2. Install the package:
```bash
pip install mcp-server-things
```

### Option 3: From Source (Development)

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

## Claude Desktop Configuration

### For PyPI Installation

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "things": {
      "command": "/path/to/your/venv/bin/python",
      "args": ["-m", "things_mcp"],
      "env": {
        "THINGS_MCP_LOG_LEVEL": "INFO",
        "THINGS_MCP_APPLESCRIPT_TIMEOUT": "30"
      }
    }
  }
}
```

### For Source Installation

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

**Notes:** 
- **PyPI**: Replace `/path/to/your/venv/bin/python` with your virtual environment's Python path
- **Source**: Replace `/path/to/mcp-server-things` with your actual installation path and include the `PYTHONPATH`
- Use the full path to the Python executable in your virtual environment
- See Configuration section below for environment variable options

![Demo showing Claude creating tasks in Things 3](demo.gif)
*Creating tasks with natural language through Claude*

## 📚 Documentation

- **[User Examples](docs/USER_EXAMPLES.md)** - Rich examples of how to use Things 3 with AI assistants
- **[Architecture Overview](docs/ARCHITECTURE.md)** - Technical design and implementation details
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - Common issues and solutions

## Features

### Core Todo Operations
- **Create**: Add todos with full metadata (tags, deadlines, projects, notes)
- **Read**: Get todos by ID, project, or built-in lists (Today, Inbox, Upcoming, etc.)
- **Update**: Modify existing todos with partial updates
- **Delete**: Remove todos safely
- **Search**: Find todos by title, notes, or advanced filters

### Project & Area Management
- Get all projects and areas with optional task inclusion
- Create new projects with initial todos
- Update project metadata and status
- Create and rename areas, including tags (`add_area`, `update_area`)
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
- **Tag Management**: Full tag support with AI creation control, plus usage reporting (`get_tag_usage`) for weekly-review cleanup
- **Date-Range Queries**: Get todos due/activating within specific timeframes
- **URL Schemes**: Native Things 3 URL scheme integration
- **Health Monitoring**: System health checks and queue status monitoring
- **Error Handling**: Robust error handling with configurable retries
- **Logging**: Structured logging with configurable levels
- **Concurrency Support**: Multi-client safe operation with operation queuing
- **Input Validation**: Configurable limits for titles, notes, and tags
- **Structured Output**: Every read tool returns both human-readable text and machine-readable `structured_content` (via FastMCP 3.x) with a consistent `{items, count, total, mode, limit, offset}` shape (`{item: {...}}` for single-item lookups like `get_todo_by_id`), so clients can consume results programmatically without re-parsing text

## Requirements

- **macOS**: This server requires macOS (tested on macOS 12+)
- **Things 3**: Things 3 must be installed and accessible
- **Python**: Python 3.8 or higher
- **Permissions**: AppleScript permissions for Things 3 access

## Quick Start

Once installed, Claude (or other MCP clients) can automatically discover and use all available tools. No additional setup required.

## Configuration

The server uses environment variables for configuration. You can set these variables in three ways:
1. System environment variables
2. A `.env` file (automatically loaded from the current directory)
3. A custom `.env` file specified with `--env-file`

### Using the .env File

1. **Review the example configuration:**
   ```bash
   cat .env.example
   ```

2. **Create your own .env file:**
   ```bash
   cp .env.example .env
   # Edit .env to customize settings
   ```

3. **Or use a custom location:**
   ```bash
   cp .env.example ~/my-things-config.env
   python -m things_mcp --env-file ~/my-things-config.env
   ```

### Key Configuration Options

```bash
# Server identification
THINGS_MCP_SERVER_NAME=things3-mcp-server

# AppleScript execution
THINGS_MCP_APPLESCRIPT_TIMEOUT=30.0       # Timeout in seconds (1-300)
THINGS_MCP_APPLESCRIPT_RETRY_COUNT=3      # Retry attempts (0-10)

# Tag management - Control AI tag creation
THINGS_MCP_AI_CAN_CREATE_TAGS=false       # false = AI can only use existing tags
THINGS_MCP_TAG_VALIDATION_CASE_SENSITIVE=false

# Logging
THINGS_MCP_LOG_LEVEL=INFO                 # DEBUG, INFO, WARNING, ERROR, CRITICAL
THINGS_MCP_LOG_FILE_PATH=/path/to/file.log # Optional: log to file instead of console

# Validation limits
THINGS_MCP_MAX_TITLE_LENGTH=500
THINGS_MCP_MAX_NOTES_LENGTH=10000
THINGS_MCP_MAX_TAGS_PER_ITEM=20
THINGS_MCP_SEARCH_RESULTS_LIMIT=100
```

### Command Line Options

The server supports several command-line options:

```bash
# Start with debug logging
python -m things_mcp --debug

# Use a custom .env file
python -m things_mcp --env-file ~/my-config.env

# Check system health
python -m things_mcp --health-check

# Test AppleScript connectivity
python -m things_mcp --test-applescript

# Show version
python -m things_mcp --version

# Customize timeout and retry settings
python -m things_mcp --timeout 60 --retry-count 5
```

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
- `add_todo(title, ...)` - Create new todo
- `update_todo(id, ...)` - Update existing todo
- `bulk_update_todos(todo_ids, ...)` - Update multiple todos in one operation
- `get_todo_by_id(todo_id)` - Get specific todo
- `delete_todo(todo_id)` - Delete todo

### Project Management
- `get_projects(include_items?)` - List projects
- `add_project(title, ...)` - Create new project
- `update_project(id, ...)` - Update existing project

### Area Management
- `get_areas(include_items?)` - List areas
- `add_area(title, tags?)` - Create new area
- `update_area(id, title?, tags?)` - Update existing area

### List Access
- `get_inbox()` - Get Inbox todos
- `get_today()` - Get Today's todos
- `get_upcoming(days?)` - Get upcoming todos (with optional days filter)
- `get_anytime()` - Get Anytime todos
- `get_someday(include_project_tasks?)` - Get Someday todos. By default only returns items whose own start state is Someday; pass `include_project_tasks=true` to also include tasks that live inside Someday projects (marked `inheritedSomeday: true`). Today/Anytime/Upcoming always exclude tasks that belong to a Someday project, regardless of this flag.
- `get_logbook(limit?, period?)` - Get completed todos
- `get_trash()` - Get trashed todos

### Date-Range Queries
- `get_due_in_days(days)` - Get todos due within specified days
- `get_activating_in_days(days)` - Get todos activating within days

### Search & Tags
- `search_todos(query)` - Basic search
- `search_advanced(...)` - Advanced search with filters
- `get_tags(include_items?)` - List tags
- `get_tag_usage(only_unused?, mode?)` - Per-tag open/total/area usage counts, sorted by usage, for cleanup. Caveats: tags sharing an identical title are merged into one row (uuid picks the last match), and area-only tags are counted via `area_count`/`total_count` but never affect `open_count`.
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

Run `mcp-server-things doctor` first. It's a read-only diagnostic that checks
Things 3 installation, whether it's running, macOS Automation permission,
database readability (Full Disk Access/TCC), `uv`/`uvx` availability, the
optional auth token, and environment/version info - printing a PASS/FAIL/WARN
table with a one-line fix hint per row (exits non-zero only if something
actually needs fixing). Use `mcp-server-things doctor --json` for
machine-readable output, or `python -m things_mcp doctor` if you're running
from source.

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

### Boot diagnostics

If the server appears to hang before an MCP client can connect (especially on
a cold start), the process writes timestamped boot-phase markers to stderr:

```
things-mcp boot: 2026-07-20T09:00:00.000+00:00 +0.001s process-start
things-mcp boot: 2026-07-20T09:00:00.010+00:00 +0.011s watchdog-armed (25.0s)
things-mcp boot: 2026-07-20T09:00:00.050+00:00 +0.051s things-import-start
things-mcp boot: 2026-07-20T09:00:00.120+00:00 +0.121s things-import-done
```

A one-shot startup watchdog also runs in the background: if boot doesn't
complete the MCP handshake within the deadline, it dumps every thread's stack
to stderr (`Timeout (0:00:25)!` followed by a traceback for each thread). On a
healthy, long-running server this fires exactly once, at the deadline, and is
harmless - it's stderr-only and does not affect the MCP stdio protocol (which
only uses stdout).

Relevant environment variables:

```bash
# Startup watchdog deadline in seconds. 0 (or any value <= 0) disables it.
THINGS_MCP_BOOT_WATCHDOG_SECS=25

# Timeout for lazily importing the third-party `things` package, in seconds.
# 0 (or any value <= 0) makes the import unbounded (blocking).
THINGS_MCP_THINGS_IMPORT_TIMEOUT_SECS=10
```

To diagnose a cold-start hang from a client's debug log: find the last
`things-mcp boot:` marker line - the phase named there is where boot stalled.
If a watchdog stack dump follows, its traceback shows exactly where each
thread was blocked at that moment.

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

---

Built for the Things 3 and MCP community.
