"""End-to-end vector indexing orchestration.

``VectorIndexer.run`` resolves embeddings (recording a cause-specific error when
the requested model is unavailable, with no silent local fallback), loads and
chunks the inputs, and writes the embedded chunks to a vector store inside a new
timestamped run directory. The store factory and the embedding resolver are
injectable so the flow can be tested without langchain-chroma or network access.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING

from artifact_store import LibraryMessage
from artifact_store.naming import format_utc_timestamp_slug, parse_utc_timestamp_slug
from log4py import get_logger
from vector_indexer import messages
from vector_indexer.chunking import chunk_documents
from vector_indexer.config import IndexingConfig
from vector_indexer.document_loader import load_documents
from vector_indexer.embeddings import (
    DEFAULT_LOCAL_MODEL,
    EmbeddingProviderUnavailable,
    ResolvedEmbedding,
    resolve_embedding,
)
from vector_indexer.manifest import (
    CHROMA_SUBDIR,
    DEFAULT_COLLECTION_NAME,
    write_manifest,
)
from vector_indexer.models import Chunk, IndexingResult
from vector_indexer.vector_store.base import VectorStore
from vector_indexer.vector_store.chroma import ChromaVectorStore

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings

__all__ = ["DEFAULT_COLLECTION_NAME", "VectorIndexer"]

_logger = get_logger(__name__)

_EMBED_BATCH_SIZE = 32

# Coarse pipeline stages reported through the progress callback so a UI can show
# what the run is doing before per-chunk counts are available.
STAGE_RESOLVING_MODEL = "resolving_model"
STAGE_LOADING = "loading"
STAGE_CHUNKING = "chunking"
STAGE_EMBEDDING = "embedding"
STAGE_SAVING = "saving"

StoreFactory = Callable[[Path, str, "Embeddings"], VectorStore]
EmbeddingResolver = Callable[[str, int | None], tuple[ResolvedEmbedding, list[LibraryMessage]]]
ProgressCallback = Callable[[dict[str, object]], None]
CancelCheck = Callable[[], bool]


def _default_store_factory(
    persist_dir: Path, collection_name: str, embeddings: Embeddings
) -> VectorStore:
    return ChromaVectorStore(persist_dir, collection_name, embeddings)


class VectorIndexer:
    """Builds a persisted vector index from text inputs."""

    def __init__(
        self,
        *,
        store_factory: StoreFactory | None = None,
        embedding_resolver: EmbeddingResolver | None = None,
    ) -> None:
        self._store_factory = store_factory or _default_store_factory
        self._embedding_resolver = embedding_resolver or resolve_embedding

    def run(
        self,
        config: IndexingConfig,
        inputs: Sequence[Path | str],
        output_base: Path | str,
        *,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        progress_callback: ProgressCallback | None = None,
        should_cancel: CancelCheck | None = None,
    ) -> IndexingResult:
        """Run the full indexing pipeline and return a structured result."""
        run_dir = Path(output_base) / format_utc_timestamp_slug()
        run_dir.mkdir(parents=True, exist_ok=True)
        result = IndexingResult(success=False, output_dir=run_dir)
        _logger.info("Indexing started: %d input(s) -> %s", len(inputs), run_dir)

        _report_stage(progress_callback, STAGE_RESOLVING_MODEL)
        resolved = self._resolve_embeddings(config, result)
        if resolved is None:
            return self._finalize(
                run_dir, config, result, model_id=None, collection_name=collection_name
            )

        chunks = self._prepare_chunks(config, inputs, result, should_cancel, progress_callback)
        if chunks is None:
            return self._finalize(
                run_dir, config, result, model_id=resolved.model_id, collection_name=collection_name
            )

        self._embed_and_store(
            chunks,
            resolved,
            run_dir,
            collection_name,
            result,
            progress_callback,
            should_cancel,
            workers=_worker_count(config.index_workers, resolved.model_id),
        )
        return self._finalize(
            run_dir, config, result, model_id=resolved.model_id, collection_name=collection_name
        )

    def _resolve_embeddings(
        self, config: IndexingConfig, result: IndexingResult
    ) -> ResolvedEmbedding | None:
        try:
            resolved, warnings = self._embedding_resolver(
                config.embedding_model, config.embedding_dimension
            )
        except EmbeddingProviderUnavailable as exc:
            _logger.error("Embedding model %r unavailable: %s", config.embedding_model, exc)
            result.errors.append(messages.classify_model_unavailable(str(exc)))
            return None
        result.warnings.extend(warnings)
        _logger.info("Embedding model resolved: %s", resolved.model_id)
        return resolved

    def _prepare_chunks(
        self,
        config: IndexingConfig,
        inputs: Sequence[Path | str],
        result: IndexingResult,
        should_cancel: CancelCheck | None,
        progress_callback: ProgressCallback | None = None,
    ) -> list[Chunk] | None:
        _report_stage(progress_callback, STAGE_LOADING)
        load_result = load_documents(inputs)
        result.skipped_file_count = load_result.skipped_file_count
        result.warnings.extend(load_result.warnings)
        if not load_result.documents:
            result.errors.append(messages.no_readable_content())
            return None
        _logger.info(
            "Loaded %d document(s) (%d skipped)",
            len(load_result.documents),
            load_result.skipped_file_count,
        )
        if _cancelled(should_cancel):
            result.warnings.append(messages.cancelled_before_chunking())
            return None
        _report_stage(progress_callback, STAGE_CHUNKING)
        try:
            chunks = chunk_documents(
                load_result.documents,
                chunk_size=config.chunk_size,
                chunk_overlap=config.chunk_overlap,
                language=config.language,
            )
        except RuntimeError as exc:
            result.errors.append(messages.chunking_failed(str(exc)))
            return None
        if not chunks:
            result.errors.append(messages.no_chunks())
            return None
        _logger.info("Chunked into %d chunk(s)", len(chunks))
        return chunks

    def _embed_and_store(
        self,
        chunks: list[Chunk],
        resolved: ResolvedEmbedding,
        run_dir: Path,
        collection_name: str,
        result: IndexingResult,
        progress_callback: ProgressCallback | None,
        should_cancel: CancelCheck | None,
        *,
        workers: int,
    ) -> None:
        store = self._store_factory(run_dir / CHROMA_SUBDIR, collection_name, resolved.embeddings)
        indexed_sources: set[str] = set()
        total = len(chunks)
        batches = list(_batched(chunks, _EMBED_BATCH_SIZE))
        # Pre-assign ids per batch so concurrent workers never share a counter.
        ids = count()
        id_lists = [[str(next(ids)) for _ in batch] for batch in batches]
        lock = threading.Lock()
        # Embeddings run in parallel (the slow, network-bound step for cloud
        # models), but writes are serialized: the ChromaDB/SQLite backend is not
        # safe for concurrent writes from multiple worker threads.
        store_lock = threading.Lock()
        cancelled = False
        _report_stage(progress_callback, STAGE_EMBEDDING)
        _logger.info(
            "Embedding %d chunk(s) in %d batch(es) with %d worker(s)",
            total,
            len(batches),
            workers,
        )

        def _store_batch(batch: list[Chunk], batch_ids: list[str]) -> None:
            texts = [chunk.text for chunk in batch]
            vectors = resolved.embeddings.embed_documents(texts)
            with store_lock:
                store.add_embeddings(
                    texts=texts,
                    embeddings=vectors,
                    metadatas=[chunk.metadata for chunk in batch],
                    ids=batch_ids,
                )
            with lock:
                result.indexed_chunk_count += len(batch)
                indexed_sources.update(chunk.document_source for chunk in batch)
                _report_progress(progress_callback, result.indexed_chunk_count, total)

        try:
            if workers > 1:
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    futures = []
                    for batch, batch_ids in zip(batches, id_lists, strict=True):
                        if _cancelled(should_cancel):
                            cancelled = True
                            break
                        futures.append(pool.submit(_store_batch, batch, batch_ids))
                    for future in futures:
                        future.result()  # propagate any worker exception
            else:
                for batch, batch_ids in zip(batches, id_lists, strict=True):
                    if _cancelled(should_cancel):
                        cancelled = True
                        break
                    _store_batch(batch, batch_ids)
            if cancelled:
                result.warnings.append(messages.cancelled_partial())
            _report_stage(progress_callback, STAGE_SAVING)
            store.persist()
        except Exception as exc:  # noqa: BLE001 - boundary around the embedding backend
            _logger.error("Embedding/storage failed: %s", exc)
            result.errors.append(messages.classify_embedding_failure(str(exc)))
            return
        result.indexed_file_count = len(indexed_sources)
        result.indexed_sources = sorted(indexed_sources)
        _logger.info(
            "Saved index: %d chunk(s) from %d source(s)",
            result.indexed_chunk_count,
            result.indexed_file_count,
        )

    def _finalize(
        self,
        run_dir: Path,
        config: IndexingConfig,
        result: IndexingResult,
        *,
        model_id: str | None,
        collection_name: str,
    ) -> IndexingResult:
        result.success = result.indexed_chunk_count > 0 and not result.errors
        _write_manifest(run_dir, config, result, model_id=model_id, collection_name=collection_name)
        _logger.info(
            "Indexing complete: success=%s files=%d chunks=%d skipped=%d",
            result.success,
            result.indexed_file_count,
            result.indexed_chunk_count,
            result.skipped_file_count,
        )
        return result


def _cancelled(should_cancel: CancelCheck | None) -> bool:
    return bool(should_cancel and should_cancel())


def _worker_count(requested: int, model_id: str) -> int:
    """Resolve effective worker count: the local ONNX model stays sequential."""
    if model_id == DEFAULT_LOCAL_MODEL:
        return 1
    return max(1, requested)


def _report_progress(
    progress_callback: ProgressCallback | None, processed: int, total: int
) -> None:
    if progress_callback is not None:
        progress_callback({"processed_chunks": processed, "total_chunks": total})


def _report_stage(progress_callback: ProgressCallback | None, stage: str) -> None:
    if progress_callback is not None:
        progress_callback({"stage": stage})


def _batched(items: Sequence[Chunk], size: int) -> Iterator[list[Chunk]]:
    batch: list[Chunk] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _write_manifest(
    run_dir: Path,
    config: IndexingConfig,
    result: IndexingResult,
    *,
    model_id: str | None,
    collection_name: str,
) -> None:
    write_manifest(
        run_dir,
        {
            "created_at": _run_created_at(run_dir),
            "embedding_model_requested": config.embedding_model,
            "embedding_model_used": model_id,
            "embedding_dimension": config.embedding_dimension,
            "collection_name": collection_name,
            "chunk_size": config.chunk_size,
            "chunk_overlap": config.chunk_overlap,
            "language": config.language,
            "index_workers": config.index_workers,
            "success": result.success,
            "indexed_file_count": result.indexed_file_count,
            "indexed_chunk_count": result.indexed_chunk_count,
            "skipped_file_count": result.skipped_file_count,
            "indexed_sources": result.indexed_sources,
            "warnings": [message.as_dict() for message in result.warnings],
            "errors": [message.as_dict() for message in result.errors],
        },
    )


def _run_created_at(run_dir: Path) -> str | None:
    """Return the run's creation time (ISO-8601 UTC) from its timestamp slug."""
    created = parse_utc_timestamp_slug(run_dir.name)
    return created.isoformat() if created else None
