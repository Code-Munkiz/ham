# time decay module (Phase 6)
"""Time-based decay scoring for cache entries."""
import math
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass


@dataclass
class TimeDecayConfig:
    """Configuration for time-based decay."""
    half_life_days: float = 7.0  # Score halves every 7 days
    max_age_days: float = 30.0   # Entries older than 30 days are considered stale
    min_score: float = 0.1       # Minimum score floor
    max_score: float = 1.0       # Maximum score ceiling


class TimeBasedDecay:
    """Time-based relevance decay calculator."""
    
    def __init__(self, config: Optional[TimeDecayConfig] = None):
        """Initialize with decay config."""
        self.config = config or TimeDecayConfig()
    
    def calculate_decay_factor(self, last_updated: str) -> float:
        """
        Calculate decay factor based on last updated timestamp.
        
        Args:
            last_updated: ISO format timestamp string
            
        Returns:
            Decay factor between 0.0 and 1.0
        """
        try:
            last_update = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
        except ValueError:
            # Fallback to current time if parsing fails
            last_update = datetime.now()
        
        now = last_update.replace(tzinfo=None)
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        else:
            now = datetime.now()
        
        # Make both naive for comparison
        if last_update.tzinfo is not None:
            last_update = last_update.replace(tzinfo=None)
        
        if now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        delta = now - last_update
        days_since_update = delta.total_seconds() / (24 * 3600)
        
        # Calculate half-life decay
        if days_since_update > self.config.max_age_days:
            return self.config.min_score
        
        decay_factor = math.pow(0.5, days_since_update / self.config.half_life_days)
        return max(self.config.min_score, min(decay_factor, self.config.max_score))
    
    def apply_decay_to_score(self, original_score: float, last_updated: str) -> float:
        """
        Apply time decay to a relevance score.
        
        Args:
            original_score: Original relevance score (0.0-1.0)
            last_updated: ISO format timestamp string
            
        Returns:
            Decay-adjusted score (0.0-1.0)
        """
        decay_factor = self.calculate_decay_factor(last_updated)
        decayed_score = original_score * decay_factor
        return max(self.config.min_score, min(decayed_score, self.config.max_score))
    
    def is_entry_stale(self, last_updated: str) -> bool:
        """Check if an entry is considered stale."""
        try:
            last_update = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
        except ValueError:
            return True
        
        now = datetime.now(last_update.tzinfo) if last_update.tzinfo else datetime.now()
        delta = now - last_update
        days_since_update = delta.total_seconds() / (24 * 3600)
        
        return days_since_update >= self.config.max_age_days
    
    def get_decay_stats(self) -> dict:
        """Get decay configuration statistics."""
        return {
            "half_life_days": self.config.half_life_days,
            "max_age_days": self.config.max_age_days,
            "min_score": self.config.min_score,
            "max_score": self.config.max_score
        }
