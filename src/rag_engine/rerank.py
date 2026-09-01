"""Re-ranking for conversational RAG (Step 5): Off / Local / LLM strategies.

``rerank_chunks`` reorders merged retrieval results so the most relevant come
first, dispatching on ``config.reranker``:

- ``"off"``   — keep the incoming (search) order, truncated to ``top_n``.
- ``"local"`` — a sentence-transformers cross-encoder scores each (query, chunk)
  pair. The dependency and model load are lazy; if either is unavailable the
  chunks keep their search order and a ``rag.rerank.unavailable`` warning is
  recorded (never an error).
- ``"llm"``   — the auxiliary chat model orders the chunks via ``RERANK_TEMPLATE``.
  A missing/offline model or unparsable reply degrades to search order + warning.

The cross-encoder loader and chat model are injectable so tests never download a
model or touch a network.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import lru_cache
from typing import TYPE_CHECKING

from artifact_store import LibraryMessage
from log4py import get_logger
from rag_engine import messages
from rag_engine.config import ConversationalConfig
from rag_engine.models import RetrievedChunk
from rag_engine.prompts import RERANK_TEMPLATE, invoke_text, parse_ranking

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = ["load_cross_encoder", "rerank_chunks"]

_logger = get_logger(__name__)

# Small, CPU-friendly cross-encoder used for local re-ranking.
_LOCAL_CROSS_ENCODER = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderUnavailable(RuntimeError):
    """Raised when the local cross-encoder dependency or model cannot be loaded."""


@lru_cache(maxsize=2)
def load_cross_encoder(model_name: str = _LOCAL_CROSS_ENCODER) -> object:
    """Load and cache a sentence-transformers ``CrossEncoder``, or raise.

    The heavy import stays here so ``import rag_engine`` never pulls torch.
    """
    try:
        from sentence_transformers import CrossEncoder
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise CrossEncoderUnavailable(
            "sentence-transformers is required for local re-ranking; install the [rerank] extra."
        ) from exc
    except Exception as exc:  # noqa: BLE001 - an incompatible torch/transformers stack must degrade
        raise CrossEncoderUnavailable(
            f"the local re-ranking dependencies could not be imported: {exc}"
        ) from exc
    try:
        return CrossEncoder(model_name)
    except Exception as exc:  # noqa: BLE001 - model download/load failure
        raise CrossEncoderUnavailable(
            f"could not load cross-encoder {model_name!r}: {exc}"
        ) from exc


def rerank_chunks(
    queries: Sequence[str],
    chunks: Sequence[RetrievedChunk],
    top_n: int,
    config: ConversationalConfig,
    *,
    encoder_loader: Callable[..., object] = load_cross_encoder,
    chat_model: BaseChatModel | None = None,
) -> tuple[list[RetrievedChunk], list[LibraryMessage]]:
    """Reorder *chunks* per ``config.reranker`` and return the top ``top_n``."""
    ordered = list(chunks)
    if not ordered or config.reranker == "off":
        return ordered[:top_n], []
    if config.reranker == "local":
        return _rerank_local(queries, ordered, top_n, encoder_loader)
    if config.reranker == "llm":
        return _rerank_llm(queries, ordered, top_n, chat_model)
    return ordered[:top_n], []


def _rerank_local(
    queries: Sequence[str],
    chunks: list[RetrievedChunk],
    top_n: int,
    encoder_loader: Callable[..., object],
) -> tuple[list[RetrievedChunk], list[LibraryMessage]]:
    query_text = " ".join(queries)
    pairs = [(query_text, chunk.text) for chunk in chunks]
    try:
        scores = encoder_loader().predict(pairs)
    except Exception as exc:  # noqa: BLE001 - any local re-rank failure degrades to search order
        _logger.warning("Local re-ranking unavailable: %s", exc)
        return chunks[:top_n], [messages.rerank_unavailable("local", str(exc))]
    order = sorted(range(len(chunks)), key=lambda index: scores[index], reverse=True)
    return [chunks[index] for index in order][:top_n], []


def _rerank_llm(
    queries: Sequence[str],
    chunks: list[RetrievedChunk],
    top_n: int,
    chat_model: BaseChatModel | None,
) -> tuple[list[RetrievedChunk], list[LibraryMessage]]:
    if chat_model is None:
        return chunks[:top_n], [messages.rerank_unavailable("llm", "no auxiliary model available")]
    query_text = " ".join(queries)
    passages = "\n".join(f"[{index}] {chunk.text}" for index, chunk in enumerate(chunks))
    prompt = RERANK_TEMPLATE.format(query=query_text, passages=passages)
    try:
        reply = invoke_text(chat_model, prompt)
    except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
        _logger.warning("LLM re-ranking failed: %s", exc)
        return chunks[:top_n], [messages.rerank_unavailable("llm", str(exc))]
    order = parse_ranking(reply, len(chunks))
    if not order:
        return chunks[:top_n], [messages.rerank_unavailable("llm", "unparsable ranking")]
    ranked = [chunks[index] for index in order]
    # Append chunks the model omitted, preserving their search order.
    ranked_indices = set(order)
    ranked.extend(chunk for index, chunk in enumerate(chunks) if index not in ranked_indices)
    return ranked[:top_n], []
