"""Dataclass models used across CausalChain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


VALID_NODE_TYPES = {
    "deploy",
    "error",
    "metric_anomaly",
    "config_change",
    "traffic_spike",
    "recovery",
    "trace_span",
    "business_metric",
    "agent_action",
    "prediction",
}

VALID_EDGE_TYPES = {
    "triggers",
    "enables",
    "correlates_with",
    "blocks",
    "degrades",
    "propagates_to",
    "impacts",
    "mitigates",
}

VALID_SEVERITIES = {"low", "medium", "high", "critical"}
VALID_STATUSES = {"open", "investigating", "resolved"}


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def parse_timestamp(value: datetime | str | None) -> datetime:
    """Normalize timestamp input into a timezone-aware datetime."""
    if value is None:
        return utc_now()
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("timestamp must be datetime, ISO string, or None")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def serialize_timestamp(value: datetime) -> str:
    """Serialize a timestamp to a stable ISO-8601 string."""
    return parse_timestamp(value).isoformat()


@dataclass(slots=True)
class CausalNode:
    """An event, state, or condition in the causal graph."""

    type: str
    source: str
    description: str
    timestamp: datetime | str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if self.type not in VALID_NODE_TYPES:
            raise ValueError(f"invalid node type: {self.type}")
        if not self.source.strip():
            raise ValueError("source is required")
        if not self.description.strip():
            raise ValueError("description is required")
        self.timestamp = parse_timestamp(self.timestamp)
        if self.metadata is None:
            self.metadata = {}


@dataclass(slots=True)
class CausalEdge:
    """A causal relationship between two nodes."""

    source_node_id: str
    target_node_id: str
    edge_type: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if self.edge_type not in VALID_EDGE_TYPES:
            raise ValueError(f"invalid edge type: {self.edge_type}")
        if not self.source_node_id or not self.target_node_id:
            raise ValueError("edge node ids are required")
        if self.source_node_id == self.target_node_id:
            raise ValueError("self edges are not allowed")
        if not 0.0 <= float(self.confidence) <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        self.confidence = float(self.confidence)
        if self.evidence is None:
            self.evidence = {}


@dataclass(slots=True)
class CausalPattern:
    """A recurring causal chain learned from resolved incidents."""

    name: str
    description: str
    node_sequence: list[str]
    typical_duration: float
    frequency: int
    confidence: float
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("pattern name is required")
        if len(self.node_sequence) < 2:
            raise ValueError("pattern node_sequence must contain at least two node types")
        if self.frequency < 1:
            raise ValueError("pattern frequency must be at least 1")
        if self.typical_duration < 0:
            raise ValueError("typical_duration must be non-negative")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(slots=True)
class Incident:
    """A recorded incident and its causal chain."""

    title: str
    severity: str
    status: str
    root_cause_node_ids: list[str]
    affected_services: list[str]
    causal_chain: list[str]
    started_at: datetime | str
    resolved_at: datetime | str | None = None
    narrative: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("incident title is required")
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(f"invalid severity: {self.severity}")
        if self.status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {self.status}")
        self.started_at = parse_timestamp(self.started_at)
        self.resolved_at = parse_timestamp(self.resolved_at) if self.resolved_at else None
        if self.resolved_at and self.resolved_at < self.started_at:
            raise ValueError("resolved_at cannot be earlier than started_at")
