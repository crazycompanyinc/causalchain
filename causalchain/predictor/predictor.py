"""Predict potential incidents from current causal state."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import parse_timestamp, serialize_timestamp, utc_now


class CausalPredictor:
    """Match recent graph state against learned patterns."""

    def __init__(self, db: CausalChainDB, lookback_minutes: int = 15) -> None:
        if lookback_minutes <= 0:
            raise ValueError("lookback_minutes must be positive")
        self.db = db
        self.lookback = timedelta(minutes=lookback_minutes)

    def predict(self) -> list[dict[str, Any]]:
        """Return potential next incidents based on partial pattern matches."""
        since = utc_now() - self.lookback
        recent = [
            node
            for node in self.db.list_nodes(since)
            if node.type not in {"business_metric", "agent_action", "prediction"}
        ]
        predictions: list[dict[str, Any]] = []
        for pattern in self.db.list_patterns():
            prefix_length = self._matching_prefix([node.type for node in recent], pattern.node_sequence)
            if 0 < prefix_length < len(pattern.node_sequence):
                observed = recent[-prefix_length:]
                remaining = pattern.node_sequence[prefix_length:]
                confidence = round(pattern.confidence * (prefix_length / len(pattern.node_sequence)), 3)
                horizon_seconds = max(60.0, pattern.typical_duration * (len(remaining) / len(pattern.node_sequence)))
                predictions.append(
                    {
                        "pattern_name": pattern.name,
                        "confidence": confidence,
                        "predicted_events": remaining,
                        "time_horizon": f"{int(horizon_seconds // 60)}m {int(horizon_seconds % 60)}s",
                        "observed_events": [node.id for node in observed],
                    }
                )
        return sorted(predictions, key=lambda item: item["confidence"], reverse=True)

    def _matching_prefix(self, recent_types: list[str], pattern_sequence: list[str]) -> int:
        best = 0
        for length in range(1, min(len(recent_types), len(pattern_sequence)) + 1):
            if recent_types[-length:] == pattern_sequence[:length]:
                best = length
        return best

    def state_summary(self) -> dict[str, Any]:
        """Return a compact recent-state summary."""
        since = utc_now() - self.lookback
        nodes = self.db.list_nodes(since)
        return {
            "since": serialize_timestamp(parse_timestamp(since)),
            "recent_event_count": len(nodes),
            "sources": sorted({node.source for node in nodes}),
        }
