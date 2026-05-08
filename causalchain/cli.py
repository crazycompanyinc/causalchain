"""Click command line interface for CausalChain."""

from __future__ import annotations

import os
import json
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import click

from causalchain.agents import ResponseCoordinator
from causalchain.alerting import PredictiveAlertEngine
from causalchain.core.db import CausalChainDB
from causalchain.core.models import Incident, serialize_timestamp, utc_now
from causalchain.graph.analyzer import CausalGraphAnalyzer
from causalchain.graph.builder import CausalGraphBuilder
from causalchain.investigator import IncidentInvestigator
from causalchain.learner import IncidentLearner
from causalchain.metrics import BusinessMetricCorrelator
from causalchain.narrator import NarrativeGenerator
from causalchain.patterns import IncidentPatternLibrary
from causalchain.postmortem import BlamelessPostmortemGenerator
from causalchain.predictor import CausalPredictor
from causalchain.realtime import RealTimeCausalGraph
from causalchain.timeline import TimelineReconstructor
from causalchain.tracing import OpenTelemetryIngestor
from causalchain.visualization import GraphVisualizationExporter
from causalchain.whatif import WhatIfSimulator


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


@cli.command("alerts")
def alerts() -> None:
    """Show predictive incident alerts."""
    db = open_db()
    try:
        rows = PredictiveAlertEngine(db).alerts()
        if not rows:
            click.secho("No predictive alerts from current causal state.", fg="green")
            return
        for row in rows:
            click.secho(f"{row['severity']} {row['pattern_name']} ({row['confidence']:.2f})", fg="yellow")
            click.echo(row["message"])
    finally:
        db.close()


@cli.command("trace-ingest")
@click.argument("path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def trace_ingest(path: Path) -> None:
    """Ingest OpenTelemetry JSON traces."""
    db = open_db()
    try:
        result = OpenTelemetryIngestor(db).ingest(json.loads(path.read_text()))
        click.secho(f"Ingested {len(result['nodes'])} spans and {len(result['edges'])} trace edges", fg="green")
    finally:
        db.close()


@cli.command("whatif")
@click.option("--action", required=True)
@click.option("--target")
def whatif(action: str, target: str | None) -> None:
    """Simulate a hypothetical mitigation action."""
    db = open_db()
    try:
        result = WhatIfSimulator(db).simulate(action, target)
        click.secho(result["recommendation"], fg="cyan")
        click.echo(f"risk_reduction={result['estimated_risk_reduction']:.2f}")
        click.echo(f"affected_services={', '.join(result['affected_services'])}")
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


@cli.command("install-patterns")
def install_patterns() -> None:
    """Install built-in incident patterns and playbooks."""
    db = open_db()
    try:
        installed = IncidentPatternLibrary(db).install_builtins()
        click.secho(f"Installed {len(installed)} built-in patterns", fg="green")
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


@cli.command("postmortem")
@click.option("--incident", "incident_id", required=True)
def postmortem(incident_id: str) -> None:
    """Generate a v2 blameless postmortem."""
    db = open_db()
    try:
        click.echo(BlamelessPostmortemGenerator(db).generate(incident_id))
    finally:
        db.close()


@cli.command("timeline")
@click.option("--incident", "incident_id", required=True)
def timeline(incident_id: str) -> None:
    """Reconstruct a minute-by-minute incident timeline."""
    db = open_db()
    try:
        for bucket in TimelineReconstructor(db).reconstruct(incident_id):
            click.secho(bucket["minute"], fg="cyan")
            for event in bucket["events"]:
                click.echo(f"- {event['source']} {event['type']}: {event['description']}")
    finally:
        db.close()


@cli.command("coordinate")
@click.option("--incident", "incident_id", required=True)
def coordinate(incident_id: str) -> None:
    """Coordinate response agents for an incident."""
    db = open_db()
    try:
        for action in ResponseCoordinator(db).coordinate(incident_id):
            click.echo(f"{action['action']} {action['target']}: {action['reason']}")
    finally:
        db.close()


@cli.command()
@click.option("--dot", is_flag=True)
@click.option("--html", "html_export", is_flag=True)
@click.option("--ascii", "ascii_export", is_flag=True)
def graph(dot: bool, html_export: bool, ascii_export: bool) -> None:
    """Export causal graph."""
    db = open_db()
    try:
        exporter = GraphVisualizationExporter(db)
        if dot:
            click.echo(exporter.dot())
        elif html_export:
            click.echo(exporter.html())
        elif ascii_export:
            click.echo(exporter.ascii())
        else:
            click.echo(CausalGraphAnalyzer(db).graph_json())
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
    IncidentPatternLibrary(db).install_builtins()
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

    trace_payload = {
        "resourceSpans": [
            {
                "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "checkout-service"}}]},
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": "trace-demo",
                                "spanId": "span-root",
                                "name": "POST /checkout",
                                "startTimeUnixNano": str(int((base + timedelta(minutes=2)).timestamp() * 1_000_000_000)),
                                "endTimeUnixNano": str(int((base + timedelta(minutes=2, seconds=2)).timestamp() * 1_000_000_000)),
                            },
                            {
                                "traceId": "trace-demo",
                                "spanId": "span-pay",
                                "parentSpanId": "span-root",
                                "name": "charge payment",
                                "status": {"code": "STATUS_CODE_ERROR"},
                                "startTimeUnixNano": str(int((base + timedelta(minutes=2, seconds=1)).timestamp() * 1_000_000_000)),
                                "endTimeUnixNano": str(int((base + timedelta(minutes=2, seconds=6)).timestamp() * 1_000_000_000)),
                            },
                        ]
                    }
                ],
            }
        ]
    }
    trace_result = OpenTelemetryIngestor(db, builder).ingest(trace_payload)
    live_updates: list[dict[str, Any]] = []
    live = RealTimeCausalGraph(db)
    live.subscribe(live_updates.append)
    live.ingest_event("metric_anomaly", "checkout-service", "Checkout queue depth still elevated", base + timedelta(minutes=10), {"metric": "queue_depth"})

    since = serialize_timestamp(base - timedelta(seconds=1))
    result = IncidentInvestigator(db).investigate(since, ["api-gateway", "payment-service", "load-balancer"])
    incident_data = result["incident"]
    incident = db.get_incident(incident_data["id"])
    incident.status = "resolved"
    incident.resolved_at = base + timedelta(minutes=len(events) + 2)
    db.add_incident(incident)
    BusinessMetricCorrelator(db).ingest_metric("conversion", 850, 1000, "checkout", base + timedelta(minutes=4), 31.33)
    pattern = IncidentLearner(db).learn_from_incident(incident)
    narrative_text = NarrativeGenerator(db).generate(incident.id)
    whatif_result = WhatIfSimulator(db).simulate("rollback_deploy", "2.3.1")
    postmortem_text = BlamelessPostmortemGenerator(db).generate(incident.id)
    agent_actions = ResponseCoordinator(db).coordinate(incident.id)

    click.secho("\nInvestigation", fg="cyan", bold=True)
    click.echo(f"Confidence: {result['confidence']:.2f}")
    click.secho("Root cause:", fg="red")
    for node in result["root_causes"]:
        click.echo(f"- {node['source']} {node['type']}: {node['description']}")
    if pattern:
        click.secho(f"\nLearned pattern: {pattern.name} ({pattern.confidence:.2f})", fg="yellow")
    click.secho("\nv2.0 capabilities", fg="cyan", bold=True)
    click.echo(f"OpenTelemetry spans ingested: {len(trace_result['nodes'])}")
    click.echo(f"Live graph updates published: {len(live_updates)}")
    click.echo(f"What-if rollback risk reduction: {whatif_result['estimated_risk_reduction']:.2f}")
    click.echo(f"Coordinated actions: {', '.join(action['action'] for action in agent_actions)}")
    click.echo(f"ASCII graph lines: {len(GraphVisualizationExporter(db).ascii().splitlines())}")
    click.secho("\nNarrative postmortem", fg="cyan", bold=True)
    click.echo(narrative_text)
    click.secho("\nBlameless v2 postmortem", fg="cyan", bold=True)
    click.echo(postmortem_text)
    db.close()


def incident_to_dict(incident: Incident) -> dict[str, Any]:
    """Serialize an incident for CLI helpers and tests."""
    data = asdict(incident)
    data["started_at"] = serialize_timestamp(incident.started_at)
    data["resolved_at"] = serialize_timestamp(incident.resolved_at) if incident.resolved_at else None
    return data
