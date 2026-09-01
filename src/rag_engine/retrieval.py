"""Open a persisted vector index and run similarity search over it (Step 3).

The index is reopened with the *same* embedding model that wrote it (read from
the run manifest) through a :class:`~rag_engine.search.VectorSearcher`, so the
retrieval pipeline never touches a specific vector store directly. Heavy imports
(langchain-chroma, chromadb) stay inside the searcher that needs them.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from artifact_store import LibraryMessage
from log4py import get_logger
from rag_engine import messages
from rag_engine.config import RagConfig
from rag_engine.models import RetrievedChunk
from rag_engine.search import VectorSearcher, open_searcher
from vector_indexer import (
    EmbeddingProviderUnavailable,
    ResolvedEmbedding,
    load_manifest,
    resolve_embedding,
)

__all__ = [
    "RetrievalResult",
    "chunk_identity",
    "load_index_embeddings",
    "retrieve",
    "retrieve_multi",
]

_logger = get_logger(__name__)

_DEFAULT_MAX_WORKERS = 6


@dataclass
class RetrievalResult:
    """Chunks returned by a search plus any structured warnings/errors."""

    chunks: list[RetrievedChunk] = field(default_factory=list)
    warnings: list[LibraryMessage] = field(default_factory=list)
    errors: list[LibraryMessage] = field(default_factory=list)


def load_index_embeddings(
    run_dir: Path | str,
) -> tuple[ResolvedEmbedding, list[LibraryMessage]]:
    """Build the embeddings recorded in *run_dir*'s manifest."""
    manifest = load_manifest(run_dir)
    model = manifest.embedding_model_used or manifest.embedding_model_requested
    if not model:
        raise ValueError("The index manifest does not record an embedding model.")
    return resolve_embedding(model, manifest.embedding_dimension)


def retrieve(
    run_dir: Path | str,
    query: str,
    config: RagConfig,
    *,
    embedding_loader: Callable[
        [Path | str], tuple[ResolvedEmbedding, list[LibraryMessage]]
    ] = load_index_embeddings,
    searcher_factory: Callable[[Path | str, Any], VectorSearcher] = open_searcher,
) -> RetrievalResult:
    """Run similarity search for *query* over the index in *run_dir*."""
    result = RetrievalResult()
    run_path = Path(run_dir)
    _logger.info(
        "Semantic search: top %d (%s) over index %s",
        config.top_k,
        config.search_type,
        run_path.name,
    )
    try:
        resolved_emb, emb_warnings = embedding_loader(run_path)
    except FileNotFoundError:
        result.errors.append(messages.index_not_found(str(run_path)))
        return result
    except EmbeddingProviderUnavailable as exc:
        result.errors.append(messages.embedding_unavailable(str(exc)))
        return result
    except (OSError, ValueError) as exc:
        result.errors.append(messages.index_unreadable(str(run_path), str(exc)))
        return result
    result.warnings.extend(emb_warnings)
    try:
        searcher = searcher_factory(run_path, resolved_emb.embeddings)
        hits = searcher.search(
            query,
            config.top_k,
            search_type=config.search_type,
            fetch_k=config.fetch_k,
            lambda_mult=config.lambda_mult,
            source_filter=config.source_filter,
        )
    except Exception as exc:  # noqa: BLE001 - boundary around the vector store
        _logger.warning("Semantic search failed over %s: %s", run_path.name, exc)
        result.errors.append(messages.retrieval_failed(str(exc)))
        return result
    chunks = [
        RetrievedChunk(
            text=hit.text,
            source=hit.source,
            score=_distance_to_similarity(hit.distance),
            metadata=hit.metadata,
        )
        for hit in hits
    ]
    result.chunks = [chunk for chunk in chunks if chunk.score >= config.score_threshold]
    if not result.chunks:
        result.warnings.append(messages.no_context())
    _logger.info(
        "Semantic search returned %d chunk(s) (%d above score threshold %.2f)",
        len(chunks),
        len(result.chunks),
        config.score_threshold,
    )
    return result


def _distance_to_similarity(distance: float) -> float:
    """Map a vector-store distance (lower = closer) to a 0-1 similarity score.

    ``similarity_search_with_score`` returns the backend's raw distance, which is
    always defined (unlike the relevance-score variant, which assumes a known
    metric range). ``1 / (1 + distance)`` gives a bounded, monotonic score that is
    1.0 for an exact match and approaches 0 as the distance grows.
    """
    return 1.0 / (1.0 + max(0.0, float(distance)))


def chunk_identity(chunk: RetrievedChunk) -> str:
    """Return a stable identity for de-duplicating a chunk across sub-questions."""
    digest = hashlib.sha1(chunk.text.encode("utf-8")).hexdigest()  # noqa: S324 - non-crypto id
    return f"{chunk.source}::{digest}"


def retrieve_multi(
    run_dir: Path | str,
    sub_questions: Sequence[str],
    config: RagConfig,
    *,
    retriever: Callable[..., RetrievalResult] = retrieve,
    max_workers: int = _DEFAULT_MAX_WORKERS,
) -> RetrievalResult:
    """Retrieve for each sub-question in parallel, then merge and de-duplicate.

    A single sub-question short-circuits to a plain :func:`retrieve`. Otherwise
    each sub-question gets its own ``top_k`` search; results are merged (keeping
    the first, highest-scored occurrence of each chunk) and every chunk carries
    the sub-questions it matched. One sub-question failing does not sink the
    others — a ``rag.retrieval.partial_failure`` warning is recorded; only when
    every sub-question fails are the errors surfaced.
    """
    questions = [text for text in (item.strip() for item in sub_questions) if text]
    if not questions:
        return RetrievalResult()
    if len(questions) == 1:
        return retriever(run_dir, questions[0], config)

    workers = max(1, min(max_workers, len(questions)))
    results: dict[str, RetrievalResult] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(retriever, run_dir, question, config): question
            for question in questions
        }
        for future, question in futures.items():
            try:
                results[question] = future.result()
            except Exception as exc:  # noqa: BLE001 - one sub-question failing is tolerated
                _logger.warning("Retrieval failed for sub-question %r: %s", question, exc)

    merged: list[RetrievedChunk] = []
    index_by_identity: dict[str, int] = {}
    warnings: list[LibraryMessage] = []
    errors: list[LibraryMessage] = []
    failed: list[str] = []
    any_ok = False
    for question in questions:
        result = results.get(question)
        if result is None:
            failed.append(question)
            continue
        warnings.extend(result.warnings)
        if result.errors:
            failed.append(question)
            errors.extend(result.errors)
            continue
        any_ok = True
        for chunk in result.chunks:
            identity = chunk_identity(chunk)
            existing = index_by_identity.get(identity)
            if existing is None:
                index_by_identity[identity] = len(merged)
                merged.append(replace(chunk, matched_queries=(question,)))
            elif question not in merged[existing].matched_queries:
                merged[existing] = replace(
                    merged[existing],
                    matched_queries=(*merged[existing].matched_queries, question),
                )

    warnings = _dedupe_by_code(warnings)
    if not any_ok:
        return RetrievalResult(chunks=[], warnings=warnings, errors=_dedupe_by_code(errors))
    merged.sort(key=lambda chunk: chunk.score, reverse=True)
    if failed:
        warnings.append(messages.retrieval_partial_failure(", ".join(failed)))
    _logger.info(
        "Multi-query retrieval: %d sub-question(s), %d unique chunk(s)",
        len(questions),
        len(merged),
    )
    return RetrievalResult(chunks=merged, warnings=warnings)


def _dedupe_by_code(items: list[LibraryMessage]) -> list[LibraryMessage]:
    """Keep the first message per code (per-sub-question warnings are redundant)."""
    seen: set[str] = set()
    unique: list[LibraryMessage] = []
    for message in items:
        if message.code in seen:
            continue
        seen.add(message.code)
        unique.append(message)
    return unique
