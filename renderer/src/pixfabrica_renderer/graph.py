from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class ClipCategory(StrEnum):
    VISUAL = "visual"
    SOUND = "sound"
    MATH = "math"
    LOGIC = "logic"


class PortConnection(BaseModel):
    node_id: str  # upstream legacy graph node id
    port: str  # output port on the upstream legacy graph node


class GraphNode(BaseModel):
    """Legacy DAG node (compose tooling). Timeline clips use RenderJob tracks."""

    id: str
    type: str
    category: ClipCategory
    inputs: dict[str, PortConnection] = {}


def topological_sort(nodes: dict[str, GraphNode]) -> list[str]:
    """Return legacy graph node IDs in topological order. Raises ValueError if a cycle is detected."""
    visited: set[str] = set()
    in_stack: set[str] = set()
    order: list[str] = []

    def visit(node_id: str) -> None:
        if node_id in in_stack:
            raise ValueError(f"Graph contains a cycle involving graph node '{node_id}'")
        if node_id in visited:
            return
        in_stack.add(node_id)
        for conn in nodes[node_id].inputs.values():
            if conn.node_id in nodes:
                visit(conn.node_id)
        in_stack.remove(node_id)
        visited.add(node_id)
        order.append(node_id)

    for node_id in nodes:
        visit(node_id)

    return order
