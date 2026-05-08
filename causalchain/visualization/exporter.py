"""Export causal graphs as DOT, HTML, or ASCII."""

from __future__ import annotations

import html

from causalchain.core.db import CausalChainDB
from causalchain.graph.analyzer import CausalGraphAnalyzer


class GraphVisualizationExporter:
    """Render causal graphs in multiple portable formats."""

    def __init__(self, db: CausalChainDB) -> None:
        self.db = db
        self.analyzer = CausalGraphAnalyzer(db)

    def dot(self) -> str:
        """Return Graphviz DOT."""
        return self.analyzer.to_dot()

    def ascii(self) -> str:
        """Return a compact ASCII adjacency view."""
        lines = ["CausalChain graph"]
        for node in self.db.list_nodes():
            lines.append(f"[{node.id[:8]}] {node.source} {node.type}: {node.description}")
            for edge in self.analyzer.outgoing_edges(node.id):
                target = self.db.get_node(edge.target_node_id)
                lines.append(f"  -> [{target.id[:8]}] {target.source} {target.type} ({edge.edge_type} {edge.confidence:.2f})")
        return "\n".join(lines)

    def html(self) -> str:
        """Return dependency-free interactive HTML."""
        graph = self.analyzer.graph_json()
        nodes = "\n".join(
            f'<li data-id="{html.escape(node["id"])}"><button>{html.escape(node["source"])} {html.escape(node["type"])}</button><span>{html.escape(node["description"])}</span></li>'
            for node in graph["nodes"]
        )
        edges = "\n".join(
            f'<li>{html.escape(edge["source_node_id"][:8])} -> {html.escape(edge["target_node_id"][:8])} {html.escape(edge["edge_type"])} {edge["confidence"]:.2f}</li>'
            for edge in graph["edges"]
        )
        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CausalChain Graph</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #17202a; }}
main {{ display: grid; grid-template-columns: minmax(16rem, 1fr) minmax(16rem, 1fr); gap: 2rem; }}
li {{ margin: .5rem 0; }}
button {{ margin-right: .5rem; }}
.selected {{ outline: 2px solid #0f766e; }}
@media (max-width: 760px) {{ main {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<h1>CausalChain Graph</h1>
<main><section><h2>Nodes</h2><ul>{nodes}</ul></section><section><h2>Edges</h2><ul>{edges}</ul></section></main>
<script>
document.querySelectorAll('button').forEach((button) => button.addEventListener('click', () => {{
  document.querySelectorAll('li').forEach((item) => item.classList.remove('selected'));
  button.closest('li').classList.add('selected');
}}));
</script>
</body>
</html>"""
