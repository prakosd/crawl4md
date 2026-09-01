"""Query planning for conversational RAG (Step 5): resolve references + split.

``plan_queries`` rewrites a user's latest question into one or more standalone
sub-questions using the running :class:`~rag_engine.models.ConversationState`.
It degrades safely: the offline model, disabled planning, or unparsable output
all fall back to a single sub-question equal to the original, never raising.
``looks_multi_part`` is a pure heuristic used to skip the model call entirely
when there is nothing to resolve or split.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING

from log4py import get_logger
from rag_engine import messages
from rag_engine.catalog import ECHO_MODEL
from rag_engine.config import ConversationalConfig
from rag_engine.models import ConversationState, QueryPlan
from rag_engine.prompts import (
    PLAN_QUERIES_TEMPLATE,
    STATE_UPDATE_TEMPLATE,
    invoke_text,
    parse_json_array,
    parse_json_object,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = ["looks_multi_part", "plan_queries", "update_state"]

_logger = get_logger(__name__)

# Signals that a question likely bundles several asks and benefits from splitting.
_MULTI_PART_MARKERS = (
    "also",
    "additionally",
    "and also",
    "what about",
    "furthermore",
    "as well as",
)
_AND_BEFORE_QUESTION = re.compile(r"\band\b[^?]*\?")
_NONE_PLACEHOLDER = "(none)"


def looks_multi_part(text: str) -> bool:
    """Heuristic (no model call): does *text* likely bundle several questions?"""
    lowered = text.lower()
    if lowered.count("?") > 1:
        return True
    if any(marker in lowered for marker in _MULTI_PART_MARKERS):
        return True
    return bool(_AND_BEFORE_QUESTION.search(lowered))


def plan_queries(
    model: BaseChatModel,
    state: ConversationState,
    raw_question: str,
    config: ConversationalConfig,
    *,
    model_id: str,
) -> QueryPlan:
    """Resolve references and split *raw_question* into standalone sub-questions.

    *model_id* is the resolved auxiliary model's id; the offline echo model
    cannot rewrite, so planning is skipped for it. Returns a degraded plan (a
    single sub-question equal to the original) whenever planning is disabled,
    offline, or the reply cannot be parsed.
    """
    raw_question = raw_question.strip()
    if not config.plan_enabled or model_id == ECHO_MODEL:
        warnings = [messages.plan_skipped_offline()] if model_id == ECHO_MODEL else []
        return QueryPlan(sub_questions=[raw_question], degraded=True, warnings=warnings)

    state_is_empty = not (state.summary or state.entities or state.recent_resolved)
    if not looks_multi_part(raw_question) and state_is_empty:
        # Nothing to resolve and nothing to split: skip the model call.
        return QueryPlan(sub_questions=[raw_question])

    prompt = PLAN_QUERIES_TEMPLATE.format(
        summary=state.summary or _NONE_PLACEHOLDER,
        entities=_format_entities(state.entities),
        recent=_format_recent(state.recent_resolved, config.plan_recent_turns),
        question=raw_question,
    )
    try:
        reply = invoke_text(model, prompt)
    except Exception as exc:  # noqa: BLE001 - planning is best-effort
        _logger.warning("Query planning failed: %s", exc)
        return QueryPlan(
            sub_questions=[raw_question], degraded=True, warnings=[messages.plan_unparsable()]
        )

    parsed = parse_json_array(reply)
    if not parsed:
        return QueryPlan(
            sub_questions=[raw_question], degraded=True, warnings=[messages.plan_unparsable()]
        )

    seen: set[str] = set()
    sub_questions: list[str] = []
    for item in parsed:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        sub_questions.append(item)
        if len(sub_questions) >= config.plan_max_subquestions:
            break
    _logger.info("Query plan: %d sub-question(s)", len(sub_questions))
    return QueryPlan(sub_questions=sub_questions)


def _format_entities(entities: dict[str, str]) -> str:
    if not entities:
        return _NONE_PLACEHOLDER
    return "\n".join(f"- {key}: {value}" for key, value in entities.items())


def _format_recent(recent: Sequence[str], limit: int) -> str:
    items = list(recent)[-limit:] if limit > 0 else []
    return "\n".join(f"- {question}" for question in items) if items else _NONE_PLACEHOLDER


def update_state(
    model: BaseChatModel,
    state: ConversationState,
    resolved_question: str,
    answer_text: str,
    config: ConversationalConfig,
    *,
    model_id: str,
    turn_index: int,
) -> ConversationState:
    """Return the next conversation state after a turn.

    Early turns (and the offline model) keep a verbatim window of recently
    *resolved* questions without summarizing. From ``state_summary_start_turn``
    onward, the auxiliary model rolls the summary/entities/open-threads forward;
    a failed or unparsable update preserves the prior state, with only the recent
    window advanced.
    """
    recent = _append_recent(
        state.recent_resolved, resolved_question.strip(), config.plan_recent_turns
    )
    if model_id == ECHO_MODEL or turn_index < config.state_summary_start_turn:
        return replace(state, recent_resolved=recent)

    prompt = STATE_UPDATE_TEMPLATE.format(
        summary=state.summary or _NONE_PLACEHOLDER,
        entities=json.dumps(state.entities) if state.entities else "{}",
        question=resolved_question.strip(),
        answer=answer_text.strip(),
        max_words=config.state_summary_max_words,
    )
    try:
        reply = invoke_text(model, prompt)
    except Exception as exc:  # noqa: BLE001 - state update is best-effort
        _logger.warning("Conversation-state update failed: %s", exc)
        return replace(state, recent_resolved=recent)

    parsed = parse_json_object(reply)
    if parsed is None:
        return replace(state, recent_resolved=recent)
    return ConversationState(
        summary=_cap_words(
            str(parsed.get("summary") or state.summary), config.state_summary_max_words
        ),
        entities=_coerce_entities(parsed.get("entities"), state.entities),
        recent_resolved=recent,
        open_threads=_coerce_str_tuple(parsed.get("open_threads")),
    )


def _append_recent(recent: Sequence[str], item: str, limit: int) -> tuple[str, ...]:
    if not item or limit <= 0:
        return () if limit <= 0 else tuple(recent)
    return (*recent, item)[-limit:]


def _cap_words(text: str, max_words: int) -> str:
    return " ".join(text.split()[:max_words])


def _coerce_entities(value: object, fallback: dict[str, str]) -> dict[str, str]:
    if isinstance(value, dict):
        return {str(key): str(val) for key, val in value.items()}
    return dict(fallback)


def _coerce_str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()
