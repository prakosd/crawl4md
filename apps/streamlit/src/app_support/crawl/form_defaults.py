"""Default form values for the crawl4md Streamlit app."""

from __future__ import annotations

from typing import Any

from app_support.settings import get_settings

_settings = get_settings()

DEFAULT_DELAY = _settings.crawl_delay
DEFAULT_ACTIVITY_LOG_SIZE = _settings.crawl_activity_log_size
DEFAULT_EXCLUDE_PATHS = _settings.crawl_exclude_paths
DEFAULT_EXCLUDE_TAGS = _settings.crawl_exclude_tags
DEFAULT_FLUSH_INTERVAL = _settings.crawl_flush_interval
DEFAULT_INCLUDE_ONLY_PATHS = _settings.crawl_include_only_paths
DEFAULT_LIMIT = _settings.crawl_limit
DEFAULT_MAX_DEPTH = _settings.crawl_max_depth
DEFAULT_MAX_CONCURRENT = _settings.crawl_max_concurrent
DEFAULT_MAX_FILE_SIZE_MB = _settings.crawl_max_file_size_mb
DEFAULT_MAX_RETRIES = _settings.crawl_max_retries
DEFAULT_OUTPUT_EXTENSION = _settings.crawl_default_output_extension
DEFAULT_TIMEOUT = _settings.crawl_timeout
DEFAULT_URLS = _settings.crawl_default_urls
DEFAULT_WAIT_FOR = _settings.crawl_wait_for
# The supported extensions, with the configured default first so the form's
# selector pre-selects it (deduplicated to avoid a repeated option).
_SUPPORTED_OUTPUT_EXTENSIONS = (".md", ".txt")
OUTPUT_EXTENSION_OPTIONS = [
    DEFAULT_OUTPUT_EXTENSION,
    *(ext for ext in _SUPPORTED_OUTPUT_EXTENSIONS if ext != DEFAULT_OUTPUT_EXTENSION),
]


def default_form_values() -> dict[str, Any]:
    """Return the default crawl settings used for a new Streamlit form."""
    return {
        "urls": DEFAULT_URLS,
        "include_only_paths": DEFAULT_INCLUDE_ONLY_PATHS,
        "exclude_paths": DEFAULT_EXCLUDE_PATHS,
        "limit": DEFAULT_LIMIT,
        "max_depth": DEFAULT_MAX_DEPTH,
        "max_concurrent": DEFAULT_MAX_CONCURRENT,
        "flush_interval": DEFAULT_FLUSH_INTERVAL,
        "delay": DEFAULT_DELAY,
        "max_retries": DEFAULT_MAX_RETRIES,
        "exclude_tags": DEFAULT_EXCLUDE_TAGS,
        "include_only_tags": "",
        "wait_for": DEFAULT_WAIT_FOR,
        "timeout": DEFAULT_TIMEOUT,
        "max_file_size_mb": DEFAULT_MAX_FILE_SIZE_MB,
        "extract_main_content": True,
        "output_extension": DEFAULT_OUTPUT_EXTENSION,
        "activity_log_size": DEFAULT_ACTIVITY_LOG_SIZE,
    }


def form_state_from_submitted(values: dict[str, Any]) -> dict[str, Any]:
    """Return the persistable field values from a submitted crawl form.

    Keeps only the keys of :func:`default_form_values` (dropping control flags
    such as ``submitted``) so the stored state can re-render the user's entries
    in the disabled form during and after a crawl instead of snapping back to
    defaults.
    """
    return {key: values.get(key, default) for key, default in default_form_values().items()}
