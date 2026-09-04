from __future__ import annotations

from app_support.conversational_rag.conversational_rag_form_ui import (
    ConversationalControls,
    aux_model_choices,
    build_conversational_config,
)


def _controls(**overrides) -> ConversationalControls:
    values = dict(
        index=None,
        answer_model="gpt-4o",
        top_k=6,
        tone="Formal",
        reranker="llm",
        aux_model_id="echo",
        decomposition=False,
        followups=True,
        inspect=True,
        followup_drop=0.3,
        followup_keep=0.7,
    )
    values.update(overrides)
    return ConversationalControls(**values)


def test_build_config_maps_controls() -> None:
    config = build_conversational_config(_controls())

    assert config.rag.llm_model == "gpt-4o"
    assert config.rag.top_k == 6
    assert config.reranker == "llm"
    assert config.aux_model_id == "echo"
    assert config.plan_enabled is False
    assert config.followups_enabled is True
    assert config.followup_drop_score == 0.3
    assert config.followup_min_score == 0.7
    assert config.tone == "Formal"


def test_build_config_blank_aux_becomes_none() -> None:
    config = build_conversational_config(_controls(aux_model_id=""))

    assert config.aux_model_id is None


def test_aux_model_choices_has_valid_default() -> None:
    options, default_index = aux_model_choices()

    assert options
    assert 0 <= default_index < len(options)
