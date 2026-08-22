"""Tests for the 3D site-graph radial layout (``site_graph_3d.layout``)."""

from __future__ import annotations

import json
import math

from app_support.site_graph_3d.graph_data import build_site_graph_model
from app_support.site_graph_3d.layout import assign_positions


def _node(node_id: str, parent: str | None = None, *, size_scale: float = 1.0) -> dict[str, object]:
    return {
        "id": node_id,
        "parent": parent,
        "is_root": parent is None,
        "size_scale": size_scale,
    }


def _body_radius(node: dict[str, object]) -> float:
    """Mirror the viewer's body sizing (max sun / planet radius) for overlap checks."""
    scale = float(node.get("size_scale", 0.0) or 0.0)
    if node.get("is_root"):
        return 3.4 + scale * 1.6
    return 0.6 + scale * 2.4


def _distance(a: dict[str, object], b: dict[str, object]) -> float:
    return math.hypot(float(a["x"]) - float(b["x"]), float(a["z"]) - float(b["z"]))


def _assert_no_overlap(nodes: list[dict[str, object]]) -> None:
    for i, first in enumerate(nodes):
        for second in nodes[i + 1 :]:
            gap = _distance(first, second)
            need = _body_radius(first) + _body_radius(second)
            assert gap >= need - 1e-6, f"{first['id']} and {second['id']} overlap: {gap} < {need}"


def test_single_root_sits_at_center() -> None:
    nodes = [_node("root"), _node("a", "root"), _node("b", "root")]

    assign_positions(nodes)

    root = next(n for n in nodes if n["id"] == "root")
    assert (root["x"], root["y"], root["z"]) == (0.0, 0.0, 0.0)


def test_children_are_farther_from_center_than_their_parent() -> None:
    nodes = [_node("root"), _node("a", "root"), _node("a1", "a")]

    assign_positions(nodes)

    depth = {n["id"]: math.hypot(float(n["x"]), float(n["z"])) for n in nodes}
    assert depth["root"] < depth["a"] < depth["a1"]


def test_positions_are_deterministic() -> None:
    first = [_node("root"), _node("a", "root"), _node("b", "root"), _node("a1", "a")]
    second = [_node("root"), _node("a", "root"), _node("b", "root"), _node("a1", "a")]

    assign_positions(first)
    assign_positions(second)

    assert [(n["x"], n["z"]) for n in first] == [(n["x"], n["z"]) for n in second]


def test_no_overlap_in_a_broad_balanced_tree() -> None:
    nodes = [_node("root")]
    for branch in range(6):
        parent = f"b{branch}"
        nodes.append(_node(parent, "root"))
        for leaf in range(5):
            nodes.append(_node(f"{parent}_{leaf}", parent))

    assign_positions(nodes)

    _assert_no_overlap(nodes)


def test_no_overlap_in_a_dense_star() -> None:
    nodes = [_node("root")]
    nodes += [_node(f"leaf{i}", "root") for i in range(60)]

    assign_positions(nodes)

    _assert_no_overlap(nodes)


def test_no_overlap_in_a_deep_branching_tree() -> None:
    nodes = [_node("root")]
    frontier = ["root"]
    counter = 0
    for _ in range(3):  # three more levels, fan-out 4 -> 1 + 4 + 16 + 64 nodes
        next_frontier: list[str] = []
        for parent in frontier:
            for _ in range(4):
                counter += 1
                child = f"n{counter}"
                nodes.append(_node(child, parent))
                next_frontier.append(child)
        frontier = next_frontier

    assign_positions(nodes)

    _assert_no_overlap(nodes)


def test_bushy_tree_packs_compactly() -> None:
    # A realistic hub-and-spoke crawl (a hub page → section pages → leaf pages)
    # packs into a tight 2-D cluster rather than a sprawling ring, so ~900 pages
    # frame on screen at once with every page still visible.
    nodes = [_node("root")]
    for section in range(30):
        sec = f"s{section}"
        nodes.append(_node(sec, "root"))
        for leaf in range(30):
            nodes.append(_node(f"{sec}_{leaf}", sec))

    assign_positions(nodes)

    _assert_no_overlap(nodes)
    extent = max(math.hypot(float(n["x"]), float(n["z"])) for n in nodes)
    assert extent < 700.0  # ~930 pages stay within a compact disc (vs. thousands before)


def test_children_cluster_near_their_own_parent() -> None:
    # A child sits nearer its own parent than a sibling
    # branch's parent, so links stay short and the tree reads as clusters.
    nodes = [
        _node("root"),
        _node("a", "root"),
        _node("b", "root"),
        _node("a1", "a"),
        _node("a2", "a"),
        _node("b1", "b"),
        _node("b2", "b"),
    ]

    assign_positions(nodes)

    pos = {n["id"]: (float(n["x"]), float(n["z"])) for n in nodes}

    def dist(p: str, q: str) -> float:
        return math.hypot(pos[p][0] - pos[q][0], pos[p][1] - pos[q][1])

    for child, own, other in (
        ("a1", "a", "b"),
        ("a2", "a", "b"),
        ("b1", "b", "a"),
        ("b2", "b", "a"),
    ):
        assert dist(child, own) < dist(child, other)


def test_no_overlap_in_a_large_irregular_tree() -> None:
    # A deterministic, uneven tree (varying fan-out and depth) stresses packing.
    nodes = [_node("root")]
    frontier = ["root"]
    counter = 0
    while frontier and len(nodes) < 350:
        parent = frontier.pop(0)
        for _ in range(1 + counter % 4):  # 1..4 children, deterministic (no hashing)
            counter += 1
            child = f"n{counter}"
            nodes.append(_node(child, parent))
            if counter % 3:  # skip a third of nodes so branches vary in depth
                frontier.append(child)

    assign_positions(nodes)

    _assert_no_overlap(nodes)
    extent = max(math.hypot(float(n["x"]), float(n["z"])) for n in nodes)
    assert math.isfinite(extent) and extent > 0.0


def test_multiple_roots_share_a_ring_off_center() -> None:
    nodes = [_node("r1"), _node("r2"), _node("r3")]
    nodes += [_node(f"r1_{i}", "r1") for i in range(4)]

    assign_positions(nodes)

    for root_id in ("r1", "r2", "r3"):
        root = next(n for n in nodes if n["id"] == root_id)
        assert math.hypot(float(root["x"]), float(root["z"])) > 0.0
    _assert_no_overlap(nodes)


def test_unreachable_cycle_nodes_are_placed_off_center() -> None:
    # Neither node is a root and each points at the other: unreachable from a root.
    nodes = [_node("a", "b"), _node("b", "a")]
    nodes[0]["is_root"] = False
    nodes[1]["is_root"] = False

    assign_positions(nodes)

    for node in nodes:
        assert math.hypot(float(node["x"]), float(node["z"])) > 0.0
    _assert_no_overlap(nodes)


def test_cycle_reachable_from_a_root_terminates() -> None:
    # A node flagged as a root that still points at a child which points back:
    # the visiting guard must break the loop rather than recurse forever.
    nodes: list[dict[str, object]] = [
        {"id": "x", "parent": "y", "is_root": True, "size_scale": 1.0},
        {"id": "y", "parent": "x", "is_root": False, "size_scale": 1.0},
    ]

    assign_positions(nodes)

    assert all({"x", "y", "z"} <= node.keys() for node in nodes)
    _assert_no_overlap(nodes)


def test_build_site_graph_model_embeds_positions() -> None:
    lines = [
        {"url": "https://x/", "discovered_from": None, "status": "success", "page_size_kb": 9},
        {"url": "https://x/a", "discovered_from": "https://x/", "status": "success"},
    ]
    jsonl = "\n".join(json.dumps(line) for line in lines)

    model = build_site_graph_model(jsonl)

    for node in model["nodes"]:
        assert {"x", "y", "z"} <= node.keys()
        assert node["y"] == 0.0
