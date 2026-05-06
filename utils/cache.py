"""
cache.py
--------
Simple in-memory caching layer to reduce Google Sheets API calls.
Dramatically speeds up dashboard and other data-heavy pages.
"""

import time
from typing import Any, Optional


class CacheManager:
    """
    Simple cache with TTL (time-to-live) support.
    Stores data in memory and expires after TTL seconds.
    """
    
    def __init__(self, ttl: int = 60):
        """
        Initialize cache with TTL in seconds.
        Default: 60 seconds (good balance between freshness and speed)
        """
        self.ttl = ttl
        self.cache = {}
        self.timestamps = {}
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if it exists and hasn't expired."""
        if key not in self.cache:
            return None
        
        # Check if expired
        age = time.time() - self.timestamps[key]
        if age > self.ttl:
            # Delete expired entry
            del self.cache[key]
            del self.timestamps[key]
            return None
        
        return self.cache[key]
    
    def set(self, key: str, value: Any) -> None:
        """Store value in cache with current timestamp."""
        self.cache[key] = value
        self.timestamps[key] = time.time()
    
    def delete(self, key: str) -> None:
        """Remove key from cache immediately."""
        if key in self.cache:
            del self.cache[key]
        if key in self.timestamps:
            del self.timestamps[key]
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self.timestamps.clear()
    
    def invalidate_pattern(self, pattern: str) -> None:
        """
        Invalidate all keys matching a pattern.
        Example: invalidate_pattern("sheet_123") removes all keys starting with "sheet_123"
        """
        keys_to_delete = [k for k in self.cache.keys() if pattern in k]
        for key in keys_to_delete:
            self.delete(key)


# Global cache instance (60 second TTL)
_cache = CacheManager(ttl=60)


def get_cache_value(key: str) -> Optional[Any]:
    """Get value from global cache."""
    return _cache.get(key)


def set_cache_value(key: str, value: Any) -> None:
    """Set value in global cache."""
    _cache.set(key, value)


def delete_cache_value(key: str) -> None:
    """Delete specific key from cache."""
    _cache.delete(key)


def invalidate_sheet_cache(spreadsheet_id: str) -> None:
    """Invalidate all cached data for a specific spreadsheet."""
    _cache.invalidate_pattern(f"sheet_{spreadsheet_id}")


def clear_all_cache() -> None:
    """Clear entire cache."""
    _cache.clear()
