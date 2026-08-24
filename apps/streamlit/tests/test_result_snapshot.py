"""Tests for the serialisable search-result snapshot helpers."""

from __future__ import annotations

from app_support.rag_shared.result_snapshot import (
    StoredResult,
    stored_results,
    stored_results_from_payload,
)


class _Chunk:
    def __init__(self, source: str, score: float, text: str, metadata: dict[str, str]) -> None:
        self.source = source
        self.score = score
        self.text = text
        self.metadata = metadata


def test_stored_results_copies_chunk_fields() -> None:
    stored = stored_results([_Chunk("a.md", 0.5, "hello", {"chunk_index": "1"})])

    assert stored == (
        StoredResult(source="a.md", score=0.5, text="hello", metadata={"chunk_index": "1"}),
    )


def test_stored_results_from_payload_rebuilds_entries() -> None:
    payload = [
        {"source": "a.md", "score": 0.9, "text": "x", "metadata": {"language": "english"}},
        {"source": "b.md", "score": 0.1, "text": "y", "metadata": {}},
    ]

    stored = stored_results_from_payload(payload)

    assert [item.source for item in stored] == ["a.md", "b.md"]
    assert stored[0].metadata == {"language": "english"}


def test_stored_results_from_payload_skips_bad_entries() -> None:
    payload = ["not a dict", {"source": "ok", "score": 0.2, "text": "t", "metadata": {}}]

    stored = stored_results_from_payload(payload)

    assert [item.source for item in stored] == ["ok"]


def test_stored_results_from_payload_tolerates_non_list() -> None:
    assert stored_results_from_payload(None) == ()
    assert stored_results_from_payload("nope") == ()
