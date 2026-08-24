"""Serialisable snapshot of retrieved search results for history persistence.

A :class:`StoredResult` is a plain, JSON-friendly copy of a retrieved chunk
(source, score, text, metadata) so the Step 3/4 history records can embed the
exact hits a query returned and later re-render them. Kept free of ``rag_engine``
so the history I/O modules stay lightweight; ``rag_ui.chunks_from_stored``
rebuilds ``RetrievedChunk`` objects for the shared result-card renderer.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

__all__ = [
    "StoredResult",
    "stored_results",
    "stored_results_from_payload",
]


class _ChunkLike(Protocol):
    """The subset of ``RetrievedChunk`` a snapshot copies (duck-typed, import-free)."""

    text: str
    source: str
    score: float
    metadata: dict[str, str]


@dataclass(frozen=True)
class StoredResult:
    """A JSON-friendly copy of one retrieved chunk, embedded in a history record."""

    source: str
    score: float
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


def stored_results(chunks: Sequence[_ChunkLike]) -> tuple[StoredResult, ...]:
    """Copy retrieved chunks into serialisable :class:`StoredResult` snapshots."""
    return tuple(
        StoredResult(
            source=chunk.source,
            score=float(chunk.score),
            text=chunk.text,
            metadata=dict(chunk.metadata),
        )
        for chunk in chunks
    )


def _stored_result_from_payload(payload: object) -> StoredResult | None:
    if not isinstance(payload, dict):
        return None
    try:
        metadata = payload.get("metadata")
        return StoredResult(
            source=str(payload.get("source", "")),
            score=float(payload.get("score", 0.0)),
            text=str(payload.get("text", "")),
            metadata=(
                {str(key): str(value) for key, value in metadata.items()}
                if isinstance(metadata, dict)
                else {}
            ),
        )
    except (TypeError, ValueError):
        return None


def stored_results_from_payload(payload: object) -> tuple[StoredResult, ...]:
    """Rebuild the results list from a parsed JSONL value, skipping bad entries."""
    if not isinstance(payload, (list, tuple)):
        return ()
    parsed = (_stored_result_from_payload(item) for item in payload)
    return tuple(item for item in parsed if item is not None)
