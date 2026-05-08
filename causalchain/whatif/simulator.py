"""Deterministic what-if simulation over the causal graph."""

from __future__ import annotations

from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.graph.analyzer import CausalGraphAnalyzer
from causalchain.ranking import RootCauseRanker


class WhatIfSimulator:
    """Estimate downstream causal impact of hypothetical actions."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db
        self.analyzer = CausalGraphAnalyzer(db)

    def simulate(self, action: str, target: str | None = None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Simulate a rollback, config revert, traffic shed, or generic mitigation."""
        metadata = metadata or {}
        candidates = self._candidate_nodes(action, target, metadata)
        affected = sorted({node_id for candidate in candidates for node_id in self._downstream(candidate)})
        baseline = RootCauseRanker(self.db).rank(candidates, affected)
        action_strength = self._action_strength(action)
        avoided_edges = [edge for edge in self.db.list_edges() if edge.source_node_id in candidates or edge.target_node_id in affected]
        risk_reduction = min(0.95, action_strength * (sum(edge.confidence for edge in avoided_edges) / max(1, len(avoided_edges))))
        return {
            "action": action,
            "target": target,
            "candidate_root_ids": candidates,
            "affected_node_ids": affected,
            "affected_services": sorted({self.db.get_node(node_id).source for node_id in affected}),
            "estimated_risk_reduction": round(risk_reduction, 3),
            "ranked_roots": baseline,
            "recommendation": self._recommendation(action, risk_reduction),
        }

    def _candidate_nodes(self, action: str, target: str | None, metadata: dict[str, Any]) -> list[str]:
        wanted_version = metadata.get("version") or target
        matches = []
        for node in self.db.list_nodes():
            if target and target not in {node.source, str(node.metadata.get("version")), node.description}:
                if target not in node.description:
                    continue
            if action.startswith("rollback") and node.type != "deploy":
                continue
            if action.startswith("revert") and node.type != "config_change":
                continue
            if wanted_version and wanted_version not in {str(node.metadata.get("version")), node.description} and wanted_version not in node.description:
                continue
            matches.append(node.id)
        if matches:
            return matches
        return [node.id for node in self.db.list_nodes() if node.type in {"deploy", "config_change"}][:1]

    def _downstream(self, node_id: str) -> set[str]:
        reached = {node_id}
        frontier = [node_id]
        while frontier:
            current = frontier.pop()
            for edge in self.analyzer.outgoing_edges(current, 0.24):
                if edge.target_node_id not in reached:
                    reached.add(edge.target_node_id)
                    frontier.append(edge.target_node_id)
        return reached

    def _action_strength(self, action: str) -> float:
        if "rollback" in action:
            return 0.9
        if "revert" in action:
            return 0.82
        if "shed" in action or "rate_limit" in action:
            return 0.65
        return 0.5

    def _recommendation(self, action: str, risk_reduction: float) -> str:
        if risk_reduction >= 0.55:
            return f"Proceed with {action}; projected causal risk reduction is material."
        if risk_reduction >= 0.25:
            return f"{action} may help, but pair it with monitoring and a narrower blast radius."
        return f"Do not rely on {action} alone; causal evidence for impact is weak."
