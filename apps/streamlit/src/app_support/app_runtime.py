"""Shared shell runtime for the Streamlit app.

Holds the settings-derived UI constants, the job-state vocabulary, and the shell
helper functions that both ``streamlit_app.py`` and the extracted UI modules
(``downloads_ui`` / ``progress_ui``) depend on. Living here breaks the import
cycle: the shell and the UI modules both import from ``app_runtime``; nothing
here imports ``streamlit_app``. ``st.session_state`` is a global singleton, so
the moved helpers read/write the same state as the shell.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st

from app_support.generated_files import build_download_tree
from app_support.log_context import get_log_session_id
from app_support.session_manager import ensure_within_root, session_dir
from app_support.settings import get_settings
from app_support.support import (
    DEFAULT_SESSION_LANGUAGE,
    CrawlJob,
    GeneratedFile,
    find_latest_crawl_dir,
    list_generated_files,
)
from app_support.vector_index.vector_index_jobs import VectorIndexJob

# ── Settings-derived + display constants ─────────────────────────────────────
_DOWNLOAD_LIMIT_BYTES = get_settings().ui_download_limit_mb * 1024 * 1024
_DOWNLOADS_REFRESH_INTERVAL = f"{get_settings().ui_downloads_refresh_sec}s"
_GENERATED_FILES_CACHE_TTL_SECONDS = 2.0
_DIALOG_PLACEHOLDER_TITLE = " "
_ICON_BUTTON_WIDTH_PX = 44
_LIVE_AREA_REFRESH_INTERVAL = f"{get_settings().ui_live_refresh_sec}s"
_PROGRESS_CHART_HEIGHT = 220
_CHART_CUMULATIVE_INTERPOLATE = "linear"
_CHART_COLOR_DISCOVERED = "#888888"
_CHART_COLOR_SUCCESSFUL = "#21C354"
_CHART_COLOR_FAILED = "#FF4B4B"
_CHART_COLOR_LIMIT = "#FACA2B"
_CHART_AREA_OPACITY = 0.45
_CHART_LIMIT_LINE_WIDTH = 2.0
_PREVIEW_DIALOG_WIDTH = "large"
# Adjust this percentage to resize the preview modal relative to the viewport.
_PREVIEW_DIALOG_VIEWPORT_PERCENT = 70
_PREVIEW_DIALOG_VIEWPORT_WIDTH = f"{_PREVIEW_DIALOG_VIEWPORT_PERCENT}vw"
_PREVIEW_DIALOG_VIEWPORT_HEIGHT = f"{_PREVIEW_DIALOG_VIEWPORT_PERCENT}vh"
_PREVIEW_DIALOG_SCOPE_CLASS = "crawl4md-preview-dialog-scope"
# Streamlit key on the preview modal's scrollable content container; the shared
# `scrollable_dialog_css` hook targets it to give the modal its own scrollbar.
_PREVIEW_DIALOG_CONTENT_KEY = "preview_dialog_content"
_PREVIEW_LIMIT_BYTES = get_settings().ui_preview_limit_kb * 1024
_PREVIEW_LIMIT_KIB = _PREVIEW_LIMIT_BYTES // 1024
_UTC_DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
_SESSIONS_ROOT = Path("outputs") / "streamlit_sessions"
_DEFAULT_LANGUAGE = DEFAULT_SESSION_LANGUAGE
# Shared status-row style used by both the progress panels and the file-preview
# dialog caption (two spans pushed to opposite edges of the row).
_STATUS_ROW_STYLE = "display:flex;justify-content:space-between;font-size:0.875rem;opacity:1"

# ── Job-state vocabulary (shared by the shell orchestration and the panels) ──
_STATE_CANCEL_REQUESTED = "cancel_requested"
_STATE_CANCELLED = "cancelled"
_STATE_COMPLETED = "completed"
_STATE_FAILED = "failed"
_STATE_IDLE = "idle"
_STATE_RUNNING = "running"
_STATE_STOPPED = "stopped"
_ACTIVE_JOB_STATES = frozenset({_STATE_RUNNING, _STATE_CANCEL_REQUESTED})
_TERMINAL_STATES = {_STATE_COMPLETED, _STATE_FAILED, _STATE_STOPPED}


# ── Session paths ────────────────────────────────────────────────────────────
def _session_root(session_id: str | None = None) -> Path:
    current_session_id = session_id or st.session_state.session_id
    if not current_session_id:
        return _SESSIONS_ROOT
    return session_dir(_SESSIONS_ROOT, current_session_id)


def _session_log_path() -> Path | None:
    """Route a log record to the active session's log file, or None before one.

    Reads the session id from the per-thread log context (set by the main script
    each run and by each background job in its own thread), so records route to
    the right session's file even from crawl/index worker threads. Returns None
    when no session is active yet, so startup logs go to stderr only.
    """
    session_id = get_log_session_id()
    if not session_id:
        return None
    return session_dir(_SESSIONS_ROOT, session_id) / get_settings().log_file


# ── Job liveness / runtime ───────────────────────────────────────────────────
def _job_is_alive(job: CrawlJob | None = None) -> bool:
    current_job = st.session_state.job if job is None else job
    return bool(current_job is not None and current_job.thread.is_alive())


def _crawl_job_active() -> bool:
    """Return True while the crawl job is running, cancelling, or still alive."""
    return _job_is_alive() or st.session_state.job_state in _ACTIVE_JOB_STATES


def _vector_job_active() -> bool:
    """Return True while the vector-index job is running, cancelling, or still alive."""
    job = st.session_state.get("vector_index_job")
    alive = job is not None and job.thread.is_alive()
    return alive or st.session_state.vector_index_state in _ACTIVE_JOB_STATES


def _files_actions_busy() -> bool:
    """Return True while a crawl or vector-index job is active.

    The Files & folders actions (Import / Export / Delete / Preview / Download)
    stay visible but disabled while either job runs, so a user cannot mutate the
    outputs that are being written mid-crawl or mid-index.
    """
    return _crawl_job_active() or _vector_job_active()


def _current_crawl_runtime() -> tuple[CrawlJob | None, str, bool, bool]:
    current_job = st.session_state.job
    current_state = st.session_state.job_state
    job_alive = _job_is_alive(current_job)
    fields_disabled = (
        current_state == _STATE_RUNNING and job_alive
    ) or current_state == _STATE_CANCEL_REQUESTED
    return current_job, current_state, job_alive, fields_disabled


def _current_vector_runtime() -> tuple[VectorIndexJob | None, str, bool, bool]:
    job = st.session_state.get("vector_index_job")
    state = st.session_state.vector_index_state
    job_alive = job is not None and job.thread.is_alive()
    fields_disabled = (state == _STATE_RUNNING and job_alive) or state == _STATE_CANCEL_REQUESTED
    return job, state, job_alive, fields_disabled


def _active_file_root() -> Path:
    session_folder = _session_root()
    active_output_dir = st.session_state.active_output_dir
    if active_output_dir:
        try:
            return ensure_within_root(session_folder, active_output_dir)
        except ValueError:
            pass
    job = st.session_state.job
    if job is not None and job.session_id == st.session_state.session_id:
        latest = find_latest_crawl_dir(job.output_base)
        if latest is not None:
            return ensure_within_root(session_folder, latest)
        return ensure_within_root(session_folder, job.output_base)
    return session_folder


# ── Auto-refresh fragment ────────────────────────────────────────────────────
def _auto_refresh_fragment(
    body: Callable[[], None],
    *,
    active: bool,
    interval: str = _LIVE_AREA_REFRESH_INTERVAL,
) -> None:
    """Render *body* as a fragment that auto-reruns only while *active*.

    Passing ``run_every=None`` while idle schedules no auto-rerun timer, so an
    idle or navigated-away page leaves no stale fragment timer to fire after a
    later full-app rerun (which otherwise logs a benign "fragment ... does not
    exist anymore" warning). Starting a job triggers a full-app rerun that
    re-registers the fragment with the polling interval.
    """
    st.fragment(run_every=interval if active else None)(body)()


# ── Cached generated-file discovery ──────────────────────────────────────────
@st.cache_data(ttl=_GENERATED_FILES_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_list_generated_files(
    session_root: str,
    search_root: str,
    download_limit_bytes: int,
    cache_token: tuple[float, int],
) -> list[GeneratedFile]:
    _ = cache_token  # Keeps token in st.cache_data's argument hash.
    return list_generated_files(
        Path(session_root),
        Path(search_root),
        download_limit_bytes=download_limit_bytes,
    )


@st.cache_data(ttl=_GENERATED_FILES_CACHE_TTL_SECONDS, show_spinner=False)
def _cached_download_tree(files: tuple[GeneratedFile, ...]) -> dict[str, Any]:
    return build_download_tree(list(files))
