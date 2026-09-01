"""UI-agnostic artifact naming and timestamp helpers.

This module is the shared source of truth for timestamped, sequence-numbered
artifact directories such as crawl outputs (``crawl_``) and vector indexes
(``vector_``). It must stay free of any UI or crawler dependencies.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from functools import cache

__all__ = [
    "CRAWL_FOLDER_PREFIX",
    "BASIC_RAG_QA_FOLDER_PREFIX",
    "CONVERSATIONAL_RAG_FOLDER_PREFIX",
    "SEARCH_FOLDER_PREFIX",
    "UTC_TIMESTAMP_SLUG_FORMAT",
    "VECTOR_FOLDER_PREFIX",
    "folder_name",
    "format_sequence_id",
    "format_utc_timestamp_slug",
    "parse_folder_sequence",
    "parse_utc_timestamp_slug",
    "sequence_sort_key",
]

CRAWL_FOLDER_PREFIX = "crawl_"
VECTOR_FOLDER_PREFIX = "vector_"
SEARCH_FOLDER_PREFIX = "search_"
BASIC_RAG_QA_FOLDER_PREFIX = "basic_rag_qa_"
CONVERSATIONAL_RAG_FOLDER_PREFIX = "conversational_rag_"
UTC_TIMESTAMP_SLUG_FORMAT = "%Y-%m-%d_%H-%M-%S"

_SEQUENCE_ID_PADDING = 2
_TIMESTAMP_ID_SECOND_PART_LENGTH = 6


def format_sequence_id(sequence: int, suffix: str, *, width: int = _SEQUENCE_ID_PADDING) -> str:
    """Return a zero-padded artifact ID such as ``01_example``."""
    if sequence < 1:
        raise ValueError("Artifact sequence must be at least 1.")
    normalized_suffix = suffix.strip("_")
    if not normalized_suffix:
        raise ValueError("Artifact suffix must not be empty.")
    return f"{sequence:0{width}d}_{normalized_suffix}"


def folder_name(prefix: str, artifact_id: str) -> str:
    """Return the on-disk folder name for an artifact ID under *prefix*."""
    return artifact_id if artifact_id.startswith(prefix) else f"{prefix}{artifact_id}"


@cache
def _sequence_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(rf"^{re.escape(prefix)}(?P<sequence>\d+)(?:_(?P<rest>.*))?$")


def parse_folder_sequence(folder: str, *, prefix: str = CRAWL_FOLDER_PREFIX) -> int | None:
    """Return the numeric sequence from ``<prefix>01_name`` or legacy ``<prefix>1_name``."""
    match = _sequence_pattern(prefix).fullmatch(folder)
    if match is None:
        return None
    rest = match.group("rest") or ""
    rest_first_part = rest.split("_", 1)[0]
    if len(rest_first_part) == _TIMESTAMP_ID_SECOND_PART_LENGTH and rest_first_part.isdigit():
        return None
    try:
        sequence = int(match.group("sequence"))
    except ValueError:
        return None
    return sequence if sequence > 0 else None


def sequence_sort_key(folder: str, *, prefix: str = CRAWL_FOLDER_PREFIX) -> tuple[int, int, str]:
    """Return a key that sorts numbered artifact folders newest-first."""
    sequence = parse_folder_sequence(folder, prefix=prefix)
    if sequence is None:
        return (1, 0, folder.lower())
    return (0, -sequence, folder.lower())


def format_utc_timestamp_slug(value: datetime | None = None) -> str:
    """Return a UTC timestamp slug for artifact output directories."""
    normalized = _normalize_utc_datetime(value or datetime.now(timezone.utc))
    return normalized.strftime(UTC_TIMESTAMP_SLUG_FORMAT)


def parse_utc_timestamp_slug(value: str) -> datetime | None:
    """Parse an artifact timestamp slug as a UTC datetime."""
    try:
        parsed = datetime.strptime(value, UTC_TIMESTAMP_SLUG_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
