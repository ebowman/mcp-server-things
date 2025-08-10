"""Simple cache manager for AppleScript operations."""

import time
from typing import Any, Dict, Optional


class CacheManager:
    """Simple in-memory cache manager."""
    
    def __init__(self, default_ttl: int = 300):
        """Initialize cache manager.
        
        Args:
            default_ttl: Default time-to-live in seconds
        """
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        if time.time() > entry['expires']:
            del self._cache[key]
            return None
        
        return entry['value']
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds, uses default if None
        """
        if ttl is None:
            ttl = self.default_ttl
        
        self._cache[key] = {
            'value': value,
            'expires': time.time() + ttl
        }
    
    def delete(self, key: str) -> bool:
        """Delete key from cache.
        
        Args:
            key: Cache key to delete
            
        Returns:
            True if key was found and deleted
        """
        return self._cache.pop(key, None) is not None
    
    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
    
    def clear_pattern(self, pattern: str) -> int:
        """Clear entries matching pattern.
        
        Args:
            pattern: Simple glob pattern (supports * wildcard)
            
        Returns:
            Number of entries cleared
        """
        if '*' not in pattern:
            # Exact match
            return 1 if self.delete(pattern) else 0
        
        # Convert glob to simple pattern matching
        prefix = pattern.split('*')[0]
        suffix = pattern.split('*')[-1] if pattern.endswith('*') else ''
        
        keys_to_delete = []
        for key in self._cache:
            if key.startswith(prefix) and (not suffix or key.endswith(suffix)):
                keys_to_delete.append(key)
        
        for key in keys_to_delete:
            del self._cache[key]
        
        return len(keys_to_delete)
    
    def size(self) -> int:
        """Get current cache size."""
        # Clean up expired entries first
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time > entry['expires']
        ]
        for key in expired_keys:
            del self._cache[key]
        
        return len(self._cache)