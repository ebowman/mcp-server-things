# Things 3 MCP Server - Development TODO

## Overview

This document tracks the development roadmap for the Things 3 MCP Server. Based on comprehensive analysis of the Things 3 AppleScript Dictionary, **43 missing features** have been identified that would significantly enhance the server's capabilities.

## Current Status

- **✅ Implemented Features**: 25 operations (37% of total AppleScript capability)
- **🚧 Missing Features**: 43 operations (63% of total AppleScript capability)
- **📈 Target Coverage**: 70%+ with Critical and High priority features

## Recently Completed ✅

- **move_record()** - Move todos/projects between lists, projects, areas (CRITICAL #1)
- **Configurable limits** - Control result counts in search_advanced and get_logbook
- **Performance optimizations** - Fixed timeout issues with large datasets (5,392 logbook items)
- **Circular reference fixes** - JSON serialization improvements in search_advanced

---

# DEVELOPMENT ROADMAP

## 🚨 CRITICAL Priority (6 remaining)
*Essential workflow features that significantly impact daily productivity*

### 2. **schedule_todo()** - Schedule Command
- **Status**: 🔴 Not Started
- **Priority**: Critical
- **Effort**: 2-3 hours
- **AppleScript**: `schedule <reference> for <date>`
- **Purpose**: Schedule todos for specific dates using native Things scheduling
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def schedule_todo(
      todo_id: str, 
      schedule_date: str  # YYYY-MM-DD or natural language
  ) -> Dict[str, Any]
  ```
- **Files to modify**: `tools.py`, `simple_server.py`
- **Testing**: Date parsing, invalid dates, already scheduled todos

### 3. **edit_todo()** - Edit Command
- **Status**: 🔴 Not Started  
- **Priority**: Critical
- **Effort**: 1-2 hours
- **AppleScript**: `edit <to do>`
- **Purpose**: Open todo for interactive editing in Things UI
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def edit_todo(todo_id: str) -> Dict[str, Any]
  ```
- **Files to modify**: `tools.py`, `simple_server.py`
- **Testing**: Invalid todo IDs, UI integration, Things focus

### 4. **show_item()** - Show Command  
- **Status**: 🔴 Not Started
- **Priority**: Critical
- **Effort**: 1-2 hours
- **AppleScript**: `show <reference>`
- **Purpose**: Display/navigate to items in Things UI
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def show_item(
      item_id: str, 
      item_type: str = "todo"  # todo, project, area
  ) -> Dict[str, Any]
  ```
- **Files to modify**: `tools.py`, `simple_server.py`
- **Testing**: All item types, invalid IDs, UI focus

### 5. **parse_natural_language()** - Quicksilver Input
- **Status**: 🔴 Not Started
- **Priority**: Critical
- **Effort**: 3-4 hours
- **AppleScript**: `parse quicksilver input <text>`
- **Purpose**: Natural language todo creation (Things' smart parsing)
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def parse_natural_language(
      input_text: str
  ) -> Dict[str, Any]  # Returns created todo details
  ```
- **Example**: `"Call John tomorrow about project #work"` → Todo with due date, contact, tags
- **Files to modify**: `tools.py`, `simple_server.py`
- **Testing**: Complex parsing, tags, dates, contacts, projects

### 6. **enhanced_todo_properties()** - Direct Property Access
- **Status**: 🔴 Not Started
- **Priority**: Critical  
- **Effort**: 2-3 hours
- **Missing Properties**: `activation date`, `due date` direct access, `contact` assignment
- **Purpose**: Efficient individual property get/set operations
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def set_todo_properties(
      todo_id: str,
      activation_date: Optional[str] = None,
      due_date: Optional[str] = None,
      contact_name: Optional[str] = None
  ) -> Dict[str, Any]
  
  @self.mcp.tool() 
  async def get_todo_properties(
      todo_id: str,
      properties: List[str]  # ["activation_date", "due_date", "contact"]
  ) -> Dict[str, Any]
  ```
- **Files to modify**: `tools.py`, `simple_server.py`
- **Testing**: All property types, invalid values, property combinations

### 7. **enhanced_project_properties()** - Project Property Access
- **Status**: 🔴 Not Started
- **Priority**: Critical
- **Effort**: 2-3 hours  
- **Missing Properties**: `status` manipulation, `area` assignment via property
- **Purpose**: Direct project property modification
- **Implementation**:
  ```python
  @self.mcp.tool()
  async def set_project_status(
      project_id: str,
      status: str  # "active", "someday", "completed", "cancelled"
  ) -> Dict[str, Any]
  
  @self.mcp.tool()
  async def assign_project_to_area(
      project_id: str,
      area_id: str
  ) -> Dict[str, Any]
  ```
- **Files to modify**: `tools.py`, `simple_server.py`
- **Testing**: All status types, area assignments, invalid IDs

---

## 🔥 HIGH Priority (12 features)
*Major functionality gaps that enable advanced workflows*

### Contact Management (4 operations)

### 8. **add_contact()** - Contact Creation
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 2-3 hours
- **AppleScript**: `add contact named <text>`
- **Implementation**: Contact creation and management system

### 9. **get_contacts()** - Contact Listing  
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 1-2 hours
- **Purpose**: List all contacts with properties

### 10. **assign_contact_to_todo()** - Contact Assignment
- **Status**: 🔴 Not Started  
- **Priority**: High
- **Effort**: 2-3 hours
- **Purpose**: Assign people to todos for collaboration

### 11. **get_todos_by_contact()** - Contact-based Search
- **Status**: 🔴 Not Started
- **Priority**: High  
- **Effort**: 1-2 hours
- **Purpose**: Find todos assigned to specific people

### Advanced Tag Operations (3 operations)

### 12. **create_tag_with_properties()** - Rich Tag Creation
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 2-3 hours
- **Purpose**: Create tags with shortcuts and hierarchy

### 13. **manage_tag_hierarchy()** - Tag Relationships
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 3-4 hours
- **Purpose**: Create nested tag structures

### 14. **manage_tag_shortcuts()** - Keyboard Shortcuts  
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 1-2 hours
- **Purpose**: Manage quick-access tag shortcuts

### Date and Schedule Management (5 operations)

### 15. **set_activation_date()** - Activation Date Control
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 1-2 hours
- **Purpose**: Control when todos become active

### 16. **set_due_date_direct()** - Direct Due Date Access
- **Status**: 🔴 Not Started
- **Priority**: High  
- **Effort**: 1-2 hours
- **Purpose**: Direct date property modification

### 17. **set_start_date()** - Start Date Scheduling
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 1-2 hours  
- **Purpose**: Control todo start dates independently

### 18. **search_by_date_range()** - Date Range Filtering
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 2-3 hours
- **Purpose**: Find todos by date ranges and date properties

### 19. **get_schedule_status()** - Schedule Status Management
- **Status**: 🔴 Not Started
- **Priority**: High
- **Effort**: 1-2 hours
- **Purpose**: Understand and control todo scheduling status

---

## 🎯 MEDIUM Priority (14 features)
*Workflow enhancements and organizational improvements*

### Area Management Extensions (4 operations)

### 20. **create_area()** - Area Creation
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 1-2 hours
- **Purpose**: Create new area containers

### 21. **set_area_properties()** - Area Configuration
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 1-2 hours
- **Purpose**: Configure area display and organization

### 22. **assign_todo_to_area()** - Area-Todo Relationships
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 2-3 hours
- **Purpose**: Organize todos within areas

### 23. **manage_area_hierarchy()** - Area Organization
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 3-4 hours
- **Purpose**: Multi-level area organization

### Project Extensions (3 operations)

### 24. **manage_project_status()** - Project Lifecycle
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 2-3 hours
- **Purpose**: Project lifecycle state management

### 25. **assign_project_to_area()** - Project Organization
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 1-2 hours
- **Purpose**: Organize projects within areas

### 26. **complete_project_workflow()** - Project Finalization
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 3-4 hours
- **Purpose**: Complete project finalization workflows

### Advanced Search and Filtering (4 operations)

### 27. **complex_search_filtering()** - Multi-Property Search
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 4-5 hours
- **Purpose**: Complex search queries with multiple conditions

### 28. **comprehensive_property_search()** - Multi-Property Search
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 3-4 hours
- **Purpose**: Search across all object properties simultaneously

### 29. **date_range_queries()** - Temporal Filtering
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 2-3 hours
- **Purpose**: Find items within date ranges

### 30. **status_based_collections()** - Status-Based Queries
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 2-3 hours
- **Purpose**: Efficient status-based queries

### List Management (3 operations)

### 31. **get_list_properties()** - List Introspection
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 1-2 hours
- **Purpose**: Detailed list information and manipulation

### 32. **discover_all_lists()** - List Discovery
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 1-2 hours
- **Purpose**: Discover and work with all Things lists

### 33. **list_specific_operations()** - List Customization
- **Status**: 🔴 Not Started
- **Priority**: Medium
- **Effort**: 2-3 hours
- **Purpose**: List-tailored operations

---

## 🔧 LOW Priority (10 features)
*Nice-to-have features for completeness*

### System Operations (3 operations)

### 34. **empty_trash()** - Trash Management
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 1 hour
- **Purpose**: Clear deleted items permanently

### 35. **log_completed_now()** - Manual Logging
- **Status**: 🔴 Not Started  
- **Priority**: Low
- **Effort**: 1 hour
- **Purpose**: Force immediate logging of completed items

### 36. **print_operations()** - Report Generation
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 2-3 hours
- **Purpose**: Generate printed reports

### UI Integration (4 operations)

### 37. **show_quick_entry_panel()** - UI Automation
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 2-3 hours
- **Purpose**: Display Things quick entry UI with pre-filled data

### 38. **window_management()** - UI Control
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 3-4 hours
- **Purpose**: Control Things UI display

### 39. **application_state_queries()** - Application Introspection
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 2-3 hours
- **Purpose**: Query Things application state, preferences

### 40. **frontmost_application_detection()** - Context Awareness
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 1-2 hours
- **Purpose**: Context-aware operations

### Advanced Parsing (3 operations)

### 41. **item_details_records()** - Batch Property Updates
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 3-4 hours
- **Purpose**: Batch property updates via records

### 42. **complex_property_records()** - Bulk Operations
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 4-5 hours
- **Purpose**: Efficient bulk property manipulation

### 43. **applescript_type_coercion()** - Type System
- **Status**: 🔴 Not Started
- **Priority**: Low
- **Effort**: 4-5 hours
- **Purpose**: Advanced type conversion and coercion

---

# IMPLEMENTATION STRATEGY

## Phase 1: Core Workflow Features (Weeks 1-2)
**Target: 70%+ API coverage**
- ✅ move_record() (COMPLETED)
- 🔲 schedule_todo() (2-3 hours)
- 🔲 edit_todo() (1-2 hours)  
- 🔲 show_item() (1-2 hours)
- 🔲 parse_natural_language() (3-4 hours)
- 🔲 enhanced_todo_properties() (2-3 hours)
- 🔲 enhanced_project_properties() (2-3 hours)

**Estimated Total**: 11-17 hours

## Phase 2: Advanced Features (Weeks 3-4)
**Target: 85%+ API coverage**
- Contact management (4 operations, 6-10 hours)
- Advanced tag operations (3 operations, 6-9 hours)
- Date/schedule management (5 operations, 7-12 hours)

**Estimated Total**: 19-31 hours

## Phase 3: Workflow Enhancements (Month 2)
**Target: 95%+ API coverage**
- Area management extensions (4 operations, 7-11 hours)
- Project extensions (3 operations, 6-9 hours) 
- Advanced search capabilities (4 operations, 11-15 hours)
- List management (3 operations, 4-7 hours)

**Estimated Total**: 28-42 hours

## Phase 4: Polish & Completeness (Optional)
**Target: 100% API coverage**
- System operations (3 operations, 4-6 hours)
- UI integration (4 operations, 8-12 hours)
- Advanced parsing (3 operations, 11-14 hours)

**Estimated Total**: 23-32 hours

---

# TECHNICAL NOTES

## Implementation Patterns

### Standard MCP Tool Pattern
```python
# simple_server.py
@self.mcp.tool()
async def new_operation(
    param1: str = Field(..., description="Required parameter"),
    param2: Optional[str] = Field(None, description="Optional parameter")
) -> Dict[str, Any]:
    """Tool description."""
    try:
        return await self.tools.new_operation(param1=param1, param2=param2)
    except Exception as e:
        logger.error(f"Error in new_operation: {e}")
        raise

# tools.py  
async def new_operation(self, param1: str, param2: Optional[str] = None) -> Dict[str, Any]:
    """Business logic implementation."""
    try:
        # Input validation
        if not param1:
            raise ValueError("param1 is required")
            
        # AppleScript execution
        script = f'''
        tell application "Things3"
            -- AppleScript logic here
            return "success"
        end tell
        '''
        
        result = await self.applescript.execute_applescript(script)
        
        if result.get("success"):
            return {
                "success": True,
                "message": "Operation completed successfully",
                "data": parsed_result
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error")
            }
            
    except Exception as e:
        logger.error(f"Error in new_operation: {e}")
        raise
```

## Testing Strategy

### Unit Tests Required
- Input validation and edge cases
- AppleScript command generation
- Error handling and recovery
- JSON serialization of results

### Integration Tests Required  
- End-to-end MCP tool functionality
- Real Things 3 integration (when available)
- Performance with large datasets
- Concurrent operation handling

### Test Data Requirements
- Sample todos, projects, areas, contacts
- Various date formats and edge cases
- Large dataset simulation (1000+ items)
- Error condition simulation

## Performance Considerations

### Optimization Strategies
- **Caching**: Read-only operations cached for 30 seconds
- **Batching**: Group similar operations when possible
- **Limiting**: Default limits on large result sets (50-500 items)
- **Validation**: Pre-flight checks to avoid expensive failures

### Resource Management
- AppleScript timeout handling (45 seconds max)
- Connection pooling for AppleScript execution
- Memory-efficient result processing
- Error recovery and retry logic

## Security Considerations

### Input Sanitization
- AppleScript injection prevention
- ID validation and whitelisting
- String escaping for AppleScript strings
- Parameter validation at multiple layers

### Operation Safety
- Atomic operations where possible
- Rollback strategies for failed operations
- Audit logging for destructive operations
- Permission validation where applicable

---

# CURRENT METRICS

## Implementation Status
- **Total AppleScript Operations Available**: 68
- **Currently Implemented**: 25 (37%)
- **Missing (This TODO)**: 43 (63%)
- **Critical Priority Remaining**: 6 operations  
- **High Priority**: 12 operations
- **Medium Priority**: 14 operations
- **Low Priority**: 10 operations

## Complexity Breakdown
- **Easy to Implement**: 15 features (1-2 hours each)
- **Medium Complexity**: 18 features (2-4 hours each)  
- **High Complexity**: 10 features (4-6 hours each)
- **Total Estimated Effort**: 81-122 hours

## Impact Analysis
- **Critical Features**: Essential daily workflows (scheduling, navigation, smart parsing)
- **High Priority Features**: Advanced automation (contacts, tag hierarchy, date management)
- **Medium Priority Features**: Organizational improvements (areas, projects, search)
- **Low Priority Features**: Completeness and polish (system ops, UI integration)

---

# CONTRIBUTION GUIDELINES

## Before Starting a Feature
1. **Review AppleScript Dictionary** - Understand native Things 3 capabilities
2. **Check existing patterns** - Follow established code conventions
3. **Write tests first** - TDD approach for reliability
4. **Update documentation** - Keep tutorial and API docs current

## Implementation Checklist
- [ ] AppleScript command research and testing
- [ ] Input validation and error handling
- [ ] MCP tool registration in simple_server.py
- [ ] Business logic implementation in tools.py
- [ ] Unit tests for all code paths
- [ ] Integration tests with real Things 3
- [ ] Documentation updates (tutorial, API reference)
- [ ] Performance testing with large datasets
- [ ] Security review for input sanitization

## Pull Request Requirements
- [ ] All tests passing
- [ ] Code follows existing patterns
- [ ] Documentation updated
- [ ] Performance benchmarks included
- [ ] Security considerations addressed
- [ ] Backward compatibility maintained

---

*Last Updated: August 2025*
*Current Version: 1.1.0 (move_record implemented)*
*Next Target: 1.5.0 (Critical features complete)*