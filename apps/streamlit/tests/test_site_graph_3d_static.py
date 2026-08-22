"""Unit tests for the static publishing of 3D site-graph viewers."""

from __future__ import annotations

from pathlib import Path

from app_support.site_graph_3d.static_publish import (
    orrery_needs_refresh,
    orrery_static_target,
    remove_orrery_static,
    write_orrery_html,
)


# Risk: the published URL must match the ``app/static`` path Streamlit serves and
# the file must land inside the static root. Verify both. Type: unit.
def test_orrery_static_target_builds_url_and_contained_path(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    target, url = orrery_static_target(
        static_root, "sess1", "crawl_01_rumbling", "2026-07-12_04-21-46", "EN"
    )
    assert url == "app/static/orrery/sess1/crawl_01_rumbling_2026-07-12_04-21-46_EN.html"
    assert (
        target == static_root / "orrery" / "sess1" / "crawl_01_rumbling_2026-07-12_04-21-46_EN.html"
    )
    assert static_root.resolve() in target.parents


# Risk: a hostile session id or crawl name could try to escape the static root via
# ``../``. Verify the segments are sanitized so the path stays contained. Type: unit.
def test_orrery_static_target_sanitizes_traversal(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    target, url = orrery_static_target(static_root, "../../etc", "crawl/../x", "2026", "EN")
    assert ".." not in target.parts
    assert static_root.resolve() in target.parents
    assert url.startswith("app/static/orrery/")


# Risk: a stale or missing published file must trigger a rebuild; a fresh one must
# not. Verify the freshness comparison against the source graph mtime. Type: unit.
def test_orrery_needs_refresh_tracks_source_mtime(tmp_path: Path) -> None:
    target = tmp_path / "orrery" / "s" / "v.html"
    assert orrery_needs_refresh(target, 1000.0, code_mtime=0.0) is True  # missing
    write_orrery_html(target, "<html></html>")
    mtime = target.stat().st_mtime
    assert orrery_needs_refresh(target, mtime + 5, code_mtime=0.0) is True  # source newer
    assert orrery_needs_refresh(target, mtime - 5, code_mtime=0.0) is False  # already fresh


# Risk: a layout/viewer code change must rebuild every published orrery even when
# the crawl data is unchanged, else users keep seeing the old layout. Type: unit.
def test_orrery_needs_refresh_rebuilds_when_viewer_code_is_newer(tmp_path: Path) -> None:
    target = tmp_path / "orrery" / "s" / "v.html"
    write_orrery_html(target, "<html></html>")
    mtime = target.stat().st_mtime
    assert orrery_needs_refresh(target, mtime - 5, code_mtime=mtime + 5) is True  # code newer
    assert orrery_needs_refresh(target, mtime - 5, code_mtime=mtime - 5) is False  # all older


# Risk: publishing must create the nested session folder and write the document.
# Verify parents are created and the content lands. Type: unit.
def test_write_orrery_html_creates_parents(tmp_path: Path) -> None:
    target = tmp_path / "static" / "orrery" / "sess1" / "v.html"
    write_orrery_html(target, "<html>hi</html>")
    assert target.read_text(encoding="utf-8") == "<html>hi</html>"


# Risk: cleanup must remove only the named sessions' folders and tolerate absent
# ones, so retention pruning cannot delete a live session's viewers. Type: unit.
def test_remove_orrery_static_removes_named_sessions_only(tmp_path: Path) -> None:
    static_root = tmp_path / "static"
    orrery = static_root / "orrery"
    (orrery / "gone").mkdir(parents=True)
    (orrery / "keep").mkdir(parents=True)
    removed = remove_orrery_static(static_root, ["gone", "never-existed"])
    assert removed == [orrery / "gone"]
    assert not (orrery / "gone").exists()
    assert (orrery / "keep").exists()


# Risk: the same crawl graph backs Explore-in-3D in both the ready-result panel and
# the download tree within one run; identical component keys would raise a
# duplicate-element-key error. Verify the key suffix disambiguates them. Type: unit.
def test_explore_3d_key_distinguishes_ready_and_tree() -> None:
    from app_support.site_graph_3d.launcher import _explore_3d_key

    relative = "crawl_01/2026-05-17_10-00-00/logs/site_graph.jsonl"
    assert _explore_3d_key("s1", "ready", relative) != _explore_3d_key("s1", "tree", relative)
