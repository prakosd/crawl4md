"""Tests for the Basic RAG Q&A page's pure helpers."""

from __future__ import annotations

import importlib
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest import MonkeyPatch
from rag_engine.models import TokenUsage

from app_support.basic_rag_qa.basic_rag_qa_history import BasicQaRecord
from app_support.i18n import STRINGS_EN

_APP_DIR = Path(__file__).resolve().parents[1]


def _page(monkeypatch: MonkeyPatch):
    monkeypatch.syspath_prepend(str(_APP_DIR))
    return importlib.import_module("app_pages.basic_rag_qa")


def _record(**overrides: object) -> BasicQaRecord:
    values: dict[str, object] = {
        "timestamp_utc": "2026-07-04T10:00:00+00:00",
        "index_folder": "vector_01_weather",
        "index_run": "2026-07-04_09-00-00",
        "embedding_model": "titan",
        "llm_model": "apac.amazon.nova-lite-v1:0",
        "tone": "Neutral",
        "top_k": 5,
        "question": "What is X?",
        "prompt": "You are ...",
        "input_tokens": 120,
        "output_tokens": 45,
        "total_tokens": 165,
        "latency_seconds": 2.34,
    }
    values.update(overrides)
    return BasicQaRecord(**values)  # type: ignore[arg-type]


def test_stats_caption_shows_counts_and_seconds(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    caption = page._stats_caption(STRINGS_EN, TokenUsage(120, 45, 165), 2.34, "Nova Lite")

    assert "Nova Lite" in caption
    assert "120" in caption
    assert "45" in caption
    assert "165" in caption
    assert "2.3s" in caption


def test_stats_caption_shows_na_without_usage(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    caption = page._stats_caption(STRINGS_EN, None, 1.0, "Echo")

    assert "Echo" in caption
    assert STRINGS_EN["BASIC_QA_TOKEN_NA"] in caption
    assert "1.0s" in caption


def test_history_stats_caption_uses_record_fields(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    caption = page._history_stats_caption(STRINGS_EN, _record())

    assert "Amazon Nova Lite" in caption
    assert "120" in caption
    assert "45" in caption
    assert "165" in caption
    assert "2.3s" in caption


def test_tokens_value_uses_na_for_missing_counts(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    value = page._tokens_value(
        STRINGS_EN, _record(input_tokens=None, output_tokens=None, total_tokens=None)
    )

    assert STRINGS_EN["BASIC_QA_TOKEN_NA"] in value


def test_history_grid_includes_model_tone_and_tokens(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    grid = page._history_grid(STRINGS_EN, _record())

    assert "apac.amazon.nova-lite-v1:0" in grid
    assert "Neutral" in grid
    assert "vector_01_weather" in grid
    assert "2026-07-04_09-00-00" in grid
    assert "120 in" in grid
    assert STRINGS_EN["BASIC_QA_HISTORY_LABEL_TIME"] in grid


def test_history_grid_shows_time_breakdown(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    grid = page._history_grid(STRINGS_EN, _record(search_seconds=0.4, latency_seconds=1.2))

    assert "0.4s + 1.2s = 1.6s" in grid  # search + answer = total


def test_apply_replay_repopulates_question_and_prompt(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {}
    monkeypatch.setattr(page.st, "session_state", state)

    page._apply_replay(
        STRINGS_EN, [], asdict(_record(question="Why sky blue?", prompt="FULL PROMPT BODY"))
    )

    assert state[page._QUESTION_KEY] == "Why sky blue?"
    assert state[page._PROMPT_KEY] == "FULL PROMPT BODY"


def test_apply_maximized_prompt_writes_back_closes_and_queues_toast(
    monkeypatch: MonkeyPatch,
) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._PROMPT_MAX_KEY: "edited body", page._MAXIMIZE_OPEN_KEY: True}
    monkeypatch.setattr(page.st, "session_state", state)

    page._apply_and_close_maximized_prompt(STRINGS_EN)

    assert state[page._PROMPT_PENDING_KEY] == "edited body"
    assert state[page._MAXIMIZE_OPEN_KEY] is False
    assert state[page._PAGE_TOAST_KEY] == STRINGS_EN["BASIC_QA_MAXIMIZE_APPLIED_TOAST"]


def test_pricing_dialog_dismiss_clears_flag(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {page._PRICING_DIALOG_OPEN_KEY: True}
    monkeypatch.setattr(page.st, "session_state", state)

    page._on_pricing_dismiss()

    assert state[page._PRICING_DIALOG_OPEN_KEY] is False


def test_save_template_persists_closes_and_queues_toast(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    page = _page(monkeypatch)
    template = page.resolve_basic_rag_qa_prompt_template()
    state: dict[str, object] = {
        page._TEMPLATE_EDIT_KEY: template,
        page._EDIT_TEMPLATE_OPEN_KEY: True,
    }
    monkeypatch.setattr(page.st, "session_state", state)

    page._save_template(STRINGS_EN, tmp_path)

    assert state[page._EDIT_TEMPLATE_OPEN_KEY] is False
    assert state[page._PAGE_TOAST_KEY] == STRINGS_EN["BASIC_QA_TEMPLATE_SAVED_TOAST"]
    assert page.resolve_basic_rag_qa_prompt_template(tmp_path) == template


def test_save_template_rejects_invalid_and_keeps_dialog_open(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    page = _page(monkeypatch)
    state: dict[str, object] = {
        page._TEMPLATE_EDIT_KEY: "bad {bogus}",
        page._EDIT_TEMPLATE_OPEN_KEY: True,
    }
    monkeypatch.setattr(page.st, "session_state", state)

    page._save_template(STRINGS_EN, tmp_path)

    assert state[page._TEMPLATE_INVALID_KEY] is True
    assert state[page._EDIT_TEMPLATE_OPEN_KEY] is True
    assert page._PAGE_TOAST_KEY not in state


def test_reset_template_deletes_closes_and_queues_toast(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    page = _page(monkeypatch)
    custom = "{question} {start} {knowledge} {end} {tone} CUSTOM"
    page.save_basic_rag_qa_template(tmp_path, custom)
    assert page.resolve_basic_rag_qa_prompt_template(tmp_path) == custom
    state: dict[str, object] = {page._EDIT_TEMPLATE_OPEN_KEY: True}
    monkeypatch.setattr(page.st, "session_state", state)

    page._reset_template(STRINGS_EN, tmp_path)

    assert state[page._EDIT_TEMPLATE_OPEN_KEY] is False
    assert state[page._PAGE_TOAST_KEY] == STRINGS_EN["BASIC_QA_TEMPLATE_RESET_TOAST"]
    assert page.resolve_basic_rag_qa_prompt_template(tmp_path) != custom


def test_transaction_rows_are_newest_first_with_process_and_tokens(
    monkeypatch: MonkeyPatch,
) -> None:
    page = _page(monkeypatch)
    older = _record(
        timestamp_utc="2026-07-04T10:00:00+00:00",
        llm_model="model-a",
        input_tokens=100,
        output_tokens=20,
        total_tokens=120,
    )
    newer = _record(
        timestamp_utc="2026-07-04T11:00:00+00:00",
        llm_model="model-b",
        input_tokens=None,
        output_tokens=None,
        total_tokens=None,
    )

    rows = page._transaction_rows(STRINGS_EN, [older, newer])

    assert len(rows) == 2
    assert rows[0][STRINGS_EN["BASIC_QA_HISTORY_META_MODEL"]] == "model-b"
    assert rows[1][STRINGS_EN["BASIC_QA_HISTORY_META_MODEL"]] == "model-a"
    assert (
        rows[0][STRINGS_EN["BASIC_QA_TXN_COL_PROCESS"]] == STRINGS_EN["BASIC_QA_PROCESS_ANSWER_GEN"]
    )
    assert rows[0][STRINGS_EN["BASIC_QA_SUMMARY_INPUT_LABEL"]] == STRINGS_EN["BASIC_QA_TOKEN_NA"]
    assert rows[1][STRINGS_EN["BASIC_QA_SUMMARY_INPUT_LABEL"]] == 100
    assert rows[1][STRINGS_EN["BASIC_QA_SUMMARY_TOTAL_LABEL"]] == 120


def test_transaction_rows_empty_without_records(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    assert page._transaction_rows(STRINGS_EN, []) == []


def test_format_cost_variants(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)

    assert page._format_cost(STRINGS_EN, None) == STRINGS_EN["BASIC_QA_TOKEN_NA"]
    assert page._format_cost(STRINGS_EN, 0.0) == "$0.0000"
    # A positive cost that rounds below the minimum shows the hint, not $0.0000.
    assert page._format_cost(STRINGS_EN, 0.0000189) == STRINGS_EN["BASIC_QA_COST_UNDER_MIN"]
    assert page._format_cost(STRINGS_EN, 0.025) == "$0.0250"
    assert page._format_cost(STRINGS_EN, 1234.5) == "$1,234.5000"


def test_record_and_session_cost_sum_priced_records(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    prices = {"paid": 0.01, "also-paid": 0.02}
    monkeypatch.setattr(page, "estimate_cost", lambda model_id, _in, _out: prices.get(model_id))
    paid = _record(llm_model="paid")
    also = _record(llm_model="also-paid")
    free = _record(llm_model="free")

    assert page._record_cost(paid) == 0.01
    assert page._record_cost(free) is None
    assert page._session_cost([paid, also, free]) == 0.03  # only priced records counted
    assert page._session_cost([free]) is None  # nothing priced -> None
    assert page._session_cost([]) is None


def test_session_direction_costs_split_input_and_output(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    # A direction-aware fake: input tokens cost 1e-6 each, output tokens 2e-6 each.
    monkeypatch.setattr(
        page,
        "estimate_cost",
        lambda model_id, _in, _out: (
            None if model_id == "free" else (_in or 0) * 1e-6 + (_out or 0) * 2e-6
        ),
    )
    rec = _record(llm_model="paid", input_tokens=1000, output_tokens=500)

    assert page._session_input_cost([rec]) == pytest.approx(1000 * 1e-6)
    assert page._session_output_cost([rec]) == pytest.approx(500 * 2e-6)
    # The input and output split sums to the combined session cost.
    assert page._session_cost([rec]) == pytest.approx(
        page._session_input_cost([rec]) + page._session_output_cost([rec])
    )


def test_session_direction_costs_none_when_unpriced(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    monkeypatch.setattr(page, "estimate_cost", lambda model_id, _in, _out: None)
    rec = _record(llm_model="free")

    assert page._session_input_cost([rec]) is None
    assert page._session_output_cost([rec]) is None


def test_transaction_rows_include_provider_cloud_and_cost(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    monkeypatch.setattr(
        page,
        "get_model_price",
        lambda model_id: (
            SimpleNamespace(provider="Amazon", cloud_service="Amazon Bedrock")
            if model_id == "priced"
            else None
        ),
    )
    monkeypatch.setattr(
        page,
        "estimate_cost",
        lambda model_id, _in, _out: 0.0025 if model_id == "priced" else None,
    )
    priced = _record(llm_model="priced")
    free = _record(llm_model="free")

    rows = page._transaction_rows(STRINGS_EN, [priced, free])
    by_model = {row[STRINGS_EN["BASIC_QA_HISTORY_META_MODEL"]]: row for row in rows}

    assert by_model["priced"][STRINGS_EN["BASIC_QA_TXN_COL_PROVIDER"]] == "Amazon"
    assert by_model["priced"][STRINGS_EN["BASIC_QA_TXN_COL_CLOUD"]] == "Amazon Bedrock"
    assert by_model["priced"][STRINGS_EN["BASIC_QA_TXN_COL_COST"]] == "$0.0025"
    na = STRINGS_EN["BASIC_QA_TOKEN_NA"]
    assert by_model["free"][STRINGS_EN["BASIC_QA_TXN_COL_PROVIDER"]] == na
    assert by_model["free"][STRINGS_EN["BASIC_QA_TXN_COL_CLOUD"]] == na
    assert by_model["free"][STRINGS_EN["BASIC_QA_TXN_COL_COST"]] == na


def test_transaction_csv_has_header_and_rows(monkeypatch: MonkeyPatch) -> None:
    page = _page(monkeypatch)
    rows = page._transaction_rows(STRINGS_EN, [_record(llm_model="model-x")])

    csv_text = page._transaction_csv(rows)
    lines = csv_text.splitlines()

    assert STRINGS_EN["BASIC_QA_TXN_COL_COST"] in lines[0]  # header row
    assert STRINGS_EN["BASIC_QA_TXN_COL_PROVIDER"] in lines[0]
    assert len(lines) == 2  # header + one record
    assert page._transaction_csv([]) == ""
