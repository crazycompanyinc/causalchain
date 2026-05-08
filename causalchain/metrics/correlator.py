"""Correlate causal incidents with business metrics."""

from __future__ import annotations

from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalNode


class BusinessMetricCorrelator:
    """Estimate business impact from metric nodes linked to an incident window."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db

    def ingest_metric(self, name: str, value: float, baseline: float, source: str = "business", timestamp: Any = None, revenue_per_unit: float = 0.0) -> CausalNode:
        """Persist a business metric observation."""
        delta_pct = 0.0 if baseline == 0 else ((value - baseline) / baseline) * 100.0
        return self.db.add_node(
            CausalNode(
                "business_metric",
                source,
                f"{name} changed {delta_pct:.1f}% from baseline",
                timestamp,
                {"metric": name, "value": value, "baseline": baseline, "delta_pct": delta_pct, "revenue_per_unit": revenue_per_unit},
            )
        )

    def impact_for_incident(self, incident_id: str) -> dict[str, Any]:
        """Return correlated business impact for an incident."""
        incident = self.db.get_incident(incident_id)
        metrics = [
            node
            for node in self.db.list_nodes(incident.started_at)
            if node.type == "business_metric" and (incident.resolved_at is None or node.timestamp <= incident.resolved_at)
        ]
        lost_revenue = 0.0
        rows = []
        for node in metrics:
            value = float(node.metadata.get("value", 0.0))
            baseline = float(node.metadata.get("baseline", 0.0))
            revenue_per_unit = float(node.metadata.get("revenue_per_unit", 0.0))
            loss = max(0.0, baseline - value) * revenue_per_unit
            lost_revenue += loss
            rows.append(
                {
                    "node_id": node.id,
                    "metric": node.metadata.get("metric"),
                    "delta_pct": round(float(node.metadata.get("delta_pct", 0.0)), 2),
                    "estimated_lost_revenue": round(loss, 2),
                }
            )
        return {"incident_id": incident_id, "metrics": rows, "estimated_lost_revenue": round(lost_revenue, 2)}
