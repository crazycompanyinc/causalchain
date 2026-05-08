"""Generate blameless postmortems with v2 analysis."""

from __future__ import annotations

from causalchain.core.db import CausalChainDB
from causalchain.core.models import Incident
from causalchain.metrics import BusinessMetricCorrelator
from causalchain.patterns import IncidentPatternLibrary
from causalchain.ranking import RootCauseRanker
from causalchain.timeline import TimelineReconstructor


class BlamelessPostmortemGenerator:
    """Create detailed, blameless markdown postmortems."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db

    def generate(self, incident: Incident | str) -> str:
        """Generate a postmortem with causal analysis, timeline, impact, and actions."""
        incident_obj = self.db.get_incident(incident) if isinstance(incident, str) else incident
        node_types = [self.db.get_node(node_id).type for node_id in incident_obj.causal_chain]
        matches = IncidentPatternLibrary(self.db).match(node_types)
        timeline = TimelineReconstructor(self.db).reconstruct(incident_obj)
        ranked = RootCauseRanker(self.db).rank(incident_obj.root_cause_node_ids, incident_obj.causal_chain[-1:])
        impact = BusinessMetricCorrelator(self.db).impact_for_incident(incident_obj.id)
        timeline_text = "\n".join(
            f"- {bucket['minute']}: " + "; ".join(f"{event['source']} {event['type']} caused_by={len(event['caused_by'])}" for event in bucket["events"])
            for bucket in timeline
        )
        root_text = "\n".join(
            f"- {item['source']} {item['type']}: score={item['score']:.2f}, impact={item['impact']:.2f}, confidence={item['confidence']:.2f}, fix_difficulty={item['fix_difficulty']:.2f}"
            for item in ranked
        ) or "- No ranked root cause available."
        pattern_text = "\n".join(f"- {match['name']}: {', '.join(match['playbook'])}" for match in matches) or "- No known pattern matched."
        metric_text = "\n".join(
            f"- {metric['metric']}: {metric['delta_pct']}%, estimated lost revenue ${metric['estimated_lost_revenue']:,.2f}"
            for metric in impact["metrics"]
        ) or "- No correlated business metrics."
        return (
            f"# Blameless Postmortem: {incident_obj.title}\n\n"
            "## Summary\n\n"
            f"CausalChain reconstructed {len(incident_obj.causal_chain)} events across {len(incident_obj.affected_services)} services. "
            "This report focuses on system conditions, controls, and recovery opportunities rather than individual fault.\n\n"
            "## Ranked Root Causes\n\n"
            f"{root_text}\n\n"
            "## Timeline\n\n"
            f"{timeline_text}\n\n"
            "## Known Patterns And Playbooks\n\n"
            f"{pattern_text}\n\n"
            "## Business Impact\n\n"
            f"{metric_text}\n\n"
            f"Total estimated lost revenue: ${impact['estimated_lost_revenue']:,.2f}.\n\n"
            "## Recommendations\n\n"
            "- Add guardrails around the top-ranked root cause.\n"
            "- Validate alerts against the earliest causal signals.\n"
            "- Update the pattern library with confirmed remediation steps.\n"
        )
