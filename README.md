# Things 3 MCP Server

[![PyPI version](https://badge.fury.io/py/things-applescript-mcp.svg)](https://pypi.org/project/things-applescript-mcp/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![macOS](https://img.shields.io/badge/macOS-12+-green.svg)](https://www.apple.com/macos/)

> **Turn AI conversations into real commitments.** Connect Claude and other AI assistants to Things 3 for natural language task management.

## Installation

### From PyPI (Recommended)

```bash
pip install things-applescript-mcp
```

### From Source

1. Clone the repository:
```bash
git clone https://github.com/yourusername/things-applescript-mcp.git
cd things-applescript-mcp
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

3. Install in development mode:
```bash
pip install -e .
```

### Claude Desktop Configuration

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "things": {
      "command": "/path/to/things-applescript-mcp/venv/bin/python",
      "args": ["-m", "things_mcp"],
      "env": {}
    }
  }
}
```

**Note:** When installing from source, use the full path to the Python executable in your virtual environment.

![Demo showing Claude creating tasks in Things 3](demo.gif)
*Creating tasks with natural language through Claude*

## 🚀 Features

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
- **Tag Management**: Full tag support and filtering
- **URL Schemes**: Native Things 3 URL scheme integration  
- **Health Monitoring**: Comprehensive system health checks
- **Caching**: Intelligent caching for improved performance
- **Error Handling**: Robust error handling with retries
- **Logging**: Structured logging for debugging and monitoring
- **Concurrency Support**: Multi-client safe operation with three-layer protection
- **Operation Queuing**: Serialized write operations to prevent conflicts
- **Shared Caching**: Cross-process result sharing for optimal performance

## 📋 Requirements

- **macOS**: This server requires macOS (tested on macOS 12+)
- **Things 3**: Things 3 must be installed and accessible
- **Python**: Python 3.8 or higher
- **Permissions**: AppleScript permissions for Things 3 access

## 🚀 Quick Start

Once installed, Claude (or other MCP clients) can automatically discover and use all available tools. No additional setup required!

## ⚙️ Configuration

### Environment Variables

```bash
# Optional configuration
export THINGS_MCP_TIMEOUT=30          # AppleScript timeout (seconds)
export THINGS_MCP_CACHE_TTL=300       # Cache TTL (seconds)
export THINGS_MCP_LOG_LEVEL=INFO      # Logging level
export THINGS_MCP_RETRY_COUNT=3       # Retry attempts
```

### Configuration File

Create a `config.yaml` file:

```yaml
server:
  timeout: 30
  cache_ttl: 300
  log_level: INFO
  retry_count: 3

things:
  app_name: "Things3"
  url_scheme: "things"
  
logging:
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "things_mcp.log"
```

## 🔧 Available MCP Tools

### Todo Management
- `get_todos(project_uuid?, include_items?)` - List todos
- `add_todo(title, ...)` - Create new todo
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

### Search & Tags
- `search_todos(query)` - Basic search
- `search_advanced(...)` - Advanced search with filters
- `get_tags(include_items?)` - List tags
- `get_tagged_items(tag)` - Get items with specific tag
- `get_recent(period)` - Get recently created items

### Navigation
- `show_item(id, query?, filter_tags?)` - Show item in Things 3
- `search_items(query)` - Search and show in Things 3

### System
- `health_check()` - Check server and Things 3 status
- `queue_status()` - Check operation queue status and statistics


## 🔧 Troubleshooting

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
# Increase timeout value
python -m things_mcp.main --timeout 60

# Or set environment variable
export THINGS_MCP_TIMEOUT=60
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

## 📊 Performance

- **Startup Time**: < 2 seconds
- **Response Time**: < 500ms for most operations (< 10ms with cache hits)
- **Cache Hit Rate**: ~85-95% for repeated queries
- **Memory Usage**: ~15MB baseline, ~50MB under high concurrent load
- **Concurrent Requests**: Up to 10+ simultaneous operations with three-layer protection
- **Throughput**: 8-12 ops/sec for reads, 1-2 ops/sec for writes (serialized)
- **Queue Processing**: < 50ms latency for operation enqueuing

## 🔒 Security

- No network access required (local AppleScript only)
- No data stored outside of Things 3
- Minimal system permissions needed
- Secure AppleScript execution with timeouts
- Input validation on all parameters

## 🤝 Contributing

We welcome contributions! Please see our [Developer Guide](docs/DEVELOPER_GUIDE.md) for details on:

- Setting up development environment
- Code style and standards
- Testing procedures
- Submitting pull requests

## 📚 Documentation

- [User Guide](docs/USER_GUIDE.md) - Detailed usage instructions
- [Developer Guide](docs/DEVELOPER_GUIDE.md) - Development and contribution guide
- [API Reference](docs/API_REFERENCE.md) - Complete MCP tool documentation
- [Concurrency Guide](docs/CONCURRENCY_GUIDE.md) - Multi-client concurrency and performance
- [Examples](examples/) - Usage examples and templates

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

- **Issues**: [GitHub Issues](https://github.com/ebowman/things-applescript-mcp/issues)
- **Discussions**: [GitHub Discussions](https://github.com/ebowman/things-applescript-mcp/discussions)
- **Email**: ebowman@boboco.ie

## 🎯 Roadmap

### Phase 1: Core Stability (Current)
- ✅ Complete MCP tool implementation
- ✅ Robust error handling and logging
- ✅ Comprehensive testing suite
- ✅ Documentation and examples

### Phase 2: Enhanced Features
- [x] Multi-client concurrency support with three-layer protection
- [x] Shared caching system for cross-process result sharing
- [x] Operation queue with priority and retry logic
- [ ] Real-time sync with Things 3 changes
- [ ] Batch operations for performance
- [ ] Advanced natural language processing
- [ ] Integration with calendar and email

### Phase 3: Advanced Integration
- [ ] Multi-user support
- [ ] API rate limiting
- [ ] Webhook support
- [ ] Analytics and reporting

---

**Built with ❤️ for the Things 3 and MCP community**