# Things 3 MCP Server

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![macOS](https://img.shields.io/badge/macOS-12+-green.svg)](https://www.apple.com/macos/)

A Model Context Protocol (MCP) server that connects Claude and other AI assistants to Things 3 for natural language task management.

## Why this server?

Writes go through **AppleScript**, not the Things URL scheme, which is what enables `delete_todo`, `move_record`/`bulk_move_records`, `remove_tags`, real IDs returned synchronously, and no Things auth token — the trade-off is a one-time macOS Automation permission prompt on first write. Operationally it also ships built-in `doctor` diagnostics, `config --write` client setup, context-optimized response modes for large databases, and ~800 unit tests.

[hald/things-mcp](https://github.com/hald/things-mcp) is a solid, lighter URL-scheme-based alternative — several of its ideas (Someday-project filtering, tag usage reporting, `.mcpb` packaging) are adopted here too. See [docs/COMPARISON.md](docs/COMPARISON.md) for the detailed matrix.

## Prerequisites

- macOS 12+
- Things 3 installed and opened at least once
- [uv](https://docs.astral.sh/uv/) (`brew install uv`)
- macOS will ask for Automation permission for Things 3 on the first write — that's expected (AppleScript is what enables delete/move operations other servers lack).

## Install

### Claude Desktop

**Option A: One-click `.mcpb`**

Download the latest `.mcpb` file from the [releases page](https://github.com/ebowman/mcp-server-things/releases) and double-click it to install into Claude Desktop.

The bundle launches the server via `uvx`, so [uv](https://docs.astral.sh/uv/) must be installed and on `PATH` (`brew install uv`). The generated config pins uv's managed Python (`--python-preference only-managed`) so a stray Intel/Rosetta Python on your PATH can't break the install; first launch may download a managed CPython.

**Option B: `config` CLI**

```bash
mcp-server-things config --client claude-desktop --write
```

Safely adds/updates the `things` entry in your Claude Desktop config (`--force` overwrites an existing, different entry instead of refusing).

**Option C: Manual JSON**

```json
{
  "mcpServers": {
    "things": {
      "command": "uvx",
      "args": ["--python-preference", "only-managed", "--python", "3.12", "mcp-server-things"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add-json things '{"command":"uvx","args":["--python-preference","only-managed","--python","3.12","mcp-server-things"]}'
claude mcp add-json things '{"command":"uvx","args":["--python-preference","only-managed","--python","3.12","mcp-server-things"]}' -s user
```

`mcp-server-things config --client claude-code` prints these exact commands.

### Any MCP client

```json
{
  "command": "uvx",
  "args": ["--python-preference", "only-managed", "--python", "3.12", "mcp-server-things"]
}
```

## Verify

Run `mcp-server-things doctor` (or `uvx mcp-server-things doctor`) to confirm Things 3, permissions, and the database are all reachable.
Then ask your client "What's in my Things inbox?".

> **`uvx mcp-server-things` fails with `Building cryptography==...` / maturin / Rust errors?**
> Your default Python is an x86_64 (Intel/Rosetta) build — `cryptography` no longer ships
> macOS x86_64 wheels. Fix: run with an arm64 interpreter, e.g. `uvx -p 3.12 mcp-server-things`
> (Homebrew or uv-managed Python), or `uv python install 3.12` first. `mcp-server-things doctor`
> warns about this.

<details>
<summary>Advanced: pip, virtualenv, from source, existing installs</summary>

Upgrading from an existing install? See [docs/UPGRADING.md](docs/UPGRADING.md).

### Option 1: From PyPI

1. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

2. Install the package:
```bash
pip install mcp-server-things
```

### Option 2: From Source (Development)

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

#### `config` CLI

`mcp-server-things config --client <claude-desktop|claude-code|generic> [--via uvx|current-python] [--write] [--force]`
prints the MCP client configuration for the requested client (or, for
`claude-desktop --write`, safely merges it into
`~/Library/Application Support/Claude/claude_desktop_config.json`, backing up
the previous file first and refusing to clobber an existing, different
`things` entry unless `--force` is also passed). Run
`mcp-server-things config --client claude-desktop --write` or
`mcp-server-things config --client claude-code` instead of hand-editing JSON
or memorizing the `claude mcp add-json` syntax.

**Shortcut for venv/pip installs:** `mcp-server-things config --client claude-desktop --via current-python` targets the currently-running interpreter (`sys.executable -m things_mcp`) instead of the default `uvx mcp-server-things`.

#### For PyPI Installation

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

#### For Source Installation

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

</details>

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

The server uses environment variables for configuration, settable via system environment variables or a `.env` file (auto-loaded from the current directory, or pointed to with `--env-file`). The env vars that matter most:

| Variable | Default | Description |
|----------|---------|-------------|
| `THINGS_MCP_LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `THINGS_MCP_AI_CAN_CREATE_TAGS` | `false` | Whether the AI can create new tags (`false` = existing tags only) |
| `THINGS_MCP_APPLESCRIPT_TIMEOUT` | `30.0` | AppleScript execution timeout in seconds (1-300) |
| `THINGS_MCP_TRANSPORT` | `stdio` | Transport to use: `stdio` or `http` |
| `THINGS_MCP_PORT` | `8000` | Port to bind to when `THINGS_MCP_TRANSPORT=http` |

See [`.env.example`](.env.example) for the full list of options, including validation limits, retry counts, the auth-token file, and `THINGS_MCP_HOST`.

### Things URL-scheme auth token

`add_checklist_items`, `prepend_checklist_items`, and `replace_checklist_items`
(and any other tool built on `things:///update`, e.g. moving a to-do under a
heading) require a Things URL-scheme auth token. Without one configured,
these tools return `success: false` with an actionable error instead of
silently doing nothing - Things itself rejects un-authenticated `update`
requests, but `open -g` still exits 0, so the failure has to be caught before
the URL is ever opened. `things:///add`-based tools (`add_todo`,
`add_project`, including todo creation with a checklist) do **not** need a
token.

To configure one:

1. In Things 3: Settings > General > Enable Things URLs > Manage.
2. Save the token to one of (checked in this order, first match wins):
   - `.things-auth` in the project root
   - `things-auth.txt` in the project root
   - `~/.things-auth` in your home directory
3. Restart the server - the token is loaded once at startup, so a token
   file added or edited after the server starts is not picked up until the
   next restart.

An empty or whitespace-only token file is treated the same as a missing one
(the loader falls through to the next candidate path).

### HTTP Transport

By default the server speaks MCP over stdio. It can optionally run an HTTP
transport instead, which is the reliable fix when a client's stdio subprocess
lacks Automation (TCC) access to Things 3: run the server from a Terminal that
has been granted access, then point the client at the HTTP URL instead of
launching it as a subprocess (see Troubleshooting for details).

| Variable | Default | Description |
|----------|---------|-------------|
| `THINGS_MCP_TRANSPORT` | `stdio` | Transport to use: `stdio` or `http` |
| `THINGS_MCP_HOST` | `127.0.0.1` | Host to bind to when `THINGS_MCP_TRANSPORT=http` |
| `THINGS_MCP_PORT` | `8000` | Port to bind to when `THINGS_MCP_TRANSPORT=http` |

```bash
THINGS_MCP_TRANSPORT=http THINGS_MCP_PORT=8000 uvx mcp-server-things
```

Then add it to Claude Code as an HTTP server:

```bash
claude mcp add --transport http things http://127.0.0.1:8000/mcp
```

`--transport`, `--host`, and `--port` CLI flags are also available and take
precedence over the environment variables above.

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

# Run with HTTP transport instead of stdio
python -m things_mcp --transport http --host 127.0.0.1 --port 8000
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

`get_today`, `get_upcoming`, `get_anytime`, `get_someday`, and `get_trash` never return headings, and exclude projects by default - pass `include_projects=true` to also include projects that belong to that list (e.g. a project due today), matching the Things app's list views. `get_inbox` has no `include_projects` flag since the Inbox can never contain projects.

- `get_inbox()` - Get Inbox todos
- `get_today(include_projects?)` - Get Today's todos
- `get_upcoming(days?, include_projects?)` - Get upcoming todos (with optional days filter)
- `get_anytime(include_projects?)` - Get Anytime todos
- `get_someday(include_project_tasks?, include_projects?)` - Get Someday todos. By default only returns items whose own start state is Someday; pass `include_project_tasks=true` to also include tasks that live inside Someday projects (marked `inheritedSomeday: true`). Today/Anytime/Upcoming always exclude tasks that belong to a Someday project, regardless of this flag.
- `get_logbook(limit?, period?)` - Get completed todos
- `get_trash(include_projects?)` - Get trashed todos

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

### Reads fail but writes work ("unable to open database file")

| Operation | Result |
|---|---|
| Read tools (`get_today`, `get_inbox`, `search_todos`, ...) | Fail instantly with `unable to open database file` |
| Write tools (`add_todo`, `update_todo`, ...) | Work normally |
| URL-scheme features needing the auth token | Also fail (the token is read from the same database) |

**Cause:** Under Claude Desktop, MCP servers are spawned via
`/Applications/Claude.app/Contents/Helpers/disclaimer`, which disclaims TCC
(privacy/permissions) responsibility for the process it launches. As a
result, the spawned server does **not** inherit Claude Desktop's Full Disk
Access grant, even though Claude.app itself has it. The Things 3 SQLite
database lives under the TCC-protected
`~/Library/Group Containers/JLMPQHK86H.com.culturedcode.ThingsMac/ThingsData-*/Things Database.thingsdatabase/main.sqlite`
(confirmed via `things.database.Database().filepath` - the same read path
this server uses for every read tool), so any process without Full Disk
Access gets `unable to open database file` immediately. Granting Full Disk
Access to Claude.app does **not** fix this, since the disclaimer helper is
what actually launches the server process.

**Fix ladder** (try in order):

1. **Recommended:** Run the server with HTTP transport from a Terminal,
   which already has disk access, instead of letting Claude Desktop spawn it
   directly:
   ```bash
   THINGS_MCP_TRANSPORT=http THINGS_MCP_PORT=8000 uvx mcp-server-things
   ```
   Then point Claude Code at it:
   ```bash
   claude mcp add --transport http things http://127.0.0.1:8000/mcp
   ```
   Stdio-only clients (including Claude Desktop) can bridge to the HTTP
   server with [`mcp-remote`](https://www.npmjs.com/package/mcp-remote):
   ```bash
   npx mcp-remote http://127.0.0.1:8000/mcp
   ```
2. Grant Full Disk Access directly to the actual launched binary (e.g. the
   `uvx` executable or the venv `python` in uv's cache) via System Settings ->
   Privacy & Security -> Full Disk Access. This works but is fragile - the
   grant can silently break when Homebrew/uv updates the binary, and the FDA
   picker sometimes greys out these paths, requiring drag-and-drop from
   Finder to add them.
3. Run `mcp-server-things doctor` to confirm the fix - the "Database
   readable" row reports PASS once Full Disk Access (or the HTTP transport
   workaround) is in place.

This is the same failure mode reported upstream in
[hald/things-mcp#62](https://github.com/hald/things-mcp/issues/62); we've
verified it applies here too since we read the Things database via the same
`things.py` library and code path.

### Checklist tools return "Things URL-scheme auth token not configured"

`add_checklist_items`, `prepend_checklist_items`, and `replace_checklist_items`
need a Things URL-scheme auth token (see "Things URL-scheme auth token" under
Configuration above). `mcp-server-things doctor` reports this as a WARN on
the "Auth token file" row, naming the affected tools, until a token file is
in place.

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
