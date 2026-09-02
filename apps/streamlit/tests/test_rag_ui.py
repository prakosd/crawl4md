from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rag_engine import RetrievedChunk
from vector_indexer import IndexManifest

from app_support.generated_files import format_local_datetime
from app_support.i18n import STRINGS_EN
from app_support.rag_shared.index_catalog import IndexRef
from app_support.rag_shared.rag_ui import (
    chunks_from_stored,
    find_index,
    format_score_percent,
    history_actions_gap_css,
    index_metadata_rows,
    kv_grid_html,
    local_time_label,
    ordered_result_tabs,
    result_detail_caption,
    result_panel_title,
    sort_results_by_score,
    stacked_label_value_html,
)
from app_support.rag_shared.result_snapshot import stored_results


def _index_ref(folder: str, run: str) -> IndexRef:
    manifest = IndexManifest(
        embedding_model_requested="m",
        embedding_model_used="m",
        embedding_dimension=512,
        collection_name="c",
        chunk_size=600,
        chunk_overlap=100,
        language="English",
        success=True,
        indexed_file_count=1,
        indexed_chunk_count=1,
        skipped_file_count=0,
    )
    return IndexRef(run_dir=Path("idx"), vector_folder=folder, run_name=run, manifest=manifest)


def test_find_index_matches_folder_and_run() -> None:
    ref = _index_ref("vector_1", "2026-07-04_09-00-00")

    assert find_index([ref], "vector_1", "2026-07-04_09-00-00") is ref
    assert find_index([ref], "vector_1", "other") is None
    assert find_index([], "vector_1", "x") is None


def test_local_time_label_passes_through_bad_value() -> None:
    assert local_time_label("not-a-timestamp") == "not-a-timestamp"
    assert local_time_label("2026-07-04T10:00:00+00:00")


def test_local_time_label_abbreviates_month_when_requested() -> None:
    full = local_time_label("2026-07-04T10:00:00+00:00")
    short = local_time_label("2026-07-04T10:00:00+00:00", abbreviate_month=True)

    assert "July" in full
    assert "Jul" in short and "July" not in short  # three-letter month for the txn table


def test_kv_grid_html_escapes_and_right_aligns_values() -> None:
    grid = kv_grid_html([("Model", "a & b"), ("Tone", "Neutral")])

    assert "grid-template-columns:auto 1fr" in grid
    assert "a &amp; b" in grid  # value is html-escaped
    assert "Neutral" in grid
    assert "margin-bottom" not in grid


def test_kv_grid_html_four_column_with_margin() -> None:
    grid = kv_grid_html([("A", "1")], columns=4, margin_bottom=True)

    assert "grid-template-columns:auto 1fr auto 1fr" in grid
    assert "margin-bottom:1rem" in grid


def test_kv_grid_html_margin_top_pulls_grid_up() -> None:
    grid = kv_grid_html([("A", "1")], margin_top=True)

    assert "margin-top:-0.5rem" in grid


def test_stacked_label_value_html_escapes_and_clips() -> None:
    block = stacked_label_value_html("Question", "a & <b>")

    assert "Question" in block
    assert "a &amp; &lt;b&gt;" in block  # value is html-escaped
    assert 'title="a &amp; &lt;b&gt;"' in block  # full text kept for hover
    assert "text-overflow:ellipsis" in block  # clipped to a single line


def test_history_actions_gap_css_scopes_to_key_prefix() -> None:
    css = history_actions_gap_css("search_history_actions_")

    assert "st-key-search_history_actions_" in css
    assert "gap:0.5rem" in css
    assert css.startswith("<style>") and css.endswith("</style>")


def _chunk(score: float) -> RetrievedChunk:
    return RetrievedChunk(text="t", source="s", score=score, metadata={})


def test_format_score_percent_clamps_to_0_100() -> None:
    assert format_score_percent(0.0) == 0
    assert format_score_percent(1.0) == 100
    assert format_score_percent(0.5) == 50
    assert format_score_percent(0.873) == 87
    assert format_score_percent(-0.2) == 0
    assert format_score_percent(1.4) == 100


def test_ordered_result_tabs_defaults_to_raw_first() -> None:
    assert ordered_result_tabs("raw") == ("raw", "preview")
    assert ordered_result_tabs("RAW") == ("raw", "preview")
    assert ordered_result_tabs("unknown") == ("raw", "preview")


def test_ordered_result_tabs_preview_first_when_configured() -> None:
    assert ordered_result_tabs("preview") == ("preview", "raw")
    assert ordered_result_tabs(" Preview ") == ("preview", "raw")


def test_sort_results_by_score_orders_highest_first() -> None:
    ordered = sort_results_by_score([_chunk(0.2), _chunk(0.9), _chunk(0.5)])

    assert [chunk.score for chunk in ordered] == [0.9, 0.5, 0.2]


def test_result_detail_caption_includes_chunk_id_size_and_language() -> None:
    chunk = RetrievedChunk(
        text="hello world",
        source="doc.md",
        score=0.5,
        metadata={"chunk_index": "3", "language": "english"},
    )

    caption = result_detail_caption(STRINGS_EN, chunk)

    assert "Chunk #3" in caption
    assert "doc.md" not in caption  # source lives in the panel title, not the caption
    assert "11 chars" in caption  # len("hello world") == 11
    assert "english" in caption


def test_result_panel_title_includes_rank_source_chunk_and_score() -> None:
    chunk = RetrievedChunk(
        text="hello world",
        source="doc.md",
        score=0.66,
        metadata={"chunk_index": "30", "language": "english"},
    )

    title = result_panel_title(STRINGS_EN, 1, chunk)

    assert "#1" in title
    assert "doc.md#30" in title
    assert "66%" in title


def test_index_metadata_rows_include_key_manifest_fields() -> None:
    manifest = IndexManifest(
        embedding_model_requested="amazon.titan-embed-text-v2:0",
        embedding_model_used="amazon.titan-embed-text-v2:0",
        embedding_dimension=512,
        collection_name="crawl4md_documents",
        chunk_size=600,
        chunk_overlap=100,
        language="english",
        success=True,
        indexed_file_count=3,
        indexed_chunk_count=42,
        skipped_file_count=0,
        created_at="2026-06-22T10:30:00+00:00",
    )

    rows = dict(index_metadata_rows(STRINGS_EN, manifest))

    assert rows[STRINGS_EN["SEARCH_META_MODEL"]] == "amazon.titan-embed-text-v2:0"
    assert rows[STRINGS_EN["SEARCH_META_LANGUAGE"]] == "english"
    assert rows[STRINGS_EN["SEARCH_META_DIMENSION_CHUNKS"]] == "512 / 42"
    assert rows[STRINGS_EN["SEARCH_META_CHUNK_SIZE_OVERLAP"]] == "600 / 100"
    assert rows[STRINGS_EN["SEARCH_META_COLLECTION"]] == "crawl4md_documents"
    expected_created = format_local_datetime(datetime(2026, 6, 22, 10, 30, tzinfo=timezone.utc))
    assert rows[STRINGS_EN["SEARCH_META_CREATED"]] == expected_created


def test_chunks_from_stored_round_trips_retrieved_chunks() -> None:
    stored = stored_results(
        [RetrievedChunk(text="hi", source="a.md", score=0.9, metadata={"chunk_index": "2"})]
    )

    chunks = chunks_from_stored(stored)

    assert len(chunks) == 1
    assert isinstance(chunks[0], RetrievedChunk)
    assert chunks[0].text == "hi"
    assert chunks[0].source == "a.md"
    assert chunks[0].score == 0.9
    assert chunks[0].metadata == {"chunk_index": "2"}
