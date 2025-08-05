# Things 3 MCP Server - API Reference

Complete reference documentation for all MCP tools provided by the Things 3 MCP server.

## 📋 Table of Contents

1. [Overview](#overview)
2. [Data Models](#data-models)
3. [Todo Management Tools](#todo-management-tools)
4. [Project Management Tools](#project-management-tools)
5. [Area Management Tools](#area-management-tools)
6. [List Access Tools](#list-access-tools)
7. [Search & Tag Tools](#search--tag-tools)
8. [Navigation Tools](#navigation-tools)
9. [System Tools](#system-tools)
10. [Error Handling](#error-handling)

## 🔍 Overview

The Things 3 MCP server provides 20+ tools for comprehensive task management integration. All tools follow consistent patterns for parameters, responses, and error handling.

### Common Patterns

#### Parameter Types
- **Required**: Must be provided
- **Optional**: Can be omitted (has default value)
- **Conditional**: Required in certain contexts

#### Response Format
All tools return structured responses with consistent formatting:

```json
{
  "success": true,
  "data": { /* actual response data */ },
  "message": "Operation completed successfully",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Error Format
Error responses follow this structure:

```json
{
  "success": false,
  "error": "Error description",
  "error_code": "ERROR_CODE",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

## 📊 Data Models

### Todo Object

```typescript
interface Todo {
  id: string;                    // Unique identifier
  uuid: string;                  // Same as id (Things uses ID as UUID)
  title: string;                 // Todo title
  notes?: string;                // Optional notes
  status: "open" | "completed" | "canceled";
  creation_date?: string;        // ISO 8601 date string
  modification_date?: string;    // ISO 8601 date string
  completion_date?: string;      // ISO 8601 date string (if completed)
  due_date?: string;            // ISO 8601 date string
  activation_date?: string;      // ISO 8601 date string (scheduled date)
  project_uuid?: string;         // Parent project ID
  area_uuid?: string;           // Parent area ID
  tags: string[];               // List of tag names
  checklist_items?: ChecklistItem[];
}
```

### Project Object

```typescript
interface Project {
  id: string;
  uuid: string;
  title: string;
  notes?: string;
  status: "open" | "completed" | "canceled";
  creation_date?: string;
  modification_date?: string;
  completion_date?: string;
  due_date?: string;
  activation_date?: string;
  area_uuid?: string;
  tags: string[];
  todos?: Todo[];              // If include_items=true
}
```

### Area Object

```typescript
interface Area {
  id: string;
  uuid: string;
  title: string;
  notes?: string;
  creation_date?: string;
  modification_date?: string;
  tags: string[];
  projects?: Project[];        // If include_items=true
  todos?: Todo[];             // If include_items=true
}
```

### Tag Object

```typescript
interface Tag {
  id: string;
  uuid: string;
  name: string;
  keyboard_shortcut?: string;
  parent_tag_uuid?: string;
  items?: (Todo | Project)[];  // If include_items=true
}
```

### Checklist Item

```typescript
interface ChecklistItem {
  title: string;
  completed: boolean;
}
```

## 📝 Todo Management Tools

### get_todos

Get todos from Things, optionally filtered by project.

**Parameters:**
- `project_uuid` (optional, string): UUID of specific project to filter by
- `include_items` (optional, boolean, default: true): Include checklist items

**Returns:** `Todo[]`

**Example Request:**
```json
{
  "tool": "get_todos",
  "parameters": {
    "project_uuid": "ABC123-DEF456",
    "include_items": true
  }
}
```

**Example Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "todo-123",
      "uuid": "todo-123",
      "title": "Review project proposal",
      "notes": "Check budget and timeline",
      "status": "open",
      "creation_date": "2024-01-01T10:00:00Z",
      "project_uuid": "ABC123-DEF456",
      "tags": ["work", "urgent"],
      "checklist_items": [
        {"title": "Read document", "completed": true},
        {"title": "Provide feedback", "completed": false}
      ]
    }
  ]
}
```

### add_todo

Create a new todo in Things.

**Parameters:**
- `title` (required, string): Todo title
- `notes` (optional, string): Todo notes
- `tags` (optional, string[]): List of tag names
- `when` (optional, string): Schedule (today, tomorrow, evening, anytime, someday, YYYY-MM-DD)
- `deadline` (optional, string): Deadline date (YYYY-MM-DD format)
- `list_id` (optional, string): Project or area ID to add to
- `list_title` (optional, string): Project or area title to add to
- `heading` (optional, string): Heading to add under
- `checklist_items` (optional, string[]): List of checklist items

**Returns:** Creation result with todo data

**Example Request:**
```json
{
  "tool": "add_todo",
  "parameters": {
    "title": "Complete presentation",
    "notes": "Include Q4 results",
    "tags": ["work", "presentation"],
    "when": "tomorrow",
    "deadline": "2024-01-20",
    "list_title": "Work Projects",
    "checklist_items": ["Create slides", "Rehearse", "Send to team"]
  }
}
```

**Example Response:**
```json
{
  "success": true,
  "message": "Todo created successfully",
  "todo": {
    "title": "Complete presentation",
    "notes": "Include Q4 results",
    "tags": ["work", "presentation"],
    "when": "tomorrow",
    "deadline": "2024-01-20",
    "list_title": "Work Projects",
    "checklist_items": ["Create slides", "Rehearse", "Send to team"],
    "created_at": "2024-01-15T10:30:00Z",
    "url": "things:///add?title=Complete%20presentation&..."
  }
}
```

### update_todo

Update an existing todo in Things.

**Parameters:**
- `id` (required, string): ID of the todo to update
- `title` (optional, string): New title
- `notes` (optional, string): New notes
- `tags` (optional, string[]): New tags (replaces existing)
- `when` (optional, string): New schedule
- `deadline` (optional, string): New deadline (YYYY-MM-DD)
- `completed` (optional, boolean): Mark as completed
- `canceled` (optional, boolean): Mark as canceled

**Returns:** Update result

**Example Request:**
```json
{
  "tool": "update_todo",
  "parameters": {
    "id": "todo-123",
    "title": "Updated title",
    "completed": true
  }
}
```

**Example Response:**
```json
{
  "success": true,
  "message": "Todo updated successfully",
  "todo_id": "todo-123",
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### get_todo_by_id

Get a specific todo by its ID.

**Parameters:**
- `todo_id` (required, string): ID of the todo to retrieve

**Returns:** `Todo` object

**Example Request:**
```json
{
  "tool": "get_todo_by_id",
  "parameters": {
    "todo_id": "todo-123"
  }
}
```

### delete_todo

Delete a todo from Things.

**Parameters:**
- `todo_id` (required, string): ID of the todo to delete

**Returns:** Deletion result

**Example Request:**
```json
{
  "tool": "delete_todo",
  "parameters": {
    "todo_id": "todo-123"
  }
}
```

**Example Response:**
```json
{
  "success": true,
  "message": "Todo deleted successfully",
  "todo_id": "todo-123",
  "deleted_at": "2024-01-15T10:30:00Z"
}
```

## 📂 Project Management Tools

### get_projects

Get all projects from Things.

**Parameters:**
- `include_items` (optional, boolean, default: false): Include tasks within projects

**Returns:** `Project[]`

**Example Request:**
```json
{
  "tool": "get_projects",
  "parameters": {
    "include_items": true
  }
}
```

### add_project

Create a new project in Things.

**Parameters:**
- `title` (required, string): Project title
- `notes` (optional, string): Project notes
- `tags` (optional, string[]): List of tags
- `when` (optional, string): When to schedule the project
- `deadline` (optional, string): Deadline date (YYYY-MM-DD)
- `area_id` (optional, string): ID of area to add to
- `area_title` (optional, string): Title of area to add to
- `todos` (optional, string[]): Initial todos to create in the project

**Returns:** Project creation result

**Example Request:**
```json
{
  "tool": "add_project",
  "parameters": {
    "title": "Website Redesign",
    "notes": "Complete overhaul of company website",
    "area_title": "Marketing",
    "deadline": "2024-03-01",
    "tags": ["web", "design"],
    "todos": [
      "Research design trends",
      "Create wireframes",
      "Develop prototype"
    ]
  }
}
```

### update_project

Update an existing project in Things.

**Parameters:** Same as `update_todo` but with `id` referring to project ID

**Returns:** Project update result

## 🏢 Area Management Tools

### get_areas

Get all areas from Things.

**Parameters:**
- `include_items` (optional, boolean, default: false): Include projects and tasks within areas

**Returns:** `Area[]`

**Example Request:**
```json
{
  "tool": "get_areas",
  "parameters": {
    "include_items": true
  }
}
```

**Example Response:**
```json
{
  "success": true,
  "data": [
    {
      "id": "area-123",
      "uuid": "area-123",
      "title": "Work",
      "notes": "Professional responsibilities",
      "creation_date": "2024-01-01T00:00:00Z",
      "tags": ["professional"],
      "projects": [/* project objects if include_items=true */],
      "todos": [/* todo objects if include_items=true */]
    }
  ]
}
```

## 📋 List Access Tools

### get_inbox

Get todos from Inbox.

**Parameters:** None

**Returns:** `Todo[]`

**Example Request:**
```json
{
  "tool": "get_inbox",
  "parameters": {}
}
```

### get_today

Get todos due today.

**Parameters:** None

**Returns:** `Todo[]`

### get_upcoming

Get upcoming todos.

**Parameters:** None

**Returns:** `Todo[]`

### get_anytime

Get todos from Anytime list.

**Parameters:** None

**Returns:** `Todo[]`

### get_someday

Get todos from Someday list.

**Parameters:** None

**Returns:** `Todo[]`

### get_logbook

Get completed todos from Logbook.

**Parameters:**
- `limit` (optional, integer, default: 50, range: 1-100): Maximum number of entries to return
- `period` (optional, string, default: "7d", pattern: `^\d+[dwmy]$`): Time period to look back

**Returns:** `Todo[]` (completed todos)

**Example Request:**
```json
{
  "tool": "get_logbook",
  "parameters": {
    "limit": 20,
    "period": "30d"
  }
}
```

### get_trash

Get trashed todos.

**Parameters:** None

**Returns:** `Todo[]`

## 🔍 Search & Tag Tools

### search_todos

Search todos by title or notes.

**Parameters:**
- `query` (required, string): Search term to look for in todo titles and notes

**Returns:** `Todo[]`

**Example Request:**
```json
{
  "tool": "search_todos",
  "parameters": {
    "query": "meeting"
  }
}
```

### search_advanced

Advanced todo search with multiple filters.

**Parameters:**
- `status` (optional, string): Filter by todo status ("incomplete", "completed", "canceled")
- `type` (optional, string): Filter by item type ("to-do", "project", "heading")
- `tag` (optional, string): Filter by tag name
- `area` (optional, string): Filter by area UUID
- `start_date` (optional, string): Filter by start date (YYYY-MM-DD)
- `deadline` (optional, string): Filter by deadline (YYYY-MM-DD)

**Returns:** `Todo[]`

**Example Request:**
```json
{
  "tool": "search_advanced",
  "parameters": {
    "status": "incomplete",
    "tag": "urgent",
    "start_date": "2024-01-01",
    "deadline": "2024-01-31"
  }
}
```

### get_tags

Get all tags.

**Parameters:**
- `include_items` (optional, boolean, default: false): Include items tagged with each tag

**Returns:** `Tag[]`

**Example Request:**
```json
{
  "tool": "get_tags",
  "parameters": {
    "include_items": false
  }
}
```

### get_tagged_items

Get items with a specific tag.

**Parameters:**
- `tag` (required, string): Tag title to filter by

**Returns:** `(Todo | Project)[]`

**Example Request:**
```json
{
  "tool": "get_tagged_items",
  "parameters": {
    "tag": "urgent"
  }
}
```

### get_recent

Get recently created items.

**Parameters:**
- `period` (required, string, pattern: `^\d+[dwmy]$`): Time period (e.g., '3d', '1w', '2m', '1y')

**Returns:** `(Todo | Project)[]`

**Example Request:**
```json
{
  "tool": "get_recent",
  "parameters": {
    "period": "7d"
  }
}
```

## 🧭 Navigation Tools

### show_item

Show a specific item or list in Things.

**Parameters:**
- `id` (required, string): ID of item to show, or built-in list name ("inbox", "today", "upcoming", "anytime", "someday", "logbook")
- `query` (optional, string): Optional query to filter by
- `filter_tags` (optional, string[]): Optional tags to filter by

**Returns:** Show result

**Example Request:**
```json
{
  "tool": "show_item",
  "parameters": {
    "id": "today",
    "query": "meeting",
    "filter_tags": ["work"]
  }
}
```

**Example Response:**
```json
{
  "success": true,
  "message": "Successfully showed item: today"
}
```

### search_items

Search for items in Things.

**Parameters:**
- `query` (required, string): Search query

**Returns:** Search result

**Example Request:**
```json
{
  "tool": "search_items",
  "parameters": {
    "query": "project presentation"
  }
}
```

## 🔧 System Tools

### health_check

Check server health and Things 3 connectivity.

**Parameters:** None

**Returns:** Health status

**Example Request:**
```json
{
  "tool": "health_check",
  "parameters": {}
}
```

**Example Response:**
```json
{
  "server_status": "healthy",
  "things_running": true,
  "applescript_available": true,
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "cache_stats": {
    "hit_rate": 0.85,
    "size": 42,
    "max_size": 100
  }
}
```

## ⚠️ Error Handling

### Error Codes

| Code | Description | Resolution |
|------|-------------|------------|
| `PERMISSION_DENIED` | AppleScript permission denied | Grant automation permissions |
| `THINGS_NOT_RUNNING` | Things 3 not accessible | Start Things 3 application |
| `TIMEOUT_ERROR` | Operation timed out | Increase timeout or retry |
| `VALIDATION_ERROR` | Invalid parameters | Check parameter format |
| `APPLESCRIPT_ERROR` | AppleScript execution failed | Check AppleScript syntax |
| `NOT_FOUND` | Item not found | Verify item ID exists |
| `NETWORK_ERROR` | URL scheme failed | Check Things 3 URL scheme support |

### Common Error Responses

#### Permission Denied
```json
{
  "success": false,
  "error": "AppleScript execution failed: Application not authorized",
  "error_code": "PERMISSION_DENIED",
  "resolution": "Grant automation permissions in System Preferences > Security & Privacy > Privacy > Automation",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Things 3 Not Running
```json
{
  "success": false,
  "error": "Things 3 is not running or not accessible",
  "error_code": "THINGS_NOT_RUNNING",
  "resolution": "Start the Things 3 application",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Validation Error
```json
{
  "success": false,
  "error": "Invalid date format for deadline parameter",
  "error_code": "VALIDATION_ERROR",
  "details": {
    "parameter": "deadline",
    "provided": "2024/01/15",
    "expected": "YYYY-MM-DD format (e.g., 2024-01-15)"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### Item Not Found
```json
{
  "success": false,
  "error": "Todo with ID 'invalid-id' not found",
  "error_code": "NOT_FOUND",
  "details": {
    "item_type": "todo",
    "item_id": "invalid-id"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Error Recovery

#### Retry Logic
Most tools implement automatic retry with exponential backoff:

1. **First attempt**: Immediate execution
2. **Second attempt**: 1-second delay
3. **Third attempt**: 2-second delay
4. **Final failure**: Return error response

#### Timeout Handling
Default timeouts can be configured:

- **AppleScript execution**: 30 seconds
- **URL scheme operations**: 10 seconds
- **Cache operations**: 5 seconds

#### Graceful Degradation
When possible, tools provide partial results:

```json
{
  "success": true,
  "data": [/* partial results */],
  "warnings": [
    "Some items could not be retrieved due to timeout"
  ],
  "items_requested": 100,
  "items_returned": 85,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

This API reference provides complete documentation for all MCP tools. For usage examples and integration guides, see the [User Guide](USER_GUIDE.md) and [Developer Guide](DEVELOPER_GUIDE.md).