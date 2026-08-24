from __future__ import annotations

from pathlib import Path

from app_support.basic_rag_qa.basic_rag_qa_history import (
    BASIC_QA_HISTORY_DIRNAME,
    BasicQaRecord,
    append_basic_rag_qa_record,
    basic_rag_qa_template_path,
    load_basic_rag_qa_history,
    load_basic_rag_qa_template,
    reset_basic_rag_qa_template,
    save_basic_rag_qa_template,
    set_basic_rag_qa_pinned,
)
from app_support.rag_shared.result_snapshot import StoredResult


def _record(**overrides: object) -> BasicQaRecord:
    base: dict[str, object] = {
        "timestamp_utc": "2026-07-04T10:00:00+00:00",
        "index_folder": "vector_1",
        "index_run": "2026-07-04_10-00-00",
        "embedding_model": "titan",
        "llm_model": "echo",
        "tone": "Neutral",
        "top_k": 5,
        "question": "What is X?",
        "prompt": "You are a retrieval-augmented AI assistant. …",
        "answer": "X is the answer.",
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
        "latency_seconds": 1.23,
    }
    base.update(overrides)
    return BasicQaRecord(**base)  # type: ignore[arg-type]


def test_append_and_load_round_trip_newest_first(tmp_path: Path) -> None:
    append_basic_rag_qa_record(tmp_path, _record(question="first"))
    append_basic_rag_qa_record(tmp_path, _record(question="second"))

    records = load_basic_rag_qa_history(tmp_path)

    assert [record.question for record in records] == ["second", "first"]
    assert (tmp_path / BASIC_QA_HISTORY_DIRNAME / "basic_rag_qa_history.csv").is_file()


def test_optional_tokens_round_trip_as_none(tmp_path: Path) -> None:
    append_basic_rag_qa_record(
        tmp_path, _record(input_tokens=None, output_tokens=None, total_tokens=None)
    )

    record = load_basic_rag_qa_history(tmp_path)[0]

    assert record.input_tokens is None
    assert record.total_tokens is None
    assert record.latency_seconds == 1.23


def test_answer_round_trips(tmp_path: Path) -> None:
    append_basic_rag_qa_record(tmp_path, _record(answer="Because it is grounded."))

    record = load_basic_rag_qa_history(tmp_path)[0]

    assert record.answer == "Because it is grounded."


def test_search_time_and_results_round_trip(tmp_path: Path) -> None:
    results = (
        StoredResult(source="a.md", score=0.88, text="alpha", metadata={"chunk_index": "0"}),
    )
    append_basic_rag_qa_record(tmp_path, _record(search_seconds=0.42, results=results))

    record = load_basic_rag_qa_history(tmp_path)[0]

    assert record.search_seconds == 0.42
    assert record.results == results
    assert record.results[0].text == "alpha"


def test_pinned_records_sort_first(tmp_path: Path) -> None:
    append_basic_rag_qa_record(
        tmp_path, _record(question="a", timestamp_utc="2026-07-04T10:00:00+00:00")
    )
    append_basic_rag_qa_record(
        tmp_path, _record(question="b", timestamp_utc="2026-07-04T10:00:01+00:00")
    )
    append_basic_rag_qa_record(
        tmp_path, _record(question="c", timestamp_utc="2026-07-04T10:00:02+00:00")
    )

    set_basic_rag_qa_pinned(tmp_path, "2026-07-04T10:00:00+00:00", True)

    history = load_basic_rag_qa_history(tmp_path)
    assert history[0].question == "a"
    assert history[0].pinned is True
    assert [record.question for record in history[1:]] == ["c", "b"]


def test_load_skips_malformed_lines(tmp_path: Path) -> None:
    directory = tmp_path / BASIC_QA_HISTORY_DIRNAME
    directory.mkdir(parents=True)
    (directory / "basic_rag_qa_history.jsonl").write_text("not json\n", encoding="utf-8")

    assert load_basic_rag_qa_history(tmp_path) == []


def test_load_empty_when_no_history(tmp_path: Path) -> None:
    assert load_basic_rag_qa_history(tmp_path) == []


# Risk: the Edit-template editor persists a per-session template; Generate must
# read back exactly what was saved. Verify the round trip + it lands in the
# history folder (so it shows in Files & folders). Type: unit.
def test_template_save_load_round_trip(tmp_path: Path) -> None:
    template = "You are X. {question} {start}{knowledge}{end} {tone}"
    assert load_basic_rag_qa_template(tmp_path) is None

    save_basic_rag_qa_template(tmp_path, template)

    assert load_basic_rag_qa_template(tmp_path) == template
    assert (tmp_path / BASIC_QA_HISTORY_DIRNAME / "prompt_template.txt").is_file()


# Risk: Reset to default must drop the saved template so the default returns, and
# must not error when nothing is saved. Type: unit.
def test_template_reset_removes_saved(tmp_path: Path) -> None:
    save_basic_rag_qa_template(tmp_path, "custom {question}{start}{knowledge}{end}{tone}")

    reset_basic_rag_qa_template(tmp_path)

    assert load_basic_rag_qa_template(tmp_path) is None
    reset_basic_rag_qa_template(tmp_path)  # idempotent when already absent


# Risk: a whitespace-only saved template would blank the prompt; loading must treat
# it as unset so the default applies. Type: unit.
def test_template_blank_saved_reads_as_none(tmp_path: Path) -> None:
    save_basic_rag_qa_template(tmp_path, "   \n")

    assert load_basic_rag_qa_template(tmp_path) is None
    assert basic_rag_qa_template_path(tmp_path).exists()
