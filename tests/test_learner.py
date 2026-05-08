"""Incident learner tests."""

from __future__ import annotations

from causalchain.learner import IncidentLearner


def test_learner_creates_pattern(db, resolved_incident):
    pattern = IncidentLearner(db).learn_from_incident(resolved_incident)
    assert pattern is not None
    assert pattern.frequency == 1
    assert pattern.node_sequence[0] == "deploy"


def test_learner_updates_pattern_frequency(db, resolved_incident):
    learner = IncidentLearner(db)
    learner.learn_from_incident(resolved_incident)
    pattern = learner.learn_from_incident(resolved_incident)
    assert pattern is not None
    assert pattern.frequency == 2


def test_learner_ignores_open_incidents(db, resolved_incident):
    resolved_incident.status = "open"
    assert IncidentLearner(db).learn_from_incident(resolved_incident) is None

