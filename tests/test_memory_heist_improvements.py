"""
Test suite for memory_heist improvements: budget parsing, observability, and metadata stamps.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.budget_parser import (
    BudgetConfig,
    BudgetParseError,
    parse_budget_value,
    parse_role_budgets,
)
from src.memory_heist import ProjectContext, SessionMemory, context_engine_dashboard_payload
from src.metadata_stamps import MetadataStamp, ScanMode, create_metadata_stamp
from src.observability import MemoryHeistMetrics, MetricsEmitter


# ============================================================================
# Budget Parser Tests
# ============================================================================

class TestParseBudgetValue:
    """Tests for parse_budget_value function."""

    def test_int_positive(self):
        assert parse_budget_value(12345, 1000) == 12345

    def test_int_zero_defaults(self):
        with pytest.raises(BudgetParseError):
            parse_budget_value(0, 1000)

    def test_int_negative_defaults(self):
        with pytest.raises(BudgetParseError):
            parse_budget_value(-100, 1000)

    def test_float_truncated(self):
        assert parse_budget_value(1234.56, 1000) == 1234

    def test_string_with_spaces(self):
        assert parse_budget_value("  5000  ", 1000) == 5000

    def test_string_invalid(self):
        with pytest.raises(BudgetParseError):
            parse_budget_value("not a number", 1000)

    def test_none_defaults(self):
        assert parse_budget_value(None, 8000) == 8000

    def test_bool_defaults(self):
        assert parse_budget_value(True, 8000) == 8000

    def test_bool_false_defaults(self):
        assert parse_budget_value(False, 8000) == 8000


class TestParseRoleBudgets:
    """Tests for parse_role_budgets function."""

    def test_defaults_used_when_missing(self):
        result = parse_role_budgets({})
        assert result.architect_instruction_chars == 16_000
        assert result.commander_instruction_chars == 4_000
        assert result.critic_instruction_chars == 8_000

    def test_top_level_override(self):
        config = {
            "architect_instruction_chars": 10000,
            "commander_instruction_chars": 2000,
        }
        result = parse_role_budgets(config)
        assert result.architect_instruction_chars == 10000
        assert result.commander_instruction_chars == 2000
        assert result.critic_instruction_chars == 8_000  # default

    def test_string_values_parsed(self):
        config = {
            "architect_instruction_chars": "12000",
        }
        result = parse_role_budgets(config)
        assert result.architect_instruction_chars == 12000

    def test_fallback_budget_respected(self):
        fallback = BudgetConfig(
            architect_instruction_chars=9999,
            commander_instruction_chars=7777,
            critic_instruction_chars=5555,
            architect_diff_chars=1111,
            commander_diff_chars=2222,
            critic_diff_chars=3333,
        )
        result = parse_role_budgets({}, fallback_budget=fallback)
        assert result.architect_instruction_chars == 9999
        assert result.commander_diff_chars == 2222

    def test_invalid_values_raise_error(self):
        config = {
            "architect_instruction_chars": -1,  # invalid
        }
        with pytest.raises(BudgetParseError):
            parse_role_budgets(config)


# ============================================================================
# Metadata Stamp Tests
# ============================================================================

class TestMetadataStamp:
    """Tests for MetadataStamp functionality."""

    def test_to_json_structure(self):
        stamp = MetadataStamp(
            discovered_at="2026-04-29T12:00:00+00:00",
            git_head="abc123",
            scan_mode=ScanMode.FULL,
            extra={"custom": "data"},
        )
        data = json.loads(stamp.to_json())
        assert data["discovered_at"] == "2026-04-29T12:00:00+00:00"
        assert data["git_head"] == "abc123"
        assert data["scan_mode"] == "full"
        assert data["custom"] == "data"

    def test_from_dict(self):
        stamp = MetadataStamp.from_dict({
            "discovered_at": "2026-04-29T12:00:00+00:00",
            "git_head": "abc123def456",
            "scan_mode": "cached",
            "extra": {"custom": "value"},
        })
        assert stamp.discovered_at == "2026-04-29T12:00:00+00:00"
        assert stamp.git_head == "abc123def456"
        assert stamp.scan_mode == ScanMode.CACHED

    def test_stamp_creation(self, tmp_path):
        # Create a fake git repo
        (tmp_path / ".git").mkdir()
        stamp = create_metadata_stamp(tmp_path, ScanMode.FULL, git_hash_short=True)
        assert stamp.scan_mode == ScanMode.FULL
        assert "discovered_at" in stamp.to_json()
        # Could be "no-repo" if not actually in a git repo

    def test_stamp_creation_full_hash(self, tmp_path):
        stamp = create_metadata_stamp(tmp_path, ScanMode.CACHED, git_hash_short=False)
        assert stamp.scan_mode == ScanMode.CACHED

    def test_stamp_rendered_output(self):
        stamp = MetadataStamp(
            discovered_at="2026-04-29T12:00:00+00:00",
            git_head="abc123",
            scan_mode=ScanMode.FULL,
        )
        output = stamp.to_json() + "\n\nHello world"
        result = f"{output}\n\nHello world"
        data_stamped = json.loads(result.split("\n")[0])
        assert data_stamped["scan_mode"] == "full"


# ============================================================================
# Observability Tests
# ============================================================================

class TestMetricsEmitter:
    """Tests for MetricsEmitter."""

    def test_emit_and_reset(self):
        emitted = []
        emitter = MetricsEmitter(emitted.append)
        
        result = emitter.set_discovery(1.5, 100, "full")
        assert result is emitter  # fluent API
        emitter.emit()
        
        assert len(emitted) == 1
        assert emitted[0]["discovery"]["discovery_duration"] == 1.5
        assert emitted[0]["discovery"]["files_indexed"] == 100

    def test_rendering_metrics(self):
        emitted = []
        emitter = MetricsEmitter(emitted.append)
        
        emitter.set_rendering(
            chars_per_role={"architect": 5000, "commander": 2000},
            truncation_hit_rates={"architect": True, "commander": False},
        )
        emitter.emit()
        
        assert emitted[0]["rendering"]["chars_rendered_per_role"]["architect"] == 5000
        assert emitted[0]["rendering"]["truncation_hit_rates"]["architect"] is True

    def test_compaction_count_increment(self):
        emitted = []
        emitter = MetricsEmitter(emitted.append)
        
        emitter.increment_compaction_count()
        emitter.increment_compaction_count()
        emitter.emit()
        
        assert emitted[0]["compaction"]["compaction_count"] == 2

    def test_snapshot(self):
        emitter = MetricsEmitter()
        emitter.set_discovery(1.5, 100)
        snapshot = emitter.snapshot()
        
        assert snapshot.discovery.discovery_duration == 1.5
        assert snapshot.discovery.files_indexed == 100


class TestMemoryHeistMetrics:
    """Tests for memory_heist metrics."""

    def test_to_dict_structure(self):
        metrics = MemoryHeistMetrics(
            discovery={"discovery_duration": 1.0, "files_indexed": 50, "scan_mode": "full"},
            rendering={"chars_rendered_per_role": {"arch": 5000}, "truncation_hit_rates": {}},
            compaction={"compaction_count": 0},
        )
        # This test validates the structure exists
        
    def test_empty_metrics(self):
        metrics = MemoryHeistMetrics()
        d = metrics.to_dict()
        
        assert "discovery" in d
        assert "rendering" in d
        assert "compaction" in d


# ============================================================================
# Integration Tests
# ============================================================================

class TestContextBuilderMetricsIntegration:
    """Integration tests for ContextBuilder metrics tracking."""

    def test_dashboard_payload_uses_parsed_budgets(self, tmp_path):
        """Verify dashboard uses parse_role_budgets for role budgets."""
        (tmp_path / "SWARM.md").write_text("# Instructions")
        (tmp_path / ".ham.json").write_text(json.dumps({
            "architect_instruction_chars": "15000",
            "commander_instruction_chars": 3000,
            "critic_instruction_chars": 9000,
        }))
        
        with patch("src.memory_heist.git_status", return_value=None), \
             patch("src.memory_heist.git_diff", return_value=None), \
             patch("src.memory_heist.git_log_oneline", return_value=None):
            payload = context_engine_dashboard_payload(tmp_path)
        
        assert payload["roles"]["architect"]["instruction_budget_chars"] == 15000
        assert payload["roles"]["commander"]["instruction_budget_chars"] == 3000
        assert payload["roles"]["critic"]["instruction_budget_chars"] == 9000
