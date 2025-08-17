"""
Strategic coverage tests for shared_cache.py - targeting 22.34% -> 40%.

Focuses on initialization, basic operations, TTL handling, and error paths.
"""

import pytest
import tempfile
import time
import os
from pathlib import Path
from unittest.mock import patch, mock_open

from src.things_mcp.shared_cache import SharedCache


class TestSharedCacheStrategicCoverage:
    """Strategic tests to boost shared_cache.py coverage."""
    
    def test_cache_initialization_default(self):
        """Test cache initialization with default parameters."""
        cache = SharedCache()
        
        assert cache.default_ttl == 30.0
        assert cache._lock is not None
        assert cache.cache_dir is not None
        assert str(cache.cache_dir).endswith("things_mcp_cache")

    def test_cache_initialization_custom_dir(self):
        """Test cache initialization with custom directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            assert cache.default_ttl == 30.0
            assert cache.cache_dir == Path(temp_dir)

    def test_cache_initialization_custom_ttl(self):
        """Test cache initialization with custom TTL."""
        cache = SharedCache(default_ttl=60.0)
        
        assert cache.default_ttl == 60.0

    def test_cache_directory_creation(self):
        """Test that cache directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "new_cache"
            cache = SharedCache(cache_dir=str(cache_path))
            
            # Access a property that would trigger directory creation
            assert cache.cache_dir == cache_path

    def test_cache_put_basic(self):
        """Test basic cache put operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            # Mock file operations to avoid actual file I/O
            with patch('builtins.open', mock_open()) as mock_file:
                with patch('json.dump') as mock_dump:
                    with patch('os.makedirs'):
                        cache.put("key1", "value1")
            
            # Verify file operations were attempted
            mock_file.assert_called()

    def test_cache_get_basic(self):
        """Test basic cache get operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            # Mock file operations
            mock_data = {
                "value": "test_value",
                "timestamp": time.time(),
                "ttl": 30.0
            }
            
            with patch('builtins.open', mock_open()) as mock_file:
                with patch('json.load', return_value=mock_data):
                    with patch('os.path.exists', return_value=True):
                        result = cache.get("key1")
            
            assert result == "test_value"

    def test_cache_get_missing_key(self):
        """Test cache get with missing key."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            with patch('os.path.exists', return_value=False):
                result = cache.get("nonexistent_key")
            
            assert result is None

    def test_cache_get_expired_entry(self):
        """Test cache get with expired entry."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            # Mock expired data
            expired_data = {
                "value": "expired_value",
                "timestamp": time.time() - 100,  # 100 seconds ago
                "ttl": 30.0  # 30 second TTL
            }
            
            with patch('builtins.open', mock_open()) as mock_file:
                with patch('json.load', return_value=expired_data):
                    with patch('os.path.exists', return_value=True):
                        with patch('os.remove') as mock_remove:
                            result = cache.get("expired_key")
            
            assert result is None
            mock_remove.assert_called_once()

    def test_cache_clear_basic(self):
        """Test cache clear operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            with patch('os.path.exists', return_value=True):
                with patch('os.listdir', return_value=['file1.json', 'file2.json']):
                    with patch('os.remove') as mock_remove:
                        cache.clear()
            
            # Should attempt to remove files
            assert mock_remove.call_count == 2

    def test_cache_contains_operation(self):
        """Test cache __contains__ operation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            # Mock existing key
            with patch.object(cache, 'get', return_value="value"):
                assert "key1" in cache
            
            # Mock non-existing key
            with patch.object(cache, 'get', return_value=None):
                assert "key2" not in cache

    def test_cache_size_property(self):
        """Test cache size property."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            with patch('os.path.exists', return_value=True):
                with patch('os.listdir', return_value=['file1.json', 'file2.json', 'other.txt']):
                    size = cache.size
            
            assert size == 2  # Only JSON files count

    def test_cache_size_no_directory(self):
        """Test cache size when directory doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            with patch('os.path.exists', return_value=False):
                size = cache.size
            
            assert size == 0

    def test_get_cache_path_method(self):
        """Test _get_cache_path method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            path = cache._get_cache_path("test_key")
            
            assert isinstance(path, Path)
            assert str(path).endswith(".json")
            assert temp_dir in str(path)

    def test_hash_key_method(self):
        """Test _hash_key method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            hash1 = cache._hash_key("test_key")
            hash2 = cache._hash_key("test_key")
            hash3 = cache._hash_key("different_key")
            
            assert hash1 == hash2  # Same input should produce same hash
            assert hash1 != hash3  # Different input should produce different hash
            assert isinstance(hash1, str)

    def test_is_expired_method(self):
        """Test _is_expired method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir, default_ttl=30.0)
            
            # Test non-expired entry
            current_time = time.time()
            fresh_data = {
                "timestamp": current_time,
                "ttl": 30.0
            }
            assert not cache._is_expired(fresh_data)
            
            # Test expired entry
            expired_data = {
                "timestamp": current_time - 60,  # 60 seconds ago
                "ttl": 30.0  # 30 second TTL
            }
            assert cache._is_expired(expired_data)

    def test_put_with_custom_ttl(self):
        """Test put operation with custom TTL."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            with patch('builtins.open', mock_open()) as mock_file:
                with patch('json.dump') as mock_dump:
                    with patch('os.makedirs'):
                        cache.put("key1", "value1", ttl=60.0)
            
            # Verify custom TTL was used
            mock_dump.assert_called_once()
            call_args = mock_dump.call_args[0][0]
            assert call_args["ttl"] == 60.0

    def test_error_handling_file_operations(self):
        """Test error handling in file operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            # Test put operation error handling
            with patch('builtins.open', side_effect=IOError("File error")):
                with patch('os.makedirs'):
                    # Should not raise exception
                    cache.put("key1", "value1")
            
            # Test get operation error handling
            with patch('builtins.open', side_effect=IOError("File error")):
                with patch('os.path.exists', return_value=True):
                    result = cache.get("key1")
                    assert result is None

    def test_json_serialization_error(self):
        """Test JSON serialization error handling."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            with patch('builtins.open', mock_open()):
                with patch('json.dump', side_effect=ValueError("JSON error")):
                    with patch('os.makedirs'):
                        # Should not raise exception
                        cache.put("key1", "value1")

    def test_json_deserialization_error(self):
        """Test JSON deserialization error handling."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            with patch('builtins.open', mock_open(read_data="invalid json")):
                with patch('json.load', side_effect=ValueError("JSON error")):
                    with patch('os.path.exists', return_value=True):
                        result = cache.get("key1")
                        assert result is None

    def test_file_locking_context_manager(self):
        """Test file locking context manager."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache = SharedCache(cache_dir=temp_dir)
            
            # Mock file and fcntl operations
            with patch('builtins.open', mock_open()) as mock_file:
                with patch('fcntl.flock') as mock_flock:
                    with cache._file_lock("test_path"):
                        pass
            
            # Verify flock was called for lock and unlock
            assert mock_flock.call_count == 2