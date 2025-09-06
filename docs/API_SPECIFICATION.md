# Things 3 MCP Server API Specification

## Overview
- **Framework**: FastMCP 2.0  
- **Protocol**: Model Context Protocol (MCP)
- **Integration**: AppleScript via subprocess calls
- **Platform**: macOS 12.0+ with Things 3 installed
- **Current Coverage**: 28 operations (37% of AppleScript API)

## Core Data Models

### Todo Object
```json
{
  "id": "string",           // Things 3 internal ID
  "uuid": "string",         // Same as ID (Things uses ID as UUID)
  "title": "string",        // Todo title/name
  "notes": "string",        // Notes content
  "status": "string",       // "open", "completed", "canceled"  
  "tags": ["string"],       // Array of tag names
  "creation_date": "string", // ISO format: "YYYY-MM-DDTHH:MM:SS"
  "modification_date": "string", // ISO format: "YYYY-MM-DDTHH:MM:SS"
  "due_date": "string|null", // ISO format: "YYYY-MM-DDTHH:MM:SS"
  "start_date": "string|null", // ISO format: "YYYY-MM-DDTHH:MM:SS" (activation date)
  "area": "string|null",    // Area name if assigned
  "project": "string|null", // Project name if assigned
  "retrieved_at": "string"  // Timestamp when fetched
}
```

### Project Object
```json
{
  "id": "string",           // Things 3 internal ID
  "uuid": "string",         // Same as ID (Things uses ID as UUID)
  "title": "string",        // Project title/name
  "notes": "string",        // Notes content
  "status": "string",       // "open", "completed", "canceled"
  "tags": ["string"],       // Array of tag names (inherited from todo)
  "creation_date": "string", // ISO format: "YYYY-MM-DDTHH:MM:SS"
  "modification_date": "string", // ISO format: "YYYY-MM-DDTHH:MM:SS"
  "due_date": "string|null", // ISO format: "YYYY-MM-DDTHH:MM:SS" (inherited)
  "start_date": "string|null", // ISO format: "YYYY-MM-DDTHH:MM:SS" (activation date, inherited)
  "completion_date": "string|null", // ISO format: "YYYY-MM-DDTHH:MM:SS" (inherited)
  "cancellation_date": "string|null", // ISO format: "YYYY-MM-DDTHH:MM:SS" (inherited)
  "area": "string|null",    // Area name if assigned (inherited)
  "project": "string|null", // Parent project name for sub-projects (inherited)
  "contact": "string|null", // Contact name if assigned (inherited)
  "retrieved_at": "string", // Timestamp when fetched
  "todos": ["object"]       // Array of Todo objects if include_items=true
}
```

### Area Object  
```json
{
  "id": "string",
  "uuid": "string",
  "title": "string", 
  "notes": "string",
  "tags": ["string"],       // Currently empty array
  "projects": ["object"]    // Array of Project objects if include_items=true
}
```

### Tag Object
```json
{
  "name": "string",         // Tag name
  "items": ["object"]       // Array of tagged items if include_items=true
}
```

## API Endpoints (Tools)

### Todo Management (7 operations)

#### 1. get_todos
- **Parameters**: 
  - `project_uuid?: string` - Optional UUID of a specific project to get todos from
  - `include_items: bool = true` - Include checklist items
- **Returns**: `List[Todo]`
- **Description**: Get all todos, optionally filtered by project

#### 2. add_todo
- **Parameters**: 
  - `title: string` (required) - Title of the todo
  - `notes?: string` - Notes for the todo
  - `tags?: string` - Comma-separated tags. NOTE: Only existing tags will be applied. New tags must be created separately by the user.
  - `when?: string` - When to schedule the todo (today, tomorrow, evening, anytime, someday, or YYYY-MM-DD)
  - `deadline?: string` - Deadline for the todo (YYYY-MM-DD)
  - `list_id?: string` - ID of project/area to add to
  - `list_title?: string` - Title of project/area to add to
  - `heading?: string` - Heading to add under
  - `checklist_items?: string` - Newline-separated checklist items to add
- **Returns**: 
```json
{
  "success": "boolean",
  "message": "string", 
  "todo_id": "string",
  "date_warnings": ["string"], // Date conflict warnings
  "tag_info": {
    "created": ["string"],
    "existing": ["string"], 
    "filtered": ["string"],
    "warnings": ["string"]
  }
}
```

#### 3. update_todo
- **Parameters**: 
  - `id: string` (required) - ID of the todo to update
  - `title?: string` - New title
  - `notes?: string` - New notes
  - `tags?: string` - Comma-separated new tags
  - `when?: string` - New schedule
  - `deadline?: string` - New deadline
  - `completed?: string` - Mark as completed (true/false)
  - `canceled?: string` - Mark as canceled (true/false)
- **Returns**: Same as add_todo plus `date_warnings` array
- **Special Feature**: Date conflict warnings when rescheduling moves todo after its due date

#### 4. get_todo_by_id
- **Parameters**: 
  - `todo_id: string` (required) - ID of the todo to retrieve
- **Returns**: `Todo`

#### 5. delete_todo
- **Parameters**: 
  - `todo_id: string` (required) - ID of the todo to delete
- **Returns**: 
```json
{
  "success": "boolean",
  "message": "string"
}
```

#### 6. move_record
- **Parameters**: 
  - `todo_id: string` (required) - ID of the todo to move
  - `destination_list: string` (required) - Destination: list name (inbox, today, anytime, someday, upcoming, logbook), project:ID, or area:ID
- **Returns**: Success/error response

#### 7. bulk_move_records
- **Parameters**:
  - `todo_ids: string` (required) - Comma-separated list of todo IDs to move
  - `destination: string` (required) - Destination: list name (inbox, today, anytime, someday, upcoming, logbook), project:ID, or area:ID
  - `preserve_scheduling: bool = true` - Whether to preserve existing scheduling when moving
  - `max_concurrent: int = 5` - Maximum concurrent operations (1-10)
- **Returns**:
```json
{
  "success": "boolean",
  "total_requested": "number",
  "moved_count": "number", 
  "failed_count": "number",
  "details": ["object"]
}
```

### Project Management (3 operations)

#### 8. get_projects
- **Parameters**: 
  - `include_items: bool = false` - Include tasks within projects
- **Returns**: `List[Project]`

#### 9. add_project
- **Parameters**: 
  - `title: string` (required) - Title of the project
  - `notes?: string` - Notes for the project
  - `tags?: string` - Comma-separated tags to apply to the project
  - `when?: string` - When to schedule the project
  - `deadline?: string` - Deadline for the project
  - `area_id?: string` - ID of area to add to
  - `area_title?: string` - Title of area to add to
  - `todos?: string` - Newline-separated initial todos to create in the project
- **Returns**: Success response with project_id

#### 10. update_project
- **Parameters**: 
  - `id: string` (required) - ID of the project to update
  - `title?: string` - New title
  - `notes?: string` - New notes
  - `tags?: string` - Comma-separated new tags
  - `when?: string` - New schedule
  - `deadline?: string` - New deadline
  - `completed?: string` - Mark as completed (true/false)
  - `canceled?: string` - Mark as canceled (true/false)
- **Returns**: Success/error response

### Area Management (1 operation)

#### 11. get_areas
- **Parameters**: 
  - `include_items: bool = false` - Include projects and tasks within areas
- **Returns**: `List[Area]`

### List-Based Views (7 operations)

#### 12. get_inbox
- **Parameters**: None
- **Returns**: `List[Todo]`
- **Description**: Get todos from Inbox

#### 13. get_today
- **Parameters**: None
- **Returns**: `List[Todo]`
- **Description**: Get todos due today

#### 14. get_upcoming
- **Parameters**: None
- **Returns**: `List[Todo]`
- **Description**: Get upcoming todos

#### 15. get_anytime
- **Parameters**: None
- **Returns**: `List[Todo]`
- **Description**: Get todos from Anytime list

#### 16. get_someday
- **Parameters**: None
- **Returns**: `List[Todo]`
- **Description**: Get todos from Someday list

#### 17. get_logbook
- **Parameters**: 
  - `limit: int = 50` - Maximum number of entries to return. Defaults to 50 (1-100)
  - `period: string = "7d"` - Time period to look back (e.g., '3d', '1w', '2m', '1y'). Defaults to '7d'
- **Returns**: `List[Todo]` (completed todos)
- **Description**: Get completed todos from Logbook, defaults to last 7 days

#### 18. get_trash
- **Parameters**: None
- **Returns**: `List[Todo]`
- **Description**: Get trashed todos

### Tag Management (5 operations)

#### 19. get_tags
- **Parameters**: 
  - `include_items: bool = false` - Include items tagged with each tag
- **Returns**: `List[Tag]`

#### 20. get_tagged_items
- **Parameters**: 
  - `tag: string` (required) - Tag title to filter by
- **Returns**: `List[Todo]`

#### 21. add_tags
- **Parameters**: 
  - `todo_id: string` (required) - ID of the todo
  - `tags: string` (required) - Comma-separated tags to add
- **Returns**: Success response with tag policy information

#### 22. remove_tags
- **Parameters**: 
  - `todo_id: string` (required) - ID of the todo
  - `tags: string` (required) - Comma-separated tags to remove
- **Returns**: Success/error response

#### 23. create_tag
- **Parameters**: 
  - `tag_name: string` (required) - Name of the tag to create
- **Returns**: Policy-controlled response (AI restrictions by default)
- **Description**: Create a new tag in Things 3. IMPORTANT: This tool is for HUMAN USE ONLY. AI assistants should not create tags automatically.

### Search Operations (3 operations)

#### 24. search_todos
- **Parameters**: 
  - `query: string` (required) - Search term to look for in todo titles and notes
- **Returns**: `List[Todo]` with full date information

#### 25. search_advanced
- **Parameters**:
  - `status?: string` - Filter by todo status (incomplete|completed|canceled)
  - `type?: string` - Filter by item type (to-do|project|heading)
  - `tag?: string` - Filter by tag
  - `area?: string` - Filter by area UUID
  - `start_date?: string` - Filter by start date (YYYY-MM-DD)
  - `deadline?: string` - Filter by deadline (YYYY-MM-DD)
  - `limit: int = 50` - Maximum number of results to return (1-500)
- **Returns**: `List[Todo]`

#### 26. get_recent
- **Parameters**: 
  - `period: string` (required) - Time period (e.g., '3d', '1w', '2m', '1y')
- **Returns**: `List[Todo]`

### System Operations (2 operations)

#### 27. health_check
- **Parameters**: None
- **Returns**:
```json
{
  "server_status": "healthy|unhealthy",
  "things_running": "boolean",
  "applescript_available": "boolean", 
  "timestamp": "string",
  "error?: string"
}
```

#### 28. queue_status
- **Parameters**: None
- **Returns**:
```json
{
  "queue_status": "object",
  "active_operations": "array",
  "timestamp": "string"
}
```

## Key Features

### Date Handling
- **Input Formats**: ISO (YYYY-MM-DD), relative (today, tomorrow), natural language
- **Output Format**: All dates normalized to ISO format "YYYY-MM-DDTHH:MM:SS"
- **European Date Support**: Handles AppleScript's "Thursday, 4. September 2025 at 00:00:00" format
- **Date Conflict Warnings**: Alerts when rescheduling creates due date conflicts

### Tag Management
- **Policy-Based**: Configurable tag creation policies (allow_all, filter_unknown, warn_unknown, reject_unknown)
- **AI Restrictions**: create_tag tool restricted to human users by default
- **Validation Service**: Tracks created, existing, filtered tags with warnings

### Error Handling & Reliability
- **Operation Queue**: Ensures write operation consistency with priority handling
- **Graceful Degradation**: Fallbacks for AppleScript failures
- **Comma Protection**: Special parsing for fields containing commas (dates, tag names)
- **Caching**: Optional caching with TTL for performance

## Identified Gaps & Missing Features

### Current Coverage: 28 operations (37% of AppleScript API)

#### Missing Core Features:
1. **Area Management**: Only get_areas implemented, missing add_area, update_area
2. **Checklist Item Management**: Limited support for checklist items within todos  
3. **Attachment Management**: No file/image attachment support
4. **Recurring Tasks**: No support for repeating todos
5. **Location-Based Tasks**: No geofencing/location trigger support

#### Missing Advanced Features:
7. **Smart Lists**: No custom smart list creation/management
8. **Batch Tag Operations**: Missing bulk tag add/remove across multiple todos
9. **Template System**: No todo/project template support  
10. **Export/Import**: No backup/restore functionality
11. **Statistics/Analytics**: No reporting on completion rates, time tracking
12. **Cross-Reference**: No linking between todos/projects

#### Incomplete Implementations:
- Project todos extraction when `include_items=true` (marked TODO)
- Area projects/todos when `include_items=true` (marked TODO)  
- Full AppleScript error context in responses
- Comprehensive validation for all date formats

#### Performance & Reliability Gaps:
- No bulk operations for add/update (only delete/move)
- Limited concurrent operation controls  
- No retry mechanisms for individual operations
- Missing transaction-like operations for complex changes

## Test Plan Recommendations

### Unit Tests (High Priority)
1. **Date Parsing & Normalization**: All input formats → ISO output
2. **Tag Policy Enforcement**: Each policy type with various scenarios  
3. **AppleScript Output Parsing**: Edge cases, malformed data, empty responses
4. **Date Conflict Detection**: Various scheduling conflict scenarios

### Integration Tests (Medium Priority)  
1. **End-to-End Workflows**: Create → Update → Move → Delete sequences
2. **Bulk Operations**: Performance and consistency under load
3. **Error Recovery**: AppleScript failures, network issues, Things 3 unavailable
4. **Concurrency**: Multiple simultaneous operations

### Performance Tests (Lower Priority)
1. **Large Dataset Handling**: 1000+ todos, projects, tags
2. **Search Performance**: Complex queries, large result sets
3. **Memory Usage**: Long-running server instances
4. **Cache Effectiveness**: Hit rates, TTL behavior

## Implementation Notes

### File Locations
- **Main Server**: `src/things_mcp/simple_server.py` (FastMCP 2.0 tool registrations)
- **Core Tools**: `src/things_mcp/tools.py` (ThingsTools class implementation)
- **AppleScript Manager**: `src/things_mcp/applescript_manager.py` (AppleScript execution and parsing)
- **Date Handling**: `src/things_mcp/locale_aware_dates.py` (Date normalization)
- **Tag Validation**: `src/things_mcp/services/tag_service.py` (Policy enforcement)

### Key Technical Details
- Uses operation queue for write consistency
- European date format support with comma protection
- Policy-based tag creation with AI restrictions
- Comprehensive error handling with fallbacks
- Date conflict warnings for scheduling operations