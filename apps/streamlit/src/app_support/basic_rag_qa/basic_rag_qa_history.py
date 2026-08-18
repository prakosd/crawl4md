"""Per-session Basic RAG Q&A history stored as a downloadable log.

Every prompt sent on Step 4 appends a :class:`BasicQaRecord` to
``basic_rag_qa_history/basic_rag_qa_history.jsonl`` inside the browser session's output folder,
with a companion CSV for easy download. Like :mod:`search_history`, this module
is pure I/O and parsing (no Streamlit dependency) so the page stays thin and the
logic is unit-testable. Records are capped at the most recent :data:`_MAX_RECORDS`.
"""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from artifact_store.naming import BASIC_RAG_QA_FOLDER_PREFIX

__all__ = [
    "BASIC_QA_HISTORY_DIRNAME",
    "BasicQaRecord",
    "append_basic_rag_qa_record",
    "basic_rag_qa_history_dir",
    "basic_rag_qa_template_path",
    "load_basic_rag_qa_history",
    "load_basic_rag_qa_template",
    "reset_basic_rag_qa_template",
    "save_basic_rag_qa_template",
    "set_basic_rag_qa_pinned",
]

# One folder per session holds the accumulating history. The basic_rag_qa_ prefix gives
# it a Q&A icon in the download tree (generated_files.download_folder_icon).
BASIC_QA_HISTORY_DIRNAME = f"{BASIC_RAG_QA_FOLDER_PREFIX}history"
_HISTORY_FILE = "basic_rag_qa_history.jsonl"
_HISTORY_CSV = "basic_rag_qa_history.csv"
# The Edit-template editor saves the user's prompt template here, inside the same
# per-session folder so it shows up (and downloads) in the Files & folders panel.
_TEMPLATE_FILE = "prompt_template.txt"
_MAX_RECORDS = 200
_CSV_COLUMNS = (
    "timestamp_utc",
    "index_folder",
    "index_run",
    "embedding_model",
    "llm_model",
    "tone",
    "top_k",
    "question",
    "prompt",
    "answer",
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "latency_seconds",
    "pinned",
)


@dataclass(frozen=True)
class BasicQaRecord:
    """One Step 4 request: the prompt sent, against which index, and its cost."""

    timestamp_utc: str
    index_folder: str
    index_run: str
    embedding_model: str
    llm_model: str
    tone: str
    top_k: int
    question: str
    prompt: str
    answer: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    latency_seconds: float = 0.0
    pinned: bool = False


def basic_rag_qa_history_dir(session_root: Path | str) -> Path:
    """Return the per-session ``basic_rag_qa_history/`` folder path."""
    return Path(session_root) / BASIC_QA_HISTORY_DIRNAME


def basic_rag_qa_template_path(session_root: Path | str) -> Path:
    """Return the per-session saved prompt-template file path."""
    return basic_rag_qa_history_dir(session_root) / _TEMPLATE_FILE


def load_basic_rag_qa_template(session_root: Path | str) -> str | None:
    """Return the session's saved prompt template, or ``None`` when unset/empty."""
    try:
        text = basic_rag_qa_template_path(session_root).read_text(encoding="utf-8")
    except OSError:
        return None
    return text if text.strip() else None


def save_basic_rag_qa_template(session_root: Path | str, template: str) -> None:
    """Persist *template* as this session's prompt template."""
    directory = basic_rag_qa_history_dir(session_root)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / _TEMPLATE_FILE).write_text(template, encoding="utf-8")


def reset_basic_rag_qa_template(session_root: Path | str) -> None:
    """Remove the session's saved prompt template, reverting to the default."""
    basic_rag_qa_template_path(session_root).unlink(missing_ok=True)


def load_basic_rag_qa_history(session_root: Path | str) -> list[BasicQaRecord]:
    """Return saved records pinned-first, then newest-first, skipping malformed lines."""
    records = _read_records(basic_rag_qa_history_dir(session_root) / _HISTORY_FILE)
    records.reverse()
    records.sort(key=lambda record: not record.pinned)  # stable: pinned first, keep date order
    return records


def append_basic_rag_qa_record(session_root: Path | str, record: BasicQaRecord) -> None:
    """Append *record*, keep only the most recent records, and refresh the CSV."""
    directory = basic_rag_qa_history_dir(session_root)
    directory.mkdir(parents=True, exist_ok=True)
    records = _read_records(directory / _HISTORY_FILE)
    records.append(record)
    kept = records[-_MAX_RECORDS:]
    _write_jsonl(directory / _HISTORY_FILE, kept)
    _write_csv(directory / _HISTORY_CSV, kept)


def set_basic_rag_qa_pinned(session_root: Path | str, timestamp_utc: str, pinned: bool) -> None:
    """Set the pinned flag on the record(s) matching *timestamp_utc* and rewrite the log.

    Records are keyed by their second-precision timestamp; a same-second collision
    (two sends within one second) would flip both, which is harmless.
    """
    directory = basic_rag_qa_history_dir(session_root)
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


def _read_records(path: Path) -> list[BasicQaRecord]:
    if not path.is_file():
        return []
    records: list[BasicQaRecord] = []
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


def _write_jsonl(path: Path, records: list[BasicQaRecord]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False))
            handle.write("\n")


def _write_csv(path: Path, records: list[BasicQaRecord]) -> None:
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
                    record.tone,
                    record.top_k,
                    record.question,
                    record.prompt,
                    record.answer,
                    "" if record.input_tokens is None else record.input_tokens,
                    "" if record.output_tokens is None else record.output_tokens,
                    "" if record.total_tokens is None else record.total_tokens,
                    f"{record.latency_seconds:.2f}",
                    record.pinned,
                ]
            )


def _optional_int(value: object) -> int | None:
    return None if value in (None, "") else int(value)


def _record_from_payload(payload: object) -> BasicQaRecord | None:
    if not isinstance(payload, dict):
        return None
    try:
        return BasicQaRecord(
            timestamp_utc=str(payload["timestamp_utc"]),
            index_folder=str(payload.get("index_folder", "")),
            index_run=str(payload.get("index_run", "")),
            embedding_model=str(payload.get("embedding_model", "")),
            llm_model=str(payload.get("llm_model", "")),
            tone=str(payload.get("tone", "")),
            top_k=int(payload.get("top_k", 0)),
            question=str(payload.get("question", "")),
            prompt=str(payload["prompt"]),
            answer=str(payload.get("answer", "")),
            input_tokens=_optional_int(payload.get("input_tokens")),
            output_tokens=_optional_int(payload.get("output_tokens")),
            total_tokens=_optional_int(payload.get("total_tokens")),
            latency_seconds=float(payload.get("latency_seconds", 0.0)),
            pinned=bool(payload.get("pinned", False)),
        )
    except (KeyError, TypeError, ValueError):
        return None
