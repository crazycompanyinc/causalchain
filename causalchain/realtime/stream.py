"""Synchronous real-time graph update stream."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalNode
from causalchain.graph.analyzer import CausalGraphAnalyzer
from causalchain.graph.builder import CausalGraphBuilder
from causalchain.tracing import OpenTelemetryIngestor

GraphSubscriber = Callable[[dict[str, Any]], None]


class RealTimeCausalGraph:
    """Maintain a live graph and notify subscribers after each ingest."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db
        self.builder = CausalGraphBuilder(db)
        self.subscribers: list[GraphSubscriber] = []
        self.sequence = 0

    def subscribe(self, callback: GraphSubscriber) -> None:
        """Register a callback receiving graph snapshots."""
        self.subscribers.append(callback)

    def ingest_event(self, type: str, source: str, description: str, timestamp: Any = None, metadata: dict[str, Any] | None = None) -> CausalNode:
        """Ingest one event and publish an updated snapshot."""
        node = self.builder.ingest_event(type, source, description, timestamp, metadata)
        self._publish("event", [node.id])
        return node

    def ingest_trace(self, payload: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
        """Ingest trace spans and publish an updated snapshot."""
        result = OpenTelemetryIngestor(self.db, self.builder).ingest(payload)
        self._publish("trace", [node.id for node in result["nodes"]])
        return result

    def snapshot(self) -> dict[str, Any]:
        """Return the current graph snapshot."""
        graph = CausalGraphAnalyzer(self.db).graph_json()
        graph["sequence"] = self.sequence
        return graph

    def _publish(self, update_type: str, node_ids: list[str]) -> None:
        self.sequence += 1
        update = self.snapshot()
        update["update_type"] = update_type
        update["changed_node_ids"] = node_ids
        for subscriber in list(self.subscribers):
            subscriber(update)
