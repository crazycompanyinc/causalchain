"""Rank competing root causes by impact, confidence, and fix difficulty."""

from __future__ import annotations

from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.graph.analyzer import CausalGraphAnalyzer


FIX_DIFFICULTY = {
    "config_change": 0.25,
    "deploy": 0.35,
    "traffic_spike": 0.55,
    "metric_anomaly": 0.65,
    "trace_span": 0.65,
    "error": 0.75,
    "business_metric": 0.8,
}


class RootCauseRanker:
    """Score candidate roots for response prioritization."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db
        self.analyzer = CausalGraphAnalyzer(db)

    def rank(self, root_node_ids: list[str], symptom_node_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Return ranked root cause records."""
        symptom_node_ids = symptom_node_ids or []
        ranked = []
        for root_id in root_node_ids:
            node = self.db.get_node(root_id)
            impact = self._impact(root_id)
            confidence = self._confidence(root_id, symptom_node_ids)
            fix_difficulty = float(node.metadata.get("fix_difficulty", FIX_DIFFICULTY.get(node.type, 0.6)))
            score = round((0.45 * impact) + (0.40 * confidence) + (0.15 * (1.0 - fix_difficulty)), 3)
            ranked.append(
                {
                    "node_id": root_id,
                    "source": node.source,
                    "type": node.type,
                    "description": node.description,
                    "impact": round(impact, 3),
                    "confidence": round(confidence, 3),
                    "fix_difficulty": round(fix_difficulty, 3),
                    "score": score,
                }
            )
        return sorted(ranked, key=lambda item: item["score"], reverse=True)

    def _impact(self, root_id: str) -> float:
        reached = {root_id}
        frontier = [root_id]
        edge_confidence = 0.0
        while frontier:
            current = frontier.pop()
            for edge in self.analyzer.outgoing_edges(current, 0.24):
                edge_confidence += edge.confidence
                if edge.target_node_id not in reached:
                    reached.add(edge.target_node_id)
                    frontier.append(edge.target_node_id)
        service_count = len({self.db.get_node(node_id).source for node_id in reached})
        return min(1.0, (0.14 * (len(reached) - 1)) + (0.12 * service_count) + (0.08 * edge_confidence))

    def _confidence(self, root_id: str, symptom_node_ids: list[str]) -> float:
        if not symptom_node_ids:
            outgoing = self.analyzer.outgoing_edges(root_id, 0.24)
            return max([edge.confidence for edge in outgoing], default=0.5)
        path_scores = []
        edges = self.db.list_edges()
        for symptom_id in symptom_node_ids:
            for path in self.analyzer.find_paths(root_id, symptom_id):
                confidences = []
                for source_id, target_id in zip(path, path[1:]):
                    matches = [edge.confidence for edge in edges if edge.source_node_id == source_id and edge.target_node_id == target_id]
                    if matches:
                        confidences.append(max(matches))
                if confidences:
                    path_scores.append(sum(confidences) / len(confidences))
        return max(path_scores, default=0.45)
