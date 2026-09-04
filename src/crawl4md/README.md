# crawl4md (core library)

The core crawling library: it follows links, extracts the main content of each
page, and writes clean, sorted Markdown. It is synchronous (no `async`/`await`
needed) and usable from a script or any Python backend.

For installation and the full configuration/output reference, see the repo
docs: [INSTALLATION.md](../../docs/INSTALLATION.md), [CONFIGURATION.md](../../docs/CONFIGURATION.md),
and [ARCHITECTURE.md](../../docs/ARCHITECTURE.md).

## Quick start

```python
from crawl4md import SiteCrawler, CrawlerConfig, PageConfig

config = CrawlerConfig(urls=["https://example.com"], limit=20, max_depth=2)
crawler = SiteCrawler(config, PageConfig())
results = crawler.crawl()
crawler.print_summary(results)
```

Output is written to a UTC-timestamped folder; the primary result is
`final/sorted_success_content_*.md`.

Each content file opens with a YAML front-matter block (crawl run metadata) and wraps
every page's human-readable header (title + `*Source: <url>*`) in render-invisible markers
(`<!-- crawl4md:source -->` … `<!-- /crawl4md:source -->`). The markers do not show when the
Markdown is rendered; they let `vector_indexer` recover each page's source and exclude both the
front matter and the header from indexed chunks. The marker strings live in `writer.py` and are
mirrored in `vector_indexer.page_source` with a "keep in sync" note (no cross-library import).

## Module map

| Module | Responsibility |
|---|---|
| `__init__.py` | Public API exports |
| `config.py` | `CrawlerConfig`, `PageConfig` (Pydantic v2) |
| `crawler.py` | `SiteCrawler` — crawl loop, retries, WAF handling, progress/cancel hooks |
| `extractor.py` | `ContentExtractor` — HTML → Markdown (trafilatura / markdownify) |
| `sorter.py` | `ContentSorter` — order pages by URL path |
| `writer.py` | `FileWriter` — size-limited content files + URL lists || `naming.py` | Crawl folder/timestamp names (re-exports `artifact_store.naming`) |
| `progress.py` | `ProgressReporter` — terminal progress |
| `messages.py` | Stable result codes + `classify_crawl_error` (built on `artifact_store.LibraryMessage`) |
| `_internal/` | Implementation details (final output, PDF, DOCX, URL filter, …) |

## Structured messages

User-facing warnings and errors come from the library as data, so any UI can localize
them. A failed page sets `CrawlResult.error_code` (e.g. `crawl.blocked`,
`crawl.empty_content`) next to the free-text `error`. Crawl-level warnings reach the
`progress_callback` as `crawl_warning` events (`{"event": "crawl_warning", "code",
"text", "severity", "params"}`) — for example OCR-unavailable or block back-off. A
fatal crawl exception can be classified with `crawl4md.messages.classify_crawl_error`.
See [docs/BUILDING_ANOTHER_UI.md](../../docs/BUILDING_ANOTHER_UI.md).

## Boundary

The core library must stay usable without the UI: it must not import `streamlit`
or `app_support`, and must not reference app-specific paths. It depends on
`artifact_store` for naming and path safety. Boundary tests enforce this.
