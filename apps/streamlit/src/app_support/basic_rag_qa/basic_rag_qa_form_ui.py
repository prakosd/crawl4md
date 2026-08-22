"""Pure option/summary helpers for the Basic RAG Q&A page (Step 4).

Kept separate from the Streamlit rendering so they are unit-testable without a
running app, mirroring the split in ``llm_form_ui`` and ``vector_form_ui``.
"""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from log4py import get_logger
from rag_engine.prompts import RAG_PROMPT_TEMPLATE

from app_support.basic_rag_qa.basic_rag_qa_history import (
    BasicQaRecord,
    load_basic_rag_qa_template,
)
from app_support.settings import get_settings

__all__ = [
    "TokenTotals",
    "apply_maximized_prompt",
    "basic_rag_qa_template_is_valid",
    "resolve_basic_rag_qa_prompt_template",
    "token_totals",
    "tone_choices",
    "usage_percent",
]

_logger = get_logger(__name__)
_settings = get_settings()
_TONE_ORDER = tuple(
    tone.strip() for tone in _settings.basic_rag_qa_tones.split(",") if tone.strip()
)
_DEFAULT_TONE = _settings.basic_rag_qa_default_tone
# basic_rag_qa_form_ui.py lives at apps/streamlit/src/app_support/basic_rag_qa/; the
# repo root is five parents up (one deeper than settings.py) and the template path
# resolves against it.
_REPO_ROOT = Path(__file__).resolve().parents[5]


def resolve_basic_rag_qa_prompt_template(session_root: Path | str | None = None) -> str:
    """Return the Step 4 prompt template.

    Precedence: a template the user saved for this session (via Edit template) →
    the configured ``BASIC_RAG_QA_PROMPT_TEMPLATE_FILE`` (resolved against the repo
    root, so an operator can reword the default without a code change) → the
    built-in ``RAG_PROMPT_TEMPLATE``. A missing/empty/unreadable source falls
    through to the next, so a bad path never breaks generation.
    """
    if session_root is not None:
        saved = load_basic_rag_qa_template(session_root)
        if saved is not None:
            return saved
    path = _REPO_ROOT / _settings.basic_rag_qa_prompt_template_file
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        _logger.warning(
            "RAG Q&A prompt template file not found at %s; using the built-in default.", path
        )
        return RAG_PROMPT_TEMPLATE
    if not text.strip():
        _logger.warning(
            "RAG Q&A prompt template file %s is empty; using the built-in default.", path
        )
        return RAG_PROMPT_TEMPLATE
    return text


def basic_rag_qa_template_is_valid(template: str) -> bool:
    """Return True when *template* has only the fields ``build_rag_prompt`` fills.

    Mirrors ``build_rag_prompt``'s ``str.format`` contract: an unknown ``{field}``
    or a stray brace raises, so the editor can reject a template that would
    otherwise silently fall back to the default.
    """
    try:
        template.format(question="", start="", knowledge="", end="", tone="")
    except (KeyError, IndexError, ValueError):
        return False
    return True


def apply_maximized_prompt(
    state: MutableMapping[str, Any], *, source_key: str, target_key: str
) -> None:
    """Copy the prompt text from *source_key* to *target_key* in *state*.

    Keeps the inline editor and the maximized dialog in sync: the dialog is seeded
    from the inline value when opened and written back when closed. A no-op when
    *source_key* is absent, so a first open or an empty dialog never errors.
    """
    if source_key in state:
        state[target_key] = state[source_key]


def tone_choices() -> tuple[list[str], int]:
    """Return the offered tones and the default-selected index (.env-configured)."""
    tones = list(_TONE_ORDER) or [_DEFAULT_TONE]
    default_index = tones.index(_DEFAULT_TONE) if _DEFAULT_TONE in tones else 0
    return tones, default_index


@dataclass(frozen=True)
class TokenTotals:
    """Session-wide input/output/total token counts across QA history."""

    input_tokens: int
    output_tokens: int
    total_tokens: int


def token_totals(records: Sequence[BasicQaRecord]) -> TokenTotals:
    """Sum token usage across *records*, treating missing counts as zero."""
    return TokenTotals(
        input_tokens=sum(record.input_tokens or 0 for record in records),
        output_tokens=sum(record.output_tokens or 0 for record in records),
        total_tokens=sum(record.total_tokens or 0 for record in records),
    )


def usage_percent(total: int, quota: int) -> float:
    """Return session token usage as a percent of *quota*, as a float.

    Returns 0.0 when *quota* is not positive, so a misconfigured budget never
    divides by zero. May exceed 100 when the session total is over budget.
    """
    if quota <= 0:
        return 0.0
    return total / quota * 100.0


def cost_usage_percent(cost: float | None, quota: float) -> float | None:
    """Return session USD cost as a percent of the cost *quota*, or None.

    Mirrors ``usage_percent`` for dollars: None when nothing is priced yet or the
    quota is not positive (so a misconfigured budget never divides by zero). May
    exceed 100 when the session cost is over budget.
    """
    if cost is None or quota <= 0:
        return None
    return cost / quota * 100.0
