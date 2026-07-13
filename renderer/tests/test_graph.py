import pytest

from pixfabrica_renderer.graph import ClipCategory, GraphNode, PortConnection, topological_sort


def make_graph_node(node_id: str, inputs: dict[str, str] | None = None) -> GraphNode:
    """Create a minimal visual graph vertex for topology tests."""
    return GraphNode(
        id=node_id,
        type="test",
        category=ClipCategory.VISUAL,
        inputs={
            port: PortConnection(node_id=upstream, port="out")
            for port, upstream in (inputs or {}).items()
        },
    )


def test_linear_chain():
    # A -> B -> C
    nodes = {
        "A": make_graph_node("A"),
        "B": make_graph_node("B", {"in": "A"}),
        "C": make_graph_node("C", {"in": "B"}),
    }
    order = topological_sort(nodes)
    assert order.index("A") < order.index("B") < order.index("C")


def test_diamond():
    # A -> B, A -> C, B+C -> D
    nodes = {
        "A": make_graph_node("A"),
        "B": make_graph_node("B", {"in": "A"}),
        "C": make_graph_node("C", {"in": "A"}),
        "D": make_graph_node("D", {"b": "B", "c": "C"}),
    }
    order = topological_sort(nodes)
    assert order.index("A") < order.index("B")
    assert order.index("A") < order.index("C")
    assert order.index("B") < order.index("D")
    assert order.index("C") < order.index("D")


def test_cycle_raises():
    nodes = {
        "A": make_graph_node("A", {"in": "B"}),
        "B": make_graph_node("B", {"in": "A"}),
    }
    with pytest.raises(ValueError, match="cycle"):
        topological_sort(nodes)


def test_single_node():
    nodes = {"A": make_graph_node("A")}
    assert topological_sort(nodes) == ["A"]
