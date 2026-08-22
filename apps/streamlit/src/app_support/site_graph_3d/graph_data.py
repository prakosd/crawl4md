"""Shape a crawl's ``site_graph.jsonl`` into a 3D-viewer node/edge model.

Pure Python — no Streamlit, no file I/O. The caller passes the raw JSONL text and
gets back a JSON-ready ``dict`` that the Three.js viewer renders as a solar
system: one planet per page, sized by page weight, coloured by crawl status, and
linked to the page it was discovered from.

Field names mirror ``crawl4md._internal.site_graph`` (the record producer):
``url``, ``discovered_from`` (``None`` for a seed/root page), ``page_size_kb``
(``None`` when a page failed or was skipped), ``status`` (``discovered`` /
``success`` / ``fail`` / ``skipped``), ``depth`` (0 for a root), and ``round_num``
(``None`` or the retry round a terminal result landed on).
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["build_site_graph_model"]

# ── Raw record keys (mirror crawl4md._internal.site_graph) ───────────────────
_KEY_URL = "url"
_KEY_DISCOVERED_FROM = "discovered_from"
_KEY_PAGE_SIZE_KB = "page_size_kb"
_KEY_STATUS = "status"
_KEY_DEPTH = "depth"
_KEY_ROUND_NUM = "round_num"

# ── Crawl status values ──────────────────────────────────────────────────────
_STATUS_SUCCESS = "success"
_STATUS_FAIL = "fail"
_STATUS_SKIPPED = "skipped"
_STATUS_DISCOVERED = "discovered"
# Colour category the viewer maps to a planet hue. Unknown statuses fall back to
# the neutral "discovered" tint so a future status never renders as an error.
_STATUS_TO_COLOR: dict[str, str] = {
    _STATUS_SUCCESS: _STATUS_SUCCESS,
    _STATUS_FAIL: _STATUS_FAIL,
    _STATUS_SKIPPED: _STATUS_SKIPPED,
    _STATUS_DISCOVERED: _STATUS_DISCOVERED,
}
_DEFAULT_COLOR = _STATUS_DISCOVERED

# ── Derived visual tuning ────────────────────────────────────────────────────
# A page counts as "retried" (yellow accent) once it lands beyond the initial
# round. round_num is 1 for the first pass, so > 1 means at least one retry.
_RETRY_ROUND_THRESHOLD = 1
# size_scale at/above this becomes a ringed gas giant in the viewer.
_GIANT_SIZE_THRESHOLD = 0.72
# Richness blends how much a page holds (size) with how much it links out
# (children), driving the lush-Earth <-> barren-Mars surface look.
_RICHNESS_SIZE_WEIGHT = 0.6
_RICHNESS_LINK_WEIGHT = 0.4
# All present pages share one size when their weights are identical; a mid scale
# keeps them visible without implying they are the largest possible.
_UNIFORM_SIZE_SCALE = 0.5
# Round derived floats so the embedded JSON stays compact and deterministic.
_FLOAT_ROUND = 4


def build_site_graph_model(jsonl_text: str) -> dict[str, Any]:
    """Build the viewer's node/edge model from raw ``site_graph.jsonl`` text.

    Returns a JSON-serialisable ``dict`` with ``nodes``, ``edges``, ``root_ids``,
    and summary ``stats``. Malformed or empty lines are skipped so a partially
    written log still renders.
    """
    records = _parse_records(jsonl_text)
    nodes = _build_nodes(records)
    edges = _build_edges(nodes)
    root_ids = [node["id"] for node in nodes if node["is_root"]]
    return {
        "nodes": nodes,
        "edges": edges,
        "root_ids": root_ids,
        "stats": _build_stats(nodes),
    }


def _parse_records(jsonl_text: str) -> list[dict[str, Any]]:
    """Parse JSONL into records, keeping the last line per URL (dedupe)."""
    by_url: dict[str, dict[str, Any]] = {}
    for raw_line in jsonl_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(record, dict):
            continue
        url = record.get(_KEY_URL)
        if not isinstance(url, str) or not url:
            continue
        by_url[url] = record
    return list(by_url.values())


def _build_nodes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known_urls = {str(record[_KEY_URL]) for record in records}
    child_counts = _count_children(records, known_urls)
    size_scales = _size_scales(records)
    max_children = max(child_counts.values(), default=0)

    nodes: list[dict[str, Any]] = []
    for record in records:
        url = str(record[_KEY_URL])
        discovered_from = _clean_parent(record.get(_KEY_DISCOVERED_FROM))
        parent = discovered_from if discovered_from in known_urls else None
        child_count = child_counts.get(url, 0)
        size_scale = size_scales.get(url, 0.0)
        link_scale = (child_count / max_children) if max_children else 0.0
        richness = _round(_RICHNESS_SIZE_WEIGHT * size_scale + _RICHNESS_LINK_WEIGHT * link_scale)
        status = str(record.get(_KEY_STATUS) or _STATUS_DISCOVERED)
        round_num = _coerce_int(record.get(_KEY_ROUND_NUM))
        nodes.append(
            {
                "id": url,
                "url": url,
                "discovered_from": discovered_from,
                "parent": parent,
                "depth": max(_coerce_int(record.get(_KEY_DEPTH)) or 0, 0),
                "status": status,
                "round_num": round_num,
                "page_size_kb": _coerce_float(record.get(_KEY_PAGE_SIZE_KB)),
                "child_count": child_count,
                "size_scale": _round(size_scale),
                "richness": richness,
                "is_root": discovered_from is None,
                "is_giant": size_scale >= _GIANT_SIZE_THRESHOLD,
                "color_category": _STATUS_TO_COLOR.get(status, _DEFAULT_COLOR),
                "retry": round_num is not None and round_num > _RETRY_ROUND_THRESHOLD,
            }
        )
    return nodes


def _count_children(records: list[dict[str, Any]], known_urls: set[str]) -> dict[str, int]:
    """Count how many pages were discovered from each page (resolvable links)."""
    counts: dict[str, int] = {}
    for record in records:
        parent = _clean_parent(record.get(_KEY_DISCOVERED_FROM))
        if parent is not None and parent in known_urls:
            counts[parent] = counts.get(parent, 0) + 1
    return counts


def _size_scales(records: list[dict[str, Any]]) -> dict[str, float]:
    """Min-max normalise page_size_kb to 0..1; missing sizes map to 0."""
    sizes: dict[str, float] = {}
    present: list[tuple[str, float]] = []
    for record in records:
        url = str(record[_KEY_URL])
        kb = _coerce_float(record.get(_KEY_PAGE_SIZE_KB))
        if kb is not None and kb > 0:
            present.append((url, kb))
        else:
            sizes[url] = 0.0
    if not present:
        return sizes
    values = [kb for _, kb in present]
    low, high = min(values), max(values)
    span = high - low
    for url, kb in present:
        sizes[url] = _UNIFORM_SIZE_SCALE if span == 0 else (kb - low) / span
    return sizes


def _build_edges(nodes: list[dict[str, Any]]) -> list[dict[str, str]]:
    """One edge per node that has a resolvable parent (drawn as a link line)."""
    return [
        {"source": str(node["parent"]), "target": str(node["id"])}
        for node in nodes
        if node["parent"] is not None
    ]


def _build_stats(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    for node in nodes:
        status = str(node["status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "total": len(nodes),
        "by_status": status_counts,
        "max_depth": max((int(node["depth"]) for node in nodes), default=0),
    }


def _clean_parent(value: Any) -> str | None:
    """Normalise a discovered_from value to a non-empty string or None."""
    if isinstance(value, str) and value:
        return value
    return None


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _round(value: float) -> float:
    return round(float(value), _FLOAT_ROUND)
