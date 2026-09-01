"""Transient Step 3/4 result keys the shell clears when switching sessions.

When the user creates or switches to another browser session, the shell must drop
the previous session's search hits and generated answer so a fresh session never
shows another one's results. These key names mirror the private constants in the
Step 3 (``app_pages.semantic_search``) and Step 4 (``app_pages.basic_rag_qa``)
page modules. ``app_support`` must not import ``app_pages`` (wrong dependency
direction), so the strings live here and ``tests/test_session_reset.py`` asserts
they stay in lock-step with the page modules.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

__all__ = [
    "BASIC_RAG_QA_RESULT_KEYS",
    "CONVERSATIONAL_RAG_RESULT_KEYS",
    "SEMANTIC_SEARCH_RESULT_KEYS",
    "TRANSIENT_RESULT_KEYS",
    "clear_transient_result_state",
]

# Step 3: the persisted hits, the one-shot expand flag, and the query behind them.
SEMANTIC_SEARCH_RESULT_KEYS: tuple[str, ...] = (
    "semantic_search_results",
    "semantic_search_results_expanded",
    "semantic_search_results_query",
)

# Step 4: the retrieval hits and timing, the generated prompt (inline + maximized +
# pending write-back), and the last answer with its stats caption.
BASIC_RAG_QA_RESULT_KEYS: tuple[str, ...] = (
    "basic_rag_qa_results",
    "basic_rag_qa_search_seconds",
    "basic_rag_qa_results_question",
    "basic_rag_qa_prompt",
    "basic_rag_qa_prompt_max",
    "basic_rag_qa_prompt_pending",
    "basic_rag_qa_answer",
    "basic_rag_qa_stats",
)

# Step 5: the conversation turns, rolling state, follow-up cache, and pending click.
CONVERSATIONAL_RAG_RESULT_KEYS: tuple[str, ...] = (
    "conversational_rag_turns",
    "conversational_rag_state",
    "conversational_rag_followup_cache",
    "conversational_rag_pending",
)

TRANSIENT_RESULT_KEYS: tuple[str, ...] = (
    *SEMANTIC_SEARCH_RESULT_KEYS,
    *BASIC_RAG_QA_RESULT_KEYS,
    *CONVERSATIONAL_RAG_RESULT_KEYS,
)


def clear_transient_result_state(session_state: MutableMapping[str, Any]) -> None:
    """Drop Step 3/4 result and answer keys so a switched-to session starts clean."""
    for key in TRANSIENT_RESULT_KEYS:
        session_state.pop(key, None)
