"""Stable message codes and builders for the crawl4md result contract.

Per-page failures set :attr:`~crawl4md.config.CrawlResult.error_code` to one of the
``CODE_*`` values below (the free-text ``error`` stays as human detail). Crawl-level
warnings are emitted as ``crawl_warning`` progress events carrying a
:class:`~artifact_store.LibraryMessage`, and :func:`classify_crawl_error` turns a
fatal crawl exception into a coded message a UI can localize. ``default_text`` is the
English shown when no localization is available, so terminal output and logs stay readable.
"""

from __future__ import annotations

from artifact_store import SEVERITY_ERROR, SEVERITY_WARNING, LibraryMessage

__all__ = [
    "CODE_BLOCKED",
    "CODE_BLOCKED_BACKOFF",
    "CODE_BROWSER_MISSING",
    "CODE_CRAWL_FAILED",
    "CODE_EMPTY_CONTENT",
    "CODE_ENGINE_MISSING",
    "CODE_OCR_UNAVAILABLE",
    "CODE_REDIRECT_LOOP",
    "CODE_SSL_CERTIFICATE",
    "CODE_UNDETECTED_UNAVAILABLE",
    "blocked_backoff",
    "classify_crawl_error",
    "ocr_unavailable",
    "undetected_unavailable",
]

# Per-page failure codes (set on CrawlResult.error_code at the point of failure).
CODE_BLOCKED = "crawl.blocked"
CODE_EMPTY_CONTENT = "crawl.empty_content"
CODE_REDIRECT_LOOP = "crawl.redirect_loop"

# Crawl-level warning codes (emitted as crawl_warning events).
CODE_OCR_UNAVAILABLE = "crawl.ocr_unavailable"
CODE_BLOCKED_BACKOFF = "crawl.blocked_backoff"
CODE_UNDETECTED_UNAVAILABLE = "crawl.undetected_unavailable"

# Fatal crawl-error codes (from classify_crawl_error).
CODE_BROWSER_MISSING = "crawl.browser_missing"
CODE_ENGINE_MISSING = "crawl.engine_missing"
CODE_SSL_CERTIFICATE = "crawl.ssl_certificate"
CODE_CRAWL_FAILED = "crawl.crawl_failed"

# Substrings that identify a missing Playwright browser executable.
_BROWSER_MISSING_SIGNATURES = (
    "browsertype.launch: executable doesn't exist",
    "playwright install",
)
# Substrings that identify the crawl4ai engine not being installed.
_ENGINE_MISSING_SIGNATURES = (
    "no module named 'crawl4ai'",
    'no module named "crawl4ai"',
)
# Substrings that mark a TLS/SSL certificate failure inside a backend exception.
_SSL_ERROR_SIGNATURES = (
    "certificate_verify_failed",
    "certificate verify failed",
    "sslcertverificationerror",
    "ssl: certificate",
)


def _warn(code: str, text: str, **params: object) -> LibraryMessage:
    return LibraryMessage(code=code, default_text=text, params=params, severity=SEVERITY_WARNING)


def _error(code: str, text: str, **params: object) -> LibraryMessage:
    return LibraryMessage(code=code, default_text=text, params=params, severity=SEVERITY_ERROR)


def ocr_unavailable() -> LibraryMessage:
    return _warn(
        CODE_OCR_UNAVAILABLE,
        "Some PDF pages are scanned images, but OCR is unavailable because Tesseract "
        "is not installed, so the text on those pages could not be extracted.",
    )


def blocked_backoff(wait_seconds: float) -> LibraryMessage:
    return _warn(
        CODE_BLOCKED_BACKOFF,
        "The website appears to be blocking automated access; "
        f"pausing about {wait_seconds:.0f}s before continuing.",
        wait_seconds=wait_seconds,
    )


def undetected_unavailable() -> LibraryMessage:
    return _warn(
        CODE_UNDETECTED_UNAVAILABLE,
        "Undetected browser mode was requested but is unavailable in this "
        "crawl4ai install; continuing with the standard stealth browser.",
    )


def classify_crawl_error(detail: str) -> LibraryMessage:
    """Turn a fatal crawl exception's text into a coded, localizable error message."""
    lowered = detail.lower()
    if any(signature in lowered for signature in _BROWSER_MISSING_SIGNATURES):
        return _error(
            CODE_BROWSER_MISSING,
            "The browser needed for crawling is not installed. Run: "
            "playwright install --with-deps chromium",
            detail=detail,
        )
    if any(signature in lowered for signature in _ENGINE_MISSING_SIGNATURES):
        return _error(
            CODE_ENGINE_MISSING,
            "The crawler engine is not installed. Install it with: "
            'pip install "rag-playground[crawl]"',
            detail=detail,
        )
    if any(signature in lowered for signature in _SSL_ERROR_SIGNATURES):
        return _error(
            CODE_SSL_CERTIFICATE,
            f"Could not crawl because a TLS/SSL certificate could not be verified: {detail}",
            detail=detail,
        )
    return _error(CODE_CRAWL_FAILED, f"The crawl could not be completed: {detail}", detail=detail)
