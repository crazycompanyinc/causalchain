"""Analyze causal graphs."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict
from typing import Any

from causalchain.core.db import CausalChainDB
from causalchain.core.models import CausalEdge, CausalNode, serialize_timestamp


class CausalGraphAnalyzer:
    """Graph algorithms for causal paths, roots, and export."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db

    def incoming_edges(self, node_id: str, min_confidence: float = 0.0) -> list[CausalEdge]:
        """Return incoming edges for a node ordered by confidence descending."""
        return sorted(
            [
                edge
                for edge in self.db.list_edges()
                if edge.target_node_id == node_id and edge.confidence >= min_confidence
            ],
            key=lambda edge: edge.confidence,
            reverse=True,
        )

    def outgoing_edges(self, node_id: str, min_confidence: float = 0.0) -> list[CausalEdge]:
        """Return outgoing edges for a node ordered by confidence descending."""
        return sorted(
            [
                edge
                for edge in self.db.list_edges()
                if edge.source_node_id == node_id and edge.confidence >= min_confidence
            ],
            key=lambda edge: edge.confidence,
            reverse=True,
        )

    def find_roots(self, symptom_node_ids: list[str], min_confidence: float = 0.24) -> list[str]:
        """Walk backwards and find root nodes with no incoming causal edge in the subgraph."""
        if not symptom_node_ids:
            return []
        visited: set[str] = set()
        roots: set[str] = set()
        queue: deque[str] = deque(symptom_node_ids)
        while queue:
            node_id = queue.popleft()
            if node_id in visited:
                continue
            visited.add(node_id)
            incoming = self.incoming_edges(node_id, min_confidence)
            if not incoming:
                roots.add(node_id)
                continue
            for edge in incoming[:3]:
                queue.append(edge.source_node_id)
        return sorted(roots, key=lambda node_id: self.db.get_node(node_id).timestamp)

    def best_chain_to(self, symptom_node_id: str, min_confidence: float = 0.24) -> list[str]:
        """Return the most confident backward chain ending at a symptom."""
        chain = [symptom_node_id]
        current = symptom_node_id
        seen = {symptom_node_id}
        while True:
            incoming = [edge for edge in self.incoming_edges(current, min_confidence) if edge.source_node_id not in seen]
            if not incoming:
                break
            best = incoming[0]
            chain.append(best.source_node_id)
            seen.add(best.source_node_id)
            current = best.source_node_id
        chain.reverse()
        return chain

    def find_paths(self, source_id: str, target_id: str, max_depth: int = 8) -> list[list[str]]:
        """Find simple paths from source to target."""
        paths: list[list[str]] = []
        queue: deque[tuple[str, list[str]]] = deque([(source_id, [source_id])])
        while queue:
            node_id, path = queue.popleft()
            if len(path) > max_depth:
                continue
            for edge in self.outgoing_edges(node_id):
                if edge.target_node_id in path:
                    continue
                new_path = path + [edge.target_node_id]
                if edge.target_node_id == target_id:
                    paths.append(new_path)
                else:
                    queue.append((edge.target_node_id, new_path))
        return paths

    def extract_node_sequence(self, node_ids: list[str]) -> list[str]:
        """Return node types for a chain."""
        return [self.db.get_node(node_id).type for node_id in node_ids]

    def graph_json(self) -> dict[str, Any]:
        """Return graph JSON with normalized timestamps."""
        nodes = []
        for node in self.db.list_nodes():
            data = asdict(node)
            data["timestamp"] = serialize_timestamp(node.timestamp)
            nodes.append(data)
        return {"nodes": nodes, "edges": [asdict(edge) for edge in self.db.list_edges()]}

    def to_dot(self) -> str:
        """Export the graph as Graphviz DOT."""
        lines = ["digraph causalchain {"]
        for node in self.db.list_nodes():
            label = f"{node.type}\\n{node.source}"
            lines.append(f'  "{node.id}" [label="{label}"];')
        for edge in self.db.list_edges():
            label = f"{edge.edge_type} {edge.confidence:.2f}"
            lines.append(f'  "{edge.source_node_id}" -> "{edge.target_node_id}" [label="{label}"];')
        lines.append("}")
        return "\n".join(lines)

    def chains_by_type(self) -> dict[tuple[str, ...], int]:
        """Count observed linear chains by node type sequence."""
        counts: dict[tuple[str, ...], int] = defaultdict(int)
        nodes = self.db.list_nodes()
        for node in nodes:
            chain = self.best_chain_to(node.id)
            if len(chain) >= 2:
                counts[tuple(self.extract_node_sequence(chain))] += 1
        return dict(counts)
