"""Generate human-readable incident narratives."""

from __future__ import annotations

from causalchain.core.db import CausalChainDB
from causalchain.core.models import Incident, serialize_timestamp


class NarrativeGenerator:
    """Create markdown postmortems from causal chains."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db

    def generate(self, incident: Incident | str) -> str:
        """Generate and persist a markdown narrative for an incident."""
        if isinstance(incident, str):
            incident_obj = self.db.get_incident(incident)
        else:
            incident_obj = incident
        nodes = [self.db.get_node(node_id) for node_id in incident_obj.causal_chain]
        roots = [self.db.get_node(node_id) for node_id in incident_obj.root_cause_node_ids]
        if not nodes:
            raise ValueError("incident has no causal chain")

        impact = ", ".join(incident_obj.affected_services) or "unknown services"
        timeline = "\n".join(
            f"- `{serialize_timestamp(node.timestamp)}` **{node.source}** {node.type}: {node.description}"
            for node in nodes
        )
        root_text = "\n".join(
            f"- **{node.source}** `{node.type}`: {node.description}"
            for node in roots
        ) or "- No root cause identified."
        story = self._story(nodes)
        resolution = "The incident remains under investigation."
        if incident_obj.status == "resolved":
            resolution = "The causal chain stopped after remediation and the incident was marked resolved."
        narrative = (
            f"# Postmortem: {incident_obj.title}\n\n"
            "## Summary\n\n"
            f"{story}\n\n"
            "## Timeline\n\n"
            f"{timeline}\n\n"
            "## Root Cause\n\n"
            f"{root_text}\n\n"
            "## Impact\n\n"
            f"Affected services: {impact}. Severity was `{incident_obj.severity}`.\n\n"
            "## Resolution\n\n"
            f"{resolution}\n"
        )
        incident_obj.narrative = narrative
        self.db.add_incident(incident_obj)
        return narrative

    def _story(self, nodes: list) -> str:
        first = nodes[0]
        last = nodes[-1]
        if len(nodes) == 1:
            return f"{last.source} reported {last.description}."
        middle = nodes[1:-1]
        bridge = ""
        if middle:
            bridge = " The chain then moved through " + ", ".join(f"{node.source} {node.type}" for node in middle) + "."
        return (
            f"The incident began with {first.type} on {first.source}: {first.description}."
            f"{bridge} It surfaced as {last.type} on {last.source}: {last.description}."
        )
