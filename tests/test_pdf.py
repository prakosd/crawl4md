"""Tests for PDF crawling and extraction support."""

from __future__ import annotations

import asyncio
import warnings
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from crawl4md import messages
from crawl4md.config import CrawlerConfig, CrawlResult, PageConfig
from crawl4md.crawler import (
    _JITTER_RETRY_MAX,
    _JITTER_RETRY_MIN,
    _OCR_UNAVAILABLE_WARNING,
    SiteCrawler,
)
from crawl4md.extractor import ContentExtractor
from crawl4md.progress import ProgressReporter
from crawl4md.writer import FileWriter, PageSidecar
from tests.conftest import _make_mock_result

# ------------------------------------------------------------------
# CrawlResult.is_pdf field
# ------------------------------------------------------------------


class TestCrawlResultIsPdf:
    def test_is_pdf_default_false(self):
        r = CrawlResult(url="https://example.com")
        assert r.is_pdf is False

    def test_is_pdf_explicit_true(self):
        r = CrawlResult(url="https://example.com/doc.pdf", is_pdf=True)
        assert r.is_pdf is True

    def test_is_pdf_explicit_false(self):
        r = CrawlResult(url="https://example.com/doc.pdf", is_pdf=False)
        assert r.is_pdf is False


# ------------------------------------------------------------------
# SiteCrawler._is_pdf_url
# ------------------------------------------------------------------


class TestIsPdfUrl:
    def test_plain_pdf_url(self):
        assert SiteCrawler._is_pdf_url("https://example.com/doc.pdf") is True

    def test_pdf_with_query_params(self):
        assert SiteCrawler._is_pdf_url("https://example.com/doc.pdf?token=abc") is True

    def test_pdf_with_fragment(self):
        assert SiteCrawler._is_pdf_url("https://example.com/doc.pdf#page=3") is True

    def test_case_insensitive(self):
        assert SiteCrawler._is_pdf_url("https://example.com/DOC.PDF") is True
        assert SiteCrawler._is_pdf_url("https://example.com/doc.Pdf") is True

    def test_non_pdf_url(self):
        assert SiteCrawler._is_pdf_url("https://example.com/page.html") is False

    def test_no_extension(self):
        assert SiteCrawler._is_pdf_url("https://example.com/download") is False

    def test_pdf_in_path_but_not_extension(self):
        assert SiteCrawler._is_pdf_url("https://example.com/pdf/report") is False

    def test_deep_path_pdf(self):
        url = "https://phl.hasil.gov.my/pdf/pdfam/Lampiran_A_Panduan.pdf"
        assert SiteCrawler._is_pdf_url(url) is True


# ------------------------------------------------------------------
# SiteCrawler._is_pdf_response
# ------------------------------------------------------------------


class TestIsPdfResponse:
    @pytest.mark.asyncio
    async def test_pdf_content_type(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_pdf_response("https://example.com/download?id=1")
        assert result is True

    @pytest.mark.asyncio
    async def test_html_content_type(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html; charset=utf-8"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_pdf_response("https://example.com/page")
        assert result is False

    @pytest.mark.asyncio
    async def test_pdf_content_type_with_params(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf; charset=binary"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_pdf_response("https://example.com/report")
        assert result is True

    @pytest.mark.asyncio
    async def test_connection_error_returns_false(self):
        import httpx

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(side_effect=httpx.ConnectError("connection failed"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await SiteCrawler._is_pdf_response("https://example.com/report")
        assert result is False

    @pytest.mark.asyncio
    async def test_forwards_headers(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client) as mock_cls:
            await SiteCrawler._is_pdf_response(
                "https://example.com/report", {"Authorization": "Bearer x"}
            )
        mock_cls.assert_called_once()
        headers = mock_cls.call_args.kwargs["headers"]
        assert headers["Authorization"] == "Bearer x"  # config header forwarded
        assert "Mozilla/" in headers["User-Agent"]  # merged with browser defaults
        assert headers["Referer"] == "https://example.com/"  # same-origin

    @pytest.mark.asyncio
    async def test_uses_provided_client(self):
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/pdf"}

        mock_client = AsyncMock()
        mock_client.head = AsyncMock(return_value=mock_response)

        with patch("crawl4md.crawler.httpx.AsyncClient") as mock_cls:
            result = await SiteCrawler._is_pdf_response(
                "https://example.com/report",
                client=mock_client,
            )

        assert result is True
        mock_client.head.assert_awaited_once_with("https://example.com/report")
        mock_cls.assert_not_called()


# ------------------------------------------------------------------
# SiteCrawler._download_pdf
# ------------------------------------------------------------------


class TestDownloadPdf:
    @pytest.mark.asyncio
    async def test_successful_download(self):
        config = MagicMock()
        config.headers = {"User-Agent": "test"}

        crawler = SiteCrawler.__new__(SiteCrawler)
        crawler.config = config
        crawler.page_config = PageConfig(ocr_languages=[])
        crawler._ocr_warned = False

        mock_response = MagicMock()
        mock_response.content = b"fake-pdf-bytes"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_doc = MagicMock()

        with (
            patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client),
            patch("crawl4md.crawler.pymupdf.open", return_value=mock_doc) as mock_open,
            patch(
                "crawl4md.crawler.pymupdf4llm.to_markdown", return_value="# PDF Title\n\nContent"
            ),
        ):
            result = await crawler._download_pdf("https://example.com/doc.pdf")

        assert result.success is True
        assert result.is_pdf is True
        assert result.markdown == "# PDF Title\n\nContent"
        assert result.url == "https://example.com/doc.pdf"
        mock_open.assert_called_once_with(stream=b"fake-pdf-bytes", filetype="pdf")
        mock_doc.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_download_failure(self):
        import httpx

        config = MagicMock()
        config.headers = {}

        crawler = SiteCrawler.__new__(SiteCrawler)
        crawler.config = config
        crawler.page_config = PageConfig(ocr_languages=[])
        crawler._ocr_warned = False

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock(status_code=404)
            )
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_client):
            result = await crawler._download_pdf("https://example.com/missing.pdf")

        assert result.success is False
        assert result.is_pdf is True
        assert "PDF download failed" in result.error

    @pytest.mark.asyncio
    async def test_download_uses_shared_pdf_client(self):
        config = MagicMock()
        config.headers = {"User-Agent": "test"}

        crawler = SiteCrawler.__new__(SiteCrawler)
        crawler.config = config
        crawler.page_config = PageConfig(ocr_languages=[])
        crawler._ocr_warned = False

        mock_response = MagicMock()
        mock_response.content = b"fake-pdf-bytes"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        crawler._pdf_client = mock_client

        mock_doc = MagicMock()

        with (
            patch("crawl4md.crawler.httpx.AsyncClient") as mock_cls,
            patch("crawl4md.crawler.pymupdf.open", return_value=mock_doc) as mock_open,
            patch("crawl4md.crawler.pymupdf4llm.to_markdown", return_value="PDF content"),
        ):
            result = await crawler._download_pdf("https://example.com/doc.pdf")

        assert result.success is True
        assert result.markdown == "PDF content"
        mock_client.get.assert_awaited_once_with("https://example.com/doc.pdf")
        mock_cls.assert_not_called()
        mock_open.assert_called_once_with(stream=b"fake-pdf-bytes", filetype="pdf")

    @patch("crawl4md._internal.final_output._CLEANUP_INTERMEDIATE_FILES", False)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_direct_pdf_empty_extraction_writes_fail_sidecar(self, mock_crawler_cls, tmp_path):
        pdf_url = "https://example.com/empty.pdf"
        mock_browser = AsyncMock()
        mock_browser.__aenter__ = AsyncMock(return_value=mock_browser)
        mock_browser.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_browser

        mock_response = MagicMock()
        mock_response.content = b"fake-pdf-bytes"
        mock_response.raise_for_status = MagicMock()
        mock_pdf_client = AsyncMock()
        mock_pdf_client.get = AsyncMock(return_value=mock_response)
        mock_pdf_client.__aenter__ = AsyncMock(return_value=mock_pdf_client)
        mock_pdf_client.__aexit__ = AsyncMock(return_value=False)
        mock_doc = MagicMock()

        page_config = PageConfig(extract_main_content=False, ocr_languages=[])
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)
        crawler = SiteCrawler(
            CrawlerConfig(urls=[pdf_url], limit=1, max_retries=0, flush_interval=1),
            page_config,
            output_base=tmp_path,
            extractor=extractor,
            writer=writer,
        )

        with (
            patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_pdf_client),
            patch("crawl4md.crawler.pymupdf.open", return_value=mock_doc),
            patch("crawl4md.crawler.pymupdf4llm.to_markdown", return_value="   "),
        ):
            results = crawler.crawl()

        assert crawler.output_dir is not None
        assert results[0].success is False
        assert results[0].error == "No extractable content"
        fail_sidecar = crawler.output_dir / "round_1" / "fail_pages.jsonl"
        assert [entry.url for entry in PageSidecar.iter_index(fail_sidecar)] == [pdf_url]
        final_dir = crawler.output_dir / "final"
        assert (final_dir / "fail_urls.txt").read_text(encoding="utf-8") == pdf_url
        assert pdf_url in next(final_dir.glob("fail_content_*.txt")).read_text(encoding="utf-8")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_direct_pdf_honors_concurrent_delay_start_slot(self, mock_crawler_cls, tmp_path):
        page_url = "https://example.com/page"
        pdf_url = "https://example.com/doc.pdf"
        events: list[tuple[str, str | float]] = []

        async def mock_arun(url, config):
            _ = config
            events.append(("page", url))
            return _make_mock_result(url, "<p>page</p>", "page markdown" * 4)

        async def fake_sleep(seconds: float) -> None:
            events.append(("sleep", seconds))

        async def mock_get(url):
            events.append(("pdf", url))
            mock_response = MagicMock()
            mock_response.content = b"fake-pdf-bytes"
            mock_response.raise_for_status = MagicMock()
            return mock_response

        mock_browser = AsyncMock()
        mock_browser.arun = AsyncMock(side_effect=mock_arun)
        mock_browser.__aenter__ = AsyncMock(return_value=mock_browser)
        mock_browser.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_browser

        mock_pdf_client = AsyncMock()
        mock_pdf_client.get = AsyncMock(side_effect=mock_get)
        mock_pdf_client.__aenter__ = AsyncMock(return_value=mock_pdf_client)
        mock_pdf_client.__aexit__ = AsyncMock(return_value=False)
        mock_doc = MagicMock()

        page_config = PageConfig(extract_main_content=False, ocr_languages=[])
        crawler = SiteCrawler(
            CrawlerConfig(
                urls=[page_url, pdf_url],
                limit=2,
                max_concurrent=2,
                delay=3,
                max_retries=0,
            ),
            page_config,
            output_base=tmp_path,
            extractor=ContentExtractor(page_config),
            writer=FileWriter(max_file_size_mb=15.0),
        )

        with (
            patch("crawl4md.crawler.random.uniform", return_value=1.0),
            patch("crawl4md.crawler.asyncio.sleep", side_effect=fake_sleep),
            patch("crawl4md.crawler.httpx.AsyncClient", return_value=mock_pdf_client),
            patch("crawl4md.crawler.pymupdf.open", return_value=mock_doc),
            patch("crawl4md.crawler.pymupdf4llm.to_markdown", return_value="PDF content"),
        ):
            results = crawler.crawl()

        pdf_start = events.index(("pdf", pdf_url))
        sleeps_before_pdf = [
            event
            for event in events[:pdf_start]
            if event[0] == "sleep" and isinstance(event[1], float) and event[1] > 0
        ]
        assert len(sleeps_before_pdf) >= 2
        assert [result.url for result in results if result.success] == [page_url, pdf_url]

    def test_direct_pdf_retry_delay_uses_retry_jitter(self, tmp_path):
        pdf_url = "https://example.com/retry.pdf"
        config = CrawlerConfig(urls=[pdf_url], delay=5, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path
        crawler._download_pdf = AsyncMock(
            return_value=CrawlResult(
                url=pdf_url,
                markdown="PDF content",
                success=True,
                is_pdf=True,
            )
        )
        progress = ProgressReporter(1, log_dir=tmp_path)
        results: list[CrawlResult] = []

        async def run_direct_pdf_retry() -> None:
            await crawler._handle_direct_pdf_url(
                url=pdf_url,
                results=results,
                generated={pdf_url},
                prior_success=0,
                prior_fail=0,
                queue=[],
                progress=progress,
                round_num=2,
                crawl_depth=1,
                round_dir=None,
                is_retry=True,
            )

        with (
            patch("crawl4md.crawler.random.uniform", return_value=2.0) as mock_uniform,
            patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            asyncio.run(run_direct_pdf_retry())

        progress.close()
        mock_uniform.assert_called_once_with(_JITTER_RETRY_MIN, _JITTER_RETRY_MAX)
        mock_sleep.assert_awaited_once_with(10.0)
        assert [result.url for result in results] == [pdf_url]


# ------------------------------------------------------------------
# Link discovery: .pdf no longer filtered
# ------------------------------------------------------------------


class TestPdfLinkDiscovery:
    def test_extract_links_includes_pdf(self):
        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="/page1">P1</a><a href="/doc.pdf">PDF</a><a href="/report.PDF">PDF2</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        assert "https://example.com/page1" in links
        assert "https://example.com/doc.pdf" in links
        assert "https://example.com/report.PDF" in links


# ------------------------------------------------------------------
# ContentExtractor._extract_pdf_page
# ------------------------------------------------------------------


class TestExtractPdfPage:
    def test_basic_extraction(self):
        result = CrawlResult(
            url="https://example.com/reports/annual_report.pdf",
            markdown="# Annual Report\n\nRevenue increased by 15%.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)

        assert page.url == result.url
        assert "annual report" in page.title.lower()
        assert "Revenue increased" in page.markdown

    def test_title_from_url_with_hyphens(self):
        result = CrawlResult(
            url="https://example.com/my-great-report.pdf",
            markdown="Content here.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert page.title == "my great report"

    def test_title_from_url_with_underscores(self):
        result = CrawlResult(
            url="https://example.com/pdf/Lampiran_A_Panduan.pdf",
            markdown="Content here.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert page.title == "Lampiran A Panduan"

    def test_title_url_encoded(self):
        result = CrawlResult(
            url="https://example.com/my%20report.pdf",
            markdown="Content.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert page.title == "my report"

    def test_title_fallback_to_url(self):
        result = CrawlResult(
            url="https://example.com/.pdf",
            markdown="Content.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        # After stripping .pdf and separators, name is empty → falls back to URL
        assert page.title == result.url

    def test_routing_via_extract_page(self):
        result = CrawlResult(
            url="https://example.com/doc.pdf",
            markdown="# PDF Content\n\nSome text.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_page(result)
        assert "PDF Content" in page.markdown
        assert page.url == result.url

    def test_skips_html_preprocessing(self):
        """Ensure _extract_pdf_page does not run HTML-based preprocessing."""
        result = CrawlResult(
            url="https://example.com/report.pdf",
            html="<nav>should not matter</nav><p>text</p>",
            markdown="# Report\n\nImportant findings.",
            success=True,
            is_pdf=True,
        )
        # Use tag filters that would normally strip content from HTML
        config = PageConfig(exclude_tags=["nav", "p"], include_only_tags=[])
        extractor = ContentExtractor(config)
        page = extractor._extract_page(result)
        # The markdown should be based on the CrawlResult.markdown, not the HTML
        assert "Important findings" in page.markdown

    def test_non_pdf_extension_in_url(self):
        """PDF from dynamic URL uses the full filename for title."""
        result = CrawlResult(
            url="https://example.com/download?id=123",
            markdown="Dynamic PDF content.",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert page.url == result.url
        assert "Dynamic PDF content" in page.markdown

    def test_unicode_line_separators_normalised(self):
        """U+2028/U+2029 from pymupdf4llm are normalised to newlines."""
        result = CrawlResult(
            url="https://example.com/report.pdf",
            markdown="Page one\u2028Page two\u2029Page three",
            success=True,
            is_pdf=True,
        )
        extractor = ContentExtractor()
        page = extractor._extract_pdf_page(result)
        assert "\u2028" not in page.markdown
        assert "\u2029" not in page.markdown
        assert "Page one" in page.markdown
        assert "Page two" in page.markdown
        assert "Page three" in page.markdown


# ------------------------------------------------------------------
# SiteCrawler._pdf_to_markdown — OCR integration
# ------------------------------------------------------------------


class TestPdfToMarkdownOcr:
    """Tests for OCR parameter passing in _pdf_to_markdown."""

    def _make_crawler(self, ocr_languages: list[str] | None = None) -> SiteCrawler:
        crawler = SiteCrawler.__new__(SiteCrawler)
        crawler.page_config = PageConfig(
            ocr_languages=ocr_languages if ocr_languages is not None else ["eng", "msa"]
        )
        crawler._ocr_warned = False
        return crawler

    def test_ocr_params_passed_with_default_languages(self):
        """When ocr_languages is non-empty, use_ocr and ocr_language are passed."""
        crawler = self._make_crawler(["eng", "msa"])
        mock_doc = MagicMock()

        with patch(
            "crawl4md.crawler.pymupdf4llm.to_markdown", return_value="# OCR Result"
        ) as mock_to_md:
            result = crawler._pdf_to_markdown(mock_doc)

        mock_to_md.assert_called_once_with(mock_doc, use_ocr=True, ocr_language="eng+msa")
        assert result == "# OCR Result"

    def test_ocr_params_not_passed_when_empty(self):
        """When ocr_languages is empty, to_markdown is called without OCR kwargs."""
        crawler = self._make_crawler([])
        mock_doc = MagicMock()

        with patch(
            "crawl4md.crawler.pymupdf4llm.to_markdown", return_value="# Plain Result"
        ) as mock_to_md:
            result = crawler._pdf_to_markdown(mock_doc)

        mock_to_md.assert_called_once_with(mock_doc)
        assert result == "# Plain Result"

    def test_multi_language_joined(self):
        """Multiple languages are joined with '+' for Tesseract."""
        crawler = self._make_crawler(["eng", "msa", "chi_sim"])
        mock_doc = MagicMock()

        with patch(
            "crawl4md.crawler.pymupdf4llm.to_markdown", return_value="# Multi"
        ) as mock_to_md:
            crawler._pdf_to_markdown(mock_doc)

        mock_to_md.assert_called_once_with(mock_doc, use_ocr=True, ocr_language="eng+msa+chi_sim")

    def test_single_language(self):
        crawler = self._make_crawler(["eng"])
        mock_doc = MagicMock()

        with patch(
            "crawl4md.crawler.pymupdf4llm.to_markdown", return_value="# Single"
        ) as mock_to_md:
            crawler._pdf_to_markdown(mock_doc)

        mock_to_md.assert_called_once_with(mock_doc, use_ocr=True, ocr_language="eng")

    def test_tesseract_unavailable_warns_and_falls_back(self):
        """RuntimeError from Tesseract triggers a warning and non-OCR fallback."""
        crawler = self._make_crawler(["eng", "msa"])
        mock_doc = MagicMock()

        with (
            patch(
                "crawl4md.crawler.pymupdf4llm.to_markdown",
                side_effect=[RuntimeError("tesseract not found"), "# Fallback"],
            ) as mock_to_md,
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            result = crawler._pdf_to_markdown(mock_doc)

        # First call with OCR, second call without
        assert mock_to_md.call_count == 2
        assert mock_to_md.call_args_list[0] == call(mock_doc, use_ocr=True, ocr_language="eng+msa")
        assert mock_to_md.call_args_list[1] == call(mock_doc)
        assert result == "# Fallback"
        assert crawler._ocr_warned is True
        assert any(_OCR_UNAVAILABLE_WARNING in str(warning.message) for warning in w)

    def test_tesseract_unavailable_emits_structured_warning_event(self):
        """OCR-unavailable also emits a structured crawl_warning progress event."""
        crawler = self._make_crawler(["eng"])
        captured: list[dict] = []
        crawler._progress_callback = captured.append
        mock_doc = MagicMock()

        with (
            patch(
                "crawl4md.crawler.pymupdf4llm.to_markdown",
                side_effect=[RuntimeError("tesseract not found"), "# Fallback"],
            ),
            warnings.catch_warnings(),
        ):
            warnings.simplefilter("always")
            crawler._pdf_to_markdown(mock_doc)

        warning_events = [e for e in captured if e.get("event") == "crawl_warning"]
        assert warning_events
        assert warning_events[0]["code"] == messages.CODE_OCR_UNAVAILABLE
        assert warning_events[0]["severity"] == "warning"

    def test_tesseract_warning_fires_only_once(self):
        """The OCR-unavailable warning should only fire once per crawler instance."""
        crawler = self._make_crawler(["eng"])
        mock_doc = MagicMock()

        with (
            patch(
                "crawl4md.crawler.pymupdf4llm.to_markdown",
                side_effect=[
                    RuntimeError("no tesseract"),
                    "# F1",
                    RuntimeError("no tesseract"),
                    "# F2",
                ],
            ),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            crawler._pdf_to_markdown(mock_doc)
            crawler._pdf_to_markdown(mock_doc)

        ocr_warnings = [x for x in w if _OCR_UNAVAILABLE_WARNING in str(x.message)]
        assert len(ocr_warnings) == 1

    def test_type_error_fallback_for_old_pymupdf4llm(self):
        """TypeError (unknown kwarg) triggers fallback for old pymupdf4llm versions."""
        crawler = self._make_crawler(["eng"])
        mock_doc = MagicMock()

        with (
            patch(
                "crawl4md.crawler.pymupdf4llm.to_markdown",
                side_effect=[TypeError("unexpected keyword argument 'use_ocr'"), "# Old Version"],
            ),
            warnings.catch_warnings(record=True) as w,
        ):
            warnings.simplefilter("always")
            result = crawler._pdf_to_markdown(mock_doc)

        assert result == "# Old Version"
        assert crawler._ocr_warned is True
        assert any(_OCR_UNAVAILABLE_WARNING in str(warning.message) for warning in w)

    def test_file_not_found_fallback(self):
        """FileNotFoundError (Tesseract binary missing) triggers fallback."""
        crawler = self._make_crawler(["eng"])
        mock_doc = MagicMock()

        with patch(
            "crawl4md.crawler.pymupdf4llm.to_markdown",
            side_effect=[FileNotFoundError("tesseract"), "# No Binary"],
        ):
            result = crawler._pdf_to_markdown(mock_doc)

        assert result == "# No Binary"
        assert crawler._ocr_warned is True


# ------------------------------------------------------------------
# PageConfig.ocr_languages validation
# ------------------------------------------------------------------


class TestOcrLanguagesConfig:
    def test_default_value(self):
        config = PageConfig()
        assert config.ocr_languages == ["eng", "msa"]

    def test_csv_string_parsed(self):
        config = PageConfig(ocr_languages="eng, msa, chi_sim")
        assert config.ocr_languages == ["eng", "msa", "chi_sim"]

    def test_list_input(self):
        config = PageConfig(ocr_languages=["eng", "fra"])
        assert config.ocr_languages == ["eng", "fra"]

    def test_empty_list_disables_ocr(self):
        config = PageConfig(ocr_languages=[])
        assert config.ocr_languages == []

    def test_empty_string_disables_ocr(self):
        config = PageConfig(ocr_languages="")
        assert config.ocr_languages == []
