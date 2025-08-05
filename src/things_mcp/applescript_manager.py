"""AppleScript manager for Things 3 integration."""

import asyncio
import logging
import subprocess
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


class AppleScriptManager:
    """Manages AppleScript execution and Things URL schemes."""
    
    def __init__(self, timeout: int = 30, retry_count: int = 3):
        """Initialize the AppleScript manager.
        
        Args:
            timeout: Command timeout in seconds
            retry_count: Number of retries for failed commands
        """
        self.timeout = timeout
        self.retry_count = retry_count
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
        logger.info("AppleScript manager initialized")
    
    def is_things_running(self) -> bool:
        """Check if Things 3 is currently running."""
        try:
            script = 'tell application "Things3" to return true'
            result = self._execute_script(script)
            return result.get("success", False)
        except Exception as e:
            logger.error(f"Error checking Things 3 status: {e}")
            return False
    
    def execute_applescript(self, script: str, cache_key: Optional[str] = None) -> Dict[str, Any]:
        """Execute an AppleScript command.
        
        Args:
            script: AppleScript code to execute
            cache_key: Optional cache key for result caching
            
        Returns:
            Dict with success status, output, and error information
        """
        # Check cache first
        if cache_key and self._get_cached_result(cache_key):
            return self._get_cached_result(cache_key)
        
        result = self._execute_script_with_retry(script)
        
        # Cache successful results
        if cache_key and result.get("success"):
            self._cache_result(cache_key, result)
        
        return result
    
    def execute_url_scheme(self, action: str, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute a Things URL scheme command.
        
        Args:
            action: Things URL action (add, update, show, etc.)
            parameters: Optional parameters for the action
            
        Returns:
            Dict with success status and result information
        """
        try:
            url = self._build_things_url(action, parameters or {})
            script = f'open location "{url}"'
            
            result = self._execute_script(script)
            
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
    
    def get_todos(self, project_uuid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get todos from Things 3.
        
        Args:
            project_uuid: Optional project UUID to filter by
            
        Returns:
            List of todo dictionaries
        """
        try:
            if project_uuid:
                script = f'''
                tell application "Things3"
                    set todoList to {{}}
                    set theProject to project id "{project_uuid}"
                    repeat with theTodo in to dos of theProject
                        set todoRecord to {{}}
                        set todoRecord to todoRecord & {{id:id of theTodo}}
                        set todoRecord to todoRecord & {{name:name of theTodo}}
                        set todoRecord to todoRecord & {{notes:notes of theTodo}}
                        set todoRecord to todoRecord & {{status:status of theTodo}}
                        set todoRecord to todoRecord & {{creation_date:creation date of theTodo}}
                        set todoRecord to todoRecord & {{modification_date:modification date of theTodo}}
                        set todoList to todoList & {{todoRecord}}
                    end repeat
                    return todoList
                end tell
                '''
            else:
                script = '''
                tell application "Things3"
                    set todoList to {}
                    repeat with theTodo in to dos
                        set todoRecord to {}
                        set todoRecord to todoRecord & {id:id of theTodo}
                        set todoRecord to todoRecord & {name:name of theTodo}
                        set todoRecord to todoRecord & {notes:notes of theTodo}
                        set todoRecord to todoRecord & {status:status of theTodo}
                        set todoRecord to todoRecord & {creation_date:creation date of theTodo}
                        set todoRecord to todoRecord & {modification_date:modification date of theTodo}
                        set todoList to todoList & {todoRecord}
                    end repeat
                    return todoList
                end tell
                '''
            
            cache_key = f"todos_{project_uuid or 'all'}"
            result = self.execute_applescript(script, cache_key)
            
            if result.get("success"):
                return self._parse_applescript_list(result.get("output", ""))
            else:
                logger.error(f"Failed to get todos: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting todos: {e}")
            return []
    
    def get_projects(self) -> List[Dict[str, Any]]:
        """Get all projects from Things 3."""
        try:
            script = '''
            tell application "Things3"
                set projectList to {}
                repeat with theProject in projects
                    set projectRecord to {}
                    set projectRecord to projectRecord & {id:id of theProject}
                    set projectRecord to projectRecord & {name:name of theProject}
                    set projectRecord to projectRecord & {notes:notes of theProject}
                    set projectRecord to projectRecord & {status:status of theProject}
                    set projectRecord to projectRecord & {creation_date:creation date of theProject}
                    set projectRecord to projectRecord & {modification_date:modification date of theProject}
                    set projectList to projectList & {projectRecord}
                end repeat
                return projectList
            end tell
            '''
            
            result = self.execute_applescript(script, "projects_all")
            
            if result.get("success"):
                return self._parse_applescript_list(result.get("output", ""))
            else:
                logger.error(f"Failed to get projects: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting projects: {e}")
            return []
    
    def get_areas(self) -> List[Dict[str, Any]]:
        """Get all areas from Things 3."""
        try:
            script = '''
            tell application "Things3"
                set areaList to {}
                repeat with theArea in areas
                    set areaRecord to {}
                    set areaRecord to areaRecord & {id:id of theArea}
                    set areaRecord to areaRecord & {name:name of theArea}
                    set areaRecord to areaRecord & {notes:notes of theArea}
                    set areaRecord to areaRecord & {creation_date:creation date of theArea}
                    set areaRecord to areaRecord & {modification_date:modification date of theArea}
                    set areaList to areaList & {areaRecord}
                end repeat
                return areaList
            end tell
            '''
            
            result = self.execute_applescript(script, "areas_all")
            
            if result.get("success"):
                return self._parse_applescript_list(result.get("output", ""))
            else:
                logger.error(f"Failed to get areas: {result.get('error')}")
                return []
        
        except Exception as e:
            logger.error(f"Error getting areas: {e}")
            return []
    
    def _execute_script_with_retry(self, script: str) -> Dict[str, Any]:
        """Execute script with retry logic."""
        last_error = None
        
        for attempt in range(self.retry_count):
            result = self._execute_script(script)
            
            if result.get("success"):
                return result
            
            last_error = result.get("error")
            
            if attempt < self.retry_count - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Script execution failed, retrying in {wait_time}s: {last_error}")
                time.sleep(wait_time)
        
        return {
            "success": False,
            "error": f"Failed after {self.retry_count} attempts: {last_error}"
        }
    
    def _execute_script(self, script: str) -> Dict[str, Any]:
        """Execute a single AppleScript command."""
        try:
            # Use osascript to execute the AppleScript
            process = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            if process.returncode == 0:
                return {
                    "success": True,
                    "output": process.stdout.strip(),
                    "execution_time": time.time()
                }
            else:
                return {
                    "success": False,
                    "error": process.stderr.strip() or "Unknown AppleScript error",
                    "return_code": process.returncode
                }
        
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": f"Script execution timed out after {self.timeout} seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution error: {str(e)}"
            }
    
    def _build_things_url(self, action: str, parameters: Dict[str, Any]) -> str:
        """Build a Things URL scheme string."""
        url = f"things:////{action}"
        
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
    
    def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get cached result if still valid."""
        if cache_key in self._cache:
            cached_data = self._cache[cache_key]
            if time.time() - cached_data["timestamp"] < self._cache_ttl:
                logger.debug(f"Cache hit for key: {cache_key}")
                return cached_data["result"]
            else:
                # Remove expired cache entry
                del self._cache[cache_key]
        
        return None
    
    def _cache_result(self, cache_key: str, result: Dict[str, Any]) -> None:
        """Cache a result with timestamp."""
        self._cache[cache_key] = {
            "result": result,
            "timestamp": time.time()
        }
        logger.debug(f"Cached result for key: {cache_key}")
    
    def _parse_applescript_list(self, output: str) -> List[Dict[str, Any]]:
        """Parse AppleScript list output into Python dictionaries.
        
        This is a simplified parser for basic AppleScript record lists.
        In a production environment, you might want a more robust parser.
        """
        try:
            # This is a basic implementation - AppleScript parsing can be complex
            # For now, return empty list and log for debugging
            logger.debug(f"AppleScript output to parse: {output}")
            
            # TODO: Implement proper AppleScript record parsing
            # For now, return mock data structure
            return []
        
        except Exception as e:
            logger.error(f"Error parsing AppleScript output: {e}")
            return []
    
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format."""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()
        logger.info("AppleScript cache cleared")
