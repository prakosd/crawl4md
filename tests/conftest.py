"""Shared fixtures for crawl4md tests."""

from __future__ import annotations

import pytest

from crawl4md.config import CrawlResult, ExtractedPage

SIMPLE_HTML = """
<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<nav><a href="/">Home</a></nav>
<main>
<h1>Hello World</h1>
<p>This is the main content of the test page.</p>
<p>It has <a href="https://example.com/other">a link</a> and some <strong>bold text</strong>.</p>
</main>
<footer>Copyright 2026</footer>
</body>
</html>
"""

HTML_WITH_LINKS = """
<!DOCTYPE html>
<html>
<head><title>Links Page</title></head>
<body>
<h1>Page with Links</h1>
<a href="/page1">Page 1</a>
<a href="/page2">Page 2</a>
<a href="https://external.com/about">External</a>
<a href="#section">Anchor</a>
</body>
</html>
"""

MINIMAL_HTML = "<html><body><p>Hello</p></body></html>"


@pytest.fixture
def simple_crawl_result() -> CrawlResult:
    return CrawlResult(
        url="https://example.com/test",
        html=SIMPLE_HTML,
        markdown="# Hello World\n\nThis is the main content of the test page.",
        success=True,
    )


@pytest.fixture
def failed_crawl_result() -> CrawlResult:
    return CrawlResult(
        url="https://example.com/fail",
        html="",
        markdown="",
        success=False,
        error="Connection timeout",
    )


@pytest.fixture
def sample_pages() -> list[ExtractedPage]:
    return [
        ExtractedPage(
            url="https://example.com/page1",
            title="Page One",
            markdown="# Page One\n\nContent of page one.",
        ),
        ExtractedPage(
            url="https://example.com/page2",
            title="Page Two",
            markdown="# Page Two\n\nContent of page two.",
        ),
        ExtractedPage(
            url="https://example.com/page3",
            title="Page Three",
            markdown="# Page Three\n\nContent of page three.",
        ),
    ]
