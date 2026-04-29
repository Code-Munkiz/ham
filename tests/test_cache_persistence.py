# test cache persistence module
"""Tests for cache persistence module."""
import os
import json
import pytest
import tempfile
import shutil
from unittest.mock import patch
from datetime import datetime

# Import from Phase 6 implementation
from src.cache_persistence import CacheStore, CacheEntry


class TestCacheEntry:
    """Test CacheEntry class."""
    
    def test_cache_entry_default_values(self):
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.8,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat()
        )
        
        assert entry.context_tags is None or isinstance(entry.context_tags, list)
        assert entry.discovery_depth == 1
        assert entry.is_important == False
    
    def test_cache_entry_with_context_tags(self):
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.8,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat(),
            context_tags=["config", "important"]
        )
        
        assert entry.context_tags == ["config", "important"]


class TestCacheStore:
    """Test CacheStore class."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        cache_dir = tempfile.mkdtemp()
        yield cache_dir
        shutil.rmtree(cache_dir, ignore_errors=True)
    
    @pytest.fixture
    def cache_store_with_custom_dir(self, temp_cache_dir):
        """Create cache store with custom directory."""
        store = CacheStore()
        store.CACHE_DIR = temp_cache_dir
        return store
    
    def test_cache_store_initialization(self, temp_cache_dir):
        store = CacheStore()
        store.CACHE_DIR = temp_cache_dir
        stats = store.get_cache_stats()
        
        assert stats["cache_dir"] == temp_cache_dir
        assert "cache_file" in stats
        assert "total_entries" in stats
    
    def test_cache_load_empty(self, cache_store_with_custom_dir):
        store = cache_store_with_custom_dir
        cache = store.load_cache()
        
        assert cache == {}
    
    def test_cache_save_and_load(self, cache_store_with_custom_dir):
        store = cache_store_with_custom_dir
        cache_path = store._get_cache_path()
        
        # Create and save cache entry
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.8,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat(),
            context_tags=["test"]
        )
        
        store.set("test_entry", entry)
        store.save_cache()
        
        # Load cache
        cache = store.load_cache()
        
        assert "test_entry" in cache
        assert cache["test_entry"].file_path == "test.py"
        assert cache["test_entry"].context_tags == ["test"]
    
    def test_cache_get_set_delete(self, cache_store_with_custom_dir):
        store = cache_store_with_custom_dir
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.8,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat()
        )
        
        # Test set
        store.set("test_key", entry)
        assert store.get("test_key") == entry
        
        # Test delete
        store.delete("test_key")
        assert store.get("test_key") is None
        
        # Verify deletion after save/load
        store.save_cache()
        store._cache = {}  # Clear in-memory cache
        store.load_cache()
        assert store.get("test_key") is None
    
    def test_cache_clear(self, cache_store_with_custom_dir):
        store = cache_store_with_custom_dir
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.8,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat()
        )
        
        store.set("key1", entry)
        store.set("key2", entry)
        store.set("key3", entry)
        store.save_cache()
        
        assert len(store.get_cached_entries()) == 3
        
        # Clear cache
        store.clear()
        store.save_cache()
        
        assert len(store.get_cached_entries()) == 0
    
    def test_cache_dirty_tracking(self, cache_store_with_custom_dir):
        store = cache_store_with_custom_dir
        
        assert store._dirty == False
        
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.8,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat()
        )
        
        store.set("key", entry)
        assert store._dirty == True
        
        store.save_cache()
        assert store._dirty == False
    
    def test_cache_multiple_entries(self, cache_store_with_custom_dir):
        store = cache_store_with_custom_dir
        
        for i in range(10):
            entry = CacheEntry(
                file_path=f"test_{i}.py",
                file_hash=f"hash_{i}",
                discovery_time=datetime.now().isoformat(),
                relevance_score=0.8 - (i * 0.05),
                file_size_bytes=1024 + (i * 100),
                last_updated=datetime.now().isoformat(),
                is_important=(i % 2 == 0)
            )
            store.set(f"key_{i}", entry)
        
        store.save_cache()
        cache = store.load_cache()
        
        assert len(cache) == 10
        assert cache["key_5"].file_path == "test_5.py"
        assert cache["key_9"].is_important == False
    
    def test_cache_path_creation(self, temp_cache_dir):
        store = CacheStore()
        store.CACHE_DIR = temp_cache_dir
        
        # Cache file doesn't exist until we write to it
        cache_path = store._get_cache_path()
        
        # Just verify the path is constructed correctly
        assert temp_cache_dir in cache_path
        assert store.CACHE_FILE in cache_path
        assert cache_path.endswith(store.CACHE_FILE)
        
        # File is created when we save - test with actual data
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.5,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat()
        )
        store.set("test_key", entry)
        store._save_cache()
        assert os.path.exists(cache_path)
    
    def test_close_background_sync(self, cache_store_with_custom_dir):
        store = cache_store_with_custom_dir
        
        assert store._background_sync is not None
        store.close()  # Should not block indefinitely
        
        # Cache should be synced
        assert not store._dirty


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
