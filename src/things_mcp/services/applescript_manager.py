"""
AppleScript Manager Service

Handles all AppleScript execution with comprehensive error handling,
caching, and fallback strategies.
"""

import subprocess
import asyncio
import logging
import json
from typing import Dict, Any, Optional, List, Union
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from ..models.response_models import AppleScriptResult, ErrorDetails
from ..utils.applescript_utils import AppleScriptTemplates
from .error_handler import ErrorHandler
from .cache_manager import CacheManager


class ExecutionMethod(Enum):
    """AppleScript execution methods"""
    URL_SCHEME = "url_scheme"
    APPLESCRIPT = "applescript"
    HYBRID = "hybrid"


@dataclass
class ExecutionConfig:
    """Configuration for AppleScript execution"""
    timeout: float = 30.0
    retry_count: int = 3
    cache_ttl: int = 300  # 5 minutes
    preferred_method: ExecutionMethod = ExecutionMethod.HYBRID
    enable_logging: bool = True


class AppleScriptManager:
    """
    Manages AppleScript execution with error handling, caching, and fallbacks.
    
    This service provides a unified interface for interacting with Things 3
    through both URL schemes and direct AppleScript execution.
    """
    
    def __init__(
        self, 
        config: Optional[ExecutionConfig] = None,
        error_handler: Optional[ErrorHandler] = None,
        cache_manager: Optional[CacheManager] = None
    ):
        self.config = config or ExecutionConfig()
        self.error_handler = error_handler or ErrorHandler()
        self.cache_manager = cache_manager or CacheManager()
        self.templates = AppleScriptTemplates()
        self.logger = logging.getLogger(__name__)
        
        # Track execution statistics
        self.stats = {
            "url_scheme_calls": 0,
            "applescript_calls": 0,
            "cache_hits": 0,
            "errors": 0
        }
    
    async def execute_url_scheme(
        self,
        action: str,
        parameters: Dict[str, Any],
        cache_key: Optional[str] = None
    ) -> AppleScriptResult:
        """
        Execute Things 3 operation using URL scheme.
        
        Args:
            action: Things 3 URL action (add, update, show, etc.)
            parameters: URL parameters as key-value pairs
            cache_key: Optional cache key for result caching
            
        Returns:
            AppleScriptResult with execution results
        """
        try:
            # Check cache first
            if cache_key and self.cache_manager:
                cached_result = await self.cache_manager.get(cache_key)
                if cached_result:
                    self.stats["cache_hits"] += 1
                    return cached_result
            
            # Build Things URL
            url = self._build_things_url(action, parameters)
            
            # Execute URL scheme
            process = await asyncio.create_subprocess_exec(
                "open", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=self.config.timeout
            )
            
            result = AppleScriptResult(
                success=process.returncode == 0,
                output=stdout.decode() if stdout else "",
                error=stderr.decode() if stderr else "",
                method=ExecutionMethod.URL_SCHEME.value,
                url=url
            )
            
            # Cache successful results
            if result.success and cache_key and self.cache_manager:
                await self.cache_manager.set(
                    cache_key, result, ttl=self.config.cache_ttl
                )
            
            self.stats["url_scheme_calls"] += 1
            return result
            
        except Exception as e:
            self.stats["errors"] += 1
            return await self.error_handler.handle_execution_error(
                e, "url_scheme", {"action": action, "parameters": parameters}
            )
    
    async def execute_applescript(
        self,
        script: str,
        script_name: Optional[str] = None,
        cache_key: Optional[str] = None
    ) -> AppleScriptResult:
        """
        Execute raw AppleScript code.
        
        Args:
            script: AppleScript code to execute
            script_name: Optional name for logging/debugging
            cache_key: Optional cache key for result caching
            
        Returns:
            AppleScriptResult with execution results
        """
        try:
            # Check cache first
            if cache_key and self.cache_manager:
                cached_result = await self.cache_manager.get(cache_key)
                if cached_result:
                    self.stats["cache_hits"] += 1
                    return cached_result
            
            # Validate script
            if not script.strip():
                raise ValueError("AppleScript cannot be empty")
            
            # Log script execution
            if self.config.enable_logging:
                self.logger.debug(f"Executing AppleScript: {script_name or 'unnamed'}")
            
            # Execute AppleScript
            process = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.config.timeout
            )
            
            result = AppleScriptResult(
                success=process.returncode == 0,
                output=stdout.decode() if stdout else "",
                error=stderr.decode() if stderr else "",
                method=ExecutionMethod.APPLESCRIPT.value,
                script=script,
                script_name=script_name
            )
            
            # Cache successful results
            if result.success and cache_key and self.cache_manager:
                await self.cache_manager.set(
                    cache_key, result, ttl=self.config.cache_ttl
                )
            
            self.stats["applescript_calls"] += 1
            return result
            
        except Exception as e:
            self.stats["errors"] += 1
            return await self.error_handler.handle_execution_error(
                e, "applescript", {"script": script, "script_name": script_name}
            )
    
    async def execute_with_fallback(
        self,
        primary_method: str,
        fallback_method: str,
        **kwargs
    ) -> AppleScriptResult:
        """
        Execute operation with automatic fallback on failure.
        
        Args:
            primary_method: Primary execution method name
            fallback_method: Fallback execution method name
            **kwargs: Method-specific arguments
            
        Returns:
            AppleScriptResult from successful method
        """
        # Try primary method
        if primary_method == "url_scheme":
            result = await self.execute_url_scheme(**kwargs)
        elif primary_method == "applescript":
            result = await self.execute_applescript(**kwargs)
        else:
            raise ValueError(f"Unknown method: {primary_method}")
        
        # Return if successful
        if result.success:
            return result
        
        # Log fallback
        self.logger.warning(
            f"Primary method '{primary_method}' failed, trying fallback '{fallback_method}'"
        )
        
        # Try fallback method
        if fallback_method == "url_scheme":
            return await self.execute_url_scheme(**kwargs)
        elif fallback_method == "applescript":
            return await self.execute_applescript(**kwargs)
        else:
            # Return original error if fallback method is invalid
            return result
    
    def _build_things_url(self, action: str, parameters: Dict[str, Any]) -> str:
        """
        Build Things URL scheme from action and parameters.
        
        Args:
            action: Things action (add, update, show, etc.)
            parameters: URL parameters
            
        Returns:
            Complete Things URL string
        """
        from urllib.parse import quote_plus
        
        # Base URL
        base_url = f"things:///{action}"
        
        if not parameters:
            return base_url
        
        # Build query string
        query_parts = []
        for key, value in parameters.items():
            if value is not None:
                if isinstance(value, (list, tuple)):
                    # Handle list parameters (like tags)
                    value_str = ",".join(str(v) for v in value)
                else:
                    value_str = str(value)
                
                query_parts.append(f"{key}={quote_plus(value_str)}")
        
        if query_parts:
            return f"{base_url}?{'&'.join(query_parts)}"
        
        return base_url
    
    async def check_things_availability(self) -> AppleScriptResult:
        """
        Check if Things 3 is available and accessible.
        
        Returns:
            AppleScriptResult with availability status
        """
        script = self.templates.get_version_script()
        result = await self.execute_applescript(script, "version_check")
        
        if result.success:
            result.data = {"version": result.output.strip()}
        
        return result
    
    async def get_execution_stats(self) -> Dict[str, Any]:
        """
        Get execution statistics for monitoring.
        
        Returns:
            Dictionary with execution statistics
        """
        return {
            **self.stats,
            "cache_size": await self.cache_manager.size() if self.cache_manager else 0,
            "cache_hit_rate": (
                self.stats["cache_hits"] / max(1, sum(self.stats.values()))
            ) * 100
        }
    
    async def clear_cache(self) -> bool:
        """
        Clear all cached results.
        
        Returns:
            True if cache was cleared successfully
        """
        if self.cache_manager:
            return await self.cache_manager.clear()
        return True