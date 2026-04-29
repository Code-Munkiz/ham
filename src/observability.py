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
class MemoryHeistMetrics:
    """All metrics from memory_heist operations."""
    discovery: DiscoveryMetrics = field(default_factory=DiscoveryMetrics)
    rendering: RenderingMetrics = field(default_factory=RenderingMetrics)
    compaction: CompactionMetrics = field(default_factory=CompactionMetrics)
    
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
        )


def create_metrics_emitter() -> MetricsEmitter:
    """Factory function to create a new MetricsEmitter."""
    return MetricsEmitter()
