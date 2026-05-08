"""FastAPI routes for CausalChain."""

from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalNode, serialize_timestamp
from causalchain.graph.analyzer import CausalGraphAnalyzer
from causalchain.graph.builder import CausalGraphBuilder
from causalchain.investigator import IncidentInvestigator
from causalchain.narrator import NarrativeGenerator
from causalchain.predictor import CausalPredictor


class EventIn(BaseModel):
    """Incoming event payload."""

    type: str
    source: str
    description: str
    timestamp: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvestigationIn(BaseModel):
    """Investigation request."""

    since: str
    affected_services: list[str] = Field(default_factory=list)
    severity: str = "high"


def make_router(db_path: str | None = None) -> APIRouter:
    """Create an API router bound to a database path."""
    router = APIRouter()
    db = CausalChainDB(db_path or os.getenv("CAUSALCHAIN_DB", "causalchain.db"))

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/events")
    async def create_event(payload: EventIn) -> dict[str, Any]:
        try:
            node = CausalGraphBuilder(db).ingest_event(
                payload.type,
                payload.source,
                payload.description,
                payload.timestamp,
                payload.metadata,
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _node_dict(node)

    @router.get("/graph")
    async def graph() -> dict[str, Any]:
        return CausalGraphAnalyzer(db).graph_json()

    @router.post("/investigate")
    async def investigate(payload: InvestigationIn) -> dict[str, Any]:
        try:
            return IncidentInvestigator(db).investigate(payload.since, payload.affected_services, payload.severity)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/predict")
    async def predict() -> list[dict[str, Any]]:
        return CausalPredictor(db).predict()

    @router.get("/patterns")
    async def patterns() -> list[dict[str, Any]]:
        return [asdict(pattern) for pattern in db.list_patterns()]

    @router.get("/incidents")
    async def incidents() -> list[dict[str, Any]]:
        rows = []
        for incident in db.list_incidents():
            data = asdict(incident)
            data["started_at"] = serialize_timestamp(incident.started_at)
            data["resolved_at"] = serialize_timestamp(incident.resolved_at) if incident.resolved_at else None
            rows.append(data)
        return rows

    @router.get("/incidents/{incident_id}/narrative")
    async def narrative(incident_id: str) -> dict[str, str]:
        try:
            return {"narrative": NarrativeGenerator(db).generate(incident_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @router.post("/webhook/alertmanager")
    async def alertmanager(payload: dict[str, Any]) -> dict[str, Any]:
        alerts = payload.get("alerts", [])
        created = []
        builder = CausalGraphBuilder(db)
        for alert in alerts:
            labels = alert.get("labels", {})
            annotations = alert.get("annotations", {})
            status = alert.get("status", "firing")
            node_type = "error" if status == "firing" else "recovery"
            created.append(
                _node_dict(
                    builder.ingest_event(
                        node_type,
                        labels.get("service", labels.get("job", "unknown")),
                        annotations.get("summary", labels.get("alertname", "Alertmanager alert")),
                        alert.get("startsAt"),
                        {"labels": labels, "annotations": annotations},
                    )
                )
            )
        return {"created": created}

    return router


def _node_dict(node: CausalNode) -> dict[str, Any]:
    data = asdict(node)
    data["timestamp"] = serialize_timestamp(node.timestamp)
    return data
