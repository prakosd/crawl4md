"""Plain data structures shared across the rag_engine pipeline.

These mirror the lightweight-result philosophy of ``vector_indexer``: a UI can
render an answer, its source chunks, and any structured warnings/errors without
importing LangChain or knowing how generation happened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from artifact_store import LibraryMessage

__all__ = [
    "ChatTurn",
    "ConversationState",
    "ConversationalAnswer",
    "QueryPlan",
    "RagAnswer",
    "RetrievedChunk",
    "TokenUsage",
    "ValidatedFollowup",
]


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk returned by similarity search, with its provenance and score."""

    text: str
    source: str
    score: float
    metadata: dict[str, str]
    # Sub-questions (from a decomposed query) this chunk was retrieved for.
    matched_queries: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChatTurn:
    """One message in a conversation history (``role`` is ``user``/``assistant``)."""

    role: str
    content: str


@dataclass
class RagAnswer:
    """Structured outcome of a QA or conversational RAG request.

    ``warnings`` and ``errors`` are :class:`~artifact_store.LibraryMessage`
    objects carrying a stable ``code`` plus structured ``params``; ``str()`` of
    each yields its English ``default_text`` for UIs without localization.
    """

    answer: str
    sources: list[RetrievedChunk] = field(default_factory=list)
    model_used: str | None = None
    warnings: list[LibraryMessage] = field(default_factory=list)
    errors: list[LibraryMessage] = field(default_factory=list)


@dataclass(frozen=True)
class TokenUsage:
    """Token counts a chat model reported for one generation, when available.

    Any field may be ``None`` when the provider reports no usage (e.g. the
    offline echo model), so a UI can show "n/a" instead of a fabricated count.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass
class QueryPlan:
    """How a raw question was resolved and split into standalone sub-questions.

    ``degraded`` is ``True`` when planning was skipped or fell back (e.g. the
    offline model, or unparsable output), so a single sub-question equal to the
    original was used.
    """

    sub_questions: list[str] = field(default_factory=list)
    degraded: bool = False
    warnings: list[LibraryMessage] = field(default_factory=list)


@dataclass(frozen=True)
class ConversationState:
    """Rolling memory the rewriter uses to resolve references across turns.

    ``recent_resolved`` holds *rewritten* (standalone) questions, never raw user
    text, so ambiguity does not compound as the conversation grows.
    """

    summary: str = ""
    entities: dict[str, str] = field(default_factory=dict)
    recent_resolved: tuple[str, ...] = ()
    open_threads: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidatedFollowup:
    """A suggested follow-up question the corpus can actually answer.

    ``chunks`` are the passages fetched while validating it, carried so a click
    can answer instantly without retrieving again. ``checked_by_llm`` records
    whether the borderline answerability check was invoked.
    """

    question: str
    chunks: list[RetrievedChunk] = field(default_factory=list)
    score: float = 0.0
    verdict: Literal["keep", "drop"] = "keep"
    checked_by_llm: bool = False


@dataclass
class ConversationalAnswer:
    """Structured outcome of one conversational RAG turn.

    Extends the single-turn answer with the query plan, validated follow-ups, the
    next conversation state, and per-stage ``timings`` (plan/retrieve/rerank/
    answer/followups seconds) so a UI can render an inspection view.
    """

    answer: str
    sources: list[RetrievedChunk] = field(default_factory=list)
    plan: QueryPlan = field(default_factory=QueryPlan)
    follow_ups: list[ValidatedFollowup] = field(default_factory=list)
    state: ConversationState = field(default_factory=ConversationState)
    model_used: str | None = None
    aux_model_used: str | None = None
    reranker_used: str | None = None
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[LibraryMessage] = field(default_factory=list)
    errors: list[LibraryMessage] = field(default_factory=list)
