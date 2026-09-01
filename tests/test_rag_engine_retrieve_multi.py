from __future__ import annotations

from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.messages import CODE_INDEX_NOT_FOUND, CODE_RETRIEVAL_PARTIAL_FAILURE
from rag_engine.models import RetrievedChunk
from rag_engine.retrieval import RetrievalResult, chunk_identity, retrieve_multi


def _chunk(text: str, source: str = "a.md", score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(text=text, source=source, score=score, metadata={})


def test_single_question_short_circuits() -> None:
    calls: list[str] = []

    def retriever(run_dir, query, config):
        calls.append(query)
        return RetrievalResult(chunks=[_chunk("x")])

    result = retrieve_multi("/tmp", ["only one"], RagConfig(), retriever=retriever)

    assert calls == ["only one"]
    assert [chunk.text for chunk in result.chunks] == ["x"]


def test_merges_and_dedupes_by_identity() -> None:
    shared = _chunk("shared", score=0.7)

    def retriever(run_dir, query, config):
        if query == "q1":
            return RetrievalResult(chunks=[shared, _chunk("only1", score=0.6)])
        return RetrievalResult(chunks=[shared, _chunk("only2", score=0.9)])

    result = retrieve_multi("/tmp", ["q1", "q2"], RagConfig(), retriever=retriever)

    # Deduped (shared appears once) and sorted by score descending.
    assert [chunk.text for chunk in result.chunks] == ["only2", "shared", "only1"]
    shared_chunk = next(chunk for chunk in result.chunks if chunk.text == "shared")
    assert set(shared_chunk.matched_queries) == {"q1", "q2"}
    only1 = next(chunk for chunk in result.chunks if chunk.text == "only1")
    assert only1.matched_queries == ("q1",)


def test_partial_failure_keeps_other_results() -> None:
    def retriever(run_dir, query, config):
        if query == "bad":
            return RetrievalResult(errors=[messages.index_not_found("/tmp")])
        return RetrievalResult(chunks=[_chunk("good")])

    result = retrieve_multi("/tmp", ["good_q", "bad"], RagConfig(), retriever=retriever)

    assert [chunk.text for chunk in result.chunks] == ["good"]
    assert any(w.code == CODE_RETRIEVAL_PARTIAL_FAILURE for w in result.warnings)
    assert result.errors == []


def test_all_failures_surface_errors() -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(errors=[messages.index_not_found("/tmp")])

    result = retrieve_multi("/tmp", ["q1", "q2"], RagConfig(), retriever=retriever)

    assert result.chunks == []
    assert any(e.code == CODE_INDEX_NOT_FOUND for e in result.errors)


def test_empty_sub_questions_returns_empty() -> None:
    def retriever(run_dir, query, config):  # pragma: no cover - must not run
        raise AssertionError("should not retrieve")

    result = retrieve_multi("/tmp", ["  ", ""], RagConfig(), retriever=retriever)

    assert result.chunks == []


def test_chunk_identity_differs_by_source_and_text() -> None:
    assert chunk_identity(_chunk("same", source="a.md")) != chunk_identity(
        _chunk("same", source="b.md")
    )
    assert chunk_identity(_chunk("same", source="a.md")) != chunk_identity(
        _chunk("other", source="a.md")
    )
