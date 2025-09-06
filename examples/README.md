# Things 3 MCP Server - Examples

This directory contains practical examples, configuration templates, and integration scripts for the Things 3 MCP server.

## Directory Structure

```
examples/
├── README.md                    # This file
├── configurations/             # Configuration file examples
│   ├── claude_desktop_config.json
│   ├── basic_config.yaml
│   ├── advanced_config.yaml
│   └── production_config.yaml
├── scripts/                    # Utility scripts
│   ├── daily_review.py
│   ├── bulk_import.py
│   ├── project_template.py
│   └── backup_todos.py
└── integrations/              # Integration examples
    ├── web_api_server.py
    ├── slack_bot.py
    ├── calendar_sync.py
    └── mcp_client_example.py
```

## Quick Start Examples

### Basic Todo Creation

```python
# Simple todo creation
import asyncio
from mcp import ClientSession

async def create_simple_todo():
    async with ClientSession() as session:
        result = await session.call_tool(
            "add_todo",
            title="Buy groceries"
        )
        print(f"Created todo: {result}")

# Run the example
asyncio.run(create_simple_todo())
```

### Daily Task Review

```python
# Daily task review workflow
async def daily_review():
    async with ClientSession() as session:
        # Check today's tasks
        today = await session.call_tool("get_today")
        print(f"Today's tasks: {len(today)}")
        
        # Check overdue items
        overdue = await session.call_tool(
            "search_advanced",
            status="incomplete",
            deadline="yesterday"  # Items with past deadlines
        )
        
        # Check inbox items
        inbox = await session.call_tool("get_inbox")
        
        print(f"Overdue: {len(overdue)}, Inbox: {len(inbox)}")

asyncio.run(daily_review())
```

### Project Creation with Tasks

```python
# Create a project with initial tasks
async def create_project_with_tasks():
    async with ClientSession() as session:
        project = await session.call_tool(
            "add_project",
            title="Website Redesign",
            notes="Complete overhaul of company website",
            area_title="Marketing",
            deadline="next-month",
            todos=[
                "Research competitor websites",
                "Create wireframes",
                "Design mockups",
                "Develop prototype",
                "User testing",
                "Launch new site"
            ]
        )
        print(f"Created project: {project}")

asyncio.run(create_project_with_tasks())
```

## Configuration Examples

### Claude Desktop Basic Configuration

```json
{
  "mcpServers": {
    "things": {
      "command": "python",
      "args": ["-m", "things_mcp.main"],
      "cwd": "/path/to/things-mcp-server"
    }
  }
}
```

### Claude Desktop Advanced Configuration

```json
{
  "mcpServers": {
    "things": {
      "command": "python",
      "args": [
        "-m", "things_mcp.main", 
        "--timeout", "60",
        "--debug"
      ],
      "cwd": "/path/to/things-mcp-server",
      "env": {
        "THINGS_MCP_LOG_LEVEL": "DEBUG",
        "THINGS_MCP_CACHE_TTL": "600",
        "THINGS_MCP_RETRY_COUNT": "3"
      }
    }
  }
}
```

### Server Configuration File

```yaml
# config/advanced_config.yaml
server:
  timeout: 60
  cache_ttl: 600
  log_level: INFO
  retry_count: 3
  max_concurrent: 10

things:
  app_name: "Things3"
  url_scheme: "things"
  verify_running: true

caching:
  enabled: true
  ttl: 600
  max_size: 1000
  persist_to_disk: true
  disk_cache_path: "./cache"

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: "logs/things_mcp.log"
  rotate: true
  max_size: "10MB"
  backup_count: 5

performance:
  connection_pool_size: 5
  applescript_timeout: 30
  url_scheme_timeout: 10
```

## Utility Scripts

### Daily Review Script

```python
#!/usr/bin/env python3
"""Daily review script for Things 3 todos."""

import asyncio
import sys
from datetime import datetime, timedelta
from mcp import ClientSession

async def daily_review():
    """Perform daily todo review."""
    async with ClientSession() as session:
        print("Daily Things Review")
        print("=" * 40)
        
        # Today's tasks
        today = await session.call_tool("get_today")
        print(f"Today's tasks: {len(today)}")
        
        if today:
            for todo in today[:5]:  # Show first 5
                print(f"  • {todo['title']}")
            if len(today) > 5:
                print(f"  ... and {len(today) - 5} more")
        
        # Overdue tasks
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        overdue = await session.call_tool(
            "search_advanced",
            status="incomplete",
            deadline=yesterday
        )
        
        if overdue:
            print(f"Overdue tasks: {len(overdue)}")
            for todo in overdue[:3]:
                print(f"  • {todo['title']} (due: {todo.get('deadline', 'unknown')})")
        
        # Inbox items
        inbox = await session.call_tool("get_inbox")
        if inbox:
            print(f"Inbox items to process: {len(inbox)}")
        
        # Recent completions
        completed = await session.call_tool("get_logbook", period="1d", limit=5)
        if completed:
            print(f"Completed yesterday: {len(completed)}")
            for todo in completed[:3]:
                print(f"  • {todo['title']}")
        
        print("\nHave a productive day!")

if __name__ == "__main__":
    asyncio.run(daily_review())
```

### Bulk Import Script

```python
#!/usr/bin/env python3
"""Bulk import todos from CSV file."""

import asyncio
import csv
import sys
from mcp import ClientSession

async def bulk_import_from_csv(csv_file: str):
    """Import todos from CSV file."""
    async with ClientSession() as session:
        imported = 0
        failed = 0
        
        with open(csv_file, 'r', newline='', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                try:
                    # Map CSV columns to todo parameters
                    todo_params = {
                        "title": row.get("title", "").strip(),
                        "notes": row.get("notes", "").strip(),
                        "tags": [tag.strip() for tag in row.get("tags", "").split(",") if tag.strip()],
                        "when": row.get("when", "").strip() or None,
                        "deadline": row.get("deadline", "").strip() or None,
                        "list_title": row.get("project", "").strip() or None
                    }
                    
                    # Remove empty values
                    todo_params = {k: v for k, v in todo_params.items() if v}
                    
                    if not todo_params.get("title"):
                        print(f"Skipping row with no title: {row}")
                        continue
                    
                    result = await session.call_tool("add_todo", **todo_params)
                    
                    if result.get("success"):
                        imported += 1
                        print(f"Imported: {todo_params['title']}")
                    else:
                        failed += 1
                        print(f"Failed: {todo_params['title']} - {result.get('error')}")
                
                except Exception as e:
                    failed += 1
                    print(f"Error processing row {reader.line_num}: {e}")
        
        print(f"\nImport Summary:")
        print(f"  Imported: {imported}")
        print(f"  Failed: {failed}")
        print(f"  Total: {imported + failed}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python bulk_import.py <csv_file>")
        print("\nCSV format: title,notes,tags,when,deadline,project")
        sys.exit(1)
    
    asyncio.run(bulk_import_from_csv(sys.argv[1]))
```

### Project Template Script

```python
#!/usr/bin/env python3
"""Create project from template."""

import asyncio
import json
import sys
from mcp import ClientSession

# Project templates
TEMPLATES = {
    "website": {
        "title": "Website Project",
        "tasks": [
            "Define requirements",
            "Research and planning", 
            "Design wireframes",
            "Create mockups",
            "Develop frontend",
            "Develop backend",
            "Testing and QA",
            "Deploy to production",
            "Post-launch review"
        ],
        "tags": ["web", "development"]
    },
    "marketing": {
        "title": "Marketing Campaign",
        "tasks": [
            "Define target audience",
            "Set campaign goals",
            "Create content calendar",
            "Design marketing materials",
            "Set up tracking",
            "Launch campaign",
            "Monitor performance",
            "Analyze results",
            "Optimize and iterate"
        ],
        "tags": ["marketing", "campaign"]
    },
    "event": {
        "title": "Event Planning",
        "tasks": [
            "Define event scope",
            "Set budget and timeline",
            "Book venue",
            "Plan logistics",
            "Create promotional materials",
            "Manage registrations",
            "Coordinate day-of activities",
            "Follow up with attendees",
            "Conduct post-event review"
        ],
        "tags": ["event", "planning"]
    }
}

async def create_project_from_template(template_name: str, project_title: str = None):
    """Create project from template."""
    if template_name not in TEMPLATES:
        print(f"Unknown template: {template_name}")
        print(f"Available templates: {', '.join(TEMPLATES.keys())}")
        return
    
    template = TEMPLATES[template_name]
    title = project_title or template["title"]
    
    async with ClientSession() as session:
        print(f"Creating project: {title}")
        
        result = await session.call_tool(
            "add_project",
            title=title,
            notes=f"Created from {template_name} template",
            tags=template["tags"],
            todos=template["tasks"]
        )
        
        if result.get("success"):
            print(f"Project created successfully!")
            print(f"   Title: {title}")
            print(f"   Tasks: {len(template['tasks'])}")
            print(f"   Tags: {', '.join(template['tags'])}")
        else:
            print(f"Failed to create project: {result.get('error')}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python project_template.py <template_name> [project_title]")
        print(f"\nAvailable templates:")
        for name, template in TEMPLATES.items():
            print(f"  {name}: {template['title']} ({len(template['tasks'])} tasks)")
        sys.exit(1)
    
    template_name = sys.argv[1]
    project_title = sys.argv[2] if len(sys.argv) > 2 else None
    
    asyncio.run(create_project_from_template(template_name, project_title))
```

## Integration Examples

### Web API Server

```python
#!/usr/bin/env python3
"""Web API server wrapping Things MCP server."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import asyncio
from mcp import ClientSession

app = FastAPI(title="Things 3 Web API", version="1.0.0")

# Request/Response models
class TodoRequest(BaseModel):
    title: str
    notes: Optional[str] = None
    tags: Optional[List[str]] = None
    when: Optional[str] = None
    deadline: Optional[str] = None
    list_title: Optional[str] = None

class TodoResponse(BaseModel):
    id: str
    title: str
    notes: Optional[str]
    status: str
    tags: List[str]

# MCP client session
mcp_session = None

@app.on_event("startup")
async def startup():
    global mcp_session
    mcp_session = ClientSession()
    await mcp_session.__aenter__()

@app.on_event("shutdown") 
async def shutdown():
    global mcp_session
    if mcp_session:
        await mcp_session.__aexit__(None, None, None)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        result = await mcp_session.call_tool("health_check")
        return {"status": "healthy", "things_running": result.get("things_running")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/todos", response_model=List[TodoResponse])
async def get_todos(project_uuid: Optional[str] = None):
    """Get all todos."""
    try:
        todos = await mcp_session.call_tool("get_todos", project_uuid=project_uuid)
        return [TodoResponse(**todo) for todo in todos]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/todos", response_model=dict)
async def create_todo(todo: TodoRequest):
    """Create a new todo."""
    try:
        result = await mcp_session.call_tool("add_todo", **todo.dict(exclude_unset=True))
        if result.get("success"):
            return result
        else:
            raise HTTPException(status_code=400, detail=result.get("error"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/todos/today", response_model=List[TodoResponse])
async def get_today_todos():
    """Get today's todos."""
    try:
        todos = await mcp_session.call_tool("get_today")
        return [TodoResponse(**todo) for todo in todos]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### MCP Client Example

```python
#!/usr/bin/env python3
"""Complete MCP client example."""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def run_things_client():
    """Run Things MCP client with various operations."""
    
    # Server parameters
    server_params = StdioServerParameters(
        command="python",
        args=["-m", "things_mcp.main"],
        env={"THINGS_MCP_LOG_LEVEL": "INFO"}
    )
    
    # Connect to server
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize session
            await session.initialize()
            
            print("Connected to Things MCP Server")
            
            # Health check
            health = await session.call_tool("health_check")
            print(f"Health: {health}")
            
            # Create a todo
            todo_result = await session.call_tool(
                "add_todo",
                title="MCP Client Test Todo",
                notes="Created from MCP client example",
                tags=["test", "mcp"],
                when="today"
            )
            print(f"Created todo: {todo_result}")
            
            # Get today's todos
            today_todos = await session.call_tool("get_today")
            print(f"Today's todos: {len(today_todos)}")
            
            # Search for our todo
            search_results = await session.call_tool(
                "search_todos",
                query="MCP Client Test"
            )
            print(f"Search results: {len(search_results)}")
            
            # Create a project
            project_result = await session.call_tool(
                "add_project",
                title="MCP Integration Project",
                notes="Testing MCP integration capabilities",
                tags=["mcp", "integration"],
                todos=[
                    "Set up MCP server",
                    "Test basic operations", 
                    "Create examples",
                    "Document usage"
                ]
            )
            print(f"Created project: {project_result}")
            
            # Get all projects
            projects = await session.call_tool("get_projects", include_items=True)
            print(f"Total projects: {len(projects)}")
            
            print("MCP client example completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_things_client())
```

## Sample Data Files

### CSV Import Template

```csv
title,notes,tags,when,deadline,project
"Review quarterly reports","Check Q4 financial data","work,finance","today","next-friday","Finance Review"
"Team standup meeting","Daily sync with development team","work,meeting","today","","Development"
"Buy groceries","Milk, bread, eggs","personal,shopping","","","Personal"
"Prepare presentation","Include latest metrics and projections","work,presentation","tomorrow","next-week","Marketing Campaign"
"Schedule dentist appointment","6-month checkup","personal,health","someday","","Personal"
```

### Project Templates JSON

```json
{
  "templates": {
    "mobile_app": {
      "title": "Mobile App Development",
      "description": "Complete mobile application development project",
      "phases": [
        {
          "name": "Planning",
          "tasks": [
            "Define app requirements",
            "Create user personas",
            "Design user flows",
            "Plan technical architecture"
          ]
        },
        {
          "name": "Design",
          "tasks": [
            "Create wireframes",
            "Design UI mockups",
            "Create design system",
            "Get design approval"
          ]
        },
        {
          "name": "Development", 
          "tasks": [
            "Set up development environment",
            "Implement core features",
            "Integrate APIs",
            "Add authentication"
          ]
        },
        {
          "name": "Testing & Launch",
          "tasks": [
            "Unit testing",
            "Integration testing",
            "User acceptance testing",
            "App store submission",
            "Launch marketing"
          ]
        }
      ],
      "tags": ["mobile", "development", "app"],
      "estimated_duration": "12 weeks"
    }
  }
}
```

## Usage Tips

### Best Practices

1. **Use Specific Tags**: Create consistent tagging systems
2. **Batch Operations**: Group related operations together
3. **Error Handling**: Always check for success in responses
4. **Caching**: Leverage built-in caching for repeated queries
5. **Health Checks**: Regularly verify system health

### Performance Optimization

```python
# Good: Batch related operations
async def efficient_project_setup():
    # Create project with initial todos in one call
    project = await session.call_tool(
        "add_project",
        title="Efficient Project",
        todos=["Task 1", "Task 2", "Task 3"]
    )
    
# Avoid: Multiple separate calls
async def inefficient_project_setup():
    project = await session.call_tool("add_project", title="Project")
    await session.call_tool("add_todo", title="Task 1", list_title="Project")
    await session.call_tool("add_todo", title="Task 2", list_title="Project")
    await session.call_tool("add_todo", title="Task 3", list_title="Project")
```

### Error Recovery

```python
async def robust_operation():
    try:
        result = await session.call_tool("add_todo", title="Important Task")
        if not result.get("success"):
            # Handle specific errors
            error = result.get("error", "")
            if "permission" in error.lower():
                print("Please grant AppleScript permissions")
            elif "not running" in error.lower():
                print("Please start Things 3")
            else:
                print(f"Unexpected error: {error}")
    except Exception as e:
        print(f"Connection error: {e}")
```

---

These examples provide practical starting points for integrating the Things 3 MCP server into your workflows. Modify them according to your specific needs and use cases.