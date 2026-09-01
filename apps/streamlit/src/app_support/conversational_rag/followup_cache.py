"""In-session cache of validated follow-ups keyed by their exact question text.

A follow-up button inserts the *identical* question string that was validated,
so an exact-match lookup returns the pre-fetched chunks and the next turn skips
retrieval entirely. Pure Python (no Streamlit): the page owns the session-state
dict; this module owns the logic and stays unit-testable.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from rag_engine import RetrievedChunk, ValidatedFollowup

__all__ = ["get_cached_chunks", "replace_followups"]


def replace_followups(
    cache: dict[str, list[RetrievedChunk]], follow_ups: Sequence[ValidatedFollowup]
) -> None:
    """Replace the cache wholesale with the latest turn's validated follow-ups.

    Replacing (not accumulating) keeps session state bounded and drops chunks
    from an index the user has since switched away from.
    """
    cache.clear()
    for item in follow_ups:
        cache[item.question] = list(item.chunks)


def get_cached_chunks(
    cache: Mapping[str, list[RetrievedChunk]], question: str
) -> list[RetrievedChunk] | None:
    """Return the pre-validated chunks for *question*, or ``None`` on a miss.

    Matching is exact by design: only a clicked suggestion (which re-inserts the
    identical validated string) hits; a hand-typed variant misses and takes the
    normal retrieval path.
    """
    chunks = cache.get(question)
    return list(chunks) if chunks is not None else None
