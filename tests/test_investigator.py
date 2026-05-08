"""Incident investigator tests."""

from __future__ import annotations

from datetime import timedelta

from causalchain.investigator import IncidentInvestigator


def test_investigator_returns_chain_and_roots(demo_graph):
    db, nodes, base = demo_graph
    result = IncidentInvestigator(db).investigate(base - timedelta(seconds=1))
    assert result["incident"] is not None
    assert result["causal_chain"][0]["id"] == nodes[0].id
    assert result["root_causes"]


def test_investigator_handles_empty_window(db):
    result = IncidentInvestigator(db).investigate("2026-05-08T00:00:00Z")
    assert result["incident"] is None
    assert result["confidence"] == 0.0

