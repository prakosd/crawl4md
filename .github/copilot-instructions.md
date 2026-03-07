# Copilot Instructions — crawl4md

## Project Overview

crawl4md is a Python library for crawling websites and extracting content as Markdown-formatted text files. It wraps Crawl4AI with a synchronous API designed for non-technical Jupyter Notebook users.

## Architecture

- **src layout**: All library code under `src/crawl4md/`.
- **Config models**: Pydantic v2 models in `config.py` — all user-facing parameters are validated here.
- **SiteCrawler**: Synchronous wrapper around Crawl4AI's async crawler. Uses `nest_asyncio` for Jupyter compatibility.
- **ContentExtractor**: Converts crawled HTML to Markdown text using trafilatura (main content) or markdownify (full HTML).
- **FileWriter**: Combines extracted pages into size-limited output files (`.txt` or `.md`, configurable via `PageConfig.output_extension`). Never splits a single page across files.
- **ProgressReporter**: Real-time progress display for Jupyter and terminal.

## Coding Conventions

- Python 3.10+, type hints on all public APIs.
- Pydantic v2 for data models (use `model_validator`, `field_validator`).
- Linting via ruff (config in `pyproject.toml`).
- Tests use pytest with mocked HTTP calls — never make real network requests in tests.
- Keep the notebook UX simple: plain language, no jargon, no code explanations.

## Key Dependencies

| Package | Purpose |
|---|---|
| crawl4ai | Web crawling engine with JS rendering |
| trafilatura | Main content extraction (strip boilerplate) |
| markdownify | Full HTML → Markdown conversion |
| pydantic | Config validation |
| nest-asyncio | Allows asyncio.run() inside Jupyter's event loop |

## File Layout

```
src/crawl4md/
├── __init__.py       # Public API exports
├── config.py         # Pydantic config models
├── crawler.py        # SiteCrawler class
├── extractor.py      # ContentExtractor class
├── writer.py         # FileWriter class
└── progress.py       # ProgressReporter class
```

## Testing

- Some tests (especially in `test_crawler.py`) involve retry rounds with `_ROUND_COOLDOWN` sleeps (default 30s per round). A single test can legitimately take 60+ seconds.
- When running tests, **be patient** — do not assume a test is stuck or retry/re-run it just because it takes a while. Wait for the full output before drawing conclusions.
- If a test is slow due to `_ROUND_COOLDOWN`, the proper fix is to patch it to 0 in the test (e.g. `@patch("crawl4md.crawler._ROUND_COOLDOWN", 0)`) or set `max_retries=0` in the test config — not to re-run the test.
