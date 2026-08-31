"""SiteCrawler — synchronous wrapper around Crawl4AI."""

from __future__ import annotations

import asyncio
import concurrent.futures
import random
import re
import sys
import time
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import Any

import httpx
import nest_asyncio

from artifact_store import LibraryMessage
from crawl4md import messages
from crawl4md._internal.block_detector import (
    _BLOCK_MAX_CONTENT_LENGTH,
)
from crawl4md._internal.block_detector import (
    _BLOCK_SIGNATURES as _BLOCK_DETECTOR_SIGNATURES,
)
from crawl4md._internal.block_detector import (
    content_length_without_chrome as _content_length_without_chrome_impl,
)
from crawl4md._internal.block_detector import (
    is_blocked as _is_blocked_impl,
)
from crawl4md._internal.crawler_progress import (
    _PROGRESS_EVENT_COMPLETED as _INTERNAL_PROGRESS_EVENT_COMPLETED,
)
from crawl4md._internal.crawler_progress import (
    _PROGRESS_EVENT_DISCOVERED as _INTERNAL_PROGRESS_EVENT_DISCOVERED,
)
from crawl4md._internal.crawler_progress import (
    _PROGRESS_EVENT_INTERRUPTED as _INTERNAL_PROGRESS_EVENT_INTERRUPTED,
)
from crawl4md._internal.crawler_progress import (
    _PROGRESS_EVENT_PAGE as _INTERNAL_PROGRESS_EVENT_PAGE,
)
from crawl4md._internal.crawler_progress import (
    _PROGRESS_EVENT_STARTED as _INTERNAL_PROGRESS_EVENT_STARTED,
)
from crawl4md._internal.crawler_progress import (
    _PROGRESS_EVENT_STATUS as _INTERNAL_PROGRESS_EVENT_STATUS,
)
from crawl4md._internal.crawler_progress import (
    _PROGRESS_EVENT_WARNING as _INTERNAL_PROGRESS_EVENT_WARNING,
)
from crawl4md._internal.crawler_progress import (
    emit_crawl_warning as _emit_crawl_warning_impl,
)
from crawl4md._internal.crawler_progress import (
    emit_page_progress as _emit_page_progress_impl,
)
from crawl4md._internal.crawler_progress import (
    emit_progress as _emit_progress_impl,
)
from crawl4md._internal.docx import (
    download_docx as _download_docx_impl,
)
from crawl4md._internal.docx import (
    is_docx_response as _is_docx_response_impl,
)
from crawl4md._internal.docx import (
    is_docx_url as _is_docx_url_impl,
)
from crawl4md._internal.final_output import (
    _CLEANUP_INTERMEDIATE_FILES as _INTERNAL_CLEANUP_INTERMEDIATE_FILES,
)
from crawl4md._internal.final_output import (
    FinalOutputWriter,
    round_dir_name,
    round_num_from_dir,
)
from crawl4md._internal.http_client import (
    document_ssl_context,
    merge_document_headers,
    referer_for_url,
)
from crawl4md._internal.network_usage import NetworkUsageRecorder
from crawl4md._internal.pdf import (
    _OCR_UNAVAILABLE_WARNING as _PDF_OCR_UNAVAILABLE_WARNING,
)
from crawl4md._internal.pdf import (
    _PDF_DOWNLOAD_TIMEOUT,
    _PDF_FALLBACK_THRESHOLD,
)
from crawl4md._internal.pdf import (
    download_pdf as _download_pdf_impl,
)
from crawl4md._internal.pdf import (
    is_pdf_response as _is_pdf_response_impl,
)
from crawl4md._internal.pdf import (
    is_pdf_url as _is_pdf_url_impl,
)
from crawl4md._internal.pdf import (
    pdf_to_markdown as _pdf_to_markdown_impl,
)
from crawl4md._internal.progress_history import (
    PROGRESS_HISTORY_FILE as _INTERNAL_PROGRESS_HISTORY_FILE,
)
from crawl4md._internal.progress_history import ProgressHistoryRecorder
from crawl4md._internal.site_graph import (
    _PAGE_RECORD_DEPTH as _INTERNAL_PAGE_RECORD_DEPTH,
)
from crawl4md._internal.site_graph import (
    _PAGE_RECORD_DISCOVERED_FROM as _INTERNAL_PAGE_RECORD_DISCOVERED_FROM,
)
from crawl4md._internal.site_graph import (
    _PAGE_RECORD_PAGE_SIZE_KB as _INTERNAL_PAGE_RECORD_PAGE_SIZE_KB,
)
from crawl4md._internal.site_graph import (
    _PAGE_RECORD_ROUND_NUM as _INTERNAL_PAGE_RECORD_ROUND_NUM,
)
from crawl4md._internal.site_graph import (
    _PAGE_RECORD_STATUS as _INTERNAL_PAGE_RECORD_STATUS,
)
from crawl4md._internal.site_graph import (
    _PAGE_RECORD_URL as _INTERNAL_PAGE_RECORD_URL,
)
from crawl4md._internal.site_graph import (
    _PAGE_SIZE_DECIMAL_PLACES as _INTERNAL_PAGE_SIZE_DECIMAL_PLACES,
)
from crawl4md._internal.site_graph import (
    _PAGE_STATUS_DISCOVERED as _INTERNAL_PAGE_STATUS_DISCOVERED,
)
from crawl4md._internal.site_graph import (
    _PAGE_STATUS_FAIL as _INTERNAL_PAGE_STATUS_FAIL,
)
from crawl4md._internal.site_graph import (
    _PAGE_STATUS_SKIPPED as _INTERNAL_PAGE_STATUS_SKIPPED,
)
from crawl4md._internal.site_graph import (
    _PAGE_STATUS_SUCCESS as _INTERNAL_PAGE_STATUS_SUCCESS,
)
from crawl4md._internal.site_graph import (
    _PAGES_REGISTRY_TMP_SUFFIX as _INTERNAL_PAGES_REGISTRY_TMP_SUFFIX,
)
from crawl4md._internal.site_graph import (
    _SITE_GRAPH_FILE as _INTERNAL_SITE_GRAPH_FILE,
)
from crawl4md._internal.site_graph import SiteGraphRecorder
from crawl4md._internal.url_filter import (
    _BOILERPLATE_DOMAINS as _URL_FILTER_BOILERPLATE_DOMAINS,
)
from crawl4md._internal.url_filter import (
    _STATIC_ASSET_EXTENSIONS as _URL_FILTER_STATIC_ASSET_EXTENSIONS,
)
from crawl4md._internal.url_filter import (
    extract_base_domains as _extract_base_domains_impl,
)
from crawl4md._internal.url_filter import (
    extract_links as _extract_links_impl,
)
from crawl4md._internal.url_filter import (
    normalize_url as _normalize_url_impl,
)
from crawl4md._internal.url_filter import (
    url_allowed as _url_allowed_impl,
)
from crawl4md._internal.url_filter import (
    url_in_allowed_domain as _url_in_allowed_domain_impl,
)
from crawl4md.config import (
    _FALLBACK_WAIT_UNTIL,
    CrawlerConfig,
    CrawlResult,
    ExtractedPage,
    PageConfig,
)
from crawl4md.extractor import ContentExtractor
from crawl4md.naming import format_utc_timestamp_slug
from crawl4md.progress import ProgressReporter
from crawl4md.writer import FileWriter, PageIndexEntry, PageSidecar
from log4py import get_logger

# Applied lazily by SiteCrawler._run_rounds_sync so Streamlit's uvloop is never
# patched at import time.


class _LazyModule:
    def __init__(self, module_name: str) -> None:
        self._module_name = module_name
        self._module: Any | None = None

    def _load(self) -> Any:
        if self._module is None:
            self._module = import_module(self._module_name)
        return self._module

    def __getattr__(self, name: str) -> Any:
        return getattr(self._load(), name)


AsyncWebCrawler: Any | None = None
BrowserConfig: Any | None = None
CrawlerRunConfig: Any | None = None
ProxyConfig: Any | None = None
UndetectedAdapter: Any | None = None
AsyncPlaywrightCrawlerStrategy: Any | None = None
pymupdf: Any = _LazyModule("pymupdf")
pymupdf4llm: Any = _LazyModule("pymupdf4llm")
mammoth: Any = _LazyModule("mammoth")
markdownify: Any = _LazyModule("markdownify")
# markdownify options for DOCX HTML->Markdown (match the extractor's full-HTML mode).
_DOCX_HEADING_STYLE = "ATX"
_DOCX_STRIP_TAGS = ("img",)


def _load_crawl4ai_classes() -> tuple[Any, Any, Any]:
    global AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
    if AsyncWebCrawler is None or BrowserConfig is None or CrawlerRunConfig is None:
        crawl4ai = import_module("crawl4ai")
        async_web_crawler_cls = crawl4ai.AsyncWebCrawler
        browser_config_cls = crawl4ai.BrowserConfig
        crawler_run_config_cls = crawl4ai.CrawlerRunConfig

        if AsyncWebCrawler is None:
            AsyncWebCrawler = async_web_crawler_cls
        if BrowserConfig is None:
            BrowserConfig = browser_config_cls
        if CrawlerRunConfig is None:
            CrawlerRunConfig = crawler_run_config_cls
    return AsyncWebCrawler, BrowserConfig, CrawlerRunConfig


def _load_proxy_config_cls() -> Any | None:
    """Return Crawl4AI's ``ProxyConfig`` class, or None when this install lacks it."""
    global ProxyConfig
    if ProxyConfig is None:
        try:
            ProxyConfig = import_module("crawl4ai").ProxyConfig
        except (ImportError, AttributeError):
            return None
    return ProxyConfig


def _load_undetected_classes() -> tuple[Any, Any] | None:
    """Return ``(AsyncPlaywrightCrawlerStrategy, UndetectedAdapter)`` or None if unavailable."""
    global UndetectedAdapter, AsyncPlaywrightCrawlerStrategy
    if UndetectedAdapter is None or AsyncPlaywrightCrawlerStrategy is None:
        try:
            UndetectedAdapter = import_module("crawl4ai").UndetectedAdapter
            AsyncPlaywrightCrawlerStrategy = import_module(
                "crawl4ai.async_crawler_strategy"
            ).AsyncPlaywrightCrawlerStrategy
        except (ImportError, AttributeError):
            return None
    return AsyncPlaywrightCrawlerStrategy, UndetectedAdapter


# Seconds to pause between retry rounds so the WAF can cool down
_ROUND_COOLDOWN = 30

# ------------------------------------------------------------------
# Jitter constants — all tunable values in one place
# ------------------------------------------------------------------

# Per-page jitter multiplier ranges (applied to config.delay)
_JITTER_ROUND1_MIN = 0.1  # Round 1: light delay to avoid WAF triggers
_JITTER_ROUND1_MAX = 1.0
_JITTER_RETRY_MIN = 0.3  # Retry rounds: heavier delay for WAF cooldown
_JITTER_RETRY_MAX = 3.0

# WAF back-off: sleep after detecting a block (applied even when delay=0)
_WAF_BACKOFF_MIN = 2.0  # Multiplier lower bound (applied to config.delay)
_WAF_BACKOFF_MAX = 5.0  # Multiplier upper bound
_WAF_BACKOFF_FLOOR = 3.0  # Minimum seconds (ensures a pause even when delay=0)
_WAF_BACKOFF_CAP = 15.0  # Maximum seconds (ceiling for escalated back-off)
_WAF_CONSECUTIVE_THRESHOLD = 3  # Consecutive blocks before escalating

# Round cooldown jitter multiplier range
_ROUND_COOLDOWN_JITTER_MIN = 0.8
_ROUND_COOLDOWN_JITTER_MAX = 1.5


# ------------------------------------------------------------------
# Browser configuration defaults
# ------------------------------------------------------------------

# User-agent generation settings used when stealth mode is enabled
_USER_AGENT_MODE = "random"
_USER_AGENT_PLATFORMS = ["desktop"]
_USER_AGENT_BROWSERS = ["Chrome", "Edge"]

# ------------------------------------------------------------------
# Output directory and file naming
# ------------------------------------------------------------------

# Subdirectory name for final merged output files
_FINAL_DIR_NAME = "final"

# Subdirectory name for crawl log/diagnostic files (activity log, progress
# history, site graph, network usage).
_LOGS_DIR_NAME = "logs"

_logger = get_logger(__name__)

# Suffix for successful-page file names (e.g. "success_content_001.txt")
_SUCCESS_SUFFIX = "success_"
# Suffix for failed-page file names (e.g. "fail_content_001.txt")
_FAIL_SUFFIX = "fail_"

# Final URL list filenames.
_SUCCESS_URLS_FILE = "success_urls.txt"
_FAIL_URLS_FILE = "fail_urls.txt"
_SORTED_SUCCESS_URLS_FILE = "sorted_success_urls.txt"
_SORTED_FAIL_URLS_FILE = "sorted_fail_urls.txt"

# ------------------------------------------------------------------
# Round file naming components
# ------------------------------------------------------------------

# When True (default), intermediate files are removed once final sorted output
# is written.  Set to False to keep every intermediate file for debugging.
# Mirrors crawl4md._internal.final_output._CLEANUP_INTERMEDIATE_FILES.
_CLEANUP_INTERMEDIATE_FILES = _INTERNAL_CLEANUP_INTERMEDIATE_FILES
# Per-round sorted files are skipped when cleanup is enabled (they are
# superseded by the final/sorted_* output).
_ENABLE_SORTED_ROUND_FILES = not _CLEANUP_INTERMEDIATE_FILES

# Prefix for sorted output files within a round or final folder
_SORTED_SUCCESS_PREFIX = "sorted_success_"
_SORTED_FAIL_PREFIX = "sorted_fail_"

# ------------------------------------------------------------------
# JSONL sidecar file naming (memory-efficient extracted-page storage)
# ------------------------------------------------------------------

# Suffix for per-round sidecar files that store extracted success pages as JSONL
_SUCCESS_SIDECAR_SUFFIX = "success_pages.jsonl"
# Suffix for per-round sidecar files that store extracted fail pages as JSONL
_FAIL_SIDECAR_SUFFIX = "fail_pages.jsonl"

# Root-level deduped page registry for future site-tree graph data.
_SITE_GRAPH_FILE = _INTERNAL_SITE_GRAPH_FILE
_PAGES_REGISTRY_TMP_SUFFIX = _INTERNAL_PAGES_REGISTRY_TMP_SUFFIX
_PAGE_RECORD_URL = _INTERNAL_PAGE_RECORD_URL
_PAGE_RECORD_DISCOVERED_FROM = _INTERNAL_PAGE_RECORD_DISCOVERED_FROM
_PAGE_RECORD_PAGE_SIZE_KB = _INTERNAL_PAGE_RECORD_PAGE_SIZE_KB
_PAGE_RECORD_STATUS = _INTERNAL_PAGE_RECORD_STATUS
_PAGE_RECORD_DEPTH = _INTERNAL_PAGE_RECORD_DEPTH
_PAGE_RECORD_ROUND_NUM = _INTERNAL_PAGE_RECORD_ROUND_NUM
_PAGE_SIZE_DECIMAL_PLACES = _INTERNAL_PAGE_SIZE_DECIMAL_PLACES
_PAGE_STATUS_DISCOVERED = _INTERNAL_PAGE_STATUS_DISCOVERED
_PAGE_STATUS_SUCCESS = _INTERNAL_PAGE_STATUS_SUCCESS
_PAGE_STATUS_FAIL = _INTERNAL_PAGE_STATUS_FAIL
_PAGE_STATUS_SKIPPED = _INTERNAL_PAGE_STATUS_SKIPPED

# ------------------------------------------------------------------
# Link extraction patterns
# ------------------------------------------------------------------

# Regex to strip URL schemes in shortened display labels
_HTTPS_PREFIX_RE = re.compile(r"^https?://")

# ------------------------------------------------------------------
# Failed-page content templates
# ------------------------------------------------------------------

# Title prefix for pages that failed to crawl
_FAILED_TITLE_PREFIX = "FAILED \u2014"
# Fallback error message when the actual error is None
_UNKNOWN_ERROR_MSG = "Unknown error"
# Markdown label for the error description section
_ERROR_SECTION_HEADER = "**Error:**"
# Markdown label for the raw response section
_RAW_RESPONSE_HEADER = "**Raw response:**"

# ------------------------------------------------------------------
# Skip / empty-extraction log labels
# ------------------------------------------------------------------

# Error message assigned when extraction produces empty markdown
_EMPTY_EXTRACTION_ERROR = "No extractable content"

# ------------------------------------------------------------------
# Redirect storm detection
# ------------------------------------------------------------------

# Consecutive redirects to the same already-visited target before
# treating subsequent ones as failures (suspected anti-bot redirect).
_REDIRECT_STORM_THRESHOLD = 3
# Error message for pages caught in a redirect storm
_REDIRECT_STORM_ERROR = "Suspected anti-bot redirect"
# Error message for redirect-skipped pages that never triggered a storm
# (queue ended or pattern broke before threshold was reached)
_UNRESOLVED_REDIRECT_ERROR = "Redirect to already-visited URL (unresolved)"
# Maximum character length for shortened URLs displayed in activity labels
_SHORT_URL_MAX_LEN = 60
# Maximum URLs included in progress event previews. Counts remain uncapped.
_PROGRESS_URL_PREVIEW_LIMIT = 5

# Seconds between cancellation checks during long sleeps.
_CANCEL_POLL_INTERVAL = 0.2

# Compatibility re-export for tests and callers that imported the private
# block signature tuple from this module before detection moved internally.
_BLOCK_SIGNATURES = _BLOCK_DETECTOR_SIGNATURES

# Compatibility re-exports for tests and UI adapters that imported private
# progress event names from this module before emission moved internally.
_PROGRESS_EVENT_COMPLETED = _INTERNAL_PROGRESS_EVENT_COMPLETED
_PROGRESS_EVENT_DISCOVERED = _INTERNAL_PROGRESS_EVENT_DISCOVERED
_PROGRESS_EVENT_INTERRUPTED = _INTERNAL_PROGRESS_EVENT_INTERRUPTED
_PROGRESS_EVENT_PAGE = _INTERNAL_PROGRESS_EVENT_PAGE
_PROGRESS_EVENT_STARTED = _INTERNAL_PROGRESS_EVENT_STARTED
_PROGRESS_EVENT_STATUS = _INTERNAL_PROGRESS_EVENT_STATUS
_PROGRESS_EVENT_WARNING = _INTERNAL_PROGRESS_EVENT_WARNING
_PROGRESS_HISTORY_FILE = _INTERNAL_PROGRESS_HISTORY_FILE

# Compatibility re-export for tests and callers that imported the private
# warning constant from this module before PDF handling moved internally.
_OCR_UNAVAILABLE_WARNING = _PDF_OCR_UNAVAILABLE_WARNING


def _shorten_url(url: str) -> str:
    """Shorten a URL for display, keeping domain + trailing path segments."""
    if len(url) <= _SHORT_URL_MAX_LEN:
        return url
    # Strip scheme
    display = _HTTPS_PREFIX_RE.sub("", url)
    if len(display) <= _SHORT_URL_MAX_LEN:
        return display
    # Keep first 25 chars (domain) + … + last 30 chars (path tail)
    return display[:25] + "…" + display[-(_SHORT_URL_MAX_LEN - 26) :]


class SiteCrawler:
    """Crawls websites and collects HTML/Markdown content.

    Provides a synchronous ``crawl()`` method that wraps Crawl4AI's
    asynchronous crawler so non-technical users never see ``async``/``await``.
    """

    def __init__(
        self,
        config: CrawlerConfig,
        page_config: PageConfig | None = None,
        *,
        output_base: Path | str | None = None,
        session_id: str | None = None,
        extractor: ContentExtractor | None = None,
        writer: FileWriter | None = None,
        activity_log_size: int = 10,
        progress_callback: Callable[[Mapping[str, object]], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        fallback_fetch_function: Callable[[str], Awaitable[str]] | None = None,
    ) -> None:
        self.config = config
        self.page_config = page_config or PageConfig()
        self._output_base = Path(output_base) if output_base else Path.cwd()
        self._session_id = session_id
        self.output_dir: Path | None = None
        self._allowed_domains: set[str] = self._extract_base_domains(
            config.urls, strip_www=config.strip_www
        )
        self._extractor = extractor
        self._writer = writer
        self._activity_log_size = activity_log_size
        self._progress_callback = progress_callback
        self._should_cancel = should_cancel
        self._fallback_fetch_function = fallback_fetch_function
        self.content_files: list[Path] = []
        # Set to the error text when an unexpected error stops the crawl mid-run;
        # the crawl still finalizes its partial output and the caller (e.g. the
        # Streamlit job) reads this to report a failure while keeping that output.
        self.crawl_error: str | None = None
        # Tracks whether the OCR-unavailable warning has already been emitted
        self._ocr_warned: bool = False
        # Internal writer for failed-page content (symmetrical with _writer)
        self._fail_writer: FileWriter | None = None
        if writer is not None:
            self._fail_writer = FileWriter(
                max_file_size_mb=self.page_config.max_file_size_mb,
                file_extension=writer._file_extension,
            )
        # Per-round JSONL sidecar paths for memory-efficient final file
        # generation.  Set by _run_rounds_async before each round.
        self._success_sidecar: Path | None = None
        self._fail_sidecar: Path | None = None
        self._run_metadata: dict[str, object] = {}
        self._run_started_at_utc: datetime | None = None
        self._progress_history: ProgressHistoryRecorder | None = None
        self._logs_dir: Path | None = None
        self._site_graph = SiteGraphRecorder()
        self._network_usage = NetworkUsageRecorder()
        self._pdf_client: httpx.AsyncClient | None = None

    @property
    def _site_graph_path(self) -> Path | None:
        return self._site_graph.path

    @_site_graph_path.setter
    def _site_graph_path(self, path: Path | None) -> None:
        self._site_graph.path = path

    @property
    def _site_graph_records(self) -> dict[str, dict[str, object]]:
        return self._site_graph.records

    @_site_graph_records.setter
    def _site_graph_records(self, records: dict[str, dict[str, object]]) -> None:
        self._site_graph.records = records

    @property
    def _site_graph_dirty(self) -> bool:
        return self._site_graph.dirty

    @_site_graph_dirty.setter
    def _site_graph_dirty(self, dirty: bool) -> None:
        self._site_graph.dirty = dirty

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(self) -> list[CrawlResult]:
        """Crawl the configured URLs and return results.

        Creates a timestamped output folder.  Runs multiple rounds:
        round 1 crawls seed URLs; subsequent rounds retry blocked/failed
        URLs up to ``max_retries`` times.  Each round writes per-round
        files (``round_N_*``).  After all rounds, final merged files
        are produced (``final_success_content_*.ext``,
        ``final_success_urls.txt``, ``final_fail_urls.txt``).

        Extracted content is persisted to per-round JSONL sidecar files
        during the crawl so that heavy ``html`` and ``markdown`` fields
        can be freed from memory.  The returned ``CrawlResult`` objects
        retain only lightweight metadata (``url``, ``success``, ``error``);
        ``html`` and ``markdown`` are empty strings.
        """
        self.output_dir = self._create_output_dir()
        logs_dir = self.output_dir / _LOGS_DIR_NAME
        logs_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir = logs_dir
        _logger.info(
            "Crawl started: %d URL(s), limit %d -> %s",
            len(self.config.urls),
            self.config.limit,
            self.output_dir,
        )
        self._run_metadata = self._build_run_metadata()
        self._progress_history = ProgressHistoryRecorder(
            output_dir=logs_dir,
            session_id=str(self._run_metadata.get("session_id", self.output_dir.name)),
        )
        self._progress_history.set_round(1)
        self._site_graph.reset(logs_dir)
        self._network_usage.reset(logs_dir)
        self._emit_progress(
            {
                "event": _PROGRESS_EVENT_STARTED,
                "output_dir": str(self.output_dir),
                "limit": self.config.limit,
                "current_url": "",
                "next_url": "",
                "eta_remaining_seconds": None,
                "active_url_count": 0,
                "active_urls": [],
                "next_url_count": 0,
                "next_urls": [],
                "max_concurrent": self.config.max_concurrent,
            }
        )
        # Attach output_dir to writer so incremental flushes land there
        if self._writer is not None:
            self._writer._output_dir = self.output_dir
            self._writer.set_run_metadata(self._run_metadata)
        if self._fail_writer is not None:
            self._fail_writer._output_dir = self.output_dir
            self._fail_writer.set_run_metadata(self._run_metadata)
        try:
            all_results = self._run_rounds_sync()
        except KeyboardInterrupt:
            # _run_rounds_async already flushed and wrote final files;
            # this catches any residual interrupt from asyncio teardown.
            all_results = []
        return all_results

    def print_summary(self, results: list[CrawlResult]) -> None:
        """Print a human-readable summary of crawl results and output files."""
        if self.output_dir is None or not self.output_dir.exists():
            print("No output folder found. Did you run crawl() first?")
            return

        success_count = sum(1 for r in results if r.success)
        fail_count = sum(1 for r in results if not r.success)

        print(f"Results: {success_count} succeeded, {fail_count} failed")
        print(f"Output folder: {self.output_dir}\n")

        def _print_files(label: str, paths: list[Path]) -> None:
            if not paths:
                return
            print(f"  {label}:")
            for f in paths:
                size_mb = f.stat().st_size / (1024 * 1024)
                print(f"    {f.name} ({size_mb:.2f} MB)")
            print()

        # --- Per-round files ---
        round_nums = sorted(
            {
                rn
                for d in self.output_dir.iterdir()
                if d.is_dir() and (rn := round_num_from_dir(d.name)) is not None
            }
        )
        for rn in round_nums:
            rd = self.output_dir / round_dir_name(rn)
            round_files = sorted(rd.iterdir())
            content = [f for f in round_files if f.name.startswith(f"{_SUCCESS_SUFFIX}content_")]
            fail_content = [f for f in round_files if f.name.startswith(f"{_FAIL_SUFFIX}content_")]
            url_files = [f for f in round_files if "urls" in f.name and f.suffix == ".txt"]
            print(f"--- {round_dir_name(rn)} ---")
            _print_files("Success content", content)
            _print_files("Fail content", fail_content)
            _print_files("URL lists", url_files)

            sorted_content = [
                f for f in round_files if f.name.startswith(f"{_SORTED_SUCCESS_PREFIX}content_")
            ]
            sorted_fail_content = [
                f for f in round_files if f.name.startswith(f"{_SORTED_FAIL_PREFIX}content_")
            ]
            sorted_url_files = [
                f
                for f in round_files
                if f.name.startswith("sorted_") and "urls" in f.name and f.suffix == ".txt"
            ]
            if sorted_content or sorted_fail_content:
                print(f"--- {round_dir_name(rn)} (sorted) ---")
                _print_files("Success content", sorted_content)
                _print_files("Fail content", sorted_fail_content)
                _print_files("URL lists", sorted_url_files)

        # --- Final folder ---
        final_dir = self.output_dir / _FINAL_DIR_NAME
        final_success = (
            sorted(final_dir.glob(f"{_SUCCESS_SUFFIX}content_*")) if final_dir.exists() else []
        )
        final_fail = (
            sorted(final_dir.glob(f"{_FAIL_SUFFIX}content_*")) if final_dir.exists() else []
        )
        if final_success or final_fail:
            print("--- Final (unsorted, merged across rounds) ---")
            _print_files("Success content", final_success)
            _print_files("Fail content", final_fail)

        # --- Sorted files in final/ (primary output) ---
        sorted_success = (
            sorted(final_dir.glob(f"{_SORTED_SUCCESS_PREFIX}content_*"))
            if final_dir.exists()
            else []
        )
        sorted_fail = (
            sorted(final_dir.glob(f"{_SORTED_FAIL_PREFIX}content_*")) if final_dir.exists() else []
        )
        all_urls = sorted(final_dir.glob("*urls*.txt")) if final_dir.exists() else []
        if sorted_success or sorted_fail:
            print("--- Sorted by URL path (primary output) ---")
            _print_files("Success content", sorted_success)
            _print_files("Fail content", sorted_fail)
            _print_files("URL lists", all_urls)

        if fail_count > 0:
            print(
                f"See final/sorted_fail_urls.txt for the "
                f"{fail_count} URL(s) that could not be crawled."
            )

    def _round_dir(self, round_num: int) -> Path:
        """Return the round subdirectory for *round_num*, creating it if needed."""
        assert self.output_dir is not None
        d = self.output_dir / round_dir_name(round_num)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _run_rounds_in_proactor_loop(self) -> list[CrawlResult]:
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._run_rounds_async())
        finally:
            loop.close()

    def _run_rounds_in_new_loop(self) -> list[CrawlResult]:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._run_rounds_async())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    def _run_rounds_sync(self) -> list[CrawlResult]:
        if sys.platform == "win32":
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(self._run_rounds_in_proactor_loop).result()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._run_rounds_async())

        try:
            nest_asyncio.apply(loop)
        except ValueError:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(self._run_rounds_in_new_loop).result()

        return loop.run_until_complete(self._run_rounds_async())

    # ------------------------------------------------------------------
    # Round orchestration
    # ------------------------------------------------------------------

    async def _run_rounds_async(self) -> list[CrawlResult]:
        """Run the initial crawl + retry rounds, producing per-round and final files."""
        all_success: list[CrawlResult] = []
        all_fail: list[CrawlResult] = []
        succeeded_urls: set[str] = set()
        all_generated: set[str] = set()
        url_depths: dict[str, int] = {}
        total_rounds = 1 + self.config.max_retries

        browser_kwargs: dict = {
            "headless": True,
            "enable_stealth": self.config.stealth,
        }
        if self.config.stealth:
            browser_kwargs["user_agent_mode"] = _USER_AGENT_MODE
            browser_kwargs["user_agent_generator_config"] = {
                "platforms": list(_USER_AGENT_PLATFORMS),
                "browsers": list(_USER_AGENT_BROWSERS),
            }
        if self.config.headers:
            browser_kwargs["headers"] = dict(self.config.headers)
        async_web_crawler_cls, browser_config_cls, crawler_run_config_cls = _load_crawl4ai_classes()
        browser_cfg = browser_config_cls(**browser_kwargs)
        run_cfg = self._build_run_config(crawler_run_config_cls)
        # Direct document (PDF/DOCX) downloads use a real browser User-Agent and a
        # same-origin Referer, and trust the OS certificate store (via truststore) so
        # a corporate TLS-intercepting proxy verifies just as the browser round does;
        # CrawlerConfig.headers override these defaults.
        seed_referer = referer_for_url(self.config.urls[0]) if self.config.urls else None
        pdf_headers = merge_document_headers(self.config.headers, referer=seed_referer)

        # Round 1 uses the standard stealth browser; retry rounds always escalate to
        # the undetected browser. The rounds run in separate browser instances, so
        # WAF challenge cookies from round 1 do not carry into the retries — an
        # intentional trade for the stronger anti-bot retry posture.
        interrupted = False
        try:
            async with httpx.AsyncClient(
                headers=pdf_headers,
                timeout=_PDF_DOWNLOAD_TIMEOUT,
                follow_redirects=True,
                verify=document_ssl_context(),
            ) as pdf_client:
                self._pdf_client = pdf_client
                # --- Round 1: full crawl with link discovery (standard browser) ---
                async with async_web_crawler_cls(config=browser_cfg) as crawler:
                    round_dir = self._round_dir(1)
                    if self._writer is not None:
                        self._writer._output_dir = round_dir
                        self._writer.reset(_SUCCESS_SUFFIX)
                    if self._fail_writer is not None:
                        self._fail_writer._output_dir = round_dir
                        self._fail_writer.reset(_FAIL_SUFFIX)
                    self._success_sidecar = round_dir / _SUCCESS_SIDECAR_SUFFIX
                    self._fail_sidecar = round_dir / _FAIL_SIDECAR_SUFFIX
                    if self._progress_history is not None:
                        self._progress_history.set_round(1)
                    self._report_status(
                        f"--- Round 1/{total_rounds}: Crawling {len(self.config.urls)} seed URL(s) ---"
                    )
                    _logger.info(
                        "Crawl round 1/%d: %d seed URL(s)", total_rounds, len(self.config.urls)
                    )
                    round_results = await self._crawl_urls_async(
                        urls=self.config.urls,
                        crawler=crawler,
                        run_cfg=run_cfg,
                        discover_links=self.config.max_depth > 1,
                        round_dir=round_dir,
                        prior_success=0,
                        prior_fail=0,
                        round_label="Initial crawl" if total_rounds > 1 else "",
                        all_generated=all_generated,
                        url_depths=url_depths,
                        round_num=1,
                    )
                    success, fail = self._split_results(round_results)
                    await self._flush_writer_buffers_async()
                    all_success.extend(success)
                    succeeded_urls.update(r.url for r in success)
                    all_fail.extend(fail)
                    await asyncio.to_thread(self._save_url_lists, all_success, fail, round_dir)
                    await asyncio.to_thread(self._write_round_success_files, 1, round_dir)
                    await asyncio.to_thread(self._write_sorted_round_files, 1, round_dir)

                    failed_urls = [r.url for r in all_fail]

                # --- Retry rounds: escalate to the undetected browser ---
                retry_kwargs: dict = {"config": browser_cfg}
                if total_rounds > 1 and failed_urls:
                    strategy = self._build_undetected_strategy(browser_cfg)
                    if strategy is not None:
                        retry_kwargs["crawler_strategy"] = strategy
                async with async_web_crawler_cls(**retry_kwargs) as crawler:
                    for round_num in range(2, total_rounds + 1):
                        self._raise_if_cancelled()
                        if not failed_urls:
                            self._report_status(
                                "\nAll pages succeeded — skipping remaining retries."
                            )
                            break

                        round_dir = self._round_dir(round_num)
                        if self._writer is not None:
                            self._writer._output_dir = round_dir
                            self._writer.reset(_SUCCESS_SUFFIX)
                        if self._fail_writer is not None:
                            self._fail_writer._output_dir = round_dir
                            self._fail_writer.reset(_FAIL_SUFFIX)
                        self._success_sidecar = round_dir / _SUCCESS_SIDECAR_SUFFIX
                        self._fail_sidecar = round_dir / _FAIL_SIDECAR_SUFFIX
                        if self._progress_history is not None:
                            self._progress_history.set_round(round_num)

                        cooldown = _ROUND_COOLDOWN * random.uniform(
                            _ROUND_COOLDOWN_JITTER_MIN, _ROUND_COOLDOWN_JITTER_MAX
                        )
                        self._report_status(
                            f"\n--- Round {round_num}/{total_rounds}: Retrying "
                            f"{len(failed_urls)} failed URL(s) "
                            f"(waiting {cooldown:.0f}s cooldown) ---"
                        )
                        _logger.info(
                            "Crawl round %d/%d: retrying %d failed URL(s)",
                            round_num,
                            total_rounds,
                            len(failed_urls),
                        )
                        await self._sleep_with_cancel(cooldown)

                        round_run_cfg = self._build_fallback_run_config(
                            crawler_run_config_cls, round_num
                        )
                        round_results = await self._crawl_urls_async(
                            urls=failed_urls,
                            crawler=crawler,
                            run_cfg=round_run_cfg,
                            discover_links=self.config.max_depth > 1,
                            is_retry=True,
                            round_dir=round_dir,
                            prior_success=len(all_success),
                            prior_fail=len(all_fail),
                            skip_urls=frozenset(succeeded_urls),
                            round_label=f"Retry {round_num - 1} of {total_rounds - 1}",
                            all_generated=all_generated,
                            url_depths=url_depths,
                            round_num=round_num,
                        )
                        success, fail = self._split_results(round_results)
                        await self._flush_writer_buffers_async()
                        # Deduplicate: only add genuinely new successes
                        new_success = [r for r in success if r.url not in succeeded_urls]
                        all_success.extend(new_success)
                        succeeded_urls.update(r.url for r in new_success)
                        # Remove newly-succeeded URLs from all_fail; add new failures (skip dupes)
                        new_success_urls = {r.url for r in new_success}
                        all_fail = [r for r in all_fail if r.url not in new_success_urls]
                        existing_fail_urls = {r.url for r in all_fail}
                        all_fail.extend(r for r in fail if r.url not in existing_fail_urls)
                        failed_urls = [r.url for r in fail]
                        await asyncio.to_thread(self._save_url_lists, all_success, fail, round_dir)
                        await asyncio.to_thread(
                            self._write_round_success_files, round_num, round_dir
                        )
                        await asyncio.to_thread(
                            self._write_sorted_round_files, round_num, round_dir
                        )

        except (KeyboardInterrupt, asyncio.CancelledError):
            interrupted = True
            _logger.warning("Crawl interrupted; writing final files from saved pages")
            self._report_status("\n\nCrawl stopped! Writing final files...")
            all_success, all_fail = self._recover_saved_results(all_success, all_fail)
        except Exception as exc:  # noqa: BLE001 - finalize partial output on any crawl error
            # An unexpected error must not lose the pages already crawled: finalize
            # the partial output like a stop does, and record the error so the
            # caller reports a failure while still surfacing that output.
            interrupted = True
            self.crawl_error = str(exc)
            _logger.warning(
                "Crawl failed mid-run (%s); writing final files from completed pages", exc
            )
            self._report_status("\n\nCrawl error! Writing final files from completed pages...")
            all_success, all_fail = self._recover_saved_results(all_success, all_fail)
        finally:
            self._pdf_client = None

        # --- Flush any remaining buffered content ---
        await self._flush_writer_buffers_async()
        await self._flush_site_graph_async()

        # --- Final merged files (unsorted) ---
        await asyncio.to_thread(self._write_final_files, all_success, all_fail)

        # --- Sorted final files (grouped by URL path) ---
        await asyncio.to_thread(self._write_sorted_files, all_success, all_fail)
        self.content_files = await asyncio.to_thread(self._get_final_content_files)

        total_crawled = len(all_success) + len(all_fail)
        if self.crawl_error is not None:
            label = "Failed"
        elif interrupted:
            label = "Interrupted"
        else:
            label = "Done"
        _logger.info(
            "Crawl %s: %d succeeded, %d failed (%d total) -> %s",
            label.lower(),
            len(all_success),
            len(all_fail),
            total_crawled,
            self.output_dir,
        )
        # Clear any lingering progress widget from the final round so the
        # summary text below isn't shown beneath a stale (partial-percent)
        # bar in Jupyter / Colab.
        try:
            from IPython import get_ipython  # type: ignore[import-untyped]

            if get_ipython() is not None:
                from IPython.display import clear_output  # type: ignore[import-untyped]

                clear_output(wait=True)
        except ImportError:
            pass
        self._report_status(
            f"\n{label}! {len(all_success)} succeeded, {len(all_fail)} failed out of {total_crawled} total."
        )
        self._emit_progress(
            {
                "event": _PROGRESS_EVENT_COMPLETED,
                "output_dir": str(self.output_dir) if self.output_dir else "",
                "successful_pages": len(all_success),
                "failed_pages": len(all_fail),
                "processed_pages": total_crawled,
                "queued_discovered_urls": total_crawled,
                "limit": self.config.limit,
                "current_url": "",
                "next_url": "",
                "eta_remaining_seconds": None,
                "active_url_count": 0,
                "active_urls": [],
                "next_url_count": 0,
                "next_urls": [],
                "max_concurrent": self.config.max_concurrent,
            }
        )
        if self.output_dir is not None:
            self._report_status(f"Output folder: {self.output_dir}")

        # Return all results (success + remaining failures) for API consumers
        return all_success + all_fail

    def _emit_progress(self, event: Mapping[str, object]) -> None:
        """Send a progress event to an optional UI integration."""
        _emit_progress_impl(self._progress_callback, event)
        if self._progress_history is not None:
            self._progress_history.record(event)

    def _emit_crawl_warning(self, message: LibraryMessage) -> None:
        """Emit a structured ``crawl_warning`` event for UI consumers."""
        _emit_crawl_warning_impl(getattr(self, "_progress_callback", None), message)

    def _warn_ocr_unavailable_once(self, *, was_warned: bool) -> None:
        """Emit the OCR-unavailable warning once, on the False->True transition."""
        if not was_warned and self._ocr_warned:
            self._emit_crawl_warning(messages.ocr_unavailable())

    def _report_status(self, message: str) -> None:
        """Render a crawl-flow status line for terminal and notebook users.

        Centralizes the crawler's own stdout so core logic does not call
        ``print`` directly; a UI that consumes progress events can ignore it.
        """
        print(message)

    def _emit_page_progress(
        self,
        results: list[CrawlResult],
        *,
        generated: set[str],
        prior_success: int,
        prior_fail: int,
        current_url: str,
        next_url: str = "",
        eta_remaining_seconds: float | None = None,
        active_urls: list[str] | None = None,
        active_url_count: int | None = None,
        next_urls: list[str] | None = None,
        next_url_count: int | None = None,
    ) -> None:
        """Emit a compact page-progress event."""
        page_event = _emit_page_progress_impl(
            None,
            results,
            generated=generated,
            prior_success=prior_success,
            prior_fail=prior_fail,
            current_url=current_url,
            output_dir=self.output_dir,
            limit=self.config.limit,
            next_url=next_url,
            eta_remaining_seconds=eta_remaining_seconds,
            active_urls=active_urls,
            active_url_count=active_url_count,
            next_urls=next_urls,
            next_url_count=next_url_count,
            max_concurrent=self.config.max_concurrent,
        )
        self._emit_progress(page_event)

    async def _flush_writer_buffers_async(self) -> None:
        if self._writer is not None:
            await asyncio.to_thread(self._writer.flush)
        if self._fail_writer is not None:
            await asyncio.to_thread(self._fail_writer.flush)

    async def _flush_site_graph_async(self) -> None:
        await asyncio.to_thread(self._flush_site_graph)

    @staticmethod
    def _graph_depth(crawl_depth: int) -> int:
        return SiteGraphRecorder.graph_depth(crawl_depth)

    def _record_page_discovered(
        self,
        *,
        normalized_url: str,
        url: str,
        discovered_from: str | None,
        crawl_depth: int,
    ) -> None:
        self._site_graph.record_discovered(
            normalized_url=normalized_url,
            url=url,
            discovered_from=discovered_from,
            crawl_depth=crawl_depth,
        )

    def _upsert_page_record(
        self,
        *,
        normalized_url: str,
        url: str,
        discovered_from: str | None,
        status: str,
        page_size_kb: float | None,
        graph_depth: int,
        round_num: int | None,
    ) -> None:
        self._site_graph.upsert_record(
            normalized_url=normalized_url,
            url=url,
            discovered_from=discovered_from,
            status=status,
            page_size_kb=page_size_kb,
            graph_depth=graph_depth,
            round_num=round_num,
        )

    def _remove_page_record(self, normalized_url: str, *, statuses: set[str] | None = None) -> None:
        self._site_graph.remove_record(normalized_url, statuses=statuses)

    def _move_page_record_for_redirect(
        self,
        *,
        source_normalized_url: str,
        target_normalized_url: str,
        target_url: str,
    ) -> None:
        self._site_graph.move_record_for_redirect(
            source_normalized_url=source_normalized_url,
            target_normalized_url=target_normalized_url,
            target_url=target_url,
        )

    def _record_page_terminal(
        self,
        *,
        source_url: str,
        crawl_result: CrawlResult,
        page: ExtractedPage | None,
        round_num: int,
        crawl_depth: int,
    ) -> None:
        self._site_graph.record_terminal(
            source_url=source_url,
            crawl_result=crawl_result,
            page=page,
            round_num=round_num,
            crawl_depth=crawl_depth,
            strip_www=self.config.strip_www,
        )
        self._record_network_usage(crawl_result=crawl_result, page=page, round_num=round_num)

    def _record_network_usage(
        self,
        *,
        crawl_result: CrawlResult,
        page: ExtractedPage | None,
        round_num: int,
    ) -> None:
        """Log proxy/API usage for this URL when the round enabled a paid resource."""
        proxy_rounds, api_round = self._paid_resource_rounds()
        if round_num in proxy_rounds:
            method = "proxy"
        elif round_num == api_round:
            method = "api"
        else:
            return
        markdown = page.markdown if page is not None else crawl_result.markdown
        size_kb = (
            round(len(markdown.encode("utf-8")) / 1024, 2)
            if crawl_result.success and markdown.strip()
            else None
        )
        status = "success" if crawl_result.success else "fail"
        size_text = "unknown size" if size_kb is None else f"{size_kb:.2f} KB"
        _logger.info("Fetched via %s [%s]: %s (%s)", method, status, crawl_result.url, size_text)
        self._network_usage.record(
            method=method,
            round_num=round_num,
            url=crawl_result.url,
            status=status,
            size_kb=size_kb,
        )

    def _record_failed_page_content(
        self,
        crawl_result: CrawlResult,
        *,
        raw_response: str | None = None,
    ) -> ExtractedPage | None:
        if self._fail_writer is None:
            return None

        error = crawl_result.error or _UNKNOWN_ERROR_MSG
        markdown = f"{_ERROR_SECTION_HEADER} {error}"
        raw_body = raw_response.strip() if raw_response else ""
        if raw_body:
            markdown = f"{markdown}\n\n{_RAW_RESPONSE_HEADER}\n\n{raw_body}"

        fail_page = ExtractedPage(
            url=crawl_result.url,
            title=f"{_FAILED_TITLE_PREFIX} {error}",
            markdown=markdown,
        )
        self._fail_writer.add(fail_page)
        if self._fail_sidecar is not None:
            PageSidecar.append(fail_page, self._fail_sidecar)
        return fail_page

    def _flush_site_graph(self) -> None:
        self._site_graph.flush()

    def _cancel_requested(self) -> bool:
        return bool(self._should_cancel is not None and self._should_cancel())

    def _raise_if_cancelled(self) -> None:
        if self._cancel_requested():
            raise asyncio.CancelledError

    async def _sleep_with_cancel(self, seconds: float) -> None:
        """Sleep in short chunks so cooperative cancellation stays responsive."""
        if self._should_cancel is None:
            await asyncio.sleep(seconds)
            return
        remaining = seconds
        while remaining > 0:
            self._raise_if_cancelled()
            interval = min(_CANCEL_POLL_INTERVAL, remaining)
            await asyncio.sleep(interval)
            remaining -= interval
        self._raise_if_cancelled()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _fetch_html_url(self, *, url: str, crawler: Any, run_cfg: object) -> Any:
        return await crawler.arun(url=url, config=run_cfg)

    def _crawl_delay_seconds(self, *, is_retry: bool) -> float:
        if self.config.delay <= 0:
            return 0.0
        if is_retry:
            return self.config.delay * random.uniform(_JITTER_RETRY_MIN, _JITTER_RETRY_MAX)
        return self.config.delay * random.uniform(_JITTER_ROUND1_MIN, _JITTER_ROUND1_MAX)

    def _next_fetch_start_after_delay(self, *, is_retry: bool) -> float:
        delay_seconds = self._crawl_delay_seconds(is_retry=is_retry)
        return time.monotonic() + delay_seconds if delay_seconds > 0 else 0.0

    async def _wait_for_fetch_start_slot(
        self,
        *,
        next_start_at: float,
        progress: ProgressReporter,
    ) -> None:
        wait_seconds = max(0.0, next_start_at - time.monotonic())
        if wait_seconds <= 0:
            return
        progress.set_activity(f"Pausing to avoid blocks ({wait_seconds:.1f}s)")
        await self._sleep_with_cancel(wait_seconds)

    @staticmethod
    def _preview_progress_urls(urls: list[str]) -> list[str]:
        return urls[:_PROGRESS_URL_PREVIEW_LIMIT]

    def _next_progress_urls(self, queue: list[tuple[str, int]]) -> list[str]:
        if not queue:
            return []
        next_count = min(len(queue), self.config.max_concurrent)
        return [url for url, _ in queue[:next_count]]

    def _emit_active_fetch_progress(
        self,
        *,
        active_urls: list[str],
        next_urls: list[str],
        eta_remaining_seconds: float | None = None,
    ) -> None:
        active_preview = self._preview_progress_urls(active_urls)
        next_preview = self._preview_progress_urls(next_urls)
        self._emit_progress(
            {
                "event": _PROGRESS_EVENT_STATUS,
                "current_url": active_preview[0] if active_preview else "",
                "next_url": next_preview[0] if next_preview else "",
                "active_url_count": len(active_urls),
                "active_urls": active_preview,
                "next_url_count": len(next_urls),
                "next_urls": next_preview,
                "max_concurrent": self.config.max_concurrent,
                "limit": self.config.limit,
                "eta_remaining_seconds": eta_remaining_seconds,
                "output_dir": str(self.output_dir) if self.output_dir else "",
            }
        )

    def _next_concurrent_frontier(
        self,
        queue: list[tuple[str, int]],
        visited: set[str],
        *,
        strip_www: bool,
        prefetched_urls: set[str],
    ) -> list[str]:
        if self.config.max_concurrent <= 1 or len(queue) <= 1:
            return []

        first_url, first_depth = queue[0]
        if first_url in prefetched_urls:
            return []

        frontier: list[str] = []
        frontier_normalized_urls: set[str] = set()
        for candidate_url, candidate_depth in queue:
            if len(frontier) >= self.config.max_concurrent:
                break
            if candidate_depth != first_depth:
                break
            if candidate_url in prefetched_urls:
                break
            normalized_url = self._normalize_url(candidate_url, strip_www=strip_www)
            if normalized_url in visited:
                break
            if normalized_url in frontier_normalized_urls:
                break
            if not self._url_allowed(candidate_url):
                break
            if self._is_document_url(candidate_url):
                break
            frontier.append(candidate_url)
            frontier_normalized_urls.add(normalized_url)

        if len(frontier) <= 1:
            return []
        return frontier

    async def _prefetch_concurrent_frontier(
        self,
        *,
        urls: list[str],
        crawler: Any,
        run_cfg: object,
        progress: ProgressReporter,
        is_retry: bool,
        next_start_at: float,
        next_urls: list[str],
    ) -> tuple[dict[str, Any], float]:
        tasks: list[asyncio.Task[Any]] = []
        started_urls: list[str] = []
        try:
            for url in urls:
                await self._wait_for_fetch_start_slot(
                    next_start_at=next_start_at,
                    progress=progress,
                )
                self._raise_if_cancelled()
                tasks.append(
                    asyncio.create_task(
                        self._fetch_html_url(url=url, crawler=crawler, run_cfg=run_cfg)
                    )
                )
                started_urls.append(url)
                self._emit_active_fetch_progress(
                    active_urls=started_urls,
                    next_urls=next_urls,
                    eta_remaining_seconds=progress.eta_remaining_seconds(),
                )
                next_start_at = self._next_fetch_start_after_delay(is_retry=is_retry)
            progress.set_activity(f"Reading page batch ({len(started_urls)} concurrent)")
            raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.CancelledError:
            raw_results = await asyncio.gather(*tasks, return_exceptions=True) if tasks else []
            if not tasks or not self._cancel_requested():
                raise

        return dict(zip(started_urls, raw_results, strict=True)), next_start_at

    async def _crawl_urls_async(
        self,
        urls: list[str],
        crawler: Any,
        run_cfg: object,
        *,
        discover_links: bool = True,
        is_retry: bool = False,
        round_dir: Path | None = None,
        prior_success: int = 0,
        prior_fail: int = 0,
        skip_urls: frozenset[str] = frozenset(),
        round_label: str = "",
        all_generated: set[str] | None = None,
        url_depths: dict[str, int] | None = None,
        round_num: int = 1,
    ) -> list[CrawlResult]:
        """Crawl a list of URLs and return per-page results.

        When *discover_links* is True, follow links up to ``max_depth``.
        When False, only crawl the given URLs with no link discovery.

        *skip_urls* contains URLs already successfully crawled in prior
        rounds — they are pre-loaded into the visited set so they will
        not be crawled again (including as redirect targets).

        *all_generated* and *url_depths* are shared mutable collections
        that persist across rounds.  ``all_generated`` tracks every URL
        ever queued (for dedup and limit enforcement); ``url_depths``
        maps each URL to its crawl depth so retried pages and their
        discovered links use the correct depth.
        """
        results: list[CrawlResult] = []
        _sw = self.config.strip_www
        visited: set[str] = set(self._normalize_url(u, strip_www=_sw) for u in skip_urls)
        generated: set[str] = all_generated if all_generated is not None else set()
        depths: dict[str, int] = url_depths if url_depths is not None else {}
        queue: list[tuple[str, int]] = []
        for seed_url in urls:
            norm_seed = self._normalize_url(seed_url, strip_www=_sw)
            if norm_seed not in generated:
                if len(generated) >= self.config.limit:
                    break
                if not self._url_allowed(seed_url):
                    continue
                self._record_page_discovered(
                    normalized_url=norm_seed,
                    url=seed_url,
                    discovered_from=None,
                    crawl_depth=depths.get(norm_seed, 1),
                )
            generated.add(norm_seed)
            queue.append((seed_url, depths.get(norm_seed, 1)))
        await self._flush_site_graph_async()
        progress = ProgressReporter(
            max(len(queue), 1),
            prior_success=prior_success,
            prior_fail=prior_fail,
            round_label=round_label,
            max_log_entries=self._activity_log_size,
            log_dir=self._logs_dir,
        )
        try:
            discovery_limit_reached = len(generated) >= self.config.limit
            prefetched_results: dict[str, Any] = {}
            next_fetch_start_at = 0.0

            consecutive_blocks = 0
            # Redirect storm tracking: count consecutive redirects to the
            # same already-visited target.  Once the threshold is reached,
            # subsequent pages are treated as failures instead of silent
            # skips so they enter the retry pipeline.
            consecutive_redirect_target: str | None = None
            consecutive_redirect_count: int = 0
            skipped_redirect_urls: list[str] = []

            def _flush_skipped_redirects(error: str) -> None:
                crawl_depth = depth if skipped_redirect_urls else 1
                self._flush_skipped_redirects(
                    skipped_redirect_urls=skipped_redirect_urls,
                    error=error,
                    results=results,
                    generated=generated,
                    progress=progress,
                    prior_success=prior_success,
                    prior_fail=prior_fail,
                    round_num=round_num,
                    crawl_depth=crawl_depth,
                    strip_www=_sw,
                )

            while queue:
                if queue[0][0] not in prefetched_results:
                    self._raise_if_cancelled()
                if not is_retry:
                    frontier = self._next_concurrent_frontier(
                        queue,
                        visited,
                        strip_www=_sw,
                        prefetched_urls=set(prefetched_results),
                    )
                    if frontier:
                        next_progress_urls = self._next_progress_urls(queue[len(frontier) :])
                        (
                            new_prefetched,
                            next_fetch_start_at,
                        ) = await self._prefetch_concurrent_frontier(
                            urls=frontier,
                            crawler=crawler,
                            run_cfg=run_cfg,
                            progress=progress,
                            is_retry=is_retry,
                            next_start_at=next_fetch_start_at,
                            next_urls=next_progress_urls,
                        )
                        prefetched_results.update(new_prefetched)

                url, depth = queue.pop(0)
                used_prefetched_result = url in prefetched_results

                norm_url = self._normalize_url(url, strip_www=_sw)
                if norm_url in visited:
                    prefetched_results.pop(url, None)
                    generated.discard(norm_url)
                    self._remove_page_record(norm_url, statuses={_PAGE_STATUS_DISCOVERED})
                    progress.total = max(len(generated), 1)
                    self._emit_progress(
                        {
                            "event": _PROGRESS_EVENT_DISCOVERED,
                            "queued_discovered_urls": len(generated),
                            "current_url": url,
                            "limit": self.config.limit,
                        }
                    )
                    continue
                visited.add(norm_url)

                if not self._url_allowed(url):
                    prefetched_results.pop(url, None)
                    continue

                # Fast path: download binary documents (PDF/DOCX) directly,
                # bypassing the browser.
                if self._is_document_url(url):
                    if not is_retry and self.config.max_concurrent > 1:
                        await self._wait_for_fetch_start_slot(
                            next_start_at=next_fetch_start_at,
                            progress=progress,
                        )
                        next_fetch_start_at = self._next_fetch_start_after_delay(is_retry=is_retry)
                    handle_document = (
                        self._handle_direct_pdf_url
                        if self._is_pdf_url(url)
                        else self._handle_direct_docx_url
                    )
                    await handle_document(
                        url=url,
                        results=results,
                        generated=generated,
                        prior_success=prior_success,
                        prior_fail=prior_fail,
                        queue=queue,
                        progress=progress,
                        round_num=round_num,
                        crawl_depth=depth,
                        round_dir=round_dir,
                        is_retry=is_retry,
                    )
                    continue
                try:
                    progress.set_activity(f"Reading page {_shorten_url(url)}")
                    if used_prefetched_result:
                        result = prefetched_results.pop(url)
                        if isinstance(result, BaseException):
                            raise result
                    else:
                        if not is_retry and self.config.max_concurrent > 1:
                            await self._wait_for_fetch_start_slot(
                                next_start_at=next_fetch_start_at,
                                progress=progress,
                            )
                            next_fetch_start_at = self._next_fetch_start_after_delay(
                                is_retry=is_retry
                            )
                        result = await self._fetch_html_url(
                            url=url, crawler=crawler, run_cfg=run_cfg
                        )

                    # Use the final URL after any redirects
                    final_url = getattr(result, "redirected_url", None) or url
                    redirected = final_url != url

                    norm_final = self._normalize_url(final_url, strip_www=_sw)
                    if redirected and norm_final in visited:
                        # Track consecutive same-target redirects
                        if norm_final == consecutive_redirect_target:
                            consecutive_redirect_count += 1
                        else:
                            # Target changed — flush any prior skipped URLs
                            # as unresolved before switching targets.
                            _flush_skipped_redirects(_UNRESOLVED_REDIRECT_ERROR)
                            consecutive_redirect_target = norm_final
                            consecutive_redirect_count = 1

                        if consecutive_redirect_count < _REDIRECT_STORM_THRESHOLD:
                            skipped_redirect_urls.append(url)
                            progress.set_activity(f"Skipped {_shorten_url(url)} (already visited)")
                            continue

                        # Storm detected — retroactively fail earlier skipped
                        # pages, then treat the current page as failure too
                        # so the retry pipeline can re-attempt all of them.
                        _flush_skipped_redirects(_REDIRECT_STORM_ERROR)
                        await self._handle_redirect_storm_page(
                            url=url,
                            results=results,
                            generated=generated,
                            prior_success=prior_success,
                            prior_fail=prior_fail,
                            queue=queue,
                            progress=progress,
                            round_num=round_num,
                            crawl_depth=depth,
                        )
                        continue

                    # Non-redirect-skip result — reset storm counter
                    consecutive_redirect_target = None
                    consecutive_redirect_count = 0

                    visited.add(norm_final)
                    generated.add(norm_final)
                    depths[norm_final] = depth

                    if redirected and not self._url_allowed(final_url):
                        # Undo the generated/visited adds above — the redirect target
                        # is outside the filter and neither the original URL nor the
                        # redirect destination should count as discovered.
                        generated.discard(self._normalize_url(url, strip_www=_sw))
                        generated.discard(norm_final)
                        visited.discard(norm_final)
                        self._remove_page_record(norm_url)
                        self._remove_page_record(norm_final)
                        self._emit_progress(
                            {
                                "event": _PROGRESS_EVENT_DISCOVERED,
                                "queued_discovered_urls": len(generated),
                                "current_url": url,
                                "limit": self.config.limit,
                            }
                        )
                        progress.set_activity(
                            f"Skipped {_shorten_url(url)} (redirect outside filter)"
                        )
                        continue

                    if redirected and norm_final != norm_url:
                        # Keep discovered URL count aligned with processable URLs by
                        # replacing the redirected source URL with its final target.
                        generated.discard(norm_url)
                        depths.pop(norm_url, None)
                        progress.total = max(len(generated), 1)

                    error_msg: str | None = None
                    if not result.success:
                        raw_err = (
                            getattr(result, "error_message", None)
                            or getattr(result, "error", None)
                            or ""
                        )
                        status = getattr(result, "status_code", None)
                        error_msg = str(raw_err) if raw_err else _UNKNOWN_ERROR_MSG
                        if status is not None:
                            error_msg += f" (HTTP {status})"

                    crawl_result = CrawlResult(
                        url=final_url,
                        html=result.html or "",
                        markdown=result.markdown or "",
                        success=result.success,
                        error=error_msg,
                        redirected_url=final_url if redirected else None,
                    )
                except Exception as exc:
                    crawl_result = CrawlResult(
                        url=url,
                        html="",
                        markdown="",
                        success=False,
                        error=f"{type(exc).__name__}: {exc}",
                    )

                # Detect WAF blocks (Incapsula etc. return HTTP 200 with block HTML).
                # Only flag as blocked when the extracted markdown is short —
                # pages with substantial content are not mere challenge pages.
                # We measure content length *after* stripping boilerplate tags
                # (nav, script, form, style) so that navigation chrome doesn't
                # inflate the count and mask a failed JS render.
                raw_markdown = crawl_result.markdown
                waf_blocked = False
                if (
                    crawl_result.success
                    and self._is_blocked(crawl_result.html)
                    and self._content_length_without_chrome(crawl_result.html)
                    < _BLOCK_MAX_CONTENT_LENGTH
                ):
                    crawl_result.success = False
                    crawl_result.error = "Blocked by WAF"
                    crawl_result.error_code = messages.CODE_BLOCKED
                    crawl_result.markdown = ""
                    waf_blocked = True

                results.append(crawl_result)
                terminal_page: ExtractedPage | None = None

                # Extract and buffer content incrementally
                if crawl_result.success and self._extractor and self._writer:
                    progress.set_activity("Saving page content")
                    page = self._extractor._extract_page(crawl_result)
                    # Post-extraction quality gate: if a block signature is
                    # present and the *extracted* content is still thin,
                    # demote to failure so the URL is retried.
                    if (
                        self._is_blocked(crawl_result.html)
                        and len(page.markdown.strip()) < _BLOCK_MAX_CONTENT_LENGTH
                    ):
                        crawl_result.success = False
                        crawl_result.error = "Blocked — page returned only boilerplate"
                        crawl_result.error_code = messages.CODE_BLOCKED
                        crawl_result.markdown = raw_markdown
                        waf_blocked = True
                    elif page.markdown.strip():
                        self._writer.add(page)
                        terminal_page = page
                        if self._success_sidecar is not None:
                            PageSidecar.append(page, self._success_sidecar)
                    else:
                        progress.set_activity(
                            f"No content found on {_shorten_url(crawl_result.url)}"
                        )
                        crawl_result.success = False
                        crawl_result.error = _EMPTY_EXTRACTION_ERROR
                        crawl_result.error_code = messages.CODE_EMPTY_CONTENT
                        crawl_result.markdown = raw_markdown

                # PDF fallback: when a page returns very little content and is
                # not a WAF block, check whether the URL actually serves a PDF.
                # This catches dynamic URLs (e.g. /download?id=123) that return
                # PDF content without a .pdf extension.
                if (
                    crawl_result.success
                    and not waf_blocked
                    and not crawl_result.is_pdf
                    and len(crawl_result.markdown.strip()) < _PDF_FALLBACK_THRESHOLD
                    and self._content_length_without_chrome(crawl_result.html)
                    < _PDF_FALLBACK_THRESHOLD
                ):
                    crawl_result, terminal_page = await self._handle_pdf_fallback(
                        url=url,
                        crawl_result=crawl_result,
                        results=results,
                        terminal_page=terminal_page,
                        progress=progress,
                    )

                # DOCX fallback: same idea for dynamic URLs that serve a Word
                # document without a .docx extension.
                if (
                    crawl_result.success
                    and not waf_blocked
                    and not crawl_result.is_pdf
                    and not crawl_result.is_docx
                    and len(crawl_result.markdown.strip()) < _PDF_FALLBACK_THRESHOLD
                    and self._content_length_without_chrome(crawl_result.html)
                    < _PDF_FALLBACK_THRESHOLD
                ):
                    crawl_result, terminal_page = await self._handle_docx_fallback(
                        url=url,
                        crawl_result=crawl_result,
                        results=results,
                        terminal_page=terminal_page,
                        progress=progress,
                    )

                progress.update(crawl_result.url, success=crawl_result.success)
                next_progress_urls = self._next_progress_urls(queue)
                self._emit_page_progress(
                    results,
                    generated=generated,
                    prior_success=prior_success,
                    prior_fail=prior_fail,
                    current_url=crawl_result.url,
                    next_url=next_progress_urls[0] if next_progress_urls else "",
                    eta_remaining_seconds=progress.eta_remaining_seconds(),
                    active_urls=[],
                    active_url_count=0,
                    next_urls=self._preview_progress_urls(next_progress_urls),
                    next_url_count=len(next_progress_urls),
                )

                # WAF back-off: pause after a block so the WAF can cool down.
                # Applies even when delay=0 (floor ensures a minimum pause).
                if waf_blocked:
                    consecutive_blocks += 1
                    if consecutive_blocks >= _WAF_CONSECUTIVE_THRESHOLD:
                        backoff = _WAF_BACKOFF_CAP
                    else:
                        backoff = max(
                            _WAF_BACKOFF_FLOOR,
                            self.config.delay * random.uniform(_WAF_BACKOFF_MIN, _WAF_BACKOFF_MAX),
                        )
                    progress.set_activity(f"Website is blocking us \u2014 waiting {backoff:.1f}s")
                    self._emit_crawl_warning(messages.blocked_backoff(backoff))
                    await self._sleep_with_cancel(backoff)
                else:
                    consecutive_blocks = 0

                # A normal result (success or WAF block) breaks any redirect
                # storm streak — flush skipped URLs and reset the counter.
                _flush_skipped_redirects(_UNRESOLVED_REDIRECT_ERROR)
                consecutive_redirect_target = None
                consecutive_redirect_count = 0

                # Buffer failed-page content for the fail content file
                if not crawl_result.success:
                    raw_body = raw_markdown.strip() or crawl_result.html.strip() or "(no response)"
                    self._record_failed_page_content(crawl_result, raw_response=raw_body)

                self._record_page_terminal(
                    source_url=url,
                    crawl_result=crawl_result,
                    page=terminal_page,
                    round_num=round_num,
                    crawl_depth=depth,
                )

                # Flush content and URL lists periodically
                if len(results) % self.config.flush_interval == 0:
                    progress.set_activity(f"Writing files ({len(results)} pages)")
                    await self._flush_writer_buffers_async()
                    await self._flush_site_graph_async()
                    if round_dir is not None:
                        success, fail = self._split_results(results)
                        await asyncio.to_thread(self._save_url_lists, success, fail, round_dir)

                # Throttle serial request starts — jitter mimics human browsing.
                # Round 1 applies a light delay; retries apply a heavier one.
                # Both require delay > 0 (default 0 keeps current fast behavior).
                if self.config.delay > 0 and not used_prefetched_result:
                    jitter = self._crawl_delay_seconds(is_retry=is_retry)
                    if is_retry:
                        progress.set_activity(f"Waiting before retry ({jitter:.1f}s)")
                    else:
                        progress.set_activity(f"Pausing to avoid blocks ({jitter:.1f}s)")
                    await self._sleep_with_cancel(jitter)

                # Discover links for deeper crawling
                if (
                    discover_links
                    and depth < self.config.max_depth
                    and crawl_result.success
                    and not discovery_limit_reached
                ):
                    discovery_limit_reached = self._discover_links_from_result(
                        url=url,
                        depth=depth,
                        crawl_result=crawl_result,
                        generated=generated,
                        depths=depths,
                        queue=queue,
                        progress=progress,
                        round_num=round_num,
                    )

                # Free heavy payload — content is persisted in sidecar / writer
                crawl_result.html = ""
                crawl_result.markdown = ""

            # Flush any remaining skipped-redirect URLs as failures so they
            # appear in the fail list for manual review.
            _flush_skipped_redirects(_UNRESOLVED_REDIRECT_ERROR)

            # Flush the last open activity so it appears in the disk log.
            progress.close()

            # Snap the bar to 100%: silently-skipped URLs (e.g. redirects to
            # already-visited targets, redirects outside the include filter)
            # were counted into ``progress.total`` via ``generated`` but never
            # call ``progress.update``, so the bar would otherwise end below
            # 100%.  Sync ``total`` to the actual number processed.
            progress.total = max(progress.count, 1)
            if progress._use_notebook:
                progress._refresh_display(force=True)

            return results
        finally:
            progress.close()

    async def _handle_document_fallback(
        self,
        *,
        url: str,
        detect: Callable[..., Awaitable[bool]],
        download: Callable[[str], Awaitable[CrawlResult]],
        redownload_activity: str,
        saving_activity: str,
        crawl_result: CrawlResult,
        results: list[CrawlResult],
        terminal_page: ExtractedPage | None,
        progress: ProgressReporter,
    ) -> tuple[CrawlResult, ExtractedPage | None]:
        is_document = await detect(
            url,
            dict(self.config.headers) if self.config.headers else None,
            client=self._pdf_client,
        )
        if not is_document:
            return crawl_result, terminal_page

        progress.set_activity(redownload_activity)
        document_result = await download(url)
        results[-1] = document_result
        crawl_result = document_result
        if document_result.success and self._extractor and self._writer:
            progress.set_activity(saving_activity)
            page = self._extractor._extract_page(document_result)
            if page.markdown.strip():
                self._writer.add(page)
                terminal_page = page
                if self._success_sidecar is not None:
                    PageSidecar.append(page, self._success_sidecar)
            else:
                progress.set_activity(f"No content found on {_shorten_url(document_result.url)}")
                document_result.success = False
                document_result.error = _EMPTY_EXTRACTION_ERROR
                document_result.error_code = messages.CODE_EMPTY_CONTENT
        return crawl_result, terminal_page

    async def _handle_pdf_fallback(
        self,
        *,
        url: str,
        crawl_result: CrawlResult,
        results: list[CrawlResult],
        terminal_page: ExtractedPage | None,
        progress: ProgressReporter,
    ) -> tuple[CrawlResult, ExtractedPage | None]:
        ocr_tag = " (OCR)" if self.page_config.ocr_languages else ""
        return await self._handle_document_fallback(
            url=url,
            detect=self._is_pdf_response,
            download=self._download_pdf,
            redownload_activity=f"Re-downloading as PDF {_shorten_url(url)}",
            saving_activity=f"Saving PDF content{ocr_tag}",
            crawl_result=crawl_result,
            results=results,
            terminal_page=terminal_page,
            progress=progress,
        )

    async def _handle_docx_fallback(
        self,
        *,
        url: str,
        crawl_result: CrawlResult,
        results: list[CrawlResult],
        terminal_page: ExtractedPage | None,
        progress: ProgressReporter,
    ) -> tuple[CrawlResult, ExtractedPage | None]:
        return await self._handle_document_fallback(
            url=url,
            detect=self._is_docx_response,
            download=self._download_docx,
            redownload_activity=f"Re-downloading as DOCX {_shorten_url(url)}",
            saving_activity="Saving DOCX content",
            crawl_result=crawl_result,
            results=results,
            terminal_page=terminal_page,
            progress=progress,
        )

    async def _handle_direct_document_url(
        self,
        *,
        url: str,
        download: Callable[[str], Awaitable[CrawlResult]],
        downloading_activity: str,
        saving_activity: str,
        results: list[CrawlResult],
        generated: set[str],
        prior_success: int,
        prior_fail: int,
        queue: list[tuple[str, int]],
        progress: ProgressReporter,
        round_num: int,
        crawl_depth: int,
        round_dir: Path | None,
        is_retry: bool,
    ) -> None:
        progress.set_activity(downloading_activity)
        crawl_result = await download(url)
        results.append(crawl_result)

        terminal_page: ExtractedPage | None = None
        if crawl_result.success and self._extractor and self._writer:
            progress.set_activity(saving_activity)
            page = self._extractor._extract_page(crawl_result)
            if page.markdown.strip():
                self._writer.add(page)
                terminal_page = page
                if self._success_sidecar is not None:
                    PageSidecar.append(page, self._success_sidecar)
            else:
                progress.set_activity(f"No content found on {_shorten_url(crawl_result.url)}")
                crawl_result.success = False
                crawl_result.error = _EMPTY_EXTRACTION_ERROR
                crawl_result.error_code = messages.CODE_EMPTY_CONTENT

        if not crawl_result.success:
            raw_body = crawl_result.markdown.strip() or crawl_result.html.strip() or None
            self._record_failed_page_content(crawl_result, raw_response=raw_body)

        progress.update(crawl_result.url, success=crawl_result.success)
        next_progress_urls = self._next_progress_urls(queue)
        self._emit_page_progress(
            results,
            generated=generated,
            prior_success=prior_success,
            prior_fail=prior_fail,
            current_url=crawl_result.url,
            next_url=next_progress_urls[0] if next_progress_urls else "",
            eta_remaining_seconds=progress.eta_remaining_seconds(),
            active_urls=[],
            active_url_count=0,
            next_urls=self._preview_progress_urls(next_progress_urls),
            next_url_count=len(next_progress_urls),
        )

        self._record_page_terminal(
            source_url=url,
            crawl_result=crawl_result,
            page=terminal_page,
            round_num=round_num,
            crawl_depth=crawl_depth,
        )

        if len(results) % self.config.flush_interval == 0:
            await self._flush_writer_buffers_async()
            await self._flush_site_graph_async()
            if round_dir is not None:
                success, fail = self._split_results(results)
                await asyncio.to_thread(self._save_url_lists, success, fail, round_dir)

        crawl_result.html = ""
        crawl_result.markdown = ""

        if self.config.delay > 0:
            jitter = self._crawl_delay_seconds(is_retry=is_retry)
            if is_retry:
                progress.set_activity(f"Waiting before retry ({jitter:.1f}s)")
            else:
                progress.set_activity(f"Pausing to avoid blocks ({jitter:.1f}s)")
            await self._sleep_with_cancel(jitter)

    async def _handle_direct_pdf_url(
        self,
        *,
        url: str,
        results: list[CrawlResult],
        generated: set[str],
        prior_success: int,
        prior_fail: int,
        queue: list[tuple[str, int]],
        progress: ProgressReporter,
        round_num: int,
        crawl_depth: int,
        round_dir: Path | None,
        is_retry: bool,
    ) -> None:
        ocr_tag = " (OCR)" if self.page_config.ocr_languages else ""
        await self._handle_direct_document_url(
            url=url,
            download=self._download_pdf,
            downloading_activity=f"Downloading PDF {_shorten_url(url)}",
            saving_activity=f"Saving PDF content{ocr_tag}",
            results=results,
            generated=generated,
            prior_success=prior_success,
            prior_fail=prior_fail,
            queue=queue,
            progress=progress,
            round_num=round_num,
            crawl_depth=crawl_depth,
            round_dir=round_dir,
            is_retry=is_retry,
        )

    async def _handle_direct_docx_url(
        self,
        *,
        url: str,
        results: list[CrawlResult],
        generated: set[str],
        prior_success: int,
        prior_fail: int,
        queue: list[tuple[str, int]],
        progress: ProgressReporter,
        round_num: int,
        crawl_depth: int,
        round_dir: Path | None,
        is_retry: bool,
    ) -> None:
        await self._handle_direct_document_url(
            url=url,
            download=self._download_docx,
            downloading_activity=f"Downloading DOCX {_shorten_url(url)}",
            saving_activity="Saving DOCX content",
            results=results,
            generated=generated,
            prior_success=prior_success,
            prior_fail=prior_fail,
            queue=queue,
            progress=progress,
            round_num=round_num,
            crawl_depth=crawl_depth,
            round_dir=round_dir,
            is_retry=is_retry,
        )

    def _flush_skipped_redirects(
        self,
        *,
        skipped_redirect_urls: list[str],
        error: str,
        results: list[CrawlResult],
        generated: set[str],
        progress: ProgressReporter,
        prior_success: int,
        prior_fail: int,
        round_num: int,
        crawl_depth: int,
        strip_www: bool,
    ) -> None:
        if len(skipped_redirect_urls) < 2:
            for skipped_url in skipped_redirect_urls:
                norm_skipped = self._normalize_url(skipped_url, strip_www=strip_www)
                generated.discard(norm_skipped)
                self._remove_page_record(
                    norm_skipped,
                    statuses={_PAGE_STATUS_DISCOVERED, _PAGE_STATUS_SKIPPED},
                )
            if skipped_redirect_urls:
                progress.total = max(len(generated), 1)
                self._emit_progress(
                    {
                        "event": _PROGRESS_EVENT_DISCOVERED,
                        "queued_discovered_urls": len(generated),
                        "current_url": skipped_redirect_urls[0],
                        "limit": self.config.limit,
                    }
                )
            skipped_redirect_urls.clear()
            return
        for skipped_url in skipped_redirect_urls:
            skipped_result = CrawlResult(
                url=skipped_url,
                html="",
                markdown="",
                success=False,
                error=error,
            )
            results.append(skipped_result)
            self._record_failed_page_content(skipped_result)
            self._record_page_terminal(
                source_url=skipped_url,
                crawl_result=skipped_result,
                page=None,
                round_num=round_num,
                crawl_depth=crawl_depth,
            )
            progress.update(skipped_url, success=False)
            self._emit_page_progress(
                results,
                generated=generated,
                prior_success=prior_success,
                prior_fail=prior_fail,
                current_url=skipped_url,
                eta_remaining_seconds=progress.eta_remaining_seconds(),
                active_urls=[],
                active_url_count=0,
                next_urls=[],
                next_url_count=0,
            )
        skipped_redirect_urls.clear()

    async def _handle_redirect_storm_page(
        self,
        *,
        url: str,
        results: list[CrawlResult],
        generated: set[str],
        prior_success: int,
        prior_fail: int,
        queue: list[tuple[str, int]],
        progress: ProgressReporter,
        round_num: int,
        crawl_depth: int,
    ) -> None:
        progress.set_activity(f"Possible block detected \u2014 skipping {_shorten_url(url)}")
        crawl_result = CrawlResult(
            url=url,
            html="",
            markdown="",
            success=False,
            error=_REDIRECT_STORM_ERROR,
            error_code=messages.CODE_REDIRECT_LOOP,
        )
        results.append(crawl_result)
        self._record_failed_page_content(crawl_result)
        self._record_page_terminal(
            source_url=url,
            crawl_result=crawl_result,
            page=None,
            round_num=round_num,
            crawl_depth=crawl_depth,
        )
        progress.update(url, success=False)
        next_progress_urls = self._next_progress_urls(queue)
        self._emit_page_progress(
            results,
            generated=generated,
            prior_success=prior_success,
            prior_fail=prior_fail,
            current_url=url,
            next_url=next_progress_urls[0] if next_progress_urls else "",
            eta_remaining_seconds=progress.eta_remaining_seconds(),
            active_urls=[],
            active_url_count=0,
            next_urls=self._preview_progress_urls(next_progress_urls),
            next_url_count=len(next_progress_urls),
        )

        backoff = max(
            _WAF_BACKOFF_FLOOR,
            self.config.delay * random.uniform(_WAF_BACKOFF_MIN, _WAF_BACKOFF_MAX),
        )
        progress.set_activity(f"Website is blocking us \u2014 waiting {backoff:.1f}s")
        self._emit_crawl_warning(messages.blocked_backoff(backoff))
        await self._sleep_with_cancel(backoff)

    def _discover_links_from_result(
        self,
        *,
        url: str,
        depth: int,
        crawl_result: CrawlResult,
        generated: set[str],
        depths: dict[str, int],
        queue: list[tuple[str, int]],
        progress: ProgressReporter,
        round_num: int,
    ) -> bool:
        progress.set_activity(f"Finding more pages on {_shorten_url(url)}")
        next_depth = depth + 1
        new_links = self._extract_links(
            crawl_result,
            crawl_result.url,
            strip_www=self.config.strip_www,
        )
        added = 0
        for link in new_links:
            norm_link = self._normalize_url(link, strip_www=self.config.strip_www)
            if norm_link in generated:
                continue
            if not self._url_allowed(link):
                if self._url_in_allowed_domain(link) and norm_link not in self._site_graph_records:
                    self._upsert_page_record(
                        normalized_url=norm_link,
                        url=link,
                        discovered_from=crawl_result.url,
                        status=_PAGE_STATUS_SKIPPED,
                        page_size_kb=None,
                        graph_depth=self._graph_depth(next_depth),
                        round_num=round_num,
                    )
                continue
            if norm_link in self._site_graph_records:
                continue
            generated.add(norm_link)
            depths[norm_link] = next_depth
            self._record_page_discovered(
                normalized_url=norm_link,
                url=link,
                discovered_from=crawl_result.url,
                crawl_depth=next_depth,
            )
            queue.append((link, next_depth))
            added += 1
        progress.update_activity_label(f"Found {added} new pages on {_shorten_url(url)}")
        self._emit_progress(
            {
                "event": _PROGRESS_EVENT_DISCOVERED,
                "queued_discovered_urls": len(generated),
                "current_url": url,
                "limit": self.config.limit,
            }
        )
        progress.total = max(len(generated), 1)
        return len(generated) >= self.config.limit

    # ------------------------------------------------------------------
    # Block detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """Return True if the HTML looks like a WAF/bot-protection block page."""
        return _is_blocked_impl(html)

    @staticmethod
    def _content_length_without_chrome(html: str) -> int:
        """Return the visible-text length after stripping boilerplate tags.

        Removes ``<nav>``, ``<script>``, ``<style>``, ``<form>``, ``<header>``,
        ``<footer>``, and ``<noscript>`` so that navigation chrome does not
        inflate the content measurement used by WAF detection.
        """
        return _content_length_without_chrome_impl(html)

    # ------------------------------------------------------------------
    # PDF handling
    # ------------------------------------------------------------------

    @staticmethod
    def _is_document_url(url: str) -> bool:
        """Return True for binary documents fetched via direct download (PDF or DOCX)."""
        return _is_pdf_url_impl(url) or _is_docx_url_impl(url)

    @staticmethod
    def _is_pdf_url(url: str) -> bool:
        """Return True if the URL path ends with ``.pdf`` (case-insensitive)."""
        return _is_pdf_url_impl(url)

    @staticmethod
    async def _is_pdf_response(
        url: str,
        headers: dict[str, str] | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> bool:
        """Issue a HEAD request and return True if Content-Type is PDF."""
        return await _is_pdf_response_impl(
            url,
            headers,
            client=client,
            http_client_cls=httpx.AsyncClient,
        )

    async def _download_pdf(self, url: str) -> CrawlResult:
        """Download a PDF and convert it to Markdown via pymupdf4llm."""
        was_warned = self._ocr_warned
        result, self._ocr_warned = await _download_pdf_impl(
            url,
            headers=dict(self.config.headers) if self.config.headers else {},
            ocr_languages=self.page_config.ocr_languages,
            ocr_warned=self._ocr_warned,
            open_pdf=pymupdf.open,
            to_markdown=pymupdf4llm.to_markdown,
            client=getattr(self, "_pdf_client", None),
            http_client_cls=httpx.AsyncClient,
        )
        self._warn_ocr_unavailable_once(was_warned=was_warned)
        return result

    @staticmethod
    def _is_docx_url(url: str) -> bool:
        """Return True if the URL path ends with ``.docx`` (case-insensitive)."""
        return _is_docx_url_impl(url)

    @staticmethod
    async def _is_docx_response(
        url: str,
        headers: dict[str, str] | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> bool:
        """Issue a HEAD request and return True if Content-Type is DOCX."""
        return await _is_docx_response_impl(
            url,
            headers,
            client=client,
            http_client_cls=httpx.AsyncClient,
        )

    async def _download_docx(self, url: str) -> CrawlResult:
        """Download a DOCX file and convert it to Markdown via mammoth + markdownify."""
        return await _download_docx_impl(
            url,
            headers=dict(self.config.headers) if self.config.headers else {},
            convert_to_html=lambda fileobj: mammoth.convert_to_html(fileobj).value,
            to_markdown=lambda html: markdownify.markdownify(
                html, heading_style=_DOCX_HEADING_STYLE, strip=list(_DOCX_STRIP_TAGS)
            ),
            client=getattr(self, "_pdf_client", None),
            http_client_cls=httpx.AsyncClient,
        )

    def _pdf_to_markdown(self, doc: Any) -> str:
        """Convert a PyMuPDF document to Markdown, with optional OCR."""
        was_warned = self._ocr_warned
        markdown, self._ocr_warned = _pdf_to_markdown_impl(
            doc,
            ocr_languages=self.page_config.ocr_languages,
            ocr_warned=self._ocr_warned,
            to_markdown=pymupdf4llm.to_markdown,
        )
        self._warn_ocr_unavailable_once(was_warned=was_warned)
        return markdown

    # ------------------------------------------------------------------
    # Result helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_results(results: list[CrawlResult]) -> tuple[list[CrawlResult], list[CrawlResult]]:
        """Split results into (success, fail) lists."""
        success = [r for r in results if r.success]
        fail = [r for r in results if not r.success]
        return success, fail

    def _final_output_writer(self) -> FinalOutputWriter:
        assert self.output_dir is not None
        return FinalOutputWriter(
            output_dir=self.output_dir,
            output_extension=self.page_config.output_extension,
            max_file_size_mb=self.page_config.max_file_size_mb,
            run_metadata=self._run_metadata,
        )

    def _save_url_lists(
        self,
        success: list[CrawlResult],
        fail: list[CrawlResult],
        dir: Path,
    ) -> None:
        """Write per-round success and fail URL lists to *dir*."""
        self._final_output_writer().save_url_lists(success, fail, dir)

    def _write_round_success_files(self, round_num: int, round_dir: Path) -> None:
        """Write cumulative round success content as a round-end snapshot.

        Streams extracted pages from JSONL sidecar files for rounds
        1..N, deduplicating by URL, and writes content files.
        """
        if self._writer is None or self.output_dir is None:
            return
        self._final_output_writer().write_round_success_files(round_num, round_dir)

    def _write_sorted_round_files(self, round_num: int, round_dir: Path) -> None:
        """Write sorted content and URL files for one round.

        Streams pages from JSONL sidecar files via lightweight indexes:
        the index list is sorted, then each page is loaded one at a
        time and fed to the writer.  Success files are cumulative
        (rounds 1..N); fail files are current round only.  Controlled
        by the ``_ENABLE_SORTED_ROUND_FILES`` module flag.
        """
        if not _ENABLE_SORTED_ROUND_FILES:
            return
        if self._writer is None or self.output_dir is None:
            return
        self._final_output_writer().write_sorted_round_files(round_num, round_dir)

    def _clear_final_content_files(self, *, sorted_files: bool) -> None:
        """Remove stale final content files before regenerating a final view."""
        self._final_output_writer().clear_final_content_files(sorted_files=sorted_files)

    def _saved_results_from_sidecars(self) -> tuple[list[CrawlResult], list[CrawlResult]]:
        """Return lightweight result metadata for every page already persisted."""
        if self.output_dir is None:
            return [], []
        return self._final_output_writer().saved_results_from_sidecars()

    def _recover_saved_results(
        self, all_success: list[CrawlResult], all_fail: list[CrawlResult]
    ) -> tuple[list[CrawlResult], list[CrawlResult]]:
        """Reload completed pages from the sidecars and emit the interrupted event.

        Shared by the stop (KeyboardInterrupt / cancel) and the unexpected-error
        paths so both finalize the same partial output; returns the results to
        write out as the final files.
        """
        saved_success, saved_fail = self._saved_results_from_sidecars()
        if saved_success or saved_fail:
            all_success = saved_success
            all_fail = saved_fail
        self._emit_progress(
            {
                "event": _PROGRESS_EVENT_INTERRUPTED,
                "output_dir": str(self.output_dir) if self.output_dir else "",
                "successful_pages": len(all_success),
                "failed_pages": len(all_fail),
                "processed_pages": len(all_success) + len(all_fail),
                "limit": self.config.limit,
                "current_url": "",
                "next_url": "",
                "eta_remaining_seconds": None,
                "active_url_count": 0,
                "active_urls": [],
                "next_url_count": 0,
                "next_urls": [],
                "max_concurrent": self.config.max_concurrent,
            }
        )
        return all_success, all_fail

    @staticmethod
    def _write_url_file(path: Path, urls: list[str]) -> None:
        """Write a URL list, or remove a stale list when no URLs remain."""
        FinalOutputWriter.write_url_file(path, urls)

    def _write_final_files(
        self,
        all_success: list[CrawlResult],
        all_fail: list[CrawlResult],
    ) -> None:
        """Produce final merged URL lists (and unsorted content when kept).

        URL lists are built from the lightweight ``CrawlResult`` metadata
        (only ``.url`` is needed). The unsorted content is written only when
        intermediate cleanup is disabled; with cleanup on (the default),
        ``write_final_files`` skips it because ``_write_sorted_files`` immediately
        supersedes and deletes it — avoiding a redundant full pass over every page
        at finalization (lower peak CPU/memory and transient disk).
        """
        self._final_output_writer().write_final_files(
            all_success,
            all_fail,
            write_content=self._writer is not None,
        )

    def _write_sorted_files(
        self,
        all_success: list[CrawlResult],
        all_fail: list[CrawlResult],
    ) -> None:
        """Sort by URL path and write sorted final files.

        Streams pages from JSONL sidecar files via lightweight indexes:
        the index list is sorted, then each page is loaded one at a
        time and fed to the writer — the full corpus never lives in
        RAM at once.
        """
        if self._writer is None:
            return
        self._final_output_writer().write_sorted_files()

    def _get_final_content_files(self) -> list[Path]:
        """Return sorted list of final content files."""
        return self._final_output_writer().get_final_content_files()

    # ------------------------------------------------------------------
    # Sidecar helpers — build lightweight indexes for streaming sort
    # ------------------------------------------------------------------

    def _index_success(self, up_to_round: int | None = None) -> list[PageIndexEntry]:
        """Build a deduplicated success index across rounds.

        When *up_to_round* is given, only includes rounds 1..N (for
        cumulative round snapshots).  Otherwise includes all rounds.
        """
        return self._final_output_writer().index_success(up_to_round)

    def _index_fail(self, up_to_round: int | None = None) -> list[PageIndexEntry]:
        """Build a deduplicated fail index, excluding any URL that succeeded.

        When *up_to_round* is given, only includes rounds 1..N.
        """
        return self._final_output_writer().index_fail(up_to_round)

    def _stream_entries_to_writer(
        self,
        entries: list[PageIndexEntry],
        prefix: str,
        output_dir: Path | None = None,
    ) -> list[Path]:
        """Stream pages from *entries* through a fresh ``FileWriter``.

        Pages are loaded one at a time via :meth:`PageSidecar.read_page_at`,
        so the full corpus never lives in RAM.
        """
        return self._final_output_writer().stream_entries_to_writer(
            entries,
            prefix=prefix,
            output_dir=output_dir,
        )

    def _build_run_config(self, run_config_cls: type) -> object:
        """Map PageConfig to a Crawl4AI CrawlerRunConfig."""
        kwargs: dict = {}

        if self.page_config.exclude_tags:
            kwargs["excluded_tags"] = self.page_config.exclude_tags

        kwargs["wait_until"] = self.page_config.wait_until

        if self.page_config.wait_for:
            kwargs["delay_before_return_html"] = self.page_config.wait_for

        if self.page_config.js_code:
            kwargs["js_code"] = self.page_config.js_code

        if self.page_config.timeout:
            kwargs["page_timeout"] = int(self.page_config.timeout * 1000)

        if self.page_config.scan_full_page:
            kwargs["scan_full_page"] = True
            kwargs["scroll_delay"] = self.page_config.scroll_delay

        if self.page_config.flatten_shadow_dom:
            kwargs["flatten_shadow_dom"] = True

        if self.config.stealth:
            kwargs["simulate_user"] = True
            kwargs["override_navigator"] = True
            kwargs["magic"] = True

        # The initial crawl (round 1) routes through the proxy only when
        # proxy_on_initial is set; the fallback API is never used on the initial
        # crawl. Both are paid resources reserved per _paid_resource_rounds.
        proxy_rounds, _ = self._paid_resource_rounds()
        self._apply_anti_bot_run_options(kwargs, use_proxy=1 in proxy_rounds)
        return run_config_cls(**kwargs)

    def _build_fallback_run_config(self, run_config_cls: type, round_num: int) -> object:
        """Build a reduced CrawlerRunConfig for retry round *round_num*.

        Disables ``scan_full_page`` and stealth run-flags (``magic``,
        ``simulate_user``, ``override_navigator``) to avoid browser
        context destruction on pages that perform JS redirects during
        page evaluation.  Also downgrades ``wait_until`` to
        ``domcontentloaded`` to avoid repeated timeouts on
        analytics-heavy sites where ``networkidle`` never resolves.

        Proxies and the fallback API are paid resources, so each is applied to at
        most one retry round (see ``_paid_resource_rounds``) to cap per-crawl cost.
        """
        kwargs: dict = {}

        if self.page_config.exclude_tags:
            kwargs["excluded_tags"] = self.page_config.exclude_tags

        kwargs["wait_until"] = _FALLBACK_WAIT_UNTIL

        if self.page_config.wait_for:
            kwargs["delay_before_return_html"] = self.page_config.wait_for

        if self.page_config.js_code:
            kwargs["js_code"] = self.page_config.js_code

        if self.page_config.timeout:
            kwargs["page_timeout"] = int(self.page_config.timeout * 1000)

        if self.page_config.flatten_shadow_dom:
            kwargs["flatten_shadow_dom"] = True

        # scan_full_page and stealth run-flags intentionally omitted

        proxy_rounds, api_round = self._paid_resource_rounds()
        self._apply_anti_bot_run_options(
            kwargs,
            use_proxy=round_num in proxy_rounds,
            use_fallback_api=round_num == api_round,
        )

        return run_config_cls(**kwargs)

    def _paid_resource_rounds(self) -> tuple[frozenset[int], int | None]:
        """Return the rounds that use the proxy and the round that uses the API.

        Both are paid resources, so each is used sparingly to cap cost. Round 1 is
        the initial crawl; retries start at round 2. By default the initial crawl
        uses neither: the first retry uses the proxy and the second uses the API
        (each at most one round). When ``config.proxy_on_initial`` is set and
        proxies are configured, the proxy is applied to the initial crawl and the
        first retry (rounds 1 and 2) and the API (if any) moves to the second
        retry (round 3). Returns ``(proxy_rounds, api_round)``; ``proxy_rounds``
        may be empty and ``api_round`` may be ``None``.
        """
        has_proxy = bool(self.config.proxies)
        has_api = self._fallback_fetch_function is not None
        if has_proxy and self.config.proxy_on_initial:
            return frozenset({1, 2}), (3 if has_api else None)
        if has_proxy and has_api:
            return frozenset({2}), 3
        if has_proxy:
            return frozenset({2}), None
        if has_api:
            return frozenset(), 2
        return frozenset(), None

    def _apply_anti_bot_run_options(
        self, kwargs: dict, *, use_proxy: bool = False, use_fallback_api: bool = False
    ) -> None:
        """Add proxy escalation and/or the fallback fetch hook to a run-config dict.

        Proxies and the fallback scraping API are paid resources applied per
        ``_paid_resource_rounds``: the proxy runs only on the round(s) it assigns
        (the initial crawl only when ``proxy_on_initial`` is set) and the fallback
        API on at most one retry round.
        """
        if use_proxy:
            proxy_config = self._build_proxy_config()
            if proxy_config is not None:
                kwargs["proxy_config"] = proxy_config
        if use_fallback_api and self._fallback_fetch_function is not None:
            kwargs["fallback_fetch_function"] = self._fallback_fetch_function

    def _build_proxy_config(self) -> list[Any] | None:
        """Build a direct-first proxy escalation list for Crawl4AI, or None.

        Returns ``[ProxyConfig.DIRECT, *proxies]`` so each request is tried without
        a proxy first, then through the configured proxies in order. Returns
        ``None`` when no proxies are set or the installed Crawl4AI lacks
        ``ProxyConfig`` (graceful no-op).
        """
        if not self.config.proxies:
            return None
        proxy_config_cls = _load_proxy_config_cls()
        if proxy_config_cls is None:
            return None
        proxies = [proxy_config_cls.from_string(proxy) for proxy in self.config.proxies]
        return [proxy_config_cls.DIRECT, *proxies]

    def _build_undetected_strategy(self, browser_cfg: object) -> object | None:
        """Build an undetected-browser crawler strategy, or None if unavailable.

        Emits a structured warning and returns ``None`` when the installed Crawl4AI
        does not provide the undetected adapter, so the crawl falls back to the
        standard stealth browser instead of failing.
        """
        loaded = _load_undetected_classes()
        if loaded is None:
            self._emit_crawl_warning(messages.undetected_unavailable())
            return None
        strategy_cls, adapter_cls = loaded
        return strategy_cls(browser_config=browser_cfg, browser_adapter=adapter_cls())

    def _url_in_allowed_domain(self, url: str) -> bool:
        """Check whether a URL belongs to the configured crawl domain(s)."""
        return _url_in_allowed_domain_impl(url, self._allowed_domains)

    def _url_allowed(self, url: str) -> bool:
        """Check whether a URL passes include/exclude filters."""
        return _url_allowed_impl(url, self.config, self._allowed_domains)

    # File extensions that are never useful pages to crawl
    _STATIC_ASSET_EXTENSIONS = _URL_FILTER_STATIC_ASSET_EXTENSIONS

    # Domains that appear as boilerplate "upgrade your browser" links on
    # many websites and are never useful crawl targets.
    _BOILERPLATE_DOMAINS = _URL_FILTER_BOILERPLATE_DOMAINS

    @staticmethod
    def _normalize_url(url: str, *, strip_www: bool = True) -> str:
        """Normalize a URL to reduce duplicate crawling.

        Applies: ``http`` → ``https``, optionally strips ``www.`` prefix,
        lowercases scheme + host, preserves path/query, and drops fragments.
        """
        return _normalize_url_impl(url, strip_www=strip_www)

    @staticmethod
    def _extract_base_domains(urls: list[str], *, strip_www: bool = True) -> set[str]:
        """Derive base domains from seed URLs (e.g. 'starhub.com' from 'www.starhub.com')."""
        return _extract_base_domains_impl(urls, strip_www=strip_www)

    @staticmethod
    def _extract_links(result: CrawlResult, base_url: str, *, strip_www: bool = True) -> list[str]:
        """Extract absolute http(s) links from crawled HTML."""
        return _extract_links_impl(result, base_url, strip_www=strip_www)

    def _create_output_dir(self) -> Path:
        """Create and return a timestamped output directory."""
        self._run_started_at_utc = datetime.now(timezone.utc)
        folder_name = format_utc_timestamp_slug(self._run_started_at_utc)
        output_dir = self._output_base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _build_run_metadata(self) -> dict[str, object]:
        """Build run-level metadata used in output-file YAML front matter."""
        assert self.output_dir is not None
        run_started_at = self._run_started_at_utc or datetime.now(timezone.utc)
        crawl_parameters: dict[str, object] = {
            "crawler_config": self.config.model_dump(mode="json"),
            "page_config": self.page_config.model_dump(mode="json"),
        }
        return {
            "crawl_start_datetime": run_started_at.isoformat(timespec="seconds"),
            "session_id": self._session_id or self.output_dir.name,
            "crawl_parameters": crawl_parameters,
        }

    def _save_url_list(self, results: list[CrawlResult]) -> None:
        """Write urls.txt with one URL per line (legacy, kept for compatibility)."""
        assert self.output_dir is not None
        urls_file = self.output_dir / "urls.txt"
        lines = [r.url for r in results]
        urls_file.write_text("\n".join(lines), encoding="utf-8")
