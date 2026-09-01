"""Shared type definition for the crawl4md translation catalog."""

from __future__ import annotations

from typing import TypedDict


class Strings(TypedDict):
    # ── Page ──────────────────────────────────────────────────────────────
    PAGE_TITLE: str
    PAGE_SUBTITLE: str
    SESSION_PREFIX: str  # template: {session_id}
    SESSION_LOADING: str
    SESSION_SELECTOR_LABEL: str
    SESSION_EXPIRY_CAPTION: str  # template: {days}
    SESSION_EXPIRY_CAPTION_SINGULAR: str
    SESSION_EXPIRY_CAPTION_DAYS_HOURS: str  # template: {days}, {hours}
    SESSION_EXPIRY_CAPTION_DAY_HOURS: str  # template: {hours}
    SESSION_EXPIRY_CAPTION_DAYS_HOUR: str  # template: {days}
    SESSION_EXPIRY_CAPTION_DAY_HOUR: str
    SESSION_EXPIRY_CAPTION_HOURS: str  # template: {hours}
    SESSION_EXPIRY_CAPTION_HOURS_SINGULAR: str
    SESSION_EXPIRY_CAPTION_SOON: str
    SESSION_CREATE_BUTTON_TOOLTIP: str
    SESSION_LOAD_BUTTON_TOOLTIP: str
    SESSION_EXTEND_BUTTON_TOOLTIP: str
    PROGRESS_HEADER: str
    PROGRESS_CAPTION: str
    PROGRESS_EXPANDER_LABEL: str
    PROGRESS_EXPANDER_LABEL_ACTIVE: str  # template: {crawl_id}
    LANG_SELECTOR_LABEL: str
    NAV_CRAWL: str
    NAV_VECTOR_INDEX: str
    NAV_SEMANTIC_SEARCH: str
    NAV_BASIC_RAG_QA: str
    NAV_CONVERSATIONAL_RAG: str
    PAGE_VECTOR_INDEX_TITLE: str
    PAGE_VECTOR_INDEX_SUBTITLE: str
    PAGE_SEMANTIC_SEARCH_TITLE: str
    PAGE_SEMANTIC_SEARCH_SUBTITLE: str
    PAGE_BASIC_RAG_QA_TITLE: str
    PAGE_BASIC_RAG_QA_SUBTITLE: str
    PAGE_CONVERSATIONAL_RAG_TITLE: str
    PAGE_CONVERSATIONAL_RAG_SUBTITLE: str
    PLACEHOLDER_SECTION_HEADER: str
    PLACEHOLDER_SECTION_CAPTION: str
    PLACEHOLDER_EXPANDER_LABEL: str
    PLACEHOLDER_VECTOR_INDEX: str
    PLACEHOLDER_SEMANTIC_SEARCH: str
    PLACEHOLDER_BASIC_RAG_QA: str
    PLACEHOLDER_CONVERSATIONAL_RAG: str
    # ── RAG pages (Steps 3-5) ─────────────────────────────────────────────
    RAG_NO_INDEX_HINT: str
    RAG_INDEX_LABEL: str
    RAG_INDEX_HELP: str
    RAG_INDEX_OPTION: str  # template: {folder}, {run}, {model}, {chunks}
    RAG_LLM_LABEL: str
    RAG_LLM_HELP: str
    RAG_LLM_TAG_OFFLINE: str
    RAG_LLM_TAG_CLOUD: str
    RAG_LLM_SIZE_SMALL: str
    RAG_LLM_SIZE_MEDIUM: str
    RAG_LLM_SIZE_LARGE: str
    RAG_LLM_INDICATOR_OFFLINE: str
    RAG_LLM_INDICATOR_CLOUD: str
    RAG_TOP_K_LABEL: str
    RAG_TOP_K_HELP: str
    RAG_SOURCES_HEADER: str
    RAG_SOURCE_CAPTION: str  # template: {source}, {score}
    RAG_MODEL_USED_CAPTION: str  # template: {model}
    RAG_GENERATING: str
    SEARCH_SECTION_HEADER: str
    SEARCH_SECTION_CAPTION: str
    SEARCH_QUERY_LABEL: str
    SEARCH_QUERY_PLACEHOLDER: str
    SEARCH_BUTTON: str
    SEARCH_SEARCHING: str
    SEARCH_RESULTS_EXPANDER: str  # template: {count}
    SEARCH_RESULTS_PANEL: str
    SEARCH_NO_RESULTS: str
    SEARCH_RESULTS_EMPTY: str
    SEARCH_META_HEADER: str
    SEARCH_META_CREATED: str
    SEARCH_META_MODEL: str
    SEARCH_META_LANGUAGE: str
    SEARCH_META_FILES: str
    SEARCH_META_DIMENSION_CHUNKS: str
    SEARCH_META_CHUNK_SIZE_OVERLAP: str
    SEARCH_META_SKIPPED: str
    SEARCH_META_COLLECTION: str
    SEARCH_TOP_N_LABEL: str
    SEARCH_TOP_N_HELP: str
    SEARCH_RESULT_HEADER: str  # template: {rank}, {source}
    SEARCH_RESULT_SIMILARITY: str
    SEARCH_RESULT_TAB_PREVIEW: str
    SEARCH_RESULT_TAB_RAW: str
    SEARCH_RESULT_ID: str  # template: {id}
    SEARCH_RESULT_SIZE: str  # template: {size}
    SEARCH_RESULT_LANGUAGE: str  # template: {language}
    SEARCH_HISTORY_EXPANDER: str
    SEARCH_HISTORY_EMPTY: str
    SEARCH_HISTORY_REPLAY_HELP: str
    SEARCH_HISTORY_PIN_HELP: str
    SEARCH_HISTORY_UNPIN_HELP: str
    SEARCH_HISTORY_INDEX_GONE: str
    SEARCH_HISTORY_LABEL_QUERY: str
    SEARCH_HISTORY_LABEL_TIME: str
    SEARCH_HISTORY_LABEL_RESULTS_TIME: str
    SEARCH_HISTORY_LABEL_INDEX_NAME: str
    SEARCH_HISTORY_LABEL_INDEX_DATE: str
    SEARCH_HISTORY_LABEL_DETAILS: str
    BASIC_QA_SECTION_HEADER: str
    BASIC_QA_SECTION_CAPTION: str
    BASIC_QA_LLM_LABEL: str
    BASIC_QA_LLM_HELP: str
    BASIC_QA_TOP_RESULTS_LABEL: str
    BASIC_QA_TOP_RESULTS_HELP: str
    BASIC_QA_TONE_LABEL: str
    BASIC_QA_TONE_HELP: str
    BASIC_QA_QUESTION_LABEL: str
    BASIC_QA_QUESTION_PLACEHOLDER: str
    BASIC_QA_GENERATE_BUTTON: str
    BASIC_QA_GENERATE_HELP: str
    BASIC_QA_SEARCHING: str
    BASIC_QA_RESULTS_EMPTY: str
    BASIC_QA_PROMPT_LABEL: str
    BASIC_QA_PROMPT_PLACEHOLDER: str
    BASIC_QA_PROMPT_HELP: str
    BASIC_QA_SEND_BUTTON: str
    BASIC_QA_SEND_HELP: str
    BASIC_QA_MAXIMIZE_HELP: str
    BASIC_QA_MAXIMIZE_TITLE: str
    BASIC_QA_MAXIMIZE_APPLY: str
    BASIC_QA_MAXIMIZE_CAPTION: str
    BASIC_QA_MAXIMIZE_APPLIED_TOAST: str
    BASIC_QA_EDIT_TEMPLATE_BUTTON: str
    BASIC_QA_EDIT_TEMPLATE_HELP: str
    BASIC_QA_EDIT_TEMPLATE_TITLE: str
    BASIC_QA_EDIT_TEMPLATE_CAPTION: str
    BASIC_QA_EDIT_TEMPLATE_SAVE: str
    BASIC_QA_EDIT_TEMPLATE_RESET: str
    BASIC_QA_EDIT_TEMPLATE_INVALID: str
    BASIC_QA_TEMPLATE_SAVED_TOAST: str
    BASIC_QA_TEMPLATE_RESET_TOAST: str
    BASIC_QA_NO_PROMPT_HINT: str
    BASIC_QA_ANSWER_HEADER: str
    BASIC_QA_ANSWER_STATS: str  # template: {model}, {input}, {output}, {total}, {seconds}
    BASIC_QA_TOKEN_NA: str
    BASIC_QA_TOKEN_PANEL_TITLE: str
    BASIC_QA_SUMMARY_QUOTA_LABEL: str
    BASIC_QA_SUMMARY_USAGE_LABEL: str
    BASIC_QA_SUMMARY_INPUT_LABEL: str
    BASIC_QA_SUMMARY_OUTPUT_LABEL: str
    BASIC_QA_SUMMARY_TOTAL_LABEL: str
    BASIC_QA_TXN_PANEL_TITLE: str
    BASIC_QA_TXN_COL_TIME: str
    BASIC_QA_TXN_COL_PROVIDER: str
    BASIC_QA_TXN_COL_CLOUD: str
    BASIC_QA_TXN_COL_COST: str
    BASIC_QA_TXN_COL_PROCESS: str
    BASIC_QA_PROCESS_ANSWER_GEN: str
    BASIC_QA_TXN_EMPTY: str
    BASIC_QA_COST_UNDER_MIN: str
    BASIC_QA_COST_DISCLAIMER: str  # template: {date}, {sources}
    BASIC_QA_PRICING_LABEL: str
    BASIC_QA_PRICING_HELP: str
    BASIC_QA_PRICING_TITLE: str
    BASIC_QA_TXN_CSV_LABEL: str
    BASIC_QA_TXN_CSV_HELP: str
    BASIC_QA_HISTORY_EXPANDER: str
    BASIC_QA_HISTORY_EMPTY: str
    BASIC_QA_HISTORY_REPLAY_HELP: str
    BASIC_QA_HISTORY_PIN_HELP: str
    BASIC_QA_HISTORY_UNPIN_HELP: str
    BASIC_QA_HISTORY_LABEL_QUESTION: str
    BASIC_QA_HISTORY_LABEL_TIME: str
    BASIC_QA_HISTORY_DETAILS_EXPANDER: str
    BASIC_QA_HISTORY_PROMPT_EXPANDER: str
    BASIC_QA_HISTORY_ANSWER_EXPANDER: str
    BASIC_QA_HISTORY_META_INDEX_NAME: str
    BASIC_QA_HISTORY_META_INDEX_DATE: str
    BASIC_QA_HISTORY_META_MODEL: str
    BASIC_QA_HISTORY_META_TONE: str
    BASIC_QA_HISTORY_META_TOP: str
    BASIC_QA_HISTORY_META_TOKENS: str
    BASIC_QA_HISTORY_META_TIME: str
    BASIC_QA_HISTORY_TOKENS_VALUE: str  # template: {input}, {output}, {total}
    BASIC_QA_HISTORY_TIME_BREAKDOWN: str  # template: {search}, {answer}, {total}
    CHAT_SECTION_HEADER: str
    CHAT_SECTION_CAPTION: str
    CHAT_INPUT_PLACEHOLDER: str
    CHAT_CLEAR_BUTTON: str
    CHAT_EMPTY_HINT: str
    # ── Conversational RAG controls + inspection (Step 5) ─────────────────
    CONV_ADVANCED_LABEL: str
    CONV_RERANKER_LABEL: str
    CONV_RERANKER_HELP: str
    CONV_RERANKER_OFF: str
    CONV_RERANKER_LOCAL: str
    CONV_RERANKER_LLM: str
    CONV_AUX_MODEL_LABEL: str
    CONV_AUX_MODEL_HELP: str
    CONV_DECOMPOSITION_LABEL: str
    CONV_DECOMPOSITION_HELP: str
    CONV_FOLLOWUPS_LABEL: str
    CONV_FOLLOWUPS_HELP: str
    CONV_INSPECT_LABEL: str
    CONV_INSPECT_HELP: str
    CONV_THRESHOLD_LABEL: str
    CONV_THRESHOLD_HELP: str
    CONV_THRESHOLD_CAPTION: str  # template: {drop}, {keep}
    CONV_INSPECT_EXPANDER: str
    CONV_TAB_DECOMPOSITION: str
    CONV_TAB_RETRIEVAL: str
    CONV_TAB_RERANKING: str
    CONV_TAB_STATE: str
    CONV_TAB_FOLLOWUPS: str
    CONV_INSPECT_QUESTION: str
    CONV_INSPECT_SUBQUESTIONS: str
    CONV_INSPECT_DEGRADED: str
    CONV_INSPECT_RERANKER_USED: str  # template: {reranker}
    CONV_INSPECT_STATE_SUMMARY: str
    CONV_INSPECT_STATE_ENTITIES: str
    CONV_INSPECT_STATE_THREADS: str
    CONV_INSPECT_STATE_RECENT: str
    CONV_INSPECT_STATE_EMPTY: str
    CONV_INSPECT_FOLLOWUPS_NONE: str
    CONV_META_TIMINGS: str
    CONV_META_PLAN: str
    CONV_META_RETRIEVE: str
    CONV_META_RERANK: str
    CONV_META_ANSWER: str
    CONV_META_FOLLOWUPS: str
    CONV_META_STATE: str
    CONV_META_ANSWER_MODEL: str
    CONV_META_AUX_MODEL: str
    CONV_META_RERANKER: str
    CONV_FOLLOWUPS_CAPTION: str
    CONV_HISTORY_PANEL_TITLE: str
    CONV_HISTORY_EMPTY: str
    CONV_HISTORY_PIN: str
    CONV_HISTORY_UNPIN: str
    CONV_HISTORY_REPLAY: str
    # ── Form ──────────────────────────────────────────────────────────────
    FORM_SUBHEADER: str
    FORM_CAPTION: str
    FORM_EXPANDER_LABEL: str
    FORM_URLS_LABEL: str
    FORM_URLS_HELP: str
    FORM_INCLUDE_PATHS_LABEL: str
    FORM_INCLUDE_PATHS_HELP: str
    FORM_EXCLUDE_PATHS_LABEL: str
    FORM_EXCLUDE_PATHS_HELP: str
    FORM_LIMIT_LABEL: str
    FORM_LIMIT_HELP: str
    FORM_DELAY_LABEL: str
    FORM_DELAY_HELP: str
    FORM_DEPTH_LABEL: str
    FORM_DEPTH_HELP: str
    FORM_RETRIES_LABEL: str
    FORM_RETRIES_HELP: str
    FORM_OUTPUT_FORMAT_LABEL: str
    FORM_OUTPUT_FORMAT_HELP: str
    FORM_EXTRACT_MAIN_LABEL: str
    FORM_EXTRACT_MAIN_HELP: str
    FORM_ADVANCED_LABEL: str
    FORM_FLUSH_LABEL: str
    FORM_FLUSH_HELP: str
    FORM_MAX_FILE_SIZE_LABEL: str
    FORM_MAX_FILE_SIZE_HELP: str
    FORM_WAIT_FOR_LABEL: str
    FORM_WAIT_FOR_HELP: str
    FORM_TIMEOUT_LABEL: str
    FORM_TIMEOUT_HELP: str
    FORM_ACTIVITY_LOG_LABEL: str
    FORM_ACTIVITY_LOG_HELP: str
    FORM_MAX_CONCURRENT_LABEL: str
    FORM_MAX_CONCURRENT_HELP: str
    FORM_EXCLUDE_TAGS_LABEL: str
    FORM_EXCLUDE_TAGS_HELP: str
    FORM_INCLUDE_ONLY_TAGS_LABEL: str
    FORM_INCLUDE_ONLY_TAGS_HELP: str
    # ── Action buttons ────────────────────────────────────────────────────
    BTN_START: str
    BTN_STOP: str
    # ── Stop dialog ───────────────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    DIALOG_STOP_BODY: str
    DIALOG_BTN_KEEP: str
    DIALOG_BTN_STOP: str
    # Vector-indexing stop dialog (reuses DIALOG_BTN_KEEP for "Keep running").
    VEC_DIALOG_STOP_BODY: str
    VEC_DIALOG_BTN_STOP: str
    # ── Load session dialog ───────────────────────────────────────────────
    # Note: @st.dialog title is fixed at decoration time and cannot be translated.
    DIALOG_LOAD_SESSION_ID_LABEL: str
    DIALOG_LOAD_SESSION_ID_PLACEHOLDER: str
    DIALOG_LOAD_SESSION_ID_HELP: str
    DIALOG_LOAD_BTN_CANCEL: str
    DIALOG_LOAD_BTN_LOAD: str
    DIALOG_LOAD_SESSION_NOT_FOUND: str  # template: {id}
    DIALOG_LOAD_SESSION_ALREADY_LOADED: str  # template: {id}
    DIALOG_LOAD_SESSION_INVALID_ID: str
    # ── Toast messages — {n} is the page count ────────────────────────────
    TOAST_SUCCESS: str
    TOAST_FAILED: str
    TOAST_DISCOVERED: str
    TOAST_SESSION_CREATED: str
    TOAST_SESSION_LOADED: str  # template: {id}
    TOAST_SESSION_EXTENDED: str
    TOAST_SESSION_EXTEND_FAILED: str
    # ── Progress metrics ──────────────────────────────────────────────────
    METRIC_PROCESSED_LABEL: str
    METRIC_PROCESSED_DELTA: str  # template: {n}
    METRIC_PROCESSED_DELTA_RETRY: str  # template: {n}
    METRIC_PROCESSED_TOOLTIP: str
    METRIC_SUCCESSFUL_LABEL: str
    METRIC_SUCCESSFUL_DELTA: str  # template: {n}
    METRIC_SUCCESSFUL_TOOLTIP: str
    METRIC_FAILED_LABEL: str
    METRIC_FAILED_DELTA: str  # template: {n}
    METRIC_FAILED_TOOLTIP: str
    METRIC_DISCOVERED_LABEL: str
    METRIC_DISCOVERED_DELTA: str  # template: {n}, {m}
    METRIC_DISCOVERED_TOOLTIP: str
    METRIC_LIMIT_LABEL: str
    METRIC_LIMIT_TOOLTIP: str
    METRIC_LIMIT_DELTA_REACHED: str
    METRIC_LIMIT_DELTA_MORE: str
    METRIC_STATE_WORD: str
    METRIC_STATE_DELTA: str
    METRIC_STATE_TOOLTIP: str
    # ── Progress bar labels ───────────────────────────────────────────────
    DENOM_DISCOVERED: str  # template: {n}
    DENOM_LIMIT: str  # template: {n}
    PROGRESS_ATTEMPTS: str  # template: {n}
    PROGRESS_COMPLETE: str
    PROGRESS_RETRYING: str
    # ── Progress charts ───────────────────────────────────────────────────
    CHART_CUMULATIVE_TITLE_SECOND: str
    CHART_CUMULATIVE_TITLE_MINUTE: str
    CHART_CUMULATIVE_TITLE_HOUR: str
    CHART_SERIES_LIMIT: str
    CHART_SERIES_DISCOVERED: str
    CHART_SERIES_SUCCESSFUL: str
    CHART_SERIES_FAILED: str
    CHART_TIME_UNIT_SECOND: str
    CHART_TIME_UNIT_MINUTE: str
    CHART_TIME_UNIT_HOUR: str
    # ── Status line ───────────────────────────────────────────────────────
    STATUS_CRAWLING: str  # template: {url_html}
    STATUS_ELAPSED: str  # template: {elapsed}
    STATUS_NEXT_URL: str  # template: {url_html}
    STATUS_ACTIVE_FETCHES: str  # template: {count}, {max}
    STATUS_NEXT_FETCHES: str  # template: {count}
    STATUS_MORE_URLS: str  # template: {count}
    # ── ETA phrases ───────────────────────────────────────────────────────
    ETA_ESTIMATING: str
    ETA_LESS_THAN_MINUTE: str
    ETA_MINUTES: str  # template: {n}
    ETA_HOURS_MINUTES: str  # template: {h}, {m}
    # ── State banners ─────────────────────────────────────────────────────
    BANNER_FAILED: str
    BANNER_CANCEL_REQUESTED: str
    BANNER_STOPPED: str
    # ── Error messages ────────────────────────────────────────────────────
    ERROR_NO_ACTIVE_CRAWL: str
    ERROR_CRAWL_ALREADY_RUNNING: str
    ERROR_SESSION_STORAGE_WRITE: str
    ERROR_CRAWL_FAILED_FALLBACK: str
    # ── Activity log ──────────────────────────────────────────────────────
    ACTIVITY_LOG_HEADER: str
    # ── Files section ─────────────────────────────────────────────────────
    FILES_HEADER: str
    FILES_CRAWL_RESULT_LABEL: str
    FILES_DOWNLOADS_SUBHEADER: str
    FILES_COL_NAME: str
    FILES_COL_TYPE: str
    FILES_COL_SIZE: str
    FILES_COL_MODIFIED: str
    FILES_DOWNLOAD_TOO_LARGE: str  # template: {file}
    FILES_EXPLORE_3D_LABEL: str
    FILES_EXPLORE_3D_HELP: str
    FILES_DOWNLOADS_IN_PROGRESS: str
    FILES_DOWNLOADS_SUBTITLE: str
    FILES_PREVIEW_BUTTON: str
    FILES_PREVIEW_HELP: str  # template: {file}
    FILES_PREVIEW_PATH: str  # template: {path}
    FILES_PREVIEW_SIZE: str  # template: {size_kib}
    FILES_PREVIEW_MODIFIED_AT: str  # template: {value}
    FILES_PREVIEW_CREATED_AT: str  # template: {value}
    FILES_PREVIEW_UNSUPPORTED: str  # template: {file}
    FILES_PREVIEW_MISSING: str  # template: {file}
    FILES_PREVIEW_READ_ERROR: str  # template: {file}
    FILES_PREVIEW_EMPTY: str  # template: {file}
    FILES_PREVIEW_TRUNCATED: str  # template: {limit_kib}
    FILES_DELETE_DIALOG_CANCEL: str
    FILES_DOWNLOAD_ZIP_BUTTON: str
    FILES_DOWNLOAD_ZIP_HELP: str  # template: {folder}
    FILES_DOWNLOAD_ZIP_TOO_LARGE: str  # template: {folder}
    FILES_EXPORT_PREPARING: str  # template: {folder}
    FILES_EXPORT_DOWNLOAD_STARTED: str
    FILES_DELETE_FOLDER_BUTTON: str
    FILES_DELETE_FOLDER_HELP: str  # template: {folder}
    FILES_DELETE_FOLDER_DIALOG_TITLE: str
    FILES_DELETE_FOLDER_DIALOG_BODY: str  # template: {folder}
    FILES_DELETE_FOLDER_DIALOG_CONFIRM: str
    FILES_UPLOAD_BUTTON: str
    FILES_UPLOAD_BUTTON_HELP: str
    FILES_UPLOAD_DIALOG_TITLE: str
    FILES_UPLOAD_PROMPT: str
    FILES_UPLOAD_INVALID: str
    FILES_UPLOAD_CONFIRM_BODY: str  # template: {folder}
    FILES_UPLOAD_CONFIRM: str
    FILES_UPLOAD_CANCEL: str
    FILES_UPLOAD_SUCCESS: str  # template: {folder}
    FILES_UPLOAD_HISTORY_IMPORT_BODY: str  # template: {folder}
    FILES_UPLOAD_HISTORY_OVERWRITE_BODY: str  # template: {folder}
    FILES_UPLOAD_HISTORY_OVERWRITE_CONFIRM: str
    FILES_SAMPLE_PANEL_TITLE: str
    FILES_SAMPLE_PANEL_CAPTION: str
    FILES_SAMPLE_CATEGORY_CRAWL_RESULTS: str
    FILES_SAMPLE_CATEGORY_VECTOR_INDEXES: str
    FILES_SAMPLE_IMPORT_HELP: str
    FILES_SAMPLE_IMPORT_SUCCESS: str  # template: {folder}
    # ── Ready result download ─────────────────────────────────────────────
    READY_RESULT_HEADER: str
    READY_RESULT_SINGLE_SUBTITLE: str
    READY_RESULT_ZIP_SUBTITLE: str  # template: {count}
    READY_RESULT_DOWNLOAD_BUTTON: str
    READY_RESULT_TOO_LARGE: str
    # ── Portfolio footer ─────────────────────────────────────────────────
    FOOTER_BUILT_BY: str  # template: {author}
    FOOTER_TAGLINE: str
    FOOTER_LINK_LINKEDIN: str
    FOOTER_LINK_GITHUB: str
    FOOTER_LINK_README: str
    FOOTER_LINK_STREAMLIT_README: str
    # ── Portfolio modal ──────────────────────────────────────────────────
    PORTFOLIO_MODAL_TITLE: str  # template: {author}
    PORTFOLIO_MODAL_BODY: str
    PORTFOLIO_MODAL_CTA: str
    PORTFOLIO_MODAL_LINK_LINKEDIN: str
    PORTFOLIO_MODAL_LINK_GITHUB: str
    PORTFOLIO_MODAL_LINK_README: str
    PORTFOLIO_MODAL_LINK_STREAMLIT_README: str
    PORTFOLIO_MODAL_CLOSE_LABEL: str
    PORTFOLIO_MODAL_PHOTO_ALT: str  # template: {author}
    # ── Vector index (Step 2) ─────────────────────────────────────────────
    VEC_SECTION_HEADER: str
    VEC_SECTION_CAPTION: str
    VEC_SOURCES_LABEL: str
    VEC_SOURCES_HELP: str
    VEC_SOURCES_EMPTY: str
    VEC_UPLOAD_LABEL: str
    VEC_UPLOAD_HELP: str
    VEC_CHUNK_SIZE_LABEL: str
    VEC_CHUNK_SIZE_HELP: str
    VEC_CHUNK_OVERLAP_LABEL: str
    VEC_CHUNK_OVERLAP_HELP: str
    VEC_WORKERS_LABEL: str
    VEC_WORKERS_HELP: str
    VEC_EMBEDDING_MODEL_LABEL: str
    VEC_EMBEDDING_MODEL_HELP: str
    VEC_MODEL_TAG_LOCAL: str
    VEC_MODEL_TAG_CLOUD: str
    VEC_MODEL_INDICATOR_LOCAL: str
    VEC_MODEL_INDICATOR_CLOUD: str
    VEC_EMBEDDING_DIMENSION_LABEL: str
    VEC_EMBEDDING_DIMENSION_HELP: str
    VEC_LANGUAGE_LABEL: str
    VEC_LANGUAGE_HELP: str
    VEC_ERROR_NO_INPUTS: str
    VEC_ERROR_ALREADY_RUNNING: str
    VEC_ERROR_NO_ACTIVE_INDEX: str
    VEC_PROGRESS_HEADER: str
    VEC_STATUS_RUNNING: str
    VEC_STATUS_CHUNKS: str  # template: {processed}, {total}
    VEC_STAGE_RESOLVING_MODEL: str
    VEC_STAGE_LOADING: str
    VEC_STAGE_CHUNKING: str
    VEC_STAGE_EMBEDDING: str
    VEC_STAGE_SAVING: str
    VEC_RESULT_SUCCESS: str  # template: {files}, {chunks}
    VEC_RESULT_FAILED: str
    VEC_RESULT_CANCELLED: str
    VEC_RESULT_SKIPPED: str  # template: {count}
    VEC_RESULT_WARNINGS_LABEL: str
    VEC_RESULT_ERRORS_LABEL: str
    VEC_ERROR_SSL_HINT: str
    VEC_ERROR_OPENAI_KEY_HINT: str
    VEC_ERROR_AWS_CREDENTIALS_HINT: str
    VEC_ERROR_EMBEDDING_FAILED_HINT: str
    VEC_ERROR_MODEL_UNAVAILABLE_HINT: str
    # ── State display labels (state_key -> display name) ──────────────────
    STATE_LABELS: dict[str, str]
    # ── Library message code -> localized template (str.format params) ─────
    # Keys are stable codes emitted by the crawl4md / vector_indexer libraries.
    # Codes absent here fall back to the library-provided English text, so the
    # libraries stay the single source of truth for wording.
    MESSAGE_CODES: dict[str, str]
