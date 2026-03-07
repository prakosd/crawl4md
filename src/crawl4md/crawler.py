"""SiteCrawler — synchronous wrapper around Crawl4AI."""

from __future__ import annotations

import asyncio
import concurrent.futures
import random
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import nest_asyncio
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

from crawl4md.config import CrawlerConfig, CrawlResult, ExtractedPage, PageConfig
from crawl4md.extractor import ContentExtractor
from crawl4md.progress import ProgressReporter
from crawl4md.sorter import ContentSorter
from crawl4md.writer import FileWriter

# Allow asyncio.run() inside Jupyter's already-running event loop
nest_asyncio.apply()

# Seconds to pause between retry rounds so the WAF can cool down
_ROUND_COOLDOWN = 30

# Known WAF / bot-protection block signatures (matched case-insensitively)
_BLOCK_SIGNATURES = (
    "incapsula incident",
    "access denied</title>",
    "attention required! | cloudflare",
    "please turn javascript on and reload the page",
    "checking your browser before accessing",
    "javascript is required",
)

# If the extracted markdown exceeds this length (in characters), the page
# contains real content and should not be classified as a WAF block even
# when a block signature is present in the raw HTML.
_BLOCK_MAX_CONTENT_LENGTH = 500


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
        # Internal writer for failed-page content (symmetrical with _writer)
        self._fail_writer: FileWriter | None = None
        if writer is not None:
            self._fail_writer = FileWriter(
                max_file_size_mb=self.page_config.max_file_size_mb,
                file_extension=writer._file_extension,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def crawl(self) -> list[CrawlResult]:
        """Crawl the configured URLs and return results.

        Creates a timestamped output folder.  Runs multiple rounds:
        round 1 crawls seed URLs; subsequent rounds retry blocked/failed
        URLs up to ``max_retries`` times.  Each round writes per-round
        files (``round_N_*``).  After all rounds, final merged files
        are produced (``final_success_content_*.ext``,
        ``final_success_urls.txt``, ``final_fail_urls.txt``).
        """
        self.output_dir = self._create_output_dir()
        # Attach output_dir to writer so incremental flushes land there
        if self._writer is not None:
            self._writer._output_dir = self.output_dir
        if self._fail_writer is not None:
            self._fail_writer._output_dir = self.output_dir
        if sys.platform == "win32":
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                all_results = pool.submit(self._run_rounds_in_proactor_loop).result()
        else:
            all_results = asyncio.run(self._run_rounds_async())
        return all_results

    def _run_rounds_in_proactor_loop(self) -> list[CrawlResult]:
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._run_rounds_async())
        finally:
            loop.close()

    # ------------------------------------------------------------------
    # Round orchestration
    # ------------------------------------------------------------------

    async def _run_rounds_async(self) -> list[CrawlResult]:
        """Run the initial crawl + retry rounds, producing per-round and final files."""
        all_success: list[CrawlResult] = []
        all_fail: list[CrawlResult] = []
        all_content_files: list[Path] = []
        all_fail_content_files: list[Path] = []
        total_rounds = 1 + self.config.max_retries  # round 1 + retries

        browser_cfg = BrowserConfig(
            headless=True,
            enable_stealth=self.config.stealth,
        )
        run_cfg = self._build_run_config(CrawlerRunConfig)

        # --- Round 1: full crawl with link discovery ---
        round_prefix = "round_1_"
        if self._writer is not None:
            self._writer.reset(f"{round_prefix}success_")
        if self._fail_writer is not None:
            self._fail_writer.reset(f"{round_prefix}fail_")
        print(f"--- Round 1/{total_rounds}: Crawling {len(self.config.urls)} seed URL(s) ---")
        round_results = await self._crawl_urls_async(
            urls=self.config.urls,
            browser_cfg=browser_cfg,
            run_cfg=run_cfg,
            discover_links=True,
            round_prefix=round_prefix,
            prior_success=0,
            prior_fail=0,
        )
        success, fail = self._split_results(round_results)
        self._save_url_lists(success, fail, round_prefix)
        if self._writer is not None:
            round_files = self._writer.flush()
            all_content_files.extend(round_files)
        if self._fail_writer is not None:
            fail_files = self._fail_writer.flush()
            all_fail_content_files.extend(fail_files)
        all_success.extend(success)
        all_fail.extend(fail)

        # --- Retry rounds ---
        failed_urls = [r.url for r in all_fail]
        for retry_num in range(1, self.config.max_retries + 1):
            if not failed_urls:
                print(f"\nAll pages succeeded — skipping remaining retries.")
                break

            round_num = retry_num + 1
            round_prefix = f"round_{round_num}_"
            if self._writer is not None:
                self._writer.reset(f"{round_prefix}success_")
            if self._fail_writer is not None:
                self._fail_writer.reset(f"{round_prefix}fail_")

            print(f"\n--- Round {round_num}/{total_rounds}: Retrying {len(failed_urls)} failed URL(s) (waiting {_ROUND_COOLDOWN}s cooldown) ---")
            await asyncio.sleep(_ROUND_COOLDOWN)

            round_results = await self._crawl_urls_async(
                urls=failed_urls,
                browser_cfg=browser_cfg,
                run_cfg=run_cfg,
                discover_links=False,
                round_prefix=round_prefix,
                prior_success=len(all_success),
                prior_fail=len(all_fail),
            )
            success, fail = self._split_results(round_results)
            self._save_url_lists(success, fail, round_prefix)
            if self._writer is not None:
                round_files = self._writer.flush()
                all_content_files.extend(round_files)
            if self._fail_writer is not None:
                fail_files = self._fail_writer.flush()
                all_fail_content_files.extend(fail_files)
            all_success.extend(success)
            all_fail = [r for r in all_fail if r.url not in {s.url for s in success}]
            all_fail.extend(fail)
            failed_urls = [r.url for r in fail]

        # --- Final merged files ---
        remaining_fail_urls = [r.url for r in all_fail]
        self._write_final_files(all_success, remaining_fail_urls, all_content_files, all_fail_content_files)

        # --- Sorted final files (grouped by URL path) ---
        self._write_sorted_files(all_success, all_fail)
        self.content_files = self._get_final_content_files()

        total_crawled = len(all_success) + len(all_fail)
        print(f"\nDone! {len(all_success)} succeeded, {len(all_fail)} failed out of {total_crawled} total.")
        assert self.output_dir is not None
        print(f"Output folder: {self.output_dir}")

        # Return all results (success + remaining failures) for API consumers
        return all_success + all_fail

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _crawl_urls_async(
        self,
        urls: list[str],
        browser_cfg: BrowserConfig,
        run_cfg: object,
        *,
        discover_links: bool = True,
        round_prefix: str = "",
        prior_success: int = 0,
        prior_fail: int = 0,
    ) -> list[CrawlResult]:
        """Crawl a list of URLs and return per-page results.

        When *discover_links* is True (round 1), follow links up to
        ``max_depth``.  When False (retry rounds), only crawl the
        given URLs with no link discovery.
        """
        results: list[CrawlResult] = []
        visited: set[str] = set()
        generated: set[str] = set()
        queue: list[tuple[str, int]] = []
        for seed_url in urls:
            if len(generated) >= self.config.limit:
                break
            generated.add(seed_url)
            queue.append((seed_url, 1))
        progress = ProgressReporter(
            min(len(urls), self.config.limit),
            prior_success=prior_success,
            prior_fail=prior_fail,
        )

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

                    if redirected and final_url in visited:
                        continue

                    visited.add(final_url)
                    generated.add(final_url)

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

                # Detect WAF blocks (Incapsula etc. return HTTP 200 with block HTML).
                # Only flag as blocked when the extracted markdown is short —
                # pages with substantial content are not mere challenge pages.
                raw_markdown = crawl_result.markdown
                if (
                    crawl_result.success
                    and self._is_blocked(crawl_result.html)
                    and len(raw_markdown.strip()) < _BLOCK_MAX_CONTENT_LENGTH
                ):
                    crawl_result.success = False
                    crawl_result.error = "Blocked by WAF"
                    crawl_result.markdown = ""

                results.append(crawl_result)
                progress.update(crawl_result.url, success=crawl_result.success)

                # Extract and buffer content incrementally
                if crawl_result.success and self._extractor and self._writer:
                    page = self._extractor._extract_page(crawl_result)
                    if page.markdown.strip():
                        self._writer.add(page)

                # Buffer failed-page content for the fail content file
                if not crawl_result.success and self._fail_writer is not None:
                    raw_body = raw_markdown.strip() or crawl_result.html.strip() or "(no response)"
                    fail_page = ExtractedPage(
                        url=crawl_result.url,
                        title=f"FAILED — {crawl_result.error or 'Unknown error'}",
                        markdown=(
                            f"**Error:** {crawl_result.error or 'Unknown error'}\n\n"
                            f"**Raw response:**\n\n{raw_body}"
                        ),
                    )
                    self._fail_writer.add(fail_page)

                # Flush content and URL lists periodically
                if len(results) % self.config.flush_interval == 0:
                    if self._writer is not None:
                        self._writer.flush()
                    if self._fail_writer is not None:
                        self._fail_writer.flush()
                    success, fail = self._split_results(results)
                    self._save_url_lists(success, fail, round_prefix)

                # Throttle between pages — wide jitter mimics human browsing
                if self.config.delay > 0:
                    jitter = self.config.delay * random.uniform(0.3, 3.0)
                    await asyncio.sleep(jitter)

                # Discover links for deeper crawling (only in round 1)
                if discover_links and depth < self.config.max_depth and crawl_result.success:
                    new_links = self._extract_links(crawl_result, crawl_result.url)
                    for link in new_links:
                        if len(generated) >= self.config.limit:
                            break
                        if link not in generated:
                            generated.add(link)
                            queue.append((link, depth + 1))
                    # Update progress total to reflect discovered pages
                    progress.total = min(len(generated), self.config.limit)

        return results

    # ------------------------------------------------------------------
    # Block detection
    # ------------------------------------------------------------------

    @staticmethod
    def _is_blocked(html: str) -> bool:
        """Return True if the HTML looks like a WAF/bot-protection block page."""
        if not html:
            return False
        html_lower = html.lower()
        return any(sig in html_lower for sig in _BLOCK_SIGNATURES)

    # ------------------------------------------------------------------
    # Result helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_results(results: list[CrawlResult]) -> tuple[list[CrawlResult], list[CrawlResult]]:
        """Split results into (success, fail) lists."""
        success = [r for r in results if r.success]
        fail = [r for r in results if not r.success]
        return success, fail

    def _save_url_lists(
        self,
        success: list[CrawlResult],
        fail: list[CrawlResult],
        prefix: str = "",
    ) -> None:
        """Write per-round success and fail URL lists."""
        assert self.output_dir is not None
        if success:
            path = self.output_dir / f"{prefix}success_urls.txt"
            path.write_text("\n".join(r.url for r in success), encoding="utf-8")
        if fail:
            path = self.output_dir / f"{prefix}fail_urls.txt"
            path.write_text("\n".join(r.url for r in fail), encoding="utf-8")

    def _write_final_files(
        self,
        all_success: list[CrawlResult],
        remaining_fail_urls: list[str],
        all_content_files: list[Path],
        all_fail_content_files: list[Path] | None = None,
    ) -> None:
        """Produce final merged output files."""
        assert self.output_dir is not None

        # final_success_urls.txt — all successful URLs across all rounds
        if all_success:
            path = self.output_dir / "final_success_urls.txt"
            path.write_text("\n".join(r.url for r in all_success), encoding="utf-8")

        # final_fail_urls.txt — URLs that still failed after all retries
        if remaining_fail_urls:
            path = self.output_dir / "final_fail_urls.txt"
            path.write_text("\n".join(remaining_fail_urls), encoding="utf-8")

        # Merge per-round content → final_success_content_001.ext, …
        if all_content_files:
            ext = self.page_config.output_extension
            final_index = 1
            for src in all_content_files:
                dst = self.output_dir / f"final_success_content_{final_index:03d}{ext}"
                shutil.copy2(src, dst)
                final_index += 1

        # Merge per-round fail content → final_fail_content_001.ext, …
        if all_fail_content_files:
            ext = self.page_config.output_extension
            final_index = 1
            for src in all_fail_content_files:
                dst = self.output_dir / f"final_fail_content_{final_index:03d}{ext}"
                shutil.copy2(src, dst)
                final_index += 1

    def _write_sorted_files(
        self,
        all_success: list[CrawlResult],
        all_fail: list[CrawlResult],
    ) -> None:
        """Re-extract, sort by URL path, and write sorted final files."""
        if self._writer is None:
            return
        assert self.output_dir is not None
        ext = self.page_config.output_extension

        # Sorted success content
        if all_success and self._extractor is not None:
            pages = [
                self._extractor._extract_page(r)
                for r in all_success
                if r.markdown.strip()
            ]
            pages = [p for p in pages if p.markdown.strip()]
            sorted_pages = ContentSorter.sort(pages)
            if sorted_pages:
                w = FileWriter(
                    output_dir=self.output_dir,
                    max_file_size_mb=self.page_config.max_file_size_mb,
                    file_extension=ext,
                    prefix="sorted_final_success_",
                )
                for page in sorted_pages:
                    w.add(page)
                w.flush()
                # Sorted success URLs
                path = self.output_dir / "sorted_final_success_urls.txt"
                path.write_text(
                    "\n".join(p.url for p in sorted_pages),
                    encoding="utf-8",
                )

        # Sorted fail content
        if all_fail:
            fail_pages = []
            for r in all_fail:
                raw_body = r.markdown.strip() or r.html.strip() or "(no response)"
                fail_pages.append(ExtractedPage(
                    url=r.url,
                    title=f"FAILED — {r.error or 'Unknown error'}",
                    markdown=(
                        f"**Error:** {r.error or 'Unknown error'}\n\n"
                        f"**Raw response:**\n\n{raw_body}"
                    ),
                ))
            sorted_fail = ContentSorter.sort(fail_pages)
            if sorted_fail:
                w = FileWriter(
                    output_dir=self.output_dir,
                    max_file_size_mb=self.page_config.max_file_size_mb,
                    file_extension=ext,
                    prefix="sorted_final_fail_",
                )
                for page in sorted_fail:
                    w.add(page)
                w.flush()
                # Sorted fail URLs
                path = self.output_dir / "sorted_final_fail_urls.txt"
                path.write_text(
                    "\n".join(p.url for p in sorted_fail),
                    encoding="utf-8",
                )

    def _get_final_content_files(self) -> list[Path]:
        """Return sorted list of final content files (prefers sorted versions)."""
        assert self.output_dir is not None
        sorted_pattern = f"sorted_final_success_content_*{self.page_config.output_extension}"
        sorted_files = sorted(self.output_dir.glob(sorted_pattern))
        if sorted_files:
            return sorted_files
        # Fall back to unsorted final files when sorting produced nothing
        pattern = f"final_success_content_*{self.page_config.output_extension}"
        return sorted(self.output_dir.glob(pattern))

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
        """Write urls.txt with one URL per line (legacy, kept for compatibility)."""
        assert self.output_dir is not None
        urls_file = self.output_dir / "urls.txt"
        lines = [r.url for r in results]
        urls_file.write_text("\n".join(lines), encoding="utf-8")
