"""Progress / live-stats UI for the Streamlit app.

Renders the crawl and vector-index live areas: status boxes, cumulative progress
charts, active/next URL rows, timing, the activity log, and the vector-index
status panel. Extracted from ``streamlit_app.py`` so the shell keeps only
navigation, session, and job orchestration. Event *draining* and app-wide toasts
stay in the shell (``_drain_job_events``, ``_emit_crawl_progress_toasts``,
``_render_crawl_event_loop``); this module only renders. ``_apply_vector_index_event``
lives here because the vector live-area fragment both drains and renders in one
pass; the shell imports it for session reattach. No import cycle: nothing here
imports ``streamlit_app``. ``st.session_state`` is a global singleton, so these
renderers read/write the same state the shell owns.
"""

from __future__ import annotations

import html
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import altair as alt
import streamlit as st
from crawl4md.naming import crawl_folder_name

from app_support.app_runtime import (
    _ACTIVE_JOB_STATES,
    _CHART_AREA_OPACITY,
    _CHART_COLOR_DISCOVERED,
    _CHART_COLOR_FAILED,
    _CHART_COLOR_LIMIT,
    _CHART_COLOR_SUCCESSFUL,
    _CHART_CUMULATIVE_INTERPOLATE,
    _CHART_LIMIT_LINE_WIDTH,
    _DEFAULT_LANGUAGE,
    _PROGRESS_CHART_HEIGHT,
    _STATE_CANCEL_REQUESTED,
    _STATE_CANCELLED,
    _STATE_COMPLETED,
    _STATE_FAILED,
    _STATE_IDLE,
    _STATE_RUNNING,
    _STATE_STOPPED,
    _STATUS_ROW_STYLE,
    _active_file_root,
    _auto_refresh_fragment,
    _crawl_job_active,
    _vector_job_active,
)
from app_support.crawl.form_defaults import DEFAULT_LIMIT
from app_support.i18n import Strings, get_strings, localize_message
from app_support.progress_chart import (
    PROGRESS_CHART_TIME_UNIT_HOUR,
    PROGRESS_CHART_TIME_UNIT_MINUTE,
    PROGRESS_CHART_TIME_UNIT_SECOND,
    load_persisted_progress_history,
    prefer_persisted_history,
    prepare_cumulative_chart_display_rows,
    prepare_cumulative_chart_rows,
    progress_chart_time_unit_seconds,
    select_progress_chart_time_unit,
)
from app_support.support import (
    activity_log_path,
    elapsed_time_display,
    format_eta_seconds,
    format_status_row,
    format_status_url_preview,
    normalize_event_urls,
    read_recent_lines,
)
from app_support.vector_index.vector_index_jobs import drain_events as drain_vector_events
from app_support.vector_index.vector_index_jobs import (
    embedding_error_hint_key,
    vector_eta_seconds,
    vector_progress_fraction,
    vector_stage_label_key,
)
from app_support.vector_index.vector_index_jobs import (
    job_state_from_event as vector_job_state_from_event,
)

_URL_RE = re.compile(r"https?://[^\s<>\"]+")
_STATUS_SUB_NEXT_ROW_STYLE = f"{_STATUS_ROW_STYLE};padding-bottom:0.5rem"
_STATUS_NEXT_ROW_STYLE = f"{_STATUS_ROW_STYLE};padding-bottom:1rem"
_VECTOR_TERMINAL_STATES = frozenset({_STATE_CANCELLED, _STATE_COMPLETED, _STATE_FAILED})
_CHART_CUMULATIVE_TITLE_KEYS = {
    PROGRESS_CHART_TIME_UNIT_SECOND: "CHART_CUMULATIVE_TITLE_SECOND",
    PROGRESS_CHART_TIME_UNIT_MINUTE: "CHART_CUMULATIVE_TITLE_MINUTE",
    PROGRESS_CHART_TIME_UNIT_HOUR: "CHART_CUMULATIVE_TITLE_HOUR",
}


def _apply_vector_index_event(event: Mapping[str, Any]) -> None:
    event_name = str(event.get("event", ""))
    st.session_state.vector_index_state = vector_job_state_from_event(event_name)
    if event_name == "progress":
        if "stage" in event:
            st.session_state.vector_index_stage = str(event["stage"])
        else:
            st.session_state.vector_index_progress = {
                "processed": int(event.get("processed_chunks", 0)),
                "total": int(event.get("total_chunks", 0)),
            }
    elif st.session_state.vector_index_state in _VECTOR_TERMINAL_STATES:
        st.session_state.vector_index_result = {
            "state": st.session_state.vector_index_state,
            "indexed_file_count": int(event.get("indexed_file_count", 0)),
            "indexed_chunk_count": int(event.get("indexed_chunk_count", 0)),
            "skipped_file_count": int(event.get("skipped_file_count", 0)),
            "warnings": list(event.get("warnings", [])),
            "errors": list(event.get("errors", [])),
        }


def _render_vector_index_timing(strings: Mapping[str, Any], processed: int, total: int) -> None:
    """Render elapsed time (docked left) and the finish estimate (docked right)."""
    started_at = st.session_state.get("vector_index_started_at")
    if started_at is None:
        return
    elapsed = datetime.now(timezone.utc) - started_at
    elapsed_text = str(elapsed).split(".")[0]
    eta_text = format_eta_seconds(
        vector_eta_seconds(processed, total, elapsed.total_seconds()), strings
    )
    st.markdown(
        f'<div style="{_STATUS_ROW_STYLE}">'
        f"<span>{strings['STATUS_ELAPSED'].format(elapsed=elapsed_text)}</span>"
        f"<span>{eta_text}</span></div>",
        unsafe_allow_html=True,
    )


def _render_vector_index_status(strings: Mapping[str, Any]) -> None:
    state = st.session_state.vector_index_state
    if state in {_STATE_RUNNING, _STATE_CANCEL_REQUESTED}:
        progress = st.session_state.vector_index_progress
        total = int(progress.get("total", 0))
        processed = int(progress.get("processed", 0))
        stage = st.session_state.get("vector_index_stage", "")
        fraction_label = vector_progress_fraction(stage, processed, total)
        if fraction_label is not None:
            fraction, label_key = fraction_label
            label = strings[label_key].format(processed=processed, total=total)
            with st.container(gap=None):
                st.markdown(
                    f'<div style="{_STATUS_SUB_NEXT_ROW_STYLE}">'
                    f"<span>{label}</span><span>{fraction * 100:.0f}%</span></div>",
                    unsafe_allow_html=True,
                )
                st.progress(fraction)
                _render_vector_index_timing(strings, processed, total)
                st.markdown(
                    f'<div style="{_STATUS_SUB_NEXT_ROW_STYLE}"><span>&nbsp;</span></div>',
                    unsafe_allow_html=True,
                )
        else:
            st.info(strings[vector_stage_label_key(stage)])
        return
    result = st.session_state.vector_index_result
    if not result:
        return
    result_state = result.get("state", "")
    if result_state == _STATE_COMPLETED:
        st.success(
            strings["VEC_RESULT_SUCCESS"].format(
                files=result.get("indexed_file_count", 0),
                chunks=result.get("indexed_chunk_count", 0),
            )
        )
    elif result_state == _STATE_CANCELLED:
        st.warning(strings["VEC_RESULT_CANCELLED"])
    else:
        st.error(strings["VEC_RESULT_FAILED"])
    if result.get("skipped_file_count"):
        st.caption(strings["VEC_RESULT_SKIPPED"].format(count=result["skipped_file_count"]))
    warnings = result.get("warnings") or []
    if warnings:
        with st.expander(strings["VEC_RESULT_WARNINGS_LABEL"], expanded=True):
            for warning in warnings:
                st.write(f"- {localize_message(strings, warning)}")
    errors = result.get("errors") or []
    if errors:
        with st.expander(strings["VEC_RESULT_ERRORS_LABEL"], expanded=True):
            for error in errors:
                st.write(f"- {localize_message(strings, error)}")
        hint_key = embedding_error_hint_key(errors)
        if hint_key:
            st.info(strings[hint_key])


def _vector_index_live_area_body() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.get("vector_index_job")
    if job is not None:
        for event in drain_vector_events(job):
            _apply_vector_index_event(event)
        if (
            not job.thread.is_alive()
            and st.session_state.vector_index_state in _VECTOR_TERMINAL_STATES
        ):
            st.session_state.vector_index_job = None
            st.rerun()
    expanded = st.session_state.vector_index_state in _ACTIVE_JOB_STATES or bool(
        st.session_state.vector_index_result
    )
    with st.expander(strings["VEC_PROGRESS_HEADER"], expanded=expanded):
        _render_vector_index_status(strings)


def _render_vector_index_live_area() -> None:
    """Auto-rerun the vector-index live area only while a vector job is active."""
    _auto_refresh_fragment(_vector_index_live_area_body, active=_vector_job_active())


def _render_crawl_timing(strings: Mapping[str, Any]) -> None:
    """Render crawl elapsed time (docked left) and the ETA (docked right).

    Sits directly under the crawl progress bar, mirroring the vector-index timing
    row. Elapsed comes from the run's start (frozen once the job ends); the ETA is
    the worker's own estimate and shows only while the crawl is active.
    """
    elapsed_str = elapsed_time_display(
        started_at=st.session_state.started_at,
        job_state=st.session_state.job_state,
        frozen_elapsed=st.session_state.last_elapsed,
    )
    if not elapsed_str:
        return
    right = ""
    if st.session_state.job_state in {_STATE_RUNNING, _STATE_CANCEL_REQUESTED}:
        eta_seconds_raw = st.session_state.latest_event.get("eta_remaining_seconds")
        eta_seconds = float(eta_seconds_raw) if eta_seconds_raw is not None else None
        right = format_eta_seconds(eta_seconds, strings)
    st.markdown(
        f'<div style="{_STATUS_ROW_STYLE}">'
        f"<span>{strings['STATUS_ELAPSED'].format(elapsed=elapsed_str)}</span>"
        f"<span>{right}</span></div>"
        f'<div style="{_STATUS_ROW_STYLE};font-size:0.25rem;"><span>&nbsp;</span></div>',
        unsafe_allow_html=True,
    )


def render_progress_and_files(
    processed: int,
    successful: int,
    failed: int,
    discovered: int,
    limit: int,
    state: str,
) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    denominator = discovered if discovered > 0 else max(limit, 1)
    covered_unique_pages = min(processed, denominator)
    progress_ratio = min(max(covered_unique_pages / denominator, 0.0), 1.0)
    progress_pct = progress_ratio * 100
    extra_attempts = max(processed - discovered, 0) if discovered > 0 else 0
    normalized_state = (state or "unknown").strip().lower()
    is_retry_phase = extra_attempts > 0 and normalized_state in {
        _STATE_RUNNING,
        _STATE_CANCEL_REQUESTED,
    }
    state_label = strings["STATE_LABELS"].get(
        normalized_state, normalized_state.replace("_", " ").title()
    )
    state_icon = {
        _STATE_IDLE: "🟡",
        _STATE_RUNNING: "🟢",
        _STATE_FAILED: "🔴",
        _STATE_COMPLETED: "✅",
        _STATE_CANCEL_REQUESTED: "🟠",
        _STATE_STOPPED: "⏹️",
    }.get(normalized_state, "⚠️")
    denominator_label = (
        strings["DENOM_DISCOVERED"].format(n=f"{discovered:,}")
        if discovered > 0
        else strings["DENOM_LIMIT"].format(n=f"{limit:,}")
    )
    processed_delta = (
        strings["METRIC_PROCESSED_DELTA_RETRY"].format(n=f"{extra_attempts:,}")
        if extra_attempts > 0
        else strings["METRIC_PROCESSED_DELTA"].format(n=f"{processed:,}")
    )
    progress_status = (
        strings["PROGRESS_RETRYING"]
        if is_retry_phase
        else f"{progress_pct:.2f}% {strings['PROGRESS_COMPLETE']}"
    )
    attempts_label = strings["PROGRESS_ATTEMPTS"].format(n=f"{processed:,}")

    with st.container():
        # Keep the attempts/percent status row tight against the progress bar
        # (gap=None + the sub row's smaller bottom padding), mirroring the vector
        # index "Indexing progress" panel. The metrics below keep the normal gap.
        with st.container(gap=None):
            st.markdown(
                f'<div style="{_STATUS_SUB_NEXT_ROW_STYLE}">'
                f"<span>📄 {attempts_label} / {denominator_label}</span>"
                f"<span>⏳ {progress_status}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )
            st.progress(progress_ratio)
            _render_crawl_timing(strings)

        row1 = st.columns(3)
        row1[0].metric(
            label=strings["METRIC_PROCESSED_LABEL"],
            value=f"{processed:,}",
            delta=processed_delta,
            delta_color="off",
            help=strings["METRIC_PROCESSED_TOOLTIP"],
            icon=":material/checklist:",
            border=True,
        )
        row1[1].metric(
            label=strings["METRIC_SUCCESSFUL_LABEL"],
            value=f"{successful:,}",
            delta=strings["METRIC_SUCCESSFUL_DELTA"].format(n=f"{successful:,}"),
            delta_color="normal",
            help=strings["METRIC_SUCCESSFUL_TOOLTIP"],
            icon=":material/check_circle:",
            border=True,
        )
        row1[2].metric(
            label=strings["METRIC_FAILED_LABEL"],
            value=f"{failed:,}",
            delta=strings["METRIC_FAILED_DELTA"].format(n=f"{failed:,}"),
            delta_color="inverse",
            help=strings["METRIC_FAILED_TOOLTIP"],
            icon=":material/error:",
            border=True,
        )

        row2 = st.columns(3)
        discovered_remaining = max(limit - discovered, 0)
        limit_reached = discovered >= limit
        limit_status_delta = (
            strings["METRIC_LIMIT_DELTA_REACHED"]
            if limit_reached
            else strings["METRIC_LIMIT_DELTA_MORE"]
        )
        row2[0].metric(
            label=strings["METRIC_DISCOVERED_LABEL"],
            value=f"{discovered:,}",
            delta=strings["METRIC_DISCOVERED_DELTA"].format(
                n=f"{discovered:,}", m=f"{discovered_remaining:,}"
            ),
            delta_color="normal",
            help=strings["METRIC_DISCOVERED_TOOLTIP"],
            icon=":material/manage_search:",
            border=True,
        )
        row2[1].metric(
            label=strings["METRIC_LIMIT_LABEL"],
            value=f"{limit:,}",
            delta=limit_status_delta,
            delta_color="off",
            help=strings["METRIC_LIMIT_TOOLTIP"],
            icon=":material/flag:",
            border=True,
        )
        with row2[2]:
            if normalized_state == _STATE_RUNNING:
                label_text = html.escape(strings["METRIC_STATE_WORD"])
                value_text = html.escape(state_label)
                delta_text = html.escape(strings["METRIC_STATE_DELTA"])
                st.html(
                    "<style>"
                    "@keyframes crawl4md-spin{to{transform:rotate(360deg)}}"
                    ".crawl4md-run-card{border:1px solid var(--st-border-color, rgba(128,128,128,0.35));border-radius:0.5rem;padding:1rem;}"
                    ".crawl4md-run-label{display:flex;align-items:center;gap:6px;font-size:0.875rem;opacity:0.7;margin-bottom:0.25rem;}"
                    ".crawl4md-run-spinner{width:11px;height:11px;border:1.5px solid var(--st-border-color, rgba(128,128,128,0.35));border-top-color:currentColor;border-radius:50%;animation:crawl4md-spin 0.8s linear infinite;flex-shrink:0;}"
                    ".crawl4md-run-value{font-size:2.25rem;font-weight:400;line-height:normal;margin-bottom:0.25rem;}"
                    ".crawl4md-run-delta{font-size:0.875rem;opacity:0.7;}"
                    f"</style><div class='crawl4md-run-card'>"
                    f"<div class='crawl4md-run-label'><div class='crawl4md-run-spinner'></div><span>{label_text}</span></div>"
                    f"<div class='crawl4md-run-value'>{value_text}</div>"
                    f"<div class='crawl4md-run-delta'>&#8593; {delta_text}</div>"
                    f"</div>"
                )
            else:
                st.metric(
                    label=strings["METRIC_STATE_WORD"],
                    value=state_label,
                    delta=strings["METRIC_STATE_DELTA"],
                    delta_color="off",
                    help=strings["METRIC_STATE_TOOLTIP"],
                    icon=state_icon,
                    border=True,
                )

        if normalized_state == _STATE_FAILED:
            st.error(strings["BANNER_FAILED"])
        elif normalized_state == _STATE_CANCEL_REQUESTED:
            st.info(strings["BANNER_CANCEL_REQUESTED"])
        elif normalized_state == _STATE_STOPPED:
            st.info(strings["BANNER_STOPPED"])


def _render_status_boxes() -> None:
    latest = st.session_state.latest_event
    processed_pages = int(latest.get("processed_pages", 0) or 0)
    successful_pages = int(latest.get("successful_pages", 0) or 0)
    failed_pages = int(latest.get("failed_pages", 0) or 0)
    discovered_pages = int(latest.get("queued_discovered_urls", 0) or 0)
    limit = int(latest.get("limit", DEFAULT_LIMIT) or DEFAULT_LIMIT)
    render_progress_and_files(
        processed=processed_pages,
        successful=successful_pages,
        failed=failed_pages,
        discovered=discovered_pages,
        limit=limit,
        state=st.session_state.job_state,
    )


def _render_status_rows() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    latest = st.session_state.latest_event
    current_url = str(latest.get("current_url", ""))
    active_urls = normalize_event_urls(latest.get("active_urls", []))
    active_url_count = max(
        int(latest.get("active_url_count", len(active_urls)) or 0),
        len(active_urls),
    )
    max_concurrent = max(
        int(latest.get("max_concurrent", active_url_count or 1) or 1),
        active_url_count,
    )
    # Elapsed + ETA now render under the progress bar (see _render_crawl_timing),
    # so these active/next URL rows show the URLs only.
    if active_url_count > 1:
        st.markdown(
            format_status_url_preview(
                label=strings["STATUS_ACTIVE_FETCHES"].format(
                    count=active_url_count,
                    max=max_concurrent,
                ),
                urls=active_urls,
                total_count=active_url_count,
                right_text="",
                style=_STATUS_ROW_STYLE,
                overflow_template=strings["STATUS_MORE_URLS"],
            ),
            unsafe_allow_html=True,
        )
    elif active_url_count == 1 and active_urls:
        st.markdown(
            format_status_row(
                url=active_urls[0],
                url_template=strings["STATUS_CRAWLING"],
                right_text="",
                style=_STATUS_ROW_STYLE,
            ),
            unsafe_allow_html=True,
        )
    elif current_url:
        st.markdown(
            format_status_row(
                url=current_url,
                url_template=strings["STATUS_CRAWLING"],
                right_text="",
                style=_STATUS_ROW_STYLE,
            ),
            unsafe_allow_html=True,
        )

    next_url = str(latest.get("next_url", ""))
    next_urls = normalize_event_urls(latest.get("next_urls", []))
    if not next_urls and next_url:
        next_urls = [next_url]
    next_url_count = max(
        int(latest.get("next_url_count", len(next_urls)) or 0),
        len(next_urls),
    )
    if next_url_count > 1:
        st.markdown(
            format_status_url_preview(
                label=strings["STATUS_NEXT_FETCHES"].format(count=next_url_count),
                urls=next_urls,
                total_count=next_url_count,
                right_text="",
                style=_STATUS_NEXT_ROW_STYLE,
                overflow_template=strings["STATUS_MORE_URLS"],
            ),
            unsafe_allow_html=True,
        )
    elif next_urls:
        st.markdown(
            format_status_row(
                url=next_urls[0] if next_urls else "",
                url_template=strings["STATUS_NEXT_URL"],
                right_text="",
                style=_STATUS_NEXT_ROW_STYLE,
            ),
            unsafe_allow_html=True,
        )

    if st.session_state.job_state == _STATE_FAILED:
        message = {
            "code": str(latest.get("error_code", "")),
            "text": str(latest.get("error", "")),
            "params": latest.get("error_params", {}),
        }
        st.error(localize_message(strings, message) or strings["ERROR_CRAWL_FAILED_FALLBACK"])


def _build_cumulative_progress_chart(
    rows: list[dict[str, float]], chart_strings: Strings
) -> alt.FacetChart | alt.LayerChart:
    color_scale = alt.Scale(
        domain=[
            chart_strings["CHART_SERIES_DISCOVERED"],
            chart_strings["CHART_SERIES_SUCCESSFUL"],
            chart_strings["CHART_SERIES_FAILED"],
            chart_strings["CHART_SERIES_LIMIT"],
        ],
        range=[
            _CHART_COLOR_DISCOVERED,
            _CHART_COLOR_SUCCESSFUL,
            _CHART_COLOR_FAILED,
            _CHART_COLOR_LIMIT,
        ],
    )
    color = alt.Color(
        "series:N",
        scale=color_scale,
        legend=alt.Legend(title=None),
    )
    x = alt.X("elapsed_time:Q", title="")

    discovered = (
        alt.Chart(
            alt.Data(
                values=[{**row, "series": chart_strings["CHART_SERIES_DISCOVERED"]} for row in rows]
            )
        )
        .mark_area(
            opacity=_CHART_AREA_OPACITY, interpolate=_CHART_CUMULATIVE_INTERPOLATE, strokeOpacity=0
        )
        .encode(
            x=x,
            y=alt.Y("discovered_pages:Q", title=""),
            color=color,
        )
    )
    successful = (
        alt.Chart(
            alt.Data(
                values=[{**row, "series": chart_strings["CHART_SERIES_SUCCESSFUL"]} for row in rows]
            )
        )
        .mark_area(
            opacity=_CHART_AREA_OPACITY, interpolate=_CHART_CUMULATIVE_INTERPOLATE, strokeOpacity=0
        )
        .encode(
            x=x,
            y=alt.Y("successful_pages:Q", title=""),
            color=color,
        )
    )
    failed = (
        alt.Chart(
            alt.Data(
                values=[{**row, "series": chart_strings["CHART_SERIES_FAILED"]} for row in rows]
            )
        )
        .mark_area(
            opacity=_CHART_AREA_OPACITY, interpolate=_CHART_CUMULATIVE_INTERPOLATE, strokeOpacity=0
        )
        .encode(
            x=x,
            y=alt.Y("processed_pages:Q", title=""),
            y2="successful_pages:Q",
            color=color,
        )
    )
    limit = (
        alt.Chart(
            alt.Data(
                values=[{**row, "series": chart_strings["CHART_SERIES_LIMIT"]} for row in rows]
            )
        )
        .mark_line(
            strokeWidth=_CHART_LIMIT_LINE_WIDTH,
            interpolate=_CHART_CUMULATIVE_INTERPOLATE,
        )
        .encode(
            x=x,
            y=alt.Y("page_limit:Q", title=""),
            color=color,
        )
    )

    return (
        alt.layer(discovered, successful, failed, limit)
        .properties(
            height=_PROGRESS_CHART_HEIGHT,
            padding={"top": 0, "right": 0, "bottom": 50, "left": 0},
        )
        .configure_legend(
            orient="none",
            direction="horizontal",
            legendX=alt.ExprRef("(width - 312) / 2"),
            legendY=alt.ExprRef("height + 30"),
        )
    )


def _render_progress_charts() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    live_history = st.session_state.get("progress_chart_history")
    if not isinstance(live_history, list):
        live_history = []

    persisted_history = load_persisted_progress_history(_active_file_root())
    selected_history = prefer_persisted_history(live_history, persisted_history)
    cumulative_rows = prepare_cumulative_chart_rows(selected_history)
    if not cumulative_rows:
        return

    time_unit = select_progress_chart_time_unit(selected_history)
    time_unit_seconds = progress_chart_time_unit_seconds(time_unit)

    cumulative_chart_rows = prepare_cumulative_chart_display_rows(
        cumulative_rows,
        time_unit_seconds=time_unit_seconds,
    )
    st.markdown(
        f'<p style="font-size:0.875rem;opacity:0.6;margin:0;padding:0">{strings[_CHART_CUMULATIVE_TITLE_KEYS[time_unit]]}</p>',
        unsafe_allow_html=True,
    )
    st.altair_chart(
        _build_cumulative_progress_chart(cumulative_chart_rows, strings),
        width="stretch",
    )


def _linkify_log_line(line: str) -> str:
    escaped = html.escape(line)
    return _URL_RE.sub(
        lambda m: (
            f'<a href="{m.group()}" target="_blank" rel="noopener noreferrer">{m.group()}</a>'
        ),
        escaped,
    )


def _render_activity_log() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    log_path = activity_log_path(_active_file_root())
    max_lines = int(st.session_state.activity_log_size)
    lines = read_recent_lines(log_path, max_lines=max_lines) if log_path else []
    st.session_state.activity_log_latest_line = lines[-1] if lines else None
    if lines:
        rows_html = "".join(
            f"<div style='padding:4px 8px;border-bottom:1px solid rgba(150,150,150,0.35);font-size:14px;font-family:sans-serif'>{_linkify_log_line(line)}</div>"
            for line in reversed(lines)
        )
        with st.expander(strings["ACTIVITY_LOG_HEADER"], expanded=False):
            st.html(
                f"<div style='height:200px;overflow-y:auto;border:1px solid rgba(150,150,150,0.35);border-radius:8px'>{rows_html}</div>"
            )


def _live_area_body() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    # Keep the panel open while a job runs and afterwards whenever there are stats,
    # so a finished/stopped crawl's final counts stay visible instead of collapsing
    # (latest_event holds the final event; it resets only on session switch / new crawl).
    live_expanded = st.session_state.job_state in _ACTIVE_JOB_STATES or bool(
        st.session_state.latest_event
    )
    with st.expander(_live_statistics_label(strings), expanded=live_expanded):
        _render_status_boxes()
        _render_progress_charts()
        _render_status_rows()
        _render_activity_log()


def _render_live_area() -> None:
    """Auto-rerun the crawl live area only while a crawl job is active."""
    _auto_refresh_fragment(_live_area_body, active=_crawl_job_active())


def _live_statistics_label(strings: Mapping[str, Any]) -> str:
    if st.session_state.job_state not in {_STATE_RUNNING, _STATE_CANCEL_REQUESTED}:
        return str(strings["PROGRESS_EXPANDER_LABEL"])
    crawl_id = str(st.session_state.get("crawl_id", "")).strip()
    if not crawl_id:
        crawl_id = str(st.session_state.latest_event.get("crawl_id", "")).strip()
    if not crawl_id:
        return str(strings["PROGRESS_EXPANDER_LABEL"])
    return str(strings["PROGRESS_EXPANDER_LABEL_ACTIVE"]).format(
        crawl_id=crawl_folder_name(crawl_id)
    )
