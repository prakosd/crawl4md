"""Tests for the shell's transient result-key clearing on session switch."""

from __future__ import annotations

import importlib
from pathlib import Path

from pytest import MonkeyPatch

from app_support.session_reset import (
    BASIC_RAG_QA_RESULT_KEYS,
    SEMANTIC_SEARCH_RESULT_KEYS,
    TRANSIENT_RESULT_KEYS,
    clear_transient_result_state,
)

_APP_DIR = Path(__file__).resolve().parents[1]


def _module(monkeypatch: MonkeyPatch, name: str):
    monkeypatch.syspath_prepend(str(_APP_DIR))
    return importlib.import_module(name)


def test_clear_drops_only_transient_keys() -> None:
    state: dict[str, object] = {key: "stale" for key in TRANSIENT_RESULT_KEYS}
    state["session_id"] = "keep-me"
    state["language"] = "EN"

    clear_transient_result_state(state)

    assert not any(key in state for key in TRANSIENT_RESULT_KEYS)
    assert state == {"session_id": "keep-me", "language": "EN"}


def test_clear_is_safe_when_keys_absent() -> None:
    state: dict[str, object] = {}

    clear_transient_result_state(state)

    assert state == {}


def test_semantic_keys_match_page_module(monkeypatch: MonkeyPatch) -> None:
    page = _module(monkeypatch, "app_pages.semantic_search")

    assert set(SEMANTIC_SEARCH_RESULT_KEYS) == {
        page._RESULTS_KEY,
        page._RESULTS_EXPAND_KEY,
        page._RESULTS_QUERY_KEY,
    }


def test_basic_rag_qa_keys_match_page_module(monkeypatch: MonkeyPatch) -> None:
    page = _module(monkeypatch, "app_pages.basic_rag_qa")

    assert set(BASIC_RAG_QA_RESULT_KEYS) == {
        page._QA_RESULTS_KEY,
        page._QA_SEARCH_SECONDS_KEY,
        page._QA_QUESTION_KEY,
        page._PROMPT_KEY,
        page._PROMPT_MAX_KEY,
        page._PROMPT_PENDING_KEY,
        page._ANSWER_KEY,
        page._STATS_KEY,
    }
