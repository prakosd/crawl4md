"""Tests for internal DOCX helper functions."""

from __future__ import annotations

import ssl
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from crawl4md._internal.docx import docx_to_markdown, download_docx, is_docx_response, is_docx_url


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
        response.content = b"docx-bytes"
        response.raise_for_status = MagicMock()
        return response


def test_is_docx_url_uses_path_extension() -> None:
    assert is_docx_url("https://example.com/REPORT.DOCX?download=1") is True
    assert is_docx_url("https://example.com/docx/report") is False
    # Legacy binary .doc is intentionally not treated as DOCX.
    assert is_docx_url("https://example.com/report.doc") is False


@pytest.mark.asyncio
async def test_is_docx_response_uses_provided_client() -> None:
    response = MagicMock()
    response.headers = {
        "content-type": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    }
    client = AsyncMock()
    client.head = AsyncMock(return_value=response)

    result = await is_docx_response("https://example.com/download", client=client)

    assert result is True
    client.head.assert_awaited_once_with("https://example.com/download")


@pytest.mark.asyncio
async def test_download_docx_fallback_uses_browser_headers_and_os_trust() -> None:
    result = await download_docx(
        "https://host.example/a/report.docx",
        headers=None,
        convert_to_html=lambda fileobj: "<p>hi</p>",
        to_markdown=lambda html: "hi",
        http_client_cls=_RecordingClient,
    )

    assert result.success is True
    kwargs = _RecordingClient.last_kwargs
    assert "Mozilla/" in kwargs["headers"]["User-Agent"]  # real browser agent
    assert kwargs["headers"]["Referer"] == "https://host.example/"  # same-origin
    assert isinstance(kwargs["verify"], ssl.SSLContext)  # OS trust store, not certifi


@pytest.mark.asyncio
async def test_is_docx_response_returns_false_on_http_error() -> None:
    client = AsyncMock()
    client.head = AsyncMock(side_effect=httpx.ConnectError("failed"))

    result = await is_docx_response("https://example.com/download", client=client)

    assert result is False


def test_docx_to_markdown_converts_via_html_intermediate() -> None:
    convert_to_html = MagicMock(return_value="<h1>Title</h1>")
    to_markdown = MagicMock(return_value="# Title")

    markdown = docx_to_markdown(
        b"docx-bytes", convert_to_html=convert_to_html, to_markdown=to_markdown
    )

    assert markdown == "# Title"
    to_markdown.assert_called_once_with("<h1>Title</h1>")
    (fileobj,), _ = convert_to_html.call_args
    assert fileobj.getvalue() == b"docx-bytes"


@pytest.mark.asyncio
async def test_download_docx_converts_response_to_markdown() -> None:
    response = MagicMock()
    response.content = b"docx-bytes"
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    convert_to_html = MagicMock(return_value="<h1>Report</h1>")
    to_markdown = MagicMock(return_value="# Report")

    result = await download_docx(
        "https://example.com/report.docx",
        headers={},
        convert_to_html=convert_to_html,
        to_markdown=to_markdown,
        client=client,
    )

    assert result.success is True
    assert result.is_docx is True
    assert result.markdown == "# Report"
    to_markdown.assert_called_once_with("<h1>Report</h1>")


@pytest.mark.asyncio
async def test_download_docx_reports_error_on_conversion_failure() -> None:
    response = MagicMock()
    response.content = b"docx-bytes"
    response.raise_for_status = MagicMock()
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    convert_to_html = MagicMock(side_effect=ValueError("bad docx"))
    to_markdown = MagicMock()

    result = await download_docx(
        "https://example.com/report.docx",
        headers={},
        convert_to_html=convert_to_html,
        to_markdown=to_markdown,
        client=client,
    )

    assert result.success is False
    assert result.is_docx is True
    assert "ValueError" in (result.error or "")
    to_markdown.assert_not_called()
