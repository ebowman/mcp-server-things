"""
Shared file-based cache system for Things 3 MCP Server.

This module provides a SharedCache class that uses file-based storage to allow
multiple MCP server instances to share cached AppleScript execution results.
"""

import json
import os
import tempfile
import time
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Union
from contextlib import contextmanager
import fcntl
import hashlib
import logging

logger = logging.getLogger(__name__)


class SharedCache:
    """
    File-based cache with TTL support and concurrent access handling.
    
    Features:
    - File-based storage in temporary directory
    - Timestamp-based TTL checking
    - Concurrent file access with proper locking
    - Atomic writes to prevent corruption
    - Automatic cleanup of expired entries
    - Thread-safe operations
    """
    
    def __init__(self, cache_dir: Optional[str] = None, default_ttl: float = 30.0):
        """
        Initialize the shared cache.
        
        Args:
            cache_dir: Directory to store cache files. If None, uses system temp dir.
            default_ttl: Default time-to-live for cache entries in seconds.
        """
        self.default_ttl = default_ttl
        self._lock = threading.RLock()
        
        # Set up cache directory
        if cache_dir is None:
            self.cache_dir = Path(tempfile.gettempdir()) / "things_mcp_cache"
        else:
            self.cache_dir = Path(cache_dir)
        
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Track last cleanup time to avoid excessive cleanup calls
        self._last_cleanup = 0
        self._cleanup_interval = 60  # Cleanup every 60 seconds
        
        logger.debug(f"SharedCache initialized with directory: {self.cache_dir}")
    
    def _get_cache_path(self, key: str) -> Path:
        """Generate a safe filename for the cache key."""
        # Use hash to create safe filename and avoid path issues
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"
    
    @contextmanager
    def _file_lock(self, file_path: Path, mode: str = 'r'):
        """
        Context manager for file locking to handle concurrent access.
        
        Args:
            file_path: Path to the file to lock
            mode: File open mode ('r' for read, 'w' for write)
        """
        lock_file = None
        try:
            # Open file with appropriate mode
            lock_file = open(file_path, mode, encoding='utf-8')
            
            # Acquire exclusive lock for write, shared lock for read
            lock_type = fcntl.LOCK_EX if 'w' in mode else fcntl.LOCK_SH
            fcntl.flock(lock_file.fileno(), lock_type)
            
            yield lock_file
            
        except (IOError, OSError) as e:
            logger.debug(f"File lock error for {file_path}: {e}")
            raise
        finally:
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except (IOError, OSError):
                    pass  # Ignore cleanup errors
    
    def _is_expired(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if a cache entry has expired."""
        if 'expires_at' not in cache_entry:
            return True
        return time.time() > cache_entry['expires_at']
    
    def _cleanup_expired(self) -> None:
        """Remove expired cache files."""
        current_time = time.time()
        
        # Skip cleanup if we did it recently
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
        
        self._last_cleanup = current_time
        
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with self._file_lock(cache_file, 'r') as f:
                        data = json.load(f)
                        if self._is_expired(data):
                            cache_file.unlink(missing_ok=True)
                            logger.debug(f"Cleaned up expired cache file: {cache_file}")
                except (json.JSONDecodeError, IOError, OSError):
                    # Remove corrupted or unreadable files
                    cache_file.unlink(missing_ok=True)
                    logger.debug(f"Cleaned up corrupted cache file: {cache_file}")
        except Exception as e:
            logger.warning(f"Error during cache cleanup: {e}")
    
    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a value from the cache.
        
        Args:
            key: The cache key
            
        Returns:
            The cached value if it exists and hasn't expired, None otherwise
        """
        with self._lock:
            cache_path = self._get_cache_path(key)
            
            if not cache_path.exists():
                return None
            
            try:
                with self._file_lock(cache_path, 'r') as f:
                    data = json.load(f)
                    
                    if self._is_expired(data):
                        # Remove expired file
                        cache_path.unlink(missing_ok=True)
                        return None
                    
                    logger.debug(f"Cache hit for key: {key}")
                    return data['value']
                    
            except (json.JSONDecodeError, IOError, OSError) as e:
                logger.debug(f"Error reading cache file {cache_path}: {e}")
                # Remove corrupted file
                cache_path.unlink(missing_ok=True)
                return None
    
    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """
        Store a value in the cache.
        
        Args:
            key: The cache key
            value: The value to cache
            ttl: Time-to-live in seconds. If None, uses default_ttl
        """
        with self._lock:
            if ttl is None:
                ttl = self.default_ttl
            
            cache_path = self._get_cache_path(key)
            expires_at = time.time() + ttl
            
            cache_entry = {
                'value': value,
                'created_at': time.time(),
                'expires_at': expires_at,
                'key': key  # Store original key for debugging
            }
            
            try:
                # Write to temporary file first for atomic operation
                temp_path = cache_path.with_suffix('.tmp')
                
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(cache_entry, f, indent=2, ensure_ascii=False)
                
                # Atomically move to final location
                temp_path.replace(cache_path)
                logger.debug(f"Cache set for key: {key}, expires at: {expires_at}")
                
            except (IOError, OSError) as e:
                logger.error(f"Error writing cache file {cache_path}: {e}")
                # Clean up temp file if it exists
                temp_path = cache_path.with_suffix('.tmp')
                temp_path.unlink(missing_ok=True)
            
            # Occasionally clean up expired entries
            self._cleanup_expired()
    
    def delete(self, key: str) -> bool:
        """
        Delete a cache entry.
        
        Args:
            key: The cache key to delete
            
        Returns:
            True if the key existed and was deleted, False otherwise
        """
        with self._lock:
            cache_path = self._get_cache_path(key)
            
            if cache_path.exists():
                try:
                    cache_path.unlink()
                    logger.debug(f"Cache entry deleted for key: {key}")
                    return True
                except (IOError, OSError) as e:
                    logger.error(f"Error deleting cache file {cache_path}: {e}")
                    return False
            
            return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            try:
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink(missing_ok=True)
                
                logger.debug("All cache entries cleared")
                
            except Exception as e:
                logger.error(f"Error clearing cache: {e}")
    
    def size(self) -> int:
        """Get the number of cache entries."""
        try:
            return len(list(self.cache_dir.glob("*.json")))
        except Exception:
            return 0
    
    def keys(self) -> list[str]:
        """
        Get all cache keys (for debugging/monitoring).
        
        Returns:
            List of original cache keys
        """
        keys = []
        
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                try:
                    with self._file_lock(cache_file, 'r') as f:
                        data = json.load(f)
                        if not self._is_expired(data) and 'key' in data:
                            keys.append(data['key'])
                except (json.JSONDecodeError, IOError, OSError):
                    continue  # Skip corrupted files
        except Exception as e:
            logger.warning(f"Error getting cache keys: {e}")
        
        return keys
    
    def stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_files = 0
        valid_entries = 0
        expired_entries = 0
        corrupted_files = 0
        total_size = 0
        
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                total_files += 1
                
                try:
                    total_size += cache_file.stat().st_size
                    
                    with self._file_lock(cache_file, 'r') as f:
                        data = json.load(f)
                        if self._is_expired(data):
                            expired_entries += 1
                        else:
                            valid_entries += 1
                            
                except (json.JSONDecodeError, IOError, OSError):
                    corrupted_files += 1
        except Exception as e:
            logger.warning(f"Error getting cache stats: {e}")
        
        return {
            'total_files': total_files,
            'valid_entries': valid_entries,
            'expired_entries': expired_entries,
            'corrupted_files': corrupted_files,
            'total_size_bytes': total_size,
            'cache_directory': str(self.cache_dir)
        }


# Global cache instance
_shared_cache: Optional[SharedCache] = None


def get_shared_cache(cache_dir: Optional[str] = None, default_ttl: float = 30.0) -> SharedCache:
    """
    Get the global shared cache instance (singleton pattern).
    
    Args:
        cache_dir: Directory to store cache files
        default_ttl: Default TTL for cache entries
        
    Returns:
        SharedCache instance
    """
    global _shared_cache
    
    if _shared_cache is None:
        _shared_cache = SharedCache(cache_dir=cache_dir, default_ttl=default_ttl)
    
    return _shared_cache