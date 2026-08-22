"""Typed, env-driven configuration for the Streamlit app.

This is the app's single source of deployment-tunable settings — the Python
equivalent of a React ``config.ts`` that loads ``process.env`` into a typed
``EnvironmentVariables`` object. Values are read (in increasing precedence) from
``.env.defaults`` (committed defaults), ``.env`` (local, git-ignored overrides),
and the process environment — which is what Streamlit Community Cloud uses, since
it exposes root-level ``secrets.toml`` keys as environment variables.

Only **non-secret** knobs live here. Credentials (``AWS_*``, ``OPENAI_API_KEY``)
stay as plain environment variables read by their own SDKs, so secrets never mix
with regular configuration.

The library config models (``crawl4md``/``vector_indexer``/``rag_engine``) remain
authoritative; these settings just let an operator change the *starting* values
per environment without editing code or redeploying.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[4]
_ENV_DEFAULTS = _REPO_ROOT / ".env.defaults"
_ENV_LOCAL = _REPO_ROOT / ".env"

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    """Deployment-tunable, non-secret settings for the app.

    Each field maps to an UPPER_SNAKE_CASE environment variable of the same name
    (case-insensitive). Change a value in ``.env`` (local) or the Streamlit Cloud
    Secrets console (deployed) and restart the app — no code change or redeploy.

    Fields are **required** and carry no in-code fallbacks: ``.env.defaults``
    (committed) is the single source of truth for every default. Constructing
    ``Settings`` without that file — and without the matching environment
    variables — is a configuration error and fails fast.
    """

    model_config = SettingsConfigDict(
        env_file=(_ENV_DEFAULTS, _ENV_LOCAL),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Step 1 · Crawl (crawl4md) ────────────────────────────────────────────
    # Default *starting* values for the crawl form; users can still override any
    # of these per crawl in the UI. Changing them sets the deployed app's
    # out-of-the-box defaults.
    #
    # Pages to crawl before stopping (the crawl breadth).
    crawl_limit: int
    # How many links deep to follow from each seed URL.
    crawl_max_depth: int
    # Parallel page fetches. Higher = faster but more load and WAF risk.
    crawl_max_concurrent: int
    # Pages buffered before each incremental flush to disk.
    crawl_flush_interval: int
    # Polite delay (seconds) between page fetches.
    crawl_delay: float
    # Extra retry rounds for failed pages (the crawler enforces a minimum of 2).
    crawl_max_retries: int
    # Seconds to wait for late content after a page loads.
    crawl_wait_for: float
    # Per-page navigation/extraction timeout, in seconds.
    crawl_timeout: float
    # Maximum size (MB) of a single extracted page file (larger pages are split).
    crawl_max_file_size_mb: float
    # Lines of activity log retained for the live crawl view.
    crawl_activity_log_size: int
    # Default seed URL(s) pre-filled in the crawl form (comma-separated for more
    # than one). Users can still edit these per crawl.
    crawl_default_urls: str
    # Default "only include" URL filter(s), comma-separated (substring or regex).
    crawl_include_only_paths: str
    # Default "skip" URL filter(s), comma-separated (substring or regex).
    crawl_exclude_paths: str
    # Default HTML tags stripped before extraction, comma-separated.
    crawl_exclude_tags: str
    # Default output file extension for extracted pages (".md" or ".txt").
    crawl_default_output_extension: str
    # When True, the initial crawl also routes through the configured proxies
    # (the CRAWL_PROXIES secret); when False (default) proxies are used only on
    # retry rounds. Has no effect unless CRAWL_PROXIES is set.
    crawl_proxy_on_initial: bool

    # ── Step 2 · Vector index (vector_indexer) ───────────────────────────────
    # Tokens per chunk. Larger keeps more context together but retrieves coarser
    # matches; smaller is more precise but produces more chunks.
    vector_chunk_size: int
    # Overlap between adjacent chunks, so context is not cut at boundaries.
    vector_chunk_overlap: int
    # Default embedding vector size. Must be supported by the chosen model;
    # smaller = cheaper/faster search, larger = potentially higher quality.
    vector_embedding_dimension: int
    # Default number of parallel embedding workers. Cloud models (Titan/OpenAI)
    # index faster with more; the local ONNX model is forced to 1 worker.
    vector_index_workers: int
    # Embedding models offered in the Vector Index dropdown, in display order
    # (comma-separated). Unknown ids are ignored; supported models not listed
    # here are still appended so none disappear.
    vector_embedding_models: str
    # The embedding model pre-selected in that dropdown.
    vector_default_embedding_model: str

    # ── Steps 3-5 · RAG (rag_engine) ─────────────────────────────────────────
    # Chunks retrieved as context for QA/conversational answers. More = broader
    # context but more tokens/noise.
    rag_top_k: int
    # Top matches (highest similarity) retrieved as knowledge on the Simple RAG
    # Q&A page (Step 4).
    basic_rag_qa_top_results: int
    # Tones offered on the Step 4 Tone selector (comma-separated), in order.
    basic_rag_qa_tones: str
    # The tone pre-selected on the Step 4 Tone selector.
    basic_rag_qa_default_tone: str
    # Path (relative to the repo root) to the Step 4 prompt template file. Edit
    # that file to reword the generated prompt without a code change; a missing
    # or empty file falls back to the built-in rag_engine default.
    basic_rag_qa_prompt_template_file: str
    # Per-session token budget shown on the Step 4 Token usage panel. The panel's
    # % Usage is the session total divided by this quota. Display-only; it does
    # not block sending.
    basic_rag_qa_session_token_quota: int
    # Per-session USD cost budget shown beside the token quota (drives the panel's
    # $ Usage %). Display-only; overridable per deploy; it does not block sending.
    basic_rag_qa_session_cost_quota: float
    # Language models offered on the RAG pages (comma-separated rag_engine
    # catalog ids), in display order. Unknown ids are ignored.
    rag_llm_models: str
    # The language model pre-selected on the RAG pages.
    rag_default_llm_model: str
    # Comma-separated size bands (XS, Small, Medium, Large, XL, Frontier) shown in
    # the RAG model picker; models outside these bands are hidden.
    rag_llm_size_bands: str
    # Default number of ranked matches shown on the Semantic Search page.
    semantic_search_top_n: int
    # Default open tab for each Semantic Search result card: "raw" or "preview".
    semantic_search_default_tab: str

    # ── Session lifecycle ────────────────────────────────────────────────────
    # Days an inactive browser session's files are kept before the startup
    # cleanup deletes them. Loading or crawling in a session resets its clock.
    session_retention_days: int

    # ── App UI limits ────────────────────────────────────────────────────────
    # Largest file (MB) the app will serve as a download (above this it is
    # shown but view-only).
    ui_download_limit_mb: int
    # Largest inline text preview (KB) before previews are truncated.
    ui_preview_limit_kb: int
    # Seconds between auto-refreshes of the live crawl/index progress panels.
    ui_live_refresh_sec: int
    # Seconds between auto-refreshes of the Output Files download panel.
    ui_downloads_refresh_sec: int
    # Shared key that signs downloadable zips so an exported folder can be
    # re-uploaded to an instance using the same key. Overridable per deployment.
    zip_signing_secret: str

    # ── Logging ──────────────────────────────────────────────────────────
    # Minimum log level shown in the terminal and the log file (threshold model:
    # DEBUG < INFO < WARNING < ERROR; the user-facing WARN is accepted for
    # WARNING). Lower shows more detail; raise to WARNING/ERROR in production to
    # quiet the per-page developer traces without a redeploy.
    log_level: str
    # Per-session developer log file, written under each browser session's folder
    # (path relative to that session's directory) and surfaced in the Files panel.
    log_file: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (loaded once)."""
    return Settings()
