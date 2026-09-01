from __future__ import annotations

from pathlib import Path

from app_support.conversational_rag.conversational_rag_history import (
    CONVERSATIONAL_RAG_HISTORY_DIRNAME,
    ConversationalTurnRecord,
    append_conversational_rag_record,
    load_conversational_rag_history,
    set_conversational_rag_pinned,
)
from app_support.rag_shared.result_snapshot import StoredResult


def _record(
    timestamp: str = "2026-09-01T00:00:00Z", raw_question: str = "q", pinned: bool = False
) -> ConversationalTurnRecord:
    return ConversationalTurnRecord(
        timestamp_utc=timestamp,
        index_folder="vector_01_x",
        index_run="2026",
        embedding_model="titan",
        llm_model="nova",
        aux_model="nova-micro",
        reranker="off",
        raw_question=raw_question,
        sub_questions=("q",),
        answer="A",
        results=(StoredResult(source="a.md", score=0.9, text="c"),),
        follow_ups_shown=("f1",),
        follow_ups_dropped=("f2",),
        pinned=pinned,
    )


def test_append_and_load_round_trip_newest_first(tmp_path: Path) -> None:
    append_conversational_rag_record(tmp_path, _record(timestamp="t1", raw_question="first"))
    append_conversational_rag_record(tmp_path, _record(timestamp="t2", raw_question="second"))

    records = load_conversational_rag_history(tmp_path)

    assert [record.raw_question for record in records] == ["second", "first"]
    csv_path = tmp_path / CONVERSATIONAL_RAG_HISTORY_DIRNAME / "conversational_rag_history.csv"
    assert csv_path.is_file()


def test_results_and_followups_persist(tmp_path: Path) -> None:
    append_conversational_rag_record(tmp_path, _record())

    record = load_conversational_rag_history(tmp_path)[0]

    assert record.sub_questions == ("q",)
    assert record.results[0].text == "c"
    assert record.follow_ups_shown == ("f1",)
    assert record.follow_ups_dropped == ("f2",)


def test_pinned_records_sort_first(tmp_path: Path) -> None:
    append_conversational_rag_record(tmp_path, _record(timestamp="t1", raw_question="old"))
    append_conversational_rag_record(tmp_path, _record(timestamp="t2", raw_question="new"))

    set_conversational_rag_pinned(tmp_path, "t1", True)
    records = load_conversational_rag_history(tmp_path)

    assert records[0].raw_question == "old"  # pinned sorts first
    assert records[0].pinned is True


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    directory = tmp_path / CONVERSATIONAL_RAG_HISTORY_DIRNAME
    directory.mkdir(parents=True)
    (directory / "conversational_rag_history.jsonl").write_text("not json\n", encoding="utf-8")

    assert load_conversational_rag_history(tmp_path) == []
