# Things 3 MCP Server - Development TODO

## Overview

This document tracks the development roadmap for the Things 3 MCP Server. Based on comprehensive analysis of the Things 3 AppleScript Dictionary, **8 missing commands** and **several property access methods** have been identified that would complete the server's AppleScript capabilities.

## Current Status

- **IMPLEMENTED**: 34 MCP tools covering ~80% of daily workflow needs
- **MISSING COMMANDS**: 8 AppleScript commands from dictionary
- **MISSING PROPERTIES**: Direct property access for dates, contacts, status
- **TARGET COVERAGE**: 95%+ with Critical priority features

## Recently Completed [DONE]

- ✅ **move_record()** - Move todos/projects between lists, projects, areas
- ✅ **Scheduling with reminders** - Support for `when="today@14:30"` datetime format
- ✅ **Reliable scheduling** - Multiple fallback methods via PureAppleScriptScheduler
- ✅ **Configurable limits** - Control result counts in search_advanced and get_logbook
- ✅ **Performance optimizations** - Fixed timeout issues with large datasets
- ✅ **Circular reference fixes** - JSON serialization improvements

---

# DEVELOPMENT ROADMAP

## CRITICAL Priority - Missing AppleScript Commands (8 commands)
*Commands explicitly defined in Things 3 AppleScript Dictionary that are not yet implemented*

### 1. **schedule** - Direct Schedule Command  
- **Status**: PARTIALLY IMPLEMENTED (via when parameter, not as standalone command)
- **Priority**: Critical
- **Effort**: 2-3 hours
- **AppleScript**: `schedule <reference> for <date>`
- **Purpose**: Direct scheduling command separate from create/update operations
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def schedule_todo(
      todo_id: str, 
      schedule_date: str  # YYYY-MM-DD or natural language
  ) -> Dict[str, Any]
  ```
- **Notes**: We have scheduling via when parameter, but not as a standalone command
- **Files to modify**: `server.py`, `tools.py`

### 2. **edit** - Edit Command
- **Status**: NOT STARTED  
- **Priority**: Critical
- **Effort**: 1-2 hours
- **AppleScript**: `edit <to do>`
- **Purpose**: Open todo for interactive editing in Things UI
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def edit_todo(todo_id: str) -> Dict[str, Any]
  ```
- **Notes**: UI-focused command, may not be suitable for headless operation
- **Files to modify**: `server.py`, `tools.py`

### 3. **show** - Show Command  
- **Status**: NOT STARTED (removed previously as UI-triggering)
- **Priority**: Critical
- **Effort**: 1-2 hours
- **AppleScript**: `show <reference>`
- **Purpose**: Display/navigate to items in Things UI
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def show_item(
      item_id: str, 
      item_type: str = "todo"  # todo, project, area, contact, list
  ) -> Dict[str, Any]
  ```
- **Notes**: Comment in code says "Removed show_item as it triggers UI changes"
- **Files to modify**: `server.py`, `tools.py`

### 4. **parse quicksilver input** - Natural Language Input
- **Status**: NOT STARTED
- **Priority**: Critical
- **Effort**: 3-4 hours
- **AppleScript**: `parse quicksilver input <text>`
- **Purpose**: Natural language todo creation using Things' smart parsing
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def parse_natural_language(
      input_text: str
  ) -> Dict[str, Any]  # Returns created todo details
  ```
- **Example**: `"Call John tomorrow about project #work"` → Todo with due date, tags
- **Files to modify**: `server.py`, `tools.py`

### 5. **add contact named** - Contact Creation
- **Status**: NOT STARTED
- **Priority**: High
- **Effort**: 2-3 hours
- **AppleScript**: `add contact named <text>`
- **Purpose**: Create new contacts in Things
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def add_contact(contact_name: str) -> Dict[str, Any]
  ```
- **Files to modify**: `server.py`, `tools.py`

### 6. **empty trash** - Trash Management
- **Status**: NOT STARTED
- **Priority**: Medium
- **Effort**: 1 hour
- **AppleScript**: `empty trash`
- **Purpose**: Permanently delete trashed items
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def empty_trash() -> Dict[str, Any]
  ```
- **Files to modify**: `server.py`, `tools.py`

### 7. **log completed now** - Force Logging
- **Status**: NOT STARTED
- **Priority**: Low
- **Effort**: 1 hour
- **AppleScript**: `log completed now`
- **Purpose**: Force immediate logging of completed items
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def log_completed_now() -> Dict[str, Any]
  ```
- **Files to modify**: `server.py`, `tools.py`

### 8. **show quick entry panel** - Quick Entry UI
- **Status**: NOT STARTED
- **Priority**: Low (UI-focused)
- **Effort**: 2-3 hours
- **AppleScript**: `show quick entry panel with autofill <boolean> with properties <item details>`
- **Purpose**: Display Things quick entry UI with pre-filled data
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def show_quick_entry_panel(
      autofill: bool = False,
      properties: Optional[Dict[str, Any]] = None
  ) -> Dict[str, Any]
  ```
- **Notes**: UI-focused command, may not be suitable for headless operation
- **Files to modify**: `server.py`, `tools.py`

---

## HIGH Priority - Property-Based Operations
*Direct property manipulation capabilities that would enhance the API*

### Direct Property Access
- **activation date** - Direct get/set for todo activation dates
- **due date** - Direct manipulation separate from scheduling
- **contact** - Assign contacts to todos (property, not command)
- **status** - Direct status manipulation for projects
- **area** - Direct area assignment for projects/todos
- **parent tag** - Tag hierarchy management
- **keyboard shortcut** - Tag keyboard shortcuts

---

## MEDIUM Priority - Enhanced Capabilities
*Features that would improve workflows but aren't critical*

### Tag Enhancements
- Tag hierarchy (parent/child relationships)
- Keyboard shortcuts for tags
- Batch tag operations

### Area Management
- Create new areas
- Set area properties (collapsed state, etc.)
- Move items between areas
- Area hierarchy support

### Project Status Management
- Set project status (active, someday, completed, canceled)
- Bulk status updates
- Status-based filtering improvements

---

## Implementation Summary

### Total AppleScript Dictionary Coverage
- **Dictionary Commands**: 10 total (close, count, delete, duplicate, exists, make, print, quit + 8 Things-specific)
- **Implemented Commands**: Most via MCP tools (create, read, update, delete operations)
- **Missing Commands**: 8 Things-specific commands listed above
- **Property Access**: Most properties readable, some not directly settable

### Current Implementation Strengths
- ✅ Full CRUD operations for todos, projects, areas, tags
- ✅ Advanced search and filtering capabilities
- ✅ Date-based queries and scheduling with reminders
- ✅ Bulk operations and performance optimizations
- ✅ Context management and usage statistics
- ✅ Reliable scheduling with multiple fallback methods

### Key Gaps
- ❌ UI-triggering commands (edit, show, quick entry panel)
- ❌ Natural language parsing (parse quicksilver input)
- ❌ Contact management (add contact named)
- ❌ System commands (empty trash, log completed now)
- ❌ Direct property setters for some fields

### Recommendation
Focus on non-UI commands first (schedule, parse quicksilver input, add contact named) as they provide the most value for automation workflows. UI-triggering commands may be less useful in headless MCP server context.

---

*Last Updated: September 2025*
*Current Version: 2.0.0 (with reminder support)*
*Next Target: 2.1.0 (add natural language parsing)*
