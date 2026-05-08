"""Coordinate response agents when incidents are detected."""

from __future__ import annotations

from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalNode, Incident, utc_now
from causalchain.ranking import RootCauseRanker


class ResponseCoordinator:
    """Create deterministic response actions for operators and agents."""

    def __init__(self, db: CausalChainDB, responders: dict[str, str] | None = None) -> None:
        self.db = db
        self.responders = responders or {"critical": "Felix-CTO", "high": "oncall-primary", "medium": "oncall-secondary"}

    def coordinate(self, incident: Incident | str) -> list[dict[str, Any]]:
        """Return and persist response actions for an incident."""
        incident_obj = self.db.get_incident(incident) if isinstance(incident, str) else incident
        ranked = RootCauseRanker(self.db).rank(incident_obj.root_cause_node_ids, incident_obj.causal_chain[-1:])
        actions = [
            {"action": "alert", "target": self.responders.get(incident_obj.severity, "oncall-primary"), "reason": f"{incident_obj.severity} incident detected"},
        ]
        if ranked:
            top = ranked[0]
            if top["type"] == "deploy":
                actions.append({"action": "pause_deploy", "target": top["source"], "reason": "deploy is top-ranked causal root"})
                actions.append({"action": "prepare_rollback", "target": top["source"], "reason": "rollback is likely controllable mitigation"})
            elif top["type"] == "config_change":
                actions.append({"action": "prepare_config_revert", "target": top["source"], "reason": "config change is top-ranked causal root"})
        actions.append({"action": "open_war_room", "target": ",".join(incident_obj.affected_services), "reason": "coordinate affected service owners"})
        for action in actions:
            self.db.add_node(CausalNode("agent_action", "causalchain", f"{action['action']} {action['target']}", utc_now(), action))
        return actions
