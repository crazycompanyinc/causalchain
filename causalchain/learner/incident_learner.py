"""Learn recurring causal patterns from resolved incidents."""

from __future__ import annotations

from collections import Counter

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalPattern, Incident


class IncidentLearner:
    """Derive deterministic causal patterns from past incidents."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db

    def learn_from_incident(self, incident: Incident) -> CausalPattern | None:
        """Learn or update a pattern from one resolved incident."""
        if incident.status != "resolved" or len(incident.causal_chain) < 2:
            return None
        sequence = [self.db.get_node(node_id).type for node_id in incident.causal_chain]
        duration = 0.0
        if incident.resolved_at:
            duration = (incident.resolved_at - incident.started_at).total_seconds()
        name = " -> ".join(sequence)
        existing = next((pattern for pattern in self.db.list_patterns() if pattern.name == name), None)
        if existing:
            frequency = existing.frequency + 1
            typical_duration = ((existing.typical_duration * existing.frequency) + duration) / frequency
            confidence = min(0.95, existing.confidence + 0.08)
            pattern = CausalPattern(
                id=existing.id,
                name=existing.name,
                description=f"Recurring incident chain observed {frequency} times.",
                node_sequence=sequence,
                typical_duration=typical_duration,
                frequency=frequency,
                confidence=round(confidence, 3),
            )
        else:
            pattern = CausalPattern(
                name=name,
                description=f"Causal chain learned from incident '{incident.title}'.",
                node_sequence=sequence,
                typical_duration=duration,
                frequency=1,
                confidence=0.55,
            )
        return self.db.add_pattern(pattern)

    def learn_all(self) -> list[CausalPattern]:
        """Learn patterns from all resolved incidents."""
        learned: list[CausalPattern] = []
        for incident in self.db.list_incidents():
            pattern = self.learn_from_incident(incident)
            if pattern:
                learned.append(pattern)
        return learned

    def recurring_type_sequences(self) -> dict[tuple[str, ...], int]:
        """Count causal chain type sequences across resolved incidents."""
        counter: Counter[tuple[str, ...]] = Counter()
        for incident in self.db.list_incidents():
            if incident.status == "resolved" and len(incident.causal_chain) >= 2:
                counter[tuple(self.db.get_node(node_id).type for node_id in incident.causal_chain)] += 1
        return dict(counter)

