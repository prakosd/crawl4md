from __future__ import annotations

from langchain_core.language_models import SimpleChatModel

from rag_engine.catalog import ECHO_MODEL
from rag_engine.config import ConversationalConfig
from rag_engine.decompose import looks_multi_part, plan_queries, update_state
from rag_engine.models import ConversationState


class _ScriptedModel(SimpleChatModel):
    reply: str = ""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
        return self.reply


class _BoomModel(SimpleChatModel):
    @property
    def _llm_type(self) -> str:
        return "boom"

    def _call(self, messages, stop=None, run_manager=None, **kwargs) -> str:
        raise RuntimeError("boom")


_STATE = ConversationState()


def test_looks_multi_part_detects_signals() -> None:
    assert looks_multi_part("What is X? And what about Y?") is True
    assert looks_multi_part("Tell me about pricing, also the tiers") is True
    assert looks_multi_part("what about the enterprise one?") is True
    assert looks_multi_part("What is X and how do I set up Y?") is True


def test_looks_multi_part_single_question_is_false() -> None:
    assert looks_multi_part("What is the capital of France?") is False


def test_plan_queries_offline_is_degraded() -> None:
    plan = plan_queries(_BoomModel(), _STATE, "hi", ConversationalConfig(), model_id=ECHO_MODEL)

    assert plan.sub_questions == ["hi"]
    assert plan.degraded is True
    assert any(w.code == "rag.chat.plan_skipped_offline" for w in plan.warnings)


def test_plan_queries_disabled_is_degraded_without_warning() -> None:
    config = ConversationalConfig(plan_enabled=False)
    plan = plan_queries(_BoomModel(), _STATE, "a and b?", config, model_id="aux")

    assert plan.sub_questions == ["a and b?"]
    assert plan.degraded is True
    assert plan.warnings == []


def test_plan_queries_short_circuits_single_question() -> None:
    # A single question with empty state must not call the model (BoomModel would raise).
    plan = plan_queries(_BoomModel(), _STATE, "What is X?", ConversationalConfig(), model_id="aux")

    assert plan.sub_questions == ["What is X?"]
    assert plan.degraded is False


def test_plan_queries_splits_multi_part() -> None:
    model = _ScriptedModel(reply='["capital of France", "population of France"]')
    plan = plan_queries(
        model, _STATE, "capital and population?", ConversationalConfig(), model_id="aux"
    )

    assert plan.sub_questions == ["capital of France", "population of France"]
    assert plan.degraded is False


def test_plan_queries_caps_and_dedupes() -> None:
    model = _ScriptedModel(reply='["a", "A", "b", "c", "d", "e"]')
    config = ConversationalConfig(plan_max_subquestions=3)
    plan = plan_queries(model, _STATE, "a and b and c and d?", config, model_id="aux")

    assert plan.sub_questions == ["a", "b", "c"]


def test_plan_queries_unparsable_is_degraded() -> None:
    model = _ScriptedModel(reply="I cannot help with that")
    plan = plan_queries(model, _STATE, "a and b?", ConversationalConfig(), model_id="aux")

    assert plan.sub_questions == ["a and b?"]
    assert plan.degraded is True
    assert any(w.code == "rag.chat.plan_unparsable" for w in plan.warnings)


def test_plan_queries_model_error_is_degraded() -> None:
    plan = plan_queries(_BoomModel(), _STATE, "a and b?", ConversationalConfig(), model_id="aux")

    assert plan.sub_questions == ["a and b?"]
    assert plan.degraded is True
    assert any(w.code == "rag.chat.plan_unparsable" for w in plan.warnings)


def test_update_state_offline_appends_recent_without_summary() -> None:
    state = ConversationState(summary="prior")
    result = update_state(
        _BoomModel(),
        state,
        "resolved q",
        "answer",
        ConversationalConfig(),
        model_id=ECHO_MODEL,
        turn_index=10,
    )

    assert result.recent_resolved == ("resolved q",)
    assert result.summary == "prior"  # not summarized offline


def test_update_state_early_turn_skips_summary() -> None:
    config = ConversationalConfig(state_summary_start_turn=4)
    result = update_state(
        _BoomModel(), ConversationState(), "q", "a", config, model_id="aux", turn_index=0
    )

    assert result.recent_resolved == ("q",)


def test_update_state_summarizes_later_turn() -> None:
    model = _ScriptedModel(
        reply='{"summary": "France discussed", "entities": {"country": "France"}, '
        '"open_threads": ["population?"]}'
    )
    config = ConversationalConfig(state_summary_start_turn=2)
    result = update_state(
        model,
        ConversationState(),
        "capital of France",
        "Paris",
        config,
        model_id="aux",
        turn_index=5,
    )

    assert result.summary == "France discussed"
    assert result.entities == {"country": "France"}
    assert result.open_threads == ("population?",)
    assert result.recent_resolved == ("capital of France",)


def test_update_state_parse_failure_preserves_prior() -> None:
    state = ConversationState(summary="prior", entities={"a": "b"})
    config = ConversationalConfig(state_summary_start_turn=2)
    result = update_state(
        _ScriptedModel(reply="not json"), state, "q", "a", config, model_id="aux", turn_index=5
    )

    assert result.summary == "prior"
    assert result.entities == {"a": "b"}
    assert result.recent_resolved == ("q",)


def test_update_state_caps_summary_words() -> None:
    long_summary = " ".join(["word"] * 300)
    model = _ScriptedModel(reply='{"summary": "' + long_summary + '"}')
    config = ConversationalConfig(state_summary_start_turn=1, state_summary_max_words=10)
    result = update_state(
        model, ConversationState(), "q", "a", config, model_id="aux", turn_index=5
    )

    assert len(result.summary.split()) == 10


def test_update_state_recent_window_capped() -> None:
    config = ConversationalConfig(plan_recent_turns=2)
    state = ConversationState(recent_resolved=("q1", "q2"))
    result = update_state(_BoomModel(), state, "q3", "a", config, model_id=ECHO_MODEL, turn_index=0)

    assert result.recent_resolved == ("q2", "q3")
