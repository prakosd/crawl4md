from __future__ import annotations

from pathlib import Path

import pytest
from rag_engine.prompts import RAG_PROMPT_TEMPLATE

from app_support.basic_rag_qa import basic_rag_qa_form_ui
from app_support.basic_rag_qa.basic_rag_qa_form_ui import (
    TokenTotals,
    apply_maximized_prompt,
    basic_rag_qa_template_is_valid,
    cost_usage_percent,
    resolve_basic_rag_qa_prompt_template,
    token_totals,
    tone_choices,
    usage_percent,
)
from app_support.basic_rag_qa.basic_rag_qa_history import (
    BasicQaRecord,
    save_basic_rag_qa_template,
)


def test_tone_choices_defaults_to_neutral() -> None:
    tones, index = tone_choices()

    assert "Neutral" in tones
    assert tones[index] == "Neutral"


def test_shipped_prompt_template_uses_customer_service_persona() -> None:
    # The committed template customizes the persona (customer service) while keeping
    # the grounding contract, so it deliberately diverges from the generic library
    # default but retains the placeholders and the answer-only-from-knowledge rule.
    template = resolve_basic_rag_qa_prompt_template()
    assert template.startswith("You are a customer service assistant")
    assert template != RAG_PROMPT_TEMPLATE
    for field in ("{question}", "{start}", "{knowledge}", "{end}", "{tone}"):
        assert field in template
    assert "ONLY the retrieved knowledge" in template
    # Source links are woven in conversationally, not as a stiff labelled list.
    assert "in passing with its link" in template


def test_resolve_prompt_template_returns_file_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = "Custom {question} {start}{knowledge}{end} {tone}"
    (tmp_path / "custom.txt").write_text(custom, encoding="utf-8")
    monkeypatch.setattr(basic_rag_qa_form_ui, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        basic_rag_qa_form_ui._settings, "basic_rag_qa_prompt_template_file", "custom.txt"
    )

    assert resolve_basic_rag_qa_prompt_template() == custom


def test_resolve_prompt_template_falls_back_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(basic_rag_qa_form_ui, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        basic_rag_qa_form_ui._settings, "basic_rag_qa_prompt_template_file", "nope.txt"
    )

    assert resolve_basic_rag_qa_prompt_template() == RAG_PROMPT_TEMPLATE


def test_resolve_prompt_template_falls_back_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "empty.txt").write_text("   \n", encoding="utf-8")
    monkeypatch.setattr(basic_rag_qa_form_ui, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        basic_rag_qa_form_ui._settings, "basic_rag_qa_prompt_template_file", "empty.txt"
    )

    assert resolve_basic_rag_qa_prompt_template() == RAG_PROMPT_TEMPLATE


def test_resolve_prompt_template_prefers_session_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A template the user saved for this session wins over the configured file.
    monkeypatch.setattr(basic_rag_qa_form_ui, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        basic_rag_qa_form_ui._settings, "basic_rag_qa_prompt_template_file", "cfg.txt"
    )
    (tmp_path / "cfg.txt").write_text(
        "config {question}{start}{knowledge}{end}{tone}", encoding="utf-8"
    )
    save_basic_rag_qa_template(tmp_path, "session {question}{start}{knowledge}{end}{tone}")

    assert resolve_basic_rag_qa_prompt_template(tmp_path).startswith("session ")


def test_resolve_prompt_template_uses_config_without_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(basic_rag_qa_form_ui, "_REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        basic_rag_qa_form_ui._settings, "basic_rag_qa_prompt_template_file", "cfg.txt"
    )
    (tmp_path / "cfg.txt").write_text(
        "config {question}{start}{knowledge}{end}{tone}", encoding="utf-8"
    )

    # No session template saved -> the configured file is used.
    assert resolve_basic_rag_qa_prompt_template(tmp_path).startswith("config ")


def test_template_is_valid_accepts_the_expected_fields() -> None:
    assert basic_rag_qa_template_is_valid("{question} {start}{knowledge}{end} {tone}") is True


def test_template_is_valid_rejects_unknown_or_stray_braces() -> None:
    assert basic_rag_qa_template_is_valid("hello {oops} {question}") is False
    assert basic_rag_qa_template_is_valid("stray { brace") is False


def test_apply_maximized_prompt_copies_source_to_target() -> None:
    state: dict[str, object] = {"src": "edited prompt"}

    apply_maximized_prompt(state, source_key="src", target_key="dst")

    assert state["dst"] == "edited prompt"
    assert state["src"] == "edited prompt"  # the source is left intact


def test_apply_maximized_prompt_is_noop_when_source_missing() -> None:
    state: dict[str, object] = {"dst": "keep"}

    apply_maximized_prompt(state, source_key="src", target_key="dst")

    assert state == {"dst": "keep"}


def _record(**tokens: object) -> BasicQaRecord:
    return BasicQaRecord(
        timestamp_utc="t",
        index_folder="f",
        index_run="r",
        embedding_model="e",
        llm_model="echo",
        tone="Neutral",
        top_k=5,
        question="q",
        prompt="p",
        **tokens,  # type: ignore[arg-type]
    )


def test_token_totals_sums_and_treats_missing_as_zero() -> None:
    records = [
        _record(input_tokens=10, output_tokens=5, total_tokens=15),
        _record(input_tokens=None, output_tokens=None, total_tokens=None),
        _record(input_tokens=3, output_tokens=2, total_tokens=5),
    ]

    totals = token_totals(records)

    assert totals == TokenTotals(input_tokens=13, output_tokens=7, total_tokens=20)


def test_token_totals_empty() -> None:
    assert token_totals([]) == TokenTotals(0, 0, 0)


def test_usage_percent_keeps_two_decimal_precision() -> None:
    assert usage_percent(1234, 100000) == pytest.approx(1.234)
    assert usage_percent(4999, 100000) == pytest.approx(4.999)


def test_usage_percent_zero_or_negative_quota_is_zero() -> None:
    assert usage_percent(500, 0) == 0.0
    assert usage_percent(500, -10) == 0.0


def test_usage_percent_at_and_over_budget() -> None:
    assert usage_percent(100000, 100000) == pytest.approx(100.0)
    assert usage_percent(150000, 100000) == pytest.approx(150.0)


def test_cost_usage_percent_basic_and_over_budget() -> None:
    assert cost_usage_percent(0.5, 1.0) == pytest.approx(50.0)
    assert cost_usage_percent(1.5, 1.0) == pytest.approx(150.0)


def test_cost_usage_percent_none_when_unpriced_or_bad_quota() -> None:
    assert cost_usage_percent(None, 1.0) is None
    assert cost_usage_percent(0.5, 0.0) is None
    assert cost_usage_percent(0.5, -1.0) is None
