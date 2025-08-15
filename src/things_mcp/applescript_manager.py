"""AppleScript manager for Things 3 integration."""

import asyncio
import logging
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote
import re

from .shared_cache import get_shared_cache
from .locale_aware_dates import locale_handler

logger = logging.getLogger(__name__)


class AppleScriptManager:
    """Manages AppleScript execution and Things URL schemes.
    
    This class implements process-level locking to prevent race conditions when
    multiple AppleScript commands are executed concurrently. The lock ensures
    that only one AppleScript executes at a time, preventing potential conflicts
    and ensuring reliable operation with Things 3.
    
    The lock is shared across all instances of AppleScriptManager to provide
    true process-level serialization.
    """
    
    # Class-level lock shared across all instances to prevent race conditions
    # This ensures only one AppleScript command executes at a time across the entire process
    _applescript_lock = asyncio.Lock()
    
    def __init__(self, timeout: int = 45, retry_count: int = 3):
        """Initialize the AppleScript manager.
        
        Args:
            timeout: Command timeout in seconds
            retry_count: Number of retries for failed commands
        """
        self.timeout = timeout
        self.retry_count = retry_count
        self._cache = get_shared_cache(default_ttl=30.0)  # Use shared cache with 30 second TTL
        self.auth_token = self._load_auth_token()
        logger.info("AppleScript manager initialized with shared cache")
    
    def _load_auth_token(self) -> Optional[str]:
        """Load Things auth token from file if it exists."""
        auth_files = [
            Path(__file__).parent.parent.parent / '.things-auth',
            Path(__file__).parent.parent.parent / 'things-auth.txt',
            Path.home() / '.things-auth'
        ]
        
        for auth_file in auth_files:
            if auth_file.exists():
                try:
                    token = auth_file.read_text().strip()
                    # Handle format: THINGS_AUTH_TOKEN=xxx or just xxx
                    if '=' in token:
                        token = token.split('=', 1)[1].strip()
                    logger.info(f"Loaded Things auth token from {auth_file}")
                    return token
                except Exception as e:
                    logger.warning(f"Failed to read auth token from {auth_file}: {e}")
        
        logger.warning("No Things auth token found. Some operations may require manual authorization.")
        return None
    
    async def is_things_running(self) -> bool:
        """Check if Things 3 is currently running."""
        try:
            script = 'tell application "Things3" to return true'
            result = await self._execute_script(script)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Error checking Things 3 status: {e}")
            return False
    
    async def execute_applescript(self, script: str, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """Execute an AppleScript command.
        
        Args:
            script: AppleScript code to execute
            cache_key: Optional cache key for result caching
            
        Returns:
            Dict with success status, output, and error information
        """
        # Check cache first
        if cache_key:
            cached_result = self._cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_result
        
        result = await self._execute_script_with_retry(script)
        
        # OPTIMIZATION: Cache successful results with granular invalidation strategy
        # Don't cache mutation operations but do cache read-only queries
        if cache_key and result.get("success") and not any(x in cache_key for x in ['search', 'add', 'update', 'delete', 'move', 'complete']):
            self._cache.set(cache_key, result)
            logger.debug(f"Cached result for key: {cache_key}")
        
        return result
    
    async def execute_url_scheme(self, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a Things URL scheme command.
        
        Args:
            action: Things URL action (add, update, show, etc.)
            parameters: Optional parameters for the action
            
        Returns:
            Dict with success status and result information
        """
        try:
            url = self._build_things_url(action, parameters or {})
            # Use do shell script with open -g to avoid bringing Things to foreground
            script = f'''do shell script "open -g '{url}'"'''
            
            result = await self._execute_script(script)
            
            # For URL schemes, success is usually indicated by no error
            if result.get("success"):
                return {
                    "success": True,
                    "url": url,
                    "message": f"Successfully executed {action} action"
                }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown error"),
                    "url": url
                }
        
        except Exception as e:
            logger.error(f"Error executing URL scheme: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def get_todos(self, project_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get todos from Things 3 using optimized batch property retrieval.
        
        Args:
            project_uuid: Optional project UUID to filter by
            
        Returns:
            List of todo dictionaries
        """
        try:
            if project_uuid:
                script = f'''
                on replaceText(someText, oldText, newText)
                    set AppleScript's text item delimiters to oldText
                    set textItems to text items of someText
                    set AppleScript's text item delimiters to newText
                    set newText to textItems as string
                    set AppleScript's text item delimiters to {{}}
                    return newText
                end replaceText
                
                tell application "Things3"
                    set theProject to project id "{project_uuid}"
                    set todoSource to to dos of theProject
                    
                    -- Check if there are any todos
                    if length of todoSource = 0 then
                        return ""
                    end if
                    
                    -- Optimized: Build output directly without intermediate arrays
                    set outputText to ""
                    repeat with theTodo in todoSource
                        if outputText is not "" then
                            set outputText to outputText & ", "
                        end if
                        
                        -- Handle date conversion properly
                        set creationDateStr to ""
                        try
                            set creationDateStr to ((creation date of theTodo) as string)
                        on error
                            set creationDateStr to "missing value"
                        end try
                        
                        set modificationDateStr to ""
                        try
                            set modificationDateStr to ((modification date of theTodo) as string)
                        on error
                            set modificationDateStr to "missing value"
                        end try
                        
                        -- Handle notes which might contain commas
                        set noteStr to ""
                        try
                            set noteStr to (notes of theTodo)
                            -- Replace commas in notes to avoid parsing issues
                            set noteStr to my replaceText(noteStr, ",", "§COMMA§")
                        on error
                            set noteStr to "missing value"
                        end try
                        
                        set outputText to outputText & "id:" & (id of theTodo) & ", name:" & (name of theTodo) & ", notes:" & noteStr & ", status:" & (status of theTodo) & ", creation_date:" & creationDateStr & ", modification_date:" & modificationDateStr
                    end repeat
                    
                    return outputText
                end tell
                '''
            else:
                script = '''
                on replaceText(someText, oldText, newText)
                    set AppleScript's text item delimiters to oldText
                    set textItems to text items of someText
                    set AppleScript's text item delimiters to newText
                    set newText to textItems as string
                    set AppleScript's text item delimiters to {}
                    return newText
                end replaceText
                
                tell application "Things3"
                    set todoSource to to dos
                    
                    -- Check if there are any todos
                    if length of todoSource = 0 then
                        return ""
                    end if
                    
                    -- Optimized: Build output directly without intermediate arrays
                    set outputText to ""
                    repeat with theTodo in todoSource
                        if outputText is not "" then
                            set outputText to outputText & ", "
                        end if
                        
                        -- Handle date conversion properly
                        set creationDateStr to ""
                        try
                            set creationDateStr to ((creation date of theTodo) as string)
                        on error
                            set creationDateStr to "missing value"
                        end try
                        
                        set modificationDateStr to ""
                        try
                            set modificationDateStr to ((modification date of theTodo) as string)
                        on error
                            set modificationDateStr to "missing value"
                        end try
                        
                        -- Handle notes which might contain commas
                        set noteStr to ""
                        try
                            set noteStr to (notes of theTodo)
                            -- Replace commas in notes to avoid parsing issues
                            set noteStr to my replaceText(noteStr, ",", "§COMMA§")
                        on error
                            set noteStr to "missing value"
                        end try
                        
                        set outputText to outputText & "id:" & (id of theTodo) & ", name:" & (name of theTodo) & ", notes:" & noteStr & ", status:" & (status of theTodo) & ", creation_date:" & creationDateStr & ", modification_date:" & modificationDateStr
                    end repeat
                    
                    return outputText
                end tell
                '''
            
            cache_key = f"todos_{project_uuid or 'all'}"
            result = await self.execute_applescript(script, cache_key)
            
            if result.get("success"):
                try:
                    return self._parse_applescript_list(result.get("output", ""))
                except ValueError as e:
                    logger.error(f"Failed to parse todos: {e}")
                    raise
            else:
                error_msg = f"AppleScript failed to get todos: {result.get('error')}"
                logger.error(error_msg)
                raise Exception(error_msg)
        
        except Exception as e:
            logger.error(f"Error getting todos: {e}")
            raise
    
    async def get_projects(self) -> List[Dict[str, Any]]:
        """Get all projects from Things 3 using optimized batch property retrieval.
        
        Projects in Things 3 inherit from todos and have identical properties.
        This method now fetches all inherited fields to maintain proper inheritance.
        """
        try:
            script = '''
            on replaceText(someText, oldText, newText)
                set AppleScript's text item delimiters to oldText
                set textItems to text items of someText
                set AppleScript's text item delimiters to newText
                set newText to textItems as string
                set AppleScript's text item delimiters to {}
                return newText
            end replaceText
            
            tell application "Things3"
                set projectSource to projects
                
                -- Check if there are any projects
                if length of projectSource = 0 then
                    return ""
                end if
                
                -- Optimized: Build output directly without intermediate arrays
                set outputText to ""
                repeat with theProject in projectSource
                    if outputText is not "" then
                        set outputText to outputText & ", "
                    end if
                    
                    -- Handle all date fields that projects inherit from todos
                    set creationDateStr to ""
                    try
                        set creationDateStr to ((creation date of theProject) as string)
                    on error
                        set creationDateStr to "missing value"
                    end try
                    
                    set modificationDateStr to ""
                    try
                        set modificationDateStr to ((modification date of theProject) as string)
                    on error
                        set modificationDateStr to "missing value"
                    end try
                    
                    set dueDateStr to ""
                    try
                        set dueDateStr to ((due date of theProject) as string)
                    on error
                        set dueDateStr to "missing value"
                    end try
                    
                    set startDateStr to ""
                    try
                        set startDateStr to ((activation date of theProject) as string)
                    on error
                        set startDateStr to "missing value"
                    end try
                    
                    set completionDateStr to ""
                    try
                        set completionDateStr to ((completion date of theProject) as string)
                    on error
                        set completionDateStr to "missing value"
                    end try
                    
                    set cancellationDateStr to ""
                    try
                        set cancellationDateStr to ((cancellation date of theProject) as string)
                    on error
                        set cancellationDateStr to "missing value"
                    end try
                    
                    -- Handle tag names (projects can have tags)
                    set tagNamesStr to ""
                    try
                        set tagNamesStr to ((tag names of theProject) as string)
                    on error
                        set tagNamesStr to "missing value"
                    end try
                    
                    -- Handle contact (projects can have contacts)
                    set contactStr to ""
                    try
                        set contactStr to ((contact of theProject) as string)
                    on error
                        set contactStr to "missing value"
                    end try
                    
                    -- Handle area (projects can be in areas)
                    set areaStr to ""
                    try
                        set areaStr to ((area of theProject) as string)
                    on error
                        set areaStr to "missing value"
                    end try
                    
                    -- Handle parent project (projects can be sub-projects)
                    set projectStr to ""
                    try
                        set projectStr to ((project of theProject) as string)
                    on error
                        set projectStr to "missing value"
                    end try
                    
                    -- Handle notes which might contain commas
                    set noteStr to ""
                    try
                        set noteStr to (notes of theProject)
                        -- Replace commas in notes to avoid parsing issues
                        set noteStr to my replaceText(noteStr, ",", "§COMMA§")
                    on error
                        set noteStr to "missing value"
                    end try
                    
                    -- Build complete project record with all inherited todo fields
                    set outputText to outputText & "id:" & (id of theProject) & ", name:" & (name of theProject) & ", notes:" & noteStr & ", status:" & (status of theProject) & ", tag_names:" & tagNamesStr & ", creation_date:" & creationDateStr & ", modification_date:" & modificationDateStr & ", due_date:" & dueDateStr & ", start_date:" & startDateStr & ", completion_date:" & completionDateStr & ", cancellation_date:" & cancellationDateStr & ", contact:" & contactStr & ", area:" & areaStr & ", project:" & projectStr
                end repeat
                
                return outputText
            end tell
            '''
            
            result = await self.execute_applescript(script, "projects_all")
            
            if result.get("success"):
                try:
                    return self._parse_applescript_list(result.get("output", ""))
                except ValueError as e:
                    logger.error(f"Failed to parse projects: {e}")
                    raise
            else:
                error_msg = f"AppleScript failed to get projects: {result.get('error')}"
                logger.error(error_msg)
                raise Exception(error_msg)
        
        except Exception as e:
            logger.error(f"Error getting projects: {e}")
            raise
    
    async def get_areas(self) -> List[Dict[str, Any]]:
        """Get all areas from Things 3 using optimized batch property retrieval.
        
        Note: Areas in Things 3 only have 'id' and 'name' properties.
        """
        try:
            script = '''
            on replaceText(someText, oldText, newText)
                set AppleScript's text item delimiters to oldText
                set textItems to text items of someText
                set AppleScript's text item delimiters to newText
                set newText to textItems as string
                set AppleScript's text item delimiters to {}
                return newText
            end replaceText
            
            tell application "Things3"
                set areaSource to areas
                
                -- Check if there are any areas
                if length of areaSource = 0 then
                    return ""
                end if
                
                -- Optimized: Build output directly without intermediate arrays
                -- Areas in Things 3 only have id and name properties
                set outputText to ""
                repeat with theArea in areaSource
                    if outputText is not "" then
                        set outputText to outputText & ", "
                    end if
                    
                    set outputText to outputText & "id:" & (id of theArea) & ", name:" & (name of theArea)
                end repeat
                
                return outputText
            end tell
            '''
            
            result = await self.execute_applescript(script, "areas_all")
            
            if result.get("success"):
                try:
                    return self._parse_applescript_list(result.get("output", ""))
                except ValueError as e:
                    logger.error(f"Failed to parse areas: {e}")
                    raise
            else:
                error_msg = f"AppleScript failed to get areas: {result.get('error')}"
                logger.error(error_msg)
                raise Exception(error_msg)
        
        except Exception as e:
            logger.error(f"Error getting areas: {e}")
            raise
    
    async def _execute_script_with_retry(self, script: str) -> Dict[str, Any]:
        """Execute script with retry logic."""
        last_error = None
        
        for attempt in range(self.retry_count):
            result = await self._execute_script(script)
            
            if result.get("success"):
                return result
            
            last_error = result.get("error")
            
            if attempt < self.retry_count - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Script execution failed, retrying in {wait_time}s: {last_error}")
                await asyncio.sleep(wait_time)
        
        return {
            "success": False,
            "error": f"Failed after {self.retry_count} attempts: {last_error}"
        }
    
    async def _execute_script(self, script: str) -> Dict[str, Any]:
        """Execute a single AppleScript command with process-level locking.
        
        This method uses an asyncio.Lock to ensure only one AppleScript command
        executes at a time across the entire process. This prevents race conditions
        and ensures reliable operation with Things 3.
        
        The lock is acquired before starting the subprocess and held until completion.
        Lock wait times > 100ms are logged for monitoring purposes.
        
        Args:
            script: AppleScript code to execute
            
        Returns:
            Dict with success status, output/error, and execution time
        """
        lock_start_time = time.time()
        
        async with self._applescript_lock:
            # Log if we waited more than 100ms for the lock
            lock_wait_time = time.time() - lock_start_time
            if lock_wait_time > 0.1:
                logger.debug(f"AppleScript lock waited {lock_wait_time:.3f}s")
            
            try:
                execution_start = time.time()
                
                # Use asyncio subprocess to execute the AppleScript
                process = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(), 
                        timeout=self.timeout
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
                    return {
                        "success": False,
                        "error": f"Script execution timed out after {self.timeout} seconds"
                    }
                
                execution_time = time.time() - execution_start
                
                if process.returncode == 0:
                    logger.debug(f"AppleScript executed successfully in {execution_time:.3f}s")
                    return {
                        "success": True,
                        "output": stdout.decode().strip(),
                        "execution_time": execution_time
                    }
                else:
                    logger.debug(f"AppleScript failed after {execution_time:.3f}s with return code {process.returncode}")
                    return {
                        "success": False,
                        "error": stderr.decode().strip() or "Unknown AppleScript error",
                        "return_code": process.returncode
                    }
            
            except Exception as e:
                logger.error(f"AppleScript execution error: {e}")
                return {
                    "success": False,
                    "error": f"Execution error: {str(e)}"
                }
    
    def _build_things_url(self, action: str, parameters: Dict[str, Any]) -> str:
        """Build a Things URL scheme string."""
        url = f"things:///{action}"
        
        # Add auth token if available and not already in parameters
        if self.auth_token and 'auth-token' not in parameters:
            parameters = parameters.copy() if parameters else {}
            parameters['auth-token'] = self.auth_token
        
        if parameters:
            # URL encode parameters
            param_strings = []
            for key, value in parameters.items():
                if value is not None:
                    if isinstance(value, list):
                        value = ",".join(str(v) for v in value)
                    param_strings.append(f"{key}={quote(str(value))}")
            
            if param_strings:
                url += "?" + "&".join(param_strings)
        
        return url
    
    
    def _parse_applescript_list(self, output: str) -> List[Dict[str, Any]]:
        """Parse AppleScript list output into Python dictionaries.
        
        Parses AppleScript record format like:
        id:todo1, name:First Todo, notes:Notes 1, status:open, id:todo2, name:Second Todo, notes:Notes 2, status:completed
        
        Raises:
            ValueError: If the output is empty or cannot be parsed
            Exception: For other parsing errors
        """
        if not output or not output.strip():
            logger.warning("AppleScript returned empty output")
            return []  # Return empty list for empty output, don't raise error
            
        logger.debug(f"AppleScript output to parse: {output}")
        
        try:
            # Parse the output - special handling for tag_names which can contain commas
            records = []
            current_record = {}
            
            # First, let's handle tag_names specially since it can contain commas
            # Strategy: find tag_names: and extract value until we hit another known field
            temp_output = output.strip()
            
            # Known field names that can follow tag_names
            known_fields = ['creation_date:', 'modification_date:', 'due_date:', 'status:', 
                          'notes:', 'id:', 'name:', 'area:', 'project:', 'start_date:', 
                          'completion_date:', 'cancellation_date:', 'contact:']
            
            # Find tag_names and protect its commas
            if 'tag_names:' in temp_output:
                start_idx = temp_output.find('tag_names:') + len('tag_names:')
                
                # Find the next field after tag_names
                end_idx = len(temp_output)  # Default to end of string
                for field in known_fields:
                    field_idx = temp_output.find(field, start_idx)
                    if field_idx != -1 and field_idx < end_idx:
                        # Found a field that comes after tag_names
                        # Back up to the comma before this field
                        comma_idx = temp_output.rfind(',', start_idx, field_idx)
                        if comma_idx != -1:
                            end_idx = comma_idx
                        else:
                            end_idx = field_idx
                
                # Extract and protect the tag value
                tag_value = temp_output[start_idx:end_idx].strip()
                if tag_value:
                    protected_value = tag_value.replace(',', '§COMMA§')
                    temp_output = temp_output[:start_idx] + protected_value + temp_output[end_idx:]
            
            # Also protect commas in date fields which contain "date Thursday, 4. September 2025 at 00:00:00"
            for date_field in ['creation_date:', 'modification_date:', 'due_date:', 'start_date:', 'completion_date:', 'cancellation_date:']:
                if date_field in temp_output:
                    # Find all instances of this date field
                    field_start = 0
                    while True:
                        field_idx = temp_output.find(date_field, field_start)
                        if field_idx == -1:
                            break
                            
                        start_idx = field_idx + len(date_field)
                        
                        # Find the next field or end of this date value
                        end_idx = len(temp_output)
                        for field in known_fields:
                            next_field_idx = temp_output.find(field, start_idx)
                            if next_field_idx != -1 and next_field_idx < end_idx:
                                # Back up to the comma before this field
                                comma_idx = temp_output.rfind(',', start_idx, next_field_idx)
                                if comma_idx != -1:
                                    end_idx = comma_idx
                                else:
                                    end_idx = next_field_idx
                        
                        # Extract the date value and protect its commas
                        date_value = temp_output[start_idx:end_idx].strip()
                        if date_value and 'date' in date_value.lower():
                            protected_value = date_value.replace(',', '§COMMA§')
                            temp_output = temp_output[:start_idx] + protected_value + temp_output[end_idx:]
                            # Adjust field_start to continue searching after the replaced text
                            field_start = start_idx + len(protected_value)
                        else:
                            field_start = start_idx
            
            # Now split by commas safely
            parts = self._split_applescript_output(temp_output)
            
            if not parts:
                logger.warning("No parts found in AppleScript output after splitting")
                return []
            
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                    
                if ':' in part:
                    key, value = part.split(':', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # If we encounter an 'id' key and already have a record, save it
                    if key == 'id' and current_record:
                        records.append(current_record)
                        current_record = {}
                    
                    # Parse different value types
                    if key in ['creation_date', 'modification_date', 'due_date', 'start_date']:
                        # Handle date parsing - AppleScript dates come as "date Monday, January 1, 2024..."
                        # The value might be incomplete due to comma splitting, so skip if it looks incomplete
                        if 'date' in value.lower() or 'day' in value.lower():
                            current_record[key] = self._parse_applescript_date(value)
                        else:
                            # This is probably a partial date due to splitting, skip it
                            continue
                    elif key == 'tag_names':
                        # Restore commas in tag names and parse
                        value = value.replace('§COMMA§', ',')
                        current_record['tags'] = self._parse_applescript_tags(value)
                    else:
                        # Handle string values, removing quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        
                        # Handle AppleScript "missing value"
                        if value == 'missing value':
                            value = None
                        
                        current_record[key] = value
                else:
                    logger.warning(f"Invalid AppleScript output part (no colon): '{part}'")
            
            # Don't forget the last record
            if current_record:
                records.append(current_record)
            
            logger.debug(f"Parsed {len(records)} records from AppleScript output")
            
            # If we expected records but got none, that might indicate a problem
            if not records and output.strip():
                logger.warning(f"Failed to parse any records from non-empty output: {output[:100]}...")
            
            return records
        
        except Exception as e:
            logger.error(f"Error parsing AppleScript output: {e}")
            # Re-raise the exception instead of silently returning empty list
            raise ValueError(f"Failed to parse AppleScript output: {e}") from e
    
    def _split_applescript_output(self, output: str) -> List[str]:
        """Split AppleScript output by commas, handling quoted strings and braces properly."""
        parts = []
        current_part = ""
        in_quotes = False
        brace_depth = 0
        
        for char in output:
            if char == '"':
                in_quotes = not in_quotes
                current_part += char
            elif char == '{' and not in_quotes:
                brace_depth += 1
                current_part += char
            elif char == '}' and not in_quotes:
                brace_depth -= 1
                current_part += char
            elif char == ',' and not in_quotes and brace_depth == 0:
                parts.append(current_part)
                current_part = ""
            else:
                current_part += char
        
        # Add the last part
        if current_part:
            parts.append(current_part)
            
        return parts
    
    def _parse_applescript_date(self, date_str: str) -> Optional[str]:
        """Parse AppleScript date format to ISO string."""
        try:
            # AppleScript dates typically come as: date "Monday, January 1, 2024 at 12:00:00 PM"
            # Remove 'date' prefix and quotes if present
            cleaned = date_str.strip()
            if cleaned.startswith('date'):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            
            if not cleaned or cleaned == 'missing value':
                return None
            
            # Restore protected commas if any
            if '§COMMA§' in cleaned:
                cleaned = cleaned.replace('§COMMA§', ',')
                
            # Try to parse various AppleScript date formats
            date_patterns = [
                # European format: "Thursday, 4. September 2025 at 00:00:00" (24-hour)
                r'^(\w+),\s+(\d+)\.\s+(\w+)\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})$',
                # "Monday, January 1, 2024 at 12:00:00 PM"
                r'^(\w+),\s+(\w+)\s+(\d+),\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)$',
                # "January 1, 2024 at 12:00:00 PM" 
                r'^(\w+)\s+(\d+),\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)$',
                # "January 1, 2024"
                r'^(\w+)\s+(\d+),\s+(\d{4})$',
                # "2024-01-01 12:00:00"
                r'^(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+(\d{1,2}):(\d{2}):(\d{2}))?$'
            ]
            
            month_names = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8,
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            
            for pattern in date_patterns:
                match = re.match(pattern, cleaned, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    
                    if pattern.startswith('^(\\w+),\\s+'):
                        if len(groups) == 7 and '\\.' in pattern:
                            # European format: "Thursday, 4. September 2025 at 00:00:00" (24-hour)
                            _, day, month_str, year, hour, minute, second = groups
                            month = month_names.get(month_str.lower())
                            if not month:
                                continue
                            dt = datetime(int(year), month, int(day), int(hour), int(minute), int(second))
                            return dt.isoformat()
                        elif len(groups) == 8:
                            # US format with AM/PM: "Monday, January 1, 2024 at 12:00:00 PM"
                            _, month_str, day, year, hour, minute, second, ampm = groups
                            month = month_names.get(month_str.lower())
                            if not month:
                                continue
                                
                            hour = int(hour)
                            if ampm.upper() == 'PM' and hour != 12:
                                hour += 12
                            elif ampm.upper() == 'AM' and hour == 12:
                                hour = 0
                                
                            dt = datetime(int(year), month, int(day), hour, int(minute), int(second))
                            return dt.isoformat()
                        
                    elif pattern.startswith('^(\\w+)\\s+'):
                        # Month day, year format
                        if len(groups) == 7:  # With time
                            month_str, day, year, hour, minute, second, ampm = groups
                            month = month_names.get(month_str.lower())
                            if not month:
                                continue
                                
                            hour = int(hour)
                            if ampm.upper() == 'PM' and hour != 12:
                                hour += 12
                            elif ampm.upper() == 'AM' and hour == 12:
                                hour = 0
                                
                            dt = datetime(int(year), month, int(day), hour, int(minute), int(second))
                            return dt.isoformat()
                        else:  # Date only
                            month_str, day, year = groups
                            month = month_names.get(month_str.lower())
                            if not month:
                                continue
                            dt = datetime(int(year), month, int(day))
                            return dt.date().isoformat()
                            
                    elif pattern.startswith('^(\\d{4})'):
                        # ISO format
                        if len(groups) == 6 and groups[3]:  # With time
                            year, month, day, hour, minute, second = groups
                            dt = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
                            return dt.isoformat()
                        else:  # Date only
                            year, month, day = groups[:3]
                            dt = datetime(int(year), int(month), int(day))
                            return dt.date().isoformat()
            
            # If no pattern matches, return the cleaned string
            logger.debug(f"Could not parse date format, returning raw: '{cleaned}'")
            return cleaned
            
        except Exception as e:
            logger.warning(f"Could not parse date '{date_str}': {e}")
            return date_str  # Return original on error
    
    def get_applescript_date_formatter(self, date_property: str, fallback_value: str = "missing value") -> str:
        """Generate AppleScript code to format a date property as YYYY-MM-DD HH:MM:SS.
        
        Args:
            date_property: The AppleScript date property (e.g., "creation date of theTodo")
            fallback_value: Value to return if date is missing (default: "missing value")
            
        Returns:
            AppleScript code that formats the date or returns fallback
        """
        return f'''
        try
            set dateValue to {date_property}
            if dateValue is missing value then
                "{fallback_value}"
            else
                set yyyy to (year of dateValue) as string
                set mm to (month of dateValue as integer) as string
                if length of mm = 1 then set mm to "0" & mm
                set dd to (day of dateValue) as string
                if length of dd = 1 then set dd to "0" & dd
                set timeStr to time string of dateValue
                yyyy & "-" & mm & "-" & dd & " " & timeStr
            end if
        on error
            "{fallback_value}"
        end try
        '''
    
    def format_applescript_date_to_iso(self, date_str: str) -> Optional[str]:
        """Convert AppleScript date string to ISO format YYYY-MM-DD HH:MM:SS.
        
        This method handles AppleScript's native date format and converts it
        to the standardized ISO format expected by the MCP API.
        
        Args:
            date_str: AppleScript date string (e.g., "date Friday, 15. August 2025 at 17:01:55")
            
        Returns:
            ISO formatted date string or None if missing/invalid
        """
        try:
            # Handle missing values
            if not date_str or date_str.strip() in ['missing value', '{}', '']:
                return None
                
            # Clean the string
            cleaned = date_str.strip()
            if cleaned.startswith('date'):
                cleaned = cleaned[4:].strip()
            if cleaned.startswith('"') and cleaned.endswith('"'):
                cleaned = cleaned[1:-1]
            
            # Enhanced pattern matching for AppleScript date formats
            patterns = [
                # "Friday, 15. August 2025 at 17:01:55"
                r'^(\w+),\s+(\d+)\.\s+(\w+)\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})$',
                # "Friday, August 15, 2025 at 5:01:55 PM" 
                r'^(\w+),\s+(\w+)\s+(\d+),\s+(\d{4})\s+at\s+(\d{1,2}):(\d{2}):(\d{2})\s+(AM|PM)$',
                # Already ISO-ish: "2025-08-15 17:01:55"
                r'^(\d{4})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2}):(\d{2})$'
            ]
            
            month_names = {
                'january': 1, 'february': 2, 'march': 3, 'april': 4,
                'may': 5, 'june': 6, 'july': 7, 'august': 8, 
                'september': 9, 'october': 10, 'november': 11, 'december': 12
            }
            
            for pattern in patterns:
                match = re.match(pattern, cleaned, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    
                    if pattern.startswith('^(\\w+),\\s+(\\d+)\\.'):
                        # "Friday, 15. August 2025 at 17:01:55"
                        weekday, day, month_str, year, hour, minute, second = groups
                        month_num = month_names.get(month_str.lower())
                        if month_num:
                            return f"{year}-{month_num:02d}-{int(day):02d} {int(hour):02d}:{minute}:{second}"
                            
                    elif pattern.startswith('^(\\w+),\\s+(\\w+)\\s+'):
                        # "Friday, August 15, 2025 at 5:01:55 PM"
                        weekday, month_str, day, year, hour, minute, second, ampm = groups
                        month_num = month_names.get(month_str.lower())
                        if month_num:
                            hour_24 = int(hour)
                            if ampm.upper() == 'PM' and hour_24 != 12:
                                hour_24 += 12
                            elif ampm.upper() == 'AM' and hour_24 == 12:
                                hour_24 = 0
                            return f"{year}-{month_num:02d}-{int(day):02d} {hour_24:02d}:{minute}:{second}"
                            
                    elif pattern.startswith('^(\\d{4})'):
                        # Already ISO format
                        return cleaned
            
            # If no pattern matches, try the existing parser
            existing_result = self._parse_applescript_date(date_str)
            if existing_result and existing_result != date_str:
                # Convert date-only to datetime format
                if len(existing_result) == 10:  # YYYY-MM-DD
                    return f"{existing_result} 00:00:00"
                return existing_result
                
            logger.debug(f"Could not parse AppleScript date format: '{cleaned}'")
            return None
            
        except Exception as e:
            logger.warning(f"Error formatting AppleScript date '{date_str}': {e}")
            return None
    
    def _parse_applescript_tags(self, tags_str: str) -> List[str]:
        """Parse AppleScript tag names list."""
        try:
            # Tags might come as a list like: {"tag1", "tag2", "tag3"}
            # or as a simple comma-separated string like: "tag1, tag2, tag3"
            if not tags_str or tags_str.strip() in ['{}', 'missing value', '']:
                return []
            
            # Remove braces if present (for list format)
            cleaned = tags_str.strip()
            if cleaned.startswith('{') and cleaned.endswith('}'):
                cleaned = cleaned[1:-1]
            
            # Split by commas and clean up each tag
            tags = []
            for tag in cleaned.split(','):
                tag = tag.strip()
                # Remove quotes if present
                if tag.startswith('"') and tag.endswith('"'):
                    tag = tag[1:-1]
                if tag:
                    tags.append(tag)
            
            return tags
        except Exception as e:
            logger.warning(f"Could not parse tags '{tags_str}': {e}")
            return []
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    async def update_project_direct(self, project_id: str, title: Optional[str] = None, 
                                   notes: Optional[str] = None, tags: Optional[List[str]] = None,
                                   when: Optional[str] = None, deadline: Optional[str] = None,
                                   completed: Optional[bool] = None, canceled: Optional[bool] = None) -> Dict[str, Any]:
        """Update a project directly using AppleScript (no URL scheme).
        
        Args:
            project_id: ID of the project to update
            title: New title
            notes: New notes  
            tags: New tags
            when: New schedule
            deadline: New deadline
            completed: Mark as completed
            canceled: Mark as canceled
            
        Returns:
            Dict with success status and result information
        """
        try:
            # Build the AppleScript to update the project
            script_parts = [
                'tell application "Things3"',
                '    try'
            ]
            
            # First check if project exists
            script_parts.extend([
                f'        set theProject to project id "{project_id}"',
                '        -- Project exists, proceed with updates'
            ])
            
            # Update title if provided
            if title is not None:
                escaped_title = title.replace('"', '\\"')
                script_parts.append(f'        set name of theProject to "{escaped_title}"')
            
            # Update notes if provided
            if notes is not None:
                escaped_notes = notes.replace('"', '\\"').replace('\n', '\\n')
                script_parts.append(f'        set notes of theProject to "{escaped_notes}"')
            
            # Handle status changes
            if completed is not None:
                if completed:
                    script_parts.append('        set status of theProject to completed')
                elif canceled is not None and canceled:
                    script_parts.append('        set status of theProject to canceled')
                else:
                    script_parts.append('        set status of theProject to open')
            elif canceled is not None:
                if canceled:
                    script_parts.append('        set status of theProject to canceled')
                else:
                    script_parts.append('        set status of theProject to open')
            
            # Handle tags if provided
            if tags is not None:
                # First clear existing tags, then add new ones
                script_parts.append('        set tag names of theProject to {}')
                if tags:
                    for tag in tags:
                        escaped_tag = tag.replace('"', '\\"')
                        script_parts.extend([
                            '        try',
                            f'            set theTag to tag named "{escaped_tag}"',
                            '        on error',
                            f'            set theTag to make new tag with properties {{name:"{escaped_tag}"}}',
                            '        end try',
                            '        set tag names of theProject to tag names of theProject & {theTag}'
                        ])
            
            # Handle scheduling if provided
            if when is not None:
                when_lower = when.lower()
                if when_lower == "today":
                    script_parts.append('        set start date of theProject to current date')
                elif when_lower == "tomorrow":
                    script_parts.append('        set start date of theProject to (current date) + 1 * days')
                elif when_lower == "evening":
                    script_parts.append('        set start date of theProject to current date')
                elif when_lower in ["anytime", "someday"]:
                    script_parts.append('        set start date of theProject to missing value')
                else:
                    # Try to parse as date string (YYYY-MM-DD) using locale-aware handler
                    try:
                        date_components = locale_handler.normalize_date_input(when)
                        if date_components:
                            year, month, day = date_components
                            date_expr = locale_handler.build_applescript_date_property(year, month, day)
                            script_parts.append(f'        set start date of theProject to ({date_expr})')
                        else:
                            logger.warning(f"Could not normalize when date: {when}")
                    except Exception as e:
                        logger.warning(f"Error parsing when date '{when}': {e}")
            
            # Handle deadline if provided
            if deadline is not None:
                try:
                    date_components = locale_handler.normalize_date_input(deadline)
                    if date_components:
                        year, month, day = date_components
                        date_expr = locale_handler.build_applescript_date_property(year, month, day)
                        script_parts.append(f'        set due date of theProject to ({date_expr})')
                    else:
                        logger.warning(f"Could not normalize deadline date: {deadline}")
                except Exception as e:
                    logger.warning(f"Error parsing deadline date '{deadline}': {e}")
            
            # Close the try block and handle errors
            script_parts.extend([
                '        return "success"',
                '    on error errMsg',
                '        if errMsg contains "Can\'t get project id" then',
                '            return "error:Project not found"',
                '        else',
                '            return "error:" & errMsg',
                '        end if',
                '    end try',
                'end tell'
            ])
            
            script = '\n'.join(script_parts)
            logger.debug(f"Executing project update script for project {project_id}")
            
            result = await self._execute_script(script)
            
            if result.get("success"):
                output = result.get("output", "").strip()
                if output == "success":
                    return {
                        "success": True,
                        "message": "Project updated successfully",
                        "project_id": project_id
                    }
                elif output.startswith("error:"):
                    error_msg = output[6:]  # Remove "error:" prefix
                    return {
                        "success": False,
                        "error": error_msg
                    }
                else:
                    return {
                        "success": False,
                        "error": f"Unexpected output: {output}"
                    }
            else:
                return {
                    "success": False,
                    "error": result.get("error", "Unknown AppleScript error")
                }
        
        except Exception as e:
            logger.error(f"Error updating project {project_id}: {e}")
            return {
                "success": False,
                "error": f"Exception during update: {str(e)}"
            }

    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()
        logger.info("AppleScript shared cache cleared")
