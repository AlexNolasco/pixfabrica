from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from pixfabrica_core.clips.base import ClipCategory  # noqa: F401  re-exported for graph models


class PortType(StrEnum):
    TEXTURE = "texture"
    AUDIO = "audio"
    FLOAT = "float"
    INT = "int"
    BOOL = "bool"
    STRING = "string"
    COLOR = "color"  # theme token name or raw hex


class PortConnection(BaseModel):
    """Legacy DAG wire from an upstream graph node's named output port."""

    node_id: str  # upstream graph node id (legacy DAG only)
    port: str  # output port name on the upstream graph node


class Transition(BaseModel):
    type: str  # "fade" | "slide" | "wipe" | ...
    duration: float  # seconds
    params: dict[str, Any] = Field(default_factory=dict)


class GraphNode(BaseModel):
    """Legacy DAG node (pre-timeline compose tooling). Timeline clips use ``RenderJob`` tracks."""

    id: str
    type: str  # plugin-registered type, e.g. "gradient_bg", "marquee_text"
    category: ClipCategory
    # input_port_name -> upstream connection
    inputs: dict[str, PortConnection] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)

    # legacy sound graph nodes — silence is padded before start_time
    start_time: float = 0.0
    # audio bus this legacy sound graph node publishes to
    audio_bus: str | None = None
    # legacy visual graph nodes — bus name for audio-reactive params
    bus_select: str | None = None

    # legacy track graph nodes — ordered child graph node ids for this track FBO
    children: list[str] = Field(default_factory=list)
    transition: Transition | None = None


class Graph(BaseModel):
    nodes: dict[str, GraphNode]
    # theme token -> value; travels with the job for white-label / multi-tenant
    theme: dict[str, str] = Field(default_factory=dict)
    fps: int = 30
    duration: float  # seconds
    width: int = 1920
    height: int = 1080


def topological_sort(nodes: dict[str, GraphNode]) -> list[str]:
    """Return legacy graph node ids in evaluation order (Kahn's algorithm)."""
    in_degree: dict[str, int] = {nid: 0 for nid in nodes}
    dependents: dict[str, list[str]] = {nid: [] for nid in nodes}

    for nid, node in nodes.items():
        for conn in node.inputs.values():
            if conn.node_id in nodes:
                in_degree[nid] += 1
                dependents[conn.node_id].append(nid)

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    order: list[str] = []

    while queue:
        nid = queue.pop(0)
        order.append(nid)
        for dependent in dependents[nid]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(order) != len(nodes):
        raise ValueError("Graph contains a cycle")

    return order
