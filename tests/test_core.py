"""Core model and database tests."""

from __future__ import annotations

import pytest

from causalchain.core.models import CausalEdge, CausalNode, Incident, parse_timestamp, utc_now


def test_node_validation_rejects_invalid_type():
    with pytest.raises(ValueError):
        CausalNode("bad", "api", "desc")


def test_edge_validation_rejects_bad_confidence():
    with pytest.raises(ValueError):
        CausalEdge("a", "b", "triggers", 1.5)


def test_incident_validation_rejects_bad_severity():
    with pytest.raises(ValueError):
        Incident("bad", "severe", "open", [], [], [], utc_now())


def test_parse_timestamp_normalizes_zulu():
    parsed = parse_timestamp("2026-05-08T00:00:00Z")
    assert parsed.tzinfo is not None
    assert parsed.isoformat().endswith("+00:00")


def test_db_persists_nodes_edges_patterns_incidents(db, resolved_incident):
    nodes = db.list_nodes()
    edges = db.list_edges()
    incidents = db.list_incidents()
    assert len(nodes) == 4
    assert edges
    assert incidents[0].id == resolved_incident.id


def test_db_graph_json_is_serializable(db, demo_graph):
    graph = db.as_graph_json()
    assert graph["nodes"]
    assert "timestamp" in graph["nodes"][0]

