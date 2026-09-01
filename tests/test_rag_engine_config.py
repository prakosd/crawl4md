from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag_engine.catalog import DEFAULT_CHAT_MODEL
from rag_engine.config import ConversationalConfig, RagConfig


def test_defaults_are_valid() -> None:
    config = RagConfig()

    assert config.llm_model == DEFAULT_CHAT_MODEL
    assert config.top_k >= 1
    assert config.max_tokens >= 1
    assert 0.0 <= config.temperature <= 2.0
    assert config.score_threshold == 0.0
    assert config.search_type == "similarity"
    assert config.fetch_k >= 1
    assert 0.0 <= config.lambda_mult <= 1.0
    assert config.source_filter == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"temperature": -0.1},
        {"temperature": 2.1},
        {"top_k": 0},
        {"max_tokens": 0},
        {"score_threshold": -0.1},
        {"score_threshold": 1.1},
        {"lambda_mult": -0.1},
        {"lambda_mult": 1.1},
        {"fetch_k": 0},
        {"search_type": "bogus"},
    ],
)
def test_invalid_values_are_rejected(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        RagConfig(**overrides)


def test_accepts_custom_values() -> None:
    config = RagConfig(llm_model="gpt-4o", temperature=0.7, max_tokens=256, top_k=6)

    assert config.llm_model == "gpt-4o"
    assert config.temperature == 0.7
    assert config.max_tokens == 256
    assert config.top_k == 6


def test_accepts_custom_retrieval_values() -> None:
    config = RagConfig(
        score_threshold=0.25,
        search_type="mmr",
        fetch_k=30,
        lambda_mult=0.7,
        source_filter=["a.md", "b.md"],
    )

    assert config.score_threshold == 0.25
    assert config.search_type == "mmr"
    assert config.fetch_k == 30
    assert config.lambda_mult == 0.7
    assert config.source_filter == ("a.md", "b.md")


def test_conversational_config_defaults() -> None:
    config = ConversationalConfig()

    assert isinstance(config.rag, RagConfig)
    assert config.aux_model_id is None
    assert config.plan_enabled is True
    assert config.reranker == "local"
    assert config.rerank_top_n >= 1
    assert config.followups_enabled is True
    assert config.followup_drop_score <= config.followup_min_score
    assert config.max_workers >= 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"reranker": "bogus"},
        {"followup_min_score": 1.1},
        {"followup_drop_score": -0.1},
        {"followup_drop_score": 0.8, "followup_min_score": 0.5},  # drop > min
        {"plan_max_subquestions": 0},
        {"rerank_top_n": 0},
        {"followup_candidate_count": 0},
        {"max_workers": 0},
        {"plan_recent_turns": -1},
    ],
)
def test_conversational_config_rejects_invalid(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        ConversationalConfig(**overrides)


def test_conversational_config_accepts_custom_values() -> None:
    config = ConversationalConfig(
        rag=RagConfig(top_k=8),
        aux_model_id="echo",
        reranker="llm",
        followup_min_score=0.7,
        followup_drop_score=0.3,
    )

    assert config.rag.top_k == 8
    assert config.aux_model_id == "echo"
    assert config.reranker == "llm"
    assert config.followup_min_score == 0.7
