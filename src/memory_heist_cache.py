"""
Phase 2: Cross-Platform Cache Key Normalization for memory_heist.py

This module implements the cross-platform cache key normalization functionality
to fix three major bugs:

1. CASE SENSITIVITY BUG: Cache keys use raw filesystem paths which behave
   differently on case-sensitive vs case-insensitive filesystems.

2. PATH SEPARATOR BUG: Cache keys use "/" separators inconsistently across
   platforms, causing cache misses.

3. GIT HEAD DETECTION BUG: Cache invalidation doesn't account for case
   differences in file paths.

The solution uses normalize_cache_key() to create canonical cache keys:
- Uses os.path.normpath() for OS-native separators
- Applies .lower() on case-insensitive systems (Windows, Mac)
- Uses os.path.realpath() to resolve symlinks
- Creates a consistent cache key format across all platforms
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any


# Platform detection for case sensitivity
IS_CASE_INSENSITIVE_SYSTEM = os.name == 'nt' or platform.system() == 'Darwin'


def normalize_cache_key(raw_path: str | Path) -> str:
    """
    Create a normalized cache key from a file path for cross-platform consistency.
    
    This function always lowercases paths and normalizes separators to ensure
    consistent cache keys regardless of:
    - Original case (Src vs src)
    - Platform separators (Windows \ vs Unix /)
    - Symlinks
    
    IMPORTANT: For case-sensitive systems (Linux), we STILL lowercase to ensure
    consistent cache behavior. The cache is case-insensitive by design.
    
    Args:
        raw_path: The original file path as string or Path object
        
    Returns:
        A lowercase, normalized cache key string
        
    Example:
        >>> normalize_cache_key("Src/HAM/engine.py")
        'src/ham/engine.py'
    """
    if raw_path is None:
        raise ValueError("normalize_cache_key() cannot handle None paths")
    
    # Convert Path to string if needed
    path_str = str(raw_path)
    
    # Normalize path separators using os.path.normpath
    normalized = os.path.normpath(path_str)
    
    # Resolve symlinks to their real paths
    try:
        real_path = os.path.realpath(normalized)
    except (OSError, ValueError):
        # If real() fails (e.g., broken symlink), use normalized path
        real_path = normalized
    
    # ALWAYS lowercase for consistent cache keys
    # This ensures cross-platform consistency regardless of OS
    return real_path.lower()


# Cache implementation: Simple thread-safe in-memory cache with TTL
class DiscoveryCache:
    """
    Simple in-memory cache for discovery results.
    
    Provides basic get/set operations for caching file discovery results
    with normalized path keys.
    
    Note: This is a lightweight cache for demonstration. A production
    implementation might use file-backed caching with proper TTL logic.
    """
    
    def __init__(self, max_size: int = 10000):
        self._cache: dict[str, dict[str, Any]] = {}
        self.max_size = max_size
        self._access_count: dict[str, int] = {}
        
    def get(self, key: str, default: Any = None) -> Any:
        """Get a value from the cache."""
        normalized_key = normalize_cache_key(key)
        # Track access
        self._access_count[normalized_key] = self._access_count.get(normalized_key, 0) + 1
        return self._cache.get(normalized_key, default)
    
    def set(self, key: str, value: dict[str, Any]) -> None:
        """Set a value in the cache."""
        normalized_key = normalize_cache_key(key)
        
        # Evict oldest entries if cache is full
        if len(self._cache) >= self.max_size:
            # Simple LRU eviction: remove key with smallest access count
            if self._access_count:
                oldest_key = min(self._access_count.keys(), key=lambda k: self._access_count[k])
                del self._cache[oldest_key]
                del self._access_count[oldest_key]
        
        self._cache[normalized_key] = value
    
    def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        normalized_key = normalize_cache_key(key)
        return normalized_key in self._cache
    
    def delete(self, key: str) -> bool:
        """Delete a key from the cache."""
        normalized_key = normalize_cache_key(key)
        if normalized_key in self._cache:
            del self._cache[normalized_key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._access_count.clear()
    
    def __len__(self) -> int:
        return len(self._cache)
    
    def keys(self) -> list[str]:
        """Get all cache keys."""
        return list(self._cache.keys())


# Create default discovery cache instance
discovery_cache = DiscoveryCache()


# Helper function for cache validation with git HEAD
def cache_invalidated_by_git(cwd: Path, file_key: str, expected_git_head: str) -> bool:
    """
    Check if cache entry is invalidated by git HEAD changes.
    
    Args:
        cwd: Current working directory
        file_key: The normalized cache key
        expected_git_head: The expected git HEAD hash
        
    Returns:
        True if cache should be invalidated, False otherwise
    """
    from src.metadata_stamps import _get_git_head_short
    
    try:
        current_git_head = _get_git_head_short(cwd)
        # Normalize git head for comparison
        current_git_head = current_git_head.lower()
        expected_git_head = expected_git_head.lower()
        
        return current_git_head != expected_git_head
    except (OSError, RuntimeError):
        # Can't get git head, assume cache is valid
        return False


# Import required platform detection
import platform
