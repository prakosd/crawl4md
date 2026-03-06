"""Configuration models for crawl4md."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, field_validator, model_validator


class CrawlerConfig(BaseModel):
    """Configuration for the web crawler."""

    urls: list[str]
    exclude_paths: list[str] = []
    include_only_paths: list[str] = []
    limit: int = 1
    max_depth: int = 1
    flush_interval: int = 10

    @field_validator("urls", mode="before")
    @classmethod
    def parse_urls(cls, v: Any) -> list[str]:
        """Accept a comma-separated string or a list of URLs."""
        if isinstance(v, str):
            v = [u.strip() for u in v.split(",") if u.strip()]
        return v

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("At least one URL is required.")
        for url in v:
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"Invalid URL (must start with http:// or https://): {url}")
        return v

    @field_validator("exclude_paths", "include_only_paths", mode="before")
    @classmethod
    def parse_path_patterns(cls, v: Any) -> list[str]:
        """Accept a comma-separated string or a list of patterns."""
        if isinstance(v, str):
            v = [p.strip() for p in v.split(",") if p.strip()]
        return v

    @field_validator("exclude_paths", "include_only_paths")
    @classmethod
    def validate_regex_patterns(cls, v: list[str]) -> list[str]:
        for pattern in v:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern '{pattern}': {e}") from e
        return v

    @field_validator("limit", "max_depth", "flush_interval")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Value must be at least 1.")
        return v


class PageConfig(BaseModel):
    """Configuration for page extraction."""

    exclude_tags: list[str] = ["nav", "script", "form", "style"]
    include_only_tags: list[str] = []
    wait_for: float | None = None
    timeout: int = 30000
    max_file_size_mb: float = 15.0
    extract_main_content: bool = True

    @field_validator("exclude_tags", "include_only_tags", mode="before")
    @classmethod
    def parse_tags(cls, v: Any) -> list[str]:
        """Accept a comma-separated string or a list of tag names."""
        if isinstance(v, str):
            v = [t.strip() for t in v.split(",") if t.strip()]
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Timeout must be non-negative.")
        return v

    @field_validator("max_file_size_mb")
    @classmethod
    def validate_max_file_size(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Max file size must be positive.")
        return v

    @model_validator(mode="after")
    def check_tag_conflict(self) -> PageConfig:
        if self.exclude_tags and self.include_only_tags:
            raise ValueError(
                "Cannot set both 'exclude_tags' and 'include_only_tags'. Use one or the other."
            )
        return self


class CrawlResult(BaseModel):
    """Result of crawling a single page."""

    url: str
    html: str = ""
    markdown: str = ""
    success: bool = True
    error: str | None = None


class ExtractedPage(BaseModel):
    """A single page after content extraction."""

    url: str
    title: str = ""
    markdown: str = ""
