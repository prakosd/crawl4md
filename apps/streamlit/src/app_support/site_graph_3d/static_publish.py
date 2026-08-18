"""Publish assembled viewer documents as static files for a refreshable URL.

Streamlit's static file serving (``server.enableStaticServing``) exposes the app's
``static/`` folder at the ``app/static`` URL path. Writing the self-contained viewer
there — instead of handing the browser an ephemeral blob URL — gives each crawl a
real page that survives a refresh or a shared link. Files are namespaced by session
id and pruned when their session is cleaned up.

Pure and Streamlit-free so it stays unit-testable; :mod:`launcher` wires it in.
"""

from __future__ import annotations

import re
import shutil
from collections.abc import Iterable
from pathlib import Path

from artifact_store import ensure_within_root

__all__ = [
    "ORRERY_STATIC_SUBDIR",
    "STATIC_URL_ROOT",
    "orrery_needs_refresh",
    "orrery_static_target",
    "remove_orrery_static",
    "write_orrery_html",
]

ORRERY_STATIC_SUBDIR = "orrery"
STATIC_URL_ROOT = "app/static"  # Streamlit serves ``static/`` here when enabled.
_UNSAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_segment(value: str) -> str:
    """Reduce one path segment to a filesystem- and URL-safe token."""
    return _UNSAFE_SEGMENT.sub("_", value.strip()).strip("._-") or "x"


def orrery_static_target(
    static_root: Path | str,
    session_id: str,
    crawl_folder: str,
    timestamp: str,
    language: str,
) -> tuple[Path, str]:
    """Return the ``(file path, URL)`` for a crawl's published viewer.

    The path is contained within *static_root* (directory-traversal guard) and the
    URL is the ``app/static/...`` path Streamlit serves it at. The language is part
    of the name so switching languages publishes a fresh document.
    """
    session_seg = _safe_segment(session_id)
    name = (
        f"{_safe_segment(crawl_folder)}_{_safe_segment(timestamp)}_{_safe_segment(language)}.html"
    )
    relative = f"{ORRERY_STATIC_SUBDIR}/{session_seg}/{name}"
    root = Path(static_root)
    path = ensure_within_root(root, root / relative)
    return path, f"{STATIC_URL_ROOT}/{relative}"


def orrery_needs_refresh(target: Path, source_mtime: float) -> bool:
    """Return True when *target* is missing or older than the source graph."""
    try:
        return target.stat().st_mtime < source_mtime
    except OSError:
        return True


def write_orrery_html(target: Path, html: str) -> None:
    """Write the assembled viewer *html* to *target*, creating parents as needed."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")


def remove_orrery_static(static_root: Path | str, session_ids: Iterable[str]) -> list[Path]:
    """Delete the published orrery folders for *session_ids*; return what was removed."""
    orrery_root = Path(static_root) / ORRERY_STATIC_SUBDIR
    removed: list[Path] = []
    for session_id in session_ids:
        folder = orrery_root / _safe_segment(session_id)
        if folder.is_dir():
            shutil.rmtree(folder)
            removed.append(folder)
    return removed
