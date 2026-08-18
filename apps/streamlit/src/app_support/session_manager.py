"""Session and path helpers for the crawl4md Streamlit app."""

from __future__ import annotations

import os
import secrets
import shutil
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Literal

from artifact_store.naming import (
    VECTOR_FOLDER_PREFIX,
    folder_name,
    format_sequence_id,
    parse_folder_sequence,
)
from artifact_store.paths import ensure_within_root as ensure_within_root
from crawl4md.naming import (
    CRAWL_FOLDER_PREFIX,
    crawl_folder_name,
    format_crawl_id,
    parse_crawl_folder_sequence,
)
from log4py import get_logger

_logger = get_logger(__name__)

_CLEANUP_LOCK_FILE = ".cleanup.lock"
_CLEANUP_LOG_FILE = "cleanup.log"
_CRAWL_PREFIX = CRAWL_FOLDER_PREFIX
_DEFAULT_RETENTION_DAYS = 7
_DEFAULT_SESSIONS_ROOT = Path("outputs") / "streamlit_sessions"
_ID_BYTES = 9
_READABLE_CRAWL_WORD_COUNT = 1
# --- Readable session ID pattern (edit these two to change the format) ---
# _READABLE_SESSION_WORD_COUNT — number of EFF words per session ID (≥1)
# _READABLE_ID_DIGITS          — digits appended after words; 0 = words only
#
# Examples:
#   2 words only  → WORD_COUNT=2, DIGITS=0  → "boulder_river"
#   4 words + 6d  → WORD_COUNT=4, DIGITS=6  → "stone_apple_river_oak_482917"
#   1 word + 2d   → WORD_COUNT=1, DIGITS=2  → "cedar_07"
#   legacy token  → set _USE_READABLE_IDS = False (ignores counts above)
# -------------------------------------------------------------------------
_READABLE_ID_DIGITS = 0
_READABLE_ID_LIMIT = 10**_READABLE_ID_DIGITS
_READABLE_SESSION_WORD_COUNT = 2
# EFF large wordlist — Creative Commons Attribution 4.0 International (CC-BY 4.0).
# Wordlist provided by the Electronic Frontier Foundation (eff.org).
# Source: https://www.eff.org/files/2016/07/18/eff_large_wordlist.txt
_EFF_WORDLIST_PACKAGE = "app_support"
_EFF_WORDLIST_RESOURCE = ("data", "eff_large_wordlist.txt")
_EFF_WORDLIST_SIZE = 7776
_LOCK_STALE_SECONDS = 60 * 60
_SECONDS_PER_DAY = 86400
_SECONDS_PER_HOUR = 3600
_SESSION_PREFIX = "session_"
_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"
_USE_READABLE_IDS = True

DEFAULT_SESSIONS_ROOT = _DEFAULT_SESSIONS_ROOT
SESSION_DIR_PREFIX = _SESSION_PREFIX  # public: session folders are "session_<id>"
DEFAULT_SESSION_LANGUAGE = "EN"
SESSION_PREFIX = _SESSION_PREFIX

_SAFE_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_-")
_SAFE_WORD_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz-")
_SESSION_CREATED_AT_FIELD = "created_at"
_SESSION_ID_FIELD = "session_id"
_SESSION_LANGUAGE_FIELD = "language"
_SESSION_RECORDS_FIELD = "sessions"
_DEFAULT_SESSION_LANGUAGE = DEFAULT_SESSION_LANGUAGE
_SUPPORTED_LANGUAGES = frozenset({DEFAULT_SESSION_LANGUAGE, "ID"})


@dataclass(frozen=True)
class SessionRecord:
    """A browser-persisted Streamlit session entry."""

    session_id: str
    created_at: datetime
    language: str = _DEFAULT_SESSION_LANGUAGE


def _normalize_language(value: object) -> str:
    normalized = str(value).strip().upper() if isinstance(value, str) else ""
    return normalized if normalized in _SUPPORTED_LANGUAGES else _DEFAULT_SESSION_LANGUAGE


def bootstrap_gate_state(
    *,
    browser_sessions_hydrated: bool,
    pending_bootstrap_session_id: str,
    session_storage_write_failed: bool,
) -> Literal["hydrating", "storing", "storage_error", "ready"]:
    """Return the current browser-session bootstrap gate state for the UI."""
    if not browser_sessions_hydrated:
        return "hydrating"
    if pending_bootstrap_session_id:
        return "storage_error" if session_storage_write_failed else "storing"
    return "ready"


def should_show_portfolio_modal(
    *,
    browser_sessions_hydrated: bool,
    last_dismissed_at: str | None,
    repeat_after_hours: int,
    now: datetime | None = None,
) -> bool:
    """Return whether the portfolio modal may be scheduled in the browser."""
    if not browser_sessions_hydrated:
        return False

    dismissed_at = _parse_utc_timestamp(last_dismissed_at)
    if dismissed_at is None:
        return True

    current_time = _normalize_utc_datetime(now or datetime.now(timezone.utc))
    return current_time - dismissed_at >= timedelta(hours=repeat_after_hours)


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return _normalize_utc_datetime(parsed)


def _normalize_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def _readable_word_pool() -> tuple[str, ...]:
    try:
        resource = resources.files(_EFF_WORDLIST_PACKAGE).joinpath(*_EFF_WORDLIST_RESOURCE)
        lines = resource.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ValueError("EFF word list resource is missing.") from exc

    words = tuple(_parse_eff_word(line) for line in lines if line.strip())
    if len(words) != _EFF_WORDLIST_SIZE:
        raise ValueError("EFF word list size is unexpected.")
    return words


def _parse_eff_word(raw_line: str) -> str:
    parts = raw_line.split(maxsplit=1)
    if len(parts) != 2:
        raise ValueError("EFF word list line is malformed.")
    word = parts[1].strip()
    if not word or word != word.lower() or any(char not in _SAFE_WORD_CHARS for char in word):
        raise ValueError("EFF word list contains an unsafe word.")
    return word


def _legacy_safe_id() -> str:
    raw_id = secrets.token_urlsafe(_ID_BYTES).lower()
    return "".join(char if char in _SAFE_ID_CHARS else "_" for char in raw_id)


def _generate_readable_session_id() -> str:
    words = [secrets.choice(_readable_word_pool()) for _ in range(_READABLE_SESSION_WORD_COUNT)]
    if _READABLE_ID_DIGITS > 0:
        digits = f"{secrets.randbelow(_READABLE_ID_LIMIT):0{_READABLE_ID_DIGITS}d}"
        return "_".join([*words, digits])
    return "_".join(words)


def _generate_readable_crawl_suffix() -> str:
    words = [secrets.choice(_readable_word_pool()) for _ in range(_READABLE_CRAWL_WORD_COUNT)]
    return "_".join(words)


def generate_safe_id() -> str:
    """Return a short lowercase ID safe for directory names."""
    if not _USE_READABLE_IDS:
        return _legacy_safe_id()
    return _generate_readable_session_id()


def validate_safe_id(value: str) -> str:
    """Validate an ID before using it in a server-side path."""
    if not value or any(char not in _SAFE_ID_CHARS for char in value):
        raise ValueError("ID contains unsafe characters.")
    return value


def create_session_record(
    session_id: str | None = None,
    *,
    language: str = _DEFAULT_SESSION_LANGUAGE,
    now: datetime | None = None,
) -> SessionRecord:
    """Create a session record with a path-safe ID and UTC creation time."""
    safe_session_id = validate_safe_id(session_id) if session_id is not None else generate_safe_id()
    created_at = now or datetime.now(timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return SessionRecord(
        session_id=safe_session_id,
        created_at=created_at.astimezone(timezone.utc),
        language=_normalize_language(language),
    )


def normalize_session_records(payload: object) -> list[SessionRecord]:
    """Return valid session records from an untrusted browser payload."""
    raw_records = (
        payload.get(_SESSION_RECORDS_FIELD, []) if isinstance(payload, Mapping) else payload
    )
    if isinstance(raw_records, (str, bytes)) or not isinstance(raw_records, Iterable):
        return []

    records_by_id: dict[str, SessionRecord] = {}
    for raw_record in raw_records:
        record = _session_record_from_payload(raw_record)
        if record is None:
            continue
        existing = records_by_id.get(record.session_id)
        if existing is None or record.created_at >= existing.created_at:
            records_by_id[record.session_id] = record
    return sorted(
        records_by_id.values(),
        key=lambda record: (record.created_at, record.session_id),
        reverse=True,
    )


def serialize_session_records(records: Iterable[SessionRecord]) -> list[dict[str, str]]:
    """Serialize session records for browser localStorage."""
    return [
        {
            _SESSION_ID_FIELD: record.session_id,
            _SESSION_CREATED_AT_FIELD: _format_session_created_at(record.created_at),
            _SESSION_LANGUAGE_FIELD: record.language,
        }
        for record in sorted(
            records,
            key=lambda item: (item.created_at, item.session_id),
            reverse=True,
        )
    ]


def latest_session_id(records: Iterable[SessionRecord]) -> str:
    """Return the newest session ID, or an empty string when no records exist."""
    sorted_records = serialize_session_records(records)
    return sorted_records[0][_SESSION_ID_FIELD] if sorted_records else ""


def _session_record_from_payload(payload: object) -> SessionRecord | None:
    if not isinstance(payload, Mapping):
        return None
    session_id = payload.get(_SESSION_ID_FIELD)
    created_at = payload.get(_SESSION_CREATED_AT_FIELD)
    if not isinstance(session_id, str) or not isinstance(created_at, str):
        return None
    try:
        return SessionRecord(
            session_id=validate_safe_id(session_id),
            created_at=_parse_session_created_at(created_at),
            language=_normalize_language(payload.get(_SESSION_LANGUAGE_FIELD)),
        )
    except ValueError:
        return None


def _parse_session_created_at(value: str) -> datetime:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Session creation time is missing.")
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Session creation time is invalid.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_session_created_at(value: datetime) -> str:
    normalized = value
    if normalized.tzinfo is None:
        normalized = normalized.replace(tzinfo=timezone.utc)
    return normalized.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def generate_crawl_id(now: datetime | None = None, *, seq: int | None = None) -> str:
    """Return a crawl ID. With seq, returns a zero-padded '{seq}_{word}' ID."""
    if seq is not None:
        return format_crawl_id(seq, _generate_readable_crawl_suffix())
    timestamp = (now or datetime.now(timezone.utc)).strftime(_TIMESTAMP_FORMAT)
    if not _USE_READABLE_IDS:
        return f"{timestamp}_{_legacy_safe_id()}"
    return f"{timestamp}_{_generate_readable_crawl_suffix()}"


def count_crawl_dirs(sessions_root: Path | str, session_id: str) -> int:
    """Return the number of existing crawl subdirectories in the session folder."""
    sdir = session_dir(sessions_root, session_id)
    if not sdir.is_dir():
        return 0
    return sum(1 for p in sdir.iterdir() if p.is_dir() and p.name.startswith(_CRAWL_PREFIX))


def next_crawl_sequence(sessions_root: Path | str, session_id: str) -> int:
    """Return the next crawl sequence after existing numbered crawl folders."""
    sdir = session_dir(sessions_root, session_id)
    if not sdir.is_dir():
        return 1
    sequences = [
        sequence
        for path in sdir.iterdir()
        if path.is_dir()
        for sequence in [parse_crawl_folder_sequence(path.name)]
        if sequence is not None
    ]
    if not sequences:
        return 1
    return max(sequences) + 1


def session_dir(sessions_root: Path | str, session_id: str) -> Path:
    """Return the directory for one Streamlit browser session."""
    safe_session_id = validate_safe_id(session_id)
    return Path(sessions_root) / f"{_SESSION_PREFIX}{safe_session_id}"


def session_exists(sessions_root: Path | str, session_id: str) -> bool:
    """Return True if the session directory exists; False for any invalid or missing ID."""
    try:
        return session_dir(sessions_root, session_id).is_dir()
    except ValueError:
        return False


def touch_session(sessions_root: Path | str, session_id: str) -> None:
    """Update the session directory mtime to now, resetting its retention clock."""
    session_dir(sessions_root, session_id).touch()


def session_time_remaining(
    sessions_root: Path | str,
    session_id: str,
    *,
    retention_days: int = _DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Return how much time is left before a session is eligible for deletion.

    Returns a (days, hours) pair. *days* is whole days remaining; *hours* is
    the remaining hours after subtracting whole days (0–23). Both are
    floor-rounded so the count never overpromises. If the session directory
    does not exist (e.g. a brand-new session), the full retention period is
    returned with zero remainder hours.
    """
    sdir = session_dir(sessions_root, session_id)
    _now = now or datetime.now(timezone.utc)
    if not sdir.is_dir():
        return (retention_days, 0)
    modified_at = datetime.fromtimestamp(sdir.stat().st_mtime, tz=timezone.utc)
    remaining_seconds = max(
        0.0, (timedelta(days=retention_days) - (_now - modified_at)).total_seconds()
    )
    whole_days = int(remaining_seconds // _SECONDS_PER_DAY)
    remainder_hours = int((remaining_seconds % _SECONDS_PER_DAY) // _SECONDS_PER_HOUR)
    return (whole_days, remainder_hours)


def crawl_output_base(sessions_root: Path | str, session_id: str, crawl_id: str) -> Path:
    """Return the output base directory for one crawl run."""
    safe_crawl_id = validate_safe_id(crawl_id)
    return session_dir(sessions_root, session_id) / crawl_folder_name(safe_crawl_id)


def prepare_session_dir(sessions_root: Path | str, session_id: str) -> Path:
    """Create and return the current Streamlit session directory."""
    path = session_dir(sessions_root, session_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare_crawl_output_base(sessions_root: Path | str, session_id: str, crawl_id: str) -> Path:
    """Create and return the output base for one crawl run."""
    path = crawl_output_base(sessions_root, session_id, crawl_id)
    path.mkdir(parents=True, exist_ok=False)
    return path


def next_vector_sequence(sessions_root: Path | str, session_id: str) -> int:
    """Return the next vector-index sequence after existing numbered folders."""
    sdir = session_dir(sessions_root, session_id)
    if not sdir.is_dir():
        return 1
    sequences = [
        sequence
        for path in sdir.iterdir()
        if path.is_dir()
        for sequence in [parse_folder_sequence(path.name, prefix=VECTOR_FOLDER_PREFIX)]
        if sequence is not None
    ]
    return max(sequences) + 1 if sequences else 1


def generate_vector_id(*, seq: int) -> str:
    """Return a zero-padded '{seq}_{word}' vector-index ID."""
    return format_sequence_id(seq, _generate_readable_crawl_suffix())


def vector_output_base(sessions_root: Path | str, session_id: str, vector_id: str) -> Path:
    """Return the output base directory for one vector-index run."""
    safe_vector_id = validate_safe_id(vector_id)
    return session_dir(sessions_root, session_id) / folder_name(
        VECTOR_FOLDER_PREFIX, safe_vector_id
    )


def prepare_vector_output_base(sessions_root: Path | str, session_id: str, vector_id: str) -> Path:
    """Create and return the output base for one vector-index run."""
    path = vector_output_base(sessions_root, session_id, vector_id)
    path.mkdir(parents=True, exist_ok=False)
    return path


def cleanup_old_sessions(
    sessions_root: Path | str = _DEFAULT_SESSIONS_ROOT,
    *,
    active_session_ids: Iterable[str] = (),
    retention_days: int = _DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> list[Path]:
    """Delete inactive session folders older than the retention period."""
    root = Path(sessions_root)
    if not root.exists():
        return []
    active_ids = {validate_safe_id(session_id) for session_id in active_session_ids}
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    removed: list[Path] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir() or not path.name.startswith(_SESSION_PREFIX):
            continue
        session_id = path.name.removeprefix(_SESSION_PREFIX)
        try:
            validate_safe_id(session_id)
        except ValueError:
            continue
        if session_id in active_ids:
            continue
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if modified_at >= cutoff:
            continue
        shutil.rmtree(path)
        removed.append(path)
    if removed:
        log_path = root / _CLEANUP_LOG_FILE
        timestamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        lines = [f"{timestamp} removed {path.name}" for path in removed]
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
        _logger.info("Session cleanup removed %d inactive session(s)", len(removed))
    return removed


def cleanup_old_sessions_with_lock(
    sessions_root: Path | str = _DEFAULT_SESSIONS_ROOT,
    *,
    active_session_ids: Iterable[str] = (),
    retention_days: int = _DEFAULT_RETENTION_DAYS,
) -> list[Path]:
    """Run cleanup under a lightweight lock file."""
    root = Path(sessions_root)
    if not root.exists():
        return []
    lock_path = root / _CLEANUP_LOCK_FILE
    if _lock_is_stale(lock_path):
        _logger.warning("Removing stale session-cleanup lock file")
        lock_path.unlink(missing_ok=True)
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return []
    try:
        with os.fdopen(lock_fd, "w", encoding="utf-8") as handle:
            handle.write(datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return cleanup_old_sessions(
            root,
            active_session_ids=active_session_ids,
            retention_days=retention_days,
        )
    finally:
        lock_path.unlink(missing_ok=True)


def _lock_is_stale(lock_path: Path) -> bool:
    if not lock_path.exists():
        return False
    modified_at = datetime.fromtimestamp(lock_path.stat().st_mtime, tz=timezone.utc)
    age = datetime.now(timezone.utc) - modified_at
    return age.total_seconds() > _LOCK_STALE_SECONDS
