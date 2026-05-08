"""Shared test helpers."""

from __future__ import annotations

from datetime import timedelta

import pytest

from causalchain.core.db import CausalChainDB
from causalchain.core.models import Incident, utc_now
from causalchain.graph.builder import CausalGraphBuilder


@pytest.fixture()
def db(tmp_path):
    store = CausalChainDB(tmp_path / "test.db")
    yield store
    store.close()


@pytest.fixture()
def demo_graph(db):
    builder = CausalGraphBuilder(db, time_window_minutes=20)
    base = utc_now()
    nodes = [
        builder.ingest_event("deploy", "api-gateway", "Deploy v2.3.1", base),
        builder.ingest_event("metric_anomaly", "redis", "Connection count 95%", base + timedelta(minutes=1)),
        builder.ingest_event("error", "payment-service", "Connection timeout", base + timedelta(minutes=2)),
        builder.ingest_event("error", "api-gateway", "Error rate 15%", base + timedelta(minutes=3)),
    ]
    return db, nodes, base


@pytest.fixture()
def resolved_incident(demo_graph):
    db, nodes, base = demo_graph
    incident = Incident(
        title="Checkout failure",
        severity="high",
        status="resolved",
        root_cause_node_ids=[nodes[0].id],
        affected_services=["api-gateway", "payment-service"],
        causal_chain=[node.id for node in nodes],
        started_at=base,
        resolved_at=base + timedelta(minutes=9),
    )
    db.add_incident(incident)
    return incident

