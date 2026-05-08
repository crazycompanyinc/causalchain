"""OpenTelemetry trace ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalEdge, CausalNode, parse_timestamp
from causalchain.graph.builder import CausalGraphBuilder


class OpenTelemetryIngestor:
    """Convert OpenTelemetry spans into causal graph nodes and span edges."""

    def __init__(self, db: CausalChainDB, builder: CausalGraphBuilder | None = None) -> None:
        self.db = db
        self.builder = builder or CausalGraphBuilder(db)

    def ingest(self, payload: dict[str, Any] | list[dict[str, Any]]) -> dict[str, Any]:
        """Ingest OTLP JSON or a plain list of span dictionaries."""
        spans = self._extract_spans(payload)
        by_span_id: dict[str, CausalNode] = {}
        created: list[CausalNode] = []
        for span in sorted(spans, key=self._span_start):
            node = self._span_to_node(span)
            self.db.add_node(node)
            self.builder.build_edges_for_node(node)
            span_id = str(span.get("spanId") or span.get("span_id") or node.id)
            by_span_id[span_id] = node
            created.append(node)

        edges: list[CausalEdge] = []
        for span in spans:
            span_id = str(span.get("spanId") or span.get("span_id") or "")
            parent_id = span.get("parentSpanId") or span.get("parent_span_id")
            if parent_id and span_id in by_span_id and str(parent_id) in by_span_id:
                parent = by_span_id[str(parent_id)]
                child = by_span_id[span_id]
                edges.append(
                    self.db.add_edge(
                        CausalEdge(
                            parent.id,
                            child.id,
                            "propagates_to",
                            0.96,
                            {
                                "trace_id": child.metadata.get("trace_id"),
                                "span_id": span_id,
                                "parent_span_id": str(parent_id),
                                "reason": "OpenTelemetry parent span relationship",
                            },
                        )
                    )
                )
        return {"nodes": created, "edges": edges}

    def _extract_spans(self, payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if "resourceSpans" not in payload:
            return list(payload.get("spans", []))
        spans: list[dict[str, Any]] = []
        for resource_span in payload.get("resourceSpans", []):
            resource_attrs = self._attributes(resource_span.get("resource", {}).get("attributes", []))
            for scope_span in resource_span.get("scopeSpans", []):
                for span in scope_span.get("spans", []):
                    merged = dict(span)
                    merged.setdefault("resource_attributes", resource_attrs)
                    spans.append(merged)
        return spans

    def _span_to_node(self, span: dict[str, Any]) -> CausalNode:
        attrs = self._attributes(span.get("attributes", []))
        attrs.update(span.get("resource_attributes", {}))
        status = span.get("status", {})
        is_error = status.get("code") in {"STATUS_CODE_ERROR", 2} or attrs.get("error") is True
        node_type = "error" if is_error else "trace_span"
        service = attrs.get("service.name") or attrs.get("service") or span.get("serviceName") or "unknown-service"
        name = span.get("name", "unnamed span")
        trace_id = span.get("traceId") or span.get("trace_id")
        span_id = span.get("spanId") or span.get("span_id")
        duration_ms = self._duration_ms(span)
        description = f"Trace span {name}"
        if is_error:
            description = f"Errored trace span {name}"
        metadata = {
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": span.get("parentSpanId") or span.get("parent_span_id"),
            "operation": name,
            "duration_ms": duration_ms,
            "attributes": attrs,
            "system": attrs.get("system") or attrs.get("deployment.environment"),
        }
        return CausalNode(node_type, str(service), description, self._span_start(span), metadata)

    def _span_start(self, span: dict[str, Any]) -> datetime:
        raw = span.get("startTimeUnixNano") or span.get("start_time_unix_nano")
        if raw:
            return datetime.fromtimestamp(int(raw) / 1_000_000_000, tz=timezone.utc)
        return parse_timestamp(span.get("startTime") or span.get("start_time"))

    def _duration_ms(self, span: dict[str, Any]) -> float | None:
        start = span.get("startTimeUnixNano") or span.get("start_time_unix_nano")
        end = span.get("endTimeUnixNano") or span.get("end_time_unix_nano")
        if start and end:
            return round((int(end) - int(start)) / 1_000_000, 3)
        return None

    def _attributes(self, attributes: list[dict[str, Any]]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for attr in attributes:
            key = attr.get("key")
            value = attr.get("value", {})
            if key:
                parsed[key] = next(iter(value.values())) if isinstance(value, dict) and value else value
        return parsed
