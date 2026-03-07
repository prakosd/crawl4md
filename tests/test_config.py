"""Tests for crawl4md.config — Pydantic model validation."""

import pytest

from crawl4md.config import CrawlerConfig, PageConfig


class TestCrawlerConfig:
    def test_valid_single_url(self):
        cfg = CrawlerConfig(urls=["https://example.com"])
        assert cfg.urls == ["https://example.com"]

    def test_valid_multiple_urls(self):
        cfg = CrawlerConfig(urls=["https://a.com", "https://b.com"])
        assert len(cfg.urls) == 2

    def test_urls_from_comma_string(self):
        cfg = CrawlerConfig(urls="https://a.com, https://b.com")
        assert cfg.urls == ["https://a.com", "https://b.com"]

    def test_empty_urls_rejected(self):
        with pytest.raises(ValueError, match="At least one URL"):
            CrawlerConfig(urls=[])

    def test_invalid_url_rejected(self):
        with pytest.raises(ValueError, match="Invalid URL"):
            CrawlerConfig(urls=["not-a-url"])

    def test_defaults(self):
        cfg = CrawlerConfig(urls=["https://example.com"])
        assert cfg.limit == 1
        assert cfg.max_depth == 1
        assert cfg.exclude_paths == []
        assert cfg.include_only_paths == []
        assert cfg.stealth is False

    def test_stealth_enabled(self):
        cfg = CrawlerConfig(urls=["https://example.com"], stealth=True)
        assert cfg.stealth is True

    def test_limit_must_be_positive(self):
        with pytest.raises(ValueError, match="at least 1"):
            CrawlerConfig(urls=["https://example.com"], limit=0)

    def test_max_depth_must_be_positive(self):
        with pytest.raises(ValueError, match="at least 1"):
            CrawlerConfig(urls=["https://example.com"], max_depth=0)

    def test_exclude_paths_from_string(self):
        cfg = CrawlerConfig(
            urls=["https://example.com"], exclude_paths="/admin, /login"
        )
        assert cfg.exclude_paths == ["/admin", "/login"]

    def test_invalid_regex_rejected(self):
        with pytest.raises(ValueError, match="Invalid regex"):
            CrawlerConfig(urls=["https://example.com"], exclude_paths=["[invalid"])

    def test_include_only_paths_validated(self):
        cfg = CrawlerConfig(
            urls=["https://example.com"],
            include_only_paths=[r"/blog/.*"],
        )
        assert cfg.include_only_paths == [r"/blog/.*"]

    def test_max_retries_default(self):
        cfg = CrawlerConfig(urls=["https://example.com"])
        assert cfg.max_retries == 2

    def test_max_retries_zero_allowed(self):
        cfg = CrawlerConfig(urls=["https://example.com"], max_retries=0)
        assert cfg.max_retries == 0

    def test_max_retries_negative_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            CrawlerConfig(urls=["https://example.com"], max_retries=-1)


class TestPageConfig:
    def test_defaults(self):
        cfg = PageConfig()
        assert cfg.exclude_tags == ["nav", "script", "form", "style"]
        assert cfg.include_only_tags == []
        assert cfg.wait_for is None
        assert cfg.timeout == 30000
        assert cfg.max_file_size_mb == 15.0
        assert cfg.extract_main_content is True

    def test_exclude_tags_from_string(self):
        cfg = PageConfig(exclude_tags="nav, footer", include_only_tags=[])
        assert cfg.exclude_tags == ["nav", "footer"]

    def test_tag_conflict_rejected(self):
        with pytest.raises(ValueError, match="Cannot set both"):
            PageConfig(exclude_tags=["nav"], include_only_tags=["main"])

    def test_include_only_tags_clears_default_exclude(self):
        cfg = PageConfig(exclude_tags=[], include_only_tags=["main", "article"])
        assert cfg.include_only_tags == ["main", "article"]
        assert cfg.exclude_tags == []

    def test_negative_timeout_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            PageConfig(timeout=-1)

    def test_zero_file_size_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            PageConfig(max_file_size_mb=0)

    def test_output_extension_default(self):
        cfg = PageConfig()
        assert cfg.output_extension == ".txt"

    def test_output_extension_md(self):
        cfg = PageConfig(output_extension=".md")
        assert cfg.output_extension == ".md"

    def test_output_extension_invalid_rejected(self):
        with pytest.raises(ValueError):
            PageConfig(output_extension=".html")
