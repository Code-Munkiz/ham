# test time-based decay module
"""Tests for time-based decay module."""
import pytest
from datetime import datetime, timedelta
from src.cache_decay import TimeBasedDecay, TimeDecayConfig


class TestTimeBasedDecayConfig:
    """Test TimeDecayConfig class."""
    
    def test_default_config(self):
        config = TimeDecayConfig()
        
        assert config.half_life_days == 7.0
        assert config.max_age_days == 30.0
        assert config.min_score == 0.1
        assert config.max_score == 1.0


class TestTimeBasedDecay:
    """Test TimeBasedDecay class."""
    
    def test_decay_factor_immediate_update(self):
        """Test decay factor for recently updated file."""
        decay = TimeBasedDecay()
        now = datetime.now().isoformat()
        factor = decay.calculate_decay_factor(now)
        
        # Should be close to 1.0
        assert 0.9 <= factor <= 1.0
    
    def test_decay_factor_after_half_life(self):
        """Test decay factor after one half-life."""
        decay = TimeBasedDecay()
        one_week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        factor = decay.calculate_decay_factor(one_week_ago)
        
        # Should be close to 0.5 (one half-life)
        assert 0.4 <= factor <= 0.6
    
    def test_decay_factor_after_long_age(self):
        """Test decay factor after max age."""
        decay = TimeBasedDecay()
        one_month_ago = (datetime.now() - timedelta(days=35)).isoformat()
        factor = decay.calculate_decay_factor(one_month_ago)
        
        # Should be close to min_score
        assert 0.09 <= factor <= 0.12
    
    def test_decay_factor_with_custom_config(self):
        """Test decay factor with custom configuration."""
        config = TimeDecayConfig(half_life_days=1.0, max_age_days=5.0, min_score=0.2)
        decay = TimeBasedDecay(config)
        
        # After 0.5 days (half of half-life)
        half_day = (datetime.now() - timedelta(hours=12)).isoformat()
        factor = decay.calculate_decay_factor(half_day)
        
        # Should be between 0.5 and 0.707 (square root of 0.5)
        assert 0.55 <= factor <= 0.85
    
    def test_apply_decay_to_score(self):
        """Test applying decay to a score."""
        decay = TimeBasedDecay()
        
        # High score, recent update
        high_score = 0.9
        now = datetime.now().isoformat()
        decayed = decay.apply_decay_to_score(high_score, now)
        
        assert 0.85 <= decayed <= 0.91
        
        # High score, old update
        old_time = (datetime.now() - timedelta(days=35)).isoformat()
        decayed_old = decay.apply_decay_to_score(high_score, old_time)
        
        assert 0.09 <= decayed_old <= 0.15
    
    def test_decay_bounds(self):
        """Test that decay factor stays within bounds."""
        decay = TimeBasedDecay()
        config = TimeDecayConfig(min_score=0.3, max_score=0.9)
        
        decay.config = config
        
        # Very recent (should cap at max)
        now = datetime.now().isoformat()
        factor = decay.calculate_decay_factor(now)
        assert 0.85 <= factor <= 0.9
        
        # Very old (should cap at min)
        old = (datetime.now() - timedelta(days=100)).isoformat()
        factor = decay.calculate_decay_factor(old)
        assert 0.3 <= factor <= 0.35
    
    def test_is_entry_stale(self):
        """Test stale detection."""
        decay = TimeBasedDecay()
        
        # Recent entry should not be stale
        assert not decay.is_entry_stale(datetime.now().isoformat())
        
        # Old entry should be stale
        old = (datetime.now() - timedelta(days=31)).isoformat()
        assert decay.is_entry_stale(old)
        
        # Boundary case (exactly 30 days) - may or may not be stale depending on seconds
        # We just verify it doesn't crash
        boundary = (datetime.now() - timedelta(days=30)).isoformat()
        result = decay.is_entry_stale(boundary)
        assert isinstance(result, bool)
    
    def test_get_decay_stats(self):
        """Test getting decay statistics."""
        decay = TimeBasedDecay()
        config = TimeDecayConfig(half_life_days=14.0)
        
        decay.config = config
        stats = decay.get_decay_stats()
        
        assert stats["half_life_days"] == 14.0
        assert stats["max_age_days"] == 30.0
        assert stats["min_score"] == 0.1
        assert stats["max_score"] == 1.0
    
    def test_invalid_timestamp_handling(self):
        """Test handling of invalid timestamps."""
        decay = TimeBasedDecay()
        
        # Should handle invalid timestamps gracefully
        factor = decay.calculate_decay_factor("not-a-date")
        assert 0.0 <= factor <= 1.0
        
        stale = decay.is_entry_stale("invalid")
        # Should return True (default to stale for invalid)
        assert stale is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
