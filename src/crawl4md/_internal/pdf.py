"""PDF detection, download, and Markdown conversion helpers."""

from __future__ import annotations

import warnings
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from crawl4md._internal.http_client import (
    document_ssl_context,
    merge_document_headers,
    referer_for_url,
)
from crawl4md.config import CrawlResult

__all__ = [
    "download_pdf",
    "is_pdf_response",
    "is_pdf_url",
    "pdf_to_markdown",
]

_PDF_EXTENSION = ".pdf"
_PDF_CONTENT_TYPE = "application/pdf"
_PDF_DOWNLOAD_TIMEOUT = 60
_PDF_FALLBACK_THRESHOLD = 50
_OCR_UNAVAILABLE_WARNING = (
    "Tesseract OCR is not installed — scanned/image-only PDFs will not be "
    "extracted. Install Tesseract and the required language packs for OCR "
    "support, or set ocr_languages=[] to silence this warning."
)


def is_pdf_url(url: str) -> bool:
    """Return True if the URL path ends with ``.pdf``."""
    return urlparse(url).path.lower().endswith(_PDF_EXTENSION)


async def is_pdf_response(
    url: str,
    headers: dict[str, str] | None = None,
    *,
    client: httpx.AsyncClient | None = None,
    http_client_cls: type[httpx.AsyncClient] = httpx.AsyncClient,
) -> bool:
    """Issue a HEAD request and return True if Content-Type is PDF."""
    try:
        if client is not None:
            response = await client.head(url)
            content_type = response.headers.get("content-type", "")
            return content_type.lower().startswith(_PDF_CONTENT_TYPE)
        async with http_client_cls(
            headers=merge_document_headers(headers, referer=referer_for_url(url)),
            timeout=_PDF_DOWNLOAD_TIMEOUT,
            follow_redirects=True,
            verify=document_ssl_context(),
        ) as fallback_client:
            response = await fallback_client.head(url)
            content_type = response.headers.get("content-type", "")
            return content_type.lower().startswith(_PDF_CONTENT_TYPE)
    except httpx.HTTPError:
        return False


async def download_pdf(
    url: str,
    *,
    headers: dict[str, str] | None,
    ocr_languages: list[str],
    ocr_warned: bool,
    open_pdf: Callable[..., Any],
    to_markdown: Callable[..., str],
    client: httpx.AsyncClient | None = None,
    http_client_cls: type[httpx.AsyncClient] = httpx.AsyncClient,
) -> tuple[CrawlResult, bool]:
    """Download a PDF and convert it to Markdown."""
    try:
        if client is None:
            async with http_client_cls(
                headers=merge_document_headers(headers, referer=referer_for_url(url)),
                timeout=_PDF_DOWNLOAD_TIMEOUT,
                follow_redirects=True,
                verify=document_ssl_context(),
            ) as fallback_client:
                response = await fallback_client.get(url)
                response.raise_for_status()
        else:
            response = await client.get(url)
            response.raise_for_status()

        doc = open_pdf(stream=response.content, filetype="pdf")
        try:
            markdown, ocr_warned = pdf_to_markdown(
                doc,
                ocr_languages=ocr_languages,
                ocr_warned=ocr_warned,
                to_markdown=to_markdown,
            )
        finally:
            doc.close()

        return CrawlResult(url=url, markdown=markdown, success=True, is_pdf=True), ocr_warned
    except Exception as exc:  # noqa: BLE001 - PDF failures are reported as CrawlResult errors.
        return (
            CrawlResult(
                url=url,
                success=False,
                error=f"PDF download failed: {type(exc).__name__}: {exc}",
                is_pdf=True,
            ),
            ocr_warned,
        )


def pdf_to_markdown(
    doc: Any,
    *,
    ocr_languages: list[str],
    ocr_warned: bool,
    to_markdown: Callable[..., str],
) -> tuple[str, bool]:
    """Convert a PyMuPDF document to Markdown, with optional OCR."""
    if not ocr_languages:
        return to_markdown(doc), ocr_warned

    try:
        return to_markdown(doc, use_ocr=True, ocr_language="+".join(ocr_languages)), ocr_warned
    except (RuntimeError, FileNotFoundError, TypeError):
        if not ocr_warned:
            ocr_warned = True
            warnings.warn(_OCR_UNAVAILABLE_WARNING, stacklevel=3)
        return to_markdown(doc), ocr_warned
