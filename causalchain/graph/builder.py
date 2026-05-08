"""Build causal graphs from event streams."""

from __future__ import annotations

from datetime import timedelta
from difflib import SequenceMatcher
from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalEdge, CausalNode, CausalPattern, parse_timestamp


DEFAULT_DEPENDENCIES: dict[str, list[str]] = {
    "api-gateway": ["payment-service", "redis", "load-balancer"],
    "payment-service": ["redis", "api-gateway"],
    "load-balancer": ["api-gateway"],
    "checkout-service": ["payment-service", "redis"],
}

TYPE_COMPATIBILITY: dict[tuple[str, str], tuple[str, float]] = {
    ("deploy", "metric_anomaly"): ("triggers", 0.85),
    ("deploy", "error"): ("triggers", 0.80),
    ("deploy", "traffic_spike"): ("enables", 0.35),
    ("config_change", "metric_anomaly"): ("triggers", 0.80),
    ("config_change", "error"): ("triggers", 0.78),
    ("traffic_spike", "metric_anomaly"): ("triggers", 0.65),
    ("traffic_spike", "error"): ("triggers", 0.62),
    ("metric_anomaly", "error"): ("degrades", 0.82),
    ("metric_anomaly", "metric_anomaly"): ("correlates_with", 0.55),
    ("error", "error"): ("triggers", 0.56),
    ("error", "metric_anomaly"): ("degrades", 0.45),
    ("error", "recovery"): ("blocks", 0.30),
    ("recovery", "metric_anomaly"): ("blocks", 0.40),
    ("recovery", "error"): ("blocks", 0.40),
}


class CausalGraphBuilder:
    """Create causal nodes and infer explainable causal edges."""

    def __init__(
        self,
        db: CausalChainDB,
        dependencies: dict[str, list[str]] | None = None,
        time_window_minutes: int = 5,
    ) -> None:
        if time_window_minutes <= 0:
            raise ValueError("time_window_minutes must be positive")
        self.db = db
        self.dependencies = dependencies or DEFAULT_DEPENDENCIES
        self.time_window = timedelta(minutes=time_window_minutes)

    def ingest_event(
        self,
        type: str,
        source: str,
        description: str,
        timestamp: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> CausalNode:
        """Create a node and infer causal edges involving nearby prior events."""
        node = self.db.add_node(CausalNode(type, source, description, timestamp, metadata or {}))
        self.build_edges_for_node(node)
        return node

    def build_edges_for_node(self, node: CausalNode) -> list[CausalEdge]:
        """Infer edges from previous nodes into a new node."""
        edges: list[CausalEdge] = []
        for prior in self.db.list_nodes():
            if prior.id == node.id:
                continue
            candidate = self.infer_edge(prior, node, self.db.list_patterns())
            if candidate is not None:
                edges.append(self.db.add_edge(candidate))
        return edges

    def rebuild_edges(self) -> list[CausalEdge]:
        """Rebuild inferred edges for all nodes currently in the database."""
        edges: list[CausalEdge] = []
        patterns = self.db.list_patterns()
        nodes = self.db.list_nodes()
        for source in nodes:
            for target in nodes:
                if source.id == target.id:
                    continue
                edge = self.infer_edge(source, target, patterns)
                if edge:
                    edges.append(self.db.add_edge(edge))
        return edges

    def infer_edge(
        self,
        source: CausalNode,
        target: CausalNode,
        patterns: list[CausalPattern] | None = None,
    ) -> CausalEdge | None:
        """Infer a causal edge from source to target, if evidence is strong enough."""
        source_time = parse_timestamp(source.timestamp)
        target_time = parse_timestamp(target.timestamp)
        if source_time >= target_time:
            return None
        gap = target_time - source_time
        if gap > self.time_window:
            return None
        compatibility = TYPE_COMPATIBILITY.get((source.type, target.type))
        if compatibility is None:
            return None

        edge_type, type_score = compatibility
        temporal_score = max(0.0, 1.0 - (gap.total_seconds() / self.time_window.total_seconds()))
        dependency_score = self._dependency_score(source.source, target.source)
        change_score = self._change_score(source, gap)
        pattern_score = self._pattern_score(source.type, target.type, patterns or [])
        metric_score = self._metric_score(source, target)

        weights = {
            "temporal_score": 0.22,
            "dependency_score": 0.23,
            "change_score": 0.18,
            "pattern_score": 0.22,
            "metric_score": 0.15,
        }
        evidence = {
            "type_compatibility": type_score,
            "time_gap_seconds": gap.total_seconds(),
            "temporal_score": round(temporal_score, 3),
            "dependency_score": round(dependency_score, 3),
            "change_score": round(change_score, 3),
            "pattern_score": round(pattern_score, 3),
            "metric_score": round(metric_score, 3),
            "reason": self._reason(source, target, edge_type),
        }
        signal_score = sum(evidence[name] * weight for name, weight in weights.items())
        confidence = min(1.0, max(0.0, (0.25 * type_score) + (0.75 * signal_score)))
        if confidence < 0.24:
            return None
        return CausalEdge(source.id, target.id, edge_type, round(confidence, 3), evidence)

    def _dependency_score(self, source: str, target: str) -> float:
        if source == target:
            return 0.65
        target_deps = self.dependencies.get(target, [])
        source_deps = self.dependencies.get(source, [])
        if source in target_deps:
            return 1.0
        if target in source_deps:
            return 0.55
        if set(target_deps).intersection(source_deps):
            return 0.35
        return 0.10

    def _change_score(self, source: CausalNode, gap: timedelta) -> float:
        if source.type not in {"deploy", "config_change"}:
            return 0.0
        minutes = gap.total_seconds() / 60.0
        return max(0.15, 1.0 - (minutes / 10.0))

    def _pattern_score(self, source_type: str, target_type: str, patterns: list[CausalPattern]) -> float:
        if not patterns:
            return 0.0
        best = 0.0
        for pattern in patterns:
            sequence = pattern.node_sequence
            for idx in range(len(sequence) - 1):
                if sequence[idx] == source_type and sequence[idx + 1] == target_type:
                    best = max(best, pattern.confidence)
        return best

    def _metric_score(self, source: CausalNode, target: CausalNode) -> float:
        source_metric = source.metadata.get("metric")
        target_metric = target.metadata.get("metric")
        if source_metric and source_metric == target_metric:
            return 1.0
        if source.type == "metric_anomaly" or target.type == "metric_anomaly":
            ratio = SequenceMatcher(None, source.description.lower(), target.description.lower()).ratio()
            return max(0.35, min(1.0, ratio))
        return 0.15

    def _reason(self, source: CausalNode, target: CausalNode, edge_type: str) -> str:
        return f"{source.type} on {source.source} plausibly {edge_type} {target.type} on {target.source}"

