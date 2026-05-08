"""Minute-by-minute incident timeline reconstruction."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import Incident, serialize_timestamp


class TimelineReconstructor:
    """Build incident timelines with causal links per event."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db

    def reconstruct(self, incident: Incident | str) -> list[dict[str, Any]]:
        """Return timeline buckets keyed by minute."""
        incident_obj = self.db.get_incident(incident) if isinstance(incident, str) else incident
        chain_ids = set(incident_obj.causal_chain)
        nodes = [self.db.get_node(node_id) for node_id in incident_obj.causal_chain]
        edges = [edge for edge in self.db.list_edges() if edge.source_node_id in chain_ids and edge.target_node_id in chain_ids]
        incoming = defaultdict(list)
        outgoing = defaultdict(list)
        for edge in edges:
            incoming[edge.target_node_id].append(edge)
            outgoing[edge.source_node_id].append(edge)
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            minute = node.timestamp.replace(second=0, microsecond=0)
            buckets[serialize_timestamp(minute)].append(
                {
                    "node_id": node.id,
                    "timestamp": serialize_timestamp(node.timestamp),
                    "source": node.source,
                    "type": node.type,
                    "description": node.description,
                    "caused_by": [edge.source_node_id for edge in incoming[node.id]],
                    "causes": [edge.target_node_id for edge in outgoing[node.id]],
                    "strongest_link": max([edge.confidence for edge in incoming[node.id] + outgoing[node.id]], default=0.0),
                }
            )
        return [{"minute": minute, "events": events} for minute, events in sorted(buckets.items())]
