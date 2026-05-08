"""Known incident patterns and response playbooks."""

from __future__ import annotations

from dataclasses import dataclass

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalPattern


@dataclass(frozen=True, slots=True)
class PatternDefinition:
    """A built-in incident pattern and its response playbook."""

    name: str
    description: str
    node_sequence: list[str]
    typical_duration: float
    confidence: float
    playbook: list[str]


BUILT_INS = [
    PatternDefinition(
        "cascading failure",
        "A dependency degradation propagates through callers until user-facing errors appear.",
        ["metric_anomaly", "error", "error"],
        2700.0,
        0.72,
        ["Identify the first degraded dependency.", "Shed non-critical traffic.", "Fail over or scale the saturated tier."],
    ),
    PatternDefinition(
        "retry storm",
        "Timeouts trigger aggressive retries that amplify load and latency.",
        ["error", "metric_anomaly", "error"],
        1800.0,
        0.78,
        ["Reduce retry budgets.", "Enable jitter/backoff.", "Temporarily rate-limit hot callers."],
    ),
    PatternDefinition(
        "thundering herd",
        "A synchronized request wave overloads shared infrastructure.",
        ["traffic_spike", "metric_anomaly", "error"],
        1500.0,
        0.74,
        ["Enable request coalescing.", "Increase cache TTLs.", "Throttle bulk clients."],
    ),
    PatternDefinition(
        "bad deploy",
        "A recent deploy is followed by anomalies and errors.",
        ["deploy", "metric_anomaly", "error"],
        1200.0,
        0.82,
        ["Pause rollout.", "Compare deploy diff against symptoms.", "Rollback if metrics improve in canary."],
    ),
]


class IncidentPatternLibrary:
    """Manage built-in and learned incident patterns."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db

    def install_builtins(self) -> list[CausalPattern]:
        """Persist built-in patterns for scoring and prediction."""
        installed = []
        for definition in BUILT_INS:
            installed.append(
                self.db.add_pattern(
                    CausalPattern(
                        name=definition.name,
                        description=definition.description,
                        node_sequence=definition.node_sequence,
                        typical_duration=definition.typical_duration,
                        frequency=1,
                        confidence=definition.confidence,
                    )
                )
            )
        return installed

    def match(self, node_sequence: list[str]) -> list[dict[str, object]]:
        """Return built-in patterns whose sequence appears in the supplied node types."""
        matches = []
        joined = " ".join(node_sequence)
        for definition in BUILT_INS:
            if " ".join(definition.node_sequence) in joined:
                matches.append({"name": definition.name, "confidence": definition.confidence, "playbook": definition.playbook})
        return sorted(matches, key=lambda item: item["confidence"], reverse=True)

    def playbook(self, name: str) -> list[str]:
        """Return playbook steps for a known pattern."""
        for definition in BUILT_INS:
            if definition.name == name:
                return list(definition.playbook)
        for pattern in self.db.list_patterns():
            if pattern.name == name:
                return ["Validate the causal chain.", "Mitigate the earliest controllable root.", "Monitor downstream recovery."]
        raise KeyError(f"pattern not found: {name}")
