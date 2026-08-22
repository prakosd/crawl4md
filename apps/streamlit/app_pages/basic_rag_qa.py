"""Step 4 content area for Basic RAG Q&A.

Two stages: **Generate prompt** runs semantic search and assembles an editable,
fully-visible RAG prompt from the retrieved knowledge; **Send** streams the
selected language model's answer and records token usage + latency. Per-session
prompt history (with replay) and a session token summary above the history round
it out. The heavy
lifting lives in ``rag_engine`` (prompt builder, streaming) and the app helpers
(``basic_rag_qa_history`` / ``basic_rag_qa_form_ui``); this module only wires widgets to them.
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st
from rag_engine import (
    RagConfig,
    build_rag_prompt,
    messages,
    resolve_chat_model,
    retrieve,
    stream_prompt,
)
from rag_engine.models import TokenUsage

from app_support.basic_rag_qa.basic_rag_qa_form_ui import (
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
    append_basic_rag_qa_record,
    load_basic_rag_qa_history,
    reset_basic_rag_qa_template,
    save_basic_rag_qa_template,
    set_basic_rag_qa_pinned,
)
from app_support.focus import focus_widget
from app_support.i18n import Strings, get_strings
from app_support.model_pricing import (
    estimate_cost,
    get_model_price,
    pricing_captured,
    pricing_sources,
    render_pricing_markdown,
)
from app_support.rag_shared.index_catalog import IndexRef
from app_support.rag_shared.llm_form_ui import (
    chat_model_choices,
    chat_model_info_for,
    chat_model_label,
)
from app_support.rag_shared.rag_ui import (
    RagPageContext,
    find_index,
    index_option_label,
    kv_grid_html,
    local_time_label,
    render_messages,
    render_results_panel,
    select_index,
    stacked_label_value_html,
)
from app_support.settings import get_settings

if TYPE_CHECKING:
    from streamlit.delta_generator import DeltaGenerator

_settings = get_settings()
_DEFAULT_TOP_RESULTS = _settings.basic_rag_qa_top_results
_DEFAULT_RESULT_TAB = _settings.semantic_search_default_tab
_MAX_TOP_RESULTS = 20
# Estimated costs show 4 decimals; a positive cost that rounds below this would
# read as $0.0000, so show a "< minimum" hint instead.
_COST_DECIMALS = 4
_COST_UNDER_MIN = 5e-5
# Filename for the Transaction history CSV export.
_TXN_CSV_FILENAME = "basic_rag_qa_transactions.csv"
_PROMPT_FIELD_HEIGHT = 260
# The maximized editor is a wide dialog with a tall text area, sized close to the
# viewport via scoped CSS (mirrors the file-preview dialog's ``:has()`` approach).
_MAXIMIZE_PROMPT_HEIGHT = 560
_MAXIMIZE_DIALOG_SCOPE_CLASS = "basic-rag-qa-maximize-scope"
_MAXIMIZE_DIALOG_VIEWPORT_WIDTH = "90vw"
# Cap the dialog and its editor to the viewport so the action buttons stay in view
# without scrolling the page; the text area scrolls internally instead.
_MAXIMIZE_DIALOG_MAX_HEIGHT = "82vh"
_MAXIMIZE_TEXTAREA_MAX_HEIGHT = "46vh"
_MAXIMIZE_DIALOG_CSS = f"""
<div class="{_MAXIMIZE_DIALOG_SCOPE_CLASS}" style="display:none"></div>
<style>
div[data-testid="stDialog"]:has(.{_MAXIMIZE_DIALOG_SCOPE_CLASS}) [role="dialog"][aria-modal="true"] {{
    width: {_MAXIMIZE_DIALOG_VIEWPORT_WIDTH} !important;
    max-width: {_MAXIMIZE_DIALOG_VIEWPORT_WIDTH} !important;
    max-height: {_MAXIMIZE_DIALOG_MAX_HEIGHT} !important;
}}
div[data-testid="stDialog"]:has(.{_MAXIMIZE_DIALOG_SCOPE_CLASS}) .stTextArea textarea {{
    max-height: {_MAXIMIZE_TEXTAREA_MAX_HEIGHT} !important;
}}
</style>
"""
_PANEL_COLUMN_WIDTHS = (0.8, 0.2)
# The Token usage panel packs five metrics in one row inside a collapsible
# expander; keep each metric value on one line so a six-figure count never wraps
# beside its icon. A hidden marker scopes the rule to this panel (mirrors the
# dialog CSS); its own element is hidden so it adds no vertical gap on top.
_TOKEN_PANEL_SCOPE_CLASS = "basic-rag-qa-token-panel"
_TOKEN_PANEL_CSS = f"""
<div class="{_TOKEN_PANEL_SCOPE_CLASS}" style="display:none"></div>
<style>
div[data-testid="stElementContainer"]:has(.{_TOKEN_PANEL_SCOPE_CLASS}) {{
    display: none;
}}
div[data-testid="stExpander"]:has(.{_TOKEN_PANEL_SCOPE_CLASS})
    div[data-testid="stMetricValue"] {{
    font-size: 1.4rem;
    white-space: nowrap;
}}
</style>
"""

# Tighten the gap between the pin and replay buttons in each history card.
_HISTORY_ACTIONS_CSS = "<style>[class*='st-key-basic_rag_qa_history_actions_']{gap:0.5rem}</style>"

# Widget keys; a history replay pre-fills these before the widgets render.
_INDEX_KEY = "basic_rag_qa_index"
_TOP_RESULTS_KEY = "basic_rag_qa_top_results"
_MODEL_KEY = "basic_rag_qa_llm_model"
_TONE_KEY = "basic_rag_qa_tone"
_QUESTION_KEY = "basic_rag_qa_question"
_PROMPT_KEY = "basic_rag_qa_prompt"
# The last Generate-prompt search hits persist so the Search results panel
# survives reruns and stays a stable fixture between the question and prompt.
_QA_RESULTS_KEY = "basic_rag_qa_results"
# The maximized-editor mirror of the prompt, a pending write-back applied before
# the inline widget renders, and the flag that keeps the dialog open across reruns.
_PROMPT_MAX_KEY = "basic_rag_qa_prompt_max"
_PROMPT_PENDING_KEY = "basic_rag_qa_prompt_pending"
_MAXIMIZE_OPEN_KEY = "basic_rag_qa_maximize_open"
# The last answer and its stats caption persist so they survive reruns after a send.
_ANSWER_KEY = "basic_rag_qa_answer"
_STATS_KEY = "basic_rag_qa_stats"
# A replay stashes a record here; a one-shot flag then moves focus to the prompt.
_REPLAY_KEY = "basic_rag_qa_replay"
_FOCUS_PROMPT_KEY = "basic_rag_qa_focus_prompt"
# The Edit-template dialog: the editable copy, the flag that keeps it open across
# reruns, and a one-shot flag set when a save is rejected for bad placeholders.
_TEMPLATE_EDIT_KEY = "basic_rag_qa_template_edit"
_EDIT_TEMPLATE_OPEN_KEY = "basic_rag_qa_edit_template_open"
# The read-only model-pricing preview dialog: a wide, scrollable modal scoped via
# a hidden marker (mirrors the maximize dialog's ``:has()`` approach).
_PRICING_DIALOG_OPEN_KEY = "basic_rag_qa_pricing_open"
_PRICING_DIALOG_SCOPE_CLASS = "basic-rag-qa-pricing-scope"
_PRICING_DIALOG_VIEWPORT_WIDTH = "80vw"
_PRICING_DIALOG_MAX_HEIGHT = "82vh"
_PRICING_DIALOG_CSS = f"""
<div class="{_PRICING_DIALOG_SCOPE_CLASS}" style="display:none"></div>
<style>
div[data-testid="stDialog"]:has(.{_PRICING_DIALOG_SCOPE_CLASS}) [role="dialog"][aria-modal="true"] {{
    width: {_PRICING_DIALOG_VIEWPORT_WIDTH} !important;
    max-width: {_PRICING_DIALOG_VIEWPORT_WIDTH} !important;
    max-height: {_PRICING_DIALOG_MAX_HEIGHT} !important;
}}
</style>
"""
_TEMPLATE_INVALID_KEY = "basic_rag_qa_template_invalid"
# Session-state contract with the shell: a page sets this to a localized success
# message; the shell (app_pages must not call st.toast) fires it once next run.
_PAGE_TOAST_KEY = "pending_page_toast"


def render_page(context: RagPageContext) -> None:
    """Render the Basic RAG Q&A page content area."""
    strings = get_strings(st.session_state.get("language", context.default_language))
    session_root = context.session_root()
    indexes = list(context.list_indexes())

    st.subheader(strings["BASIC_QA_SECTION_HEADER"], anchor="basic-rag-qa-header")
    st.caption(strings["BASIC_QA_SECTION_CAPTION"])

    # Apply a pending replay before the widgets render, then seed first-run
    # defaults so a replay can overwrite them without a Streamlit warning.
    replay = st.session_state.pop(_REPLAY_KEY, None)
    if replay is not None:
        _apply_replay(strings, indexes, replay)
    # A maximized-editor edit is written back here, before the prompt widget
    # renders, so it lands as the field's value without a widget-mutation error.
    if _PROMPT_PENDING_KEY in st.session_state:
        st.session_state[_PROMPT_KEY] = st.session_state.pop(_PROMPT_PENDING_KEY)
    model_options, default_model_index = chat_model_choices()
    tones, default_tone_index = tone_choices()
    st.session_state.setdefault(_TOP_RESULTS_KEY, _DEFAULT_TOP_RESULTS)
    st.session_state.setdefault(_MODEL_KEY, model_options[default_model_index])
    st.session_state.setdefault(_TONE_KEY, tones[default_tone_index])
    st.session_state.setdefault(_QUESTION_KEY, "")
    st.session_state.setdefault(_PROMPT_KEY, "")

    index, model, tone, top_results = _render_panel(strings, indexes, model_options, tones)
    question, generate = _render_question_form(strings, session_root, disabled=index is None)
    do_generate = bool(generate and index is not None and question.strip())
    _render_search_results(
        strings,
        index,
        question.strip() if question else "",
        top_results,
        tone,
        do_generate,
        session_root,
    )

    prompt_text, send, maximize, answer_slot = _render_prompt_form(strings, disabled=index is None)
    if st.session_state.pop(_FOCUS_PROMPT_KEY, False):
        focus_widget(_PROMPT_KEY)
    if maximize:
        apply_maximized_prompt(st.session_state, source_key=_PROMPT_KEY, target_key=_PROMPT_MAX_KEY)
        st.session_state[_MAXIMIZE_OPEN_KEY] = True

    answered_now = False
    if send and index is not None:
        st.session_state[_ANSWER_KEY] = None
        st.session_state[_STATS_KEY] = None
        if prompt_text.strip():
            with answer_slot:
                answered_now = _send_prompt(
                    strings,
                    session_root,
                    index=index,
                    model=model,
                    tone=tone,
                    top_results=top_results,
                    question=question,
                    prompt_text=prompt_text,
                )
        else:
            with answer_slot:
                st.info(strings["BASIC_QA_NO_PROMPT_HINT"])
    if not answered_now:
        with answer_slot:
            _render_stored_answer(strings)

    if st.session_state.get(_MAXIMIZE_OPEN_KEY):
        _prompt_maximize_dialog(strings)
    if st.session_state.get(_EDIT_TEMPLATE_OPEN_KEY):
        _edit_template_dialog(strings, session_root)
    if st.session_state.get(_PRICING_DIALOG_OPEN_KEY):
        _pricing_dialog(strings)

    records = load_basic_rag_qa_history(session_root)
    _render_token_summary(strings, records)
    _render_basic_rag_qa_history(strings, session_root, records)

    context.render_downloads()


def _render_panel(
    strings: Strings,
    indexes: Sequence[IndexRef],
    model_options: Sequence[str],
    tones: Sequence[str],
) -> tuple[IndexRef | None, str, str, int]:
    """Render the index / top-results / model / tone panel; return the choices."""
    with st.container(border=True):
        index_col, top_col = st.columns(_PANEL_COLUMN_WIDTHS, vertical_alignment="center")
        with index_col:
            index = select_index(strings, indexes, key=_INDEX_KEY)
        with top_col:
            top_results = int(
                st.number_input(
                    strings["BASIC_QA_TOP_RESULTS_LABEL"],
                    min_value=1,
                    max_value=_MAX_TOP_RESULTS,
                    step=1,
                    help=strings["BASIC_QA_TOP_RESULTS_HELP"],
                    disabled=index is None,
                    key=_TOP_RESULTS_KEY,
                )
            )
        model_col, tone_col = st.columns(_PANEL_COLUMN_WIDTHS)
        with model_col:
            model = st.selectbox(
                strings["BASIC_QA_LLM_LABEL"],
                options=list(model_options),
                format_func=lambda model_id: chat_model_label(model_id, strings),
                help=strings["BASIC_QA_LLM_HELP"],
                disabled=index is None,
                key=_MODEL_KEY,
            )
        with tone_col:
            tone = st.selectbox(
                strings["BASIC_QA_TONE_LABEL"],
                options=list(tones),
                help=strings["BASIC_QA_TONE_HELP"],
                disabled=index is None,
                key=_TONE_KEY,
            )
    return index, model, tone, top_results


def _render_question_form(
    strings: Strings, session_root: Path, *, disabled: bool
) -> tuple[str, bool]:
    """Render the question field + Generate-prompt / Edit-template buttons.

    Generate is defined first so Enter submits it, not Edit template. Edit template
    is a form-submit button (so it can live in the panel, right of Generate) that
    opens the editor via its on-click without triggering generation.
    """
    with st.form("basic_rag_qa_question_form", enter_to_submit=True, border=True):
        question = st.text_input(
            strings["BASIC_QA_QUESTION_LABEL"],
            placeholder=strings["BASIC_QA_QUESTION_PLACEHOLDER"],
            disabled=disabled,
            key=_QUESTION_KEY,
        )
        generate_col, edit_col = st.columns(2, vertical_alignment="center")
        with generate_col:
            generate = st.form_submit_button(
                strings["BASIC_QA_GENERATE_BUTTON"],
                type="primary",
                icon=":material/auto_awesome:",
                help=strings["BASIC_QA_GENERATE_HELP"],
                disabled=disabled,
            )
        with edit_col, st.container(horizontal_alignment="right"):
            st.form_submit_button(
                strings["BASIC_QA_EDIT_TEMPLATE_BUTTON"],
                icon=":material/edit_note:",
                help=strings["BASIC_QA_EDIT_TEMPLATE_HELP"],
                on_click=_open_edit_template,
                args=(session_root,),
            )
    return question, generate


def _render_prompt_form(
    strings: Strings, *, disabled: bool
) -> tuple[str, bool, bool, DeltaGenerator]:
    """Render the editable prompt field + Send/Maximize buttons.

    Returns the prompt text, the Send state, the Maximize state, and an in-form
    container placed under the buttons so the streamed answer renders inside this
    panel. Send is defined first so Ctrl/Cmd+Enter maps to it, not Maximize.
    """
    with st.form("basic_rag_qa_prompt_form", enter_to_submit=True, border=True):
        prompt_text = st.text_area(
            strings["BASIC_QA_PROMPT_LABEL"],
            placeholder=strings["BASIC_QA_PROMPT_PLACEHOLDER"],
            help=strings["BASIC_QA_PROMPT_HELP"],
            height=_PROMPT_FIELD_HEIGHT,
            disabled=disabled,
            key=_PROMPT_KEY,
        )
        # Maximize sits at the far left and Send at the far right; Send is still
        # defined first so Ctrl/Cmd+Enter submits it rather than Maximize.
        left_col, right_col = st.columns(2, vertical_alignment="center")
        with right_col, st.container(horizontal_alignment="right"):
            send = st.form_submit_button(
                strings["BASIC_QA_SEND_BUTTON"],
                type="primary",
                icon=":material/send:",
                help=strings["BASIC_QA_SEND_HELP"],
                disabled=disabled,
            )
        with left_col:
            maximize = st.form_submit_button(
                ":material/fullscreen:",
                help=strings["BASIC_QA_MAXIMIZE_HELP"],
                disabled=disabled,
            )
        answer_slot = st.container()
    return prompt_text, send, maximize, answer_slot


def _apply_and_close_maximized_prompt(strings: Strings) -> None:
    """Write the maximized editor's text back to the inline prompt, then close.

    Bound to the dialog's Apply button: it copies the edited text into the inline
    prompt's pending key (applied before the inline widget renders next run) and
    closes the dialog. Dismissing any other way (X / click-away / Esc) keeps the
    inline prompt as-is, discarding the dialog edits.
    """
    apply_maximized_prompt(
        st.session_state, source_key=_PROMPT_MAX_KEY, target_key=_PROMPT_PENDING_KEY
    )
    st.session_state[_MAXIMIZE_OPEN_KEY] = False
    st.session_state[_PAGE_TOAST_KEY] = strings["BASIC_QA_MAXIMIZE_APPLIED_TOAST"]


def _on_maximize_dismiss() -> None:
    """Close the dialog without saving — X / click-away / Esc discard the edits."""
    st.session_state[_MAXIMIZE_OPEN_KEY] = False


@st.dialog(" ", width="large", on_dismiss=_on_maximize_dismiss)
def _prompt_maximize_dialog(strings: Strings) -> None:
    """Show the prompt in a large, editable dialog with an explicit Apply button.

    Editing here does not touch the inline prompt; only **Apply** writes the text
    back (and closes). Dismissing another way (X / click-away / Esc) discards the
    edits, leaving the inline prompt unchanged.
    """
    st.markdown(
        f"{_MAXIMIZE_DIALOG_CSS}\n\n"
        f"**{strings['BASIC_QA_MAXIMIZE_TITLE']}**  \n"
        f"<span style='opacity:0.6;font-size:0.875rem'>"
        f"{strings['BASIC_QA_MAXIMIZE_CAPTION']}</span>",
        unsafe_allow_html=True,
    )
    st.text_area(
        strings["BASIC_QA_PROMPT_LABEL"],
        height=_MAXIMIZE_PROMPT_HEIGHT,
        label_visibility="collapsed",
        key=_PROMPT_MAX_KEY,
    )
    with st.container(horizontal_alignment="right"):
        if st.button(
            strings["BASIC_QA_MAXIMIZE_APPLY"],
            type="primary",
            icon=":material/check:",
        ):
            _apply_and_close_maximized_prompt(strings)
            st.rerun()


def _open_edit_template(session_root: Path) -> None:
    """Seed the editor from the effective template, then open the dialog."""
    st.session_state[_TEMPLATE_EDIT_KEY] = resolve_basic_rag_qa_prompt_template(session_root)
    st.session_state[_TEMPLATE_INVALID_KEY] = False
    st.session_state[_EDIT_TEMPLATE_OPEN_KEY] = True


def _save_template(strings: Strings, session_root: Path) -> None:
    """Persist the edited template; keep the dialog open with a warning if invalid."""
    template = st.session_state.get(_TEMPLATE_EDIT_KEY, "")
    if not basic_rag_qa_template_is_valid(template):
        st.session_state[_TEMPLATE_INVALID_KEY] = True
        return
    save_basic_rag_qa_template(session_root, template)
    st.session_state[_EDIT_TEMPLATE_OPEN_KEY] = False
    st.session_state[_PAGE_TOAST_KEY] = strings["BASIC_QA_TEMPLATE_SAVED_TOAST"]


def _reset_template(strings: Strings, session_root: Path) -> None:
    """Delete the session template, then close the dialog with a toast."""
    reset_basic_rag_qa_template(session_root)
    st.session_state[_TEMPLATE_INVALID_KEY] = False
    st.session_state[_EDIT_TEMPLATE_OPEN_KEY] = False
    st.session_state[_PAGE_TOAST_KEY] = strings["BASIC_QA_TEMPLATE_RESET_TOAST"]


def _on_edit_template_dismiss() -> None:
    """Close the editor without saving (X / click-away / Esc discard edits)."""
    st.session_state[_EDIT_TEMPLATE_OPEN_KEY] = False


@st.dialog(" ", width="large", on_dismiss=_on_edit_template_dismiss)
def _edit_template_dialog(strings: Strings, session_root: Path) -> None:
    """Edit the per-session prompt template that Generate prompt fills in.

    Save persists the template for this session (used until reset); Reset removes it
    so the default returns. The placeholders must survive, so an invalid template is
    rejected rather than silently falling back to the default.
    """
    st.markdown(
        f"{_MAXIMIZE_DIALOG_CSS}\n\n"
        f"**{strings['BASIC_QA_EDIT_TEMPLATE_TITLE']}**  \n"
        f"<span style='opacity:0.6;font-size:0.875rem'>"
        f"{strings['BASIC_QA_EDIT_TEMPLATE_CAPTION']}</span>",
        unsafe_allow_html=True,
    )
    if st.session_state.pop(_TEMPLATE_INVALID_KEY, False):
        st.warning(strings["BASIC_QA_EDIT_TEMPLATE_INVALID"])
    st.text_area(
        strings["BASIC_QA_EDIT_TEMPLATE_TITLE"],
        height=_MAXIMIZE_PROMPT_HEIGHT,
        label_visibility="collapsed",
        key=_TEMPLATE_EDIT_KEY,
    )
    reset_col, save_col = st.columns(2, vertical_alignment="center")
    with reset_col:
        if st.button(
            strings["BASIC_QA_EDIT_TEMPLATE_RESET"],
            icon=":material/restart_alt:",
        ):
            _reset_template(strings, session_root)
            st.rerun()
    with save_col, st.container(horizontal_alignment="right"):
        if st.button(
            strings["BASIC_QA_EDIT_TEMPLATE_SAVE"],
            type="primary",
            icon=":material/check:",
        ):
            _save_template(strings, session_root)
            st.rerun()


def _render_search_results(
    strings: Strings,
    index: IndexRef | None,
    question: str,
    top_results: int,
    tone: str,
    do_generate: bool,
    session_root: Path,
) -> None:
    """Render the always-present Search results panel between question and prompt.

    On a fresh Generate, run retrieval with a spinner, build the editable prompt
    from the hits, and store them; the panel below then renders those hits
    collapsed, its title carrying the match count. Otherwise it shows the last
    search's hits (or a hint), so the panel stays a stable fixture whose gap to
    the prompt panel never shifts.
    """
    if do_generate and index is not None:
        with st.spinner(strings["BASIC_QA_SEARCHING"]):
            result = retrieve(index.run_dir, question, RagConfig(top_k=top_results))
        render_messages(strings, result.warnings, result.errors)
        st.session_state[_QA_RESULTS_KEY] = list(result.chunks)
        st.session_state[_PROMPT_KEY] = build_rag_prompt(
            question,
            result.chunks,
            tone,
            template=resolve_basic_rag_qa_prompt_template(session_root),
        )
        st.session_state[_ANSWER_KEY] = None
        st.session_state[_STATS_KEY] = None
        st.session_state[_FOCUS_PROMPT_KEY] = True
    stored = st.session_state.get(_QA_RESULTS_KEY)
    empty_hint = (
        strings["SEARCH_NO_RESULTS"]
        if _QA_RESULTS_KEY in st.session_state
        else strings["BASIC_QA_RESULTS_EMPTY"]
    )
    render_results_panel(
        strings, stored or [], empty_hint=empty_hint, default_tab=_DEFAULT_RESULT_TAB
    )


def _send_prompt(
    strings: Strings,
    session_root: Path,
    *,
    index: IndexRef,
    model: str,
    tone: str,
    top_results: int,
    question: str,
    prompt_text: str,
) -> bool:
    """Stream the model's answer to *prompt_text* and record it; return success."""
    resolved, warnings = resolve_chat_model(model)
    render_messages(strings, warnings, [])
    with st.container(border=True):
        st.markdown(f"**{strings['BASIC_QA_ANSWER_HEADER']}**")
        generation = stream_prompt(resolved.model, prompt_text)
        start = time.perf_counter()
        try:
            st.write_stream(generation)
        except Exception as exc:  # noqa: BLE001 - boundary around the chat backend
            render_messages(strings, [], [messages.classify_generation_failure(str(exc))])
            return False
        elapsed = time.perf_counter() - start
        caption = _stats_caption(
            strings, generation.usage, elapsed, chat_model_info_for(resolved.model_id).label
        )
        st.caption(caption)
    _record_send(
        session_root,
        index=index,
        model_used=resolved.model_id,
        tone=tone,
        top_results=top_results,
        question=question,
        prompt_text=prompt_text,
        answer=generation.text,
        usage=generation.usage,
        elapsed=elapsed,
    )
    st.session_state[_ANSWER_KEY] = generation.text
    st.session_state[_STATS_KEY] = caption
    return True


def _record_send(
    session_root: Path,
    *,
    index: IndexRef,
    model_used: str,
    tone: str,
    top_results: int,
    question: str,
    prompt_text: str,
    answer: str,
    usage: TokenUsage | None,
    elapsed: float,
) -> None:
    append_basic_rag_qa_record(
        session_root,
        BasicQaRecord(
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            index_folder=index.vector_folder,
            index_run=index.run_name,
            embedding_model=index.manifest.embedding_model_used or "",
            llm_model=model_used,
            tone=tone,
            top_k=int(top_results),
            question=question.strip(),
            prompt=prompt_text,
            answer=answer,
            input_tokens=usage.input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            total_tokens=usage.total_tokens if usage else None,
            latency_seconds=elapsed,
        ),
    )


def _render_stored_answer(strings: Strings) -> None:
    """Re-render the last answer (and stats) so it survives reruns after a send."""
    answer = st.session_state.get(_ANSWER_KEY)
    if not answer:
        return
    with st.container(border=True):
        st.markdown(f"**{strings['BASIC_QA_ANSWER_HEADER']}**")
        st.write(answer)
        caption = st.session_state.get(_STATS_KEY)
        if caption:
            st.caption(caption)


def _record_cost(record: BasicQaRecord) -> float | None:
    """Estimated USD cost for one recorded request, or None when it can't be priced."""
    return estimate_cost(record.llm_model, record.input_tokens, record.output_tokens)


def _session_cost(records: Sequence[BasicQaRecord]) -> float | None:
    """Sum the priced requests' estimated USD cost; None when none can be priced."""
    priced = [cost for record in records if (cost := _record_cost(record)) is not None]
    return sum(priced) if priced else None


def _session_input_cost(records: Sequence[BasicQaRecord]) -> float | None:
    """Sum the priced requests' estimated USD input-token cost; None when unpriced."""
    priced = [
        cost
        for record in records
        if (cost := estimate_cost(record.llm_model, record.input_tokens, 0)) is not None
    ]
    return sum(priced) if priced else None


def _session_output_cost(records: Sequence[BasicQaRecord]) -> float | None:
    """Sum the priced requests' estimated USD output-token cost; None when unpriced."""
    priced = [
        cost
        for record in records
        if (cost := estimate_cost(record.llm_model, 0, record.output_tokens)) is not None
    ]
    return sum(priced) if priced else None


def _format_cost(strings: Strings, cost: float | None) -> str:
    """Render a USD cost estimate, the n/a dash, or a below-minimum hint."""
    if cost is None:
        return strings["BASIC_QA_TOKEN_NA"]
    if 0 < cost < _COST_UNDER_MIN:
        return strings["BASIC_QA_COST_UNDER_MIN"]
    return f"${cost:,.{_COST_DECIMALS}f}"


def _cost_delta(strings: Strings, cost: float | None) -> str | None:
    """Format a USD cost as a neutral metric delta, or None to omit it."""
    return None if cost is None else _format_cost(strings, cost)


def _on_pricing_dismiss() -> None:
    """Close the read-only pricing preview (X / click-away / Esc)."""
    st.session_state[_PRICING_DIALOG_OPEN_KEY] = False


@st.dialog(" ", width="large", on_dismiss=_on_pricing_dismiss)
def _pricing_dialog(strings: Strings) -> None:
    """Show the current model pricing catalog as a read-only Markdown table."""
    st.markdown(
        f"{_PRICING_DIALOG_CSS}\n\n**{strings['BASIC_QA_PRICING_TITLE']}**",
        unsafe_allow_html=True,
    )
    st.markdown(render_pricing_markdown())


def _render_token_summary(strings: Strings, records: Sequence[BasicQaRecord]) -> None:
    """Render the collapsible Token usage panel: token totals plus budget metrics.

    Five equal metrics, each a token/count on top and its USD figure below (a
    neutral delta): Input / Output / Total, then the static Quota (token budget /
    cost budget) and Usage (tokens ÷ token quota, floored; cost ÷ cost quota).
    Display-only: neither quota blocks a send. A nested Transaction history table
    breaks the cost down per request. Counts are thousands-separated and kept on
    one line (scoped CSS) so a six-figure value never wraps beside its icon.
    """
    totals = token_totals(records)
    quota = _settings.basic_rag_qa_session_token_quota
    cost_quota = _settings.basic_rag_qa_session_cost_quota
    percent = usage_percent(totals.total_tokens, quota)
    session_cost = _session_cost(records)
    cost_percent = cost_usage_percent(session_cost, cost_quota)
    with st.expander(strings["BASIC_QA_TOKEN_PANEL_TITLE"], expanded=False):
        st.markdown(_TOKEN_PANEL_CSS, unsafe_allow_html=True)
        input_col, output_col, total_col, quota_col, usage_col = st.columns(5)
        input_col.metric(
            strings["BASIC_QA_SUMMARY_INPUT_LABEL"],
            f"{totals.input_tokens:,}",
            delta=_cost_delta(strings, _session_input_cost(records)),
            delta_color="off",
            icon=":material/login:",
        )
        output_col.metric(
            strings["BASIC_QA_SUMMARY_OUTPUT_LABEL"],
            f"{totals.output_tokens:,}",
            delta=_cost_delta(strings, _session_output_cost(records)),
            delta_color="off",
            icon=":material/logout:",
        )
        total_col.metric(
            strings["BASIC_QA_SUMMARY_TOTAL_LABEL"],
            f"{totals.total_tokens:,}",
            delta=_cost_delta(strings, session_cost),
            delta_color="off",
            icon=":material/functions:",
        )
        quota_col.metric(
            strings["BASIC_QA_SUMMARY_QUOTA_LABEL"],
            f"{quota:,}",
            delta=f"${cost_quota:,.2f}",
            delta_color="off",
            icon=":material/data_usage:",
        )
        usage_col.metric(
            strings["BASIC_QA_SUMMARY_USAGE_LABEL"],
            f"{percent}%",
            delta=None if cost_percent is None else f"{cost_percent:.2f}%",
            delta_color="off",
            icon=":material/percent:",
        )
        _render_transaction_history(strings, records)


def _transaction_rows(
    strings: Strings, records: Sequence[BasicQaRecord]
) -> list[dict[str, object]]:
    """Build the Transaction history rows, newest first, one per recorded request.

    Only answer-generation requests are recorded today; the Process column names
    the step so future process types (e.g. semantic search) can share the table.
    """
    na = strings["BASIC_QA_TOKEN_NA"]
    process = strings["BASIC_QA_PROCESS_ANSWER_GEN"]
    ordered = sorted(records, key=lambda record: record.timestamp_utc, reverse=True)
    rows: list[dict[str, object]] = []
    for record in ordered:
        price = get_model_price(record.llm_model)
        rows.append(
            {
                strings["BASIC_QA_TXN_COL_TIME"]: local_time_label(
                    record.timestamp_utc, abbreviate_month=True
                ),
                strings["BASIC_QA_HISTORY_META_MODEL"]: record.llm_model or "—",
                strings["BASIC_QA_TXN_COL_PROVIDER"]: price.provider if price else na,
                strings["BASIC_QA_TXN_COL_CLOUD"]: price.cloud_service if price else na,
                strings["BASIC_QA_SUMMARY_INPUT_LABEL"]: na
                if record.input_tokens is None
                else record.input_tokens,
                strings["BASIC_QA_SUMMARY_OUTPUT_LABEL"]: na
                if record.output_tokens is None
                else record.output_tokens,
                strings["BASIC_QA_SUMMARY_TOTAL_LABEL"]: na
                if record.total_tokens is None
                else record.total_tokens,
                strings["BASIC_QA_TXN_COL_COST"]: _format_cost(strings, _record_cost(record)),
                strings["BASIC_QA_TXN_COL_PROCESS"]: process,
            }
        )
    return rows


def _transaction_csv(rows: list[dict[str, object]]) -> str:
    """Serialize the Transaction history rows to CSV text (localized headers)."""
    if not rows:
        return ""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _render_cost_disclaimer(strings: Strings) -> None:
    """Caption below the table noting costs are estimates, citing the price sources."""
    captured = pricing_captured()
    sources = pricing_sources()
    if not captured and not sources:
        return
    links = ", ".join(f"[{source.name}]({source.url})" for source in sources)
    st.caption(
        strings["BASIC_QA_COST_DISCLAIMER"].format(
            date=captured or strings["BASIC_QA_TOKEN_NA"],
            sources=links or strings["BASIC_QA_TOKEN_NA"],
        )
    )


def _render_transaction_history(strings: Strings, records: Sequence[BasicQaRecord]) -> None:
    """Render the collapsed per-request token log nested in the Token usage panel."""
    with st.expander(strings["BASIC_QA_TXN_PANEL_TITLE"], expanded=False):
        rows = _transaction_rows(strings, records)
        if not rows:
            st.caption(strings["BASIC_QA_TXN_EMPTY"])
            return
        with st.container(horizontal=True, horizontal_alignment="right"):
            if st.button(
                strings["BASIC_QA_PRICING_LABEL"],
                icon=":material/request_quote:",
                help=strings["BASIC_QA_PRICING_HELP"],
            ):
                st.session_state[_PRICING_DIALOG_OPEN_KEY] = True
            st.download_button(
                strings["BASIC_QA_TXN_CSV_LABEL"],
                data=_transaction_csv(rows),
                file_name=_TXN_CSV_FILENAME,
                mime="text/csv",
                icon=":material/download:",
                help=strings["BASIC_QA_TXN_CSV_HELP"],
            )
        st.dataframe(rows, hide_index=True, width="stretch")
        _render_cost_disclaimer(strings)


def _stats_caption(
    strings: Strings, usage: TokenUsage | None, seconds: float, model_label: str
) -> str:
    """Build the per-answer model + token + latency caption, n/a for missing counts."""
    na = strings["BASIC_QA_TOKEN_NA"]
    return strings["BASIC_QA_ANSWER_STATS"].format(
        model=model_label,
        input=na if usage is None or usage.input_tokens is None else usage.input_tokens,
        output=na if usage is None or usage.output_tokens is None else usage.output_tokens,
        total=na if usage is None or usage.total_tokens is None else usage.total_tokens,
        seconds=f"{seconds:.1f}",
    )


def _history_stats_caption(strings: Strings, record: BasicQaRecord) -> str:
    """Build the model + token + latency caption for a stored answer in history."""
    na = strings["BASIC_QA_TOKEN_NA"]
    return strings["BASIC_QA_ANSWER_STATS"].format(
        model=chat_model_info_for(record.llm_model).label or record.llm_model,
        input=na if record.input_tokens is None else record.input_tokens,
        output=na if record.output_tokens is None else record.output_tokens,
        total=na if record.total_tokens is None else record.total_tokens,
        seconds=f"{record.latency_seconds:.1f}",
    )


def _apply_replay(strings: Strings, indexes: Sequence[IndexRef], replay: dict) -> None:
    """Pre-fill the Step 4 widgets from a stored history record before they render."""
    st.session_state[_QUESTION_KEY] = str(replay.get("question", ""))
    st.session_state[_PROMPT_KEY] = str(replay.get("prompt", ""))
    st.session_state[_TOP_RESULTS_KEY] = int(replay.get("top_k", _DEFAULT_TOP_RESULTS))
    options, _ = chat_model_choices()
    model = str(replay.get("llm_model", ""))
    if model in options:
        st.session_state[_MODEL_KEY] = model
    tones, _ = tone_choices()
    tone = str(replay.get("tone", ""))
    if tone in tones:
        st.session_state[_TONE_KEY] = tone
    ref = find_index(indexes, str(replay.get("index_folder", "")), str(replay.get("index_run", "")))
    if ref is not None:
        st.session_state[_INDEX_KEY] = index_option_label(strings, ref)
    st.session_state[_ANSWER_KEY] = None
    st.session_state[_STATS_KEY] = None
    st.session_state[_FOCUS_PROMPT_KEY] = True


def _tokens_value(strings: Strings, record: BasicQaRecord) -> str:
    na = strings["BASIC_QA_TOKEN_NA"]
    return strings["BASIC_QA_HISTORY_TOKENS_VALUE"].format(
        input=na if record.input_tokens is None else record.input_tokens,
        output=na if record.output_tokens is None else record.output_tokens,
        total=na if record.total_tokens is None else record.total_tokens,
    )


def _history_grid(strings: Strings, record: BasicQaRecord) -> str:
    """Build the 4-column label/value grid summarising one history record."""
    rows = [
        (strings["BASIC_QA_HISTORY_LABEL_TIME"], local_time_label(record.timestamp_utc)),
        (strings["BASIC_QA_HISTORY_META_INDEX_NAME"], record.index_folder),
        (strings["BASIC_QA_HISTORY_META_INDEX_DATE"], record.index_run),
        (strings["BASIC_QA_HISTORY_META_MODEL"], record.llm_model or "—"),
        (strings["BASIC_QA_HISTORY_META_TONE"], record.tone or "—"),
        (strings["BASIC_QA_HISTORY_META_TOP"], str(record.top_k)),
        (strings["BASIC_QA_HISTORY_META_TOKENS"], _tokens_value(strings, record)),
        (
            strings["BASIC_QA_HISTORY_META_TIME"],
            strings["BASIC_QA_HISTORY_SECONDS"].format(seconds=f"{record.latency_seconds:.1f}"),
        ),
    ]
    return kv_grid_html(rows, columns=4, margin_bottom=True)


def _render_basic_rag_qa_history(
    strings: Strings, session_root: Path, records: Sequence[BasicQaRecord]
) -> None:
    """Render the collapsible prompt history as tidy cards with replay + details.

    Each card leads with the question + a replay button (mirroring the Search
    history layout), then a collapsed Details expander (4-column grid) and a
    collapsed Prompt expander showing the exact prompt that was sent. Replaying a
    card reloads its question, prompt, and options back into the form.
    """
    with st.expander(strings["BASIC_QA_HISTORY_EXPANDER"], expanded=False):
        if not records:
            st.caption(strings["BASIC_QA_HISTORY_EMPTY"])
            return
        st.markdown(_HISTORY_ACTIONS_CSS, unsafe_allow_html=True)
        for position, record in enumerate(records):
            with st.container(border=True):
                head, actions = st.columns([0.8, 0.2], vertical_alignment="center")
                head.markdown(
                    stacked_label_value_html(
                        strings["BASIC_QA_HISTORY_LABEL_QUESTION"], record.question or "—"
                    ),
                    unsafe_allow_html=True,
                )
                with (
                    actions,
                    st.container(
                        horizontal=True,
                        horizontal_alignment="right",
                        gap="small",
                        key=f"basic_rag_qa_history_actions_{position}",
                    ),
                ):
                    pin_help = (
                        strings["BASIC_QA_HISTORY_UNPIN_HELP"]
                        if record.pinned
                        else strings["BASIC_QA_HISTORY_PIN_HELP"]
                    )
                    if st.button(
                        ":material/keep_off:" if record.pinned else ":material/keep:",
                        key=f"basic_rag_qa_history_pin_{position}",
                        help=pin_help,
                        type="primary" if record.pinned else "secondary",
                    ):
                        set_basic_rag_qa_pinned(
                            session_root, record.timestamp_utc, not record.pinned
                        )
                        st.rerun()
                    if st.button(
                        ":material/replay:",
                        key=f"basic_rag_qa_history_replay_{position}",
                        help=strings["BASIC_QA_HISTORY_REPLAY_HELP"],
                    ):
                        st.session_state[_REPLAY_KEY] = asdict(record)
                        st.rerun()
                with st.expander(strings["BASIC_QA_HISTORY_DETAILS_EXPANDER"], expanded=False):
                    st.markdown(_history_grid(strings, record), unsafe_allow_html=True)
                with st.expander(strings["BASIC_QA_HISTORY_PROMPT_EXPANDER"], expanded=False):
                    st.code(record.prompt or "—", language="markdown", wrap_lines=True)
                with st.expander(strings["BASIC_QA_HISTORY_ANSWER_EXPANDER"], expanded=False):
                    st.write(record.answer or "—")
                    st.caption(_history_stats_caption(strings, record))
