from __future__ import annotations

from langchain_core.language_models import SimpleChatModel

from rag_engine.config import ConversationalConfig
from rag_engine.followups import answerability_check, suggest_followups, validate_followups
from rag_engine.models import QueryPlan, RetrievedChunk
from rag_engine.retrieval import RetrievalResult


class _ScriptedModel(SimpleChatModel):
    reply: str = ""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
        return self.reply


def _chunk(text: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(text=text, source="a.md", score=score, metadata={})


def test_suggest_followups_disabled_returns_empty() -> None:
    model = _ScriptedModel(reply='["q1"]')
    result = suggest_followups(
        model, [_chunk("t", 0.9)], QueryPlan(), ConversationalConfig(followups_enabled=False)
    )
    assert result == []


def test_suggest_followups_no_chunks_returns_empty() -> None:
    result = suggest_followups(
        _ScriptedModel(reply='["q1"]'), [], QueryPlan(), ConversationalConfig()
    )
    assert result == []


def test_suggest_followups_parses_candidates() -> None:
    model = _ScriptedModel(reply='["What is X?", "How about Y?"]')
    result = suggest_followups(
        model, [_chunk("t", 0.9)], QueryPlan(sub_questions=["orig"]), ConversationalConfig()
    )
    assert result == ["What is X?", "How about Y?"]


def test_answerability_check_reads_yes_no() -> None:
    yes = answerability_check(_ScriptedModel(reply="YES, definitely"), "q", [_chunk("t", 0.9)], 2)
    no = answerability_check(_ScriptedModel(reply="NO"), "q", [_chunk("t", 0.9)], 2)
    assert yes is True
    assert no is False


def test_validate_followups_keeps_high_score() -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=[_chunk("c", 0.9)])

    result = validate_followups("/tmp", ["good"], ConversationalConfig(), retriever=retriever)

    assert [f.question for f in result] == ["good"]
    assert result[0].chunks[0].score == 0.9
    assert result[0].checked_by_llm is False


def test_validate_followups_drops_low_score() -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=[_chunk("c", 0.1)])

    assert validate_followups("/tmp", ["bad"], ConversationalConfig(), retriever=retriever) == []


def test_validate_followups_borderline_kept_by_llm() -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=[_chunk("c", 0.5)])

    result = validate_followups(
        "/tmp",
        ["maybe"],
        ConversationalConfig(),
        model=_ScriptedModel(reply="YES"),
        retriever=retriever,
    )

    assert [f.question for f in result] == ["maybe"]
    assert result[0].checked_by_llm is True


def test_validate_followups_borderline_dropped_by_llm() -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=[_chunk("c", 0.5)])

    result = validate_followups(
        "/tmp",
        ["maybe"],
        ConversationalConfig(),
        model=_ScriptedModel(reply="NO"),
        retriever=retriever,
    )

    assert result == []


def test_validate_followups_borderline_without_model_drops() -> None:
    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=[_chunk("c", 0.5)])

    assert validate_followups("/tmp", ["maybe"], ConversationalConfig(), retriever=retriever) == []


def test_validate_followups_empty_candidates() -> None:
    def retriever(run_dir, query, config):  # pragma: no cover - must not retrieve
        raise AssertionError("should not retrieve")

    assert validate_followups("/tmp", ["", "  "], ConversationalConfig(), retriever=retriever) == []


def test_validate_followups_sorts_and_truncates() -> None:
    scores = {"a": 0.7, "b": 0.95, "c": 0.8}

    def retriever(run_dir, query, config):
        return RetrievalResult(chunks=[_chunk("c", scores[query])])

    result = validate_followups(
        "/tmp", ["a", "b", "c"], ConversationalConfig(followup_show_count=2), retriever=retriever
    )

    assert [f.question for f in result] == ["b", "c"]
