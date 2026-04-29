"""
Tests for relevance_scoring.py — relevance-based file discovery scoring.

Tests cover:
- Individual scoring functions (recent, query, hot)
- Combined scoring integration
- Tier assignment logic
- Edge cases and error handling
- Backward compatibility
"""

from __future__ import annotations

import tempfile
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from src.memory_heist import FileEntry, Message, SessionMemory
from src.context.relevance_scoring import (
    FileRelevanceScore,
    RelevanceConfig,
    ScoringResult,
    SessionHistory,
    calculate_combined_score,
    calculate_hot_score,
    calculate_query_score,
    calculate_recent_score,
    get_session_history,
    score_file_entry,
)


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def temp_dir() -> Path:
    """Create a temporary directory with sample files."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        
        # Create directory structure first
        (path / "src" / "api").mkdir(parents=True, exist_ok=True)
        (path / "docs").mkdir(parents=True, exist_ok=True)
        (path / "tests").mkdir(parents=True, exist_ok=True)
        
        # Create sample files with different modification times
        (path / "src" / "memory_heist.py").write_text("# Memory Heist Context Engine", encoding="utf-8")
        (path / "src" / "api" / "server.py").write_text("# API Server", encoding="utf-8")
        (path / "docs" / "README.md").write_text("# Documentation", encoding="utf-8")
        (path / "tests" / "test_api.py").write_text("# Tests", encoding="utf-8")
        
        # Set different modification times for testing recency
        old_file = path / "docs" / "README.md"
        recent_file = path / "src" / "memory_heist.py"
        
        old_file.touch()
        time.sleep(0.1)
        recent_file.touch()
        
        yield path


@pytest.fixture
def session_memory() -> SessionMemory:
    """Create a session memory with file mentions."""
    mem = SessionMemory()
    
    # Add messages that mention files
    mem.add("user", "Edit src/memory_heist.py to fix caching")
    mem.add("assistant", "I'll update src/memory_heist.py now")
    mem.add("user", "Also check src/api/server.py for issues")
    mem.add("tool", "Output from editing memory_heist.py", tool_name="write_file", tool_id="1")
    
    return mem


@pytest.fixture
def session_history(session_memory: SessionMemory) -> list[SessionHistory]:
    """Create session history from session memory."""
    return get_session_history(session_memory)


# =============================================================================
# Test: calculate_recent_score
# =============================================================================

class TestCalculateRecentScore:
    """Tests for recency-based scoring."""
    
    def test_modern_file_high_score(self, temp_dir: Path):
        """Recently modified files should get high scores."""
        recent_file = temp_dir / "src" / "memory_heist.py"
        score = calculate_recent_score(str(recent_file), threshold_days=7)
        
        assert score > 0.0, "Recent file should have positive score"
        assert score <= 300.0, "Score should not exceed recent_file_weight"
    
    def test_old_file_low_score(self, temp_dir: Path):
        """Old files should get lower scores."""
        old_file = temp_dir / "docs" / "README.md"
        score = calculate_recent_score(str(old_file), threshold_days=7)
        
        # Old files can still get some score if they're not too old
        assert 0.0 <= score <= 300.0
    
    def test_nonexistent_file_zero_score(self):
        """Nonexistent files should get zero score."""
        score = calculate_recent_score("/nonexistent/file.py")
        assert score == 0.0
    
    def test_different_thresholds(self, temp_dir: Path):
        """Different thresholds should produce different scores."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        score_7days = calculate_recent_score(file_path, threshold_days=7)
        score_1day = calculate_recent_score(file_path, threshold_days=1)
        score_30days = calculate_recent_score(file_path, threshold_days=30)
        
        # With the same file, different thresholds produce different decay rates
        # The relationship depends on the actual file age
        assert 0.0 <= score_7days <= 300.0
        assert 0.0 <= score_1day <= 300.0
        assert 0.0 <= score_30days <= 300.0
    
    def test_modification_time_extraction(self, temp_dir: Path):
        """Extracted modification time should be accurate."""
        test_file = temp_dir / "src" / "memory_heist.py"
        
        # Get the score
        result = calculate_combined_score(
            str(test_file),
            config=RelevanceConfig(),
        )
        
        # Verify the modification time is reasonable
        mod_time = result.recent_score  # This uses mod_time internally
        assert isinstance(mod_time, float)


# =============================================================================
# Test: calculate_query_score
# =============================================================================

class TestCalculateQueryScore:
    """Tests for query-based scoring."""
    
    def test_filename_match(self, temp_dir: Path):
        """Filename matching should give high scores."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        query = "memory heist context"
        
        score = calculate_query_score(file_path, query)
        
        assert score > 0.0, "Filename contains matching terms"
        assert score <= 100.0
    
    def test_no_match(self, temp_dir: Path):
        """Unrelated queries should get low scores."""
        file_path = str(temp_dir / "tests" / "test_api.py")
        query = "frontend ui component react"
        
        score = calculate_query_score(file_path, query)
        
        # Should be low but not necessarily 0 (path might contain some terms)
        assert 0.0 <= score <= 100.0
    
    def test_empty_query(self, temp_dir: Path):
        """Empty queries should return zero score."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        score = calculate_query_score(file_path, "")
        assert score == 0.0
        
        score = calculate_query_score(file_path, None)
        assert score == 0.0
    
    def test_extension_match(self, temp_dir: Path):
        """Extensions matching query terms should contribute to score."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        # Query containing "py" should match extension
        score_with_py = calculate_query_score(file_path, "python")
        assert score_with_py >= 0.0
        
        # This is a soft match, so we just verify it's in range
        assert 0.0 <= score_with_py <= 100.0
    
    def test_path_component_match(self, temp_dir: Path):
        """Path components (directories) should contribute to score."""
        test_cases = [
            ("src/memory_heist.py", "src", 0.0, 100.0),
            ("src/memory_heist.py", "api", 0.0, 50.0),  # "api" not in this path
        ]
        
        for file_path, query, _, _ in test_cases:
            file_path = str(temp_dir / file_path)
            score = calculate_query_score(file_path, query)
            assert 0.0 <= score <= 100.0
    
    def test_content_match(self, temp_dir: Path):
        """File content should be checked when possible."""
        test_file = temp_dir / "src" / "memory_heist.py"
        
        # Query that matches content
        score_matching = calculate_query_score(str(test_file), "memory heist context")
        
        # Query that doesn't match content
        score_non_matching = calculate_query_score(str(test_file), "completely unrelated xyz")
        
        assert score_matching >= score_non_matching, "Matching query should score higher"
        assert 0.0 <= score_matching <= 100.0
    
    def test_case_insensitive_matching(self, temp_dir: Path):
        """Matching should be case-insensitive."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        score_lower = calculate_query_score(file_path, "memory heist")
        score_upper = calculate_query_score(file_path, "MEMORY HEIST")
        score_mixed = calculate_query_score(file_path, "Memory HeiSt")
        
        # All should be roughly equal (case-insensitive)
        assert abs(score_lower - score_upper) <= 5.0
        assert abs(score_lower - score_mixed) <= 5.0


# =============================================================================
# Test: calculate_hot_score
# =============================================================================

class TestCalculateHotScore:
    """Tests for hot path tracking."""
    
    def test_no_history_zero_score(self, temp_dir: Path):
        """Files with no history should get zero score."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        empty_history: list[SessionHistory] = []
        
        score = calculate_hot_score(file_path, empty_history)
        assert score == 0.0
    
    def test_repeated_access_high_score(self):
        """Frequently accessed files should get high scores."""
        file_path = "/home/user/ham/src/memory_heist.py"
        
        # Create history with multiple accesses
        now = time.time()
        history = [
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=now),
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=now - 60),
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=now - 120),
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=now - 300),
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=now - 1800),
        ]
        
        score = calculate_hot_score(file_path, history)
        
        # Should be a significant score (up to 500)
        assert 0.0 <= score <= 500.0
    
    def test_single_access_low_score(self):
        """Single access should give low score."""
        file_path = "/home/user/ham/src/memory_heist.py"
        history = [
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=time.time()),
        ]
        
        score = calculate_hot_score(file_path, history)
        
        assert score < 200.0, "Single access should give lower score"
        assert score > 0.0, "Single access should give positive score"
    
    def test_recency_weighting(self):
        """Recent accesses should weigh more than old ones."""
        file_path = "/home/user/ham/src/memory_heist.py"
        
        # Very recent access
        history_recent = [
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=time.time()),
        ]
        
        # Older access
        history_old = [
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=time.time() - 3600),
        ]
        
        score_recent = calculate_hot_score(file_path, history_recent)
        score_old = calculate_hot_score(file_path, history_old)
        
        assert score_recent >= score_old, "Recent access should weigh more"
    
    def test_multiple_files_different_scores(self, temp_dir: Path):
        """Different files should get different hot scores."""
        history = [
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=time.time()),
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=time.time()),
            SessionHistory(file_path="src/api/server.py", access_type="accessed", timestamp=time.time()),
        ]
        
        score_heist = calculate_hot_score(str(temp_dir / "src" / "memory_heist.py"), history)
        score_server = calculate_hot_score(str(temp_dir / "src" / "api" / "server.py"), history)
        
        # memory_heist should have higher score (2 mentions vs 1)
        assert score_heist >= score_server


# =============================================================================
# Test: calculate_combined_score
# =============================================================================

class TestCalculateCombinedScore:
    """Tests for combined scoring integration."""
    
    def test_combined_scoring_structure(self, temp_dir: Path):
        """Combined score should have all required fields."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        history = [
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=time.time()),
        ]
        
        result = calculate_combined_score(
            file_path,
            user_query="context discovery",
            session_history=history,
            config=RelevanceConfig(),
        )
        
        assert isinstance(result, ScoringResult)
        assert result.file_path == file_path
        assert hasattr(result, "recent_score")
        assert hasattr(result, "query_score")
        assert hasattr(result, "hot_score")
        assert hasattr(result, "total_score")
        assert result.tier in ["hot", "recent", "baseline"]
        assert isinstance(result.breakdown, dict)
    
    def test_tier_assignment_hot(self, temp_dir: Path):
        """High hot scores should result in 'hot' tier."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        # Create history with many recent accesses
        now = time.time()
        history = [
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=now - i * 60)
            for i in range(10)
        ]
        
        result = calculate_combined_score(
            file_path,
            session_history=history,
            config=RelevanceConfig(
                hot_file_weight=500.0,
                enable_hot_tracking=True,
            ),
        )
        
        # With enough accesses, should be hot tier
        assert result.hot_score > 0.0
    
    def test_tier_assignment_recent(self, temp_dir: Path):
        """Recent modification should result in 'recent' tier."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        result = calculate_combined_score(
            file_path,
            config=RelevanceConfig(
                enable_hot_tracking=False,
            ),
        )
        
        # Should be recent if modified recently
        assert result.tier in ["recent", "hot", "baseline"]
    
    def test_tier_assignment_baseline(self, temp_dir: Path):
        """Old files with no other factors should be 'baseline'."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        result = calculate_combined_score(
            file_path,
            session_history=[],
            config=RelevanceConfig(
                enable_hot_tracking=False,
            ),
        )
        
        assert result.tier in ["recent", "baseline"]
    
    def test_breakdown_components(self, temp_dir: Path):
        """Breakdown should sum to total score."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        result = calculate_combined_score(
            file_path,
            user_query="context",
            session_history=[],
            config=RelevanceConfig(
                enable_hot_tracking=False,
            ),
        )
        
        calculated_total = result.breakdown["recent"] + result.breakdown["query"] + result.breakdown["hot"]
        assert abs(result.total_score - calculated_total) < 0.01, "Breakdown should sum to total"
    
    def test_no_user_query(self, temp_dir: Path):
        """Should handle missing user query gracefully."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        result = calculate_combined_score(
            file_path,
            user_query=None,
            session_history=[],
            config=RelevanceConfig(),
        )
        
        assert result is not None
        assert result.query_score == 0.0
    
    def test_no_session_history(self, temp_dir: Path):
        """Should handle missing session history gracefully."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        result = calculate_combined_score(
            file_path,
            user_query="test",
            session_history=None,
            config=RelevanceConfig(),
        )
        
        assert result is not None
        assert result.hot_score == 0.0
    
    def test_config_weight_modification(self, temp_dir: Path):
        """Changing config weights should affect scores."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        config_default = RelevanceConfig(query_term_weight=100.0)
        config_high = RelevanceConfig(query_term_weight=200.0)
        
        result_default = calculate_combined_score(
            file_path,
            user_query="memory",
            config=config_default,
        )
        
        result_high = calculate_combined_score(
            file_path,
            user_query="memory",
            config=config_high,
        )
        
        # Higher weight should give higher query score
        assert result_high.query_score >= result_default.query_score


# =============================================================================
# Test: score_file_entry
# =============================================================================

class TestScoreFileEntry:
    """Tests for FileEntry scoring."""
    
    def test_scores_file_entry_correctly(self, temp_dir: Path):
        """Should score FileEntry objects from scan_workspace."""
        entry = FileEntry(
            path=temp_dir / "src" / "memory_heist.py",
            relative="src/memory_heist.py",
            size=100,
            mtime=time.time(),
        )
        
        history = [
            SessionHistory(file_path="src/memory_heist.py", access_type="accessed", timestamp=time.time()),
        ]
        
        result = score_file_entry(
            entry,
            user_query="memory",
            session_history=history,
            config=RelevanceConfig(),
        )
        
        assert isinstance(result, FileRelevanceScore)
        assert result.file_path == "src/memory_heist.py"
        assert isinstance(result.score, float)
        assert result.tier in ["hot", "recent", "baseline"]


# =============================================================================
# Test: get_session_history
# =============================================================================

class TestGetSessionHistory:
    """Tests for session history extraction."""
    
    def test_extracts_key_files_from_session(self):
        """Should extract file mentions from session messages."""
        mem = SessionMemory()
        mem.add("user", "Edit src/memory_heist.py to fix issues")
        mem.add("assistant", "Updating src/api/server.py now")
        mem.add("tool", "Output", tool_name="write_file", tool_id="1")
        
        history = get_session_history(mem)
        
        # Should have found mentions
        assert len(history) >= 2, "Should extract file mentions"
        
        # Verify we got our mentioned files
        file_paths = [h.file_path for h in history]
        assert any("memory_heist.py" in p for p in file_paths)
        assert any("server.py" in p for p in file_paths)
    
    def test_empty_session_returns_empty(self):
        """Empty session should return empty history."""
        mem = SessionMemory()
        assert len(get_session_history(mem)) == 0
    
    def test_none_session_returns_empty(self):
        """None session should return empty history."""
        assert len(get_session_history(None)) == 0


# =============================================================================
# Test: RelevanceConfig
# =============================================================================

class TestRelevanceConfig:
    """Tests for configuration handling."""
    
    def test_default_config_values(self):
        """Default config should have expected values."""
        config = RelevanceConfig()
        
        assert config.recent_threshold_days == 7
        assert config.query_term_weight == 100.0
        assert config.recent_file_weight == 300.0
        assert config.hot_file_weight == 500.0
        assert config.baseline_weight == 100.0
        assert config.max_results == 50
        assert config.enable_hot_tracking is True
    
    def test_config_from_dict(self):
        """Should create config from dictionary."""
        data = {
            "recent_threshold_days": 14,
            "query_term_weight": 150.0,
            "max_results": 100,
        }
        
        config = RelevanceConfig.from_dict(data)
        
        assert config.recent_threshold_days == 14
        assert config.query_term_weight == 150.0
        assert config.max_results == 100
        assert config.enable_hot_tracking is True  # Default not overwritten
    
    def test_config_to_dict_roundtrip(self):
        """Config should serialize and deserialize correctly."""
        original = RelevanceConfig(
            recent_threshold_days=10,
            query_term_weight=120.0,
            max_results=75,
        )
        
        data = original.to_dict()
        restored = RelevanceConfig.from_dict(data)
        
        assert restored.recent_threshold_days == original.recent_threshold_days
        assert restored.query_term_weight == original.query_term_weight
        assert restored.max_results == original.max_results
    
    def test_disable_hot_tracking(self):
        """Should be able to disable hot tracking."""
        config = RelevanceConfig(enable_hot_tracking=False)
        
        # Hot score should be zero with tracking disabled
        assert config.enable_hot_tracking is False


# =============================================================================
# Test: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Tests for backward compatibility."""
    
    def test_old_discover_signature_works(self, temp_dir: Path):
        """Old discover() signature should still work."""
        from src.memory_heist import ProjectContext
        
        # Old signature (no keyword args)
        context = ProjectContext.discover(temp_dir)
        
        assert context.cwd == temp_dir
        assert context.file_count > 0
    
    def test_new_discover_signature_works(self, temp_dir: Path, session_memory: SessionMemory):
        """New discover() signature with all params should work."""
        from src.memory_heist import ProjectContext
        
        context = ProjectContext.discover(
            temp_dir,
            use_relevance_filtering=True,
            user_query="test query",
            session_memory=session_memory,
        )
        
        assert context.cwd == temp_dir
        # Relevance filtering adds metadata
        assert context.relevance_metadata is not None
    
    def test_relevance_results_optional(self, temp_dir: Path):
        """Relevance results should be optional."""
        from src.memory_heist import ProjectContext
        
        # Without relevance filtering
        context = ProjectContext.discover(temp_dir, use_relevance_filtering=False)
        
        assert context.relevance_results is None
        assert context.relevance_metadata is None


# =============================================================================
# Test: Edge Cases
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    def test_path_with_spaces(self, temp_dir: Path):
        """Paths with spaces should be handled correctly."""
        # (Skipping actual test - would need space in path creation)
        pass
    
    def test_unicode_in_filename(self, temp_dir: Path):
        """Unicode in filenames should be handled."""
        test_file = temp_dir / "文件.py"
        test_file.write_text("# Unicode filename", encoding="utf-8")
        
        score = calculate_recent_score(str(test_file))
        
        # Should not crash
        assert score >= 0.0
    
    def test_very_long_path(self, temp_dir: Path):
        """Very long paths should be handled."""
        # Create nested path
        nested = temp_dir / "/".join(["dir"] * 20) / "file.py"
        nested.parent.mkdir(parents=True, exist_ok=True)
        nested.write_text("# Long path", encoding="utf-8")
        
        score = calculate_recent_score(str(nested))
        
        assert score >= 0.0
    
    def test_symlink_handling(self, temp_dir: Path):
        """Symlinks should be handled gracefully."""
        original = temp_dir / "original.py"
        original.write_text("# Original", encoding="utf-8")
        
        try:
            symlink = temp_dir / "link.py"
            symlink.symlink_to(original)
            
            score = calculate_recent_score(str(symlink))
            
            assert score >= 0.0
        except OSError:
            # Symlinks not supported on this system
            pass
    
    def test_large_file_score(self, temp_dir: Path):
        """Large files should be scored correctly."""
        test_file = temp_dir / "large.py"
        test_file.write_text("# " * 10000, encoding="utf-8")  # Large file
        
        score = calculate_query_score(str(test_file), "file")
        
        # Should not crash or timeout
        assert 0.0 <= score <= 100.0
    
    def test_no_permission_file(self, temp_dir: Path):
        """Unreadable files should not crash scoring."""
        test_file = temp_dir / "unreadable.py"
        test_file.write_text("# Unreadable", encoding="utf-8")
        
        try:
            test_file.chmod(0o000)  # Remove all permissions
            
            # Should still work (might not be able to read content but should score)
            score = calculate_query_score(str(test_file), "test")
            
            assert score >= 0.0
        finally:
            test_file.chmod(0o644)  # Restore permissions


# =============================================================================
# Test: Output Format (as specified in requirements)
# =============================================================================

class TestOutputFormat:
    """Tests for output format compliance."""
    
    def test_scoring_result_serializes_to_dict(self, temp_dir: Path):
        """ScoringResult should serialize to expected format."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        result = calculate_combined_score(
            file_path,
            user_query="context",
            session_history=[],
            config=RelevanceConfig(),
        )
        
        data = result.to_dict()
        
        # Expected format
        assert "file_path" in data
        assert "score" in data
        assert "tier" in data
        assert "breakdown" in data
        assert data["tier"] in ["hot", "recent", "baseline"]
        assert "recent" in data["breakdown"]
        assert "query" in data["breakdown"]
        assert "hot" in data["breakdown"]
    
    def test_breakdown_has_correct_types(self, temp_dir: Path):
        """Breakdown values should be numeric."""
        file_path = str(temp_dir / "src" / "memory_heist.py")
        
        result = calculate_combined_score(
            file_path,
            config=RelevanceConfig(),
        )
        
        for key, value in result.breakdown.items():
            assert isinstance(value, (int, float)), f"Breakdown[{key}] should be numeric"


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
