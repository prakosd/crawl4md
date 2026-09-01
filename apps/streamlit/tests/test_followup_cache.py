from __future__ import annotations

from rag_engine import RetrievedChunk, ValidatedFollowup

from app_support.conversational_rag.followup_cache import get_cached_chunks, replace_followups


def _chunk(text: str) -> RetrievedChunk:
    return RetrievedChunk(text=text, source="a.md", score=0.9, metadata={})


def test_replace_and_get_hit() -> None:
    cache: dict = {}
    replace_followups(cache, [ValidatedFollowup(question="Q1", chunks=[_chunk("c1")])])

    hit = get_cached_chunks(cache, "Q1")

    assert hit is not None
    assert [chunk.text for chunk in hit] == ["c1"]


def test_get_miss_on_variant_text() -> None:
    cache: dict = {}
    replace_followups(cache, [ValidatedFollowup(question="Q1", chunks=[_chunk("c1")])])

    assert get_cached_chunks(cache, "q1") is None  # exact match only


def test_replace_is_wholesale() -> None:
    cache: dict = {}
    replace_followups(cache, [ValidatedFollowup(question="Q1", chunks=[_chunk("c1")])])
    replace_followups(cache, [ValidatedFollowup(question="Q2", chunks=[_chunk("c2")])])

    assert get_cached_chunks(cache, "Q1") is None
    assert get_cached_chunks(cache, "Q2") is not None


def test_get_returns_copy() -> None:
    cache: dict = {}
    replace_followups(cache, [ValidatedFollowup(question="Q1", chunks=[_chunk("c1")])])

    hit = get_cached_chunks(cache, "Q1")
    assert hit is not None
    hit.append(_chunk("mutated"))

    assert len(get_cached_chunks(cache, "Q1")) == 1  # cache unaffected
