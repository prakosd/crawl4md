"""Tests for the shared document-download HTTP setup."""

from __future__ import annotations

import ssl

from crawl4md._internal.http_client import (
    document_ssl_context,
    merge_document_headers,
    referer_for_url,
)


def test_merge_document_headers_adds_browser_defaults() -> None:
    headers = merge_document_headers(None)

    assert "Mozilla/" in headers["User-Agent"]  # real browser agent, not python-httpx
    assert headers["Accept"].startswith("application/pdf")
    assert "Accept-Language" in headers


def test_merge_document_headers_lets_config_override_defaults() -> None:
    headers = merge_document_headers({"User-Agent": "custom-agent", "X-Test": "1"})

    assert headers["User-Agent"] == "custom-agent"
    assert headers["X-Test"] == "1"


def test_merge_document_headers_sets_referer_but_config_wins() -> None:
    added = merge_document_headers(None, referer="https://site.example/")
    assert added["Referer"] == "https://site.example/"

    overridden = merge_document_headers(
        {"Referer": "https://other.example/"}, referer="https://site.example/"
    )
    assert overridden["Referer"] == "https://other.example/"


def test_referer_for_url_returns_same_origin() -> None:
    assert (
        referer_for_url("https://www.nrma.com.au/content/dam/x.pdf") == "https://www.nrma.com.au/"
    )
    assert referer_for_url("not-a-url") is None


def test_document_ssl_context_is_a_cached_ssl_context() -> None:
    ctx = document_ssl_context()

    assert isinstance(ctx, ssl.SSLContext)
    assert document_ssl_context() is ctx  # cached: one shared context per process
