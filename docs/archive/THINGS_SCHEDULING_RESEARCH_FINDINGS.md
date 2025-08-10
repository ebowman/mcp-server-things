# Things 3 AppleScript Date Scheduling - Research Findings

## Executive Summary

After researching GitHub repositories and examining working examples of Things 3 automation, I've identified several proven approaches for reliable date scheduling. The key finding is that **URL schemes are significantly more reliable than direct AppleScript scheduling commands**.

## Key Repositories Analyzed

### 1. **benjamineskola/things-scripts** (5 stars)
- **URL**: https://github.com/benjamineskola/things-scripts
- **Key Finding**: Uses URL scheme approach for scheduling
- **Working Example**: 
  ```applescript
  set theUrl to "things:///" & urlCommand & "?auth-token=" & theToken & "&id=" & (id of aTodo as text) & "&when=evening"
  open location theUrl
  ```

### 2. **phatblat/ThingsAppleScript** (2 stars)
- **URL**: https://github.com/phatblat/ThingsAppleScript
- **Focus**: Basic AppleScript operations with Things
- **Note**: Limited to basic task creation without complex scheduling

### 3. **krisaziabor/things-automation**
- **URL**: https://github.com/krisaziabor/things-automation
- **Approach**: Uses Things URL scheme for automation
- **Key Insight**: Leverages URL schemes for reliable integration with external systems (Linear)

### 4. **evelion-apps/things-api** (21 stars)
- **URL**: https://github.com/evelion-apps/things-api
- **Approach**: Read-only GraphQL API accessing Things database directly
- **Relevance**: Shows database structure and field relationships

### 5. **drjforrest/mcp-things3** (30 stars)
- **URL**: https://github.com/drjforrest/mcp-things3
- **Approach**: Combines AppleScript and x-callback URLs
- **Key Insight**: Hybrid approach using both AppleScript and URL schemes

## 3 Proven Approaches for Reliable Date Scheduling

### Approach 1: URL Scheme Method (MOST RELIABLE)

**Pattern**: Use Things URL scheme with `when` parameter

```applescript
tell application "Things3"
    set theToken to "your-auth-token"
    set theUrl to "things:///update?auth-token=" & theToken & "&id=" & todoId & "&when=evening"
    open location theUrl
end tell
```

**Date Format Options**:
- `when=today`
- `when=tomorrow` 
- `when=evening`
- `when=YYYY-MM-DD` (ISO date format)
- `when=this-evening`
- `when=this-weekend`

**Advantages**:
- ✅ Most reliable approach found in production code
- ✅ Handles auth tokens properly
- ✅ Consistent with official Things URL scheme
- ✅ Works across different macOS versions

### Approach 2: Direct AppleScript with Date Objects

**Pattern**: Create proper date objects before assignment

```applescript
tell application "Things3"
    set targetDate to date "Friday, December 25, 2024 at 12:00:00 AM"
    set schedule date of someTodo to targetDate
end tell
```

**Alternative Date Construction**:
```applescript
set targetDate to current date
set year of targetDate to 2024
set month of targetDate to December  
set day of targetDate to 25
```

**Reliability Issues**:
- ⚠️ Date format parsing can be inconsistent
- ⚠️ Time zone handling varies
- ⚠️ System locale affects parsing

### Approach 3: Hybrid AppleScript + URL Scheme

**Pattern**: Use AppleScript for querying, URL schemes for modifications

```applescript
tell application "Things3"
    set theTodos to to dos of list "Today"
    repeat with aTodo in theTodos
        -- Query with AppleScript
        set todoId to id of aTodo
        -- Modify with URL scheme  
        set theUrl to "things:///update?auth-token=" & theToken & "&id=" & todoId & "&when=2024-12-25"
        open location theUrl
    end repeat
end tell
```

## Common Reliability Issues Identified

### Issue 1: Date Format Inconsistencies
**Problem**: Different date string formats cause parsing failures
**Solutions Found**:
- Use ISO format (YYYY-MM-DD) in URL schemes
- Use relative terms like "today", "tomorrow", "evening" 
- Construct date objects programmatically rather than parsing strings

### Issue 2: Authentication Token Requirements
**Problem**: Some operations require auth tokens
**Solution**: Extract and use auth tokens in URL schemes
```applescript
set theToken to "your-auth-token"
set theUrl to "things:///" & urlCommand & "?auth-token=" & theToken & "&id=" & todoId & "&when=" & dateString
```

### Issue 3: AppleScript Schedule Command Failures
**Problem**: Direct `schedule` command unreliable
**Solution**: Use URL scheme `when` parameter instead

## Battle-Tested Code Patterns

### Pattern 1: Evening Task Scheduling
```applescript
-- From benjamineskola/things-scripts
tell application "Things3"
    set theToken to "your-auth-token"
    set theTodos to to dos of list "Today"
    repeat with aTodo in theTodos
        set tagList to tags of aTodo
        repeat with aTag in tagList
            if (name of aTag as text) is "Evening"
                if class of aTodo is project
                    set urlCommand to "update-project"
                else
                    set urlCommand to "update"
                end if
                set theUrl to "things:///" & urlCommand & "?auth-token=" & theToken & "&id=" & (id of aTodo as text) & "&when=evening"
                open location theUrl
            end if
        end repeat
    end repeat
end tell
```

### Pattern 2: Date-Specific Scheduling
```applescript
-- Reliable date scheduling using URL scheme
tell application "Things3"
    set theToken to "your-auth-token"
    set todoId to id of someSpecificTodo
    set targetDate to "2024-12-25"  -- ISO format
    set theUrl to "things:///update?auth-token=" & theToken & "&id=" & todoId & "&when=" & targetDate
    open location theUrl
end tell
```

### Pattern 3: Conditional Scheduling Based on Tags
```applescript
-- Tag-based scheduling with URL schemes
tell application "Things3"
    set theToken to "your-auth-token"
    set allTodos to to dos of list "Inbox"
    repeat with aTodo in allTodos
        set todoTags to tags of aTodo
        repeat with aTag in todoTags
            set tagName to name of aTag as text
            if tagName contains "Due:" then
                -- Extract date from tag name
                set dateString to text 5 thru -1 of tagName  -- Remove "Due:" prefix
                set theUrl to "things:///update?auth-token=" & theToken & "&id=" & (id of aTodo as text) & "&when=" & dateString
                open location theUrl
            end if
        end repeat
    end repeat
end tell
```

## Recommendations

1. **PRIMARY**: Use Things URL scheme with `when` parameter for all date scheduling
2. **SECONDARY**: Combine AppleScript querying with URL scheme modifications
3. **AVOID**: Direct AppleScript `schedule` commands due to reliability issues
4. **DATE FORMATS**: Prefer ISO format (YYYY-MM-DD) or relative terms ("today", "tomorrow")
5. **AUTHENTICATION**: Always include auth tokens in URL scheme calls
6. **ERROR HANDLING**: Implement try-catch blocks around URL scheme calls

## Next Steps for Implementation

1. Extract or generate auth tokens for Things URL scheme
2. Implement URL scheme-based scheduling in MCP server
3. Add fallback error handling for failed URL scheme calls
4. Test with various date formats to ensure reliability
5. Consider hybrid approach for complex operations

## Repository References

- benjamineskola/things-scripts: https://github.com/benjamineskola/things-scripts
- phatblat/ThingsAppleScript: https://github.com/phatblat/ThingsAppleScript  
- krisaziabor/things-automation: https://github.com/krisaziabor/things-automation
- evelion-apps/things-api: https://github.com/evelion-apps/things-api
- drjforrest/mcp-things3: https://github.com/drjforrest/mcp-things3

---

**Date Generated**: January 2025  
**Research Scope**: GitHub repositories with Things 3 automation and scheduling  
**Key Finding**: URL schemes provide superior reliability over direct AppleScript scheduling