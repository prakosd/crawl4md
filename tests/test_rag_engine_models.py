from __future__ import annotations

import dataclasses

import pytest

from rag_engine.models import (
    ConversationalAnswer,
    ConversationState,
    QueryPlan,
    RetrievedChunk,
    ValidatedFollowup,
)


def test_retrieved_chunk_matched_queries_defaults_empty() -> None:
    chunk = RetrievedChunk(text="t", source="a.md", score=0.5, metadata={})

    assert chunk.matched_queries == ()


def test_retrieved_chunk_accepts_matched_queries() -> None:
    chunk = RetrievedChunk(
        text="t", source="a.md", score=0.5, metadata={}, matched_queries=("q1", "q2")
    )

    assert chunk.matched_queries == ("q1", "q2")


def test_query_plan_defaults() -> None:
    plan = QueryPlan()

    assert plan.sub_questions == []
    assert plan.degraded is False
    assert plan.warnings == []


def test_conversation_state_defaults_and_is_frozen() -> None:
    state = ConversationState()

    assert state.summary == ""
    assert state.entities == {}
    assert state.recent_resolved == ()
    assert state.open_threads == ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        state.summary = "changed"  # type: ignore[misc]


def test_validated_followup_defaults() -> None:
    followup = ValidatedFollowup(question="What next?")

    assert followup.chunks == []
    assert followup.score == 0.0
    assert followup.verdict == "keep"
    assert followup.checked_by_llm is False


def test_conversational_answer_defaults() -> None:
    answer = ConversationalAnswer(answer="hi")

    assert answer.sources == []
    assert isinstance(answer.plan, QueryPlan)
    assert answer.follow_ups == []
    assert isinstance(answer.state, ConversationState)
    assert answer.model_used is None
    assert answer.aux_model_used is None
    assert answer.reranker_used is None
    assert answer.timings == {}
    assert answer.warnings == []
    assert answer.errors == []
