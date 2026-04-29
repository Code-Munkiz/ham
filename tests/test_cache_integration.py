# test cache integration (Phase 6)
"""Integration tests for cache persistence with memory_heist."""
import os
import pytest
import tempfile
import shutil
from datetime import datetime

from src.cache_persistence import CacheStore, CacheEntry
from src.incremental_discovery import IncrementalDiscovery, FileChange


class TestCacheIntegration:
    """Integration tests for cache system."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def cache_store(self):
        """Create cache store."""
        return CacheStore()
    
    @pytest.fixture
    def discovery_engine(self, cache_store):
        """Create discovery engine."""
        return IncrementalDiscovery(cache_store)
    
    def test_full_discovery_workflow(self, temp_dir, discovery_engine, cache_store):
        """Test complete discovery workflow."""
        # Create test files
        file1 = os.path.join(temp_dir, "test1.py")
        file2 = os.path.join(temp_dir, "test2.py")
        
        with open(file1, 'w') as f:
            f.write("# test file 1")
        with open(file2, 'w') as f:
            f.write("# test file 2")
        
        # First scan - should find new files
        changes1 = discovery_engine.scan_for_changes(temp_dir)
        
        # Save to cache
        for change in changes1:
            if change.change_type == 'created':
                entry = CacheEntry(
                    file_path=change.file_path,
                    file_hash=change.new_hash,
                    discovery_time=datetime.now().isoformat(),
                    relevance_score=0.8,
                    file_size_bytes=os.path.getsize(os.path.join(temp_dir, change.file_path)),
                    last_updated=datetime.now().isoformat(),
                    context_tags=["integration_test"]
                )
                cache_store.set(change.file_path, entry)
        cache_store.save_cache()
        
        # Verify cache has entries
        cached_entries = cache_store.get_cached_entries()
        assert len(cached_entries) == 2
        
        # Clear in-memory cache and reload from disk
        cache_store._cache = {}
        cache_store.load_cache()
        
        # Second scan - should find no changes
        changes2 = discovery_engine.scan_for_changes(temp_dir)
        changed = discovery_engine.get_changed_files(changes2)
        unchanged = [c for c in changes2 if c.change_type == 'unchanged']
        
        assert len(changed) == 0
        assert len(unchanged) == 2
    
    def test_cache_with_time_decay(self, temp_dir, discovery_engine, cache_store):
        """Test cache entries with time decay."""
        from src.cache_decay import TimeBasedDecay
        
        # Create cache entry
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, 'w') as f:
            f.write("# test")
        
        changes = discovery_engine.scan_for_changes(temp_dir)
        created_changes = [c for c in changes if c.change_type == 'created']
        
        for change in created_changes:
            entry = CacheEntry(
                file_path=change.file_path,
                file_hash=change.new_hash,
                discovery_time=datetime.now().isoformat(),
                relevance_score=1.0,
                file_size_bytes=os.path.getsize(file_path),
                last_updated=datetime.now().isoformat(),
                context_tags=["decay_test"]
            )
            cache_store.set(f"test_{change.file_path}", entry)
        cache_store.save_cache()
        
        # Apply time decay
        decay = TimeBasedDecay()
        cached_entry = cache_store.get(f"test_{change.file_path}")
        decayed_score = decay.apply_decay_to_score(cached_entry.relevance_score, cached_entry.last_updated)
        
        # Should be close to 1.0 for recent
        assert 0.85 <= decayed_score <= 1.0
        
        # Simulate old entry
        from datetime import timedelta
        old_time = (datetime.now() - timedelta(days=35)).isoformat()
        old_decay = decay.apply_decay_to_score(1.0, old_time)
        assert 0.09 <= old_decay <= 0.15
    
    def test_cache_persistence_across_sessions(self, temp_dir):
        """Test cache survives across "sessions" (cache store reloads)."""
        # Create cache store and entries
        cache_store1 = CacheStore()
        cache_store1.CACHE_DIR = os.path.join(temp_dir, "cache1")
        
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.8,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat(),
            context_tags=["persistence_test"]
        )
        cache_store1.set("persistent_key", entry)
        cache_store1.save_cache()
        
        # Create new cache store (simulates new session)
        cache_store2 = CacheStore()
        cache_store2.CACHE_DIR = os.path.join(temp_dir, "cache1")
        cache_store2.load_cache()
        
        # Verify data persisted
        assert cache_store2.get("persistent_key") is not None
        assert cache_store2.get("persistent_key").file_path == "test.py"
        assert cache_store2.get("persistent_key").context_tags == ["persistence_test"]
    
    def test_cache_with_modified_files(self, temp_dir, discovery_engine, cache_store):
        """Test cache detection of file modifications."""
        # Create file
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, 'w') as f:
            f.write("# initial")
        
        # First scan
        changes1 = discovery_engine.scan_for_changes(temp_dir)
        created = [c for c in changes1 if c.change_type == 'created']
        
        # Save to cache
        for change in created:
            entry = CacheEntry(
                file_path=change.file_path,
                file_hash=change.new_hash,
                discovery_time=datetime.now().isoformat(),
                relevance_score=0.5,
                file_size_bytes=os.path.getsize(file_path),
                last_updated=datetime.now().isoformat()
            )
            cache_store.set(f"test_{change.file_path}", entry)
        cache_store.save_cache()
        
        # Modify file
        with open(file_path, 'w') as f:
            f.write("# modified")
        
        # Clear cache and reload
        cache_store._cache = {}
        cache_store.load_cache()
        
        # Scan again
        changes2 = discovery_engine.scan_for_changes(temp_dir)
        modified = [c for c in changes2 if c.change_type == 'modified']
        
        assert len(modified) == 1
        assert modified[0].old_hash != modified[0].new_hash
    
    def test_cache_with_deleted_files(self, temp_dir, discovery_engine, cache_store):
        """Test cache detection of file deletions."""
        # Create file
        file_path = os.path.join(temp_dir, "test.py")
        with open(file_path, 'w') as f:
            f.write("# test")
        
        # First scan
        changes1 = discovery_engine.scan_for_changes(temp_dir)
        created = [c for c in changes1 if c.change_type == 'created']
        
        # Save to cache
        for change in created:
            entry = CacheEntry(
                file_path=change.file_path,
                file_hash=change.new_hash,
                discovery_time=datetime.now().isoformat(),
                relevance_score=0.5,
                file_size_bytes=os.path.getsize(file_path),
                last_updated=datetime.now().isoformat()
            )
            cache_store.set(change.file_path, entry)
        cache_store.save_cache()
        
        # Delete file
        os.remove(file_path)
        
        # Clear cache and reload
        cache_store._cache = {}
        cache_store.load_cache()
        
        # Scan again
        changes2 = discovery_engine.scan_for_changes(temp_dir)
        deleted = [c for c in changes2 if c.change_type == 'deleted']
        
        assert len(deleted) == 1
        assert deleted[0].old_hash is not None
    
    def test_cache_dirty_tracking(self, temp_dir):
        """Test that cachedirty flag works correctly."""
        cache_store = CacheStore()
        cache_store.CACHE_DIR = os.path.join(temp_dir, "dirty_test")
        
        assert cache_store._dirty == False
        
        entry = CacheEntry(
            file_path="test.py",
            file_hash="abc123",
            discovery_time=datetime.now().isoformat(),
            relevance_score=0.5,
            file_size_bytes=1024,
            last_updated=datetime.now().isoformat()
        )
        cache_store.set("key", entry)
        assert cache_store._dirty == True
        
        cache_store.save_cache()
        assert cache_store._dirty == False
        
        # Verify file exists
        cache_path = cache_store._get_cache_path()
        assert os.path.exists(cache_path)
    
    def test_multiple_cache_entries_with_tags(self, temp_dir):
        """Test multiple cache entries with different context tags."""
        cache_store = CacheStore()
        cache_store.CACHE_DIR = os.path.join(temp_dir, "multi_cache")
        
        # Create multiple entries
        for i in range(5):
            entry = CacheEntry(
                file_path=f"file{i}.py",
                file_hash=f"hash{i}",
                discovery_time=datetime.now().isoformat(),
                relevance_score=0.8 - (i * 0.1),
                file_size_bytes=1024 + (i * 100),
                last_updated=datetime.now().isoformat(),
                context_tags=[f"tag{i}"]
            )
            cache_store.set(f"key_{i}", entry)
        
        cache_store.save_cache()
        
        # Verify all saved
        cached = cache_store.get_cached_entries()
        assert len(cached) == 5
        assert cached[3].file_path == "file3.py"
        assert cached[3].context_tags == ["tag3"]
        
        # Verify persistence
        cache_store._cache = {}
        cache_store.load_cache()
        assert len(cache_store.get_cached_entries()) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
