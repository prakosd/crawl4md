"""Per-session Conversational RAG (Step 5) history stored as a downloadable log.

Every turn appends a :class:`ConversationalTurnRecord` to
``conversational_rag_history/conversational_rag_history.jsonl`` inside the browser
session's output folder, with a companion CSV for download. Like
:mod:`basic_rag_qa_history`, this module is pure I/O and parsing (no Streamlit)
so the page stays thin and the logic is unit-testable. Records are capped at the
most recent :data:`_MAX_RECORDS`.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from artifact_store.naming import CONVERSATIONAL_RAG_FOLDER_PREFIX

from app_support.rag_shared.result_snapshot import StoredResult, stored_results_from_payload

__all__ = [
    "CONVERSATIONAL_RAG_HISTORY_DIRNAME",
    "ConversationalTurnRecord",
    "append_conversational_rag_record",
    "conversational_rag_history_dir",
    "load_conversational_rag_history",
    "set_conversational_rag_pinned",
]

# One folder per session holds the accumulating history.
CONVERSATIONAL_RAG_HISTORY_DIRNAME = f"{CONVERSATIONAL_RAG_FOLDER_PREFIX}history"
_HISTORY_FILE = "conversational_rag_history.jsonl"
_HISTORY_CSV = "conversational_rag_history.csv"
_MAX_RECORDS = 200
_LIST_SEPARATOR = "; "
_CSV_COLUMNS = (
    "timestamp_utc",
    "index_folder",
    "index_run",
    "embedding_model",
    "llm_model",
    "aux_model",
    "reranker",
    "raw_question",
    "sub_questions",
    "answer",
    "plan_seconds",
    "retrieve_seconds",
    "rerank_seconds",
    "answer_seconds",
    "followups_seconds",
    "state_seconds",
    "total_seconds",
    "follow_ups_shown",
    "follow_ups_dropped",
    "pinned",
)


@dataclass(frozen=True)
class ConversationalTurnRecord:
    """One Step 5 turn: the question, how it was planned/ranked, and its answer."""

    timestamp_utc: str
    index_folder: str
    index_run: str
    embedding_model: str
    llm_model: str
    aux_model: str
    reranker: str
    raw_question: str
    sub_questions: tuple[str, ...]
    answer: str
    plan_seconds: float = 0.0
    retrieve_seconds: float = 0.0
    rerank_seconds: float = 0.0
    answer_seconds: float = 0.0
    followups_seconds: float = 0.0
    state_seconds: float = 0.0
    total_seconds: float = 0.0
    results: tuple[StoredResult, ...] = ()
    follow_ups_shown: tuple[str, ...] = ()
    follow_ups_dropped: tuple[str, ...] = ()
    pinned: bool = False


def conversational_rag_history_dir(session_root: Path | str) -> Path:
    """Return the per-session ``conversational_rag_history/`` folder path."""
    return Path(session_root) / CONVERSATIONAL_RAG_HISTORY_DIRNAME


def load_conversational_rag_history(session_root: Path | str) -> list[ConversationalTurnRecord]:
    """Return saved records pinned-first, then newest-first, skipping malformed lines."""
    records = _read_records(conversational_rag_history_dir(session_root) / _HISTORY_FILE)
    records.reverse()
    records.sort(key=lambda record: not record.pinned)  # stable: pinned first, keep date order
    return records


def append_conversational_rag_record(
    session_root: Path | str, record: ConversationalTurnRecord
) -> None:
    """Append *record*, keep only the most recent records, and refresh the CSV."""
    directory = conversational_rag_history_dir(session_root)
    directory.mkdir(parents=True, exist_ok=True)
    records = _read_records(directory / _HISTORY_FILE)
    records.append(record)
    kept = records[-_MAX_RECORDS:]
    _write_jsonl(directory / _HISTORY_FILE, kept)
    _write_csv(directory / _HISTORY_CSV, kept)


def set_conversational_rag_pinned(
    session_root: Path | str, timestamp_utc: str, pinned: bool
) -> None:
    """Set the pinned flag on the record(s) matching *timestamp_utc* and rewrite the log."""
    directory = conversational_rag_history_dir(session_root)
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


def _read_records(path: Path) -> list[ConversationalTurnRecord]:
    if not path.is_file():
        return []
    records: list[ConversationalTurnRecord] = []
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


def _write_jsonl(path: Path, records: list[ConversationalTurnRecord]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False))
            handle.write("\n")


def _write_csv(path: Path, records: list[ConversationalTurnRecord]) -> None:
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
                    record.llm_model,
                    record.aux_model,
                    record.reranker,
                    record.raw_question,
                    _LIST_SEPARATOR.join(record.sub_questions),
                    record.answer,
                    f"{record.plan_seconds:.2f}",
                    f"{record.retrieve_seconds:.2f}",
                    f"{record.rerank_seconds:.2f}",
                    f"{record.answer_seconds:.2f}",
                    f"{record.followups_seconds:.2f}",
                    f"{record.state_seconds:.2f}",
                    f"{record.total_seconds:.2f}",
                    _LIST_SEPARATOR.join(record.follow_ups_shown),
                    _LIST_SEPARATOR.join(record.follow_ups_dropped),
                    record.pinned,
                ]
            )


def _str_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def _record_from_payload(payload: object) -> ConversationalTurnRecord | None:
    if not isinstance(payload, dict):
        return None
    try:
        return ConversationalTurnRecord(
            timestamp_utc=str(payload["timestamp_utc"]),
            index_folder=str(payload.get("index_folder", "")),
            index_run=str(payload.get("index_run", "")),
            embedding_model=str(payload.get("embedding_model", "")),
            llm_model=str(payload.get("llm_model", "")),
            aux_model=str(payload.get("aux_model", "")),
            reranker=str(payload.get("reranker", "")),
            raw_question=str(payload["raw_question"]),
            sub_questions=_str_tuple(payload.get("sub_questions")),
            answer=str(payload.get("answer", "")),
            plan_seconds=float(payload.get("plan_seconds", 0.0)),
            retrieve_seconds=float(payload.get("retrieve_seconds", 0.0)),
            rerank_seconds=float(payload.get("rerank_seconds", 0.0)),
            answer_seconds=float(payload.get("answer_seconds", 0.0)),
            followups_seconds=float(payload.get("followups_seconds", 0.0)),
            state_seconds=float(payload.get("state_seconds", 0.0)),
            total_seconds=float(payload.get("total_seconds", 0.0)),
            results=stored_results_from_payload(payload.get("results")),
            follow_ups_shown=_str_tuple(payload.get("follow_ups_shown")),
            follow_ups_dropped=_str_tuple(payload.get("follow_ups_dropped")),
            pinned=bool(payload.get("pinned", False)),
        )
    except (KeyError, TypeError, ValueError):
        return None
