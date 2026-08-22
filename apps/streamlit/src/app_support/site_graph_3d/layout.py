"""Compute a compact circle-packed layout for the 3D site graph (pure Python).

Assigns each node a flat ``(x, y, z)`` world position so the viewer renders the
whole site as a legible cluster of clusters rather than a sprawl. One
deterministic recursion keeps it unit-testable without a browser:

1. **Pack** — each subtree is laid out around its own page: the page sits at the
   centre and its child subtrees are packed into concentric shells around it,
   biggest first, so a busy page fans its children into a tight 2-D disc (area
   grows ~ with the child count, radius ~ its root) instead of one wide ring.
2. **Nest** — a packed subtree becomes a single disc that its parent packs in
   turn, so the seed page ends up at the centre with everything clustered around
   it and the overall extent stays compact enough to see every page at once.

Shells clear the central body and each other and sibling discs never overlap, so
the layout is overlap-free by construction. ``y`` is always ``0`` (the layout is
planar); the viewer keeps its gentle tilt and spin. (A deep single-child chain —
rare on real hub-and-spoke sites — extends further than a bushy subtree.)
"""

from __future__ import annotations

import math
from typing import Any

__all__ = ["assign_positions"]

# World-unit tuning. The viewer's planet bodies run ~0.6-3.0 and a sun ~3.4-5.0,
# so a leaf disc and the central hole clear the largest bodies with a little slack.
_LEAF_RADIUS = 4.5  # bounding-circle radius of a childless page (> largest planet)
_SUN_RADIUS = 5.5  # central hole reserved for a seed page's sun body (> largest sun)
_GAP = 2.0  # clearance between adjacent bodies / shells
_BAND_GAP = 9.0  # radial gap out to the ring of unreachable (cycle) nodes
_FLOAT_ROUND = 4
_FULL_CIRCLE = 2 * math.pi


def assign_positions(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add flat circle-packed ``x`` / ``y`` / ``z`` positions to *nodes* in place.

    Each page sits at the centre of its subtree with its child subtrees packed
    into shells around it, and every packed subtree is itself packed by its
    parent, so the seed page ends up central with the whole site clustered around
    it and no two bodies overlap. Deterministic for a given graph (children are
    visited in ``id`` order). Nodes unreachable from any root — e.g. caught in a
    discovered-from cycle — ring the outside so nothing is dropped. Returns the
    same list.
    """
    by_id = {node["id"]: node for node in nodes}
    children = _children_by_parent(nodes, by_id)
    roots = sorted(
        node["id"] for node in nodes if node.get("is_root") or node.get("parent") not in by_id
    )
    positions: dict[str, tuple[float, float]] = {}
    if len(roots) == 1:
        placed, _ = _pack_subtree(roots[0], children, is_root=True, visiting=set())
        positions.update(placed)
    elif roots:
        _place_roots(roots, children, positions)
    _place_unreachable(nodes, positions)

    for node in nodes:
        x, z = positions.get(node["id"], (0.0, 0.0))
        node["x"] = round(x, _FLOAT_ROUND)
        node["y"] = 0.0
        node["z"] = round(z, _FLOAT_ROUND)
    return nodes


def _children_by_parent(
    nodes: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]
) -> dict[str, list[str]]:
    """Map each page to its resolvable children, sorted by id for determinism."""
    children: dict[str, list[str]] = {}
    for node in nodes:
        parent = node.get("parent")
        if parent is not None and parent in by_id and parent != node["id"]:
            children.setdefault(parent, []).append(node["id"])
    for kids in children.values():
        kids.sort()
    return children


def _pack_subtree(
    node_id: str,
    children: dict[str, list[str]],
    *,
    is_root: bool,
    visiting: set[str],
) -> tuple[dict[str, tuple[float, float]], float]:
    """Return (positions relative to *node_id* at the origin, bounding radius).

    The page sits at the origin; its child subtrees are laid out recursively and
    then packed as discs into shells around it (see :func:`_pack_around`). A cycle
    back-edge is treated as a leaf so the recursion terminates.
    """
    body = _SUN_RADIUS if is_root else _LEAF_RADIUS
    visiting.add(node_id)
    kids = [kid for kid in children.get(node_id, []) if kid not in visiting]
    if not kids:
        visiting.discard(node_id)
        return {node_id: (0.0, 0.0)}, body
    child_layouts = [_pack_subtree(kid, children, is_root=False, visiting=visiting) for kid in kids]
    visiting.discard(node_id)
    centres, bound = _pack_around(body, [radius for _, radius in child_layouts])
    placed: dict[str, tuple[float, float]] = {node_id: (0.0, 0.0)}
    for (sub_positions, _), (cx, cy) in zip(child_layouts, centres, strict=True):
        for nid, (x, y) in sub_positions.items():
            placed[nid] = (x + cx, y + cy)
    return placed, bound


def _pack_around(
    centre_radius: float, disc_radii: list[float]
) -> tuple[list[tuple[float, float]], float]:
    """Pack child discs into shells around a central hole; keep the parent clear.

    Discs are seated biggest-first so each shell's slot is sized to its largest
    member; a shell holds as many discs as fit around its ring and the next shell
    steps out past it. Returns each disc's centre (in the input order) and the
    cluster's bounding radius. Adjacent discs on a ring, discs on neighbouring
    shells, and the central hole all keep a ``_GAP`` of clearance, so nothing
    overlaps.
    """
    order = sorted(range(len(disc_radii)), key=lambda i: (-disc_radii[i], i))
    centres: list[tuple[float, float]] = [(0.0, 0.0)] * len(disc_radii)
    bound = centre_radius
    inner = centre_radius  # distance from the origin to the inner edge of the next shell
    cursor = 0
    while cursor < len(order):
        slot = disc_radii[order[cursor]]  # the largest remaining disc sizes this shell
        ring = inner + _GAP + slot
        step = 2 * math.asin(min(1.0, (slot + _GAP / 2) / ring))  # min angle between slots
        capacity = max(1, int(_FULL_CIRCLE / step))
        shell = order[cursor : cursor + capacity]
        for position, index in enumerate(shell):
            theta = _FULL_CIRCLE * position / len(shell)
            cx, cy = ring * math.cos(theta), ring * math.sin(theta)
            centres[index] = (cx, cy)
            bound = max(bound, math.hypot(cx, cy) + disc_radii[index])
        inner = ring + slot
        cursor += len(shell)
    return centres, bound


def _place_roots(
    roots: list[str],
    children: dict[str, list[str]],
    positions: dict[str, tuple[float, float]],
) -> None:
    """Pack multiple seed pages (each its own sun) around the origin."""
    layouts = [_pack_subtree(root, children, is_root=True, visiting=set()) for root in roots]
    centres, _ = _pack_around(0.0, [radius for _, radius in layouts])
    for (placed, _), (cx, cy) in zip(layouts, centres, strict=True):
        for nid, (x, y) in placed.items():
            positions[nid] = (x + cx, y + cy)


def _place_unreachable(
    nodes: list[dict[str, Any]], positions: dict[str, tuple[float, float]]
) -> None:
    """Ring any node unreachable from a root (e.g. a cycle) around the outside.

    Crawl graphs are single-parent forests, so this is a rare safety net; without
    it such a node would default to the centre and overlap the sun.
    """
    unreachable = sorted(node["id"] for node in nodes if node["id"] not in positions)
    if not unreachable:
        return
    extent = max((math.hypot(x, z) for x, z in positions.values()), default=0.0)
    spacing = (2 * _LEAF_RADIUS + _GAP) / (2 * math.sin(math.pi / max(len(unreachable), 2)))
    ring = max(extent + _BAND_GAP + _LEAF_RADIUS, spacing)
    for index, node_id in enumerate(unreachable):
        theta = _FULL_CIRCLE * index / len(unreachable)
        positions[node_id] = (ring * math.cos(theta), ring * math.sin(theta))
