"""Tests for the semantic search page's pure replay/summary helpers."""

from __future__ import annotations

import importlib
from dataclasses import asdict
from pathlib import Path

from pytest import MonkeyPatch

from app_support.i18n import STRINGS_EN
from app_support.semantic_search.search_history import SearchRecord

_APP_DIR = Path(__file__).resolve().parents[1]


def _page(monkeypatch: MonkeyPatch):
    monkeypatch.syspath_prepend(str(_APP_DIR))
    return importlib.import_module("app_pages.semantic_search")


def _record(**overrides: object) -> SearchRecord:
    values: dict[str, object] = {
        "timestamp_utc": "2026-07-01T10:00:00+00:00",
        "index_folder": "vector_01_weather",
        "index_run": "2026-07-01_09-00-00",
        "embedding_model": "titan",
        "query": "rain today",
        "top_k": 7,
        "result_count": 4,
        "top_score": 0.9,
    }
    values.update(overrides)
    return SearchRecord(**values)  # type: ignore[arg-type]


def test_config_from_record_uses_top_k(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    config = page._config_from_record(asdict(_record()))

    assert config.top_k == 7


def test_index_detail_rows_enrich_from_manifest(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    from vector_indexer import IndexManifest

    from app_support.rag_shared.index_catalog import IndexRef

    manifest = IndexManifest(
        embedding_model_requested="amazon.titan-embed-text-v2:0",
        embedding_model_used="amazon.titan-embed-text-v2:0",
        embedding_dimension=512,
        collection_name="c",
        chunk_size=600,
        chunk_overlap=100,
        language="English",
        success=True,
        indexed_file_count=3,
        indexed_chunk_count=1197,
        skipped_file_count=0,
    )
    ref = IndexRef(
        run_dir=Path("idx"),
        vector_folder="vector_01_x",
        run_name="2026-07-01_09-00-00",
        manifest=manifest,
    )

    rows = dict(page._index_detail_rows(STRINGS_EN, _record(), ref))

    assert rows[STRINGS_EN["SEARCH_META_MODEL"]] == "amazon.titan-embed-text-v2:0"
    assert rows[STRINGS_EN["SEARCH_META_LANGUAGE"]] == "English"
    assert rows[STRINGS_EN["SEARCH_META_DIMENSION_CHUNKS"]] == "512 / 1197"
    assert rows[STRINGS_EN["SEARCH_META_CHUNK_SIZE_OVERLAP"]] == "600 / 100"


def test_search_history_grid_includes_query_facts(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    grid = page._search_history_grid(STRINGS_EN, _record(), None)

    assert STRINGS_EN["SEARCH_META_MODEL"] in grid
    assert "vector_01_weather" in grid
    assert "2026-07-01_09-00-00" in grid
    assert STRINGS_EN["SEARCH_HISTORY_LABEL_RESULTS_TIME"] in grid
    assert "4 / " in grid  # result count paired with the search time
    assert "titan" in grid


def test_search_history_grid_shows_search_time(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    grid = page._search_history_grid(STRINGS_EN, _record(search_seconds=0.34), None)

    assert "4 / 0.3s" in grid


def test_index_detail_rows_fall_back_when_index_gone(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    rows = dict(page._index_detail_rows(STRINGS_EN, _record(embedding_model="titan-x"), None))

    assert rows[STRINGS_EN["SEARCH_META_MODEL"]] == "titan-x"
    assert rows[STRINGS_EN["SEARCH_META_DIMENSION_CHUNKS"]] == "— / —"


def test_replay_prefills_query_and_reruns_without_warnings(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(_APP_DIR))

    def render(session_dir: str) -> None:
        from pathlib import Path as _Path
        from types import SimpleNamespace
        from unittest.mock import patch

        import app_pages.semantic_search as page
        from vector_indexer import IndexManifest

        from app_support.rag_shared.index_catalog import IndexRef
        from app_support.rag_shared.rag_ui import RagPageContext

        root = _Path(session_dir)
        manifest = IndexManifest(
            embedding_model_requested="titan",
            embedding_model_used="titan",
            embedding_dimension=512,
            collection_name="c",
            chunk_size=600,
            chunk_overlap=100,
            language="english",
            success=True,
            indexed_file_count=1,
            indexed_chunk_count=3,
            skipped_file_count=0,
            indexed_sources=("a.md",),
        )
        ref = IndexRef(
            run_dir=root / "idx",
            vector_folder="vector_01_x",
            run_name="2026-07-01_09-00-00",
            manifest=manifest,
        )
        context = RagPageContext(
            default_language="EN",
            list_indexes=lambda: [ref],
            render_downloads=lambda: None,
            session_root=lambda: root,
        )
        empty = SimpleNamespace(chunks=[], warnings=[], errors=[])
        with patch.object(page, "retrieve", return_value=empty):
            page.render_page(context)

    app = AppTest.from_function(render, kwargs={"session_dir": str(tmp_path)})
    app.run(timeout=10)
    assert not app.exception

    app.session_state["semantic_search_replay"] = asdict(_record(query="rerun me"))
    app.run(timeout=10)

    assert not app.exception
    # The magnifier replay re-fills the query widget across the rerun and re-runs
    # the search (retrieve is mocked); the setdefault pattern keeps the keyed
    # widgets from tripping Streamlit's default-value-plus-Session-State warning.
    assert app.session_state["semantic_search_query"] == "rerun me"


def _render_index_page(session_dir: str, n_chunks: int = 0) -> None:
    """Self-contained page render for AppTest with one available index.

    Kept fully self-contained (all imports local) because AppTest.from_function
    runs the source in an isolated namespace where module globals are absent.
    """
    from pathlib import Path as _Path
    from types import SimpleNamespace
    from unittest.mock import patch

    import app_pages.semantic_search as page
    from rag_engine import RetrievedChunk
    from vector_indexer import IndexManifest

    from app_support.rag_shared.index_catalog import IndexRef
    from app_support.rag_shared.rag_ui import RagPageContext

    root = _Path(session_dir)
    manifest = IndexManifest(
        embedding_model_requested="titan",
        embedding_model_used="titan",
        embedding_dimension=512,
        collection_name="c",
        chunk_size=600,
        chunk_overlap=100,
        language="english",
        success=True,
        indexed_file_count=1,
        indexed_chunk_count=3,
        skipped_file_count=0,
        indexed_sources=("a.md",),
    )
    ref = IndexRef(
        run_dir=root / "idx",
        vector_folder="vector_01_x",
        run_name="2026-07-01_09-00-00",
        manifest=manifest,
    )
    context = RagPageContext(
        default_language="EN",
        list_indexes=lambda: [ref],
        render_downloads=lambda: None,
        session_root=lambda: root,
    )
    chunks = [
        RetrievedChunk(text=f"hit {i}", source="a.md", score=0.9, metadata={"chunk_index": i})
        for i in range(n_chunks)
    ]
    result = SimpleNamespace(chunks=chunks, warnings=[], errors=[])
    with patch.object(page, "retrieve", return_value=result):
        page.render_page(context)


def test_replay_restores_matching_index_selection(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(_APP_DIR))

    app = AppTest.from_function(_render_index_page, kwargs={"session_dir": str(tmp_path)})
    app.run(timeout=10)
    assert not app.exception

    app.session_state["semantic_search_replay"] = asdict(
        _record(index_folder="vector_01_x", index_run="2026-07-01_09-00-00")
    )
    app.run(timeout=10)

    assert not app.exception
    # Replaying a history row switches the Vector DB picker to the recorded index.
    assert app.session_state["semantic_search_index"].startswith(
        "vector_01_x / 2026-07-01_09-00-00"
    )


def test_search_results_persist_across_reruns(monkeypatch: MonkeyPatch, tmp_path: Path) -> None:
    from streamlit.testing.v1 import AppTest

    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(_APP_DIR))

    app = AppTest.from_function(
        _render_index_page, kwargs={"session_dir": str(tmp_path), "n_chunks": 2}
    )
    app.run(timeout=10)
    assert not app.exception

    app.session_state["semantic_search_replay"] = asdict(
        _record(index_folder="vector_01_x", index_run="2026-07-01_09-00-00")
    )
    app.run(timeout=10)
    assert not app.exception
    assert len(app.session_state["semantic_search_results"]) == 2

    # A later rerun without a new search keeps the persisted results panel data.
    app.run(timeout=10)
    assert not app.exception
    assert len(app.session_state["semantic_search_results"]) == 2
