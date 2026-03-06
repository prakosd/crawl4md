"""Tests for crawl4md.crawler — SiteCrawler (mocked)."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from crawl4md.config import CrawlerConfig, ExtractedPage
from crawl4md.crawler import SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter


def _make_mock_result(url: str, html: str = "<p>hello</p>", markdown: str = "hello"):
    """Create a mock crawl4ai result object."""
    result = MagicMock()
    result.url = url
    result.html = html
    result.markdown = markdown
    result.success = True
    return result


class TestSiteCrawler:
    def test_creates_timestamped_output_dir(self, tmp_path: Path):
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        output_dir = crawler._create_output_dir()

        assert output_dir.exists()
        assert output_dir.parent == tmp_path
        # Matches YYYY-MM-DD_HH-MM-SS
        assert re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", output_dir.name)

    def test_url_allowed_no_filters(self):
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://example.com/any") is True

    def test_url_allowed_rejects_external_domain(self):
        config = CrawlerConfig(urls=["https://www.starhub.com/personal/support.html"])
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://www.starhub.com/personal/page") is True
        assert crawler._url_allowed("https://starhub.com/other") is True
        assert crawler._url_allowed("https://sub.starhub.com/page") is True
        assert crawler._url_allowed("https://otherdomain.com/page") is False

    def test_url_allowed_exclude(self):
        config = CrawlerConfig(
            urls=["https://example.com"], exclude_paths=[r"/admin"]
        )
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://example.com/admin/settings") is False
        assert crawler._url_allowed("https://example.com/blog") is True

    def test_url_allowed_include_only(self):
        config = CrawlerConfig(
            urls=["https://example.com"], include_only_paths=[r"/blog"]
        )
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://example.com/blog/post1") is True
        assert crawler._url_allowed("https://example.com/about") is False

    def test_extract_links(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html='<a href="/page1">P1</a> <a href="https://other.com">O</a> <a href="#frag">F</a>',
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        assert "https://example.com/page1" in links
        assert "https://other.com" in links
        # Fragment-only links are resolved to the base URL
        assert all(not link.endswith("#frag") for link in links)

    def test_extract_links_skips_static_assets(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="/page1">P1</a>'
                '<a href="/style.css">CSS</a>'
                '<a href="/favicon.ico">ICO</a>'
                '<a href="/app.js">JS</a>'
                '<a href="/image.png">PNG</a>'
                '<a href="/font.woff2">WOFF2</a>'
                '<a href="/doc.pdf">PDF</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        assert "https://example.com/page1" in links
        assert "https://example.com/style.css" not in links
        assert "https://example.com/favicon.ico" not in links
        assert "https://example.com/app.js" not in links
        assert "https://example.com/image.png" not in links
        assert "https://example.com/font.woff2" not in links
        assert "https://example.com/doc.pdf" not in links

    def test_extract_links_skips_template_placeholders(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="/page1">P1</a>'
                '<a href="https://example.com/${offer_url}">Offer</a>'
                '<a href="https://example.com/${msa_link}">MSA</a>'
                '<a href="https://example.com/{{slug}}">Slug</a>'
                '<a href="https://example.com/{%url%}">Django</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        assert "https://example.com/page1" in links
        assert len(links) == 1  # Only the real link survives

    def test_save_url_list(self, tmp_path: Path):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        results = [
            CrawlResult(url="https://example.com/a", success=True),
            CrawlResult(url="https://example.com/b", success=True),
        ]
        crawler._save_url_list(results)

        urls_file = tmp_path / "urls.txt"
        assert urls_file.exists()
        lines = urls_file.read_text(encoding="utf-8").splitlines()
        assert lines == ["https://example.com/a", "https://example.com/b"]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_crawl_single_page(self, mock_crawler_cls, tmp_path: Path):
        """Test that crawl() returns results and creates output."""
        mock_result = _make_mock_result("https://example.com", "<p>hi</p>", "hi")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].url == "https://example.com"
        assert results[0].success is True
        assert crawler.output_dir is not None
        assert (crawler.output_dir / "urls.txt").exists()

    def test_stealth_enables_browser_and_run_flags(self):
        """Stealth mode sets enable_stealth, simulate_user, override_navigator, magic."""
        from crawl4ai import BrowserConfig, CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"], stealth=True)
        crawler = SiteCrawler(config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.simulate_user is True
        assert run_cfg.override_navigator is True
        assert run_cfg.magic is True

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_crawl_with_extractor_and_writer(self, mock_crawler_cls, tmp_path: Path):
        """Content files are written incrementally when extractor/writer are provided."""
        html = "<html><head><title>Test</title></head><body><p>Hello world</p></body></html>"
        mock_result = _make_mock_result("https://example.com", html, "Hello world")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        from crawl4md.config import PageConfig

        config = CrawlerConfig(urls=["https://example.com"], limit=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path,
            extractor=extractor, writer=writer,
        )
        results = crawler.crawl()

        assert len(results) == 1
        assert len(crawler.content_files) >= 1
        content = crawler.content_files[0].read_text(encoding="utf-8")
        assert "https://example.com" in content
