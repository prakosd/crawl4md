"""Assemble the standalone 3D viewer HTML from the frontend assets.

Pure Python — no Streamlit. Reads the viewer's HTML/CSS/JS assets, inlines them
into one self-contained document (three.js and d3-force still load from pinned
CDNs via the import map), and injects the per-crawl graph model plus localized
labels. The launcher passes the finished HTML to the inline component, which
turns it into a Blob and opens it in a new tab.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from app_support.site_graph_3d.graph_data import build_site_graph_model

__all__ = [
    "D3_FORCE_CDN",
    "D3_FORCE_VERSION",
    "TEXTURE_CDN_BASE",
    "THREE_CDN_BASE",
    "THREE_VERSION",
    "build_viewer_html",
]

# Pinned so the new tab always loads a known-good three.js (never @latest). Bump
# deliberately: the addons (OrbitControls, EffectComposer, UnrealBloomPass) must
# exist at this version on the CDN. Offline tabs won't render — this is a live,
# internet-connected viewer by design.
THREE_VERSION = "0.160.0"
THREE_CDN_BASE = f"https://cdn.jsdelivr.net/npm/three@{THREE_VERSION}"

# d3-force computes the viewer's layout in the browser (pinned like three.js): the
# ES-module bundle that jsdelivr serves at ``/+esm`` resolves via the import map.
D3_FORCE_VERSION = "3.0.0"
D3_FORCE_CDN = f"https://cdn.jsdelivr.net/npm/d3-force@{D3_FORCE_VERSION}/+esm"

# Realistic NASA planet/sun/star textures, pinned to a jsdelivr-served commit of
# the reference solar-system repo (CORS-enabled). The viewer enhances its
# procedural look with these when reachable and silently keeps procedural /
# black on failure, so the tab still works without them.
TEXTURE_CDN_BASE = (
    "https://cdn.jsdelivr.net/gh/SoumyaEXE/3d-Solar-System-ThreeJS@alpha/dist/textures"
)

_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
_STYLE_PLACEHOLDER = "__VIEWER_STYLE__"
_SCRIPT_PLACEHOLDER = "__VIEWER_SCRIPT__"
_THREE_BASE_PLACEHOLDER = "__THREE_BASE__"
_D3_FORCE_PLACEHOLDER = "__D3_FORCE_URL__"
_TEXTURE_BASE_PLACEHOLDER = "__TEXTURE_BASE_URL__"
_GRAPH_PLACEHOLDER = "__GRAPH_DATA__"
_LABELS_PLACEHOLDER = "__LABELS__"


def build_viewer_html(jsonl_text: str, labels: Mapping[str, str]) -> str:
    """Return the complete standalone viewer document for one crawl graph."""
    model = build_site_graph_model(jsonl_text)
    return (
        _viewer_template()
        .replace(_GRAPH_PLACEHOLDER, _embed_json(model))
        .replace(_LABELS_PLACEHOLDER, _embed_json(dict(labels)))
    )


@lru_cache(maxsize=1)
def _viewer_template() -> str:
    """Inline the static assets once; the graph/labels are filled per call.

    ``viewer.js`` is inlined into a ``<script type="module">`` element, so it must
    never contain the literal ``</script>``; the per-crawl graph/labels JSON is
    injected separately and ``<`` is escaped in :func:`_embed_json`.
    """
    return (
        _read_asset("viewer.html")
        .replace(_STYLE_PLACEHOLDER, _read_asset("viewer.css"))
        .replace(_SCRIPT_PLACEHOLDER, _read_asset("viewer.js"))
        .replace(_THREE_BASE_PLACEHOLDER, THREE_CDN_BASE)
        .replace(_D3_FORCE_PLACEHOLDER, D3_FORCE_CDN)
        .replace(_TEXTURE_BASE_PLACEHOLDER, TEXTURE_CDN_BASE)
    )


def _read_asset(name: str) -> str:
    return (_ASSETS_DIR / name).read_text(encoding="utf-8")


def _embed_json(value: Any) -> str:
    """JSON for embedding in a <script>; escape ``<`` so no ``</script>`` breaks out."""
    return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c")
