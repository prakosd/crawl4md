"""Configuration model for a retrieval-augmented generation request.

``RagConfig`` captures the user-tunable knobs for answering a question over an
index: which chat model to use, how many chunks to retrieve, and the generation
parameters. It is UI-independent and validated with Pydantic v2.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from rag_engine.catalog import DEFAULT_CHAT_MODEL

__all__ = ["ConversationalConfig", "RagConfig"]

_DEFAULT_TEMPERATURE = 0.0
_MAX_TEMPERATURE = 2.0
_DEFAULT_MAX_TOKENS = 1024
_DEFAULT_TOP_K = 4
_DEFAULT_SCORE_THRESHOLD = 0.0
_DEFAULT_FETCH_K = 20
_DEFAULT_LAMBDA_MULT = 0.5


class RagConfig(BaseModel):
    """User-supplied parameters that control retrieval and generation."""

    llm_model: str = DEFAULT_CHAT_MODEL
    temperature: float = _DEFAULT_TEMPERATURE
    max_tokens: int = _DEFAULT_MAX_TOKENS
    top_k: int = _DEFAULT_TOP_K
    # Minimum 0-1 similarity a chunk must reach to be returned (0 = keep all).
    score_threshold: float = _DEFAULT_SCORE_THRESHOLD
    # "similarity" (plain nearest-neighbour) or "mmr" (diversified results).
    search_type: Literal["similarity", "mmr"] = "similarity"
    # MMR candidate pool size; the k results are diversified from these.
    fetch_k: int = _DEFAULT_FETCH_K
    # MMR diversity 0-1: 1.0 favours relevance, 0.0 favours diversity.
    lambda_mult: float = _DEFAULT_LAMBDA_MULT
    # Restrict results to these source files (empty = search all sources).
    source_filter: tuple[str, ...] = ()

    @field_validator("temperature")
    @classmethod
    def _validate_temperature(cls, value: float) -> float:
        if not 0.0 <= value <= _MAX_TEMPERATURE:
            raise ValueError(f"temperature must be between 0 and {_MAX_TEMPERATURE}.")
        return value

    @field_validator("score_threshold", "lambda_mult")
    @classmethod
    def _validate_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("Value must be between 0 and 1.")
        return value

    @field_validator("max_tokens", "top_k", "fetch_k")
    @classmethod
    def _require_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Value must be at least 1.")
        return value


class ConversationalConfig(BaseModel):
    """Knobs for the advanced conversational RAG pipeline (Step 5).

    Wraps a :class:`RagConfig` (retrieval + answer generation) and adds the
    stage toggles and thresholds for query decomposition, re-ranking, rolling
    conversation state, and validated follow-up suggestions. UI controls map
    directly onto these fields.
    """

    rag: RagConfig = Field(default_factory=RagConfig)
    # Small helper model for planning/state/follow-ups/LLM re-rank; None = auto-pick.
    aux_model_id: str | None = None

    plan_enabled: bool = True
    plan_max_subquestions: int = 4
    plan_recent_turns: int = 2

    reranker: Literal["off", "local", "llm"] = "local"
    rerank_top_n: int = 5

    followups_enabled: bool = True
    followup_candidate_count: int = 6
    followup_show_count: int = 3
    followup_probe_k: int = 3
    # At/above keep outright; at/below drop outright; between -> LLM answerability check.
    followup_min_score: float = 0.60
    followup_drop_score: float = 0.40
    answerability_chunks: int = 2

    answer_recent_turns: int = 3
    state_summary_start_turn: int = 4
    state_summary_max_words: int = 150

    max_workers: int = 6

    # Requested answer tone (free-form label, e.g. "Neutral"/"Formal"/"Friendly");
    # threaded into the answer prompt so the model matches it.
    tone: str = "Neutral"

    @field_validator("followup_min_score", "followup_drop_score")
    @classmethod
    def _validate_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("Value must be between 0 and 1.")
        return value

    @field_validator(
        "plan_max_subquestions",
        "rerank_top_n",
        "followup_candidate_count",
        "followup_show_count",
        "followup_probe_k",
        "answerability_chunks",
        "state_summary_max_words",
        "max_workers",
    )
    @classmethod
    def _require_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Value must be at least 1.")
        return value

    @field_validator("plan_recent_turns", "answer_recent_turns", "state_summary_start_turn")
    @classmethod
    def _require_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("Value must be 0 or greater.")
        return value

    @field_validator("tone")
    @classmethod
    def _validate_tone(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("tone must not be empty.")
        return cleaned

    @model_validator(mode="after")
    def _validate_threshold_order(self) -> ConversationalConfig:
        if self.followup_drop_score > self.followup_min_score:
            raise ValueError("followup_drop_score must be <= followup_min_score.")
        return self
