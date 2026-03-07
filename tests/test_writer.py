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

    def test_md_extension_batch(self, tmp_path: Path, sample_pages):
        writer = FileWriter(file_extension=".md")
        files = writer.write(sample_pages, tmp_path)
        assert all(f.suffix == ".md" for f in files)
        assert files[0].name == "content_001.md"

    def test_write_override_extension(self, tmp_path: Path, sample_pages):
        writer = FileWriter(file_extension=".txt")
        files = writer.write(sample_pages, tmp_path, file_extension=".md")
        assert all(f.suffix == ".md" for f in files)

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


class TestFileWriterIncremental:
    """Tests for the incremental add/flush API."""

    def test_add_and_flush_writes_file(self, tmp_path: Path, sample_pages):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0)
        for page in sample_pages:
            writer.add(page)
        files = writer.flush()

        assert len(files) == 1
        assert files[0].name == "content_001.txt"
        content = files[0].read_text(encoding="utf-8")
        assert "https://example.com/page1" in content
        assert "https://example.com/page3" in content

    def test_add_and_flush_md_extension(self, tmp_path: Path, sample_pages):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0, file_extension=".md")
        for page in sample_pages:
            writer.add(page)
        files = writer.flush()

        assert len(files) == 1
        assert files[0].name == "content_001.md"
        assert files[0].suffix == ".md"

    def test_multiple_flushes_append_to_same_file(self, tmp_path: Path):
        """Consecutive flushes write to the same file until size limit."""
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0)

        page1 = ExtractedPage(url="https://example.com/a", markdown="First page")
        page2 = ExtractedPage(url="https://example.com/b", markdown="Second page")

        writer.add(page1)
        files1 = writer.flush()
        assert len(files1) == 1

        writer.add(page2)
        files2 = writer.flush()
        assert len(files2) == 1  # still the same file

        content = files2[0].read_text(encoding="utf-8")
        assert "https://example.com/a" in content
        assert "https://example.com/b" in content

    def test_flush_respects_max_file_size(self, tmp_path: Path):
        """A new file starts when adding a page would exceed the limit."""
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=0.001)
        big_text = "x" * 500
        pages = [
            ExtractedPage(url=f"https://example.com/p{i}", markdown=big_text)
            for i in range(3)
        ]
        for page in pages:
            writer.add(page)
        files = writer.flush()

        assert len(files) > 1
        for f in files:
            assert f.exists()

    def test_flush_creates_new_file_after_size_reached(self, tmp_path: Path):
        """Flushing small pages, then adding more still respects size limit."""
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=0.001)

        page1 = ExtractedPage(url="https://example.com/a", markdown="x" * 500)
        page2 = ExtractedPage(url="https://example.com/b", markdown="y" * 500)

        writer.add(page1)
        writer.flush()

        writer.add(page2)
        files = writer.flush()

        assert len(files) == 2
        assert files[0].name == "content_001.txt"
        assert files[1].name == "content_002.txt"

    def test_oversized_page_gets_own_file(self, tmp_path: Path):
        """A page exceeding max_file_size_mb is written alone."""
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=0.001)
        small = ExtractedPage(url="https://example.com/small", markdown="tiny")
        huge = ExtractedPage(url="https://example.com/huge", markdown="x" * 2000)

        writer.add(small)
        with pytest.warns(UserWarning, match="exceeds"):
            writer.add(huge)
        files = writer.flush()

        assert len(files) >= 2
        # The small and huge pages are in separate files
        contents = [f.read_text(encoding="utf-8") for f in files]
        small_file = [c for c in contents if "https://example.com/small" in c]
        huge_file = [c for c in contents if "https://example.com/huge" in c]
        assert len(small_file) == 1
        assert len(huge_file) == 1

    def test_empty_flush_returns_empty(self, tmp_path: Path):
        writer = FileWriter(output_dir=tmp_path, max_file_size_mb=15.0)
        files = writer.flush()
        assert files == []

    def test_creates_output_dir_if_missing(self, tmp_path: Path):
        out = tmp_path / "sub" / "dir"
        writer = FileWriter(output_dir=out, max_file_size_mb=15.0)
        page = ExtractedPage(url="https://example.com/a", markdown="content")
        writer.add(page)
        files = writer.flush()
        assert out.exists()
        assert len(files) == 1
