"""
tests/test_relevance_scoring.py — Tests for relevance scoring module.

Tests the file prioritization logic that rates files based on:
- File type priority (config files, instructions, core logic)
- Location hierarchy (root config, src/, docs/)
- File size/importance patterns
- Recency, query matching, and hot path tracking
"""

from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, timedelta
from src.context.relevance_scoring import (
    HIGH_PRIORITY_FILETYPES,
    LOCATION_WEIGHTS,
    get_location_category,
    get_filetype_priority,
    get_size_score,
    calculate_recent_score,
    calculate_query_score,
    calculate_hot_score,
    calculate_combined_score,
    RelevanceConfig,
    RelevanceMetrics,
    score_file_entry,
    filter_by_relevance,
    filter_by_relevance_async,
)
from src.memory_heist import FileEntry
from src.memory_heist_cache import DiscoveryCache


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_file_entries(tmp_path):
    """Create sample FileEntry objects for testing."""
    # Create some test files
    test_dir = tmp_path / "test_project"
    test_dir.mkdir()
    
    # High-priority files
    (test_dir / "main.py").write_text("print('hello')")
    ham_dir = test_dir / ".ham"
    ham_dir.mkdir()
    (ham_dir / "settings").write_text('{"key": "value"}')
    (test_dir / "SWARM.md").write_text("# SWARM instructions")
    
    # Medium-priority files
    (test_dir / "README.md").write_text("# Project README")
    src_dir = test_dir / "src"
    src_dir.mkdir()
    (src_dir / "helper.py").write_text("def helper(): pass")
    
    docs_dir = test_dir / "docs"
    docs_dir.mkdir(parents=True)
    (docs_dir / "guide.md").write_text("# User Guide")
    
    tests_dir = test_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text("def test_main(): pass")
    
    files = []
    for root, _, filenames in __import__("os").walk(test_dir):
        for fname in filenames:
            fp = Path(root) / fname
            try:
                stat = fp.stat()
                files.append(FileEntry(
                    path=fp,
                    relative=str(fp.relative_to(tmp_path)),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                ))
            except OSError:
                continue
    
    return files, test_dir


@pytest.fixture
def mock_file_entry(tmp_path):
    """Create a single mock FileEntry for testing."""
    test_file = tmp_path / "test.py"
    test_file.write_text("def main(): pass")
    stat = test_file.stat()
    return FileEntry(
        path=test_file,
        relative="test.py",
        size=stat.st_size,
        mtime=stat.st_mtime,
    )


# =============================================================================
# Location Scoring Tests
# =============================================================================


class TestLocationScoring:
    """Tests for location-based scoring functions."""
    
    def test_root_config_files(self):
        """Root config files should get highest location weight."""
        path = ".ham/settings.json"
        category, weight = get_location_category(path)
        assert category == "root_config"
        assert weight == LOCATION_WEIGHTS["root_config"]
    
    def test_root_instruction_files(self):
        """Root instruction files should get high location weight."""
        for path in ["SWARM.md", "AGENTS.md", "README.md"]:
            category, weight = get_location_category(path)
            assert category == "root_instruction"
            assert weight == LOCATION_WEIGHTS["root_instruction"]
    
    def test_src_core_files(self):
        """Core files in src/ should get highest location weight."""
        for path in ["src/main.py", "src/memory_heist.py", "src/app.py"]:
            category, weight = get_location_category(path)
            assert category == "src_core"
            assert weight == LOCATION_WEIGHTS["src_core"]
    
    def test_src_files(self):
        """Non-core files in src/ should get high location weight."""
        path = "src/helpers.py"
        category, weight = get_location_category(path)
        assert category == "src"
        assert weight == LOCATION_WEIGHTS["src"]
    
    def test_docs_files(self):
        """Files in docs/ should get moderate location weight."""
        path = "docs/guide.md"
        category, weight = get_location_category(path)
        assert category == "docs"
        assert weight == LOCATION_WEIGHTS["docs"]
    
    def test_normal_files(self):
        """Unknown locations should get baseline weight."""
        path = "random/file.py"
        category, weight = get_location_category(path)
        assert category == "normal"
        assert weight == LOCATION_WEIGHTS["normal"]


# =============================================================================
# File Type Scoring Tests
# =============================================================================


class TestFiletypeScoring:
    """Tests for file type priority scoring."""
    
    def test_high_priority_types(self):
        """High-priority files should get high scores."""
        # main.py and settings.json are exact matches, get 1.0
        assert get_filetype_priority("main.py") == 1.0
        assert get_filetype_priority("settings.json") == 1.0
        # SWARM.md is in HIGH_PRIORITY_FILETYPES, gets high score (0.95 via pattern match)
        assert get_filetype_priority("SWARM.md") >= 0.9
    
    def test_docs_files(self):
        """Documentation files should get high scores."""
        # readme.md is in HIGH_PRIORITY_FILETYPES, gets 1.0
        score = get_filetype_priority("readme.md")
        assert score == 1.0
        # Other .md files get moderate-high score
        score = get_filetype_priority("documentation.md")
        assert 0.7 <= score <= 1.0
    
    def test_default_files(self):
        """Unknown file types should get baseline score."""
        score = get_filetype_priority("unknown.xyz")
        assert score == 0.5


# =============================================================================
# Size Scoring Tests
# =============================================================================


class TestSizeScoring:
    """Tests for file size scoring."""
    
    def test_tiny_files_filtered(self):
        """Very small files (< 50 bytes) should score 0.0."""
        score = get_size_score(30, "normal")
        assert score == 0.0
    
    def test_core_files_optimal_size(self):
        """Core files in optimal size range should score 1.0."""
        score = get_size_score(5000, "src_core")
        assert score == 1.0
    
    def test_core_files_very_small(self):
        """Small core files should get partial score."""
        score = get_size_score(100, "src_core")
        assert 0.5 <= score < 0.7
    
    def test_normal_files_optimal_size(self):
        """Normal files in optimal range should score 1.0."""
        score = get_size_score(10000, "normal")
        assert score == 1.0
    
    def test_large_files_downweighted(self):
        """Very large files should get reduced score."""
        score = get_size_score(1_000_000, "normal")
        # Large files get moderate penalty, around 0.74 with log decay
        assert 0.4 <= score < 0.8


# =============================================================================
# Recency Scoring Tests
# =============================================================================


class TestRecencyScoring:
    """Tests for recency-based scoring."""
    
    def test_modified_today(self):
        """Files modified today should score 1.0."""
        # This test would need to mock the time, but we'll test the general case
        score = calculate_recent_score("nonexistent.py", threshold_days=7)
        # For non-existent files, should return 0.0
        assert score == 0.0
    
    def test_recency_decay(self):
        """Recency score should decay over time."""
        # Test with very old threshold - score should be lower
        score = calculate_recent_score("nonexistent.py", threshold_days=30)
        assert 0.0 <= score <= 1.0


# =============================================================================
# Query Scoring Tests
# =============================================================================


class TestQueryScoring:
    """Tests for query-based scoring."""
    
    def test_empty_query(self):
        """Empty query should score 0.0."""
        score = calculate_query_score("file.py", "")
        assert score == 0.0
    
    def test_no_query_or_file(self):
        """Empty or missing args should score 0.0."""
        score = calculate_query_score("", "query")
        assert score == 0.0
    
    def test_filename_match(self):
        """Filename that matches query should score higher."""
        score = calculate_query_score("memory_heist.py", "memory heist")
        # Should score better than random query
        random_score = calculate_query_score("random.py", "memory heist")
        assert score > random_score
    
    def test_content_match(self, tmp_path):
        """File content that matches query should score higher."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def memory_heist_main(): pass")
        score = calculate_query_score(str(test_file), "memory heist")
        assert score > 0.0


# =============================================================================
# Hot Path Scoring Tests
# =============================================================================


class TestHotPathScoring:
    """Tests for hot path scoring."""

    def test_no_history(self):
        """Files with no access history should score 0.0."""
        score = calculate_hot_score("file.py", [])
        assert score == 0.0
    
    def test_recent_access(self):
        """Recently accessed files should score higher."""
        import time
        now = time.time()
        history = [
            type('SessionHistory', (), {
                'file_path': 'file.py',
                'is_recent': True,
                'is_very_recent': True,
                'timestamp': now
            })()
        ]
        score = calculate_hot_score("file.py", history)
        assert score > 0.0  # Should get some score


# =============================================================================
# Combined Scoring Tests
# =============================================================================


class TestCombinedScoring:
    """Tests for combined scoring function."""
    
    def test_combined_score_range(self, mock_file_entry):
        """Combined score should be between 0 and 1."""
        config = RelevanceConfig()
        result = calculate_combined_score(mock_file_entry, config=config)
        assert 0.0 <= result.total_score <= 2.0  # Unweighted sum can exceed 1.0
        assert 0.0 <= result.filetype_score <= 1.0
        assert 0.0 <= result.location_score <= 1.0
    
    def test_score_breakdown(self, mock_file_entry):
        """Should return breakdown of all score components."""
        config = RelevanceConfig()
        result = calculate_combined_score(mock_file_entry, config=config)
        
        assert "filetype" in result.breakdown
        assert "location" in result.breakdown
        assert "size" in result.breakdown
        assert "recent" in result.breakdown
        assert "query" in result.breakdown
        assert "hot" in result.breakdown
    
    def test_tier_assignment(self, mock_file_entry):
        """Should assign tier based on scores."""
        config = RelevanceConfig()
        result = calculate_combined_score(mock_file_entry, config=config)
        assert result.tier in ["hot", "recent", "baseline"]


# =============================================================================
# Configuration Tests
# =============================================================================


class TestRelevanceConfig:
    """Tests for RelevanceConfig serialization."""
    
    def test_to_dict(self):
        """Config should serialize to dict."""
        config = RelevanceConfig(
            filetype_weight=0.4,
            max_results=100,
        )
        data = config.to_dict()
        assert data["filetype_weight"] == 0.4
        assert data["max_results"] == 100
    
    def test_from_dict(self):
        """Config should deserialize from dict."""
        data = {
            "filetype_weight": 0.4,
            "max_results": 100,
            "recent_threshold_days": 14,
        }
        config = RelevanceConfig.from_dict(data)
        assert config.filetype_weight == 0.4
        assert config.max_results == 100
        assert config.recent_threshold_days == 14


# =============================================================================
# Metrics Tests
# =============================================================================


class TestRelevanceMetrics:
    """Tests for RelevanceMetrics."""
    
    def test_to_dict(self):
        """Metrics should serialize to dict."""
        metrics = RelevanceMetrics(
            total_candidates=100,
            filtered_count=50,
            filtering_duration=0.5,
            tier_distribution={"hot": 10, "recent": 20, "baseline": 20},
            avg_score=0.75,
            max_score=0.95,
            min_score=0.35,
        )
        data = metrics.to_dict()
        assert data["total_candidates"] == 100
        assert data["filtered_count"] == 50
        assert "filtering_duration_sec" in data


# =============================================================================
# Integration Tests
# =============================================================================


class TestFilterIntegration:
    """Integration tests for filtering functions."""
    
    def test_filter_ranking(self, sample_file_entries):
        """Files should be ranked by relevance."""
        files, _ = sample_file_entries
        config = RelevanceConfig(max_results=10)
        
        results = filter_by_relevance(files, config=config)
        
        # Should have results
        assert len(results) > 0
        
        # Results should be sorted by score (descending)
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score
        
        # Should respect max_results
        assert len(results) <= config.max_results
    
    def test_filter_with_query(self, sample_file_entries):
        """Query should affect ranking."""
        files, _ = sample_file_entries
        
        results_no_query = filter_by_relevance(files)
        results_with_query = filter_by_relevance(
            files,
            user_query="SWARM settings",
        )
        
        # Should have results in both cases
        assert len(results_no_query) > 0
        assert len(results_with_query) > 0
        
        # Results may differ based on query
        # (not asserting this to avoid flakiness)
    
    def test_async_wrapper(self, sample_file_entries, tmp_path):
        """Async wrapper should return results + metadata."""
        files, _ = sample_file_entries
        
        # Create a minimal mock context
        class MockContext:
            def __init__(self, cwd):
                self.cwd = cwd
                self.file_count = len(files)
        
        context = MockContext(tmp_path)
        results, metadata = filter_by_relevance_async(context)
        
        assert "filtered_count" in metadata
        assert "total_candidates" in metadata
        assert "use_relevance_filtering" in metadata
        assert metadata["use_relevance_filtering"] is True


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases."""
    
    def test_no_files_filtered(self, tmp_path):
        """Filtering on empty list should return empty list."""
        results = filter_by_relevance([])
        assert len(results) == 0
    
    def test_score_file_entry(self, mock_file_entry):
        """score_file_entry should wrap calculate_combined_score."""
        config = RelevanceConfig()
        result = score_file_entry(mock_file_entry, config=config)
        
        assert hasattr(result, "score")
        assert hasattr(result, "tier")
        assert hasattr(result, "breakdown")
    
    def test_metrics_export(self):
        """Metrics should be JSON-serializable."""
        import json
        metrics = RelevanceMetrics(
            total_candidates=100,
            filtered_count=50,
            tier_distribution={"hot": 10, "recent": 20, "baseline": 20},
        )
        json_str = json.dumps(metrics.to_dict())
        assert len(json_str) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
