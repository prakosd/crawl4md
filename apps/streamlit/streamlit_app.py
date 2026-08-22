from __future__ import annotations

import os

# Best-effort: prefer protobuf's pure-Python parser, which tolerates out-of-date
# ``*_pb2`` modules that the C/upb backend rejects with "Descriptors cannot be
# created directly" (seen when a newer protobuf is paired with stale generated code,
# e.g. via chromadb reached through vector_indexer). This only takes effect when
# this module is imported before protobuf; under ``streamlit run`` Streamlit imports
# protobuf first, so the reliable fix is the ``protobuf`` version pin in
# apps/streamlit/requirements.txt. Kept here for non-``streamlit run`` entry points,
# set before the module imports below (see E402 ignore).
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

# The offline embedding model (ChromaDB's bundled ONNX MiniLM) tokenizes through
# HuggingFace ``tokenizers``, whose Rust parallelism is unsafe across the forks
# Streamlit and Playwright perform — it prints a "process just got forked" warning
# and risks deadlocks. Default it off before any heavy import loads tokenizers;
# ``setdefault`` still lets an operator override it explicitly.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import html
import importlib
import sys
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

import streamlit as st
from artifact_store.crawl_results import list_crawl_result_files
from log4py import configure_logging, get_logger
from pydantic import ValidationError
from streamlit.components.v2 import component as component_v2
from vector_indexer import IndexingConfig

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _DIALOG_PLACEHOLDER_TITLE,
    _ICON_BUTTON_WIDTH_PX,
    _SESSIONS_ROOT,
    _STATE_CANCEL_REQUESTED,
    _STATE_CANCELLED,
    _STATE_COMPLETED,
    _STATE_FAILED,
    _STATE_IDLE,
    _STATE_RUNNING,
    _STATE_STOPPED,
    _TERMINAL_STATES,
    _auto_refresh_fragment,
    _crawl_job_active,
    _current_crawl_runtime,
    _current_vector_runtime,
    _session_log_path,
    _session_root,
)
from app_support.crawl.form_defaults import default_form_values
from app_support.dialog_ui import render_confirm_dialog
from app_support.downloads_ui import _render_downloads, _render_ready_result_panel
from app_support.focus import focus_widget
from app_support.i18n import CATALOG, Strings, get_strings
from app_support.log_context import set_log_session_id
from app_support.pages import (
    APP_PAGE_SPECS,
    DEFAULT_PAGE_ID,
    AppPageSpec,
    page_spec_by_nav_label,
)
from app_support.progress_chart import (
    append_live_progress_sample,
)
from app_support.progress_ui import (
    _apply_vector_index_event,
    _render_live_area,
    _render_vector_index_live_area,
)
from app_support.rag_shared.index_catalog import list_session_indexes
from app_support.rag_shared.rag_ui import RagPageContext
from app_support.session_manager import (
    SESSION_DIR_PREFIX,
    generate_vector_id,
    next_vector_sequence,
)
from app_support.settings import get_settings
from app_support.site_graph_3d.static_publish import remove_orrery_static
from app_support.support import (
    DEFAULT_ACTIVITY_LOG_SIZE,
    CrawlJob,
    SessionRecord,
    active_registry_session_ids,
    bootstrap_gate_state,
    build_configs,
    cleanup_old_sessions_with_lock,
    create_session_record,
    drain_events,
    generate_crawl_id,
    get_active_job_snapshot,
    job_state_from_event,
    latest_session_id,
    next_crawl_sequence,
    normalize_session_records,
    request_cancel,
    serialize_session_records,
    session_dir,
    session_exists,
    session_time_remaining,
    should_show_portfolio_modal,
    start_crawl_job,
    touch_session,
    validate_safe_id,
)
from app_support.vector_index.vector_index_jobs import (
    active_vector_registry_session_ids,
    get_active_vector_job_snapshot,
    start_vector_index_job,
)
from app_support.vector_index.vector_index_jobs import request_cancel as request_vector_cancel

_APP_DIR = Path(__file__).resolve().parent

# Load a local .env (e.g. AWS_*/OPENAI_API_KEY for Step 2 embeddings) when
# python-dotenv is installed. In Codespaces/CI these come from the real
# environment instead, so a missing package or file is not an error.
try:
    from dotenv import load_dotenv as _load_dotenv

    _load_dotenv(_APP_DIR.parents[1] / ".env")
except ImportError:
    pass


# Configure project-wide logging once per process, before any runtime work emits
# records. Only the project's own top-level loggers are configured, keeping
# third-party (chromadb, urllib3, playwright) noise out. The file destination is
# routed per record to the active session's log (see _session_log_path), so each
# session gets its own log under its folder; stderr stays global.
_PROJECT_LOGGER_NAMES = (
    "artifact_store",
    "crawl4md",
    "app_support",
    "rag_engine",
    "vector_indexer",
)


@st.cache_resource(show_spinner=False)
def _configure_app_logging() -> bool:
    settings = get_settings()
    configure_logging(
        level=settings.log_level,
        logger_names=_PROJECT_LOGGER_NAMES,
        log_file_router=_session_log_path,
    )
    return True


_configure_app_logging()
_logger = get_logger("app_support.app")

_VECTOR_INDEX_PAGE_ID = "vector_index"
_RAG_PAGE_IDS = ("semantic_search", "basic_rag_qa", "conversational_rag")
_DIALOG_LOAD_SESSION_TITLE = "Load Session"
_HOURS_PER_DAY = 24
_AUTHOR_NAME = "Danang Prakoso"
_AUTHOR_LINKEDIN_URL = "https://www.linkedin.com/in/prakosd"
_PROJECT_GITHUB_URL = "https://github.com/prakosd/rag-playground"
_README_URL = "https://github.com/prakosd/crawl4md/blob/master/README.md"
_STREAMLIT_README_URL = "https://github.com/prakosd/crawl4md/blob/master/apps/streamlit/README.md"
_LINKEDIN_ICON_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCA1MTIg"
    "NTEyJz48cmVjdCB3aWR0aD0nNTEyJyBoZWlnaHQ9JzUxMicgcng9JzcyJyBmaWxsPScjMEE3"
    "RUI3Jy8+PGNpcmNsZSBjeD0nMTQyJyBjeT0nMTQyJyByPSc0NCcgZmlsbD0nd2hpdGUnLz48"
    "cmVjdCB4PScxMDgnIHk9JzIwMicgd2lkdGg9JzY4JyBoZWlnaHQ9JzIxNCcgcng9JzEyJyBm"
    "aWxsPSd3aGl0ZScvPjxwYXRoIGZpbGw9J3doaXRlJyBkPSdNMjA1IDIwMmg2N3YzMWMxNS0y"
    "MyA0MC0zNSA3Mi0zNSA0OCAwIDgwIDMyIDgwIDEwMXYxMTdoLTY5VjMwN2MwLTM1LTEzLTUy"
    "LTQwLTUyLTI4IDAtNDIgMjAtNDIgNTh2MTAzaC02OHonLz48L3N2Zz4="
)
_GITHUB_ICON_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCA5OCA5"
    "Nic+PHBhdGggZmlsbD0nYmxhY2snIGZpbGwtcnVsZT0nZXZlbm9kZCcgZD0nTTQ4LjkgMEMyMS45"
    "IDAgMCAyMiAwIDQ5LjFjMCAyMS43IDE0IDQwLjEgMzMuNSA0Ni42IDIuNS41IDMuMy0xLjEgMy4z"
    "LTIuNCAwLTEuMi0uMS01LjItLjEtOS40LTEzLjYgMy0xNi41LTUuOS0xNi41LTUuOS0yLjIt"
    "NS43LTUuNC03LjItNS40LTcuMi00LjQtMyAuMy0zIC4zLTMgNC45LjMgNy41IDUuMSA3LjUgNS4x"
    "IDQuMyA3LjUgMTEuNCA1LjMgMTQuMiA0LjEuNC0zLjIgMS43LTUuMyAzLjEtNi41LTEwLjktMS4y"
    "LTIyLjMtNS41LTIyLjMtMjQuNCAwLTUuNCAxLjktOS44IDUtMTMuMi0uNS0xLjItMi4yLTYuMy41"
    "LTEzIDAgMCA0LjEtMS4zIDEzLjQgNSAzLjktMS4xIDgtMS42IDEyLjItMS42czguMy42IDEyLjIg"
    "MS42YzkuMy02LjMgMTMuNC01IDEzLjQtNSAyLjcgNi43IDEgMTEuOC41IDEzIDMuMSAzLjQgNSA3"
    "LjggNSAxMy4yIDAgMTguOS0xMS41IDIzLjEtMjIuNCAyNC40IDEuOCAxLjYgMy4zIDQuNiAzLjMg"
    "OS4zIDAgNi43LS4xIDEyLjEtLjEgMTMuOCAwIDEuMy45IDIuOSAzLjQgMi40Qzg0IDg5LjEgOTgg"
    "NzAuNyA5OCA0OS4xIDk4IDIyIDc2IDAgNDguOSAweicgY2xpcC1ydWxlPSdldmVub2RkJy8+"
    "PC9zdmc+"
)
# White-fill variant for dark themes, where the black mark is nearly invisible.
_GITHUB_ICON_DARK_DATA_URI = (
    "data:image/svg+xml;base64,"
    "PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCA5OCA5"
    "Nic+PHBhdGggZmlsbD0nd2hpdGUnIGZpbGwtcnVsZT0nZXZlbm9kZCcgZD0nTTQ4LjkgMEMyMS45"
    "IDAgMCAyMiAwIDQ5LjFjMCAyMS43IDE0IDQwLjEgMzMuNSA0Ni42IDIuNS41IDMuMy0xLjEgMy4z"
    "LTIuNCAwLTEuMi0uMS01LjItLjEtOS40LTEzLjYgMy0xNi41LTUuOS0xNi41LTUuOS0yLjIt"
    "NS43LTUuNC03LjItNS40LTcuMi00LjQtMyAuMy0zIC4zLTMgNC45LjMgNy41IDUuMSA3LjUgNS4x"
    "IDQuMyA3LjUgMTEuNCA1LjMgMTQuMiA0LjEuNC0zLjIgMS43LTUuMyAzLjEtNi41LTEwLjktMS4y"
    "LTIyLjMtNS41LTIyLjMtMjQuNCAwLTUuNCAxLjktOS44IDUtMTMuMi0uNS0xLjItMi4yLTYuMy41"
    "LTEzIDAgMCA0LjEtMS4zIDEzLjQgNSAzLjktMS4xIDgtMS42IDEyLjItMS42czguMy42IDEyLjIg"
    "MS42YzkuMy02LjMgMTMuNC01IDEzLjQtNSAyLjcgNi43IDEgMTEuOC41IDEzIDMuMSAzLjQgNSA3"
    "LjggNSAxMy4yIDAgMTguOS0xMS41IDIzLjEtMjIuNCAyNC40IDEuOCAxLjYgMy4zIDQuNiAzLjMg"
    "OS4zIDAgNi43LS4xIDEyLjEtLjEgMTMuOCAwIDEuMy45IDIuOSAzLjQgMi40Qzg0IDg5LjEgOTgg"
    "NzAuNyA5OCA0OS4xIDk4IDIyIDc2IDAgNDguOSAweicgY2xpcC1ydWxlPSdldmVub2RkJy8+"
    "PC9zdmc+"
)


def _github_icon_data_uri() -> str:
    """Return the GitHub mark matching the active theme (white on dark, black on light)."""
    try:
        is_dark = st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001 - theme is best-effort; default to the light-mode mark
        is_dark = False
    return _GITHUB_ICON_DARK_DATA_URI if is_dark else _GITHUB_ICON_DATA_URI


_AUTHOR_PHOTO_URL = "https://media.licdn.com/dms/image/v2/D5603AQEraqyhOd5bOg/profile-displayphoto-shrink_200_200/profile-displayphoto-shrink_200_200/0/1731589103775?e=2147483647&v=beta&t=RTXvNnlM_jS1bPSRiBSC1hBfeIAAwhYVxXKv3ON9MUs"
_TOAST_PAGE_SUCCESS_ICON = "✅"
_TOAST_PAGE_FAIL_ICON = "❌"
_TOAST_PAGE_DISCOVERED_ICON = "🔎"
_CREATE_TOAST_STATE = "_create_toast"
_EXTEND_TOAST_STATE = "_extend_toast"
_LOAD_TOAST_STATE = "_load_toast"
_SWITCH_TOAST_STATE = "_switch_toast"
# A page (app_pages/**, which must not call st.toast) sets this to a localized
# success message; the shell fires it once on the next run.
_PENDING_PAGE_TOAST_STATE = "pending_page_toast"
_EXTEND_TOAST_SUCCESS = "success"
_EXTEND_TOAST_FAILED = "failed"
_REFRESH_FORM_STATES = {
    _STATE_COMPLETED,
    _STATE_FAILED,
    _STATE_STOPPED,
}
_FORM_MAX_WIDTH_PX = 980
_PORTFOLIO_MODAL_COMPONENT_KEY = "portfolio_modal"
_PORTFOLIO_MODAL_FIRST_DELAY_SECONDS = 60
_PORTFOLIO_MODAL_REPEAT_DAYS = 7
_PORTFOLIO_MODAL_REPEAT_HOURS = _HOURS_PER_DAY * _PORTFOLIO_MODAL_REPEAT_DAYS
_PORTFOLIO_MODAL_LAST_SHOWN_FIELD = "portfolio_modal_last_shown_at"
_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD = "portfolio_modal_last_dismissed_at"
_SESSION_STORAGE_COMPONENT_KEY = "browser_session_storage"
_SESSION_RECORDS_CACHE_STATE = "normalized_session_records_cache"
_SESSION_RECORDS_CACHE_MAX_ENTRIES = 8
_SESSION_RECORDS_FIELD = "sessions"
_SESSION_ID_FIELD = "session_id"
_SESSION_CREATED_AT_FIELD = "created_at"
_SESSION_LANGUAGE_FIELD = "language"
_SESSION_STORAGE_KEY = "crawl4md.streamlit.sessions.v1"
_SESSION_SELECTED_ID_FIELD = "selected_session_id"
_SESSION_STORAGE_HTML = """
<div id="crawl4md-session-storage" hidden></div>
"""
_SESSION_STORAGE_JS = """
const SESSION_ID_PATTERN = /^[a-z0-9_-]+$/
const SUPPORTED_LANGUAGES = new Set(["EN", "ID"])

function normalizeTimestamp(value) {
    if (typeof value !== "string") return null
    const parsed = new Date(value)
    if (Number.isNaN(parsed.getTime())) return null
    return parsed.toISOString().replace(".000Z", "Z")
}

function normalizeRecords(records) {
    const byId = new Map()
    for (const record of records || []) {
        if (!record || typeof record.session_id !== "string") continue
        if (!SESSION_ID_PATTERN.test(record.session_id)) continue
        if (typeof record.created_at !== "string") continue
        const createdAt = new Date(record.created_at)
        if (Number.isNaN(createdAt.getTime())) continue
        const rawLang = typeof record.language === "string" ? record.language.trim().toUpperCase() : ""
        const language = SUPPORTED_LANGUAGES.has(rawLang) ? rawLang : "EN"
        const normalized = {
            session_id: record.session_id,
            created_at: createdAt.toISOString().replace(".000Z", "Z"),
            language,
        }
        const existing = byId.get(normalized.session_id)
        if (!existing || createdAt >= new Date(existing.created_at)) {
            byId.set(normalized.session_id, normalized)
        }
    }
    return Array.from(byId.values()).sort((left, right) => {
        const timeDelta = new Date(right.created_at) - new Date(left.created_at)
        if (timeDelta !== 0) return timeDelta
        return right.session_id.localeCompare(left.session_id)
    })
}

function readStorage(storageKey) {
    try {
        const rawValue = window.localStorage.getItem(storageKey)
        if (!rawValue) {
            return {
                records: [],
                selectedSessionId: null,
                portfolioModalLastShownAt: null,
                portfolioModalLastDismissedAt: null,
            }
        }
        const parsed = JSON.parse(rawValue)
        const records = Array.isArray(parsed)
            ? normalizeRecords(parsed)
            : normalizeRecords(parsed.sessions)
        const rawSelected = typeof parsed.selected_session_id === "string"
            ? parsed.selected_session_id.trim()
            : null
        const selectedSessionId = rawSelected && SESSION_ID_PATTERN.test(rawSelected)
            ? rawSelected
            : null
        return {
            records,
            selectedSessionId,
            portfolioModalLastShownAt: normalizeTimestamp(parsed.portfolio_modal_last_shown_at),
            portfolioModalLastDismissedAt: normalizeTimestamp(parsed.portfolio_modal_last_dismissed_at),
        }
    } catch {
        return {
            records: [],
            selectedSessionId: null,
            portfolioModalLastShownAt: null,
            portfolioModalLastDismissedAt: null,
        }
    }
}

function writeStorage(
    storageKey,
    records,
    selectedSessionId,
    portfolioModalLastShownAt,
    portfolioModalLastDismissedAt,
) {
    try {
        const payload = { version: 1, sessions: records }
        if (selectedSessionId) payload.selected_session_id = selectedSessionId
        if (portfolioModalLastShownAt) {
            payload.portfolio_modal_last_shown_at = portfolioModalLastShownAt
        }
        if (portfolioModalLastDismissedAt) {
            payload.portfolio_modal_last_dismissed_at = portfolioModalLastDismissedAt
        }
        window.localStorage.setItem(storageKey, JSON.stringify(payload))
        return true
    } catch {
        return false
    }
}

export default function (component) {
    const { data, setStateValue } = component
    const storageKey = data.storageKey
    const {
        records: storedRecords,
        selectedSessionId: storedSelectedId,
        portfolioModalLastShownAt,
        portfolioModalLastDismissedAt,
    } = readStorage(storageKey)
    const idsToRemove = new Set(Array.isArray(data.recordsToRemove) ? data.recordsToRemove : [])
    const filteredStoredRecords = idsToRemove.size > 0
        ? storedRecords.filter(r => !idsToRemove.has(r.session_id))
        : storedRecords
    const pendingRecords = Array.isArray(data.pendingRecords) ? data.pendingRecords : []
    const nextRecords = normalizeRecords([...filteredStoredRecords, ...pendingRecords])
    const nextSerialized = JSON.stringify(nextRecords)
    const storedSerialized = JSON.stringify(storedRecords)
    const pendingSelectedId = typeof data.pendingSelectedSessionId === "string"
        ? data.pendingSelectedSessionId.trim()
        : null
    const nextSelectedId = pendingSelectedId || storedSelectedId
    const hasPendingRecords = pendingRecords.length > 0
    const recordsNeedWrite = nextSerialized !== storedSerialized
    const selectedNeedsWrite = !!pendingSelectedId && pendingSelectedId !== storedSelectedId
    let storedPending = (!hasPendingRecords || !recordsNeedWrite) && !selectedNeedsWrite
    if (recordsNeedWrite || selectedNeedsWrite) {
        storedPending = writeStorage(
            storageKey,
            nextRecords,
            nextSelectedId,
            portfolioModalLastShownAt,
            portfolioModalLastDismissedAt,
        )
    }
    const storageWriteFailed = (hasPendingRecords || !!pendingSelectedId) && storedPending === false
    if (hasPendingRecords && storedPending) {
        setStateValue("stored_records", nextRecords)
    }
    if (data.storageWriteFailed !== storageWriteFailed) {
        setStateValue("storage_write_failed", storageWriteFailed)
    }

    const pythonRecords = normalizeRecords(Array.isArray(data.records) ? data.records : [])
    if (JSON.stringify(pythonRecords) !== nextSerialized) {
        setStateValue("records", nextRecords)
    }
    if (data.hydrated !== true) {
        setStateValue("hydrated", true)
    }
    if (nextSelectedId && data.selectedSessionId !== nextSelectedId) {
        setStateValue("selected_session_id", nextSelectedId)
    }
    if (
        portfolioModalLastShownAt
        && data.portfolioModalLastShownAt !== portfolioModalLastShownAt
    ) {
        setStateValue("portfolio_modal_last_shown_at", portfolioModalLastShownAt)
    }
    if (
        portfolioModalLastDismissedAt
        && data.portfolioModalLastDismissedAt !== portfolioModalLastDismissedAt
    ) {
        setStateValue("portfolio_modal_last_dismissed_at", portfolioModalLastDismissedAt)
    }
}
"""

_PORTFOLIO_MODAL_HTML = """
<div id="crawl4md-portfolio-modal-root"></div>
"""

_PORTFOLIO_MODAL_CSS = """
:host {
    font-family: var(--st-font, "Source Sans Pro", sans-serif);
}

#crawl4md-portfolio-modal-root {
    display: contents;
}

.portfolio-modal-overlay {
    position: fixed;
    inset: 0;
    z-index: 10000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: rgba(17, 24, 39, 0.48);
    backdrop-filter: blur(2px);
}

.portfolio-modal-overlay[hidden] {
    display: none;
}

.portfolio-modal-panel {
    position: relative;
    width: min(560px, calc(100vw - 32px));
    max-height: min(82vh, 720px);
    overflow: auto;
    box-sizing: border-box;
    padding: 24px;
    color: var(--st-text-color, #111827);
    background: var(--st-background-color, #ffffff);
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: var(--st-base-radius, 8px);
    box-shadow: 0 20px 60px rgba(15, 23, 42, 0.28);
}

.portfolio-modal-close {
    position: absolute;
    top: 10px;
    right: 10px;
    width: 36px;
    height: 36px;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
    border-radius: var(--st-button-radius, 8px);
    color: var(--st-text-color, #111827);
    background: var(--st-secondary-background-color, #f3f4f6);
    cursor: pointer;
    font-size: 18px;
    line-height: 1;
}

.portfolio-modal-header {
    display: flex;
    gap: 16px;
    align-items: center;
    padding-right: 34px;
}

.portfolio-modal-avatar {
    width: 84px;
    height: 84px;
    flex: 0 0 auto;
    object-fit: cover;
    border-radius: 50%;
    border: 1px solid var(--st-border-color, rgba(49, 51, 63, 0.2));
}

.portfolio-modal-title {
    margin: 0;
    color: var(--st-heading-color, var(--st-text-color, #111827));
    font: 700 1.35rem/1.25 var(--st-heading-font, var(--st-font, sans-serif));
}

.portfolio-modal-kicker {
    margin: 6px 0 0;
    color: var(--st-text-color, #111827);
    opacity: 0.72;
    font-size: 0.95rem;
}

.portfolio-modal-copy {
    margin: 18px 0 0;
    font-size: 0.98rem;
    line-height: 1.6;
}

.portfolio-modal-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 18px;
    margin-top: 20px;
}

.portfolio-modal-link {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--st-link-color, var(--st-primary-color, #ff4b4b));
    text-decoration: none;
    font-weight: 600;
}

.portfolio-modal-link:hover {
    text-decoration: underline;
}

.portfolio-modal-doc-link {
    color: var(--st-link-color, var(--st-primary-color, #ff4b4b));
    text-decoration: none;
    font-weight: 600;
}

.portfolio-modal-doc-link:hover {
    text-decoration: underline;
}

.portfolio-modal-icon-image {
    width: 22px;
    height: 22px;
    flex: 0 0 auto;
    object-fit: contain;
}

@media (max-width: 520px) {
    .portfolio-modal-panel {
        padding: 20px;
    }

    .portfolio-modal-header {
        align-items: flex-start;
    }

    .portfolio-modal-avatar {
        width: 64px;
        height: 64px;
    }
}
"""

_PORTFOLIO_MODAL_JS = """
const MODAL_VISIBLE_CLASS = "is-visible"

function readPayload(storageKey) {
    try {
        const rawValue = window.localStorage.getItem(storageKey)
        if (!rawValue) return { version: 1, sessions: [] }
        const parsed = JSON.parse(rawValue)
        if (Array.isArray(parsed)) return { version: 1, sessions: parsed }
        if (parsed && typeof parsed === "object") return parsed
    } catch {
        return { version: 1, sessions: [] }
    }
    return { version: 1, sessions: [] }
}

function utcNow() {
    return new Date().toISOString().replace(".000Z", "Z")
}

function writeTimestamp(storageKey, field, value) {
    if (!storageKey || !field) return
    try {
        const payload = readPayload(storageKey)
        payload.version = 1
        payload[field] = value
        window.localStorage.setItem(storageKey, JSON.stringify(payload))
    } catch {
        return
    }
}

function appendText(parent, tagName, className, text) {
    const element = document.createElement(tagName)
    element.className = className
    element.textContent = text || ""
    parent.appendChild(element)
    return element
}

function appendLink(parent, href, label, iconUrl, iconClass) {
    const link = document.createElement("a")
    link.className = iconClass ? `portfolio-modal-link ${iconClass}` : "portfolio-modal-link"
    link.href = href || "#"
    link.target = "_blank"
    link.rel = "noopener noreferrer"
    const icon = document.createElement("img")
    icon.className = iconClass
        ? `portfolio-modal-icon-image ${iconClass}`
        : "portfolio-modal-icon-image"
    icon.setAttribute("aria-hidden", "true")
    icon.alt = ""
    icon.src = iconUrl || ""
    link.appendChild(icon)
    link.appendChild(document.createTextNode(label || ""))
    parent.appendChild(link)
}

function updateIconSrc(overlay, iconClass, iconUrl) {
    if (typeof iconUrl !== "string" || !iconUrl) return
    const icon = overlay.querySelector(`.portfolio-modal-icon-image.${iconClass}`)
    if (icon && icon.getAttribute("src") !== iconUrl) icon.src = iconUrl
}

const instances = new WeakMap()

export default function (component) {
    const { data, parentElement } = component
    const root = parentElement.querySelector("#crawl4md-portfolio-modal-root")
    if (!root) return

    let instance = instances.get(parentElement)
    if (!instance) {
        instance = { timer: null, open: false, overlay: null, onKeyDown: null }
        instances.set(parentElement, instance)
    }

    if (data.shouldShow !== true) {
        if (instance.timer) window.clearTimeout(instance.timer)
        if (instance.onKeyDown) document.removeEventListener("keydown", instance.onKeyDown)
        root.innerHTML = ""
        instance.timer = null
        instance.open = false
        instance.overlay = null
        instance.onKeyDown = null
        return
    }

    if (instance.overlay) {
        if (!root.contains(instance.overlay)) root.appendChild(instance.overlay)
        // Theme toggles re-run this component with new icon URLs; refresh the
        // existing overlay so the mark recolors on every toggle, not just once.
        updateIconSrc(instance.overlay, "github", data.githubIconUrl)
        updateIconSrc(instance.overlay, "linkedin", data.linkedinIconUrl)
        return
    }

    root.innerHTML = ""

    const overlay = document.createElement("div")
    overlay.className = "portfolio-modal-overlay"
    overlay.hidden = true

    const panel = document.createElement("section")
    panel.className = "portfolio-modal-panel"
    panel.setAttribute("role", "dialog")
    panel.setAttribute("aria-modal", "true")
    panel.setAttribute("aria-labelledby", "portfolio-modal-title")

    const closeButton = document.createElement("button")
    closeButton.className = "portfolio-modal-close"
    closeButton.type = "button"
    closeButton.setAttribute("aria-label", data.closeLabel || "Close")
    closeButton.textContent = "x"
    panel.appendChild(closeButton)

    const header = document.createElement("div")
    header.className = "portfolio-modal-header"
    const image = document.createElement("img")
    image.className = "portfolio-modal-avatar"
    image.src = data.photoUrl || ""
    image.alt = data.photoAlt || ""
    header.appendChild(image)
    const headerText = document.createElement("div")
    const title = appendText(headerText, "h2", "portfolio-modal-title", data.title)
    title.id = "portfolio-modal-title"
    appendText(headerText, "p", "portfolio-modal-kicker", data.tagline)
    header.appendChild(headerText)
    panel.appendChild(header)

    appendText(panel, "p", "portfolio-modal-copy", data.body)
    appendText(panel, "p", "portfolio-modal-copy", data.cta)

    const docLinks = document.createElement("p")
    docLinks.className = "portfolio-modal-copy"
    const readmeLink = document.createElement("a")
    readmeLink.className = "portfolio-modal-doc-link"
    readmeLink.href = data.readmeUrl || "#"
    readmeLink.target = "_blank"
    readmeLink.rel = "noopener noreferrer"
    readmeLink.textContent = data.readmeLabel || ""
    const sep = document.createTextNode(" \u00b7 ")
    const stReadmeLink = document.createElement("a")
    stReadmeLink.className = "portfolio-modal-doc-link"
    stReadmeLink.href = data.streamlitReadmeUrl || "#"
    stReadmeLink.target = "_blank"
    stReadmeLink.rel = "noopener noreferrer"
    stReadmeLink.textContent = data.streamlitReadmeLabel || ""
    docLinks.appendChild(readmeLink)
    docLinks.appendChild(sep)
    docLinks.appendChild(stReadmeLink)
    panel.appendChild(docLinks)

    const actions = document.createElement("div")
    actions.className = "portfolio-modal-actions"
    appendLink(actions, data.linkedinUrl, data.linkedinLabel, data.linkedinIconUrl, "linkedin")
    appendLink(actions, data.githubUrl, data.githubLabel, data.githubIconUrl, "github")
    panel.appendChild(actions)
    overlay.appendChild(panel)
    root.appendChild(overlay)

    function dismiss() {
        if (!instance.open) return
        writeTimestamp(data.storageKey, data.lastDismissedField, utcNow())
        overlay.classList.remove(MODAL_VISIBLE_CLASS)
        overlay.hidden = true
        instance.open = false
        document.removeEventListener("keydown", onKeyDown)
    }

    function onKeyDown(event) {
        if (event.key === "Escape") dismiss()
    }

    instance.overlay = overlay
    instance.onKeyDown = onKeyDown

    overlay.addEventListener("click", event => {
        if (event.target === overlay) dismiss()
    })
    closeButton.addEventListener("click", dismiss)

    const delayMs = Math.max(0, Number(data.delaySeconds || 0)) * 1000
    instance.timer = window.setTimeout(() => {
        instance.timer = null
        overlay.hidden = false
        overlay.classList.add(MODAL_VISIBLE_CLASS)
        instance.open = true
        writeTimestamp(data.storageKey, data.lastShownField, utcNow())
        document.addEventListener("keydown", onKeyDown)
        closeButton.focus()
    }, delayMs)

    return () => {
        if (instance.timer) window.clearTimeout(instance.timer)
        document.removeEventListener("keydown", onKeyDown)
        root.innerHTML = ""
        instances.delete(parentElement)
    }
}
"""


st.set_page_config(
    page_title="crawl4md — Website Crawler",
    page_icon=":material/travel_explore:",
    layout="wide",
)


_SESSION_STORAGE_COMPONENT = component_v2(
    "crawl4md_session_storage",
    html=_SESSION_STORAGE_HTML,
    js=_SESSION_STORAGE_JS,
)

_PORTFOLIO_MODAL_COMPONENT = component_v2(
    "crawl4md_portfolio_modal",
    html=_PORTFOLIO_MODAL_HTML,
    css=_PORTFOLIO_MODAL_CSS,
    js=_PORTFOLIO_MODAL_JS,
)


@st.cache_resource(show_spinner=False)
def _run_startup_cleanup(active_session_ids: tuple[str, ...]) -> None:
    removed = cleanup_old_sessions_with_lock(
        _SESSIONS_ROOT,
        active_session_ids=active_session_ids,
        retention_days=get_settings().session_retention_days,
    )
    # Prune each removed session's published 3D viewers from the static dir.
    remove_orrery_static(
        _APP_DIR / "static",
        [path.name.removeprefix(SESSION_DIR_PREFIX) for path in removed],
    )


def _init_state() -> None:
    st.session_state.setdefault("session_id", "")
    st.session_state.setdefault("browser_session_records", [])
    st.session_state.setdefault("browser_sessions_hydrated", False)
    st.session_state.setdefault("pending_browser_session_records", [])
    st.session_state.setdefault("pending_bootstrap_session_id", "")
    st.session_state.setdefault("session_storage_write_failed", False)
    st.session_state.setdefault("preferred_session_id", "")
    st.session_state.setdefault("pending_selected_session_id", "")
    st.session_state.setdefault("session_ids_to_purge", [])
    st.session_state.setdefault("job", None)
    st.session_state.setdefault("job_state", _STATE_IDLE)
    st.session_state.setdefault("crawl_id", "")
    st.session_state.setdefault("events", [])
    st.session_state.setdefault("latest_event", {})
    st.session_state.setdefault("progress_chart_history", [])
    st.session_state.setdefault("active_output_dir", "")
    st.session_state.setdefault("started_at", None)
    st.session_state.setdefault("last_elapsed", "")
    st.session_state.setdefault("activity_log_size", DEFAULT_ACTIVITY_LOG_SIZE)
    st.session_state.setdefault("activity_log_latest_line", None)
    st.session_state.setdefault("preview_file_relative_path", "")
    st.session_state.setdefault("delete_folder_relative_path", "")
    st.session_state.setdefault("export_folder_relative_path", "")
    st.session_state.setdefault("form_defaults", default_form_values())
    st.session_state.setdefault("stop_confirmation_open", False)
    st.session_state.setdefault("vector_index_job", None)
    st.session_state.setdefault("vector_index_id", "")
    st.session_state.setdefault("vector_index_state", _STATE_IDLE)
    st.session_state.setdefault("vector_index_progress", {})
    st.session_state.setdefault("vector_index_stage", "")
    st.session_state.setdefault("vector_index_result", {})
    st.session_state.setdefault("vector_index_started_at", None)
    st.session_state.setdefault("vector_index_stop_confirmation_open", False)
    st.session_state.setdefault("session_load_dialog_open", False)
    st.session_state.setdefault("_load_session_enter", False)
    st.session_state.setdefault("language", _DEFAULT_LANGUAGE)
    st.session_state.setdefault(_PORTFOLIO_MODAL_LAST_SHOWN_FIELD, "")
    st.session_state.setdefault(_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD, "")
    st.session_state.setdefault(_SESSION_RECORDS_CACHE_STATE, {})


def _session_records_cache_key(payload: object) -> tuple[tuple[str, str, str, str], ...]:
    raw_records = (
        payload.get(_SESSION_RECORDS_FIELD, []) if isinstance(payload, Mapping) else payload
    )
    if isinstance(raw_records, (str, bytes)) or not isinstance(raw_records, Iterable):
        return ()

    key_parts: list[tuple[str, str, str, str]] = []
    for raw_record in raw_records:
        if isinstance(raw_record, SessionRecord):
            key_parts.append(
                (
                    "record",
                    raw_record.session_id,
                    raw_record.created_at.isoformat(),
                    raw_record.language,
                )
            )
            continue
        if isinstance(raw_record, Mapping):
            key_parts.append(
                (
                    "mapping",
                    str(raw_record.get(_SESSION_ID_FIELD, "")),
                    str(raw_record.get(_SESSION_CREATED_AT_FIELD, "")),
                    str(raw_record.get(_SESSION_LANGUAGE_FIELD, "")),
                )
            )
            continue
        key_parts.append(("other", repr(raw_record), "", ""))
    return tuple(key_parts)


def _cached_normalize_session_records(payload: object) -> list[SessionRecord]:
    cache_key = _session_records_cache_key(payload)
    cache = st.session_state.get(_SESSION_RECORDS_CACHE_STATE)
    if not isinstance(cache, dict):
        cache = {}
        st.session_state[_SESSION_RECORDS_CACHE_STATE] = cache
    cached_records = cache.get(cache_key)
    if cached_records is not None:
        return list(cached_records)

    records = normalize_session_records(payload)
    if len(cache) >= _SESSION_RECORDS_CACHE_MAX_ENTRIES:
        cache.clear()
    cache[cache_key] = tuple(records)
    return records


@st.cache_data(ttl=60, show_spinner=False)
def _cached_session_exists(sessions_root: str, session_id: str) -> bool:
    return session_exists(Path(sessions_root), session_id)


def _filter_server_valid_sessions(
    records: list[SessionRecord], current_session_id: str
) -> tuple[list[SessionRecord], list[str]]:
    """Split records into server-valid and missing; exempt the current session."""
    sessions_root_str = str(_SESSIONS_ROOT.resolve())
    valid: list[SessionRecord] = []
    invalid_ids: list[str] = []
    for record in records:
        if (
            record.session_id == current_session_id
            or _cached_session_exists(  # exempt the current session
                sessions_root_str, record.session_id
            )
        ):
            valid.append(record)
        else:
            invalid_ids.append(record.session_id)
    return valid, invalid_ids


def _browser_session_records() -> list[SessionRecord]:
    records = st.session_state.get("browser_session_records", [])
    if isinstance(records, list) and all(isinstance(record, SessionRecord) for record in records):
        return records
    return _cached_normalize_session_records(records)


def _component_field(result: Any, field: str) -> Any:
    value = getattr(result, field, None)
    if value is not None:
        return value
    component_state = st.session_state.get(_SESSION_STORAGE_COMPONENT_KEY, {})
    getter = getattr(component_state, "get", None)
    if callable(getter):
        return getter(field)
    return getattr(component_state, field, None)


def _component_result_field(result: Any, field: str) -> Any:
    return getattr(result, field, None)


def _mount_session_storage() -> None:
    result = _SESSION_STORAGE_COMPONENT(
        key=_SESSION_STORAGE_COMPONENT_KEY,
        data={
            "storageKey": _SESSION_STORAGE_KEY,
            "records": serialize_session_records(_browser_session_records()),
            "pendingRecords": st.session_state.pending_browser_session_records,
            "pendingSelectedSessionId": st.session_state.pending_selected_session_id,
            "selectedSessionId": st.session_state.preferred_session_id,
            "hydrated": st.session_state.browser_sessions_hydrated,
            "storageWriteFailed": st.session_state.session_storage_write_failed,
            "recordsToRemove": st.session_state.get("session_ids_to_purge", []),
            "portfolioModalLastShownAt": st.session_state.get(
                _PORTFOLIO_MODAL_LAST_SHOWN_FIELD, ""
            ),
            "portfolioModalLastDismissedAt": st.session_state.get(
                _PORTFOLIO_MODAL_LAST_DISMISSED_FIELD, ""
            ),
        },
        on_records_change=lambda: None,
        on_stored_records_change=lambda: None,
        on_storage_write_failed_change=lambda: None,
        on_hydrated_change=lambda: None,
        on_selected_session_id_change=lambda: None,
        on_portfolio_modal_last_shown_at_change=lambda: None,
        on_portfolio_modal_last_dismissed_at_change=lambda: None,
    )
    _apply_session_storage_result(result)


def _apply_session_storage_result(result: Any) -> None:
    records_payload = _component_field(result, "records")
    if records_payload is not None:
        normalized_payload = _cached_normalize_session_records(records_payload)
        st.session_state.browser_session_records = _cached_normalize_session_records(
            [
                *serialize_session_records(normalized_payload),
                *serialize_session_records(_browser_session_records()),
                *st.session_state.pending_browser_session_records,
            ]
        )
    storage_write_failed = _component_result_field(result, "storage_write_failed")
    if storage_write_failed is not None:
        st.session_state.session_storage_write_failed = bool(storage_write_failed)
    if _component_field(result, "hydrated") is True:
        st.session_state.browser_sessions_hydrated = True
    if records_payload is not None and st.session_state.browser_sessions_hydrated:
        valid, invalid_ids = _filter_server_valid_sessions(
            _browser_session_records(), str(st.session_state.get("session_id", ""))
        )
        st.session_state.browser_session_records = valid
        st.session_state.session_ids_to_purge = invalid_ids

    pending = _cached_normalize_session_records(st.session_state.pending_browser_session_records)
    stored_payload = _component_result_field(result, "stored_records")
    pending_ack_payload = stored_payload
    if (
        pending_ack_payload is None
        and records_payload is not None
        and not st.session_state.session_storage_write_failed
    ):
        pending_ack_payload = records_payload
    if pending and pending_ack_payload is not None:
        stored_ids = {
            record.session_id for record in _cached_normalize_session_records(pending_ack_payload)
        }
        if {record.session_id for record in pending}.issubset(stored_ids):
            st.session_state.pending_browser_session_records = []
        if st.session_state.pending_bootstrap_session_id in stored_ids:
            st.session_state.pending_bootstrap_session_id = ""
            st.session_state.session_storage_write_failed = False

    # Restore the previously selected session id from browser storage if present.
    stored_selected_id = _component_result_field(result, "selected_session_id")
    if isinstance(stored_selected_id, str) and stored_selected_id.strip():
        candidate = stored_selected_id.strip()
        records = _browser_session_records()
        known_ids = {r.session_id for r in records}
        if candidate in known_ids and not st.session_state.preferred_session_id:
            st.session_state.preferred_session_id = candidate

    last_shown_at = _component_field(result, _PORTFOLIO_MODAL_LAST_SHOWN_FIELD)
    if isinstance(last_shown_at, str):
        st.session_state[_PORTFOLIO_MODAL_LAST_SHOWN_FIELD] = last_shown_at.strip()
    last_dismissed_at = _component_field(result, _PORTFOLIO_MODAL_LAST_DISMISSED_FIELD)
    if isinstance(last_dismissed_at, str):
        st.session_state[_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD] = last_dismissed_at.strip()

    # Clear pending_selected_session_id after one round-trip — JS writes synchronously
    # so confirmation via stored_payload is not needed.
    if st.session_state.pending_selected_session_id:
        st.session_state.pending_selected_session_id = ""


def _normalize_language(value: object) -> str:
    normalized = str(value).strip().upper() if isinstance(value, str) else ""
    return normalized if normalized in CATALOG else _DEFAULT_LANGUAGE


def _language_widget_key() -> str:
    session_id = str(st.session_state.get("session_id", "")).strip()
    return f"language_selector_{session_id or 'bootstrap'}"


def _sync_language_widget_state() -> str:
    widget_key = _language_widget_key()
    language = _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.session_state.language = language
    return widget_key


def _select_session_id(session_id: str, *, restore_language: bool = True) -> None:
    if not session_id:
        return
    records = _browser_session_records()
    known_ids = {record.session_id for record in records}
    if session_id not in known_ids:
        return
    if st.session_state.session_id != session_id:
        st.session_state.preview_file_relative_path = ""
        st.session_state.events = []
        st.session_state.latest_event = {}
        st.session_state.progress_chart_history = []
        st.session_state.active_output_dir = ""
        st.session_state.activity_log_latest_line = None
        st.session_state.last_elapsed = ""
        st.session_state.job = None
        st.session_state.job_state = _STATE_IDLE
        st.session_state.started_at = None
        st.session_state.prev_successful_pages = 0
        st.session_state.prev_failed_pages = 0
        st.session_state.prev_discovered_pages = 0
        # Detach any vector-index job too, so the newly selected session reattaches
        # its own active indexing run (if any) instead of showing a stale one.
        st.session_state.vector_index_job = None
        st.session_state.vector_index_id = ""
        st.session_state.vector_index_state = _STATE_IDLE
        st.session_state.vector_index_progress = {}
        st.session_state.vector_index_stage = ""
        st.session_state.vector_index_result = {}
        st.session_state.vector_index_started_at = None
        # Persist the newly selected session id back to browser storage only on change.
        st.session_state.pending_selected_session_id = session_id
    st.session_state.session_id = session_id
    st.session_state.preferred_session_id = session_id
    if not restore_language:
        return
    for record in records:
        if record.session_id == session_id:
            st.session_state.language = _normalize_language(record.language)
            break


def _commit_session_record(record: SessionRecord) -> None:
    """Merge *record* into browser session state and stage it for localStorage write."""
    records = _cached_normalize_session_records(
        [
            *serialize_session_records(_browser_session_records()),
            *serialize_session_records([record]),
        ]
    )
    pending_records = _cached_normalize_session_records(
        [
            *st.session_state.pending_browser_session_records,
            *serialize_session_records([record]),
        ]
    )
    st.session_state.browser_session_records = records
    st.session_state.pending_browser_session_records = serialize_session_records(pending_records)
    st.session_state.pending_bootstrap_session_id = record.session_id
    st.session_state.session_storage_write_failed = False


def _create_new_session() -> None:
    record = create_session_record()
    st.session_state.language = record.language
    _commit_session_record(record)
    _select_session_id(record.session_id)
    st.session_state[_CREATE_TOAST_STATE] = True
    st.rerun()


def _register_and_select_session(session_id: str) -> None:
    """Register an externally known session into local browser records and select it."""
    mtime = session_dir(_SESSIONS_ROOT, session_id).stat().st_mtime
    created_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
    touch_session(_SESSIONS_ROOT, session_id)
    current_language = _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
    record = create_session_record(session_id=session_id, language=current_language, now=created_at)
    _commit_session_record(record)
    st.session_state.session_load_dialog_open = False
    st.session_state[_LOAD_TOAST_STATE] = record.session_id
    _select_session_id(record.session_id, restore_language=False)
    st.rerun()


def _on_load_session_dismiss() -> None:
    st.session_state.session_load_dialog_open = False
    st.session_state["_load_session_enter"] = False


@st.dialog(_DIALOG_LOAD_SESSION_TITLE, width="small", on_dismiss=_on_load_session_dismiss)
def _load_session_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

    def _on_input_commit() -> None:
        st.session_state["_load_session_enter"] = True

    session_id_input = st.text_input(
        label=strings["DIALOG_LOAD_SESSION_ID_LABEL"],
        placeholder=strings["DIALOG_LOAD_SESSION_ID_PLACEHOLDER"],
        help=strings["DIALOG_LOAD_SESSION_ID_HELP"],
        key="load_session_id_input",
        on_change=_on_input_commit,
    )
    if st.session_state.pop("_focus_session_id", False):
        focus_widget("load_session_id_input")
    error_slot = st.empty()
    cancel_col, _, load_col = st.columns([2, 5, 3])
    with cancel_col:
        if st.button(strings["DIALOG_LOAD_BTN_CANCEL"], key="load_session_cancel"):
            st.session_state["_load_session_enter"] = False
            st.session_state.session_load_dialog_open = False
            st.rerun()
    with load_col, st.container(horizontal_alignment="right"):
        load_clicked = st.button(
            strings["DIALOG_LOAD_BTN_LOAD"],
            type="primary",
            icon=":material/folder_open:",
            key="load_session_confirm",
        )
    enter_submitted = st.session_state.get("_load_session_enter", False)
    st.session_state["_load_session_enter"] = False
    if load_clicked or enter_submitted:
        stripped = session_id_input.strip()
        if not stripped:
            error_slot.error(strings["DIALOG_LOAD_SESSION_INVALID_ID"])
            return
        try:
            validate_safe_id(stripped)
        except ValueError:
            error_slot.error(strings["DIALOG_LOAD_SESSION_INVALID_ID"])
            return
        known_ids = {r.session_id for r in _browser_session_records()}
        if stripped in known_ids:
            st.session_state[_SWITCH_TOAST_STATE] = stripped
            st.session_state.session_load_dialog_open = False
            _select_session_id(stripped)
            st.rerun()
        if not session_exists(_SESSIONS_ROOT, stripped):
            error_slot.error(strings["DIALOG_LOAD_SESSION_NOT_FOUND"].format(id=stripped))
            return
        _register_and_select_session(stripped)


def _ensure_selected_session() -> None:
    records = _browser_session_records()
    if records:
        known_ids = {record.session_id for record in records}
        preferred_session_id = str(st.session_state.get("preferred_session_id", ""))
        current_session_id = str(st.session_state.get("session_id", ""))
        selected_session_id = current_session_id
        if preferred_session_id in known_ids:
            selected_session_id = preferred_session_id
        elif current_session_id not in known_ids:
            selected_session_id = latest_session_id(records)
        restore_language = (
            selected_session_id != current_session_id
            or str(st.session_state.get("language", "")).strip().upper() not in CATALOG
        )
        _select_session_id(
            selected_session_id,
            restore_language=restore_language,
        )
        return

    record = create_session_record()
    st.session_state.browser_session_records = [record]
    st.session_state.pending_browser_session_records = serialize_session_records([record])
    st.session_state.pending_bootstrap_session_id = record.session_id
    st.session_state.session_storage_write_failed = False
    _select_session_id(record.session_id)
    st.rerun()


def _on_language_change(widget_key: str) -> None:
    new_lang = _normalize_language(st.session_state.get(widget_key, _DEFAULT_LANGUAGE))
    st.session_state.language = new_lang
    session_id = st.session_state.session_id
    records = _browser_session_records()
    updated = [
        SessionRecord(r.session_id, r.created_at, new_lang) if r.session_id == session_id else r
        for r in records
    ]
    st.session_state.browser_session_records = updated
    updated_record = next((r for r in updated if r.session_id == session_id), None)
    if updated_record is not None:
        pending = _cached_normalize_session_records(
            [
                *st.session_state.pending_browser_session_records,
                *serialize_session_records([updated_record]),
            ]
        )
        st.session_state.pending_browser_session_records = serialize_session_records(pending)


def _session_options() -> list[str]:
    return [record.session_id for record in _browser_session_records()]


def _session_selector_index(options: list[str]) -> int:
    if st.session_state.session_id in options:
        return options.index(st.session_state.session_id)
    return 0


def _drain_job_events(job: CrawlJob | None) -> bool:
    """Apply worker events to the Streamlit-facing crawl state."""
    if job is None:
        return False
    state_changed = False
    for event in drain_events(job):
        event_name = str(event.get("event", ""))
        st.session_state.events.append(event)
        st.session_state.latest_event.update(event)
        chart_history = st.session_state.get("progress_chart_history")
        if not isinstance(chart_history, list):
            chart_history = []
        st.session_state.progress_chart_history = append_live_progress_sample(
            chart_history,
            event,
            started_at=st.session_state.started_at,
        )
        output_dir = str(event.get("output_dir", ""))
        if output_dir:
            st.session_state.active_output_dir = output_dir
        next_state = job_state_from_event(event_name)
        # Keep the UI in Stop-pending state if older worker events arrive late.
        if st.session_state.job_state == _STATE_CANCEL_REQUESTED and next_state in {
            _STATE_RUNNING,
            _STATE_CANCEL_REQUESTED,
        }:
            next_state = _STATE_CANCEL_REQUESTED
        elif next_state == _STATE_CANCELLED:
            next_state = _STATE_STOPPED
        if next_state != st.session_state.job_state:
            state_changed = True
        st.session_state.job_state = next_state
        if next_state in _TERMINAL_STATES:
            started_at = st.session_state.started_at
            if started_at is not None:
                elapsed = datetime.now(timezone.utc) - started_at
                st.session_state.last_elapsed = str(elapsed).split(".")[0]
            st.session_state.started_at = None
            st.session_state.job = None
            st.session_state.form_defaults = default_form_values()
    return state_changed


def _reattach_selected_session_job() -> None:
    """Restore a running crawl job from the process-local registry after browser refresh.

    Called after session selection so that `st.session_state.session_id` is already set.
    Does nothing if a job is already attached to this Streamlit session.
    """
    if st.session_state.job is not None:
        return
    session_id = st.session_state.session_id
    if not session_id:
        return
    snapshot = get_active_job_snapshot(session_id)
    if snapshot is None:
        return
    st.session_state.job = snapshot.job
    st.session_state.crawl_id = snapshot.crawl_id
    st.session_state.job_state = snapshot.job_state
    st.session_state.started_at = snapshot.started_at
    st.session_state.activity_log_size = snapshot.activity_log_size
    st.session_state.latest_event = dict(snapshot.latest_event)
    st.session_state.active_output_dir = snapshot.active_output_dir
    # Seed page-count deltas so the first drain doesn't fire spurious toast messages.
    st.session_state.prev_successful_pages = int(snapshot.latest_event.get("successful_pages", 0))
    st.session_state.prev_failed_pages = int(snapshot.latest_event.get("failed_pages", 0))
    st.session_state.prev_discovered_pages = int(
        snapshot.latest_event.get("queued_discovered_urls", 0)
    )
    st.session_state.progress_chart_history = []
    if snapshot.latest_event:
        st.session_state.progress_chart_history = append_live_progress_sample(
            st.session_state.progress_chart_history,
            snapshot.latest_event,
            started_at=snapshot.started_at,
        )


def _reattach_selected_session_vector_job() -> None:
    """Restore a running indexing job from the process-local registry after refresh.

    Mirrors `_reattach_selected_session_job` for Step 2 so a second browser tab (or
    a reloaded page) shows the in-progress indexing and keeps the form locked while
    it runs. Does nothing if a vector job is already attached to this session.
    """
    if st.session_state.vector_index_job is not None:
        return
    session_id = st.session_state.session_id
    if not session_id:
        return
    snapshot = get_active_vector_job_snapshot(session_id)
    if snapshot is None:
        return
    st.session_state.vector_index_job = snapshot.job
    st.session_state.vector_index_id = snapshot.vector_id
    st.session_state.vector_index_state = snapshot.job_state
    st.session_state.vector_index_started_at = snapshot.started_at
    st.session_state.vector_index_progress = {}
    st.session_state.vector_index_stage = ""
    st.session_state.vector_index_result = {}
    # Replay the latest event so the reattached page shows the current stage,
    # chunk progress, or terminal result without waiting for the next emit.
    if snapshot.latest_event:
        _apply_vector_index_event(snapshot.latest_event)


def _start_job(values: dict[str, Any]) -> None:
    # Guard: if the registry already has an alive job for this session (e.g. a
    # second tab opened the same session), reattach instead of starting a new crawl.
    if get_active_job_snapshot(st.session_state.session_id) is not None:
        _reattach_selected_session_job()
        return st.rerun()
    try:
        crawler_config, page_config, activity_log_size = build_configs(values)
    except (ValidationError, ValueError) as exc:
        st.error(str(exc))
        return
    crawl_id = generate_crawl_id(
        seq=next_crawl_sequence(_SESSIONS_ROOT, st.session_state.session_id)
    )
    job = start_crawl_job(
        session_id=st.session_state.session_id,
        crawl_id=crawl_id,
        crawler_config=crawler_config,
        page_config=page_config,
        activity_log_size=activity_log_size,
        sessions_root=_SESSIONS_ROOT,
    )
    st.session_state.job = job
    st.session_state.crawl_id = crawl_id
    st.session_state.job_state = _STATE_RUNNING
    st.session_state.started_at = datetime.now(timezone.utc)
    st.session_state.last_elapsed = ""
    st.session_state.events = []
    st.session_state.latest_event = {"limit": crawler_config.limit}
    st.session_state.progress_chart_history = []
    st.session_state.prev_successful_pages = 0
    st.session_state.prev_failed_pages = 0
    st.session_state.prev_discovered_pages = 0
    st.session_state.active_output_dir = ""
    st.session_state.activity_log_size = activity_log_size
    st.session_state.activity_log_latest_line = None
    st.rerun()


def _stop_job() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.job
    if job is not None and job.thread.is_alive():
        st.session_state.job_state = _STATE_CANCEL_REQUESTED
        request_cancel(job)
        return st.rerun()
    st.warning(strings["ERROR_NO_ACTIVE_CRAWL"])


def _on_stop_dismiss() -> None:
    st.session_state.stop_confirmation_open = False


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_stop_dismiss)
def _stop_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

    def _cancel() -> None:
        st.session_state.stop_confirmation_open = False
        st.rerun()

    def _confirm() -> None:
        st.session_state.stop_confirmation_open = False
        _stop_job()

    render_confirm_dialog(
        body=strings["DIALOG_STOP_BODY"],
        cancel_label=strings["DIALOG_BTN_KEEP"],
        cancel_key="stop_cancel_button",
        on_cancel=_cancel,
        confirm_label=strings["DIALOG_BTN_STOP"],
        confirm_key="stop_confirm_button",
        confirm_icon=":material/stop_circle:",
        on_confirm=_confirm,
    )


def _crawl_result_files() -> list[Any]:
    return list(list_crawl_result_files(_session_root()))


def _list_session_indexes() -> list[Any]:
    return list_session_indexes(_session_root())


def _start_vector_index_job(values: dict[str, Any]) -> None:
    # Guard: if the registry already has an alive indexing job for this session
    # (e.g. a second tab started one), reattach instead of launching a duplicate.
    if get_active_vector_job_snapshot(st.session_state.session_id) is not None:
        _reattach_selected_session_vector_job()
        return st.rerun()
    try:
        config = IndexingConfig(
            chunk_size=values["chunk_size"],
            chunk_overlap=values["chunk_overlap"],
            embedding_model=values["embedding_model"],
            embedding_dimension=values["embedding_dimension"],
            language=values["language"],
            index_workers=values["index_workers"],
        )
    except (ValidationError, ValueError) as exc:
        st.error(str(exc))
        return
    uploads = [(file.name, file.getvalue()) for file in values["uploaded_files"]]
    vector_id = generate_vector_id(
        seq=next_vector_sequence(_SESSIONS_ROOT, st.session_state.session_id)
    )
    job = start_vector_index_job(
        session_id=st.session_state.session_id,
        vector_id=vector_id,
        config=config,
        selected_paths=values["selected_paths"],
        uploads=uploads,
        sessions_root=_SESSIONS_ROOT,
    )
    st.session_state.vector_index_job = job
    st.session_state.vector_index_id = vector_id
    st.session_state.vector_index_state = _STATE_RUNNING
    st.session_state.vector_index_progress = {}
    st.session_state.vector_index_stage = ""
    st.session_state.vector_index_result = {}
    st.session_state.vector_index_started_at = datetime.now(timezone.utc)
    st.rerun()


def _stop_vector_index_job() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    job = st.session_state.get("vector_index_job")
    if job is not None and job.thread.is_alive():
        st.session_state.vector_index_state = _STATE_CANCEL_REQUESTED
        request_vector_cancel(job)
        return st.rerun()
    st.warning(strings["VEC_ERROR_NO_ACTIVE_INDEX"])


def _on_vector_stop_dismiss() -> None:
    st.session_state.vector_index_stop_confirmation_open = False


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_vector_stop_dismiss)
def _vector_index_stop_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

    def _cancel() -> None:
        st.session_state.vector_index_stop_confirmation_open = False
        st.rerun()

    def _confirm() -> None:
        st.session_state.vector_index_stop_confirmation_open = False
        _stop_vector_index_job()

    render_confirm_dialog(
        body=strings["VEC_DIALOG_STOP_BODY"],
        cancel_label=strings["DIALOG_BTN_KEEP"],
        cancel_key="vector_stop_cancel_button",
        on_cancel=_cancel,
        confirm_label=strings["VEC_DIALOG_BTN_STOP"],
        confirm_key="vector_stop_confirm_button",
        confirm_icon=":material/stop_circle:",
        on_confirm=_confirm,
    )


def _emit_crawl_progress_toasts(strings: Strings) -> None:
    """Emit app-wide crawl progress toasts from the shared shell only."""
    latest = st.session_state.latest_event
    successful_pages = int(latest.get("successful_pages", 0) or 0)
    failed_pages = int(latest.get("failed_pages", 0) or 0)
    discovered_pages = int(latest.get("queued_discovered_urls", 0) or 0)
    new_success = successful_pages - int(st.session_state.get("prev_successful_pages", 0))
    new_fail = failed_pages - int(st.session_state.get("prev_failed_pages", 0))
    new_discovered = discovered_pages - int(st.session_state.get("prev_discovered_pages", 0))
    if not st.session_state.get("preview_file_relative_path", ""):
        if new_success > 0:
            st.toast(
                strings["TOAST_SUCCESS"].format(n=successful_pages),
                icon=_TOAST_PAGE_SUCCESS_ICON,
            )
        if new_fail > 0:
            st.toast(
                strings["TOAST_FAILED"].format(n=failed_pages),
                icon=_TOAST_PAGE_FAIL_ICON,
            )
        if new_discovered > 0:
            st.toast(
                strings["TOAST_DISCOVERED"].format(n=discovered_pages),
                icon=_TOAST_PAGE_DISCOVERED_ICON,
            )
    st.session_state.prev_successful_pages = successful_pages
    st.session_state.prev_failed_pages = failed_pages
    st.session_state.prev_discovered_pages = discovered_pages


def _crawl_event_loop_body() -> None:
    """Drain crawl events and emit shell-owned toasts on every workflow page."""
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    state_changed = _drain_job_events(st.session_state.job)
    if state_changed and st.session_state.job_state in _REFRESH_FORM_STATES:
        st.rerun()
    _emit_crawl_progress_toasts(strings)


def _render_crawl_event_loop() -> None:
    """Auto-rerun the crawl event loop only while a crawl job is active."""
    _auto_refresh_fragment(_crawl_event_loop_body, active=_crawl_job_active())


def _render_footer() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    built_by = html.escape(strings["FOOTER_BUILT_BY"].format(author=_AUTHOR_NAME))
    tagline = html.escape(strings["FOOTER_TAGLINE"])
    linkedin_label = html.escape(strings["FOOTER_LINK_LINKEDIN"])
    github_label = html.escape(strings["FOOTER_LINK_GITHUB"])
    linkedin_url = html.escape(_AUTHOR_LINKEDIN_URL, quote=True)
    github_url = html.escape(_PROJECT_GITHUB_URL, quote=True)
    linkedin_icon = html.escape(_LINKEDIN_ICON_DATA_URI, quote=True)
    github_icon = html.escape(_github_icon_data_uri(), quote=True)
    readme_label = html.escape(strings["FOOTER_LINK_README"])
    streamlit_readme_label = html.escape(strings["FOOTER_LINK_STREAMLIT_README"])
    readme_url = html.escape(_README_URL, quote=True)
    streamlit_readme_url = html.escape(_STREAMLIT_README_URL, quote=True)
    st.markdown(
        f"""
        <style>
        .crawl4md-footer {{
            margin: 2.5rem 0 0;
            padding: 1rem 0 0;
            border-top: 1px solid rgba(49, 51, 63, 0.18);
            color: inherit;
            opacity: 0.88;
            font-size: 0.9rem;
        }}
        .crawl4md-footer-inner {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.5rem 0.75rem;
        }}
        .crawl4md-footer-meta {{
            opacity: 0.76;
        }}
        .crawl4md-footer-link {{
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            color: inherit;
            text-decoration: none;
            font-weight: 600;
        }}
        .crawl4md-footer-link:hover {{
            text-decoration: underline;
        }}
        .crawl4md-footer-icon-image {{
            width: 1.25rem;
            height: 1.25rem;
            flex: 0 0 auto;
            object-fit: contain;
        }}
        </style>
        <footer class="crawl4md-footer">
            <div class="crawl4md-footer-inner">
                <span>{built_by}</span>
                <span class="crawl4md-footer-meta">{tagline}</span>
                <a class="crawl4md-footer-link" href="{linkedin_url}" target="_blank" rel="noopener noreferrer">
                    <img class="crawl4md-footer-icon-image" src="{linkedin_icon}" alt="" aria-hidden="true">{linkedin_label}
                </a>
                <a class="crawl4md-footer-link" href="{github_url}" target="_blank" rel="noopener noreferrer">
                    <img class="crawl4md-footer-icon-image" src="{github_icon}" alt="" aria-hidden="true">{github_label}
                </a>
                <a class="crawl4md-footer-link" href="{readme_url}" target="_blank" rel="noopener noreferrer">
                    {readme_label}
                </a>
                <a class="crawl4md-footer-link" href="{streamlit_readme_url}" target="_blank" rel="noopener noreferrer">
                    {streamlit_readme_label}
                </a>
            </div>
        </footer>
        """,
        unsafe_allow_html=True,
    )


def _render_portfolio_modal() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    should_show = should_show_portfolio_modal(
        browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
        last_dismissed_at=st.session_state.get(_PORTFOLIO_MODAL_LAST_DISMISSED_FIELD),
        repeat_after_hours=_PORTFOLIO_MODAL_REPEAT_HOURS,
    )
    _PORTFOLIO_MODAL_COMPONENT(
        key=_PORTFOLIO_MODAL_COMPONENT_KEY,
        height=0,
        data={
            "shouldShow": should_show,
            "delaySeconds": _PORTFOLIO_MODAL_FIRST_DELAY_SECONDS,
            "storageKey": _SESSION_STORAGE_KEY,
            "lastShownField": _PORTFOLIO_MODAL_LAST_SHOWN_FIELD,
            "lastDismissedField": _PORTFOLIO_MODAL_LAST_DISMISSED_FIELD,
            "title": strings["PORTFOLIO_MODAL_TITLE"].format(author=_AUTHOR_NAME),
            "tagline": strings["FOOTER_TAGLINE"],
            "body": strings["PORTFOLIO_MODAL_BODY"],
            "cta": strings["PORTFOLIO_MODAL_CTA"],
            "linkedinLabel": strings["PORTFOLIO_MODAL_LINK_LINKEDIN"],
            "githubLabel": strings["PORTFOLIO_MODAL_LINK_GITHUB"],
            "closeLabel": strings["PORTFOLIO_MODAL_CLOSE_LABEL"],
            "photoAlt": strings["PORTFOLIO_MODAL_PHOTO_ALT"].format(author=_AUTHOR_NAME),
            "photoUrl": _AUTHOR_PHOTO_URL,
            "linkedinUrl": _AUTHOR_LINKEDIN_URL,
            "githubUrl": _PROJECT_GITHUB_URL,
            "linkedinIconUrl": _LINKEDIN_ICON_DATA_URI,
            "githubIconUrl": _github_icon_data_uri(),
            "readmeUrl": _README_URL,
            "streamlitReadmeUrl": _STREAMLIT_README_URL,
            "readmeLabel": strings["PORTFOLIO_MODAL_LINK_README"],
            "streamlitReadmeLabel": strings["PORTFOLIO_MODAL_LINK_STREAMLIT_README"],
        },
    )


def _render_shared_styles() -> None:
    st.markdown(
        f"""
        <style>
        div[data-testid="stMainBlockContainer"],
        section.main .block-container {{
            max-width: {_FORM_MAX_WIDTH_PX}px !important;
            margin-left: auto;
            margin-right: auto;
        }}
        div[data-testid="stForm"] {{
            max-width: {_FORM_MAX_WIDTH_PX}px;
            margin-left: auto;
            margin-right: auto;
        }}
        h3#crawl4md-header,
        h3#vector-index-header,
        h3#semantic-search-header,
        h3#basic-rag-qa-header,
        h3#conversational-rag-header {{
            padding-top: 0 !important;
            padding-bottom: 0 !important;
        }}
        h3#progress {{
            padding-bottom: 0 !important;
        }}
        div[data-testid="stForm"] .stHeading h3 {{
            padding: 0.75rem 0 0 !important;
        }}
        div[class*="st-key-Stop"] button {{
            background-color: #dc2626;
            border-color: #dc2626;
            color: white;
        }}
        div[class*="st-key-Stop"] button:hover {{
            background-color: #b91c1c;
            border-color: #b91c1c;
            color: white;
        }}
        div[data-testid="stToastContainer"] {{
            top: auto !important;
            bottom: 1rem !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_session_controls(
    *,
    fields_disabled: bool,
    language_widget_key: str,
    strings: Strings,
) -> None:
    session_options = _session_options()
    session_controls_col, language_col = st.columns([5, 1], vertical_alignment="top")
    with session_controls_col:
        extend_toast = st.session_state.pop(_EXTEND_TOAST_STATE, None)
        if extend_toast == _EXTEND_TOAST_SUCCESS:
            st.toast(strings["TOAST_SESSION_EXTENDED"], icon=_TOAST_PAGE_SUCCESS_ICON)
        elif extend_toast == _EXTEND_TOAST_FAILED:
            st.toast(strings["TOAST_SESSION_EXTEND_FAILED"], icon=_TOAST_PAGE_FAIL_ICON)
        with st.container(gap="xxsmall"):
            with st.container(horizontal=True, vertical_alignment="bottom", gap="xxsmall"):
                with st.container(
                    horizontal=True, vertical_alignment="center", width="content", gap="xxsmall"
                ):
                    st.markdown(strings["SESSION_SELECTOR_LABEL"])
                    selected_session = st.selectbox(
                        label=strings["SESSION_SELECTOR_LABEL"],
                        options=session_options,
                        index=_session_selector_index(session_options),
                        key=f"session_selector_{st.session_state.session_id}",
                        label_visibility="collapsed",
                        width=240,
                        disabled=fields_disabled,
                    )
                if st.button(
                    "",
                    width=_ICON_BUTTON_WIDTH_PX,
                    key="session_create_button",
                    icon=":material/add:",
                    help=strings["SESSION_CREATE_BUTTON_TOOLTIP"],
                    disabled=fields_disabled,
                ):
                    _create_new_session()
                if st.button(
                    "",
                    width=_ICON_BUTTON_WIDTH_PX,
                    key="session_load_button",
                    icon=":material/folder_open:",
                    help=strings["SESSION_LOAD_BUTTON_TOOLTIP"],
                    disabled=fields_disabled,
                ):
                    st.session_state.session_load_dialog_open = True
                    st.session_state["_focus_session_id"] = True
                    st.rerun()
                if st.button(
                    "",
                    width=_ICON_BUTTON_WIDTH_PX,
                    key="session_extend_button",
                    icon=":material/more_time:",
                    help=strings["SESSION_EXTEND_BUTTON_TOOLTIP"],
                    disabled=fields_disabled,
                ):
                    try:
                        touch_session(_SESSIONS_ROOT, st.session_state.session_id)
                        st.session_state[_EXTEND_TOAST_STATE] = _EXTEND_TOAST_SUCCESS
                    except (OSError, ValueError):
                        st.session_state[_EXTEND_TOAST_STATE] = _EXTEND_TOAST_FAILED
                    st.rerun()
            days_left, hours_left = session_time_remaining(
                _SESSIONS_ROOT,
                st.session_state.session_id,
                retention_days=get_settings().session_retention_days,
            )
            if days_left == 0:
                if hours_left == 0:
                    expiry_key = "SESSION_EXPIRY_CAPTION_SOON"
                elif hours_left == 1:
                    expiry_key = "SESSION_EXPIRY_CAPTION_HOURS_SINGULAR"
                else:
                    expiry_key = "SESSION_EXPIRY_CAPTION_HOURS"
            elif hours_left == 0:
                expiry_key = (
                    "SESSION_EXPIRY_CAPTION_SINGULAR"
                    if days_left == 1
                    else "SESSION_EXPIRY_CAPTION"
                )
            elif hours_left == 1:
                expiry_key = (
                    "SESSION_EXPIRY_CAPTION_DAY_HOUR"
                    if days_left == 1
                    else "SESSION_EXPIRY_CAPTION_DAYS_HOUR"
                )
            else:
                expiry_key = (
                    "SESSION_EXPIRY_CAPTION_DAY_HOURS"
                    if days_left == 1
                    else "SESSION_EXPIRY_CAPTION_DAYS_HOURS"
                )
            st.caption(strings[expiry_key].format(days=days_left, hours=hours_left))
        if selected_session != st.session_state.session_id:
            _select_session_id(str(selected_session))
            st.rerun()
    with language_col, st.container(horizontal_alignment="right"):
        language_default = (
            _normalize_language(st.session_state.get("language", _DEFAULT_LANGUAGE))
            if language_widget_key not in st.session_state
            else None
        )
        st.segmented_control(
            label=strings["LANG_SELECTOR_LABEL"],
            options=list(CATALOG.keys()),
            key=language_widget_key,
            default=language_default,
            label_visibility="collapsed",
            disabled=fields_disabled,
            on_change=_on_language_change,
            args=(language_widget_key,),
        )


def _import_page_module(module_name: str) -> Any:
    app_dir = str(_APP_DIR)
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    return importlib.import_module(module_name)


def _crawl_page_context(crawl_module: Any) -> Any:
    return crawl_module.CrawlPageContext(
        current_runtime=_current_crawl_runtime,
        start_job=_start_job,
        stop_confirmation_dialog=_stop_confirmation_dialog,
        render_ready_result_panel=_render_ready_result_panel,
        render_live_area=_render_live_area,
        render_downloads=_render_downloads,
        default_language=_DEFAULT_LANGUAGE,
    )


def _vector_index_page_context(vector_module: Any) -> Any:
    return vector_module.VectorIndexPageContext(
        current_runtime=_current_vector_runtime,
        crawl_result_files=_crawl_result_files,
        start_job=_start_vector_index_job,
        stop_confirmation_dialog=_vector_index_stop_confirmation_dialog,
        render_live_area=_render_vector_index_live_area,
        render_downloads=_render_downloads,
        default_language=_DEFAULT_LANGUAGE,
    )


def _rag_page_context() -> RagPageContext:
    return RagPageContext(
        default_language=_DEFAULT_LANGUAGE,
        list_indexes=_list_session_indexes,
        render_downloads=_render_downloads,
        session_root=_session_root,
    )


def _page_renderers() -> dict[str, Callable[[], None]]:
    renderers: dict[str, Callable[[], None]] = {}
    for page_spec in APP_PAGE_SPECS:
        page_module = _import_page_module(page_spec.module_name)
        if page_spec.page_id == DEFAULT_PAGE_ID:
            renderers[page_spec.page_id] = partial(
                page_module.render_page,
                _crawl_page_context(page_module),
            )
        elif page_spec.page_id == _VECTOR_INDEX_PAGE_ID:
            renderers[page_spec.page_id] = partial(
                page_module.render_page,
                _vector_index_page_context(page_module),
            )
        elif page_spec.page_id in _RAG_PAGE_IDS:
            renderers[page_spec.page_id] = partial(
                page_module.render_page,
                _rag_page_context(),
            )
        else:
            renderers[page_spec.page_id] = page_module.render_page
    return renderers


def _navigation_pages(strings: Strings) -> list[Any]:
    renderers = _page_renderers()
    return [
        st.Page(
            renderers[page_spec.page_id],
            title=strings[page_spec.nav_label_key],
            icon=page_spec.icon,
            url_path=page_spec.url_path,
            default=page_spec.page_id == DEFAULT_PAGE_ID,
        )
        for page_spec in APP_PAGE_SPECS
    ]


def _render_page_header(page_spec: AppPageSpec, strings: Strings) -> None:
    st.title(strings[page_spec.title_key])
    st.write(strings[page_spec.subtitle_key])


_init_state()
_mount_session_storage()
active_strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))

# Show deferred "session created" toast only once the storage component has
# confirmed the localStorage write. Firing earlier shows it on an intermediate
# rerun that can be replaced by component callbacks, making the toast disappear.
if (
    st.session_state.get(_CREATE_TOAST_STATE)
    and not st.session_state.pending_browser_session_records
):
    st.session_state.pop(_CREATE_TOAST_STATE)
    st.toast(active_strings["TOAST_SESSION_CREATED"], icon=_TOAST_PAGE_SUCCESS_ICON)
if st.session_state.get(_LOAD_TOAST_STATE) and not st.session_state.pending_browser_session_records:
    _load_toast_id = st.session_state.pop(_LOAD_TOAST_STATE)
    st.toast(
        active_strings["TOAST_SESSION_LOADED"].format(id=_load_toast_id),
        icon=":material/folder_open:",
    )
if (
    st.session_state.get(_SWITCH_TOAST_STATE)
    and not st.session_state.pending_browser_session_records
):
    _switch_toast_id = st.session_state.pop(_SWITCH_TOAST_STATE)
    st.toast(
        active_strings["DIALOG_LOAD_SESSION_ALREADY_LOADED"].format(id=_switch_toast_id),
        icon=":material/folder_open:",
    )
if st.session_state.get("upload_done_folder"):
    _upload_folder = st.session_state.pop("upload_done_folder")
    st.toast(
        active_strings["FILES_UPLOAD_SUCCESS"].format(folder=_upload_folder),
        icon=_TOAST_PAGE_SUCCESS_ICON,
    )
if st.session_state.get("sample_import_done_folder"):
    _sample_folder = st.session_state.pop("sample_import_done_folder")
    st.toast(
        active_strings["FILES_SAMPLE_IMPORT_SUCCESS"].format(folder=_sample_folder),
        icon=_TOAST_PAGE_SUCCESS_ICON,
    )
_pending_page_toast = st.session_state.pop(_PENDING_PAGE_TOAST_STATE, None)
if _pending_page_toast:
    st.toast(_pending_page_toast, icon=_TOAST_PAGE_SUCCESS_ICON)

# Register the page router on *every* run before any st.stop() so a deep-linked
# URL (e.g. /vector-index) survives the session-bootstrap reruns below. Were
# st.navigation() reached only after the gates, stopping during hydration would
# drop the requested page and Streamlit would fall back to the default page.
_render_shared_styles()
navigation_page = st.navigation(_navigation_pages(active_strings), position="top")

bootstrap_state = bootstrap_gate_state(
    browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
    pending_bootstrap_session_id=st.session_state.pending_bootstrap_session_id,
    session_storage_write_failed=st.session_state.session_storage_write_failed,
)
if bootstrap_state == "hydrating":
    st.title(active_strings["PAGE_TITLE"])
    st.write(active_strings["PAGE_SUBTITLE"])
    st.info(active_strings["SESSION_LOADING"])
    st.stop()

_ensure_selected_session()
bootstrap_state = bootstrap_gate_state(
    browser_sessions_hydrated=st.session_state.browser_sessions_hydrated,
    pending_bootstrap_session_id=st.session_state.pending_bootstrap_session_id,
    session_storage_write_failed=st.session_state.session_storage_write_failed,
)
active_language_widget_key = _sync_language_widget_state()
if bootstrap_state != "ready":
    active_strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.title(active_strings["PAGE_TITLE"])
    st.write(active_strings["PAGE_SUBTITLE"])
    if bootstrap_state == "storage_error":
        st.error(active_strings["ERROR_SESSION_STORAGE_WRITE"])
        st.stop()
    st.info(active_strings["SESSION_LOADING"])
    st.stop()

_reattach_selected_session_job()
_reattach_selected_session_vector_job()
_run_startup_cleanup(
    tuple(
        sorted(
            set(_session_options())
            | active_registry_session_ids()
            | active_vector_registry_session_ids()
        )
    )
)

# Route this run's log records to the selected session's log file.
set_log_session_id(st.session_state.get("session_id", ""))

active_strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
_render_crawl_event_loop()

selected_page_spec = page_spec_by_nav_label(navigation_page.title, active_strings)
_render_page_header(selected_page_spec, active_strings)
_, _, _, session_fields_disabled = _current_crawl_runtime()
_render_session_controls(
    fields_disabled=session_fields_disabled,
    language_widget_key=active_language_widget_key,
    strings=active_strings,
)
if st.session_state.session_load_dialog_open:
    _load_session_dialog()

navigation_page.run()
_render_footer()
_render_portfolio_modal()
