"""Detect causal links across services and systems."""

from __future__ import annotations

from datetime import timedelta

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalEdge


class CrossSystemCorrelator:
    """Infer cross-system edges using metadata, dependencies, and timing."""

    def __init__(self, db: CausalChainDB, system_dependencies: dict[str, list[str]] | None = None) -> None:
        self.db = db
        self.system_dependencies = system_dependencies or {}

    def correlate(self, window_minutes: int = 10) -> list[CausalEdge]:
        """Create cross-system causal edges for close, related events."""
        window = timedelta(minutes=window_minutes)
        nodes = self.db.list_nodes()
        edges = []
        for source in nodes:
            source_system = source.metadata.get("system")
            if not source_system:
                continue
            for target in nodes:
                target_system = target.metadata.get("system")
                if source.id == target.id or not target_system or source_system == target_system:
                    continue
                if not source.timestamp < target.timestamp <= source.timestamp + window:
                    continue
                confidence = self._confidence(source.source, target.source, str(source_system), str(target_system))
                if confidence < 0.35:
                    continue
                edges.append(
                    self.db.add_edge(
                        CausalEdge(
                            source.id,
                            target.id,
                            "propagates_to",
                            confidence,
                            {
                                "source_system": source_system,
                                "target_system": target_system,
                                "reason": f"{source.source} in {source_system} plausibly affected {target.source} in {target_system}",
                            },
                        )
                    )
                )
        return edges

    def _confidence(self, source: str, target: str, source_system: str, target_system: str) -> float:
        deps = self.system_dependencies.get(target_system, [])
        if source_system in deps:
            return 0.78
        if source == target:
            return 0.62
        if source.split("-")[0] == target.split("-")[0]:
            return 0.52
        return 0.36
