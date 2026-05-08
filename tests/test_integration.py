"""Integration tests for API and CLI."""

from __future__ import annotations

import asyncio

from click.testing import CliRunner

from causalchain.cli import cli
from causalchain.server.app import create_app
from causalchain.server.routes import EventIn, InvestigationIn


def endpoint(app, path: str):
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route.endpoint
    raise AssertionError(f"route not found: {path}")


def test_api_health_and_event_ingest(tmp_path):
    app = create_app(str(tmp_path / "api.db"))
    assert asyncio.run(endpoint(app, "/health")()) == {"status": "ok"}
    response = asyncio.run(
        endpoint(app, "/events")(EventIn(type="deploy", source="api-gateway", description="Deploy"))
    )
    assert response["type"] == "deploy"


def test_api_investigate(tmp_path):
    app = create_app(str(tmp_path / "api2.db"))
    asyncio.run(endpoint(app, "/events")(EventIn(type="deploy", source="api-gateway", description="Deploy")))
    asyncio.run(endpoint(app, "/events")(EventIn(type="error", source="api-gateway", description="Errors")))
    response = asyncio.run(endpoint(app, "/investigate")(InvestigationIn(since="2000-01-01T00:00:00Z")))
    assert response["incident"] is not None


def test_cli_init_and_ingest(tmp_path, monkeypatch):
    monkeypatch.setenv("CAUSALCHAIN_DB", str(tmp_path / "cli.db"))
    runner = CliRunner()
    assert runner.invoke(cli, ["init"]).exit_code == 0
    result = runner.invoke(
        cli,
        ["ingest", "--type", "deploy", "--source", "api-gateway", "--description", "Deploy"],
    )
    assert result.exit_code == 0
    assert "Ingested deploy" in result.output


def test_cli_demo_runs():
    runner = CliRunner()
    result = runner.invoke(cli, ["demo"])
    assert result.exit_code == 0
    assert "Narrative postmortem" in result.output
