# Things 3 MCP Server - User Guide

A comprehensive guide to using the Things 3 MCP server for task management integration.

## 📖 Table of Contents

1. [Installation & Setup](#installation--setup)
2. [Configuration](#configuration)
3. [Available MCP Tools](#available-mcp-tools)
4. [Usage Examples](#usage-examples)
5. [Integration Patterns](#integration-patterns)
6. [Best Practices](#best-practices)
7. [Troubleshooting](#troubleshooting)

## 🚀 Installation & Setup

### Prerequisites

Before installing the Things 3 MCP server, ensure you have:

- **macOS**: Version 10.15 (Catalina) or later
- **Things 3**: Installed from Mac App Store or Things website
- **Python**: Version 3.8 or higher
- **AppleScript Access**: Terminal/IDE must have permission to control Things 3

### Step 1: Grant Permissions

1. Open **System Preferences** > **Security & Privacy** > **Privacy**
2. Select **Automation** from the left sidebar
3. Find your terminal application (Terminal, iTerm2, VS Code, etc.)
4. Enable access to **Things3**

### Step 2: Install the Server

#### Option A: From Source (Recommended)

```bash
# Clone and install
git clone https://github.com/your-repo/things-mcp-server.git
cd things-mcp-server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

#### Option B: Direct Installation

```bash
pip install things-mcp-server
```

### Step 3: Verify Installation

```bash
# Check if Things 3 MCP server is working
python -m things_mcp.main --health-check

# Expected output:
# ✓ AppleScript available
# ✓ Things 3 is running and accessible
# ✓ AppleScript execution working
# ✓ Health check completed successfully
```

### Step 4: Claude Desktop Integration

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "things": {
      "command": "python",
      "args": ["-m", "things_mcp.main"],
      "cwd": "/path/to/things-mcp-server",
      "env": {
        "THINGS_MCP_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

## ⚙️ Configuration

### Environment Variables

Configure the server behavior using environment variables:

```bash
# Core settings
export THINGS_MCP_TIMEOUT=30          # AppleScript timeout (seconds)
export THINGS_MCP_CACHE_TTL=300       # Cache TTL (seconds)  
export THINGS_MCP_LOG_LEVEL=INFO      # Logging level
export THINGS_MCP_RETRY_COUNT=3       # Retry attempts

# Advanced settings
export THINGS_MCP_APP_NAME="Things3"  # Things app name
export THINGS_MCP_URL_SCHEME="things" # URL scheme prefix
export THINGS_MCP_MAX_CONCURRENT=5    # Max concurrent operations
```

### Configuration File

Create `config/settings.yaml`:

```yaml
server:
  timeout: 30
  cache_ttl: 300
  log_level: INFO
  retry_count: 3
  max_concurrent: 5

things:
  app_name: "Things3"
  url_scheme: "things"
  verify_running: true

caching:
  enabled: true
  ttl: 300
  max_size: 1000

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/things_mcp.log"
  rotate: true
  max_size: "10MB"
  backup_count: 5
```

## 🔧 Available MCP Tools

### Todo Management Tools

#### `get_todos`
Get todos from Things, optionally filtered by project.

**Parameters:**
- `project_uuid` (optional): UUID of specific project
- `include_items` (default: true): Include checklist items

**Returns:** List of todo objects

```python
# Get all todos
todos = await client.call_tool("get_todos")

# Get todos from specific project
project_todos = await client.call_tool(
    "get_todos", 
    project_uuid="ABC123-DEF456"
)
```

#### `add_todo`
Create a new todo in Things.

**Parameters:**
- `title` (required): Todo title
- `notes` (optional): Todo notes
- `tags` (optional): List of tag names
- `when` (optional): Schedule (today, tomorrow, evening, anytime, someday, YYYY-MM-DD)
- `deadline` (optional): Deadline date (YYYY-MM-DD)
- `list_id` (optional): Project/area ID
- `list_title` (optional): Project/area title
- `heading` (optional): Heading to add under
- `checklist_items` (optional): List of checklist items

**Returns:** Todo creation result

```python
# Simple todo
result = await client.call_tool(
    "add_todo",
    title="Buy milk"
)

# Complex todo
result = await client.call_tool(
    "add_todo",
    title="Complete project proposal",
    notes="Include budget analysis and timeline",
    tags=["work", "urgent"],
    when="tomorrow",
    deadline="2024-01-15",
    list_title="Work Projects",
    checklist_items=[
        "Research requirements",
        "Draft proposal",
        "Review with team"
    ]
)
```

#### `update_todo`
Update an existing todo.

**Parameters:**
- `id` (required): Todo ID
- `title` (optional): New title
- `notes` (optional): New notes
- `tags` (optional): New tags
- `when` (optional): New schedule
- `deadline` (optional): New deadline
- `completed` (optional): Mark as completed
- `canceled` (optional): Mark as canceled

```python
# Update todo title and mark completed
result = await client.call_tool(
    "update_todo",
    id="todo-123",
    title="Updated title",
    completed=True
)
```

#### `get_todo_by_id`
Get a specific todo by ID.

```python
todo = await client.call_tool("get_todo_by_id", todo_id="todo-123")
```

#### `delete_todo`
Delete a todo from Things.

```python
result = await client.call_tool("delete_todo", todo_id="todo-123")
```

### Project Management Tools

#### `get_projects`
Get all projects from Things.

**Parameters:**
- `include_items` (default: false): Include tasks within projects

```python
# Get all projects
projects = await client.call_tool("get_projects")

# Get projects with their tasks
projects_with_tasks = await client.call_tool(
    "get_projects",
    include_items=True
)
```

#### `add_project`
Create a new project.

**Parameters:**
- `title` (required): Project title
- `notes` (optional): Project notes
- `tags` (optional): List of tags
- `when` (optional): Schedule
- `deadline` (optional): Deadline
- `area_id` (optional): Area ID
- `area_title` (optional): Area title
- `todos` (optional): Initial todos

```python
project = await client.call_tool(
    "add_project",
    title="Website Redesign",
    notes="Complete website overhaul",
    area_title="Marketing",
    deadline="2024-03-01",
    todos=[
        "Research competitors",
        "Create wireframes",
        "Design mockups"
    ]
)
```

#### `update_project`
Update an existing project (same parameters as `update_todo`).

### Area Management Tools

#### `get_areas`
Get all areas from Things.

**Parameters:**
- `include_items` (default: false): Include projects and tasks

```python
areas = await client.call_tool("get_areas", include_items=True)
```

### List Access Tools

#### Built-in List Tools
Access Things 3's built-in smart lists:

```python
# Get items from different lists
inbox_items = await client.call_tool("get_inbox")
today_items = await client.call_tool("get_today")
upcoming_items = await client.call_tool("get_upcoming")
anytime_items = await client.call_tool("get_anytime")
someday_items = await client.call_tool("get_someday")
trash_items = await client.call_tool("get_trash")

# Get completed items from logbook
logbook_items = await client.call_tool(
    "get_logbook",
    limit=20,        # Max 20 items
    period="30d"     # Last 30 days
)
```

### Search & Tag Tools

#### `search_todos`
Basic text search in todos.

```python
results = await client.call_tool(
    "search_todos",
    query="meeting"
)
```

#### `search_advanced`
Advanced search with multiple filters.

**Parameters:**
- `status` (optional): incomplete, completed, canceled
- `type` (optional): to-do, project, heading
- `tag` (optional): Tag name
- `area` (optional): Area UUID
- `start_date` (optional): Start date (YYYY-MM-DD)
- `deadline` (optional): Deadline date (YYYY-MM-DD)

```python
results = await client.call_tool(
    "search_advanced",
    status="incomplete",
    tag="urgent",
    start_date="2024-01-01",
    deadline="2024-01-31"
)
```

#### `get_tags`
Get all tags.

```python
tags = await client.call_tool("get_tags", include_items=False)
```

#### `get_tagged_items`
Get items with specific tag.

```python
urgent_items = await client.call_tool(
    "get_tagged_items",
    tag="urgent"
)
```

#### `get_recent`
Get recently created items.

```python
recent = await client.call_tool(
    "get_recent",
    period="7d"  # 3d, 1w, 2m, 1y
)
```

### Navigation Tools

#### `show_item`
Show item in Things 3 UI.

```python
# Show specific item
result = await client.call_tool(
    "show_item",
    id="todo-123"
)

# Show list with filters
result = await client.call_tool(
    "show_item",
    id="today",
    query="meeting",
    filter_tags=["work"]
)
```

#### `search_items`
Search and show results in Things 3.

```python
result = await client.call_tool(
    "search_items",
    query="project presentation"
)
```

### System Tools

#### `health_check`
Check server and Things 3 connectivity.

```python
health = await client.call_tool("health_check")
# Returns: server_status, things_running, applescript_available, timestamp
```

## 💡 Usage Examples

### Daily Task Management

```python
async def daily_task_workflow():
    # Check what's due today
    today = await client.call_tool("get_today")
    print(f"You have {len(today)} tasks due today")
    
    # Add new task for tomorrow
    await client.call_tool(
        "add_todo",
        title="Review daily reports",
        when="tomorrow",
        tags=["routine", "work"]
    )
    
    # Check inbox for new items
    inbox = await client.call_tool("get_inbox")
    if inbox:
        print(f"You have {len(inbox)} items in your inbox")
```

### Project Planning

```python
async def create_project_workflow():
    # Create a new project
    project = await client.call_tool(
        "add_project",
        title="Q1 Marketing Campaign",
        notes="Comprehensive marketing push for Q1 goals",
        area_title="Marketing",
        deadline="2024-03-31",
        tags=["q1", "marketing", "campaign"],
        todos=[
            "Define target audience",
            "Create content calendar",
            "Design marketing materials",
            "Launch campaign",
            "Analyze results"
        ]
    )
    
    # Add additional tasks to the project
    if project.get("success"):
        project_id = project["project"]["id"]
        
        await client.call_tool(
            "add_todo",
            title="Budget approval meeting",
            list_id=project_id,
            when="next week",
            tags=["meeting", "budget"]
        )
```

### Search and Organization

```python
async def organize_tasks():
    # Find all overdue tasks
    overdue = await client.call_tool(
        "search_advanced",
        status="incomplete",
        deadline="2024-01-01"  # Tasks with deadlines before today
    )
    
    # Find all urgent items
    urgent = await client.call_tool(
        "get_tagged_items",
        tag="urgent"
    )
    
    # Get recent completed items for review
    completed = await client.call_tool(
        "get_logbook",
        period="7d",
        limit=10
    )
    
    print(f"Overdue: {len(overdue)}, Urgent: {len(urgent)}, Completed this week: {len(completed)}")
```

### Batch Operations

```python
async def batch_todo_creation():
    # Create multiple related todos
    meeting_todos = [
        "Prepare agenda",
        "Book conference room",
        "Send invites",
        "Prepare presentation"
    ]
    
    for todo_title in meeting_todos:
        await client.call_tool(
            "add_todo",
            title=todo_title,
            list_title="Team Meetings",
            tags=["meeting", "preparation"],
            when="this week"
        )
```

## 🔗 Integration Patterns

### Claude Desktop Integration

With the MCP server running in Claude Desktop, you can:

```
# Natural language requests
"Add a todo to review the quarterly budget due next Friday"

"Show me all urgent tasks that are overdue"

"Create a project for the website redesign with initial planning tasks"

"What tasks do I have scheduled for today?"
```

### Custom MCP Client

```python
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_things_client():
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "things_mcp.main"],
        env={"THINGS_MCP_LOG_LEVEL": "DEBUG"}
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize session
            await session.initialize()
            
            # Use the tools
            result = await session.call_tool(
                "add_todo",
                title="Test todo from MCP client"
            )
            print(f"Result: {result}")

asyncio.run(run_things_client())
```

### Web API Integration

```python
from fastapi import FastAPI
from things_mcp import ThingsMCPServer

app = FastAPI()
things_server = ThingsMCPServer()

@app.post("/api/todos")
async def create_todo(todo_data: dict):
    return await things_server.tools.add_todo(**todo_data)

@app.get("/api/todos/today")
async def get_today_todos():
    return await things_server.tools.get_today()
```

## 📋 Best Practices

### Performance Optimization

1. **Use Caching**: Enable caching for frequently accessed data
```python
# Cache is automatically used for repeated queries within TTL
todos = await client.call_tool("get_todos")  # Database query
todos = await client.call_tool("get_todos")  # Cache hit
```

2. **Batch Operations**: Group related operations together
```python
# Good: Single project with multiple todos
await client.call_tool("add_project", title="Project", todos=["task1", "task2"])

# Less efficient: Multiple separate calls
await client.call_tool("add_project", title="Project")
await client.call_tool("add_todo", title="task1", list_title="Project")
await client.call_tool("add_todo", title="task2", list_title="Project")
```

3. **Specific Queries**: Use specific filters to reduce data transfer
```python
# Good: Specific project query
todos = await client.call_tool("get_todos", project_uuid="ABC123")

# Less efficient: Get all then filter
all_todos = await client.call_tool("get_todos")
project_todos = [t for t in all_todos if t.get("project_uuid") == "ABC123"]
```

### Error Handling

```python
async def robust_todo_creation():
    try:
        result = await client.call_tool(
            "add_todo",
            title="Important task"
        )
        
        if not result.get("success"):
            print(f"Failed to create todo: {result.get('error')}")
            
    except Exception as e:
        print(f"Error calling MCP tool: {e}")
        
        # Fallback: Check if Things 3 is running
        health = await client.call_tool("health_check")
        if not health.get("things_running"):
            print("Things 3 is not running. Please start the application.")
```

### Data Validation

```python
from datetime import datetime, date

def validate_date(date_str: str) -> bool:
    """Validate date string format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False

async def create_validated_todo():
    deadline = "2024-01-15"
    
    if not validate_date(deadline):
        print("Invalid date format. Use YYYY-MM-DD.")
        return
        
    result = await client.call_tool(
        "add_todo",
        title="Validated todo",
        deadline=deadline
    )
```

### Tag Management

```python
async def consistent_tagging():
    # Get existing tags to maintain consistency
    existing_tags = await client.call_tool("get_tags")
    tag_names = [tag["name"] for tag in existing_tags]
    
    # Use consistent tag names
    new_tags = ["work", "urgent"]  # Instead of "Work", "URGENT", etc.
    
    # Validate tags exist
    for tag in new_tags:
        if tag not in tag_names:
            print(f"Warning: Tag '{tag}' doesn't exist yet")
    
    await client.call_tool(
        "add_todo",
        title="Consistently tagged todo",
        tags=new_tags
    )
```

## 🔧 Troubleshooting

### Common Issues

#### 1. Permission Denied Errors

**Problem**: `AppleScript execution failed: Application not authorized`

**Solution**:
1. Open **System Preferences** > **Security & Privacy** > **Privacy**
2. Select **Automation**
3. Find your application (Terminal, VS Code, etc.)
4. Enable access to **Things3**
5. Restart your terminal/application

#### 2. Things 3 Not Found

**Problem**: `Things 3 application not found`

**Solutions**:
```bash
# Check if Things 3 is installed
ls /Applications/ | grep -i things

# Verify application name
python -c "import subprocess; print(subprocess.run(['osascript', '-e', 'tell application \"System Events\" to get name of every application process'], capture_output=True, text=True).stdout)"
```

#### 3. Timeout Errors

**Problem**: `AppleScript execution timed out`

**Solutions**:
```bash
# Increase timeout
export THINGS_MCP_TIMEOUT=60
python -m things_mcp.main

# Or use command line option
python -m things_mcp.main --timeout 60
```

#### 4. Cache Issues

**Problem**: Stale data returned from cache

**Solutions**:
```bash
# Disable cache temporarily
export THINGS_MCP_CACHE_TTL=0

# Or clear cache directory
rm -rf ~/.things_mcp_cache/
```

#### 5. Connection Issues

**Problem**: MCP client cannot connect to server

**Solutions**:
```bash
# Test server directly
python -m things_mcp.main --health-check

# Check if port is in use
lsof -i :3000

# Try different port
python -m things_mcp.main --port 3001
```

### Debug Mode

Enable comprehensive debugging:

```bash
# Enable debug logging
export THINGS_MCP_LOG_LEVEL=DEBUG
python -m things_mcp.main --debug

# Monitor logs in real-time
tail -f things_mcp.log
```

### Health Diagnostics

Run comprehensive health checks:

```bash
# Full system check
python -m things_mcp.main --health-check

# Test AppleScript specifically
python -m things_mcp.main --test-applescript

# Verify Things 3 connectivity
python -c "
import subprocess
result = subprocess.run(['osascript', '-e', 'tell application \"Things3\" to get version'], capture_output=True, text=True)
print(f'Things 3 version: {result.stdout.strip()}')
"
```

### Performance Monitoring

```python
import time
import asyncio

async def monitor_performance():
    start_time = time.time()
    
    # Test operation
    result = await client.call_tool("get_today")
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"Operation took {duration:.2f} seconds")
    print(f"Returned {len(result)} items")
    
    # Monitor cache hit rate
    health = await client.call_tool("health_check")
    print(f"Cache stats: {health.get('cache_stats', {})}")
```

## 📞 Support

If you encounter issues not covered in this guide:

1. **Check Logs**: Review `things_mcp.log` for detailed error messages
2. **Health Check**: Run `python -m things_mcp.main --health-check`
3. **GitHub Issues**: Report bugs at [GitHub Issues](https://github.com/your-repo/things-mcp-server/issues)
4. **Community**: Join discussions at [GitHub Discussions](https://github.com/your-repo/things-mcp-server/discussions)

---

This user guide provides comprehensive information for using the Things 3 MCP server effectively. For development and contribution information, see the [Developer Guide](DEVELOPER_GUIDE.md).