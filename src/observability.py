"""
observability.py — Metrics emission for memory_heist.

Provides structured metrics tracking for:
- discovery_duration (seconds)
- files_indexed (count)
- chars_rendered_per_role (dict with architect/commander/critic)
- truncation_hit_rates (boolean for each role/component)
- compaction_frequency (count per session)

Metrics can be emitted via callbacks, logged, or returned as a dict.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class DiscoveryMetrics:
    """Metrics for workspace discovery phase."""
    discovery_duration: float = 0.0
    files_indexed: int = 0
    scan_mode: str = "full"  # "full" or "cached"


@dataclass
class RenderingMetrics:
    """Metrics for prompt rendering phase."""
    chars_rendered_per_role: dict[str, int] = field(default_factory=dict)
    truncation_hit_rates: dict[str, bool] = field(default_factory=dict)


@dataclass
class CompactionMetrics:
    """Metrics for session compaction phase."""
    compaction_count: int = 0


@dataclass
class RelevanceMetrics:
    """Metrics for relevance filtering phase."""
    total_candidates: int = 0
    filtered_count: int = 0
    filtering_duration: float = 0.0
    enable_hot_tracking: bool = True
    tier_distribution: dict[str, int] = field(default_factory=dict)
    avg_score: float = 0.0
    max_score: float = 0.0
    min_score: float = 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a JSON-serializable dict."""
        return {
            "total_candidates": self.total_candidates,
            "filtered_count": self.filtered_count,
            "filtering_duration_sec": round(self.filtering_duration, 4),
            "enable_hot_tracking": self.enable_hot_tracking,
            "tier_distribution": self.tier_distribution,
            "avg_score": round(self.avg_score, 4),
            "max_score": round(self.max_score, 4),
            "min_score": round(self.min_score, 4),
        }


@dataclass
class ValidationMetrics:
    """Metrics for config validation phase."""
    configs_validated: int = 0
    configs_trusted: int = 0
    configs_skipped: int = 0
    avg_trust_score: float = 0.0
    trust_scores: list[float] = field(default_factory=list)
    total_score: float = 0.0
    
    def add_result(self, score: float) -> None:
        """Add a validation result to metrics."""
        self.configs_validated += 1
        self.trust_scores.append(score)
        self.total_score += score
        self.avg_trust_score = self.total_score / self.configs_validated if self.configs_validated else 0.0
    
    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a JSON-serializable dict."""
        return {
            "configs_validated": self.configs_validated,
            "configs_trusted": self.configs_trusted,
            "configs_skipped": self.configs_skipped,
            "avg_trust_score": round(self.avg_trust_score, 3),
        }


@dataclass
class MemoryHeistMetrics:
    """All metrics from memory_heist operations."""
    discovery: DiscoveryMetrics = field(default_factory=DiscoveryMetrics)
    rendering: RenderingMetrics = field(default_factory=RenderingMetrics)
    compaction: CompactionMetrics = field(default_factory=CompactionMetrics)
    relevance: RelevanceMetrics = field(default_factory=RelevanceMetrics)
    validation: ValidationMetrics = field(default_factory=ValidationMetrics)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to a JSON-serializable dict."""
        return {
            "discovery": {
                "discovery_duration": self.discovery.discovery_duration,
                "files_indexed": self.discovery.files_indexed,
                "scan_mode": self.discovery.scan_mode,
            },
            "rendering": {
                "chars_rendered_per_role": self.rendering.chars_rendered_per_role,
                "truncation_hit_rates": self.rendering.truncation_hit_rates,
            },
            "compaction": {
                "compaction_count": self.compaction.compaction_count,
            },
            "relevance": {
                "total_candidates": self.relevance.total_candidates,
                "filtered_count": self.relevance.filtered_count,
                "filtering_duration_sec": round(self.relevance.filtering_duration, 4),
                "enable_hot_tracking": self.relevance.enable_hot_tracking,
                "tier_distribution": self.relevance.tier_distribution,
                "avg_score": round(self.relevance.avg_score, 4),
                "max_score": round(self.relevance.max_score, 4),
                "min_score": round(self.relevance.min_score, 4),
            },
            "validation": {
                "configs_validated": self.validation.configs_validated,
                "configs_trusted": self.validation.configs_trusted,
                "configs_skipped": self.validation.configs_skipped,
                "avg_trust_score": round(self.validation.avg_trust_score, 3),
            },
        }


class MetricsEmitter:
    """Callback-based metrics emission."""
    
    def __init__(self, emitter: Callable[[dict[str, Any]], None] | None = None):
        """
        Initialize metrics emitter.
        
        Args:
            emitter: Optional callback to receive metrics. Called with metrics dict.
        """
        self.emitter = emitter
        self._pending_metrics: MemoryHeistMetrics = MemoryHeistMetrics()
    
    def emit(self) -> None:
        """Emit current metrics to the registered callback and reset."""
        if self.emitter:
            metrics = self._pending_metrics.to_dict()
            self.emitter(metrics)
        self._pending_metrics = MemoryHeistMetrics()
    
    def set_discovery(
        self,
        duration: float,
        files_indexed: int,
        scan_mode: str = "full",
    ) -> "MetricsEmitter":
        """Set discovery metrics."""
        self._pending_metrics.discovery = DiscoveryMetrics(
            discovery_duration=duration,
            files_indexed=files_indexed,
            scan_mode=scan_mode,
        )
        return self
    
    def set_rendering(
        self,
        chars_per_role: dict[str, int],
        truncation_hit_rates: dict[str, bool] | None = None,
    ) -> "MetricsEmitter":
        """Set rendering metrics."""
        self._pending_metrics.rendering = RenderingMetrics(
            chars_rendered_per_role=chars_per_role,
            truncation_hit_rates=truncation_hit_rates or {},
        )
        return self
    
    def increment_compaction_count(self) -> "MetricsEmitter":
        """Increment compaction counter."""
        self._pending_metrics.compaction.compaction_count += 1
        return self
    
    def set_relevance(
        self,
        total_candidates: int,
        filtered_count: int,
        filtering_duration: float,
        tier_distribution: dict[str, int] | None = None,
        avg_score: float = 0.0,
        max_score: float = 0.0,
        min_score: float = 0.0,
        enable_hot_tracking: bool = True,
    ) -> "MetricsEmitter":
        """Set relevance filtering metrics."""
        self._pending_metrics.relevance = RelevanceMetrics(
            total_candidates=total_candidates,
            filtered_count=filtered_count,
            filtering_duration=filtering_duration,
            enable_hot_tracking=enable_hot_tracking,
            tier_distribution=tier_distribution or {},
            avg_score=avg_score,
            max_score=max_score,
            min_score=min_score,
        )
        return self
    
    def set_validation(
        self,
        configs_validated: int = 0,
        configs_trusted: int = 0,
        configs_skipped: int = 0,
        avg_trust_score: float = 0.0,
    ) -> "MetricsEmitter":
        """Set validation metrics."""
        self._pending_metrics.validation = ValidationMetrics(
            configs_validated=configs_validated,
            configs_trusted=configs_trusted,
            configs_skipped=configs_skipped,
            avg_trust_score=avg_trust_score,
        )
        return self
    
    def snapshot(self) -> MemoryHeistMetrics:
        """Return a copy of current metrics without emitting."""
        return self._pending_metrics


class SessionMetricsCollector:
    """Collects metrics across a session."""
    
    def __init__(self) -> None:
        self.metrics: list[MemoryHeistMetrics] = []
    
    def record(self, metrics: MemoryHeistMetrics) -> None:
        """Record metrics from a single operation."""
        self.metrics.append(metrics)
    
    def aggregate(self) -> MemoryHeistMetrics:
        """Aggregate all recorded metrics."""
        if not self.metrics:
            return MemoryHeistMetrics()
        
        total_duration = sum(m.discovery.discovery_duration for m in self.metrics)
        total_files = sum(m.discovery.files_indexed for m in self.metrics)
        total_compaction = sum(m.compaction.compaction_count for m in self.metrics)
        
        # Merge chars_per_role by summing
        chars_per_role: dict[str, int] = {}
        for m in self.metrics:
            for role, chars in m.rendering.chars_rendered_per_role.items():
                chars_per_role[role] = chars_per_role.get(role, 0) + chars
        
        # Merge relevance metrics (use last non-default values)
        total_candidates = sum(m.relevance.total_candidates for m in self.metrics)
        total_filtered = sum(m.relevance.filtered_count for m in self.metrics)
        relevance_duration = sum(m.relevance.filtering_duration for m in self.metrics)
        tier_dist = {}
        for m in self.metrics:
            for tier, count in m.relevance.tier_distribution.items():
                tier_dist[tier] = tier_dist.get(tier, 0) + count
        
        return MemoryHeistMetrics(
            discovery=DiscoveryMetrics(
                discovery_duration=total_duration,
                files_indexed=total_files,
                scan_mode=self.metrics[0].discovery.scan_mode,
            ),
            rendering=RenderingMetrics(
                chars_rendered_per_role=chars_per_role or chars_per_role,
                truncation_hit_rates={} if not self.metrics[0].rendering.truncation_hit_rates else self.metrics[0].rendering.truncation_hit_rates,
            ),
            compaction=CompactionMetrics(
                compaction_count=total_compaction,
            ),
            relevance=RelevanceMetrics(
                total_candidates=total_candidates,
                filtered_count=total_filtered,
                filtering_duration=relevance_duration,
                enable_hot_tracking=self.metrics[0].relevance.enable_hot_tracking,
                tier_distribution=tier_dist or {},
                avg_score=0.0,  # Would need weighted average calculation
                max_score=0.0,
                min_score=0.0,
            ),
        )


def create_metrics_emitter() -> MetricsEmitter:
    """Factory function to create a new MetricsEmitter."""
    return MetricsEmitter()
