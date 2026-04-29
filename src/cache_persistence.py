# cache persistence module (Phase 6)
"""Cache storage and persistence for discovery results."""
import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional
import threading
import time
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class CacheEntry:
    """Represents a single cache entry for a discovered file."""
    file_path: str
    file_hash: str
    discovery_time: str
    relevance_score: float
    file_size_bytes: int
    last_updated: str
    discovery_depth: int = 1
    is_important: bool = False
    context_tags: List[str] = None
    
    def __post_init__(self):
        if self.context_tags is None:
            self.context_tags = []


class CacheStore:
    """Persistent cache store for memory_heist discovery results."""
    
    CACHE_DIR = os.path.join(os.path.expanduser("~"), ".ham", "cache")
    CACHE_FILE = "discovery_cache.json"
    SYNC_INTERVAL = 300  # 5 minutes
    
    def __init__(self):
        self._lock = threading.Lock()
        self._cache: Dict[str, CacheEntry] = {}
        self._dirty = False
        self._background_sync = None
        self._start_background_sync()
    
    def _get_cache_path(self) -> str:
        """Get the cache file path."""
        os.makedirs(self.CACHE_DIR, exist_ok=True)
        return os.path.join(self.CACHE_DIR, self.CACHE_FILE)
    
    def _start_background_sync(self):
        """Start background sync thread for dirty cache."""
        def sync_loop():
            while True:
                time.sleep(self.SYNC_INTERVAL)
                if self._dirty:
                    self._save_cache()
        
        self._background_sync = threading.Thread(target=sync_loop, daemon=True)
        self._background_sync.start()
    
    def load_cache(self) -> Dict[str, CacheEntry]:
        """Load cache from disk."""
        cache_path = self._get_cache_path()
        if not os.path.exists(cache_path):
            return {}
        
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
            
            cache = {}
            for key, entry_data in data.items():
                cache[key] = CacheEntry(**entry_data)
            
            self._cache = cache
            return cache
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Cache load error: {e}")
            return {}
    
    def save_cache(self):
        """Save cache to disk synchronously."""
        self._save_cache()
    
    def _save_cache(self):
        """Internal save implementation."""
        cache_path = self._get_cache_path()
        
        # Ensure directory exists (cache_path includes filename, dirname extracts folder)
        cache_dir = os.path.dirname(cache_path)
        if cache_dir:  # Only create if directory is specified
            os.makedirs(cache_dir, exist_ok=True)
        
        with self._lock:
            if not self._dirty:
                return
            
            data = {}
            for key, entry in self._cache.items():
                data[key] = asdict(entry)
            
            with open(cache_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            self._dirty = False
    
    def get(self, cache_key: str) -> Optional[CacheEntry]:
        """Get cache entry by key."""
        with self._lock:
            return self._cache.get(cache_key)
    
    def set(self, cache_key: str, entry: CacheEntry):
        """Set cache entry."""
        with self._lock:
            self._cache[cache_key] = entry
            self._dirty = True
    
    def delete(self, cache_key: str):
        """Delete cache entry."""
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                self._dirty = True
    
    def get_cached_entries(self) -> List[CacheEntry]:
        """Get all cached entries."""
        with self._lock:
            return list(self._cache.values())
    
    def clear(self):
        """Clear all cache entries."""
        with self._lock:
            self._cache = {}
            self._dirty = True
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        with self._lock:
            return {
                "total_entries": len(self._cache),
                "cache_dir": self.CACHE_DIR,
                "cache_file": self._get_cache_path(),
                "is_dirty": self._dirty
            }
    
    def close(self):
        """Force save and close background sync."""
        self._save_cache()
        if self._background_sync:
            self._background_sync.join(timeout=5)
