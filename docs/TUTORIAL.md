# Things 3 MCP Server - Complete Tutorial

## 🚀 Quick Start Guide

The Things 3 MCP Server enables Claude (and other AI assistants) to interact with your Things 3 application directly. This means you can manage your todos, projects, and entire productivity system through natural language conversations!

## Table of Contents
- [Installation](#installation)
- [Basic Usage](#basic-usage)
- [Cool Things You Can Do](#cool-things-you-can-do)
- [Advanced Workflows](#advanced-workflows)
- [API Reference](#api-reference)
- [Troubleshooting](#troubleshooting)

## Installation

### Prerequisites
- macOS with Things 3 installed
- Python 3.8+
- Claude Desktop app (or any MCP-compatible client)

### Setup Steps

1. **Clone the repository:**
```bash
git clone https://github.com/yourusername/things-applescript-mcp.git
cd things-applescript-mcp
```

2. **Install dependencies:**
```bash
pip install -e .
```

3. **Configure Claude Desktop:**
Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "things": {
      "command": "python",
      "args": [
        "/path/to/things-applescript-mcp/src/things_mcp/simple_server.py"
      ],
      "env": {}
    }
  }
}
```

4. **Set up Things authentication (optional):**
Create a file `~/.things-auth` with your Things URL scheme token:
```
THINGS_AUTH_TOKEN=your_token_here
```

5. **Restart Claude Desktop** to load the MCP server.

## Basic Usage

### 1. Creating Todos

**Simple todo:**
```python
"Add a todo to buy milk"
```
Result: Creates a todo titled "buy milk" in your Inbox

**Todo with details:**
```python
"Create a todo to prepare presentation with notes about including slides and demos, due Friday, tagged with work"
```
Result: Creates a rich todo with notes, deadline, and tags

**Batch creation:**
```python
"Add these todos for my morning routine:
- Make coffee
- Review calendar
- Check emails
- Plan top 3 priorities"
```
Result: Creates multiple todos at once

### 2. Managing Projects

**Create a project:**
```python
"Create a project called 'Website Redesign' with todos for research, wireframes, and implementation"
```

**Update project:**
```python
"Mark the Website Redesign project as completed"
```

### 3. Working with Lists

**View Today list:**
```python
"Show me what's on my Today list"
```

**Check Upcoming:**
```python
"What do I have coming up this week?"
```

**Review Inbox:**
```python
"What's in my inbox that needs to be processed?"
```

### 4. Using Tags

**Get all tags:**
```python
"List all my tags"
```

**Find tagged items:**
```python
"Show me all todos tagged with 'urgent'"
```

**Add tags to existing todos:**
```python
"Add the tag 'priority' to my presentation todo"
```

## Cool Things You Can Do

### 🎯 1. GTD Weekly Review Automation

```python
"Help me do my weekly review:
1. Show me all completed tasks from last week
2. List any overdue items
3. Show todos without projects or tags
4. Create a project for next week's priorities"
```

The MCP server can automate your entire GTD weekly review process!

### 📊 2. Productivity Analytics

```python
"Analyze my productivity:
- How many tasks did I complete this week?
- What projects am I working on?
- Which tags am I using most?
- Show me tasks that have been in Someday for over a month"
```

### 🔄 3. Bulk Operations

```python
"Move all todos tagged 'work' that are in Someday to Anytime"
```

```python
"Add the tag 'Q1-2025' to all projects in my Work area"
```

### 🧹 4. Inbox Zero Processing

```python
"Process my inbox:
- Show each item one by one
- Let me decide: today, upcoming, someday, or delete
- Add appropriate tags and projects
- Move to the right list"
```

### 📅 5. Smart Scheduling

```python
"Look at my Today list and:
- Flag anything that seems overdue
- Suggest what to postpone if I have too much
- Identify quick wins I can do in under 5 minutes"
```

### 🎨 6. Project Templates

```python
"Create a project template for client onboarding with these phases:
- Initial contact (email, schedule meeting)
- Discovery (requirements, timeline, budget)
- Proposal (draft, review, send)
- Setup (contracts, kickoff, access)"
```

### 🔍 7. Advanced Search & Filter

```python
"Find all todos that:
- Are tagged with 'waiting'
- Created more than a week ago
- Don't have a due date
- Are not in a project"
```

### 📈 8. Progress Tracking

```python
"Show me the progress on my 'Product Launch' project:
- What's completed?
- What's remaining?
- What's overdue?
- Estimate completion based on current pace"
```

## Advanced Workflows

### Workflow 1: Daily Planning Assistant

```python
# Morning planning routine
"Good morning! Please:
1. Show me what's due today
2. Check if anything is overdue
3. Look at my calendar (if integrated)
4. Suggest 3 most important tasks for today
5. Move them to Today if not already there
6. Create a 'Daily Notes' todo for capturing thoughts"
```

### Workflow 2: Project Status Reports

```python
# Weekly project status
"Generate a status report for all active projects:
- Name and completion percentage
- Recent completed items
- Upcoming milestones
- Blocked or waiting items
- Suggested next actions"
```

### Workflow 3: Email to Todo Processing

```python
# Process email subjects into todos
"Here are email subjects I need to handle:
- 'Re: Budget proposal review'
- 'Meeting notes from product sync'
- 'Client feedback on mockups'

Create todos for each with appropriate tags and put in Today if urgent"
```

### Workflow 4: Recurring Task Management

```python
# Set up recurring patterns
"Create these recurring patterns:
- Every Monday: Weekly planning (tag: planning)
- Every Friday: Weekly review (tag: review)  
- First of month: Pay bills (tag: finance)
- Quarterly: Update OKRs (tag: goals)"
```

### Workflow 5: Context-Based Task Lists

```python
# Get tasks by context
"I'm at my computer with 30 minutes free. Show me tasks that:
- Are tagged 'computer' or 'online'
- Take less than 30 minutes
- Are not blocked by anything
- Sorted by priority"
```

## API Reference

### Core Endpoints (24 Total)

#### Todo Operations
- `get_todos()` - Get all todos with optional project filter
- `add_todo()` - Create new todo with rich attributes
- `update_todo()` - Modify existing todo
- `get_todo_by_id()` - Retrieve specific todo
- `delete_todo()` - Remove todo (use with caution!)

#### Project Operations
- `get_projects()` - List all projects
- `add_project()` - Create new project
- `update_project()` - Modify project

#### List Operations
- `get_inbox()` - Get Inbox items
- `get_today()` - Get Today list
- `get_upcoming()` - Get Upcoming items
- `get_anytime()` - Get Anytime list
- `get_someday()` - Get Someday items
- `get_logbook()` - Get completed items
- `get_trash()` - Get deleted items

#### Tag Operations
- `get_tags()` - List all tags with IDs
- `get_tagged_items()` - Get items with specific tag

#### Search Operations
- `search_todos()` - Text search across todos
- `search_advanced()` - Complex filtered search
- `get_recent()` - Recently created items

#### UI Integration
- `show_item()` - Display item in Things 3
- `search_items()` - Search and display results

#### System
- `health_check()` - Verify server status

### Example API Calls

```python
# Create a rich todo
add_todo(
    title="Prepare Q1 Report",
    notes="Include revenue, costs, and projections",
    when="tomorrow",
    deadline="2025-01-15",
    tags=["work", "priority"],
    checklist_items=["Gather data", "Create charts", "Write summary"]
)

# Advanced search
search_advanced(
    status="incomplete",
    tag="work",
    area="Professional",
    start_date="2025-01-01"
)

# Get recent activity
get_recent(period="3d")  # Last 3 days
```

## Best Practices

### 1. **Use Tags Consistently**
- Create a tag taxonomy (e.g., contexts, projects, priority levels)
- Apply tags when creating todos for better organization

### 2. **Leverage Natural Language**
- The MCP server understands context
- Speak naturally: "due next Friday" instead of specific dates

### 3. **Batch Operations**
- Process multiple todos at once for efficiency
- Use bulk updates for project-wide changes

### 4. **Regular Reviews**
- Set up weekly review automation
- Use the logbook to track productivity

### 5. **Smart Filtering**
- Combine multiple criteria for powerful searches
- Save common searches as "views"

## Troubleshooting

### Common Issues

**1. "Things 3 not responding"**
- Ensure Things 3 is running
- Check System Preferences > Security > Privacy > Automation
- Grant permissions for Terminal/Python to control Things 3

**2. "Timeout errors"**
- Large operations may take time
- The server has retry logic built-in
- Consider breaking up bulk operations

**3. "Items not appearing"**
- Check which list/view you're in within Things 3
- Verify the item was created in the expected location
- Use `show_item()` to navigate to specific items

**4. "Authentication issues"**
- Ensure your auth token is correctly configured
- Check the `~/.things-auth` file
- Token format: `THINGS_AUTH_TOKEN=xxxxx`

### Performance Tips

1. **Use IDs for updates** - Faster than searching by name
2. **Limit search scope** - Specify projects/areas when possible
3. **Cache frequently used data** - Tags, projects change less often
4. **Batch similar operations** - Group creates/updates

## Real-World Use Cases

### Use Case 1: Content Creator Workflow
```python
"I'm planning content for next month. Create a project called 'March Content' with todos for:
- 4 blog posts (each with research, write, edit, publish subtasks)
- 2 videos (script, record, edit, upload)
- 5 social media campaigns
Tag everything with 'content' and spread due dates across the month"
```

### Use Case 2: Student Assignment Tracker
```python
"Track my assignments:
- Show all todos tagged 'homework'
- Highlight anything due in next 3 days
- Create study session todos for each assignment
- Add estimated time to complete in notes"
```

### Use Case 3: Travel Planning
```python
"I'm traveling to Paris next month. Create a travel project with:
- Pre-trip (passport, tickets, hotel, packing)
- During trip (daily itineraries)
- Post-trip (expenses, photos, thank you notes)
Set appropriate deadlines based on departure date"
```

### Use Case 4: Meeting Follow-ups
```python
"I just finished a meeting about the product launch. Create todos:
- Send meeting notes to attendees (today)
- Update project timeline (this week)
- Schedule follow-up with design team (next week)
- Review budget implications (tag: finance)
All under the 'Product Launch' project"
```

## Advanced Integration Ideas

### 1. **Combine with Calendar Data**
Use Claude to cross-reference your calendar and create todos for meeting prep.

### 2. **Email Integration**
Forward emails to Claude to automatically create actionable todos.

### 3. **Time Tracking**
Ask Claude to analyze your completed todos and estimate time spent on different projects.

### 4. **Goal Tracking**
Set up quarterly/yearly goals and have Claude track progress through your todos.

### 5. **Team Coordination**
Share project status updates generated from your Things data.

## Conclusion

The Things 3 MCP Server transforms Things from a great todo app into an AI-powered productivity system. Whether you're doing simple task management or complex project orchestration, the natural language interface makes it effortless.

Start with basic todo creation, then gradually explore the advanced features. The server is designed to grow with your needs, from simple task capture to sophisticated productivity workflows.

Remember: The goal isn't to use every feature, but to find the workflows that make YOU more productive. Experiment, iterate, and build your perfect system!

## Need Help?

- **GitHub Issues**: Report bugs or request features
- **Documentation**: Check the API reference for detailed parameters
- **Examples**: The `/examples` folder has more code samples
- **Community**: Share your workflows and learn from others

Happy organizing! 🚀