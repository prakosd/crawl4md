"""Per-session semantic-search history stored as a downloadable log.

Every search on Step 3 appends a :class:`SearchRecord` to
``search_history/search_history.jsonl`` inside the browser session's output
folder, with a companion CSV for easy download. This module is pure I/O and
parsing (no Streamlit dependency) so the page stays thin and the logic is
unit-testable. Records are capped at the most recent :data:`_MAX_RECORDS` to keep
the file bounded.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from artifact_store.naming import SEARCH_FOLDER_PREFIX

from app_support.rag_shared.result_snapshot import StoredResult, stored_results_from_payload

__all__ = [
    "SEARCH_HISTORY_DIRNAME",
    "SearchRecord",
    "append_search_record",
    "load_search_history",
    "search_history_dir",
    "set_search_pinned",
]

# One folder per session holds the accumulating history. The search_ prefix gives
# it a magnifier icon in the download tree (generated_files.download_folder_icon).
SEARCH_HISTORY_DIRNAME = f"{SEARCH_FOLDER_PREFIX}history"
_HISTORY_FILE = "search_history.jsonl"
_HISTORY_CSV = "search_history.csv"
_MAX_RECORDS = 200
_CSV_COLUMNS = (
    "timestamp_utc",
    "index_folder",
    "index_run",
    "embedding_model",
    "query",
    "top_k",
    "result_count",
    "search_seconds",
    "top_score",
    "pinned",
)


@dataclass(frozen=True)
class SearchRecord:
    """One semantic search: what was asked, against which index, with what result."""

    timestamp_utc: str
    index_folder: str
    index_run: str
    embedding_model: str
    query: str
    top_k: int
    result_count: int = 0
    top_score: float | None = None
    search_seconds: float | None = None
    results: tuple[StoredResult, ...] = ()
    pinned: bool = False


def search_history_dir(session_root: Path | str) -> Path:
    """Return the per-session ``search_history/`` folder path."""
    return Path(session_root) / SEARCH_HISTORY_DIRNAME


def load_search_history(session_root: Path | str) -> list[SearchRecord]:
    """Return saved records pinned-first, then newest-first, skipping malformed lines."""
    records = _read_records(search_history_dir(session_root) / _HISTORY_FILE)
    records.reverse()
    records.sort(key=lambda record: not record.pinned)  # stable: pinned first, keep date order
    return records


def append_search_record(session_root: Path | str, record: SearchRecord) -> None:
    """Append *record*, keep only the most recent records, and refresh the CSV."""
    directory = search_history_dir(session_root)
    directory.mkdir(parents=True, exist_ok=True)
    records = _read_records(directory / _HISTORY_FILE)
    records.append(record)
    kept = records[-_MAX_RECORDS:]
    _write_jsonl(directory / _HISTORY_FILE, kept)
    _write_csv(directory / _HISTORY_CSV, kept)


def set_search_pinned(session_root: Path | str, timestamp_utc: str, pinned: bool) -> None:
    """Set the pinned flag on the record(s) matching *timestamp_utc* and rewrite the log.

    Records are keyed by their second-precision timestamp; a same-second collision
    (two searches within one second) would flip both, which is harmless.
    """
    directory = search_history_dir(session_root)
    path = directory / _HISTORY_FILE
    records = _read_records(path)
    changed = False
    for index, record in enumerate(records):
        if record.timestamp_utc == timestamp_utc and record.pinned != pinned:
            records[index] = replace(record, pinned=pinned)
            changed = True
    if changed:
        _write_jsonl(path, records)
        _write_csv(directory / _HISTORY_CSV, records)


def _read_records(path: Path) -> list[SearchRecord]:
    if not path.is_file():
        return []
    records: list[SearchRecord] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        record = _record_from_payload(payload)
        if record is not None:
            records.append(record)
    return records


def _write_jsonl(path: Path, records: list[SearchRecord]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False))
            handle.write("\n")


def _write_csv(path: Path, records: list[SearchRecord]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_CSV_COLUMNS)
        for record in records:
            writer.writerow(
                [
                    record.timestamp_utc,
                    record.index_folder,
                    record.index_run,
                    record.embedding_model,
                    record.query,
                    record.top_k,
                    record.result_count,
                    "" if record.search_seconds is None else f"{record.search_seconds:.2f}",
                    "" if record.top_score is None else f"{record.top_score:.4f}",
                    record.pinned,
                ]
            )


def _record_from_payload(payload: object) -> SearchRecord | None:
    if not isinstance(payload, dict):
        return None
    try:
        top_score = payload.get("top_score")
        search_seconds = payload.get("search_seconds")
        return SearchRecord(
            timestamp_utc=str(payload["timestamp_utc"]),
            index_folder=str(payload.get("index_folder", "")),
            index_run=str(payload.get("index_run", "")),
            embedding_model=str(payload.get("embedding_model", "")),
            query=str(payload["query"]),
            top_k=int(payload.get("top_k", 0)),
            result_count=int(payload.get("result_count", 0)),
            top_score=None if top_score in (None, "") else float(top_score),
            search_seconds=None if search_seconds in (None, "") else float(search_seconds),
            results=stored_results_from_payload(payload.get("results")),
            pinned=bool(payload.get("pinned", False)),
        )
    except (KeyError, TypeError, ValueError):
        return None
