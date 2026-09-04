"""Single-turn retrieval-augmented question answering (Step 4).

The pure generation helpers (``generate_answer`` / ``stream_answer``) take an
already-resolved chat model and chunks, so a UI can stream tokens and tests can
run offline with the echo model. ``answer_question`` orchestrates the full flow
(retrieve -> resolve model -> generate) and returns a structured ``RagAnswer``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

from artifact_store import LibraryMessage
from log4py import get_logger
from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.llm import ResolvedChatModel, resolve_chat_model
from rag_engine.models import RagAnswer, RetrievedChunk, TokenUsage
from rag_engine.prompts import _DEFAULT_TONE, QA_SYSTEM_PROMPT, format_context
from rag_engine.retrieval import RetrievalResult, retrieve

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = [
    "PromptGeneration",
    "answer_question",
    "generate_answer",
    "generate_from_prompt",
    "stream_answer",
    "stream_prompt",
]

_logger = get_logger(__name__)


def _qa_chain(
    chat_model: BaseChatModel, chunks: Sequence[RetrievedChunk], *, tone: str = _DEFAULT_TONE
) -> tuple[Any, dict]:
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages(
        [("system", QA_SYSTEM_PROMPT), ("human", "{question}")]
    )
    return prompt | chat_model | StrOutputParser(), {
        "context": format_context(chunks),
        "tone": tone,
    }


def generate_answer(
    chat_model: BaseChatModel, question: str, chunks: Sequence[RetrievedChunk]
) -> str:
    """Generate a single answer string from *question* and *chunks*."""
    chain, base = _qa_chain(chat_model, chunks)
    return chain.invoke({**base, "question": question})


def stream_answer(
    chat_model: BaseChatModel, question: str, chunks: Sequence[RetrievedChunk]
) -> Iterator[str]:
    """Yield answer tokens for *question* and *chunks* as they are generated."""
    chain, base = _qa_chain(chat_model, chunks)
    yield from chain.stream({**base, "question": question})


def _message_text(message: Any) -> str:
    """Extract plain text from a chat message or streamed chunk's ``content``."""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part if isinstance(part, str) else str(part.get("text", ""))
            for part in content
            if isinstance(part, (str, dict))
        ]
        return "".join(parts)
    return str(content)


def _token_usage(message: Any) -> TokenUsage | None:
    """Map a message's ``usage_metadata`` to a ``TokenUsage`` (``None`` if absent)."""
    usage = getattr(message, "usage_metadata", None)
    if not usage:
        return None
    return TokenUsage(
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
    )


class PromptGeneration:
    """Streams a raw prompt's answer and captures the full text plus token usage.

    Iterate it (e.g. via ``st.write_stream``) to receive answer-text chunks as
    they arrive. When iteration finishes, ``text`` holds the complete answer and
    ``usage`` the token counts the model reported (``None`` when the provider
    reports none, e.g. the echo model). The *prompt* is sent verbatim as a single
    human message, so what the user sees is exactly what the model receives.
    """

    def __init__(self, chat_model: BaseChatModel, prompt: str) -> None:
        self._chat_model = chat_model
        self._prompt = prompt
        self.text = ""
        self.usage: TokenUsage | None = None

    def __iter__(self) -> Iterator[str]:
        from langchain_core.messages import HumanMessage

        _logger.info("Running model on prompt (%d chars, streaming)", len(self._prompt))
        aggregate: Any = None
        parts: list[str] = []
        for chunk in self._chat_model.stream([HumanMessage(content=self._prompt)]):
            if aggregate is None:
                aggregate = chunk
            else:
                try:
                    aggregate = aggregate + chunk
                except TypeError:  # a chunk type that does not support merging
                    aggregate = chunk
            piece = _message_text(chunk)
            if piece:
                parts.append(piece)
                yield piece
        self.text = "".join(parts)
        self.usage = _token_usage(aggregate)
        _logger.info("Model response complete (%d chars, tokens=%s)", len(self.text), self.usage)


def stream_prompt(chat_model: BaseChatModel, prompt: str) -> PromptGeneration:
    """Return a :class:`PromptGeneration` that streams *prompt* to *chat_model*."""
    return PromptGeneration(chat_model, prompt)


def generate_from_prompt(chat_model: BaseChatModel, prompt: str) -> tuple[str, TokenUsage | None]:
    """Send *prompt* verbatim and return the full answer text and token usage."""
    from langchain_core.messages import HumanMessage

    _logger.info("Running model on prompt (%d chars)", len(prompt))
    message = chat_model.invoke([HumanMessage(content=prompt)])
    return _message_text(message), _token_usage(message)


def answer_question(
    run_dir: Path | str,
    question: str,
    config: RagConfig,
    *,
    retriever: Callable[..., RetrievalResult] = retrieve,
    chat_resolver: Callable[
        ..., tuple[ResolvedChatModel, list[LibraryMessage]]
    ] = resolve_chat_model,
) -> RagAnswer:
    """Answer a single *question* over the index in *run_dir*."""
    question = question.strip()
    if not question:
        return RagAnswer(answer="", errors=[messages.empty_question()])

    retrieval = retriever(run_dir, question, config)
    if retrieval.errors:
        return RagAnswer(
            answer="",
            sources=retrieval.chunks,
            warnings=retrieval.warnings,
            errors=retrieval.errors,
        )

    resolved, chat_warnings = chat_resolver(
        config.llm_model, temperature=config.temperature, max_tokens=config.max_tokens
    )
    _logger.info(
        "RAG Q&A over %s: model=%s, %d context chunk(s)",
        Path(run_dir).name,
        resolved.model_id,
        len(retrieval.chunks),
    )
    answer = RagAnswer(
        answer="",
        sources=retrieval.chunks,
        model_used=resolved.model_id,
        warnings=[*retrieval.warnings, *chat_warnings],
    )
    try:
        answer.answer = generate_answer(resolved.model, question, retrieval.chunks)
    except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
        _logger.warning("RAG answer generation failed: %s", exc)
        answer.errors.append(messages.classify_generation_failure(str(exc)))
    return answer
