"""Predictor tests."""

from __future__ import annotations

from datetime import timedelta

from causalchain.core.models import CausalPattern, utc_now
from causalchain.graph.builder import CausalGraphBuilder
from causalchain.predictor import CausalPredictor


def test_predictor_matches_partial_pattern(db):
    db.add_pattern(
        CausalPattern(
            "deploy -> metric_anomaly -> error",
            "test",
            ["deploy", "metric_anomaly", "error"],
            600,
            3,
            0.8,
        )
    )
    base = utc_now()
    builder = CausalGraphBuilder(db)
    builder.ingest_event("deploy", "api-gateway", "Deploy", base - timedelta(minutes=1))
    builder.ingest_event("metric_anomaly", "redis", "Connections", base)
    predictions = CausalPredictor(db).predict()
    assert predictions[0]["predicted_events"] == ["error"]


def test_predictor_returns_empty_without_patterns(db, demo_graph):
    assert CausalPredictor(db).predict() == []

