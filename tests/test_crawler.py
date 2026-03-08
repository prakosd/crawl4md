"""Tests for crawl4md.crawler — SiteCrawler (mocked)."""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from crawl4md.config import CrawlerConfig, ExtractedPage
from crawl4md.crawler import SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter


def _make_mock_result(url: str, html: str = "<p>hello</p>", markdown: str = "hello", *, redirected_url: str | None = None):
    """Create a mock crawl4ai result object."""
    result = MagicMock()
    result.url = url
    result.html = html
    result.markdown = markdown
    result.success = True
    result.redirected_url = redirected_url
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
        assert (crawler.output_dir / "final_success_urls.txt").exists()

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


class TestIsBlocked:
    """Tests for WAF/bot-protection block detection."""

    def test_detects_incapsula(self):
        html = '<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>'
        assert SiteCrawler._is_blocked(html) is True

    def test_detects_incapsula_case_insensitive(self):
        html = '<html><body>request unsuccessful. incapsula incident id: 456</body></html>'
        assert SiteCrawler._is_blocked(html) is True

    def test_detects_access_denied(self):
        html = '<html><head><title>Access Denied</title></head><body>blocked</body></html>'
        assert SiteCrawler._is_blocked(html) is True

    def test_ignores_normal_html(self):
        html = '<html><body><p>Normal content</p></body></html>'
        assert SiteCrawler._is_blocked(html) is False

    def test_empty_html_not_blocked(self):
        assert SiteCrawler._is_blocked("") is False

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_real_content_not_blocked(self, mock_crawler_cls, tmp_path: Path):
        """A page that contains a WAF signature but also substantial markdown is not flagged."""
        html = (
            '<html><head><title>Plans</title></head>'
            '<body><noscript>Please turn JavaScript on and reload the page</noscript>'
            '<p>' + 'Real content. ' * 100 + '</p></body></html>'
        )
        long_markdown = 'Real content. ' * 100
        mock_result = _make_mock_result("https://example.com", html, long_markdown)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is True
        assert results[0].error is None

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_short_content_is_blocked(self, mock_crawler_cls, tmp_path: Path):
        """A page that contains a WAF signature and only short markdown is flagged as blocked."""
        html = (
            '<html><head><title>Access Denied</title></head>'
            '<body>Please turn JavaScript on and reload the page</body></html>'
        )
        mock_result = _make_mock_result("https://example.com", html, "Access Denied")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is False
        assert results[0].error == "Blocked by WAF"


class TestSaveUrlLists:
    """Tests for per-round URL list splitting."""

    def test_splits_success_and_fail(self, tmp_path: Path):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        success = [CrawlResult(url="https://example.com/a", success=True)]
        fail = [CrawlResult(url="https://example.com/b", success=False, error="Blocked")]
        crawler._save_url_lists(success, fail, "round_1_")

        assert (tmp_path / "round_1_success_urls.txt").read_text(encoding="utf-8") == "https://example.com/a"
        assert (tmp_path / "round_1_fail_urls.txt").read_text(encoding="utf-8") == "https://example.com/b"

    def test_no_fail_file_when_all_succeed(self, tmp_path: Path):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        success = [CrawlResult(url="https://example.com/a", success=True)]
        crawler._save_url_lists(success, [], "round_1_")

        assert (tmp_path / "round_1_success_urls.txt").exists()
        assert not (tmp_path / "round_1_fail_urls.txt").exists()


class TestRetryRounds:
    """Tests for the multi-round crawl with retries."""

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retries_blocked_pages(self, mock_crawler_cls, tmp_path: Path):
        """Blocked pages in round 1 are retried in round 2."""
        blocked_html = '<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>'
        ok_result = _make_mock_result("https://example.com/ok", "<p>good</p>", "good")
        blocked_result = _make_mock_result("https://example.com/blocked", blocked_html, "blocked")
        # Round 2: the previously-blocked page now succeeds
        retry_ok_result = _make_mock_result("https://example.com/blocked", "<p>now ok</p>", "now ok")

        call_count = {"n": 0}
        async def mock_arun(url, config):
            call_count["n"] += 1
            if url == "https://example.com/ok":
                return ok_result
            # First call for /blocked returns block, second returns ok
            if url == "https://example.com/blocked":
                if call_count["n"] <= 2:
                    return blocked_result
                return retry_ok_result
            return ok_result

        mock_instance = AsyncMock()
        mock_instance.arun = mock_arun
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/ok", "https://example.com/blocked"],
            limit=10, max_retries=1,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert crawler.output_dir is not None
        # Round 1 files
        assert (crawler.output_dir / "round_1_success_urls.txt").exists()
        assert (crawler.output_dir / "round_1_fail_urls.txt").exists()
        # Round 2 files
        assert (crawler.output_dir / "round_2_success_urls.txt").exists()
        # Final files
        assert (crawler.output_dir / "final_success_urls.txt").exists()
        # All pages should succeed after retry
        success = [r for r in results if r.success]
        assert len(success) == 2

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_skips_retries_when_all_succeed(self, mock_crawler_cls, tmp_path: Path):
        """No retry rounds when everything succeeds in round 1."""
        ok_result = _make_mock_result("https://example.com/a", "<p>ok</p>", "ok")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/a"],
            limit=10, max_retries=2,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert crawler.output_dir is not None
        # Round 1 exists
        assert (crawler.output_dir / "round_1_success_urls.txt").exists()
        # Round 2 should NOT exist (early exit)
        assert not (crawler.output_dir / "round_2_success_urls.txt").exists()
        assert not (crawler.output_dir / "round_2_fail_urls.txt").exists()
        # Final success
        assert (crawler.output_dir / "final_success_urls.txt").exists()
        assert not (crawler.output_dir / "final_fail_urls.txt").exists()

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_retries_zero_no_retries(self, mock_crawler_cls, tmp_path: Path):
        """max_retries=0 means no retry rounds."""
        blocked_html = '<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>'
        blocked_result = _make_mock_result("https://example.com/x", blocked_html, "blocked")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/x"],
            limit=10, max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert crawler.output_dir is not None
        # Only round 1
        assert (crawler.output_dir / "round_1_fail_urls.txt").exists()
        assert not (crawler.output_dir / "round_2_fail_urls.txt").exists()
        # Final fail
        assert (crawler.output_dir / "final_fail_urls.txt").exists()
        assert not (crawler.output_dir / "final_success_urls.txt").exists()
        # No content files since everything was blocked
        assert len(crawler.content_files) == 0

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_updates_result_url(self, mock_crawler_cls, tmp_path: Path):
        """CrawlResult.url should be the final URL after a redirect."""
        mock_result = _make_mock_result(
            "https://example.com/old",
            redirected_url="https://example.com/new",
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/old"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].url == "https://example.com/new"
        assert results[0].redirected_url == "https://example.com/new"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_deduplicates_when_both_urls_are_seeds(self, mock_crawler_cls, tmp_path: Path):
        """Seeding both the original and redirect target should produce one result."""
        original = "https://example.com/old"
        target = "https://example.com/new"

        mock_result_redirect = _make_mock_result(original, redirected_url=target)
        mock_result_direct = _make_mock_result(target)

        mock_instance = AsyncMock()
        # First call: /old redirects to /new. Second call: /new (direct).
        mock_instance.arun = AsyncMock(side_effect=[mock_result_redirect, mock_result_direct])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[original, target], limit=10)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # Only one result — the second seed is skipped because /new is already visited
        assert len(results) == 1
        assert results[0].url == target
        # arun should be called only once (the second URL is skipped before crawling)
        assert mock_instance.arun.call_count == 1

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_deduplicates_reverse_order(self, mock_crawler_cls, tmp_path: Path):
        """If the target is crawled first, the redirecting URL is still deduplicated."""
        original = "https://example.com/old"
        target = "https://example.com/new"

        mock_result_direct = _make_mock_result(target)
        mock_result_redirect = _make_mock_result(original, redirected_url=target)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[mock_result_direct, mock_result_redirect])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[target, original], limit=10)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # Two arun calls happen (we can't know /old redirects until we crawl it),
        # but only one result is kept since /new is already visited
        assert len(results) == 1
        assert results[0].url == target

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_links_resolved_against_final_url(self, mock_crawler_cls, tmp_path: Path):
        """Links discovered on a redirected page should resolve against the final URL."""
        html = '<a href="sibling">Link</a>'
        mock_result = _make_mock_result(
            "https://example.com/old",
            html=html,
            redirected_url="https://example.com/section/new",
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/old"], limit=1, max_depth=2)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        # The relative link "sibling" should resolve against /section/new
        urls_file = (crawler.output_dir / "final_success_urls.txt").read_text(encoding="utf-8")
        assert "https://example.com/section/new" in urls_file

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_to_disallowed_path_is_skipped(self, mock_crawler_cls, tmp_path: Path):
        """A redirect landing outside include_only_paths should be skipped."""
        mock_result = _make_mock_result(
            "https://example.com/blog/post",
            redirected_url="https://example.com/enterprise/page",
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/blog/post"],
            include_only_paths=["/blog"],
            limit=1,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # The redirect target is outside /blog, so it should be skipped
        assert len(results) == 0


class TestFailContentFiles:
    """Tests for fail content file generation (symmetrical with success content)."""

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fail_content_file_created_for_blocked_page(self, mock_crawler_cls, tmp_path: Path):
        """Blocked pages produce a fail content file with error and raw response."""
        blocked_html = '<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>'
        blocked_result = _make_mock_result("https://example.com/blocked", blocked_html, "blocked page text")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        from crawl4md.config import PageConfig

        config = CrawlerConfig(urls=["https://example.com/blocked"], limit=1, max_retries=0, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(config, page_config, output_base=tmp_path, extractor=extractor, writer=writer)
        crawler.crawl()

        assert crawler.output_dir is not None
        # Per-round fail content file
        fail_files = list(crawler.output_dir.glob("round_1_fail_content_*.txt"))
        assert len(fail_files) >= 1
        content = fail_files[0].read_text(encoding="utf-8")
        assert "https://example.com/blocked" in content
        assert "Blocked by WAF" in content
        assert "blocked page text" in content  # raw response preserved

        # Final merged fail content file
        final_fail = list(crawler.output_dir.glob("final_fail_content_*.txt"))
        assert len(final_fail) >= 1

    @patch("crawl4ml.crawler._ROUND_COOLDOWN", 0) if False else patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fail_content_includes_error_and_raw_markdown(self, mock_crawler_cls, tmp_path: Path):
        """Fail content contains both the error reason and the raw markdown response."""
        blocked_html = '<html><body>Access Denied</title></body></html>'
        blocked_result = _make_mock_result("https://example.com/denied", blocked_html, "access denied markdown")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        from crawl4md.config import PageConfig

        config = CrawlerConfig(urls=["https://example.com/denied"], limit=1, max_retries=0, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(config, page_config, output_base=tmp_path, extractor=extractor, writer=writer)
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("round_1_fail_content_*.txt"))
        assert len(fail_files) >= 1
        content = fail_files[0].read_text(encoding="utf-8")
        assert "**Error:** Blocked by WAF" in content
        assert "**Raw response:**" in content
        assert "access denied markdown" in content

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_no_fail_content_when_all_succeed(self, mock_crawler_cls, tmp_path: Path):
        """No fail content files are created when all pages succeed."""
        ok_result = _make_mock_result("https://example.com/ok", "<p>ok</p>", "ok content")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=ok_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        from crawl4md.config import PageConfig

        config = CrawlerConfig(urls=["https://example.com/ok"], limit=1, max_retries=0, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(config, page_config, output_base=tmp_path, extractor=extractor, writer=writer)
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("*fail_content*"))
        assert len(fail_files) == 0

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fail_content_not_created_without_writer(self, mock_crawler_cls, tmp_path: Path):
        """No fail content files when no writer is provided."""
        blocked_html = '<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>'
        blocked_result = _make_mock_result("https://example.com/x", blocked_html, "blocked")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/x"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        assert crawler.output_dir is not None
        fail_files = list(crawler.output_dir.glob("*fail_content*"))
        assert len(fail_files) == 0


class TestPrintSummary:
    """Tests for SiteCrawler.print_summary()."""

    def test_prints_success_and_fail_counts(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        results = [
            CrawlResult(url="https://example.com/a", success=True),
            CrawlResult(url="https://example.com/b", success=False, error="fail"),
        ]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "1 succeeded" in out
        assert "1 failed" in out
        assert str(tmp_path) in out

    def test_prints_round_files(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        # Create dummy round files
        (tmp_path / "round_1_success_content_001.md").write_text("x" * 100, encoding="utf-8")
        (tmp_path / "round_1_success_urls.txt").write_text("https://example.com/a", encoding="utf-8")

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "--- Round 1 ---" in out
        assert "round_1_success_content_001.md" in out

    def test_prints_sorted_files(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        (tmp_path / "sorted_final_success_content_001.md").write_text("data", encoding="utf-8")
        (tmp_path / "sorted_final_success_urls.txt").write_text("url", encoding="utf-8")

        results = [CrawlResult(url="https://example.com/a", success=True)]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "Sorted by URL path" in out
        assert "sorted_final_success_content_001.md" in out

    def test_prints_fail_hint(self, tmp_path: Path, capsys):
        from crawl4md.config import CrawlResult

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = tmp_path

        results = [
            CrawlResult(url="https://example.com/a", success=False, error="blocked"),
            CrawlResult(url="https://example.com/b", success=False, error="blocked"),
        ]
        crawler.print_summary(results)
        out = capsys.readouterr().out
        assert "2 URL(s) that could not be crawled" in out

    def test_no_output_dir_shows_message(self, capsys):
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config)
        crawler.output_dir = None

        crawler.print_summary([])
        out = capsys.readouterr().out
        assert "No output folder found" in out

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_fail_content_merged_across_rounds(self, mock_crawler_cls, tmp_path: Path):
        """Fail content from multiple rounds is merged into final fail_content files."""
        blocked_html = '<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>'
        blocked_result = _make_mock_result("https://example.com/stuck", blocked_html, "still blocked")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        from crawl4md.config import PageConfig

        config = CrawlerConfig(urls=["https://example.com/stuck"], limit=1, max_retries=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(config, page_config, output_base=tmp_path, extractor=extractor, writer=writer)
        crawler.crawl()

        assert crawler.output_dir is not None
        # Per-round fail content files from both rounds
        round1_fail = list(crawler.output_dir.glob("round_1_fail_content_*.txt"))
        round2_fail = list(crawler.output_dir.glob("round_2_fail_content_*.txt"))
        assert len(round1_fail) >= 1
        assert len(round2_fail) >= 1
        # Final merged fail content
        final_fail = list(crawler.output_dir.glob("final_fail_content_*.txt"))
        assert len(final_fail) >= 1

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retry_skips_already_succeeded_url(self, mock_crawler_cls, tmp_path: Path):
        """A retry round should not re-crawl a URL that already succeeded."""
        url_a = "https://example.com/a"
        url_b = "https://example.com/b"

        # Round 1: A succeeds, B is blocked
        result_a = _make_mock_result(url_a)
        blocked_html = '<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>'
        result_b_blocked = _make_mock_result(url_b, html=blocked_html, markdown="blocked")

        # Round 2: B is retried, but redirects to A (already succeeded)
        result_b_redirect = _make_mock_result(url_b, redirected_url=url_a)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b_blocked, result_b_redirect])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[url_a, url_b], limit=10, max_retries=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # A should appear only once in the success results
        success_urls = [r.url for r in results if r.success]
        assert success_urls.count(url_a) == 1

    @patch("crawl4md.crawler._ROUND_COOLDOWN", 0)
    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_final_sorted_files_no_duplicates(self, mock_crawler_cls, tmp_path: Path):
        """Sorted final URL files should contain no duplicate URLs."""
        url_a = "https://example.com/a"
        url_b = "https://example.com/b"

        # Round 1: A succeeds, B is blocked
        result_a = _make_mock_result(url_a)
        blocked_html = '<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>'
        result_b_blocked = _make_mock_result(url_b, html=blocked_html, markdown="blocked")

        # Round 2: B succeeds
        result_b_ok = _make_mock_result(url_b)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b_blocked, result_b_ok])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        from crawl4md.config import PageConfig

        config = CrawlerConfig(urls=[url_a, url_b], limit=10, max_retries=1, flush_interval=1)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(config, page_config, output_base=tmp_path, extractor=extractor, writer=writer)
        crawler.crawl()

        assert crawler.output_dir is not None

        # Check sorted final success URLs have no duplicates
        sorted_urls_path = crawler.output_dir / "sorted_final_success_urls.txt"
        if sorted_urls_path.exists():
            urls = sorted_urls_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(urls) == len(set(urls)), f"Duplicate URLs found: {[u for u in urls if urls.count(u) > 1]}"

        # Check final success URLs have no duplicates
        final_urls_path = crawler.output_dir / "final_success_urls.txt"
        if final_urls_path.exists():
            urls = final_urls_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(urls) == len(set(urls)), f"Duplicate URLs found: {[u for u in urls if urls.count(u) > 1]}"

        # Check final fail URLs have no duplicates (if any)
        final_fail_path = crawler.output_dir / "final_fail_urls.txt"
        if final_fail_path.exists():
            urls = final_fail_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(urls) == len(set(urls)), f"Duplicate fail URLs found: {[u for u in urls if urls.count(u) > 1]}"
