# SPARC Plan: Simplified Hybrid Implementation

## 1. SPECIFICATION

### 1.1 Core Requirements
- Use things.py for ALL read operations
- Use AppleScript for ALL write operations
- Remove all caching (not needed with direct DB access)
- No fallback mechanisms - trust things.py
- Clean, simple implementation

### 1.2 Success Criteria
- `get_tags()` returns instantly (< 100ms)
- All read operations are at least 10x faster
- Code is simpler and more maintainable
- No more timeout issues

### 1.3 Assumptions
- things.py is reliable and mature
- Things 3 paid version only
- Direct database access is always available
- No backward compatibility requirements

## 2. PSEUDOCODE

### 2.1 Core Logic (Simple)
```
FUNCTION get_tags(include_items):
    tags = things.tags()
    result = []
    
    FOR each tag in tags:
        tag_dict = {
            'id': tag.uuid,
            'name': tag.title,
            'uuid': tag.uuid
        }
        
        IF include_items:
            tag_dict['items'] = things.todos(tag=tag.title)
        ELSE:
            # Just count - super fast with SQL
            tag_dict['item_count'] = len(things.todos(tag=tag.title))
        
        result.append(tag_dict)
    
    RETURN result

FUNCTION get_todos(project_id=None):
    IF project_id:
        todos = things.todos(project=project_id)
    ELSE:
        todos = things.todos()
    
    RETURN [convert_todo(t) for t in todos]

FUNCTION add_todo(title, notes, tags, when, ...):
    # Still use AppleScript for writes
    script = build_applescript_add(title, notes, tags, when)
    RETURN execute_applescript(script)

FUNCTION update_todo(todo_id, changes):
    # Still use AppleScript for updates
    script = build_applescript_update(todo_id, changes)
    RETURN execute_applescript(script)
```

## 3. ARCHITECTURE

### 3.1 Simplified Architecture
```
┌─────────────────────────────────────────┐
│         MCP Server Interface            │
├─────────────────────────────────────────┤
│           HybridTools                   │
│                                         │
│  Read Operations    Write Operations   │
│        ↓                    ↓           │
│   things.py          AppleScriptMgr    │
│        ↓                    ↓           │
│  SQLite Database      Things 3 App     │
└─────────────────────────────────────────┘
```

### 3.2 Class Structure (Simple)
```python
class HybridTools:
    def __init__(self, applescript_manager):
        self.applescript = applescript_manager
        # No caching, no fallback, no monitoring
    
    # Read operations - Direct to things.py
    async def get_todos(self, **filters) -> List[Dict]
    async def get_projects(self) -> List[Dict]
    async def get_areas(self) -> List[Dict]
    async def get_tags(self, include_items=False) -> List[Dict]
    async def search_todos(self, query: str) -> List[Dict]
    async def get_inbox(self) -> List[Dict]
    async def get_today(self) -> List[Dict]
    async def get_upcoming(self) -> List[Dict]
    
    # Write operations - Still AppleScript
    async def add_todo(self, **kwargs) -> Dict
    async def update_todo(self, todo_id: str, **kwargs) -> Dict
    async def delete_todo(self, todo_id: str) -> Dict
    async def move_todo(self, todo_id: str, destination: str) -> Dict
```

## 4. REFINEMENT

### 4.1 Data Conversion
```python
def convert_todo(things_todo: Dict) -> Dict:
    """Convert things.py format to MCP format."""
    return {
        'id': things_todo.get('uuid'),
        'title': things_todo.get('title'),
        'notes': things_todo.get('notes'),
        'status': things_todo.get('status'),
        'tags': things_todo.get('tags', []),
        'created': things_todo.get('created'),
        'modified': things_todo.get('modified'),
        'when': things_todo.get('start_date'),
        'deadline': things_todo.get('deadline'),
        'completed': things_todo.get('stop_date'),
        'project': things_todo.get('project'),
        'area': things_todo.get('area'),
        'checklist': things_todo.get('checklist_items', [])
    }

def convert_project(things_project: Dict) -> Dict:
    """Convert things.py project to MCP format."""
    return {
        'id': things_project.get('uuid'),
        'title': things_project.get('title'),
        'notes': things_project.get('notes'),
        'tags': things_project.get('tags', []),
        'area': things_project.get('area'),
        'status': things_project.get('status'),
        'items': things_project.get('items', [])
    }
```

### 4.2 Testing Strategy (Simple)
```python
# test_hybrid_simple.py
def test_get_tags_fast():
    """Verify tags return quickly."""
    start = time.time()
    tags = hybrid.get_tags(include_items=False)
    elapsed = time.time() - start
    
    assert elapsed < 0.5  # Should be instant
    assert len(tags) > 0
    assert all('item_count' in tag for tag in tags)

def test_get_todos_with_project():
    """Test filtered todo retrieval."""
    project_id = "some-project-uuid"
    todos = hybrid.get_todos(project_id=project_id)
    
    assert all(t['project'] == project_id for t in todos)

def test_add_todo_still_works():
    """Verify write operations still use AppleScript."""
    result = hybrid.add_todo(
        title="Test Todo",
        notes="Test notes"
    )
    assert result['success']
    assert 'id' in result
```

## 5. CODE

### 5.1 Complete Implementation
```python
# hybrid_tools.py
import things
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime

class HybridTools:
    """
    Simple hybrid implementation:
    - Read from things.py (fast)
    - Write with AppleScript (full control)
    - No caching, no fallback, no complexity
    """
    
    def __init__(self, applescript_manager):
        self.applescript = applescript_manager
    
    # ========== READ OPERATIONS (things.py) ==========
    
    async def get_todos(self, project_id: Optional[str] = None) -> List[Dict]:
        """Get todos directly from database."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_todos_sync, project_id)
    
    def _get_todos_sync(self, project_id: Optional[str] = None) -> List[Dict]:
        if project_id:
            todos = things.todos(project=project_id)
        else:
            todos = things.todos()
        
        return [self._convert_todo(t) for t in todos]
    
    async def get_projects(self) -> List[Dict]:
        """Get all projects."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_projects_sync)
    
    def _get_projects_sync(self) -> List[Dict]:
        projects = things.projects()
        return [self._convert_project(p) for p in projects]
    
    async def get_areas(self) -> List[Dict]:
        """Get all areas."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_areas_sync)
    
    def _get_areas_sync(self) -> List[Dict]:
        areas = things.areas()
        return [self._convert_area(a) for a in areas]
    
    async def get_tags(self, include_items: bool = False) -> List[Dict]:
        """Get all tags with counts or items."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_tags_sync, include_items)
    
    def _get_tags_sync(self, include_items: bool) -> List[Dict]:
        tags = things.tags()
        result = []
        
        for tag in tags:
            tag_dict = {
                'id': tag.get('uuid', ''),
                'uuid': tag.get('uuid', ''),
                'name': tag.get('title', ''),
                'title': tag.get('title', '')
            }
            
            if include_items:
                # Get actual items for this tag
                tagged_todos = things.todos(tag=tag['title'])
                tag_dict['items'] = [self._convert_todo(t) for t in tagged_todos]
            else:
                # Just count - this is instant with SQL
                tagged_todos = things.todos(tag=tag['title'])
                tag_dict['item_count'] = len(list(tagged_todos))
            
            result.append(tag_dict)
        
        return result
    
    async def search_todos(self, query: str) -> List[Dict]:
        """Search todos."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._search_sync, query)
    
    def _search_sync(self, query: str) -> List[Dict]:
        results = things.search(query)
        return [self._convert_todo(t) for t in results]
    
    async def get_inbox(self) -> List[Dict]:
        """Get inbox items."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_inbox_sync)
    
    def _get_inbox_sync(self) -> List[Dict]:
        todos = things.inbox()
        return [self._convert_todo(t) for t in todos]
    
    async def get_today(self) -> List[Dict]:
        """Get today items."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_today_sync)
    
    def _get_today_sync(self) -> List[Dict]:
        todos = things.today()
        return [self._convert_todo(t) for t in todos]
    
    async def get_upcoming(self) -> List[Dict]:
        """Get upcoming items."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_upcoming_sync)
    
    def _get_upcoming_sync(self) -> List[Dict]:
        todos = things.upcoming()
        return [self._convert_todo(t) for t in todos]
    
    async def get_anytime(self) -> List[Dict]:
        """Get anytime items."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_anytime_sync)
    
    def _get_anytime_sync(self) -> List[Dict]:
        todos = things.anytime()
        return [self._convert_todo(t) for t in todos]
    
    async def get_someday(self) -> List[Dict]:
        """Get someday items."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_someday_sync)
    
    def _get_someday_sync(self) -> List[Dict]:
        todos = things.someday()
        return [self._convert_todo(t) for t in todos]
    
    async def get_logbook(self) -> List[Dict]:
        """Get completed items."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_logbook_sync)
    
    def _get_logbook_sync(self) -> List[Dict]:
        todos = things.logbook()
        return [self._convert_todo(t) for t in todos]
    
    async def get_trash(self) -> List[Dict]:
        """Get trashed items."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_trash_sync)
    
    def _get_trash_sync(self) -> List[Dict]:
        todos = things.trash()
        return [self._convert_todo(t) for t in todos]
    
    # ========== WRITE OPERATIONS (AppleScript) ==========
    
    async def add_todo(self, title: str, **kwargs) -> Dict:
        """Add a new todo using AppleScript."""
        # Build and execute AppleScript
        script = self._build_add_todo_script(title, **kwargs)
        result = await self.applescript.execute_applescript(script)
        return self._parse_add_result(result)
    
    async def update_todo(self, todo_id: str, **kwargs) -> Dict:
        """Update a todo using AppleScript."""
        script = self._build_update_todo_script(todo_id, **kwargs)
        result = await self.applescript.execute_applescript(script)
        return self._parse_update_result(result)
    
    async def delete_todo(self, todo_id: str) -> Dict:
        """Delete a todo using AppleScript."""
        script = f'''
        tell application "Things3"
            set targetTodo to to do id "{todo_id}"
            delete targetTodo
            return "deleted"
        end tell
        '''
        result = await self.applescript.execute_applescript(script)
        return {'success': result.get('success', False)}
    
    async def complete_todo(self, todo_id: str) -> Dict:
        """Complete a todo using AppleScript."""
        script = f'''
        tell application "Things3"
            set targetTodo to to do id "{todo_id}"
            set status of targetTodo to completed
            return "completed"
        end tell
        '''
        result = await self.applescript.execute_applescript(script)
        return {'success': result.get('success', False)}
    
    async def move_todo(self, todo_id: str, destination: str) -> Dict:
        """Move a todo using AppleScript."""
        script = self._build_move_script(todo_id, destination)
        result = await self.applescript.execute_applescript(script)
        return {'success': result.get('success', False)}
    
    # ========== CONVERSION HELPERS ==========
    
    def _convert_todo(self, todo: Dict) -> Dict:
        """Convert things.py todo to our format."""
        return {
            'id': todo.get('uuid', ''),
            'uuid': todo.get('uuid', ''),
            'title': todo.get('title', ''),
            'notes': todo.get('notes', ''),
            'status': todo.get('status', 'open'),
            'tags': todo.get('tags', []),
            'created': todo.get('created', ''),
            'modified': todo.get('modified', ''),
            'when': todo.get('start_date', ''),
            'deadline': todo.get('deadline', ''),
            'completed': todo.get('stop_date', ''),
            'project': todo.get('project', ''),
            'area': todo.get('area', ''),
            'heading': todo.get('heading', ''),
            'checklist': todo.get('checklist_items', [])
        }
    
    def _convert_project(self, project: Dict) -> Dict:
        """Convert things.py project to our format."""
        return {
            'id': project.get('uuid', ''),
            'uuid': project.get('uuid', ''),
            'title': project.get('title', ''),
            'notes': project.get('notes', ''),
            'tags': project.get('tags', []),
            'area': project.get('area', ''),
            'status': project.get('status', 'open')
        }
    
    def _convert_area(self, area: Dict) -> Dict:
        """Convert things.py area to our format."""
        return {
            'id': area.get('uuid', ''),
            'uuid': area.get('uuid', ''),
            'title': area.get('title', ''),
            'tags': area.get('tags', [])
        }
    
    # ========== APPLESCRIPT BUILDERS ==========
    
    def _build_add_todo_script(self, title: str, **kwargs) -> str:
        """Build AppleScript for adding a todo."""
        # Implementation from existing code
        notes = kwargs.get('notes', '')
        when = kwargs.get('when', '')
        tags = kwargs.get('tags', [])
        
        script = f'''
        tell application "Things3"
            set newTodo to make new to do with properties {{name:"{title}"}}
            '''
        
        if notes:
            script += f'\nset notes of newTodo to "{notes}"'
        
        if when:
            script += f'\nset activation date of newTodo to date "{when}"'
        
        if tags:
            for tag in tags:
                script += f'\nset tag names of newTodo to tag names of newTodo & "{tag}"'
        
        script += '''
            return id of newTodo
        end tell
        '''
        
        return script
    
    def _build_update_todo_script(self, todo_id: str, **kwargs) -> str:
        """Build AppleScript for updating a todo."""
        script = f'''
        tell application "Things3"
            set targetTodo to to do id "{todo_id}"
            '''
        
        if 'title' in kwargs:
            script += f'\nset name of targetTodo to "{kwargs["title"]}"'
        
        if 'notes' in kwargs:
            script += f'\nset notes of targetTodo to "{kwargs["notes"]}"'
        
        if 'completed' in kwargs and kwargs['completed']:
            script += '\nset status of targetTodo to completed'
        
        script += '''
            return "updated"
        end tell
        '''
        
        return script
    
    def _build_move_script(self, todo_id: str, destination: str) -> str:
        """Build AppleScript for moving a todo."""
        return f'''
        tell application "Things3"
            set targetTodo to to do id "{todo_id}"
            move targetTodo to list "{destination}"
            return "moved"
        end tell
        '''
    
    def _parse_add_result(self, result: Dict) -> Dict:
        """Parse AppleScript add result."""
        if result.get('success'):
            return {
                'success': True,
                'id': result.get('output', '').strip()
            }
        return {'success': False, 'error': result.get('error')}
    
    def _parse_update_result(self, result: Dict) -> Dict:
        """Parse AppleScript update result."""
        return {'success': result.get('success', False)}
```

### 5.2 Server Integration
```python
# server.py updates
from things_mcp.hybrid_tools import HybridTools

class ThingsMCPServer:
    def __init__(self):
        # Remove cache manager - not needed
        self.applescript = AppleScriptManager()
        self.tools = HybridTools(self.applescript)
    
    def register_tools(self):
        # Same tool registrations, but now using hybrid
        @self.mcp.tool()
        async def get_tags(include_items: bool = False):
            """Get tags - now super fast!"""
            return await self.tools.get_tags(include_items)
        
        @self.mcp.tool()
        async def get_todos(project_id: Optional[str] = None):
            """Get todos - no more timeouts!"""
            return await self.tools.get_todos(project_id)
        
        # ... rest of tools
```

## 6. MIGRATION STEPS

1. **Install things.py**
   ```bash
   pip install things.py
   ```

2. **Replace tools.py with hybrid_tools.py**
   - Remove all caching code
   - Remove all AppleScript read operations
   - Keep AppleScript write operations

3. **Update server.py**
   - Remove cache manager
   - Use HybridTools instead of ThingsTools

4. **Test everything**
   ```bash
   pytest tests/
   ```

5. **Deploy**
   - No configuration needed
   - No feature flags
   - Just works

## 7. EXPECTED RESULTS

- `get_tags()`: 30-60s → <0.1s ✅
- `get_todos()`: 5-10s → <0.2s ✅
- `search()`: 2-5s → <0.1s ✅
- No timeouts ever ✅
- Simpler code ✅
- No caching complexity ✅