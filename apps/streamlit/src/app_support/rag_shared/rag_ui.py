"""Shared UI building blocks for the RAG pages (Steps 3-5).

Holds the page context the shell injects plus the render helpers common to
semantic search, QA, and conversational RAG: the index picker, the source list,
localized library messages, and chat-history conversion. Page modules stay thin
by composing these with ``rag_engine`` calls.
"""

from __future__ import annotations

import html
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
from artifact_store import LibraryMessage
from rag_engine import ChatTurn, RetrievedChunk
from vector_indexer import IndexManifest

from app_support.generated_files import format_local_datetime
from app_support.i18n import Strings, localize_message
from app_support.rag_shared.index_catalog import IndexRef

# Result-card tab identifiers. Streamlit always activates the first tab, so the
# configured default tab is rendered first to make it the initial selection.
_RESULT_TAB_RAW = "raw"
_RESULT_TAB_PREVIEW = "preview"

# Trim the default vertical gap above each result card's Raw/Preview tabs so the
# tabs sit closer to the chunk's caption.
_RESULT_CARD_CSS = (
    "<style>div[data-testid='stVerticalBlockBorderWrapper'] "
    "div[data-testid='stTabs']{margin-top:-0.75rem}</style>"
)

__all__ = [
    "RagPageContext",
    "find_index",
    "format_score_percent",
    "index_metadata_rows",
    "index_option_label",
    "kv_grid_html",
    "local_time_label",
    "ordered_result_tabs",
    "render_index_metadata",
    "render_messages",
    "render_model_caption",
    "render_result_cards",
    "render_results_panel",
    "render_sources",
    "result_detail_caption",
    "select_index",
    "sort_results_by_score",
    "stacked_label_value_html",
    "to_chat_turns",
]


@dataclass(frozen=True)
class RagPageContext:
    """Shell-provided services for the RAG content areas (Steps 3-5)."""

    default_language: str
    list_indexes: Callable[[], Sequence[IndexRef]]
    render_downloads: Callable[[], None]
    session_root: Callable[[], Path]


def index_option_label(strings: Strings, ref: IndexRef) -> str:
    """Return the picker label describing one index option."""
    return strings["RAG_INDEX_OPTION"].format(
        folder=ref.vector_folder,
        run=ref.run_name,
        model=ref.manifest.embedding_model_used or "?",
        chunks=ref.manifest.indexed_chunk_count,
    )


def select_index(strings: Strings, indexes: Sequence[IndexRef], *, key: str) -> IndexRef | None:
    """Render the index picker; return the chosen index or ``None`` when empty."""
    if not indexes:
        st.info(strings["RAG_NO_INDEX_HINT"])
        return None
    labels: dict[str, IndexRef] = {index_option_label(strings, ref): ref for ref in indexes}
    chosen = st.selectbox(
        strings["RAG_INDEX_LABEL"],
        options=list(labels),
        help=strings["RAG_INDEX_HELP"],
        key=key,
    )
    return labels.get(chosen)


def render_sources(
    strings: Strings,
    sources: Sequence[RetrievedChunk],
    *,
    header_key: str = "RAG_SOURCES_HEADER",
) -> None:
    """Render retrieved chunks as labelled, expandable source snippets."""
    if not sources:
        return
    st.markdown(f"**{strings[header_key]}**")
    for index, chunk in enumerate(sources, start=1):
        caption = strings["RAG_SOURCE_CAPTION"].format(
            source=chunk.source or "?", score=round(chunk.score, 3)
        )
        with st.expander(f"{index}. {caption}"):
            st.write(chunk.text)


def format_score_percent(score: float) -> int:
    """Clamp a 0-1 similarity to an integer percentage for display."""
    return round(max(0.0, min(1.0, score)) * 100)


def sort_results_by_score(chunks: Sequence[RetrievedChunk]) -> list[RetrievedChunk]:
    """Return chunks ordered by similarity score, highest first."""
    return sorted(chunks, key=lambda chunk: chunk.score, reverse=True)


def index_metadata_rows(strings: Strings, manifest: IndexManifest) -> list[tuple[str, str]]:
    """Return ordered (label, value) pairs describing an index for compact display."""
    return [
        (strings["SEARCH_META_CREATED"], _format_created_at(manifest.created_at)),
        (
            strings["SEARCH_META_MODEL"],
            manifest.embedding_model_used or manifest.embedding_model_requested or "—",
        ),
        (strings["SEARCH_META_LANGUAGE"], manifest.language or "—"),
        (
            strings["SEARCH_META_DIMENSION_CHUNKS"],
            f"{_value_or_dash(manifest.embedding_dimension)} / {manifest.indexed_chunk_count}",
        ),
        (
            strings["SEARCH_META_CHUNK_SIZE_OVERLAP"],
            f"{_value_or_dash(manifest.chunk_size)} / {_value_or_dash(manifest.chunk_overlap)}",
        ),
        (strings["SEARCH_META_FILES"], str(manifest.indexed_file_count)),
        (strings["SEARCH_META_SKIPPED"], str(manifest.skipped_file_count)),
        (strings["SEARCH_META_COLLECTION"], manifest.collection_name),
    ]


def _value_or_dash(value: object) -> str:
    return "—" if value is None else str(value)


def find_index(indexes: Sequence[IndexRef], folder: str, run: str) -> IndexRef | None:
    """Return the index matching *folder* + *run*, or ``None`` when none does."""
    return next(
        (ref for ref in indexes if ref.vector_folder == folder and ref.run_name == run), None
    )


def local_time_label(timestamp_utc: str, *, abbreviate_month: bool = False) -> str:
    """Convert a stored UTC timestamp to the app's local-time display label.

    Invalid values pass through unchanged; naive timestamps are treated as UTC.
    Set ``abbreviate_month`` for a three-letter month (e.g. '1 Jul 2026 15:39').
    """
    try:
        parsed = datetime.fromisoformat(timestamp_utc)
    except ValueError:
        return timestamp_utc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return format_local_datetime(parsed, abbreviate_month=abbreviate_month)


def kv_grid_html(
    rows: Sequence[tuple[str, str]],
    *,
    columns: int = 2,
    margin_bottom: bool = False,
    margin_top: bool = False,
) -> str:
    """Render label/value *rows* as a compact aligned grid (values right-aligned).

    *columns* is 2 (label | value, full width) or 4 (label value label value, denser),
    so the index Details panel and the Step 3/4 history cards share one tidy look.
    *margin_top* pulls the grid up to sit closer to the row above it.
    """
    cells = "".join(
        f'<div style="opacity:0.65">{html.escape(label)}</div>'
        f'<div style="text-align:right">{html.escape(value)}</div>'
        for label, value in rows
    )
    template = "auto 1fr auto 1fr" if columns == 4 else "auto 1fr"
    extra = ""
    if margin_top:
        extra += ";margin-top:-0.5rem"
    if margin_bottom:
        extra += ";margin-bottom:1rem"
    return (
        f'<div style="display:grid;grid-template-columns:{template};'
        f'gap:2px 1.5rem;font-size:0.875rem{extra}">{cells}</div>'
    )


def stacked_label_value_html(label: str, value: str) -> str:
    """Build a dim-gray label stacked tightly above a single-line value.

    Matches the kv-grid label style (dim, 0.875rem) and clips the value to one
    line with an ellipsis (full text on hover), so the Search history card's
    question label + value stay within the replay button's height.
    """
    return (
        '<div style="display:flex;flex-direction:column;line-height:1.25;overflow:hidden;'
        'margin-top:-0.35rem">'
        f'<div style="opacity:0.65;font-size:0.875rem">{html.escape(label)}</div>'
        '<div style="font-weight:600;white-space:nowrap;overflow:hidden;'
        f'text-overflow:ellipsis" title="{html.escape(value)}">{html.escape(value)}</div>'
        "</div>"
    )


def _format_created_at(created_at: str | None) -> str:
    """Format an ISO-8601 manifest timestamp as a local-time label (— when absent).

    Reuses ``local_time_label`` so the index's Created value reads in the same local
    time as the Search history and Output Files sections.
    """
    return "—" if not created_at else local_time_label(created_at)


def result_detail_caption(strings: Strings, chunk: RetrievedChunk) -> str:
    """Build the per-result detail line: chunk id, character size, and language."""
    chunk_index = chunk.metadata.get("chunk_index", "?")
    parts = [
        strings["SEARCH_RESULT_ID"].format(id=f"{chunk.source or '?'}#{chunk_index}"),
        strings["SEARCH_RESULT_SIZE"].format(size=len(chunk.text)),
    ]
    language = chunk.metadata.get("language")
    if language:
        parts.append(strings["SEARCH_RESULT_LANGUAGE"].format(language=language))
    return " · ".join(parts)


def render_index_metadata(strings: Strings, index: IndexRef) -> None:
    """Show the selected index's manifest details as a compact 4-column grid."""
    grid = kv_grid_html(index_metadata_rows(strings, index.manifest), columns=4, margin_bottom=True)
    with st.expander(strings["SEARCH_META_HEADER"], expanded=False):
        st.markdown(grid, unsafe_allow_html=True)


def ordered_result_tabs(default_tab: str) -> tuple[str, str]:
    """Return the (first, second) result-tab order with *default_tab* first.

    Streamlit always activates the first tab, so placing the configured tab
    first makes it the initial selection. Unknown values fall back to raw-first.
    """
    if default_tab.strip().lower() == _RESULT_TAB_PREVIEW:
        return (_RESULT_TAB_PREVIEW, _RESULT_TAB_RAW)
    return (_RESULT_TAB_RAW, _RESULT_TAB_PREVIEW)


def render_result_cards(
    strings: Strings,
    chunks: Sequence[RetrievedChunk],
    *,
    default_tab: str = _RESULT_TAB_RAW,
) -> None:
    """Render ranked result cards (sorted highest-first) with no surrounding panel.

    Shared by the Step 3 results panel and the Step 4 search-results panel so both
    show identical hit cards. Each card shows a source + similarity header row with
    the chunk's id, size, and language beneath the title, then the chunk text in
    Raw/Preview tabs (the configured *default_tab* first). The first card carries
    the tab-gap CSS inline so it is not a standalone element that adds a spacer.
    """
    tab_order = ordered_result_tabs(default_tab)
    tab_labels = {
        _RESULT_TAB_RAW: strings["SEARCH_RESULT_TAB_RAW"],
        _RESULT_TAB_PREVIEW: strings["SEARCH_RESULT_TAB_PREVIEW"],
    }
    for rank, chunk in enumerate(sort_results_by_score(chunks), start=1):
        with st.container(border=True):
            title_col, score_col = st.columns([0.7, 0.3], vertical_alignment="center")
            # Fold the tab-gap CSS into the first card's title markdown so it is
            # not a standalone element that would add an empty spacer above the
            # first card — keeping the first card flush with the panel top.
            lead_css = _RESULT_CARD_CSS if rank == 1 else ""
            title_col.markdown(
                f"{lead_css}"
                f'<h4 style="margin:0;padding:0">'
                f"{html.escape(strings['SEARCH_RESULT_HEADER'].format(rank=rank, source=chunk.source or '?'))}"
                "</h4>",
                unsafe_allow_html=True,
            )
            title_col.markdown(
                f'<p style="opacity:0.6;font-size:0.875rem;margin:0;margin-bottom:0">'
                f"{html.escape(result_detail_caption(strings, chunk))}</p>",
                unsafe_allow_html=True,
            )
            score_col.markdown(
                f'<h4 style="text-align:right;margin:0">'
                f"{strings['SEARCH_RESULT_SIMILARITY']} {format_score_percent(chunk.score)}%</h4>",
                unsafe_allow_html=True,
            )
            tabs = st.tabs([tab_labels[key] for key in tab_order])
            for key, tab in zip(tab_order, tabs, strict=True):
                with tab, st.container(border=True):
                    if key == _RESULT_TAB_RAW:
                        st.code(chunk.text, language="markdown", wrap_lines=True)
                    else:
                        st.markdown(chunk.text)


def render_results_panel(
    strings: Strings,
    chunks: Sequence[RetrievedChunk],
    *,
    empty_hint: str,
    default_tab: str = _RESULT_TAB_RAW,
    expanded: bool = False,
) -> None:
    """Render search hits as ranked cards inside an always-present collapsible panel.

    The panel is a stable fixture: it renders even with no hits (showing *empty_hint*
    instead of cards) so the gap to the block below never shifts. When there are hits
    the title carries the match count; callers pass ``expanded=True`` right after a
    search so fresh results open at once.
    """
    ranked = sort_results_by_score(chunks)
    if not ranked:
        with st.expander(strings["SEARCH_RESULTS_PANEL"], expanded=expanded):
            st.caption(empty_hint)
        return
    label = strings["SEARCH_RESULTS_EXPANDER"].format(count=len(ranked))
    with st.expander(label, expanded=expanded):
        render_result_cards(strings, ranked, default_tab=default_tab)


def render_messages(
    strings: Strings,
    warnings: Sequence[LibraryMessage],
    errors: Sequence[LibraryMessage],
) -> None:
    """Localize and display library warnings (yellow) and errors (red)."""
    for warning in warnings:
        st.warning(localize_message(strings, warning.as_dict()))
    for error in errors:
        st.error(localize_message(strings, error.as_dict()))


def render_model_caption(strings: Strings, model_used: str | None) -> None:
    """Show which chat model produced the answer."""
    if model_used:
        st.caption(strings["RAG_MODEL_USED_CAPTION"].format(model=model_used))


def to_chat_turns(history: Sequence[dict]) -> list[ChatTurn]:
    """Convert stored chat messages into ``ChatTurn`` objects for retrieval."""
    return [ChatTurn(role=message["role"], content=message["content"]) for message in history]
