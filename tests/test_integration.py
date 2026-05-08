"""Integration tests for API and CLI."""

from __future__ import annotations

from click.testing import CliRunner
from fastapi.testclient import TestClient

from causalchain.cli import cli
from causalchain.server.app import create_app


def test_api_health_and_event_ingest(tmp_path):
    app = create_app(str(tmp_path / "api.db"))
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}
    response = client.post(
        "/events",
        json={"type": "deploy", "source": "api-gateway", "description": "Deploy"},
    )
    assert response.status_code == 200
    assert response.json()["type"] == "deploy"


def test_api_investigate(tmp_path):
    app = create_app(str(tmp_path / "api2.db"))
    client = TestClient(app)
    client.post("/events", json={"type": "deploy", "source": "api-gateway", "description": "Deploy"})
    client.post("/events", json={"type": "error", "source": "api-gateway", "description": "Errors"})
    response = client.post("/investigate", json={"since": "2000-01-01T00:00:00Z"})
    assert response.status_code == 200
    assert response.json()["incident"] is not None


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
