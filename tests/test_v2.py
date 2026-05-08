"""CausalChain v2 feature tests."""

from __future__ import annotations

from datetime import timedelta

from causalchain.agents import ResponseCoordinator
from causalchain.alerting import PredictiveAlertEngine
from causalchain.correlation import CrossSystemCorrelator
from causalchain.core.models import Incident, utc_now
from causalchain.graph.builder import CausalGraphBuilder
from causalchain.metrics import BusinessMetricCorrelator
from causalchain.patterns import IncidentPatternLibrary
from causalchain.postmortem import BlamelessPostmortemGenerator
from causalchain.ranking import RootCauseRanker
from causalchain.realtime import RealTimeCausalGraph
from causalchain.timeline import TimelineReconstructor
from causalchain.tracing import OpenTelemetryIngestor
from causalchain.visualization import GraphVisualizationExporter
from causalchain.whatif import WhatIfSimulator


def test_opentelemetry_ingest_creates_span_nodes_and_parent_edge(db):
    base = utc_now()
    payload = {
        "spans": [
            {
                "traceId": "t1",
                "spanId": "s1",
                "name": "GET /checkout",
                "serviceName": "api",
                "startTimeUnixNano": str(int(base.timestamp() * 1_000_000_000)),
                "endTimeUnixNano": str(int((base + timedelta(seconds=1)).timestamp() * 1_000_000_000)),
            },
            {
                "traceId": "t1",
                "spanId": "s2",
                "parentSpanId": "s1",
                "name": "db query",
                "serviceName": "db",
                "status": {"code": "STATUS_CODE_ERROR"},
                "startTimeUnixNano": str(int((base + timedelta(seconds=1)).timestamp() * 1_000_000_000)),
                "endTimeUnixNano": str(int((base + timedelta(seconds=2)).timestamp() * 1_000_000_000)),
            },
        ]
    }
    result = OpenTelemetryIngestor(db).ingest(payload)
    assert len(result["nodes"]) == 2
    assert any(edge.edge_type == "propagates_to" for edge in result["edges"])
    assert {node.type for node in result["nodes"]} == {"trace_span", "error"}


def test_realtime_graph_publishes_snapshots(db):
    updates = []
    live = RealTimeCausalGraph(db)
    live.subscribe(updates.append)
    node = live.ingest_event("deploy", "api", "Deploy")
    assert updates[-1]["changed_node_ids"] == [node.id]
    assert updates[-1]["sequence"] == 1


def test_whatif_ranking_timeline_and_exports(demo_graph):
    db, nodes, _ = demo_graph
    incident = Incident(
        "Checkout failure",
        "high",
        "investigating",
        [nodes[0].id],
        ["api-gateway", "payment-service"],
        [node.id for node in nodes],
        nodes[0].timestamp,
    )
    db.add_incident(incident)
    ranked = RootCauseRanker(db).rank(incident.root_cause_node_ids, [nodes[-1].id])
    simulation = WhatIfSimulator(db).simulate("rollback_deploy", "api-gateway")
    timeline = TimelineReconstructor(db).reconstruct(incident.id)
    exporter = GraphVisualizationExporter(db)
    assert ranked[0]["node_id"] == nodes[0].id
    assert simulation["estimated_risk_reduction"] > 0
    assert timeline[0]["events"]
    assert "CausalChain graph" in exporter.ascii()
    assert "<html" in exporter.html()


def test_pattern_library_predictive_alerts_and_postmortem(db):
    library = IncidentPatternLibrary(db)
    library.install_builtins()
    base = utc_now()
    builder = CausalGraphBuilder(db)
    first = builder.ingest_event("deploy", "api", "Deploy v2.3", base, {"version": "2.3"})
    second = builder.ingest_event("metric_anomaly", "api", "Latency high", base + timedelta(minutes=1), {"metric": "latency"})
    incident = Incident(
        "API latency",
        "high",
        "resolved",
        [first.id],
        ["api"],
        [first.id, second.id],
        base,
        base + timedelta(minutes=5),
    )
    db.add_incident(incident)
    BusinessMetricCorrelator(db).ingest_metric("conversion", 85, 100, "business", base + timedelta(minutes=2), 10)
    alerts = PredictiveAlertEngine(db, min_confidence=0.1).alerts()
    postmortem = BlamelessPostmortemGenerator(db).generate(incident.id)
    assert alerts
    assert "bad deploy" in alerts[0]["pattern_name"]
    assert "Blameless Postmortem" in postmortem
    assert "Total estimated lost revenue: $150.00" in postmortem


def test_cross_system_correlation_and_agent_coordination(db):
    base = utc_now()
    builder = CausalGraphBuilder(db)
    root = builder.ingest_event("metric_anomaly", "database", "Slow queries", base, {"system": "system-a"})
    symptom = builder.ingest_event("error", "api", "Timeouts", base + timedelta(minutes=2), {"system": "system-b"})
    edges = CrossSystemCorrelator(db, {"system-b": ["system-a"]}).correlate()
    incident = Incident("Cross-system timeout", "critical", "investigating", [root.id], ["database", "api"], [root.id, symptom.id], base)
    db.add_incident(incident)
    actions = ResponseCoordinator(db).coordinate(incident.id)
    assert edges
    assert actions[0]["target"] == "Felix-CTO"
