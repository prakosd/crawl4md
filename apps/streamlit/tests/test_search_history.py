"""Tests for the per-session semantic-search history log."""

from __future__ import annotations

import csv
from pathlib import Path

from app_support.rag_shared.result_snapshot import StoredResult
from app_support.semantic_search.search_history import (
    SEARCH_HISTORY_DIRNAME,
    SearchRecord,
    append_search_record,
    load_search_history,
    search_history_dir,
    set_search_pinned,
)


def _record(query: str, **overrides: object) -> SearchRecord:
    values: dict[str, object] = {
        "timestamp_utc": "2026-07-01T10:00:00+00:00",
        "index_folder": "vector_01_weather",
        "index_run": "2026-07-01_09-00-00",
        "embedding_model": "amazon.titan-embed-text-v2:0",
        "query": query,
        "top_k": 5,
        "result_count": 3,
        "top_score": 0.8123,
    }
    values.update(overrides)
    return SearchRecord(**values)  # type: ignore[arg-type]


def test_load_history_empty_when_missing(tmp_path: Path) -> None:
    assert load_search_history(tmp_path) == []


def test_search_history_dir_uses_search_prefix(tmp_path: Path) -> None:
    assert search_history_dir(tmp_path) == tmp_path / SEARCH_HISTORY_DIRNAME
    assert SEARCH_HISTORY_DIRNAME.startswith("search_")


def test_append_then_load_is_newest_first(tmp_path: Path) -> None:
    append_search_record(tmp_path, _record("first"))
    append_search_record(tmp_path, _record("second"))

    history = load_search_history(tmp_path)

    assert [record.query for record in history] == ["second", "first"]


def test_record_round_trips_all_fields(tmp_path: Path) -> None:
    original = _record("weather today")
    append_search_record(tmp_path, original)

    (loaded,) = load_search_history(tmp_path)

    assert loaded == original
    assert loaded.top_score == 0.8123


def test_record_round_trips_search_time_and_results(tmp_path: Path) -> None:
    results = (
        StoredResult(source="a.md", score=0.91, text="hello", metadata={"chunk_index": "0"}),
        StoredResult(source="b.md", score=0.42, text="world", metadata={"language": "english"}),
    )
    original = _record("felix", search_seconds=0.73, results=results)
    append_search_record(tmp_path, original)

    (loaded,) = load_search_history(tmp_path)

    assert loaded == original
    assert loaded.search_seconds == 0.73
    assert loaded.results == results
    assert loaded.results[0].metadata == {"chunk_index": "0"}


def test_history_is_capped_to_recent_records(tmp_path: Path) -> None:
    for index in range(230):
        append_search_record(tmp_path, _record(f"q{index}"))

    history = load_search_history(tmp_path)

    assert len(history) == 200
    # Newest-first: the most recent query is q229; the oldest kept is q30.
    assert history[0].query == "q229"
    assert history[-1].query == "q30"


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    append_search_record(tmp_path, _record("valid"))
    history_file = search_history_dir(tmp_path) / "search_history.jsonl"
    history_file.write_text(
        history_file.read_text(encoding="utf-8") + "not json\n", encoding="utf-8"
    )

    history = load_search_history(tmp_path)

    assert [record.query for record in history] == ["valid"]


def test_csv_companion_has_header_and_rows(tmp_path: Path) -> None:
    append_search_record(tmp_path, _record("alpha", search_seconds=0.5))
    append_search_record(tmp_path, _record("beta", top_score=None))

    csv_path = search_history_dir(tmp_path) / "search_history.csv"
    rows = list(csv.DictReader(csv_path.read_text(encoding="utf-8").splitlines()))

    assert [row["query"] for row in rows] == ["alpha", "beta"]
    assert rows[0]["top_score"] == "0.8123"
    assert rows[1]["top_score"] == ""
    assert rows[0]["search_seconds"] == "0.50"
    assert rows[1]["search_seconds"] == ""


def test_pinned_records_sort_first(tmp_path: Path) -> None:
    append_search_record(tmp_path, _record("a", timestamp_utc="2026-07-01T10:00:00+00:00"))
    append_search_record(tmp_path, _record("b", timestamp_utc="2026-07-01T10:00:01+00:00"))
    append_search_record(tmp_path, _record("c", timestamp_utc="2026-07-01T10:00:02+00:00"))

    set_search_pinned(tmp_path, "2026-07-01T10:00:00+00:00", True)

    history = load_search_history(tmp_path)
    assert history[0].query == "a"
    assert history[0].pinned is True
    assert [record.query for record in history[1:]] == ["c", "b"]


def test_unpin_restores_newest_first_order(tmp_path: Path) -> None:
    append_search_record(tmp_path, _record("a", timestamp_utc="2026-07-01T10:00:00+00:00"))
    append_search_record(tmp_path, _record("b", timestamp_utc="2026-07-01T10:00:01+00:00"))
    set_search_pinned(tmp_path, "2026-07-01T10:00:00+00:00", True)
    set_search_pinned(tmp_path, "2026-07-01T10:00:00+00:00", False)

    assert [record.query for record in load_search_history(tmp_path)] == ["b", "a"]
