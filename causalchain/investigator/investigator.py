"""Trace causal chains for new incidents."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import Incident, parse_timestamp, serialize_timestamp
from causalchain.graph.analyzer import CausalGraphAnalyzer


class IncidentInvestigator:
    """Investigate recent symptoms and identify likely root causes."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db
        self.analyzer = CausalGraphAnalyzer(db)

    def investigate(
        self,
        since: datetime | str,
        affected_services: list[str] | None = None,
        severity: str = "high",
        persist: bool = True,
    ) -> dict[str, Any]:
        """Investigate events since a timestamp."""
        start = parse_timestamp(since)
        services = set(affected_services or [])
        candidates = [
            node
            for node in self.db.list_nodes(start)
            if node.type in {"error", "metric_anomaly"} and (not services or node.source in services)
        ]
        if not candidates:
            return {
                "incident": None,
                "root_causes": [],
                "causal_chain": [],
                "confidence": 0.0,
                "message": "No incident symptoms found in the requested window.",
            }
        symptom = candidates[-1]
        chain_ids = self.analyzer.best_chain_to(symptom.id)
        root_ids = self.analyzer.find_roots([symptom.id])
        confidence = self._chain_confidence(chain_ids)
        affected = sorted({self.db.get_node(node_id).source for node_id in chain_ids})
        incident = Incident(
            title=f"{symptom.source} {symptom.type}: {symptom.description}",
            severity=severity,
            status="investigating",
            root_cause_node_ids=root_ids,
            affected_services=affected,
            causal_chain=chain_ids,
            started_at=self.db.get_node(chain_ids[0]).timestamp,
        )
        if persist:
            self.db.add_incident(incident)
        return {
            "incident": asdict(incident),
            "root_causes": [self._node_dict(node_id) for node_id in root_ids],
            "causal_chain": [self._node_dict(node_id) for node_id in chain_ids],
            "confidence": confidence,
        }

    def _chain_confidence(self, chain_ids: list[str]) -> float:
        if len(chain_ids) < 2:
            return 0.0
        edges = self.db.list_edges()
        scores = []
        for source_id, target_id in zip(chain_ids, chain_ids[1:]):
            matches = [edge.confidence for edge in edges if edge.source_node_id == source_id and edge.target_node_id == target_id]
            if matches:
                scores.append(max(matches))
        return round(sum(scores) / len(scores), 3) if scores else 0.0

    def _node_dict(self, node_id: str) -> dict[str, Any]:
        node = self.db.get_node(node_id)
        data = asdict(node)
        data["timestamp"] = serialize_timestamp(node.timestamp)
        return data

