"""SiteCrawler — synchronous wrapper around Crawl4AI."""

from __future__ import annotations

import asyncio
import concurrent.futures
import random
import re
import sys
from datetime import datetime
from pathlib import Path

import nest_asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from crawl4md.config import CrawlerConfig, CrawlResult, PageConfig
from crawl4md.extractor import ContentExtractor
from crawl4md.progress import ProgressReporter
from crawl4md.writer import FileWriter

# Allow asyncio.run() inside Jupyter's already-running event loop
nest_asyncio.apply()


class SiteCrawler:
    """Crawls websites and collects HTML/Markdown content.

    Provides a synchronous ``crawl()`` method that wraps Crawl4AI's
    asynchronous crawler so non-technical users never see ``async``/``await``.
    """

    def __init__(
        self,
        config: CrawlerConfig,
        page_config: PageConfig | None = None,
        *,
        output_base: Path | str | None = None,
        extractor: ContentExtractor | None = None,
        writer: FileWriter | None = None,
    ) -> None:
        self.config = config
        self.page_config = page_config or PageConfig()
        self._output_base = Path(output_base) if output_base else Path.cwd()
        self.output_dir: Path | None = None
        self._allowed_domains: set[str] = self._extract_base_domains(config.urls)
        self._extractor = extractor
        self._writer = writer
        self.content_files: list[Path] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(self) -> list[CrawlResult]:
        """Crawl the configured URLs and return results.

        Creates a timestamped output folder and writes a ``urls.txt``
        file listing every crawled URL.
        """
        self.output_dir = self._create_output_dir()
        # Attach output_dir to writer so incremental flushes land there
        if self._writer is not None:
            self._writer._output_dir = self.output_dir
        if sys.platform == "win32":
            # Windows Jupyter uses SelectorEventLoop which doesn't support
            # subprocesses needed by Playwright. Run in a ProactorEventLoop
            # on a separate thread.
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                results = pool.submit(self._crawl_in_proactor_loop).result()
        else:
            results = asyncio.run(self._crawl_async())
        self._save_url_list(results)
        # Flush any remaining content and record written files
        if self._writer is not None:
            self.content_files = self._writer.flush()
        return results

    def _crawl_in_proactor_loop(self) -> list[CrawlResult]:
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._crawl_async())
        finally:
            loop.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _crawl_async(self) -> list[CrawlResult]:
        browser_cfg = BrowserConfig(
            headless=True,
            enable_stealth=self.config.stealth,
        )
        run_cfg = self._build_run_config(CrawlerRunConfig)

        results: list[CrawlResult] = []
        visited: set[str] = set()
        # Track every URL ever queued so we can cap at `limit`
        generated: set[str] = set()
        queue: list[tuple[str, int]] = []
        for seed_url in self.config.urls:
            if len(generated) >= self.config.limit:
                break
            generated.add(seed_url)
            queue.append((seed_url, 1))
        progress = ProgressReporter(self.config.limit)

        async with AsyncWebCrawler(config=browser_cfg) as crawler:
            while queue and len(results) < self.config.limit:
                url, depth = queue.pop(0)

                if url in visited:
                    continue
                visited.add(url)

                if not self._url_allowed(url):
                    continue

                try:
                    result = await crawler.arun(url=url, config=run_cfg)

                    # Use the final URL after any redirects
                    final_url = getattr(result, "redirected_url", None) or url
                    redirected = final_url != url

                    # Deduplicate: skip if the redirect target was already visited
                    if redirected and final_url in visited:
                        continue

                    # Mark the final URL as visited so future duplicates are skipped
                    visited.add(final_url)
                    generated.add(final_url)

                    # Filter the final URL against include/exclude rules
                    if redirected and not self._url_allowed(final_url):
                        continue

                    crawl_result = CrawlResult(
                        url=final_url,
                        html=result.html or "",
                        markdown=result.markdown or "",
                        success=result.success,
                        error=None if result.success else str(getattr(result, "error", "")),
                        redirected_url=final_url if redirected else None,
                    )
                except Exception as exc:
                    crawl_result = CrawlResult(
                        url=url,
                        html="",
                        markdown="",
                        success=False,
                        error=str(exc),
                    )

                results.append(crawl_result)
                progress.update(crawl_result.url)

                # Extract and buffer content incrementally
                if crawl_result.success and self._extractor and self._writer:
                    page = self._extractor._extract_page(crawl_result)
                    if page.markdown.strip():
                        self._writer.add(page)

                # Flush urls.txt and content files periodically
                if len(results) % self.config.flush_interval == 0:
                    self._save_url_list(results)
                    if self._writer is not None:
                        self._writer.flush()

                # Throttle between pages to avoid triggering bot detection
                if self.config.delay > 0:
                    jitter = self.config.delay * random.uniform(0.5, 1.5)
                    await asyncio.sleep(jitter)

                # Discover links for deeper crawling
                if depth < self.config.max_depth and crawl_result.success:
                    new_links = self._extract_links(crawl_result, crawl_result.url)
                    for link in new_links:
                        if len(generated) >= self.config.limit:
                            break
                        if link not in generated:
                            generated.add(link)
                            queue.append((link, depth + 1))

        assert self.output_dir is not None
        progress.finish(str(self.output_dir))
        return results

    def _build_run_config(self, run_config_cls: type) -> object:
        """Map PageConfig to a Crawl4AI CrawlerRunConfig."""
        kwargs: dict = {}

        if self.page_config.exclude_tags:
            kwargs["excluded_tags"] = self.page_config.exclude_tags

        if self.page_config.wait_for:
            kwargs["delay_before_return_html"] = self.page_config.wait_for

        if self.page_config.timeout:
            kwargs["page_timeout"] = self.page_config.timeout

        if self.config.stealth:
            kwargs["simulate_user"] = True
            kwargs["override_navigator"] = True
            kwargs["magic"] = True

        return run_config_cls(**kwargs)

    def _url_allowed(self, url: str) -> bool:
        """Check whether a URL passes include/exclude filters."""
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Restrict to the same base domain(s) as the seed URLs
        if self._allowed_domains and not any(
            parsed.netloc == d or parsed.netloc.endswith("." + d)
            for d in self._allowed_domains
        ):
            return False

        # Block boilerplate browser-upgrade domains
        netloc_path = parsed.netloc + parsed.path
        if any(netloc_path.startswith(d) or netloc_path.startswith("www." + d)
               for d in self._BOILERPLATE_DOMAINS):
            return False

        if self.config.include_only_paths and not any(
            re.search(p, url) for p in self.config.include_only_paths
        ):
            return False

        return not (
            self.config.exclude_paths
            and any(re.search(p, url) for p in self.config.exclude_paths)
        )

    # File extensions that are never useful pages to crawl
    _STATIC_ASSET_EXTENSIONS = frozenset((
        ".css", ".js", ".ico", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".webp", ".bmp", ".tiff", ".woff", ".woff2", ".ttf", ".eot",
        ".otf", ".mp3", ".mp4", ".avi", ".mov", ".webm", ".ogg",
        ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z",
        ".xml", ".json", ".rss", ".atom",
    ))

    # Domains that appear as boilerplate "upgrade your browser" links on
    # many websites and are never useful crawl targets.
    _BOILERPLATE_DOMAINS = frozenset((
        "browsehappy.com",
        "google.com",
    ))

    @staticmethod
    def _extract_base_domains(urls: list[str]) -> set[str]:
        """Derive base domains from seed URLs (e.g. 'starhub.com' from 'www.starhub.com')."""
        from urllib.parse import urlparse

        domains: set[str] = set()
        for url in urls:
            netloc = urlparse(url).netloc.lower()
            # Strip www. prefix to get the base domain
            if netloc.startswith("www."):
                netloc = netloc[4:]
            domains.add(netloc)
        return domains

    @staticmethod
    def _extract_links(result: CrawlResult, base_url: str) -> list[str]:
        """Extract absolute http(s) links from crawled HTML."""
        from urllib.parse import urljoin, urlparse

        links: list[str] = []
        for match in re.finditer(r'href=["\']([^"\']+)["\']', result.html):
            href = match.group(1)
            # Skip unresolved template placeholders (e.g. ${var}, {{var}}, {%var%})
            if re.search(r"\$\{|%7B%7B|\{\{|\{%", href):
                continue
            absolute = urljoin(base_url, href)
            if absolute.startswith(("http://", "https://")):
                # Strip fragments
                absolute = absolute.split("#")[0]
                # Skip boilerplate browser-upgrade links
                parsed = urlparse(absolute)
                netloc_path = parsed.netloc + parsed.path
                if any(netloc_path.startswith(d) or netloc_path.startswith("www." + d)
                       for d in SiteCrawler._BOILERPLATE_DOMAINS):
                    continue
                # Skip static asset URLs
                path = parsed.path.lower()
                if any(path.endswith(ext) for ext in SiteCrawler._STATIC_ASSET_EXTENSIONS):
                    continue
                if absolute not in links:
                    links.append(absolute)
        return links

    def _create_output_dir(self) -> Path:
        """Create and return a timestamped output directory."""
        folder_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_dir = self._output_base / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)
        return output_dir

    def _save_url_list(self, results: list[CrawlResult]) -> None:
        """Write urls.txt with one URL per line."""
        assert self.output_dir is not None
        urls_file = self.output_dir / "urls.txt"
        lines = [r.url for r in results]
        urls_file.write_text("\n".join(lines), encoding="utf-8")
