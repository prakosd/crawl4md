"""Conversational, history-aware retrieval-augmented generation (Step 5).

A follow-up question is first rewritten into a standalone search query using the
recent conversation (``condense_question``), context is retrieved for that query,
and the answer is generated with the recent history in the prompt. The pure
helpers take an already-resolved chat model so a UI can stream and tests run
offline with the echo model.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, Any

from artifact_store import LibraryMessage
from log4py import get_logger
from rag_engine import messages
from rag_engine.catalog import ECHO_MODEL
from rag_engine.config import ConversationalConfig, RagConfig
from rag_engine.decompose import plan_queries, update_state
from rag_engine.followups import suggest_followups, validate_followups
from rag_engine.llm import ResolvedChatModel, resolve_auxiliary_model, resolve_chat_model
from rag_engine.models import (
    ChatTurn,
    ConversationalAnswer,
    ConversationState,
    QueryPlan,
    RagAnswer,
    RetrievedChunk,
    ValidatedFollowup,
)
from rag_engine.prompts import (
    _DEFAULT_TONE,
    CONDENSE_SYSTEM_PROMPT,
    QA_SYSTEM_PROMPT,
    format_context,
)
from rag_engine.rerank import rerank_chunks
from rag_engine.retrieval import RetrievalResult, retrieve, retrieve_multi

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = [
    "chat_answer",
    "condense_question",
    "conversational_answer",
    "generate_chat_answer",
    "stream_chat_answer",
]

_logger = get_logger(__name__)


def _report(callback: Callable[[LibraryMessage], None] | None, message: LibraryMessage) -> None:
    """Send a pipeline-progress message to *callback* when one is provided."""
    if callback is not None:
        callback(message)


def _history_messages(history: Sequence[ChatTurn]) -> list[tuple[str, str]]:
    return [("ai" if turn.role == "assistant" else "human", turn.content) for turn in history]


def condense_question(chat_model: BaseChatModel, history: Sequence[ChatTurn], question: str) -> str:
    """Rewrite a follow-up *question* into a standalone search query."""
    question = question.strip()
    if not history:
        return question
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [("system", CONDENSE_SYSTEM_PROMPT), *_history_messages(history), ("human", "{question}")]
    )
    chain = prompt | chat_model | StrOutputParser()
    rewritten = chain.invoke({"question": question}).strip()
    return rewritten or question


def _chat_chain(
    chat_model: BaseChatModel,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    *,
    tone: str = _DEFAULT_TONE,
) -> tuple[Any, dict]:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [("system", QA_SYSTEM_PROMPT), *_history_messages(history), ("human", "{question}")]
    )
    base = {"context": format_context(chunks), "tone": tone}
    return prompt | chat_model | StrOutputParser(), base


def generate_chat_answer(
    chat_model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    *,
    tone: str = _DEFAULT_TONE,
) -> str:
    """Generate a conversational answer string."""
    chain, base = _chat_chain(chat_model, chunks, history, tone=tone)
    return chain.invoke({**base, "question": question})


def stream_chat_answer(
    chat_model: BaseChatModel,
    question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    *,
    tone: str = _DEFAULT_TONE,
) -> Iterator[str]:
    """Yield conversational answer tokens as they are generated."""
    chain, base = _chat_chain(chat_model, chunks, history, tone=tone)
    yield from chain.stream({**base, "question": question})


def chat_answer(
    run_dir: Path | str,
    question: str,
    history: Sequence[ChatTurn],
    config: RagConfig,
    *,
    retriever: Callable[..., RetrievalResult] = retrieve,
    chat_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_chat_model,
) -> RagAnswer:
    """Answer a follow-up *question* using conversation *history* and the index."""
    question = question.strip()
    if not question:
        return RagAnswer(answer="", errors=[messages.empty_question()])

    resolved, chat_warnings = chat_resolver(
        config.llm_model, temperature=config.temperature, max_tokens=config.max_tokens
    )
    _logger.info(
        "Conversational RAG over %s: model=%s, %d turn(s) of history",
        Path(run_dir).name,
        resolved.model_id,
        len(history),
    )
    # Echo cannot rewrite a query, so only condense with a real model.
    if history and resolved.model_id != ECHO_MODEL:
        try:
            search_query = condense_question(resolved.model, history, question)
        except Exception:  # noqa: BLE001 - condensation is best-effort
            search_query = question
    else:
        search_query = question

    retrieval = retriever(run_dir, search_query, config)
    if retrieval.errors:
        return RagAnswer(
            answer="",
            sources=retrieval.chunks,
            model_used=resolved.model_id,
            warnings=[*chat_warnings, *retrieval.warnings],
            errors=retrieval.errors,
        )

    answer = RagAnswer(
        answer="",
        sources=retrieval.chunks,
        model_used=resolved.model_id,
        warnings=[*chat_warnings, *retrieval.warnings],
    )
    try:
        answer.answer = generate_chat_answer(resolved.model, question, retrieval.chunks, history)
    except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
        _logger.warning("Conversational RAG generation failed: %s", exc)
        answer.errors.append(messages.classify_generation_failure(str(exc)))
    return answer


def conversational_answer(
    run_dir: Path | str,
    raw_question: str,
    state: ConversationState,
    config: ConversationalConfig,
    *,
    history: Sequence[ChatTurn] = (),
    cached_chunks: Sequence[RetrievedChunk] | None = None,
    retriever: Callable[..., RetrievalResult] = retrieve,
    chat_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_chat_model,
    aux_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_auxiliary_model,
    progress_callback: Callable[[LibraryMessage], None] | None = None,
) -> ConversationalAnswer:
    """Answer a turn with the advanced conversational RAG pipeline (Step 5).

    Resolves the answer model and a small auxiliary model, then runs the full
    pipeline: plan (decompose) → multi-query retrieval → re-ranking → grounded
    answer → validated follow-ups → conversation-state update, returning a
    ``ConversationalAnswer`` with per-stage timings. A ``cached_chunks`` hit skips
    planning, retrieval, and re-ranking and answers straight from the carried
    passages (still generating follow-ups and updating state).
    """
    raw_question = raw_question.strip()
    if not raw_question:
        return ConversationalAnswer(answer="", state=state, errors=[messages.empty_question()])

    timings: dict[str, float] = {}
    warnings: list[LibraryMessage] = []

    resolved, chat_warnings = chat_resolver(
        config.rag.llm_model,
        temperature=config.rag.temperature,
        max_tokens=config.rag.max_tokens,
    )
    warnings.extend(chat_warnings)
    aux_resolved, aux_warnings = aux_resolver(config)
    warnings.extend(aux_warnings)
    recent = list(history)[-2 * config.answer_recent_turns :] if config.answer_recent_turns else []
    turn_index = len(history) // 2

    if cached_chunks is not None:
        _logger.info("Conversational RAG over %s: cache hit", Path(run_dir).name)
        return _compose_turn(
            run_dir,
            raw_question,
            list(cached_chunks),
            recent,
            QueryPlan(sub_questions=[raw_question]),
            state,
            resolved,
            aux_resolved,
            config,
            retriever=retriever,
            warnings=warnings,
            timings=timings,
            turn_index=turn_index,
            reranker_used=None,
            progress_callback=progress_callback,
        )

    _logger.info(
        "Conversational RAG over %s: model=%s, aux=%s",
        Path(run_dir).name,
        resolved.model_id,
        aux_resolved.model_id,
    )

    _report(progress_callback, messages.progress_plan())
    start = perf_counter()
    plan = plan_queries(
        aux_resolved.model, state, raw_question, config, model_id=aux_resolved.model_id
    )
    timings["plan"] = perf_counter() - start
    warnings.extend(plan.warnings)
    sub_questions = plan.sub_questions or [raw_question]

    _report(progress_callback, messages.progress_retrieve())
    start = perf_counter()
    retrieval = retrieve_multi(
        run_dir,
        sub_questions,
        config.rag,
        retriever=retriever,
        max_workers=config.max_workers,
    )
    timings["retrieve"] = perf_counter() - start
    warnings.extend(retrieval.warnings)
    if retrieval.errors:
        return ConversationalAnswer(
            answer="",
            sources=retrieval.chunks,
            plan=plan,
            state=state,
            model_used=resolved.model_id,
            aux_model_used=aux_resolved.model_id,
            timings=timings,
            warnings=warnings,
            errors=retrieval.errors,
        )

    _report(progress_callback, messages.progress_rerank())
    start = perf_counter()
    reranked, rerank_warnings = rerank_chunks(
        sub_questions,
        retrieval.chunks,
        config.rerank_top_n,
        config,
        chat_model=aux_resolved.model if aux_resolved.model_id != ECHO_MODEL else None,
    )
    timings["rerank"] = perf_counter() - start
    warnings.extend(rerank_warnings)

    return _compose_turn(
        run_dir,
        raw_question,
        reranked,
        recent,
        plan,
        state,
        resolved,
        aux_resolved,
        config,
        retriever=retriever,
        warnings=warnings,
        timings=timings,
        turn_index=turn_index,
        reranker_used=config.reranker,
        progress_callback=progress_callback,
    )


def _answer_stage(
    resolved: ResolvedChatModel,
    raw_question: str,
    chunks: Sequence[RetrievedChunk],
    history: Sequence[ChatTurn],
    tone: str,
) -> tuple[str, list[LibraryMessage], float]:
    """Generate the grounded answer, returning (text, errors, elapsed seconds)."""
    errors: list[LibraryMessage] = []
    start = perf_counter()
    answer_text = ""
    try:
        answer_text = generate_chat_answer(resolved.model, raw_question, chunks, history, tone=tone)
    except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
        _logger.warning("Conversational RAG generation failed: %s", exc)
        errors.append(messages.classify_generation_failure(str(exc)))
    return answer_text, errors, perf_counter() - start


def _followups_stage(
    run_dir: Path | str,
    aux: ResolvedChatModel,
    chunks: Sequence[RetrievedChunk],
    plan: QueryPlan,
    config: ConversationalConfig,
    retriever: Callable[..., RetrievalResult],
) -> tuple[list[ValidatedFollowup], list[LibraryMessage], float]:
    """Suggest and validate follow-ups, returning (follow_ups, warnings, elapsed seconds)."""
    warnings: list[LibraryMessage] = []
    follow_ups: list[ValidatedFollowup] = []
    start = perf_counter()
    try:
        candidates = suggest_followups(aux.model, chunks, plan, config)
        follow_ups = validate_followups(
            run_dir, candidates, config, model=aux.model, retriever=retriever
        )
        if candidates and not follow_ups:
            warnings.append(messages.followups_none_valid())
    except Exception as exc:  # noqa: BLE001 - follow-ups are optional
        _logger.warning("Follow-up generation failed: %s", exc)
        warnings.append(messages.followups_generation_failed(str(exc)))
    return follow_ups, warnings, perf_counter() - start


def _compose_turn(
    run_dir: Path | str,
    raw_question: str,
    chunks: list[RetrievedChunk],
    history: Sequence[ChatTurn],
    plan: QueryPlan,
    state: ConversationState,
    resolved: ResolvedChatModel,
    aux: ResolvedChatModel,
    config: ConversationalConfig,
    *,
    retriever: Callable[..., RetrievalResult],
    warnings: list[LibraryMessage],
    timings: dict[str, float],
    turn_index: int,
    reranker_used: str | None,
    progress_callback: Callable[[LibraryMessage], None] | None = None,
) -> ConversationalAnswer:
    """Generate the answer and follow-ups concurrently, then roll state forward.

    The answer (main model) and follow-ups (auxiliary model) are independent given
    the retrieved chunks, so they run on a small thread pool to overlap their model
    calls; ``update_state`` follows because it needs the finished answer.
    """
    _report(progress_callback, messages.progress_answer())
    follow_ups: list[ValidatedFollowup] = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        answer_future = executor.submit(
            _answer_stage, resolved, raw_question, chunks, history, config.tone
        )
        followups_future = (
            executor.submit(_followups_stage, run_dir, aux, chunks, plan, config, retriever)
            if config.followups_enabled and aux.model_id != ECHO_MODEL
            else None
        )
        answer_text, errors, timings["answer"] = answer_future.result()
        if followups_future is not None:
            follow_ups, followups_warnings, timings["followups"] = followups_future.result()
            warnings.extend(followups_warnings)

    resolved_question = "; ".join(plan.sub_questions) or raw_question
    _report(progress_callback, messages.progress_state())
    start = perf_counter()
    next_state = update_state(
        aux.model,
        state,
        resolved_question,
        answer_text,
        config,
        model_id=aux.model_id,
        turn_index=turn_index,
    )
    timings["state"] = perf_counter() - start

    return ConversationalAnswer(
        answer=answer_text,
        sources=chunks,
        plan=plan,
        follow_ups=follow_ups,
        state=next_state,
        model_used=resolved.model_id,
        aux_model_used=aux.model_id,
        reranker_used=reranker_used,
        timings=timings,
        warnings=warnings,
        errors=errors,
    )
