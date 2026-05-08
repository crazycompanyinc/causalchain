"""Click command line interface for CausalChain."""

from __future__ import annotations

import os
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import click

from causalchain.core.db import CausalChainDB
from causalchain.core.models import Incident, serialize_timestamp, utc_now
from causalchain.graph.analyzer import CausalGraphAnalyzer
from causalchain.graph.builder import CausalGraphBuilder
from causalchain.investigator import IncidentInvestigator
from causalchain.learner import IncidentLearner
from causalchain.narrator import NarrativeGenerator
from causalchain.predictor import CausalPredictor


def db_path() -> str:
    """Resolve the active database path."""
    return os.getenv("CAUSALCHAIN_DB", "causalchain.db")


def open_db() -> CausalChainDB:
    """Open the active database."""
    return CausalChainDB(db_path())


@click.group()
def cli() -> None:
    """CausalChain incident analysis."""


@cli.command()
def init() -> None:
    """Initialize CausalChain in the current directory."""
    db = open_db()
    db.close()
    click.secho(f"Initialized CausalChain at {Path(db_path()).resolve()}", fg="green")


@cli.command()
@click.option("--type", "event_type", required=True)
@click.option("--source", required=True)
@click.option("--description", required=True)
@click.option("--timestamp")
def ingest(event_type: str, source: str, description: str, timestamp: str | None) -> None:
    """Ingest an event."""
    db = open_db()
    try:
        node = CausalGraphBuilder(db).ingest_event(event_type, source, description, timestamp)
        click.secho(f"Ingested {node.type} from {node.source}", fg="green")
        click.echo(f"id: {node.id}")
    finally:
        db.close()


@cli.command()
@click.option("--since", required=True)
@click.option("--service", "services", multiple=True)
def investigate(since: str, services: tuple[str, ...]) -> None:
    """Investigate what caused events since a timestamp."""
    db = open_db()
    try:
        result = IncidentInvestigator(db).investigate(since, list(services))
        if not result["incident"]:
            click.secho(result["message"], fg="yellow")
            return
        click.secho(f"Confidence: {result['confidence']:.2f}", fg="cyan")
        click.secho("Root causes:", fg="red")
        for node in result["root_causes"]:
            click.echo(f"- {node['source']} {node['type']}: {node['description']}")
        click.secho("Causal chain:", fg="cyan")
        for node in result["causal_chain"]:
            click.echo(f"- {node['timestamp']} {node['source']} {node['type']}: {node['description']}")
    finally:
        db.close()


@cli.command()
def predict() -> None:
    """Predict potential incidents from current state."""
    db = open_db()
    try:
        predictions = CausalPredictor(db).predict()
        if not predictions:
            click.secho("No predictions from current causal state.", fg="green")
            return
        for item in predictions:
            click.secho(f"{item['pattern_name']} ({item['confidence']:.2f})", fg="yellow")
            click.echo(f"Next: {', '.join(item['predicted_events'])} within {item['time_horizon']}")
    finally:
        db.close()


@cli.command()
def patterns() -> None:
    """Show learned causal patterns."""
    db = open_db()
    try:
        rows = db.list_patterns()
        if not rows:
            click.secho("No learned patterns yet.", fg="yellow")
            return
        for pattern in rows:
            click.secho(pattern.name, fg="cyan")
            click.echo(f"frequency={pattern.frequency} confidence={pattern.confidence:.2f}")
    finally:
        db.close()


@cli.command()
@click.option("--incident", "incident_id", required=True)
def narrative(incident_id: str) -> None:
    """Generate narrative postmortem."""
    db = open_db()
    try:
        click.echo(NarrativeGenerator(db).generate(incident_id))
    finally:
        db.close()


@cli.command()
@click.option("--dot", is_flag=True)
def graph(dot: bool) -> None:
    """Export causal graph."""
    db = open_db()
    try:
        analyzer = CausalGraphAnalyzer(db)
        if dot:
            click.echo(analyzer.to_dot())
        else:
            click.echo(analyzer.graph_json())
    finally:
        db.close()


@cli.command()
@click.option("--port", default=8000, show_default=True)
def serve(port: int) -> None:
    """Start API server."""
    import uvicorn

    uvicorn.run("causalchain.server.app:app", host="0.0.0.0", port=port, reload=False)


@cli.command()
def demo() -> None:
    """Run a built-in demo incident."""
    db = CausalChainDB(":memory:")
    builder = CausalGraphBuilder(db, time_window_minutes=20)
    base = utc_now()
    events: list[tuple[str, str, str, dict[str, Any]]] = [
        ("deploy", "api-gateway", "Deploy v2.3.1 added an unindexed query", {"version": "2.3.1"}),
        ("metric_anomaly", "redis", "Connection count rises to 95%", {"metric": "connections"}),
        ("error", "payment-service", "Connection pool timeouts begin", {"metric": "connections"}),
        ("error", "payment-service", "Aggressive retries amplify latency", {"retry_rate": "high"}),
        ("metric_anomaly", "api-gateway", "Retry storm overwhelms request workers", {"metric": "latency"}),
        ("error", "api-gateway", "User-facing error rate spikes to 15%", {"metric": "errors"}),
        ("error", "load-balancer", "api-gateway marked unhealthy", {"health": "failed"}),
        ("recovery", "api-gateway", "Engineers rollback deploy v2.3.1", {"version": "2.3.0"}),
        ("recovery", "payment-service", "Timeouts return to baseline", {"metric": "connections"}),
    ]
    click.secho("CausalChain demo incident", fg="cyan", bold=True)
    nodes = []
    for idx, (event_type, source, description, metadata) in enumerate(events):
        node = builder.ingest_event(event_type, source, description, base + timedelta(minutes=idx), metadata)
        nodes.append(node)
        edges = CausalGraphAnalyzer(db).incoming_edges(node.id)
        click.secho(f"\n[{idx + 1}] {source} {event_type}", fg="green")
        click.echo(description)
        for edge in edges[:2]:
            click.echo(f"  edge: {edge.edge_type} confidence={edge.confidence:.2f} evidence={edge.evidence['reason']}")

    since = serialize_timestamp(base - timedelta(seconds=1))
    result = IncidentInvestigator(db).investigate(since, ["api-gateway", "payment-service", "load-balancer"])
    incident_data = result["incident"]
    incident = db.get_incident(incident_data["id"])
    incident.status = "resolved"
    incident.resolved_at = base + timedelta(minutes=len(events) + 2)
    db.add_incident(incident)
    pattern = IncidentLearner(db).learn_from_incident(incident)
    narrative_text = NarrativeGenerator(db).generate(incident.id)

    click.secho("\nInvestigation", fg="cyan", bold=True)
    click.echo(f"Confidence: {result['confidence']:.2f}")
    click.secho("Root cause:", fg="red")
    for node in result["root_causes"]:
        click.echo(f"- {node['source']} {node['type']}: {node['description']}")
    if pattern:
        click.secho(f"\nLearned pattern: {pattern.name} ({pattern.confidence:.2f})", fg="yellow")
    click.secho("\nNarrative postmortem", fg="cyan", bold=True)
    click.echo(narrative_text)
    db.close()


def incident_to_dict(incident: Incident) -> dict[str, Any]:
    """Serialize an incident for CLI helpers and tests."""
    data = asdict(incident)
    data["started_at"] = serialize_timestamp(incident.started_at)
    data["resolved_at"] = serialize_timestamp(incident.resolved_at) if incident.resolved_at else None
    return data
