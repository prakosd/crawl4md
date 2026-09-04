"""Tests for crawl4md.crawler — core SiteCrawler and WAF detection."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from crawl4md import messages
from crawl4md.config import CrawlerConfig, PageConfig
from crawl4md.crawler import _BLOCK_SIGNATURES, _PROGRESS_EVENT_STATUS, SiteCrawler
from crawl4md.extractor import ContentExtractor
from crawl4md.writer import FileWriter
from tests.conftest import _make_mock_result


def test_run_rounds_sync_uses_worker_loop_when_loop_running() -> None:
    crawler = SiteCrawler(CrawlerConfig(urls=["https://example.com"]))

    class _ImmediateFuture:
        def __init__(self, value: list[str]) -> None:
            self._value = value

        def result(self) -> list[str]:
            return self._value

    class _ImmediateExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def submit(self, fn):
            return _ImmediateFuture(fn())

    running_loop = object()

    with (
        patch("crawl4md.crawler.sys.platform", "linux"),
        patch("crawl4md.crawler.asyncio.get_running_loop", return_value=running_loop),
        patch(
            "crawl4md.crawler.concurrent.futures.ThreadPoolExecutor",
            return_value=_ImmediateExecutor(),
        ) as mock_executor,
        patch.object(crawler, "_run_rounds_in_new_loop", return_value=["ok"]) as mock_runner,
    ):
        assert crawler._run_rounds_sync() == ["ok"]

    mock_executor.assert_called_once_with(max_workers=1)
    mock_runner.assert_called_once_with()


def test_run_rounds_sync_completes_from_within_running_loop() -> None:
    crawler = SiteCrawler(CrawlerConfig(urls=["https://example.com"]))

    async def fake_run_rounds_async() -> list[str]:
        return ["ok"]

    crawler._run_rounds_async = fake_run_rounds_async  # type: ignore[method-assign]

    async def driver() -> list[str]:
        # A loop is already running on this thread, so _run_rounds_sync must
        # offload to a worker thread running _run_rounds_in_new_loop instead of
        # nesting the crawl inside the caller's loop.
        return crawler._run_rounds_sync()

    with patch("crawl4md.crawler.sys.platform", "linux"):
        assert asyncio.run(driver()) == ["ok"]


def test_run_rounds_sync_uses_asyncio_run_without_running_loop() -> None:
    crawler = SiteCrawler(CrawlerConfig(urls=["https://example.com"]))

    async def fake_run_rounds_async() -> list[str]:
        return ["ok"]

    crawler._run_rounds_async = fake_run_rounds_async  # type: ignore[method-assign]

    def fake_asyncio_run(coroutine):
        coroutine.close()
        return ["ok"]

    with (
        patch("crawl4md.crawler.sys.platform", "linux"),
        patch("crawl4md.crawler.asyncio.get_running_loop", side_effect=RuntimeError),
        patch("crawl4md.crawler.asyncio.run", side_effect=fake_asyncio_run) as mock_run,
    ):
        assert crawler._run_rounds_sync() == ["ok"]

    mock_run.assert_called_once()


def test_run_rounds_sync_uses_proactor_worker_on_windows() -> None:
    crawler = SiteCrawler(CrawlerConfig(urls=["https://example.com"]))

    class _ImmediateFuture:
        def __init__(self, value: list[str]) -> None:
            self._value = value

        def result(self) -> list[str]:
            return self._value

    class _ImmediateExecutor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def submit(self, fn):
            return _ImmediateFuture(fn())

    with (
        patch("crawl4md.crawler.sys.platform", "win32"),
        patch(
            "crawl4md.crawler.concurrent.futures.ThreadPoolExecutor",
            return_value=_ImmediateExecutor(),
        ) as mock_executor,
        patch.object(crawler, "_run_rounds_in_proactor_loop", return_value=["ok"]) as mock_runner,
    ):
        assert crawler._run_rounds_sync() == ["ok"]

    mock_executor.assert_called_once_with(max_workers=1)
    mock_runner.assert_called_once_with()


class TestSiteCrawler:
    def test_creates_timestamped_output_dir(self, tmp_path: Path):
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        output_dir = crawler._create_output_dir()

        assert output_dir.exists()
        assert output_dir.parent == tmp_path
        # Matches YYYY-MM-DD_HH-MM-SS
        assert re.match(r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}", output_dir.name)

    def test_build_run_metadata_uses_utc_crawl_start_datetime(self, tmp_path: Path):
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.output_dir = crawler._create_output_dir()

        metadata = crawler._build_run_metadata()

        parsed = datetime.fromisoformat(str(metadata["crawl_start_datetime"]))
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timezone.utc.utcoffset(parsed)

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
        config = CrawlerConfig(urls=["https://example.com"], exclude_paths=[r"/admin"])
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://example.com/admin/settings") is False
        assert crawler._url_allowed("https://example.com/blog") is True

    def test_url_allowed_include_only(self):
        config = CrawlerConfig(urls=["https://example.com"], include_only_paths=[r"/blog"])
        crawler = SiteCrawler(config)
        assert crawler._url_allowed("https://example.com/blog/post1") is True
        assert crawler._url_allowed("https://example.com/about") is False

    def test_url_allowed_uses_cached_regex_patterns(self):
        config = CrawlerConfig(
            urls=["https://example.com"],
            include_only_paths=[r"/blog"],
            exclude_paths=[r"/admin"],
        )
        crawler = SiteCrawler(config)

        with patch("crawl4md.crawler.re.search", side_effect=AssertionError):
            assert crawler._url_allowed("https://example.com/blog/post1") is True
            assert crawler._url_allowed("https://example.com/blog/admin") is False

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
                '<a href="/DependencyHandler.axd?s=abc&amp;t=Css">AXD</a>'
                '<a href="/Service.asmx">ASMX</a>'
                '<a href="/Handler.ashx?id=1">ASHX</a>'
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
        # PDF links are now allowed through for PDF crawling support
        assert "https://example.com/doc.pdf" in links
        assert not any("DependencyHandler.axd" in link for link in links)
        assert "https://example.com/Service.asmx" not in links
        assert not any("Handler.ashx" in link for link in links)

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
    def test_default_static_crawl_remains_serial(self, mock_crawler_cls, tmp_path: Path):
        active_calls = 0
        max_active_calls = 0
        events: list[tuple[str, str]] = []

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_calls, max_active_calls
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            events.append(("start", url))
            await asyncio.sleep(0)
            events.append(("end", url))
            active_calls -= 1
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        urls = ["https://example.com/a", "https://example.com/b"]
        config = CrawlerConfig(urls=urls, limit=2, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)

        crawler.crawl()

        assert max_active_calls == 1
        assert events == [
            ("start", urls[0]),
            ("end", urls[0]),
            ("start", urls[1]),
            ("end", urls[1]),
        ]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_static_urls_run_together(self, mock_crawler_cls, tmp_path: Path):
        active_calls = 0
        max_active_calls = 0
        release: asyncio.Event | None = None

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_calls, max_active_calls, release
            if release is None:
                release = asyncio.Event()
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            if max_active_calls == 3:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            active_calls -= 1
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        urls = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]
        config = CrawlerConfig(urls=urls, limit=3, max_concurrent=3, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)

        results = crawler.crawl()

        assert max_active_calls == 3
        assert mock_instance.arun.await_count == 3
        assert [result.url for result in results if result.success] == urls

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_progress_events_show_active_and_next_urls(
        self, mock_crawler_cls, tmp_path: Path
    ):
        active_calls = 0
        max_active_calls = 0
        release: asyncio.Event | None = None

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_calls, max_active_calls, release
            if release is None:
                release = asyncio.Event()
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            if max_active_calls == 3:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            active_calls -= 1
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict[str, object]] = []

        def collect_event(event: Mapping[str, object]) -> None:
            events.append(dict(event))

        urls = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
            "https://example.com/d",
        ]
        config = CrawlerConfig(urls=urls, limit=4, max_concurrent=3, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=collect_event)

        crawler.crawl()

        status_events = [event for event in events if event.get("event") == _PROGRESS_EVENT_STATUS]
        assert status_events
        full_batch_event = next(
            event for event in status_events if event.get("active_url_count") == 3
        )
        assert full_batch_event["active_urls"] == urls[:3]
        assert full_batch_event["next_url_count"] == 1
        assert full_batch_event["next_urls"] == [urls[3]]

        page_events = [event for event in events if event.get("event") == "page_processed"]
        assert page_events[0]["active_url_count"] == 0
        assert page_events[0]["active_urls"] == []

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_progress_preview_is_capped_for_large_ui_value(
        self, mock_crawler_cls, tmp_path: Path
    ):
        active_calls = 0
        max_active_calls = 0
        release: asyncio.Event | None = None

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_calls, max_active_calls, release
            if release is None:
                release = asyncio.Event()
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            if max_active_calls == 20:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            active_calls -= 1
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict[str, object]] = []

        def collect_event(event: Mapping[str, object]) -> None:
            events.append(dict(event))

        urls = [f"https://example.com/page-{index}" for index in range(25)]
        config = CrawlerConfig(urls=urls, limit=25, max_concurrent=20, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=collect_event)

        crawler.crawl()

        status_events = [event for event in events if event.get("event") == _PROGRESS_EVENT_STATUS]
        large_batch_event = next(
            event for event in status_events if event.get("active_url_count") == 20
        )
        assert large_batch_event["max_concurrent"] == 20
        assert large_batch_event["active_url_count"] == 20
        assert large_batch_event["active_urls"] == urls[:5]
        assert large_batch_event["next_url_count"] == 5
        assert large_batch_event["next_urls"] == urls[20:25]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_one_does_not_emit_active_batch_status(
        self, mock_crawler_cls, tmp_path: Path
    ):
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            side_effect=[
                _make_mock_result("https://example.com/a", "<p>a</p>", "a"),
                _make_mock_result("https://example.com/b", "<p>b</p>", "b"),
            ]
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict[str, object]] = []

        def collect_event(event: Mapping[str, object]) -> None:
            events.append(dict(event))

        urls = ["https://example.com/a", "https://example.com/b"]
        config = CrawlerConfig(urls=urls, limit=2, max_concurrent=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=collect_event)

        crawler.crawl()

        status_events = [event for event in events if event.get("event") == _PROGRESS_EVENT_STATUS]
        assert status_events == []

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_activity_log_records_batch_entry(
        self, mock_crawler_cls, tmp_path: Path
    ):
        active_calls = 0
        max_active_calls = 0
        release: asyncio.Event | None = None

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_calls, max_active_calls, release
            if release is None:
                release = asyncio.Event()
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            if max_active_calls == 3:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            active_calls -= 1
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        urls = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]
        config = CrawlerConfig(urls=urls, limit=3, max_concurrent=3, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)

        crawler.crawl()

        assert crawler.output_dir is not None
        log_text = (crawler.output_dir / "logs" / "activity_log.txt").read_text(encoding="utf-8")
        assert "Reading page batch (3 concurrent)" in log_text

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_prefetched_pages_drain_after_cancel_request(
        self, mock_crawler_cls, tmp_path: Path
    ):
        active_calls = 0
        max_active_calls = 0
        cancel_requested = False
        completed_urls: list[str] = []
        release: asyncio.Event | None = None

        urls = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/c",
        ]

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_calls, max_active_calls, cancel_requested, release
            if release is None:
                release = asyncio.Event()
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            if max_active_calls == len(urls):
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            active_calls -= 1
            completed_urls.append(url)
            if len(completed_urls) == len(urls):
                cancel_requested = True
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=urls, limit=3, max_concurrent=3, max_retries=0)
        crawler = SiteCrawler(
            config,
            output_base=tmp_path,
            should_cancel=lambda: cancel_requested,
        )

        results = crawler.crawl()

        assert max_active_calls == 3
        assert [result.url for result in results if result.success] == urls

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_started_prefetch_drains_after_cancel_during_delay(
        self, mock_crawler_cls, tmp_path: Path
    ):
        urls = ["https://example.com/a", "https://example.com/b"]
        cancel_requested = False
        sleep_calls: list[float] = []

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            return _make_mock_result(url, f"<p>{url}</p>", url)

        async def fake_sleep(seconds: float) -> None:
            nonlocal cancel_requested
            sleep_calls.append(seconds)
            cancel_requested = True

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        page_config = PageConfig(extract_main_content=False)
        config = CrawlerConfig(
            urls=urls,
            limit=2,
            max_concurrent=2,
            delay=3,
            max_retries=0,
        )
        crawler = SiteCrawler(
            config,
            page_config,
            output_base=tmp_path,
            extractor=ContentExtractor(page_config),
            writer=FileWriter(max_file_size_mb=15.0),
            should_cancel=lambda: cancel_requested,
        )

        with (
            patch("crawl4md.crawler.random.uniform", return_value=1.0),
            patch("crawl4md.crawler.asyncio.sleep", side_effect=fake_sleep),
        ):
            results = crawler.crawl()

        assert sleep_calls
        assert mock_instance.arun.await_count == 1
        assert [result.url for result in results if result.success] == [urls[0]]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_static_url_exception_becomes_failure(
        self, mock_crawler_cls, tmp_path: Path
    ):
        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            if url.endswith("/bad"):
                raise RuntimeError("boom")
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        urls = ["https://example.com/good", "https://example.com/bad"]
        config = CrawlerConfig(urls=urls, limit=2, max_concurrent=2, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)

        results = crawler.crawl()

        successes = [result for result in results if result.success]
        failures = [result for result in results if not result.success]
        assert [result.url for result in successes] == ["https://example.com/good"]
        assert len(failures) == 1
        assert failures[0].url == "https://example.com/bad"
        assert failures[0].error == "RuntimeError: boom"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_discovered_same_depth_urls_run_together(
        self, mock_crawler_cls, tmp_path: Path
    ):
        seed_url = "https://example.com"
        child_urls = [
            "https://example.com/b",
            "https://example.com/c",
            "https://example.com/d",
        ]
        seed_html = "".join(f'<a href="/{url.rsplit("/", 1)[-1]}">child</a>' for url in child_urls)
        active_child_calls = 0
        max_active_child_calls = 0
        release: asyncio.Event | None = None

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_child_calls, max_active_child_calls, release
            if url == seed_url:
                return _make_mock_result(seed_url, seed_html, "seed")
            if release is None:
                release = asyncio.Event()
            active_child_calls += 1
            max_active_child_calls = max(max_active_child_calls, active_child_calls)
            if max_active_child_calls == 3:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            active_child_calls -= 1
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[seed_url],
            limit=4,
            max_depth=2,
            max_concurrent=3,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        results = crawler.crawl()

        assert max_active_child_calls == 3
        assert [result.url for result in results if result.success] == [seed_url, *child_urls]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_depth_crawl_waits_until_links_are_discovered(
        self, mock_crawler_cls, tmp_path: Path
    ):
        seed_url = "https://example.com"
        child_urls = ["https://example.com/b", "https://example.com/c"]
        seed_finished = False
        child_started_before_seed_finished = False
        seed_html = '<a href="/b">B</a><a href="/c">C</a>'

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal seed_finished, child_started_before_seed_finished
            if url == seed_url:
                await asyncio.sleep(0)
                seed_finished = True
                return _make_mock_result(seed_url, seed_html, "seed")
            if not seed_finished:
                child_started_before_seed_finished = True
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[seed_url],
            limit=3,
            max_depth=2,
            max_concurrent=2,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        results = crawler.crawl()

        assert child_started_before_seed_finished is False
        assert [result.url for result in results if result.success] == [seed_url, *child_urls]

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_depth_child_exception_becomes_failure(
        self, mock_crawler_cls, tmp_path: Path
    ):
        seed_url = "https://example.com"
        seed_html = '<a href="/good">Good</a><a href="/bad">Bad</a>'

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            if url == seed_url:
                return _make_mock_result(seed_url, seed_html, "seed")
            if url.endswith("/bad"):
                raise RuntimeError("boom")
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[seed_url],
            limit=3,
            max_depth=2,
            max_concurrent=2,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        results = crawler.crawl()

        successes = [result.url for result in results if result.success]
        failures = [result for result in results if not result.success]
        assert successes == [seed_url, "https://example.com/good"]
        assert len(failures) == 1
        assert failures[0].url == "https://example.com/bad"
        assert failures[0].error == "RuntimeError: boom"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_delay_spaces_request_starts(self, mock_crawler_cls, tmp_path: Path):
        seed_url = "https://example.com"
        seed_html = '<a href="/b">B</a><a href="/c">C</a>'
        sleep_calls: list[float] = []

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            if url == seed_url:
                return _make_mock_result(seed_url, seed_html, "seed")
            return _make_mock_result(url, f"<p>{url}</p>", url)

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[seed_url],
            limit=3,
            max_depth=2,
            max_concurrent=2,
            delay=3,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        with (
            patch("crawl4md.crawler.random.uniform", return_value=1.0),
            patch("crawl4md.crawler.asyncio.sleep", side_effect=fake_sleep),
        ):
            crawler.crawl()

        assert any(seconds >= 3 for seconds in sleep_calls)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_delay_spaces_leftover_serial_url(
        self, mock_crawler_cls, tmp_path: Path
    ):
        seed_url = "https://example.com"
        child_urls = [
            "https://example.com/b",
            "https://example.com/c",
            "https://example.com/d",
        ]
        seed_html = '<a href="/b">B</a><a href="/c">C</a><a href="/d">D</a>'
        events: list[tuple[str, str | float]] = []

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            events.append(("start", url))
            if url == seed_url:
                return _make_mock_result(seed_url, seed_html, "seed")
            return _make_mock_result(url, f"<p>{url}</p>", url)

        async def fake_sleep(seconds: float) -> None:
            events.append(("sleep", seconds))

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[seed_url],
            limit=4,
            max_depth=2,
            max_concurrent=2,
            delay=3,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        with (
            patch("crawl4md.crawler.random.uniform", return_value=1.0),
            patch("crawl4md.crawler.asyncio.sleep", side_effect=fake_sleep),
        ):
            crawler.crawl()

        child_c_start = events.index(("start", child_urls[1]))
        child_d_start = events.index(("start", child_urls[2]))
        sleeps_between_child_c_and_d = [
            event
            for event in events[child_c_start + 1 : child_d_start]
            if event[0] == "sleep" and isinstance(event[1], float) and event[1] > 0
        ]
        assert sleeps_between_child_c_and_d

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_delay_still_allows_overlap_for_slow_pages(
        self, mock_crawler_cls, tmp_path: Path
    ):
        seed_url = "https://example.com"
        seed_html = '<a href="/b">B</a><a href="/c">C</a>'
        active_child_calls = 0
        max_active_child_calls = 0
        release: asyncio.Event | None = None

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_child_calls, max_active_child_calls, release
            if url == seed_url:
                return _make_mock_result(seed_url, seed_html, "seed")
            if release is None:
                release = asyncio.Event()
            active_child_calls += 1
            max_active_child_calls = max(max_active_child_calls, active_child_calls)
            if max_active_child_calls == 2:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            active_child_calls -= 1
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[seed_url],
            limit=3,
            max_depth=2,
            max_concurrent=2,
            delay=3,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        with (
            patch("crawl4md.crawler.random.uniform", return_value=0.1),
            patch("crawl4md.crawler.asyncio.sleep", new_callable=AsyncMock),
        ):
            crawler.crawl()

        assert max_active_child_calls == 2

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_max_concurrent_frontier_deduplicates_normalized_urls(
        self, mock_crawler_cls, tmp_path: Path
    ):
        urls = [
            "https://example.com/a",
            "https://example.com/b",
            "https://example.com/a#section",
        ]
        active_calls = 0
        max_active_calls = 0
        release: asyncio.Event | None = None

        async def mock_arun(url, **kwargs):
            _ = kwargs["config"]
            nonlocal active_calls, max_active_calls, release
            if release is None:
                release = asyncio.Event()
            active_calls += 1
            max_active_calls = max(max_active_calls, active_calls)
            if max_active_calls == 2:
                release.set()
            await asyncio.wait_for(release.wait(), timeout=1)
            active_calls -= 1
            return _make_mock_result(url, f"<p>{url}</p>", url)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=mock_arun)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=urls,
            limit=3,
            max_depth=2,
            max_concurrent=3,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)

        results = crawler.crawl()

        assert max_active_calls == 2
        assert mock_instance.arun.await_count == 2
        assert [result.url for result in results if result.success] == urls[:2]

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
        assert (crawler.output_dir / "final" / "success_urls.txt").exists()

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_limit_stops_further_discovery_after_overshoot(self, mock_crawler_cls, tmp_path: Path):
        """Round 1 may overshoot limit in one burst, then processes all discovered pages."""
        seed_url = "https://example.com"
        discovered_count = 23
        discovered_urls = [f"https://example.com/p{i}" for i in range(1, discovered_count + 1)]
        seed_html = "".join(f'<a href="/p{i}">P{i}</a>' for i in range(1, discovered_count + 1))

        side_effects = [_make_mock_result(seed_url, seed_html, "seed")]
        side_effects.extend(
            _make_mock_result(url, "<p>child</p>", "child") for url in discovered_urls
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=side_effects)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=[seed_url], limit=20, max_depth=2, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # Discovery can overshoot in a single burst from a page under the limit.
        # All already-discovered pages are still processed.
        assert len(results) == 1 + discovered_count
        assert mock_instance.arun.await_count == 1 + discovered_count
        assert all(result.success for result in results)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_seed_url_excluded_by_include_only_not_in_discovered(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """Seed URLs that don't match include_only_paths are not added to discovered count."""
        # Two seeds: /blog matches the include filter, /about does not.
        result_blog = _make_mock_result("https://example.com/blog/", "<p>blog</p>", "blog")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=result_blog)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(
            urls=["https://example.com/blog/", "https://example.com/about"],
            include_only_paths=[r"/blog"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        results = crawler.crawl()

        # Only /blog passes the include filter — /about is skipped entirely.
        assert len(results) == 1
        assert results[0].url == "https://example.com/blog/"

        # Discovered count should be 1 (only /blog), not 2.
        page_events = [e for e in events if "queued_discovered_urls" in e]
        assert page_events, "Expected at least one event with queued_discovered_urls"
        max_discovered = max(int(e["queued_discovered_urls"]) for e in page_events)
        assert max_discovered == 1, f"Expected 1 discovered, got {max_discovered}"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_seed_url_excluded_by_exclude_paths_not_in_discovered(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """Seed URLs matching exclude_paths are not added to discovered count."""
        result_page = _make_mock_result("https://example.com/page", "<p>page</p>", "page")
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=result_page)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(
            urls=["https://example.com/page", "https://example.com/admin/settings"],
            exclude_paths=[r"/admin"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        results = crawler.crawl()

        # Only /page passes — /admin/settings is filtered by exclude_paths.
        assert len(results) == 1
        assert results[0].url == "https://example.com/page"

        # Discovered count must not include the excluded seed URL.
        page_events = [e for e in events if "queued_discovered_urls" in e]
        assert page_events, "Expected at least one event with queued_discovered_urls"
        max_discovered = max(int(e["queued_discovered_urls"]) for e in page_events)
        assert max_discovered == 1, f"Expected 1 discovered, got {max_discovered}"

    def test_stealth_enables_browser_and_run_flags(self):
        """Stealth mode sets enable_stealth, simulate_user, override_navigator, magic, scan_full_page."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"], stealth=True)
        crawler = SiteCrawler(config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.simulate_user is True
        assert run_cfg.override_navigator is True
        assert run_cfg.magic is True
        assert run_cfg.scan_full_page is True
        assert run_cfg.scroll_delay == 0.4

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_random_ua_when_stealth(self, mock_crawler_cls, tmp_path: Path):
        """When stealth=True, BrowserConfig gets random user agent mode."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=_make_mock_result("https://example.com"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, stealth=True)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        browser_cfg = (
            mock_crawler_cls.call_args[1].get("config") or mock_crawler_cls.call_args[0][0]
        )
        assert browser_cfg.user_agent_mode == "random"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_headers_passed_to_browser_config(self, mock_crawler_cls, tmp_path: Path):
        """Custom headers are forwarded to BrowserConfig."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=_make_mock_result("https://example.com"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com"], limit=1, headers={"Accept-Language": "en"}
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        browser_cfg = (
            mock_crawler_cls.call_args[1].get("config") or mock_crawler_cls.call_args[0][0]
        )
        assert browser_cfg.headers.get("Accept-Language") == "en"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_one_browser_per_phase_round_one_and_retries(self, mock_crawler_cls, tmp_path: Path):
        """Round 1 and the retry phase each use one browser (two total, not per-round)."""
        blocked_html = "<html><body>Request unsuccessful. Incapsula incident ID: 999</body></html>"
        blocked_result = _make_mock_result("https://example.com/a", blocked_html, "blocked")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=blocked_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/a"], limit=1, max_retries=2)
        crawler = SiteCrawler(config, output_base=tmp_path)
        crawler.crawl()

        # One browser for round 1, one shared across all retry rounds.
        assert mock_crawler_cls.call_count == 2

    def test_js_code_passed_to_run_config(self):
        """js_code from PageConfig is forwarded to CrawlerRunConfig."""
        from crawl4ai import CrawlerRunConfig

        page_config = PageConfig(js_code="document.querySelector('.faq').click()")
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, page_config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.js_code == ["document.querySelector('.faq').click()"]

    def test_timeout_converted_to_milliseconds(self):
        """timeout (seconds) is converted to page_timeout (milliseconds) in CrawlerRunConfig."""
        from crawl4ai import CrawlerRunConfig

        page_config = PageConfig(timeout=15)
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, page_config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.page_timeout == 15000

    def test_flatten_shadow_dom_passed_to_run_config(self):
        """flatten_shadow_dom=True is forwarded to CrawlerRunConfig."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.flatten_shadow_dom is True

    def test_flatten_shadow_dom_false_not_passed(self):
        """flatten_shadow_dom=False is not forwarded (avoids init script injection)."""
        from crawl4ai import CrawlerRunConfig

        page_config = PageConfig(flatten_shadow_dom=False)
        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config, page_config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.flatten_shadow_dom is False

    def test_flatten_shadow_dom_in_fallback_run_config(self):
        """flatten_shadow_dom=True is also forwarded to the fallback CrawlerRunConfig."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config)

        run_cfg = crawler._build_fallback_run_config(CrawlerRunConfig, 2)
        assert run_cfg.flatten_shadow_dom is True

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
            config,
            page_config,
            output_base=tmp_path,
            extractor=extractor,
            writer=writer,
        )
        results = crawler.crawl()

        assert len(results) == 1
        assert len(crawler.content_files) >= 1

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_discovered_equals_processed_on_completion(self, mock_crawler_cls, tmp_path: Path):
        """After crawl completes, discovered count equals processed count."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            return_value=_make_mock_result("https://example.com", "<p>ok</p>", "ok")
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        results = crawler.crawl()

        assert len(results) == 1
        # Simulate Streamlit event merging — final merged state should tally.
        merged: dict = {}
        for e in events:
            merged.update(e)
        assert merged.get("queued_discovered_urls") == merged.get("processed_pages")
        assert int(merged.get("successful_pages", 0)) + int(merged.get("failed_pages", 0)) == int(
            merged.get("processed_pages", 0)
        )

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_already_visited_redirect_removed_from_discovered(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """A queued URL visited via redirect from another page is removed from discovered."""
        # /a redirects to /b; /b is also a separately-seeded URL.
        # /a is processed (redirect result has url=/b); when /b is dequeued it
        # is already in visited — it should be removed from generated so
        # discovered stays equal to processed.
        result_a = _make_mock_result("https://example.com/a", "", "")
        result_a.redirected_url = "https://example.com/b"

        mock_instance = AsyncMock()
        # Only /a is crawled — /b is dequeued but already visited, skipped
        mock_instance.arun = AsyncMock(side_effect=[result_a])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        results = crawler.crawl()

        # Only one result: redirect from /a to /b
        assert len(results) == 1
        assert results[0].url == "https://example.com/b"

        # Simulate how Streamlit merges events (latest_event.update(event)).
        # After the last page event (discovered=2, processed=1) a urls_discovered
        # event fires with discovered=1 — merged state should tally.
        merged: dict = {}
        for e in events:
            merged.update(e)
        assert merged.get("queued_discovered_urls") == merged.get("processed_pages"), (
            f"discovered={merged.get('queued_discovered_urls')} != "
            f"processed={merged.get('processed_pages')}"
        )

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_single_redirect_to_visited_removed_from_discovered(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """URL redirecting to an already-visited page is removed from discovered.

        When exactly one URL redirects to an already-visited target (below the
        storm threshold), _flush_skipped_redirects silently drops it.  The fix
        must discard that URL from ``generated`` so discovered == processed.
        """
        # /b is crawled first (queue order), then /a redirects to /b.
        result_b = _make_mock_result("https://example.com/b", "<p>b</p>", "b")
        result_a = _make_mock_result("https://example.com/a", "", "")
        result_a.redirected_url = "https://example.com/b"

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_b, result_a])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(
            urls=["https://example.com/b", "https://example.com/a"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].url == "https://example.com/b"

        merged: dict = {}
        for e in events:
            merged.update(e)
        assert merged.get("queued_discovered_urls") == merged.get("processed_pages"), (
            f"discovered={merged.get('queued_discovered_urls')} != "
            f"processed={merged.get('processed_pages')}"
        )

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_to_new_target_replaces_source_in_discovered(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """A redirected source URL must not be double-counted in discovered pages."""
        result_a = _make_mock_result("https://example.com/a", "", "")
        result_a.redirected_url = "https://example.com/b"

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(
            urls=["https://example.com/a"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].url == "https://example.com/b"

        merged: dict = {}
        for event in events:
            merged.update(event)
        assert merged.get("queued_discovered_urls") == merged.get("processed_pages")
        assert int(merged.get("successful_pages", 0)) + int(merged.get("failed_pages", 0)) == int(
            merged.get("processed_pages", 0)
        )


class TestIsBlocked:
    """Tests for WAF/bot-protection block detection."""

    def test_detects_all_configured_signatures(self):
        for signature in _BLOCK_SIGNATURES:
            html = f"<html><body>{signature.upper()}</body></html>"
            assert SiteCrawler._is_blocked(html) is True

    def test_detects_incapsula(self):
        html = "<html><body>Request unsuccessful. Incapsula incident ID: 123</body></html>"
        assert SiteCrawler._is_blocked(html) is True

    def test_detects_incapsula_case_insensitive(self):
        html = "<html><body>request unsuccessful. incapsula incident id: 456</body></html>"
        assert SiteCrawler._is_blocked(html) is True

    def test_detects_access_denied(self):
        html = "<html><head><title>Access Denied</title></head><body>blocked</body></html>"
        assert SiteCrawler._is_blocked(html) is True

    def test_ignores_normal_html(self):
        html = "<html><body><p>Normal content</p></body></html>"
        assert SiteCrawler._is_blocked(html) is False

    def test_empty_html_not_blocked(self):
        assert SiteCrawler._is_blocked("") is False

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_real_content_not_blocked(self, mock_crawler_cls, tmp_path: Path):
        """A page that contains a WAF signature but also substantial markdown is not flagged."""
        html = (
            "<html><head><title>Plans</title></head>"
            "<body><noscript>Please turn JavaScript on and reload the page</noscript>"
            "<p>" + "Real content. " * 100 + "</p></body></html>"
        )
        long_markdown = "Real content. " * 100
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
            "<html><head><title>Access Denied</title></head>"
            "<body>Please turn JavaScript on and reload the page</body></html>"
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
        assert results[0].error_code == messages.CODE_BLOCKED

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_nav_chrome_still_blocked(self, mock_crawler_cls, tmp_path: Path):
        """A page with WAF signature whose raw markdown exceeds 500 chars due to
        nav chrome should still be flagged when the *real* content is empty."""
        # Simulate a JS-required page with navigation boilerplate
        nav_text = " ".join(["Nav link"] * 100)  # >500 chars of nav chrome
        html = (
            "<html><head><title>Product PLP/PDP</title></head><body>"
            f"<nav>{nav_text}</nav>"
            "<main><noscript>JavaScript is required</noscript></main>"
            "</body></html>"
        )
        # Crawl4AI raw markdown includes the nav text
        long_nav_markdown = nav_text + "\nJavaScript is required"
        mock_result = _make_mock_result("https://example.com/product", html, long_nav_markdown)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/product"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is False
        assert "Blocked" in (results[0].error or "")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_waf_signature_with_real_main_content_not_blocked(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """A page with a WAF signature but substantial <main> content stays successful."""
        real_content = "Galaxy S26 Ultra specs and pricing. " * 30  # >500 chars of real content
        html = (
            "<html><head><title>Galaxy S26 Ultra</title></head><body>"
            "<nav>Menu Home About</nav>"
            "<noscript>JavaScript is required</noscript>"
            f"<main><p>{real_content}</p></main>"
            "</body></html>"
        )
        mock_result = _make_mock_result("https://example.com/product", html, real_content)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/product"], limit=1)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is True
        assert results[0].error is None

    def test_content_length_without_chrome_strips_nav(self):
        """_content_length_without_chrome ignores nav, header, footer, script, style, form."""
        html = (
            "<html><body>"
            "<nav>Menu Home About Contact Support</nav>"
            "<header>Site Header</header>"
            "<main><p>Real content here</p></main>"
            "<footer>Footer links</footer>"
            "</body></html>"
        )
        length = SiteCrawler._content_length_without_chrome(html)
        assert "Real content here" in html
        # Should only count the <main> content, not nav/header/footer
        assert length < 50
        assert length > 0

    def test_content_length_without_chrome_empty_html(self):
        assert SiteCrawler._content_length_without_chrome("") == 0

    def test_fallback_run_config_disables_scan_and_stealth(self):
        """Fallback config omits scan_full_page and stealth run-flags."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"], stealth=True)
        page_config = PageConfig(scan_full_page=True, timeout=20, js_code="alert(1)")
        crawler = SiteCrawler(config, page_config)

        fallback = crawler._build_fallback_run_config(CrawlerRunConfig, 2)
        assert fallback.scan_full_page is False
        assert fallback.magic is False
        assert fallback.simulate_user is False
        assert fallback.override_navigator is False
        # Non-stealth settings are preserved
        assert fallback.page_timeout == 20000
        assert fallback.js_code == ["alert(1)"]

    def test_fallback_run_config_downgrades_wait_until(self):
        """Fallback config downgrades wait_until to domcontentloaded."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        page_config = PageConfig(wait_until="networkidle")
        crawler = SiteCrawler(config, page_config)

        fallback = crawler._build_fallback_run_config(CrawlerRunConfig, 2)
        assert fallback.wait_until == "domcontentloaded"

    def test_run_config_passes_wait_until(self):
        """wait_until is forwarded to CrawlerRunConfig."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        page_config = PageConfig(wait_until="networkidle")
        crawler = SiteCrawler(config, page_config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.wait_until == "networkidle"

    def test_run_config_default_wait_until(self):
        """Default wait_until is networkidle."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        crawler = SiteCrawler(config)

        run_cfg = crawler._build_run_config(CrawlerRunConfig)
        assert run_cfg.wait_until == "networkidle"

    def test_fallback_preserves_same_base_settings_as_primary(self):
        """Fallback config carries the same excluded_tags, timeout, js_code, wait_for, wait_until."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        page_config = PageConfig(
            exclude_tags="nav, form",
            wait_until="networkidle",
            wait_for=5,
            timeout=30,
            js_code="window.scrollTo(0,0)",
        )
        crawler = SiteCrawler(config, page_config)

        primary = crawler._build_run_config(CrawlerRunConfig)
        fallback = crawler._build_fallback_run_config(CrawlerRunConfig, 2)

        assert fallback.excluded_tags == primary.excluded_tags
        assert fallback.page_timeout == primary.page_timeout
        assert fallback.js_code == primary.js_code
        assert fallback.delay_before_return_html == primary.delay_before_return_html
        # wait_until is intentionally downgraded in fallback
        assert fallback.wait_until == "domcontentloaded"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_retry_rounds_use_fallback_run_config(self, mock_crawler_cls, tmp_path: Path):
        """Retry rounds pass the fallback (reduced) run config, not the primary."""
        # Round 1: page fails; Retry round 2: page succeeds
        fail_result = _make_mock_result("https://example.com")
        fail_result.success = False
        fail_result.error = ""
        fail_result.markdown = ""
        fail_result.html = ""

        ok_result = _make_mock_result("https://example.com")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[fail_result, ok_result])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=1)
        page_config = PageConfig(scan_full_page=True)
        crawler = SiteCrawler(config, page_config, output_base=tmp_path)
        crawler.crawl()

        # arun called twice: once in round 1, once in retry
        assert mock_instance.arun.call_count == 2

        # Round 1 config should have scan_full_page=True
        round1_cfg = mock_instance.arun.call_args_list[0][1].get("config")
        assert round1_cfg.scan_full_page is True

        # Retry config should have scan_full_page=False (fallback)
        retry_cfg = mock_instance.arun.call_args_list[1][1].get("config")
        assert retry_cfg.scan_full_page is False
        assert retry_cfg.magic is False
        assert retry_cfg.wait_until == "domcontentloaded"

    def test_fallback_run_config_always_domcontentloaded(self):
        """Fallback config uses domcontentloaded even when user sets domcontentloaded."""
        from crawl4ai import CrawlerRunConfig

        config = CrawlerConfig(urls=["https://example.com"])
        page_config = PageConfig(wait_until="domcontentloaded")
        crawler = SiteCrawler(config, page_config)

        fallback = crawler._build_fallback_run_config(CrawlerRunConfig, 2)
        assert fallback.wait_until == "domcontentloaded"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_error_includes_status_code(self, mock_crawler_cls, tmp_path: Path):
        """When a page fails, the error message includes the HTTP status code."""
        fail_result = _make_mock_result("https://example.com")
        fail_result.success = False
        fail_result.error = ""
        fail_result.status_code = 403
        fail_result.markdown = ""
        fail_result.html = ""

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=fail_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert "HTTP 403" in (results[0].error or "")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_error_includes_exception_type(self, mock_crawler_cls, tmp_path: Path):
        """When arun raises, the error includes the exception class name."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=RuntimeError("Execution context was destroyed"))
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert results[0].success is False
        assert "RuntimeError" in (results[0].error or "")
        assert "Execution context was destroyed" in (results[0].error or "")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_failed_result_with_empty_error_shows_unknown(self, mock_crawler_cls, tmp_path: Path):
        """A failed result with no error attribute shows 'Unknown error'."""
        fail_result = _make_mock_result("https://example.com")
        fail_result.success = False
        fail_result.error = None
        fail_result.error_message = None
        fail_result.status_code = 0
        fail_result.markdown = ""
        fail_result.html = ""

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=fail_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        assert "Unknown error" in (results[0].error or "")
        assert "HTTP 0" in (results[0].error or "")


class TestNormalizeUrl:
    """Tests for _normalize_url — URL normalization to reduce duplicate crawling."""

    def test_http_to_https(self):
        assert SiteCrawler._normalize_url("http://example.com/page") == "https://example.com/page"

    def test_strips_www(self):
        assert (
            SiteCrawler._normalize_url("https://www.example.com/page") == "https://example.com/page"
        )

    def test_http_and_www_combined(self):
        assert (
            SiteCrawler._normalize_url("http://www.example.com/page") == "https://example.com/page"
        )

    def test_lowercases_host(self):
        assert SiteCrawler._normalize_url("https://Example.COM/Page") == "https://example.com/Page"

    def test_preserves_path_and_query(self):
        url = "https://example.com/a/b?q=1&r=2"
        assert SiteCrawler._normalize_url(url) == url

    def test_strips_fragment(self):
        assert (
            SiteCrawler._normalize_url("https://example.com/page#section")
            == "https://example.com/page"
        )

    def test_idempotent(self):
        url = "https://example.com/page"
        assert SiteCrawler._normalize_url(SiteCrawler._normalize_url(url)) == url

    # -- strip_www=True (explicit) --

    def test_strip_www_true_removes_www(self):
        assert (
            SiteCrawler._normalize_url("https://www.example.com/page", strip_www=True)
            == "https://example.com/page"
        )

    def test_strip_www_true_http_and_www(self):
        assert (
            SiteCrawler._normalize_url("http://www.example.com/page", strip_www=True)
            == "https://example.com/page"
        )

    # -- strip_www=False --

    def test_strip_www_false_preserves_www(self):
        assert (
            SiteCrawler._normalize_url("https://www.example.com/page", strip_www=False)
            == "https://www.example.com/page"
        )

    def test_strip_www_false_http_and_www(self):
        assert (
            SiteCrawler._normalize_url("http://www.example.com/page", strip_www=False)
            == "https://www.example.com/page"
        )

    def test_strip_www_false_no_www_unchanged(self):
        assert (
            SiteCrawler._normalize_url("https://example.com/page", strip_www=False)
            == "https://example.com/page"
        )


class TestExtractBaseDomains:
    """Tests for _extract_base_domains with strip_www flag."""

    def test_strip_www_true_removes_www(self):
        domains = SiteCrawler._extract_base_domains(
            ["https://www.example.com/page"], strip_www=True
        )
        assert domains == {"example.com"}

    def test_strip_www_false_preserves_www(self):
        domains = SiteCrawler._extract_base_domains(
            ["https://www.example.com/page"], strip_www=False
        )
        assert domains == {"www.example.com"}

    def test_strip_www_true_no_www_unchanged(self):
        domains = SiteCrawler._extract_base_domains(["https://example.com/page"], strip_www=True)
        assert domains == {"example.com"}


class TestExtractLinksNormalization:
    """Tests that _extract_links normalizes discovered URLs."""

    def test_extract_links_normalizes_http_and_www(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="http://www.example.com/page1">P1</a>'
                '<a href="https://example.com/page1">P1 dup</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com")
        # Both should normalize to the same URL
        assert links.count("https://example.com/page1") == 1

    def test_extract_links_strip_www_true_deduplicates(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="http://www.example.com/page1">P1</a>'
                '<a href="https://example.com/page1">P1 dup</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com", strip_www=True)
        assert links == ["https://example.com/page1"]

    def test_extract_links_strip_www_false_keeps_both(self):
        from crawl4md.config import CrawlResult

        result = CrawlResult(
            url="https://example.com",
            html=(
                '<a href="http://www.example.com/page1">P1</a>'
                '<a href="https://example.com/page1">P1 dup</a>'
            ),
            success=True,
        )
        links = SiteCrawler._extract_links(result, "https://example.com", strip_www=False)
        assert len(links) == 2
        assert "https://www.example.com/page1" in links
        assert "https://example.com/page1" in links


class TestRedirectDedup:
    """Tests that redirect dedup is logged and does not silently discard."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_to_visited_is_logged(self, mock_crawler_cls, tmp_path: Path):
        """When a redirect targets an already-visited URL, it should be logged."""
        # Page A succeeds normally, Page B redirects to A's normalized URL
        result_a = _make_mock_result("https://example.com/a", "<p>content A</p>", "content A")
        result_a.redirected_url = None

        result_b = _make_mock_result("http://www.example.com/b", "<p>content B</p>", "content B")
        result_b.redirected_url = "https://example.com/a"

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=["https://example.com/a", "http://www.example.com/b"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        # Only page A should be in results — page B's redirect target was already visited
        assert len(results) == 1
        assert results[0].url == "https://example.com/a"

        # Activity log should contain a "Skipped" entry for the redirect
        log_txt = crawler.output_dir / "logs" / "activity_log.txt"
        if log_txt.exists():
            log_content = log_txt.read_text(encoding="utf-8")
            assert "Skipped" in log_content or "skip" in log_content.lower()

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_redirect_outside_filter_removed_from_discovered(
        self, mock_crawler_cls, tmp_path: Path
    ):
        """URL that redirects outside the include filter must not stay in discovered count."""
        result_a = _make_mock_result("https://example.com/a", "<p>content A</p>", "content A")
        result_a.redirected_url = None

        # /b redirects to an external domain (outside the filter)
        result_b = _make_mock_result("https://example.com/b", "", "")
        result_b.redirected_url = "https://other.com/page"

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        results = crawler.crawl()

        # Only page A should succeed
        assert len(results) == 1
        assert results[0].url == "https://example.com/a"

        # The redirect-outside-filter URL must not inflate the discovered count —
        # a urls_discovered event must be emitted after the discard, ending at 1.
        discovered_events = [e for e in events if e.get("event") == "urls_discovered"]
        assert discovered_events, "Expected at least one urls_discovered event after discard"
        final_discovered = discovered_events[-1]["queued_discovered_urls"]
        assert final_discovered == 1, f"Expected 1 discovered (only /a), got {final_discovered}"


class TestRedirectStorm:
    """Tests for anti-bot redirect storm detection."""

    @staticmethod
    def _make_redirect_side_effects(
        target: str,
        source_urls: list[str],
    ) -> list:
        """Create mock arun results where every source redirects to *target*."""
        effects = []
        for src in source_urls:
            r = _make_mock_result(src, "<p>redirect page</p>", "redirect page")
            r.redirected_url = target
            effects.append(r)
        return effects

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_below_threshold_flushed_as_unresolved(self, mock_crawler_cls, tmp_path: Path):
        """Below-threshold redirects appear as unresolved failures at end-of-loop."""
        from crawl4md.crawler import _UNRESOLVED_REDIRECT_ERROR

        target = "https://example.com/home"
        # First page succeeds (populates visited with target)
        result_home = _make_mock_result(target, "<p>home</p>", "home")
        # Two more pages redirect to /home (below threshold of 3)
        redirects = self._make_redirect_side_effects(
            target, ["https://example.com/a", "https://example.com/b"]
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redirects])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[target, "https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert successes[0].url == target
        # The two redirects are flushed as unresolved failures at end-of-loop
        assert len(failures) == 2
        assert all(r.error == _UNRESOLVED_REDIRECT_ERROR for r in failures)
        assert {r.url for r in failures} == {
            "https://example.com/a",
            "https://example.com/b",
        }

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_at_threshold_becomes_failure(self, mock_crawler_cls, tmp_path: Path):
        """After reaching the threshold, all redirect pages become failures.

        p0 and p1 are retroactively converted when p2 triggers the storm;
        p2 and p3 are direct storm failures.
        """
        from crawl4md.crawler import _REDIRECT_STORM_ERROR

        target = "https://example.com/home"
        sources = [f"https://example.com/p{i}" for i in range(4)]

        result_home = _make_mock_result(target, "<p>home</p>", "home")
        redirects = self._make_redirect_side_effects(target, sources)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redirects])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[target, *sources],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 1
        assert successes[0].url == target
        # All 4 redirects become failures (p0/p1 retroactive, p2/p3 direct)
        assert len(failures) == 4
        assert all(r.error == _REDIRECT_STORM_ERROR for r in failures)
        # Failures carry the original URL, not the redirect target
        failure_urls = {r.url for r in failures}
        assert failure_urls == {f"https://example.com/p{i}" for i in range(4)}

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_cancel_during_storm_backoff_emits_interrupted(self, mock_crawler_cls, tmp_path: Path):
        from crawl4md.crawler import _PROGRESS_EVENT_INTERRUPTED

        target = "https://example.com/home"
        sources = [f"https://example.com/p{i}" for i in range(3)]
        expected_crawl_calls = 1 + len(sources)

        result_home = _make_mock_result(target, "<p>home</p>", "home")
        redirects = self._make_redirect_side_effects(target, sources)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redirects])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict[str, object]] = []
        config = CrawlerConfig(
            urls=[target, *sources],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(
            config,
            output_base=tmp_path,
            progress_callback=events.append,
            should_cancel=lambda: mock_instance.arun.call_count >= expected_crawl_calls,
        )

        crawler.crawl()

        assert any(event.get("event") == _PROGRESS_EVENT_INTERRUPTED for event in events)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_progress_closed_when_cancelled_before_first_page(
        self, mock_crawler_cls, tmp_path: Path
    ):
        from crawl4md.progress import ProgressReporter

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock()
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        close_calls: list[ProgressReporter] = []
        original_close = ProgressReporter.close

        def close_spy(progress: ProgressReporter) -> None:
            close_calls.append(progress)
            original_close(progress)

        config = CrawlerConfig(urls=["https://example.com/a"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path, should_cancel=lambda: True)

        with patch("crawl4md.crawler.ProgressReporter.close", autospec=True) as mock_close:
            mock_close.side_effect = close_spy
            crawler.crawl()

        assert close_calls

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_counter_resets_on_successful_crawl(self, mock_crawler_cls, tmp_path: Path):
        """A non-redirect result resets the counter and flushes skipped URLs."""
        from crawl4md.crawler import _UNRESOLVED_REDIRECT_ERROR

        target = "https://example.com/home"
        # Sequence: home, redirect×2, normal_page, redirect×2
        # The normal page resets the counter; both batches of 2 are
        # flushed as unresolved failures (batch 1 on reset, batch 2
        # at end-of-loop).
        result_home = _make_mock_result(target, "<p>home</p>", "home")
        redir_a = self._make_redirect_side_effects(
            target, ["https://example.com/r1", "https://example.com/r2"]
        )
        result_normal = _make_mock_result("https://example.com/good", "<p>good</p>", "good")
        redir_b = self._make_redirect_side_effects(
            target, ["https://example.com/r3", "https://example.com/r4"]
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redir_a, result_normal, *redir_b])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[
                target,
                "https://example.com/r1",
                "https://example.com/r2",
                "https://example.com/good",
                "https://example.com/r3",
                "https://example.com/r4",
            ],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2
        assert {r.url for r in successes} == {target, "https://example.com/good"}
        # All 4 redirects flushed as unresolved failures
        assert len(failures) == 4
        assert all(r.error == _UNRESOLVED_REDIRECT_ERROR for r in failures)
        assert {r.url for r in failures} == {f"https://example.com/r{i}" for i in range(1, 5)}

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_different_targets_flush_on_switch(self, mock_crawler_cls, tmp_path: Path):
        """Redirects to different targets flush prior batch as unresolved."""
        from crawl4md.crawler import _UNRESOLVED_REDIRECT_ERROR

        target_a = "https://example.com/home-a"
        target_b = "https://example.com/home-b"

        result_a = _make_mock_result(target_a, "<p>a</p>", "a")
        result_b = _make_mock_result(target_b, "<p>b</p>", "b")
        # 2 redirects to target_a, then 2 to target_b — neither reaches 3
        redir_a = self._make_redirect_side_effects(
            target_a, ["https://example.com/r1", "https://example.com/r2"]
        )
        redir_b = self._make_redirect_side_effects(
            target_b, ["https://example.com/r3", "https://example.com/r4"]
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_a, result_b, *redir_a, *redir_b])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[
                target_a,
                target_b,
                "https://example.com/r1",
                "https://example.com/r2",
                "https://example.com/r3",
                "https://example.com/r4",
            ],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2
        assert {r.url for r in successes} == {target_a, target_b}
        # r1/r2 flushed on target switch; r3/r4 flushed at end-of-loop
        assert len(failures) == 4
        assert all(r.error == _UNRESOLVED_REDIRECT_ERROR for r in failures)
        assert {r.url for r in failures} == {f"https://example.com/r{i}" for i in range(1, 5)}

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_storm_retroactive_vs_direct_order(self, mock_crawler_cls, tmp_path: Path):
        """Retroactive failures appear before the storm-triggered failure in results."""
        from crawl4md.crawler import _REDIRECT_STORM_ERROR

        target = "https://example.com/home"
        # 3 redirects: p0 and p1 are below threshold, p2 triggers storm
        sources = [f"https://example.com/p{i}" for i in range(3)]
        result_home = _make_mock_result(target, "<p>home</p>", "home")
        redirects = self._make_redirect_side_effects(target, sources)

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(side_effect=[result_home, *redirects])
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[target, *sources],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        failures = [r for r in results if not r.success]
        assert len(failures) == 3
        # Retroactive failures (p0, p1) appear before the direct one (p2)
        assert failures[0].url == "https://example.com/p0"
        assert failures[1].url == "https://example.com/p1"
        assert failures[2].url == "https://example.com/p2"
        assert all(r.error == _REDIRECT_STORM_ERROR for r in failures)

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_mixed_storm_and_unresolved(self, mock_crawler_cls, tmp_path: Path):
        """Storm batch uses STORM error; post-reset batch uses UNRESOLVED error."""
        from crawl4md.crawler import _REDIRECT_STORM_ERROR, _UNRESOLVED_REDIRECT_ERROR

        target = "https://example.com/home"
        # Sequence: home, redirect×3 (storm), normal, redirect×2 (unresolved)
        result_home = _make_mock_result(target, "<p>home</p>", "home")
        storm_batch = self._make_redirect_side_effects(
            target, [f"https://example.com/s{i}" for i in range(3)]
        )
        result_normal = _make_mock_result("https://example.com/good", "<p>good</p>", "good")
        tail_batch = self._make_redirect_side_effects(
            target, ["https://example.com/t0", "https://example.com/t1"]
        )

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            side_effect=[result_home, *storm_batch, result_normal, *tail_batch]
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(
            urls=[
                target,
                "https://example.com/s0",
                "https://example.com/s1",
                "https://example.com/s2",
                "https://example.com/good",
                "https://example.com/t0",
                "https://example.com/t1",
            ],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path)
        results = crawler.crawl()

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        assert len(successes) == 2

        storm_failures = [r for r in failures if r.error == _REDIRECT_STORM_ERROR]
        unresolved_failures = [r for r in failures if r.error == _UNRESOLVED_REDIRECT_ERROR]
        # s0, s1, s2 are storm failures (retroactive + direct)
        assert {r.url for r in storm_failures} == {f"https://example.com/s{i}" for i in range(3)}
        # t0, t1 are unresolved (flushed at end-of-loop)
        assert {r.url for r in unresolved_failures} == {
            "https://example.com/t0",
            "https://example.com/t1",
        }


class TestEmptyExtraction:
    """Tests that empty extraction is treated as failure."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_empty_extraction_demoted_to_failure(self, mock_crawler_cls, tmp_path: Path):
        """When extraction produces empty markdown, the page becomes a failure."""
        # HTML that crawl4ai reports as success, but extraction produces nothing
        html = "<html><head></head><body></body></html>"
        mock_result = _make_mock_result("https://example.com/empty", html, "")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/empty"], limit=1, max_retries=0)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        results = crawler.crawl()

        assert len(results) == 1
        assert results[0].success is False
        assert "No extractable content" in (results[0].error or "")

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_empty_extraction_appears_in_fail_urls(self, mock_crawler_cls, tmp_path: Path):
        """Empty extraction pages should appear in fail_urls.txt."""
        html = "<html><head></head><body></body></html>"
        mock_result = _make_mock_result("https://example.com/empty", html, "")

        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(return_value=mock_result)
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        config = CrawlerConfig(urls=["https://example.com/empty"], limit=1, max_retries=0)
        page_config = PageConfig(extract_main_content=False)
        extractor = ContentExtractor(page_config)
        writer = FileWriter(max_file_size_mb=15.0)

        crawler = SiteCrawler(
            config, page_config, output_base=tmp_path, extractor=extractor, writer=writer
        )
        crawler.crawl()

        fail_urls = crawler.output_dir / "final" / "fail_urls.txt"
        assert fail_urls.exists()
        content = fail_urls.read_text(encoding="utf-8")
        assert "https://example.com/empty" in content


class TestProgressEventFields:
    """Tests for next_url and eta_remaining_seconds in progress events."""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_page_event_has_next_url_and_eta_fields(self, mock_crawler_cls, tmp_path: Path):
        """page_processed events include next_url and eta_remaining_seconds keys."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            return_value=_make_mock_result("https://example.com", "<p>ok</p>", "ok")
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        crawler.crawl()

        page_events = [e for e in events if e.get("event") == "page_processed"]
        assert page_events, "Expected at least one page_processed event"
        for event in page_events:
            assert "next_url" in event
            assert "eta_remaining_seconds" in event

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_next_url_empty_for_last_page(self, mock_crawler_cls, tmp_path: Path):
        """next_url is empty string when the queue is empty (last in-flight page)."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            return_value=_make_mock_result("https://example.com", "<p>ok</p>", "ok")
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        crawler.crawl()

        page_events = [e for e in events if e.get("event") == "page_processed"]
        assert page_events
        # Single-URL crawl: queue is empty when page is processed
        last_page_event = page_events[-1]
        assert last_page_event["next_url"] == ""

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_next_url_is_set_when_more_pages_queued(self, mock_crawler_cls, tmp_path: Path):
        """next_url is populated with the queued URL when there are pages left."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            side_effect=[
                _make_mock_result("https://example.com/a", "<p>a</p>", "a"),
                _make_mock_result("https://example.com/b", "<p>b</p>", "b"),
            ]
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        crawler.crawl()

        page_events = [e for e in events if e.get("event") == "page_processed"]
        assert len(page_events) >= 2
        # After first page, second is still queued
        first_event = page_events[0]
        assert first_event["next_url"] == "https://example.com/b"

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_started_completed_events_have_safe_defaults(self, mock_crawler_cls, tmp_path: Path):
        """crawl_started and crawl_completed events clear URL and ETA status fields."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            return_value=_make_mock_result("https://example.com", "<p>ok</p>", "ok")
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(urls=["https://example.com"], limit=1, max_retries=0)
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        crawler.crawl()

        started = next((e for e in events if e.get("event") == "crawl_started"), None)
        completed = next((e for e in events if e.get("event") == "crawl_completed"), None)

        assert started is not None
        assert started["current_url"] == ""
        assert started["next_url"] == ""
        assert started["eta_remaining_seconds"] is None

        assert completed is not None
        assert completed["current_url"] == ""
        assert completed["next_url"] == ""
        assert completed["eta_remaining_seconds"] is None

    @patch("crawl4md.crawler.AsyncWebCrawler")
    def test_eta_remaining_seconds_is_float_in_page_events(self, mock_crawler_cls, tmp_path: Path):
        """page_processed events have eta_remaining_seconds as float after update() increments count."""
        mock_instance = AsyncMock()
        mock_instance.arun = AsyncMock(
            side_effect=[
                _make_mock_result("https://example.com/a", "<p>a</p>", "a"),
                _make_mock_result("https://example.com/b", "<p>b</p>", "b"),
            ]
        )
        mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
        mock_instance.__aexit__ = AsyncMock(return_value=False)
        mock_crawler_cls.return_value = mock_instance

        events: list[dict] = []
        config = CrawlerConfig(
            urls=["https://example.com/a", "https://example.com/b"],
            limit=10,
            max_retries=0,
        )
        crawler = SiteCrawler(config, output_base=tmp_path, progress_callback=events.append)
        crawler.crawl()

        page_events = [e for e in events if e.get("event") == "page_processed"]
        assert len(page_events) >= 2
        # progress.update() increments count before _emit_page_progress is called,
        # so eta_remaining_seconds() returns a float for all page events.
        for event in page_events:
            assert isinstance(event["eta_remaining_seconds"], float)


@patch("crawl4md.crawler.AsyncWebCrawler")
def test_crawl_emits_lifecycle_logs(
    mock_crawler_cls, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async def mock_arun(url, **kwargs):
        _ = kwargs["config"]
        return _make_mock_result(url, f"<p>{url}</p>", url)

    mock_instance = AsyncMock()
    mock_instance.arun = AsyncMock(side_effect=mock_arun)
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=False)
    mock_crawler_cls.return_value = mock_instance

    config = CrawlerConfig(urls=["https://example.com/a"], limit=1, max_retries=0)
    crawler = SiteCrawler(config, output_base=tmp_path)

    with caplog.at_level(logging.INFO, logger="crawl4md"):
        crawler.crawl()

    logged = [record.getMessage() for record in caplog.records]
    assert any("Crawl started" in message for message in logged)
    assert any("Crawl done" in message for message in logged)
