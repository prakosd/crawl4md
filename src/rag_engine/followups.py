"""Follow-up suggestion generation and validation for conversational RAG.

``suggest_followups`` proposes candidate questions from the retrieved topics.
``validate_followups`` keeps only the candidates the corpus can actually answer
by probe-retrieving each (in parallel) and applying a two-tier score threshold
with an LLM answerability check in the borderline band. Kept follow-ups carry
the passages fetched while validating them, so a click can answer instantly.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

from log4py import get_logger
from rag_engine.config import ConversationalConfig
from rag_engine.models import QueryPlan, RetrievedChunk, ValidatedFollowup
from rag_engine.prompts import (
    ANSWERABILITY_TEMPLATE,
    SUGGEST_FOLLOWUPS_TEMPLATE,
    invoke_text,
    parse_json_array,
)
from rag_engine.retrieval import RetrievalResult, retrieve

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = ["answerability_check", "suggest_followups", "validate_followups"]

_logger = get_logger(__name__)

_MAX_TOPICS = 6
_TOPIC_SNIPPET_CHARS = 160
_NONE_PLACEHOLDER = "(none)"
_YES = "yes"


def suggest_followups(
    model: BaseChatModel,
    chunks: Sequence[RetrievedChunk],
    plan: QueryPlan,
    config: ConversationalConfig,
) -> list[str]:
    """Generate candidate follow-up questions from the retrieved topics.

    Returns an empty list when follow-ups are disabled or nothing was retrieved,
    and on a parse failure. A model error propagates so the caller can record a
    generation-failure warning.
    """
    if not config.followups_enabled or not chunks:
        return []
    prompt = SUGGEST_FOLLOWUPS_TEMPLATE.format(
        topics=_context_topics(chunks),
        questions=_format_questions(plan.sub_questions),
        count=config.followup_candidate_count,
    )
    return parse_json_array(invoke_text(model, prompt)) or []


def answerability_check(
    model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    limit: int,
) -> bool:
    """Return whether the top *limit* *chunks* can answer *question* (YES/NO)."""
    context = "\n\n".join(chunk.text for chunk in list(chunks)[:limit])
    prompt = ANSWERABILITY_TEMPLATE.format(context=context, question=question)
    try:
        reply = invoke_text(model, prompt).strip().lower()
    except Exception as exc:  # noqa: BLE001 - the check is best-effort
        _logger.warning("Answerability check failed: %s", exc)
        return False
    return reply.startswith(_YES)


def validate_followups(
    run_dir: Path | str,
    candidates: Sequence[str],
    config: ConversationalConfig,
    *,
    model: BaseChatModel | None = None,
    retriever: Callable[..., RetrievalResult] = retrieve,
) -> list[ValidatedFollowup]:
    """Keep only candidates the corpus can answer, carrying their probe chunks.

    Each candidate is probe-retrieved in parallel. A best score at/above
    ``followup_min_score`` keeps it outright; at/below ``followup_drop_score``
    drops it; in between, the LLM answerability check decides. Kept follow-ups
    are sorted by score and truncated to ``followup_show_count``.
    """
    unique = _dedupe([text.strip() for text in candidates if text.strip()])
    if not unique:
        return []
    probe = config.rag.model_copy(update={"top_k": config.followup_probe_k})
    workers = max(1, min(config.max_workers, len(unique)))
    results: dict[str, RetrievalResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(retriever, run_dir, question, probe): question for question in unique
        }
        for future, question in futures.items():
            try:
                results[question] = future.result()
            except Exception as exc:  # noqa: BLE001 - one probe failing is tolerated
                _logger.warning("Follow-up probe failed for %r: %s", question, exc)

    kept: list[ValidatedFollowup] = []
    for question in unique:
        result = results.get(question)
        if result is None or result.errors or not result.chunks:
            continue
        best = max(chunk.score for chunk in result.chunks)
        checked = False
        if best >= config.followup_min_score:
            keep = True
        elif best <= config.followup_drop_score:
            keep = False
        elif model is not None:
            checked = True
            keep = answerability_check(model, question, result.chunks, config.answerability_chunks)
        else:
            keep = False
        if keep:
            kept.append(
                ValidatedFollowup(
                    question=question,
                    chunks=result.chunks,
                    score=best,
                    verdict="keep",
                    checked_by_llm=checked,
                )
            )
    kept.sort(key=lambda item: item.score, reverse=True)
    return kept[: config.followup_show_count]


def _context_topics(chunks: Sequence[RetrievedChunk]) -> str:
    topics: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        if chunk.source in seen:
            continue
        seen.add(chunk.source)
        snippet = " ".join(chunk.text.split())[:_TOPIC_SNIPPET_CHARS]
        topics.append(f"- {chunk.source}: {snippet}")
        if len(topics) >= _MAX_TOPICS:
            break
    return "\n".join(topics) if topics else _NONE_PLACEHOLDER


def _format_questions(questions: Sequence[str]) -> str:
    items = [question for question in questions if question]
    return "\n".join(f"- {question}" for question in items) if items else _NONE_PLACEHOLDER


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique
