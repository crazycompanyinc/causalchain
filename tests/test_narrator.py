"""Narrator tests."""

from __future__ import annotations

from causalchain.narrator import NarrativeGenerator


def test_narrator_generates_markdown_sections(db, resolved_incident):
    text = NarrativeGenerator(db).generate(resolved_incident.id)
    assert "## Summary" in text
    assert "## Timeline" in text
    assert "## Root Cause" in text


def test_narrator_persists_narrative(db, resolved_incident):
    NarrativeGenerator(db).generate(resolved_incident.id)
    assert db.get_incident(resolved_incident.id).narrative.startswith("# Postmortem")

