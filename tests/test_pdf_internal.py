"""Tests for internal PDF helper functions."""

from __future__ import annotations

import ssl
import warnings
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from crawl4md._internal.pdf import download_pdf, is_pdf_response, is_pdf_url, pdf_to_markdown


class _RecordingClient:
    """Fake httpx client that records its constructor kwargs for the fallback path."""

    last_kwargs: dict = {}

    def __init__(self, **kwargs: object) -> None:
        type(self).last_kwargs = kwargs

    async def __aenter__(self) -> _RecordingClient:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def get(self, url: str):  # noqa: ANN201 - test double
        response = MagicMock()
        response.content = b"pdf-bytes"
        response.raise_for_status = MagicMock()
        return response


def test_is_pdf_url_uses_path_extension() -> None:
    assert is_pdf_url("https://example.com/DOC.PDF?download=1") is True
    assert is_pdf_url("https://example.com/pdf/report") is False


@pytest.mark.asyncio
async def test_is_pdf_response_uses_provided_client() -> None:
    response = MagicMock()
    response.headers = {"content-type": "application/pdf; charset=binary"}
    client = AsyncMock()
    client.head = AsyncMock(return_value=response)

    result = await is_pdf_response("https://example.com/report", client=client)

    assert result is True
    client.head.assert_awaited_once_with("https://example.com/report")


@pytest.mark.asyncio
async def test_download_pdf_fallback_uses_browser_headers_and_os_trust() -> None:
    result, _ = await download_pdf(
        "https://host.example/a/report.pdf",
        headers={},
        ocr_languages=[],
        ocr_warned=False,
        open_pdf=MagicMock(return_value=MagicMock()),
        to_markdown=MagicMock(return_value="# R"),
        http_client_cls=_RecordingClient,
    )

    assert result.success is True
    kwargs = _RecordingClient.last_kwargs
    assert "Mozilla/" in kwargs["headers"]["User-Agent"]  # real browser agent
    assert kwargs["headers"]["Referer"] == "https://host.example/"  # same-origin
    assert isinstance(kwargs["verify"], ssl.SSLContext)  # OS trust store, not certifi


@pytest.mark.asyncio
async def test_is_pdf_response_returns_false_on_http_error() -> None:
    client = AsyncMock()
    client.head = AsyncMock(side_effect=httpx.ConnectError("failed"))

    result = await is_pdf_response("https://example.com/report", client=client)

    assert result is False


@pytest.mark.asyncio
async def test_download_pdf_converts_response_to_markdown() -> None:
    response = MagicMock()
    response.content = b"pdf-bytes"
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    doc = MagicMock()
    open_pdf = MagicMock(return_value=doc)
    to_markdown = MagicMock(return_value="# Report")

    result, ocr_warned = await download_pdf(
        "https://example.com/report.pdf",
        headers={},
        ocr_languages=[],
        ocr_warned=False,
        open_pdf=open_pdf,
        to_markdown=to_markdown,
        client=client,
    )

    assert result.success is True
    assert result.is_pdf is True
    assert result.markdown == "# Report"
    assert ocr_warned is False
    open_pdf.assert_called_once_with(stream=b"pdf-bytes", filetype="pdf")
    doc.close.assert_called_once()


@pytest.mark.asyncio
async def test_download_pdf_closes_document_when_conversion_fails() -> None:
    response = MagicMock()
    response.content = b"pdf-bytes"
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    doc = MagicMock()
    open_pdf = MagicMock(return_value=doc)
    to_markdown = MagicMock(side_effect=ValueError("bad pdf"))

    result, ocr_warned = await download_pdf(
        "https://example.com/report.pdf",
        headers={},
        ocr_languages=[],
        ocr_warned=False,
        open_pdf=open_pdf,
        to_markdown=to_markdown,
        client=client,
    )

    assert result.success is False
    assert result.is_pdf is True
    assert "ValueError" in (result.error or "")
    assert ocr_warned is False
    doc.close.assert_called_once()


def test_pdf_to_markdown_warns_once_and_falls_back_without_ocr() -> None:
    doc = MagicMock()
    to_markdown = MagicMock(side_effect=[RuntimeError("tesseract"), "fallback"])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        markdown, ocr_warned = pdf_to_markdown(
            doc,
            ocr_languages=["eng"],
            ocr_warned=False,
            to_markdown=to_markdown,
        )

    assert markdown == "fallback"
    assert ocr_warned is True
    assert len(caught) == 1
    assert to_markdown.call_count == 2
