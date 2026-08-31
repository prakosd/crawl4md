"""DOCX detection, download, and Markdown conversion helpers.

Mirrors :mod:`crawl4md._internal.pdf`: the heavy converters (mammoth for
DOCX→HTML, markdownify for HTML→Markdown) are injected by the caller so this
module stays dependency-free and unit-testable without those packages. Legacy
``.doc`` (the binary Word format) is intentionally not supported here.
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO
from urllib.parse import urlparse

import httpx

from crawl4md._internal.http_client import (
    document_ssl_context,
    merge_document_headers,
    referer_for_url,
)
from crawl4md.config import CrawlResult

__all__ = [
    "download_docx",
    "docx_to_markdown",
    "is_docx_response",
    "is_docx_url",
]

_DOCX_EXTENSION = ".docx"
_DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_DOCX_DOWNLOAD_TIMEOUT = 60


def is_docx_url(url: str) -> bool:
    """Return True if the URL path ends with ``.docx`` (case-insensitive)."""
    return urlparse(url).path.lower().endswith(_DOCX_EXTENSION)


async def is_docx_response(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    client: httpx.AsyncClient | None = None,
    http_client_cls: type[httpx.AsyncClient] = httpx.AsyncClient,
) -> bool:
    """Issue a HEAD request and return True if Content-Type is DOCX."""
    try:
        if client is not None:
            response = await client.head(url)
            content_type = response.headers.get("content-type", "")
            return content_type.lower().startswith(_DOCX_CONTENT_TYPE)
        async with http_client_cls(
            headers=merge_document_headers(headers, referer=referer_for_url(url)),
            timeout=_DOCX_DOWNLOAD_TIMEOUT,
            follow_redirects=True,
            verify=document_ssl_context(),
        ) as fallback_client:
            response = await fallback_client.head(url)
            content_type = response.headers.get("content-type", "")
            return content_type.lower().startswith(_DOCX_CONTENT_TYPE)
    except httpx.HTTPError:
        return False


def docx_to_markdown(
    content: bytes,
    *,
    convert_to_html: Callable[..., str],
    to_markdown: Callable[..., str],
) -> str:
    """Convert DOCX bytes to Markdown through a clean HTML intermediate."""
    html = convert_to_html(BytesIO(content))
    return to_markdown(html)


async def download_docx(
    url: str,
    *,
    headers: dict[str, str] | None,
    convert_to_html: Callable[..., str],
    to_markdown: Callable[..., str],
    client: httpx.AsyncClient | None = None,
    http_client_cls: type[httpx.AsyncClient] = httpx.AsyncClient,
) -> CrawlResult:
    """Download a DOCX file and convert it to Markdown."""
    try:
        if client is None:
            async with http_client_cls(
                headers=merge_document_headers(headers, referer=referer_for_url(url)),
                timeout=_DOCX_DOWNLOAD_TIMEOUT,
                follow_redirects=True,
                verify=document_ssl_context(),
            ) as fallback_client:
                response = await fallback_client.get(url)
                response.raise_for_status()
        else:
            response = await client.get(url)
            response.raise_for_status()

        markdown = docx_to_markdown(
            response.content,
            convert_to_html=convert_to_html,
            to_markdown=to_markdown,
        )
        return CrawlResult(url=url, markdown=markdown, success=True, is_docx=True)
    except Exception as exc:  # noqa: BLE001 - DOCX failures are reported as CrawlResult errors.
        return CrawlResult(
            url=url,
            success=False,
            error=f"DOCX download failed: {type(exc).__name__}: {exc}",
            is_docx=True,
        )
