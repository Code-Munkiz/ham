# incremental discovery module (Phase 6)
"""Incremental discovery engine for memory_heist."""
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
import hashlib
import stat


@dataclass
class FileChange:
    """Represents a detected file change."""
    file_path: str
    change_type: str  # 'created', 'modified', 'deleted', 'unchanged'
    old_hash: Optional[str] = None
    new_hash: Optional[str] = None
    last_modified: Optional[str] = None
    file_size: int = 0


class IncrementalDiscovery:
    """Incremental discovery engine for memory_heist."""
    
    def __init__(self, cache_store):
        """Initialize with cache store."""
        self.cache_store = cache_store
    
    def scan_for_changes(self, root_dir: str, cache_key_prefix: str = "") -> List[FileChange]:
        """Scan directory and detect changes since last cache."""
        changes = []
        cached_entries = {}
        
        # Load cached entries
        cached_entries = {}
        for entry in self.cache_store.get_cached_entries():
            cached_entries[entry.file_path] = entry
        
        # Walk directory
        for root, dirs, files in os.walk(root_dir):
            # Skip hidden directories and common noise
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            
            for filename in files:
                if filename.startswith('.'):
                    continue
                
                file_path = os.path.join(root, filename)
                relative_path = os.path.relpath(file_path, root_dir)
                
                file_hash = self._calculate_file_hash(file_path)
                stats = os.stat(file_path)
                
                # Create cache key
                cache_key = f"{cache_key_prefix}{relative_path}"
                
                if relative_path in cached_entries:
                    cached_entry = cached_entries[relative_path]
                    if file_hash == cached_entry.file_hash:
                        # Unchanged
                        changes.append(FileChange(
                            file_path=relative_path,
                            change_type='unchanged',
                            old_hash=file_hash,
                            new_hash=file_hash,
                            last_modified=datetime.fromtimestamp(stats.st_mtime).isoformat(),
                            file_size=stats.st_size
                        ))
                    else:
                        # Modified
                        changes.append(FileChange(
                            file_path=relative_path,
                            change_type='modified',
                            old_hash=cached_entry.file_hash,
                            new_hash=file_hash,
                            last_modified=datetime.fromtimestamp(stats.st_mtime).isoformat(),
                            file_size=stats.st_size
                        ))
                else:
                    # New file
                    changes.append(FileChange(
                        file_path=relative_path,
                        change_type='created',
                        new_hash=file_hash,
                        last_modified=datetime.fromtimestamp(stats.st_mtime).isoformat(),
                        file_size=stats.st_size
                    ))
        
        # Check for deleted files
        for cached_path, cached_entry in cached_entries.items():
            if not os.path.exists(os.path.join(root_dir, cached_path)):
                changes.append(FileChange(
                    file_path=cached_path,
                    change_type='deleted',
                    old_hash=cached_entry.file_hash,
                    new_hash=None
                ))
        
        return changes
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate file hash for change detection."""
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
                return hashlib.md5(content).hexdigest()
        except (IOError, OSError):
            return "error"
    
    def get_changed_files(self, changes: List[FileChange]) -> List[FileChange]:
        """Filter to only changed files (not unchanged)."""
        return [c for c in changes if c.change_type in ['created', 'modified', 'deleted']]
    
    def get_new_files(self, changes: List[FileChange]) -> List[FileChange]:
        """Filter to only newly created files."""
        return [c for c in changes if c.change_type == 'created']
    
    def get_modified_files(self, changes: List[FileChange]) -> List[FileChange]:
        """Filter to only modified files."""
        return [c for c in changes if c.change_type == 'modified']
