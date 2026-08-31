"""Shared HTTP setup for direct document (PDF/DOCX) downloads.

The crawler fetches PDFs and DOCX files with ``httpx`` directly (not through the
browser). Two defaults here make those downloads behave like the browser round:
a real desktop User-Agent (so hosts that reject the bare ``httpx`` agent still
serve the file) and an OS-trust-store TLS context via ``truststore`` (so a
corporate TLS-intercepting proxy's root CA verifies, just as it does for the
browser and ``pip``). ``CrawlerConfig.headers`` always override these defaults.
"""

from __future__ import annotations

import ssl
from functools import lru_cache
from urllib.parse import urlsplit

import truststore

__all__ = [
    "DEFAULT_DOCUMENT_HEADERS",
    "document_ssl_context",
    "merge_document_headers",
    "referer_for_url",
]

# A current desktop-Chrome User-Agent plus the Accept headers a browser sends for
# a file download; hosts that reject the default "python-httpx/x" agent serve this.
_DOCUMENT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_DOCUMENT_HEADERS = {
    "User-Agent": _DOCUMENT_USER_AGENT,
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@lru_cache(maxsize=1)
def document_ssl_context() -> ssl.SSLContext:
    """Return a TLS context that trusts the OS certificate store.

    Uses ``truststore`` so the OS trust store (which carries a corporate proxy's
    root CA, like the browser and ``pip``) verifies the connection — ``httpx``'s
    default ``certifi`` bundle does not, which otherwise fails document downloads
    behind a TLS-intercepting proxy. Cached: one shared context per process.
    """
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def merge_document_headers(
    config_headers: dict[str, str] | None,
    referer: str | None = None,
) -> dict[str, str]:
    """Merge the browser-like defaults with the caller's headers (caller wins).

    An optional same-origin ``referer`` is added first so ``CrawlerConfig.headers``
    stays authoritative — a caller-supplied Referer (or any other header) overrides.
    """
    headers = dict(DEFAULT_DOCUMENT_HEADERS)
    if referer:
        headers["Referer"] = referer
    if config_headers:
        headers.update(config_headers)
    return headers


def referer_for_url(url: str) -> str | None:
    """Return the same-origin ``scheme://host/`` Referer for *url*, or None."""
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}/"
