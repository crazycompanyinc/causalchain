"""Generate predictive incident alerts from current causal state."""

from __future__ import annotations

from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalNode, utc_now
from causalchain.predictor import CausalPredictor


class PredictiveAlertEngine:
    """Convert causal predictions into actionable alerts."""

    def __init__(self, db: CausalChainDB, min_confidence: float = 0.25) -> None:
        self.db = db
        self.min_confidence = min_confidence

    def alerts(self) -> list[dict[str, Any]]:
        """Return predicted incident alerts ordered by severity."""
        alerts = []
        for prediction in CausalPredictor(self.db).predict():
            if prediction["confidence"] < self.min_confidence:
                continue
            severity = "critical" if prediction["confidence"] >= 0.65 else "high" if prediction["confidence"] >= 0.4 else "medium"
            minutes = self._minutes(prediction["time_horizon"])
            alerts.append(
                {
                    "severity": severity,
                    "pattern_name": prediction["pattern_name"],
                    "confidence": prediction["confidence"],
                    "message": f"Current trajectory suggests {prediction['pattern_name']} in ~{minutes} minutes.",
                    "predicted_events": prediction["predicted_events"],
                    "observed_events": prediction["observed_events"],
                    "time_to_incident_minutes": minutes,
                }
            )
        return sorted(alerts, key=lambda item: (item["severity"] != "critical", -item["confidence"]))

    def persist_alerts(self) -> list[CausalNode]:
        """Persist generated alerts as prediction nodes."""
        nodes = []
        for alert in self.alerts():
            nodes.append(
                self.db.add_node(
                    CausalNode(
                        "prediction",
                        "causalchain",
                        alert["message"],
                        utc_now(),
                        alert,
                    )
                )
            )
        return nodes

    def _minutes(self, horizon: str) -> int:
        parts = horizon.split()
        minutes = 0
        for part in parts:
            if part.endswith("m"):
                minutes += int(part[:-1])
        return max(1, minutes)
