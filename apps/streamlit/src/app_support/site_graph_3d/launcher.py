"""Streamlit launcher for the 3D site-graph viewer.

Thin UI adapter: reads a crawl's ``site_graph.jsonl``, assembles the standalone
viewer document (:mod:`viewer_assembler`), and mounts an inline CCv2 button that
opens it in a new browser tab. All rendering lives in the frontend assets; this
module only wires data + localized labels into the component.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import streamlit as st
from streamlit.components.v2 import component as component_v2

from app_support.app_runtime import _DEFAULT_LANGUAGE
from app_support.i18n import get_strings
from app_support.site_graph_3d.static_publish import (
    orrery_needs_refresh,
    orrery_static_target,
    write_orrery_html,
)
from app_support.site_graph_3d.viewer_assembler import build_viewer_html
from app_support.site_graph_3d.viewer_labels import viewer_labels
from app_support.support import GeneratedFile

__all__ = ["render_explore_3d_button"]

_COMPONENT_NAME = "crawl4md_site_graph_3d"
_ASSETS_DIR = Path(__file__).resolve().parent / "assets"
# The Streamlit main script lives in apps/streamlit/; its ``static/`` folder is
# served at the ``app/static`` URL when ``server.enableStaticServing`` is on.
_STATIC_ROOT = Path(__file__).resolve().parents[3] / "static"
# launcher.js renders the button into the component's host element directly, so
# the mounted HTML only needs to be a minimal, unambiguous inline root.
_LAUNCHER_HTML = """
<span></span>
"""


@lru_cache(maxsize=1)
def _component():
    """Register the inline launcher component once (deferred to first render)."""
    return component_v2(
        _COMPONENT_NAME,
        html=_LAUNCHER_HTML,
        js=(_ASSETS_DIR / "launcher.js").read_text(encoding="utf-8"),
        css=(_ASSETS_DIR / "launcher.css").read_text(encoding="utf-8"),
    )


def render_explore_3d_button(
    file: GeneratedFile,
    *,
    disabled: bool = False,
    key_suffix: str = "tree",
    full_width: bool = False,
) -> None:
    """Mount the "Explore in 3D" button for a ``site_graph.jsonl`` file.

    *key_suffix* disambiguates the component when the same crawl's graph backs two
    buttons in one run (the download tree and the ready-result panel). *full_width*
    stretches the button to fill its column (used beside the ready-result Download).
    """
    language = st.session_state.get("language", _DEFAULT_LANGUAGE)
    strings = get_strings(language)
    # A disabled button can't be clicked, and the panel auto-refreshes while a job
    # runs, so skip the (larger) document rebuild + publish until it's live.
    if disabled:
        url = ""
    else:
        url = _publish_viewer(file, language)
        if url is None:
            return
    _component()(
        data={
            "url": url,
            "label": strings["FILES_EXPLORE_3D_LABEL"],
            "help": strings["FILES_EXPLORE_3D_HELP"],
            "disabled": bool(disabled),
            "full_width": bool(full_width),
        },
        key=_explore_3d_key(st.session_state.get("session_id", ""), key_suffix, file.relative_path),
    )


def _explore_3d_key(session_id: str, key_suffix: str, relative_path: str) -> str:
    """Return the Streamlit component key for one Explore-in-3D button.

    *key_suffix* keeps the download-tree and ready-panel buttons for the same crawl
    graph distinct, avoiding a duplicate-element-key error when both render.
    """
    return f"explore3d_{session_id}_{key_suffix}_{relative_path}"


def _publish_viewer(file: GeneratedFile, language: str) -> str | None:
    """Publish the crawl's viewer to the static dir; return its URL (or None)."""
    parts = file.relative_path.split("/")
    if len(parts) < 2:
        return None
    session_id = st.session_state.get("session_id", "")
    try:
        target, url = orrery_static_target(_STATIC_ROOT, session_id, parts[0], parts[1], language)
        source_mtime = file.path.stat().st_mtime
    except (OSError, ValueError):
        return None
    if orrery_needs_refresh(target, source_mtime):
        try:
            jsonl_text = file.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        write_orrery_html(target, build_viewer_html(jsonl_text, viewer_labels(language)))
    return url
