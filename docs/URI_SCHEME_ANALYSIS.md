# Things URI Scheme vs AppleScript Analysis

## Issue
When using Things URI schemes, if an item doesn't exist (e.g., wrong ID), Things shows a modal dialog to the user. This is poor UX and breaks automation flow.

## Current URI Scheme Usage

After analyzing the codebase, the following operations still use Things URI schemes (`things:///`):

### 1. **add_todo** (`execute_url_scheme("add", params)`)
- Location: `tools.py:229`
- Current: Uses URI scheme for creating todos
- **Can be replaced**: YES - AppleScript can create todos with all properties

### 2. **update_todo** (`execute_url_scheme("update", params)`)
- Location: `tools.py:354`
- Current: Uses URI scheme for updating todos
- **Can be replaced**: YES - AppleScript can update all todo properties
- **Issue**: This is likely causing the modal dialog when ID doesn't exist

### 3. **add_project** (`execute_url_scheme("add-project", params)`)
- Location: `tools.py:556`
- Current: Uses URI scheme for creating projects
- **Can be replaced**: YES - AppleScript can create projects

### 4. **update_project** (`execute_url_scheme("update", params)`)
- Location: `tools.py:626`
- Current: Uses URI scheme for updating projects
- **Can be replaced**: YES - AppleScript can update projects
- **Issue**: This is causing the modal dialog for "Website Redesign" project

## Operations Already Using AppleScript

✅ **get_todo_by_id** - Uses AppleScript
✅ **delete_todo** - Uses AppleScript  
✅ **get_todos** - Uses AppleScript
✅ **get_projects** - Uses AppleScript
✅ **get_areas** - Uses AppleScript
✅ **get_tags** - Uses AppleScript
✅ **add_tags** - Uses AppleScript
✅ **remove_tags** - Uses AppleScript
✅ **search_todos** - Uses AppleScript

## Problems with URI Schemes

1. **Modal Dialogs**: Shows error dialogs when items don't exist
2. **Limited Error Handling**: Can't gracefully handle missing items
3. **No Return Values**: Can't get the created item's ID
4. **Limited Validation**: Can't check if item exists before updating
5. **UI Disruption**: Opens Things app and changes focus

## Recommended Solution

Replace ALL remaining URI scheme usage with AppleScript:

### 1. Replace `add_todo` with AppleScript
```applescript
tell application "Things3"
    set newTodo to make new to do with properties {name:"Title", notes:"Notes"}
    if tags exist then
        repeat with tagName in tags
            set tag tagName of newTodo to tagName
        end repeat
    end if
    return id of newTodo
end tell
```

### 2. Replace `update_todo` with AppleScript
```applescript
tell application "Things3"
    try
        set theTodo to to do id "ID"
        set name of theTodo to "New Title"
        set notes of theTodo to "New Notes"
        -- Update other properties
        return "success"
    on error
        return "error: Todo not found"
    end try
end tell
```

### 3. Replace `add_project` with AppleScript
```applescript
tell application "Things3"
    set newProject to make new project with properties {name:"Title", notes:"Notes"}
    -- Add todos to project
    repeat with todoTitle in todos
        make new to do with properties {name:todoTitle} at newProject
    end repeat
    return id of newProject
end tell
```

### 4. Replace `update_project` with AppleScript
```applescript
tell application "Things3"
    try
        set theProject to project id "ID"
        set name of theProject to "New Title"
        -- Update other properties
        return "success"
    on error
        return "error: Project not found"
    end try
end tell
```

## Benefits of Full AppleScript Migration

1. **Better Error Handling**: Graceful failures with try/catch
2. **No Modal Dialogs**: Silent failures that can be logged
3. **Return Values**: Get IDs of created items
4. **Validation**: Check existence before operations
5. **No UI Disruption**: Operations happen in background
6. **More Control**: Direct access to all Things properties
7. **Consistency**: All operations use same approach

## Implementation Priority

1. **HIGH**: `update_todo` and `update_project` - These are causing modal dialogs
2. **MEDIUM**: `add_todo` and `add_project` - For consistency and better return values
3. **LOW**: Remove URL scheme building code after migration

## Testing Requirements

After migration, test:
- Creating todos/projects with all properties
- Updating non-existent items (should fail gracefully)
- Tag creation and application
- Date parsing and assignment
- Checklist item creation
- Project hierarchy (areas, headings)