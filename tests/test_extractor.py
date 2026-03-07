"""Tests for crawl4md.extractor — ContentExtractor."""

from __future__ import annotations

from unittest.mock import patch

from crawl4md.config import CrawlResult, PageConfig
from crawl4md.extractor import ContentExtractor
from tests.conftest import MINIMAL_HTML, SIMPLE_HTML


class TestContentExtractor:
    def test_extract_skips_failed_results(self, failed_crawl_result):
        extractor = ContentExtractor()
        pages = extractor.extract([failed_crawl_result])
        assert pages == []

    def test_extract_main_content_with_trafilatura(self, simple_crawl_result):
        extractor = ContentExtractor(PageConfig(extract_main_content=True))
        with patch("crawl4md.extractor.trafilatura") as mock_traf:
            mock_traf.extract.return_value = "# Hello World\n\nMain content."
            pages = extractor.extract([simple_crawl_result])

        assert len(pages) == 1
        assert pages[0].url == "https://example.com/test"
        assert "Main content" in pages[0].markdown

    def test_extract_full_html_with_markdownify(self, simple_crawl_result):
        config = PageConfig(extract_main_content=False, exclude_tags=[], include_only_tags=[])
        extractor = ContentExtractor(config)
        pages = extractor.extract([simple_crawl_result])

        assert len(pages) == 1
        assert pages[0].url == "https://example.com/test"
        # markdownify should produce some markdown
        assert len(pages[0].markdown) > 0

    def test_extract_title(self):
        extractor = ContentExtractor()
        title = extractor._extract_title(SIMPLE_HTML)
        assert title == "Test Page"

    def test_extract_title_missing(self):
        extractor = ContentExtractor()
        title = extractor._extract_title("<html><body>no title</body></html>")
        assert title == ""

    def test_filter_tags_exclude(self):
        config = PageConfig(exclude_tags=["nav", "footer"], include_only_tags=[])
        extractor = ContentExtractor(config)
        html = "<div><nav>skip</nav><p>keep</p><footer>skip</footer></div>"
        filtered = extractor._filter_tags(html)
        assert "skip" not in filtered
        assert "keep" in filtered

    def test_filter_tags_include_only(self):
        config = PageConfig(exclude_tags=[], include_only_tags=["main"])
        extractor = ContentExtractor(config)
        html = "<div>outside</div><main><p>inside</p></main>"
        filtered = extractor._filter_tags(html)
        assert "inside" in filtered
        assert "outside" not in filtered

    def test_empty_html_produces_no_pages(self):
        result = CrawlResult(url="https://example.com", html="", success=True)
        with patch("crawl4md.extractor.trafilatura") as mock_traf:
            mock_traf.extract.return_value = ""
            extractor = ContentExtractor()
            pages = extractor.extract([result])
        assert pages == []

    def test_extract_multiple_results(self):
        results = [
            CrawlResult(url=f"https://example.com/p{i}", html=MINIMAL_HTML, success=True)
            for i in range(3)
        ]
        config = PageConfig(extract_main_content=False, exclude_tags=[], include_only_tags=[])
        extractor = ContentExtractor(config)
        pages = extractor.extract(results)
        assert len(pages) == 3


class TestFixMarkdownTables:
    """Tests for the _fix_markdown_tables post-processing."""

    def test_inserts_separator_when_missing(self):
        text = (
            "Col A | Col B | Col C |\n"
            "val1 | val2 | val3 |\n"
            "val4 | val5 | val6 |"
        )
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        assert lines[0] == "| Col A | Col B | Col C |"
        assert lines[1] == "| --- | --- | --- |"
        assert lines[2] == "| val1 | val2 | val3 |"

    def test_preserves_existing_separator(self):
        text = (
            "| Col A | Col B |\n"
            "|---|---|\n"
            "| val1 | val2 |"
        )
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        assert lines[0] == "| Col A | Col B |"
        assert lines[1] == "| --- | --- |"
        assert lines[2] == "| val1 | val2 |"

    def test_no_table_passes_through(self):
        text = "Just some text.\n\nNo tables here."
        result = ContentExtractor._fix_markdown_tables(text)
        assert result == text

    def test_single_row_table_no_separator_added(self):
        text = "Only | one | row |"
        result = ContentExtractor._fix_markdown_tables(text)
        # A single row doesn't need a separator (no data rows follow)
        assert "---" not in result

    def test_mixed_content_with_table(self):
        text = (
            "# Heading\n"
            "\n"
            "Some text.\n"
            "\n"
            "Header A | Header B |\n"
            "data1 | data2 |\n"
            "\n"
            "More text."
        )
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        assert lines[4] == "| Header A | Header B |"
        assert lines[5] == "| --- | --- |"
        assert lines[6] == "| data1 | data2 |"

    def test_trafilatura_table_output(self):
        """Simulate the actual trafilatura output for the HomeHub+ pricing table."""
        text = (
            "**HomeHub+ 5G**\n"
            "\n"
            "Ala Carte (price/month) | HomeHub+ 5G (price/month) | Savings | |\n"
            "TV+ Pass (Entertainment+/Asian+) | $30.56 | $82.00 | Save up to $16.54/mth |\n"
            "| 5Gbps Broadband | $45.00 | ||\n"
            "| Netflix Standard Plan (2 screens) | $22.98 | ||\n"
            "| Total monthly subscription | $98.54 |"
        )
        result = ContentExtractor._fix_markdown_tables(text)
        lines = result.split("\n")
        # Header normalized with leading pipe
        assert lines[2].startswith("| Ala Carte")
        # Separator should be inserted after header row
        assert "---" in lines[3]
        # First data row should follow with consistent pipes
        assert "$30.56" in lines[4]
        assert lines[4].startswith("|")
        # Rows with || get expanded to empty cells and padded to 4 columns
        assert lines[5].count("|") == lines[2].count("|")
        # Short row padded
        assert "Total monthly subscription" in lines[7]
        assert lines[7].count("|") == lines[2].count("|")
