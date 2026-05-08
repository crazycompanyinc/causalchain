"""Graph builder and analyzer tests."""

from __future__ import annotations

from datetime import timedelta

from causalchain.core.models import utc_now
from causalchain.graph.analyzer import CausalGraphAnalyzer
from causalchain.graph.builder import CausalGraphBuilder


def test_builder_creates_edge_for_plausible_causal_pair(db):
    base = utc_now()
    builder = CausalGraphBuilder(db)
    first = builder.ingest_event("deploy", "api-gateway", "Deploy", base)
    second = builder.ingest_event("error", "api-gateway", "Errors", base + timedelta(minutes=1))
    incoming = CausalGraphAnalyzer(db).incoming_edges(second.id)
    assert incoming[0].source_node_id == first.id
    assert incoming[0].confidence > 0.4


def test_builder_rejects_reverse_incompatible_pair(db):
    base = utc_now()
    builder = CausalGraphBuilder(db)
    builder.ingest_event("error", "api-gateway", "Errors", base)
    builder.ingest_event("deploy", "api-gateway", "Deploy", base + timedelta(minutes=1))
    assert db.list_edges() == []


def test_builder_respects_time_window(db):
    base = utc_now()
    builder = CausalGraphBuilder(db, time_window_minutes=5)
    builder.ingest_event("deploy", "api-gateway", "Deploy", base)
    builder.ingest_event("error", "api-gateway", "Errors", base + timedelta(minutes=10))
    assert db.list_edges() == []


def test_dependency_score_boosts_known_dependency(db):
    base = utc_now()
    builder = CausalGraphBuilder(db)
    source = builder.ingest_event("metric_anomaly", "redis", "Connections", base)
    target = builder.ingest_event("error", "payment-service", "Timeouts", base + timedelta(minutes=1))
    edge = CausalGraphAnalyzer(db).incoming_edges(target.id)[0]
    assert edge.source_node_id == source.id
    assert edge.evidence["dependency_score"] == 1.0


def test_analyzer_finds_best_chain_and_roots(demo_graph):
    db, nodes, _ = demo_graph
    analyzer = CausalGraphAnalyzer(db)
    chain = analyzer.best_chain_to(nodes[-1].id)
    roots = analyzer.find_roots([nodes[-1].id])
    assert chain[0] == nodes[0].id
    assert nodes[0].id in roots


def test_analyzer_exports_dot(demo_graph):
    db, _, _ = demo_graph
    dot = CausalGraphAnalyzer(db).to_dot()
    assert dot.startswith("digraph causalchain")
    assert "->" in dot

