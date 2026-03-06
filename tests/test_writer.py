"""Tests for crawl4md.writer — FileWriter."""

from __future__ import annotations

from pathlib import Path

import pytest

from crawl4md.config import ExtractedPage
from crawl4md.writer import FileWriter


class TestFileWriter:
    def test_writes_single_file(self, tmp_path: Path, sample_pages):
        writer = FileWriter()
        files = writer.write(sample_pages, tmp_path, max_file_size_mb=15.0)

        assert len(files) == 1
        assert files[0].name == "content_001.txt"
        content = files[0].read_text(encoding="utf-8")
        assert "https://example.com/page1" in content
        assert "https://example.com/page2" in content
        assert "https://example.com/page3" in content

    def test_file_contains_url_headers(self, tmp_path: Path, sample_pages):
        writer = FileWriter()
        files = writer.write(sample_pages, tmp_path)
        content = files[0].read_text(encoding="utf-8")

        assert "URL: https://example.com/page1" in content
        assert "Title: Page One" in content

    def test_file_contains_separators(self, tmp_path: Path, sample_pages):
        writer = FileWriter()
        files = writer.write(sample_pages, tmp_path)
        content = files[0].read_text(encoding="utf-8")

        assert "=" * 80 in content

    def test_splits_at_size_limit(self, tmp_path: Path):
        """Produces multiple files when content exceeds max size."""
        big_text = "x" * 500
        pages = [
            ExtractedPage(url=f"https://example.com/p{i}", markdown=big_text)
            for i in range(5)
        ]
        writer = FileWriter()
        # Tiny limit forces splitting
        files = writer.write(pages, tmp_path, max_file_size_mb=0.001)

        assert len(files) > 1
        for f in files:
            assert f.exists()

    def test_never_splits_single_page(self, tmp_path: Path):
        """A single page that exceeds the limit gets its own file."""
        big_page = ExtractedPage(
            url="https://example.com/huge",
            markdown="x" * 2000,
        )
        small_page = ExtractedPage(
            url="https://example.com/small",
            markdown="tiny",
        )
        writer = FileWriter()
        with pytest.warns(UserWarning, match="exceeds"):
            files = writer.write([big_page, small_page], tmp_path, max_file_size_mb=0.001)

        # Big page should be alone in its file
        assert len(files) == 2
        big_content = files[0].read_text(encoding="utf-8")
        assert "https://example.com/huge" in big_content
        assert "https://example.com/small" not in big_content

    def test_naming_scheme(self, tmp_path: Path, sample_pages):
        writer = FileWriter()
        files = writer.write(sample_pages, tmp_path)
        assert all(f.name.startswith("content_") for f in files)
        assert all(f.suffix == ".txt" for f in files)

    def test_empty_pages_produces_no_files(self, tmp_path: Path):
        writer = FileWriter()
        files = writer.write([], tmp_path)
        assert files == []

    def test_creates_output_dir_if_missing(self, tmp_path: Path, sample_pages):
        out = tmp_path / "sub" / "dir"
        writer = FileWriter()
        files = writer.write(sample_pages, out)
        assert out.exists()
        assert len(files) == 1
