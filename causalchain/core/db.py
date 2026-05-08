"""SQLite storage for CausalChain."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from causalchain.core.models import (
    CausalEdge,
    CausalNode,
    CausalPattern,
    Incident,
    parse_timestamp,
    serialize_timestamp,
)


class CausalChainDB:
    """Small SQLite repository with WAL enabled."""

    def __init__(self, path: str | Path = "causalchain.db") -> None:
        self.path = Path(path)
        if self.path.parent and str(self.path.parent) != ".":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.initialize()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self.conn.close()

    def initialize(self) -> None:
        """Create tables if they do not already exist."""
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
              id TEXT PRIMARY KEY,
              type TEXT NOT NULL,
              source TEXT NOT NULL,
              description TEXT NOT NULL,
              timestamp TEXT NOT NULL,
              metadata TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edges (
              id TEXT PRIMARY KEY,
              source_node_id TEXT NOT NULL,
              target_node_id TEXT NOT NULL,
              edge_type TEXT NOT NULL,
              confidence REAL NOT NULL,
              evidence TEXT NOT NULL,
              UNIQUE(source_node_id, target_node_id, edge_type),
              FOREIGN KEY(source_node_id) REFERENCES nodes(id) ON DELETE CASCADE,
              FOREIGN KEY(target_node_id) REFERENCES nodes(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS patterns (
              id TEXT PRIMARY KEY,
              name TEXT NOT NULL UNIQUE,
              description TEXT NOT NULL,
              node_sequence TEXT NOT NULL,
              typical_duration REAL NOT NULL,
              frequency INTEGER NOT NULL,
              confidence REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS incidents (
              id TEXT PRIMARY KEY,
              title TEXT NOT NULL,
              severity TEXT NOT NULL,
              status TEXT NOT NULL,
              root_cause_node_ids TEXT NOT NULL,
              affected_services TEXT NOT NULL,
              causal_chain TEXT NOT NULL,
              started_at TEXT NOT NULL,
              resolved_at TEXT,
              narrative TEXT NOT NULL
            );
            """
        )
        self.conn.commit()

    def add_node(self, node: CausalNode) -> CausalNode:
        """Persist a node."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO nodes
            (id, type, source, description, timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                node.id,
                node.type,
                node.source,
                node.description,
                serialize_timestamp(node.timestamp),
                json.dumps(node.metadata, sort_keys=True),
            ),
        )
        self.conn.commit()
        return node

    def add_edge(self, edge: CausalEdge) -> CausalEdge:
        """Persist an edge, keeping the highest confidence duplicate."""
        existing = self.conn.execute(
            """
            SELECT id, confidence FROM edges
            WHERE source_node_id=? AND target_node_id=? AND edge_type=?
            """,
            (edge.source_node_id, edge.target_node_id, edge.edge_type),
        ).fetchone()
        if existing and float(existing["confidence"]) >= edge.confidence:
            return self.get_edge(existing["id"])
        if existing:
            edge.id = existing["id"]
        self.conn.execute(
            """
            INSERT OR REPLACE INTO edges
            (id, source_node_id, target_node_id, edge_type, confidence, evidence)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                edge.id,
                edge.source_node_id,
                edge.target_node_id,
                edge.edge_type,
                edge.confidence,
                json.dumps(edge.evidence, sort_keys=True),
            ),
        )
        self.conn.commit()
        return edge

    def add_pattern(self, pattern: CausalPattern) -> CausalPattern:
        """Persist a learned pattern."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO patterns
            (id, name, description, node_sequence, typical_duration, frequency, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pattern.id,
                pattern.name,
                pattern.description,
                json.dumps(pattern.node_sequence),
                pattern.typical_duration,
                pattern.frequency,
                pattern.confidence,
            ),
        )
        self.conn.commit()
        return pattern

    def add_incident(self, incident: Incident) -> Incident:
        """Persist an incident."""
        self.conn.execute(
            """
            INSERT OR REPLACE INTO incidents
            (id, title, severity, status, root_cause_node_ids, affected_services,
             causal_chain, started_at, resolved_at, narrative)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                incident.id,
                incident.title,
                incident.severity,
                incident.status,
                json.dumps(incident.root_cause_node_ids),
                json.dumps(incident.affected_services),
                json.dumps(incident.causal_chain),
                serialize_timestamp(incident.started_at),
                serialize_timestamp(incident.resolved_at) if incident.resolved_at else None,
                incident.narrative,
            ),
        )
        self.conn.commit()
        return incident

    def list_nodes(self, since: datetime | str | None = None) -> list[CausalNode]:
        """Return nodes ordered by timestamp."""
        params: tuple[Any, ...] = ()
        query = "SELECT * FROM nodes"
        if since is not None:
            query += " WHERE timestamp >= ?"
            params = (serialize_timestamp(parse_timestamp(since)),)
        query += " ORDER BY timestamp ASC"
        return [self._row_to_node(row) for row in self.conn.execute(query, params)]

    def list_edges(self) -> list[CausalEdge]:
        """Return all edges."""
        return [self._row_to_edge(row) for row in self.conn.execute("SELECT * FROM edges")]

    def list_patterns(self) -> list[CausalPattern]:
        """Return learned patterns ordered by confidence."""
        rows = self.conn.execute("SELECT * FROM patterns ORDER BY confidence DESC, frequency DESC")
        return [self._row_to_pattern(row) for row in rows]

    def list_incidents(self) -> list[Incident]:
        """Return incidents ordered by start time descending."""
        rows = self.conn.execute("SELECT * FROM incidents ORDER BY started_at DESC")
        return [self._row_to_incident(row) for row in rows]

    def get_node(self, node_id: str) -> CausalNode:
        """Load one node by id."""
        row = self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        if row is None:
            raise KeyError(f"node not found: {node_id}")
        return self._row_to_node(row)

    def get_edge(self, edge_id: str) -> CausalEdge:
        """Load one edge by id."""
        row = self.conn.execute("SELECT * FROM edges WHERE id=?", (edge_id,)).fetchone()
        if row is None:
            raise KeyError(f"edge not found: {edge_id}")
        return self._row_to_edge(row)

    def get_incident(self, incident_id: str) -> Incident:
        """Load one incident by id."""
        row = self.conn.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
        if row is None:
            raise KeyError(f"incident not found: {incident_id}")
        return self._row_to_incident(row)

    def as_graph_json(self) -> dict[str, Any]:
        """Return a JSON-serializable graph representation."""
        return {
            "nodes": [self._public_dict(node) for node in self.list_nodes()],
            "edges": [asdict(edge) for edge in self.list_edges()],
        }

    def _public_dict(self, node: CausalNode) -> dict[str, Any]:
        data = asdict(node)
        data["timestamp"] = serialize_timestamp(node.timestamp)
        return data

    def _row_to_node(self, row: sqlite3.Row) -> CausalNode:
        return CausalNode(
            id=row["id"],
            type=row["type"],
            source=row["source"],
            description=row["description"],
            timestamp=row["timestamp"],
            metadata=json.loads(row["metadata"]),
        )

    def _row_to_edge(self, row: sqlite3.Row) -> CausalEdge:
        return CausalEdge(
            id=row["id"],
            source_node_id=row["source_node_id"],
            target_node_id=row["target_node_id"],
            edge_type=row["edge_type"],
            confidence=float(row["confidence"]),
            evidence=json.loads(row["evidence"]),
        )

    def _row_to_pattern(self, row: sqlite3.Row) -> CausalPattern:
        return CausalPattern(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            node_sequence=json.loads(row["node_sequence"]),
            typical_duration=float(row["typical_duration"]),
            frequency=int(row["frequency"]),
            confidence=float(row["confidence"]),
        )

    def _row_to_incident(self, row: sqlite3.Row) -> Incident:
        return Incident(
            id=row["id"],
            title=row["title"],
            severity=row["severity"],
            status=row["status"],
            root_cause_node_ids=json.loads(row["root_cause_node_ids"]),
            affected_services=json.loads(row["affected_services"]),
            causal_chain=json.loads(row["causal_chain"]),
            started_at=row["started_at"],
            resolved_at=row["resolved_at"],
            narrative=row["narrative"],
        )
