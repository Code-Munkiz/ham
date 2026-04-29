# test incremental discovery module
"""Tests for incremental discovery module."""
import os
import pytest
import tempfile
import shutil
from datetime import datetime

from src.incremental_discovery import IncrementalDiscovery
from src.cache_persistence import CacheStore, CacheEntry


class TestIncrementalDiscovery:
    """Test IncrementalDiscovery class."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def cache_store(self):
        """Create cache store for testing."""
        return CacheStore()
    
    @pytest.fixture
    def discovery_engine(self, cache_store):
        """Create discovery engine with cache store."""
        return IncrementalDiscovery(cache_store)
    
    def test_scan_for_changes_with_new_files(self, temp_dir, discovery_engine):
        """Test scanning directory with new files."""
        # Create some test files
        with open(os.path.join(temp_dir, "file1.py"), 'w') as f:
            f.write("# test file 1")
        with open(os.path.join(temp_dir, "file2.py"), 'w') as f:
            f.write("# test file 2")
        
        # Scan for changes
        changes = discovery_engine.scan_for_changes(temp_dir, "test_")
        
        # Should detect all files as created
        created_files = [c for c in changes if c.change_type == 'created']
        assert len(created_files) == 2
        
        for change in created_files:
            assert change.new_hash is not None
    
    def test_scan_for_changes_with_modified_files(self, temp_dir, discovery_engine, cache_store):
        """Test scanning directory with modified files."""
        # Create initial file
        file_path = os.path.join(temp_dir, "file.py")
        with open(file_path, 'w') as f:
            f.write("# initial content")
        
        # Scan initially
        changes1 = discovery_engine.scan_for_changes(temp_dir)
        created_changes = [c for c in changes1 if c.change_type == 'created']
        
        # Save changes to cache (without prefix matching)
        for change in created_changes:
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
        
        # Modify file
        with open(file_path, 'w') as f:
            f.write("# modified content")
        
        # Clear cache and reload
        cache_store._cache = {}
        cache_store.load_cache()
        
        # Scan again
        changes2 = discovery_engine.scan_for_changes(temp_dir)
        modified_changes = [c for c in changes2 if c.change_type == 'modified']
        
        assert len(modified_changes) == 1
        assert modified_changes[0].old_hash != modified_changes[0].new_hash
    
    def test_scan_for_changes_with_deleted_files(self, temp_dir, discovery_engine, cache_store):
        """Test scanning directory with deleted files."""
        # Create initial file
        file_path = os.path.join(temp_dir, "file.py")
        with open(file_path, 'w') as f:
            f.write("# test content")
        
        # Scan initially
        changes1 = discovery_engine.scan_for_changes(temp_dir)
        created_changes = [c for c in changes1 if c.change_type == 'created']
        
        # Save changes to cache
        for change in created_changes:
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
        deleted_changes = [c for c in changes2 if c.change_type == 'deleted']
        
        assert len(deleted_changes) == 1
        assert deleted_changes[0].old_hash is not None
    
    def test_scan_filters_hidden_files(self, temp_dir, discovery_engine):
        """Test that hidden files are filtered out."""
        # Create hidden and non-hidden files
        with open(os.path.join(temp_dir, "visible.py"), 'w') as f:
            f.write("# visible")
        with open(os.path.join(temp_dir, ".hidden.py"), 'w') as f:
            f.write("# hidden")
        os.makedirs(os.path.join(temp_dir, ".hidden_dir"), exist_ok=True)
        with open(os.path.join(temp_dir, ".hidden_dir", "file.py"), 'w') as f:
            f.write("# in hidden dir")
        
        # Scan for changes
        changes = discovery_engine.scan_for_changes(temp_dir, "test_")
        
        # Should only find visible file
        visible_changes = [c for c in changes if c.change_type == 'created' and not c.file_path.startswith('.')]
        hidden_changes = [c for c in changes if c.change_type == 'created' and c.file_path.startswith('.')]
        
        assert len(visible_changes) == 1
        assert len(hidden_changes) == 0
    
    def test_get_changed_files(self, temp_dir, discovery_engine):
        """Test filtering to only changed files."""
        # Create test files
        with open(os.path.join(temp_dir, "file1.py"), 'w') as f:
            f.write("# file 1")
        
        # First scan to save to cache
        changes1 = discovery_engine.scan_for_changes(temp_dir)
        created = [c for c in changes1 if c.change_type == 'created']
        
        cache_store = discovery_engine.cache_store
        for change in created:
            entry = CacheEntry(
                file_path=change.file_path,
                file_hash=change.new_hash,
                discovery_time=datetime.now().isoformat(),
                relevance_score=0.5,
                file_size_bytes=os.path.getsize(os.path.join(temp_dir, change.file_path)),
                last_updated=datetime.now().isoformat()
            )
            cache_store.set(change.file_path, entry)
        cache_store.save_cache()
        
        # Clear cache and reload
        cache_store._cache = {}
        cache_store.load_cache()
        
        # Scan (file should be unchanged)
        changes2 = discovery_engine.scan_for_changes(temp_dir)
        
        # Filter to only changed
        changed = discovery_engine.get_changed_files(changes2)
        
        assert len(changed) == 0
        assert len([c for c in changes2 if c.change_type == 'unchanged']) == 1
    
    def test_get_new_files(self, temp_dir, discovery_engine):
        """Test filtering to only new files."""
        # Create test files
        with open(os.path.join(temp_dir, "new_file.py"), 'w') as f:
            f.write("# new file")
        
        changes = discovery_engine.scan_for_changes(temp_dir, "test_")
        new_files = discovery_engine.get_new_files(changes)
        
        assert len(new_files) == 1
        assert new_files[0].change_type == 'created'
    
    def test_get_modified_files(self, temp_dir, discovery_engine, cache_store):
        """Test filtering to only modified files."""
        # Create initial file
        file_path = os.path.join(temp_dir, "file.py")
        with open(file_path, 'w') as f:
            f.write("# initial")
        
        # First scan
        changes1 = discovery_engine.scan_for_changes(temp_dir)
        created_changes = [c for c in changes1 if c.change_type == 'created']
        
        # Save to cache
        for change in created_changes:
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
        
        # Modify file
        with open(file_path, 'w') as f:
            f.write("# modified")
        
        # Clear cache and reload
        cache_store._cache = {}
        cache_store.load_cache()
        
        # Second scan
        changes2 = discovery_engine.scan_for_changes(temp_dir)
        modified_changes = discovery_engine.get_modified_files(changes2)
        
        assert len(modified_changes) == 1
        assert modified_changes[0].change_type == 'modified'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
