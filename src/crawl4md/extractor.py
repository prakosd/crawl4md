"""ContentExtractor — converts crawled HTML to clean Markdown text."""

from __future__ import annotations

import re

import trafilatura
from markdownify import markdownify

from crawl4md.config import CrawlResult, ExtractedPage, PageConfig
from crawl4md.progress import ProgressReporter


class ContentExtractor:
    """Extracts readable Markdown content from crawled pages.

    Uses **trafilatura** when ``extract_main_content`` is enabled (strips
    navigation, headers, footers) and **markdownify** for full-HTML mode.
    """

    def __init__(self, page_config: PageConfig | None = None) -> None:
        self.page_config = page_config or PageConfig()

    def extract(self, results: list[CrawlResult]) -> list[ExtractedPage]:
        """Convert a list of crawl results into extracted Markdown pages."""
        successful = [r for r in results if r.success]
        progress = ProgressReporter(len(successful), action="Extracted")
        pages: list[ExtractedPage] = []
        for result in successful:
            page = self._extract_page(result)
            progress.update(result.url)
            if page.markdown.strip():
                pages.append(page)
        progress.finish()
        return pages

    def _extract_page(self, result: CrawlResult) -> ExtractedPage:
        """Extract content from a single crawl result."""
        if self.page_config.extract_main_content:
            return self._extract_main_content(result)
        return self._extract_full_html(result)

    def _extract_main_content(self, result: CrawlResult) -> ExtractedPage:
        """Use trafilatura to extract the main body content."""
        extracted = trafilatura.extract(
            result.html,
            output_format="markdown",
            include_links=True,
            include_tables=True,
        )
        md = self._fix_markdown_tables(extracted or "")
        title = self._extract_title(result.html)
        return ExtractedPage(
            url=result.url,
            title=title,
            markdown=md,
        )

    def _extract_full_html(self, result: CrawlResult) -> ExtractedPage:
        """Use markdownify on the (optionally tag-filtered) HTML."""
        html = self._filter_tags(result.html)
        md = markdownify(html, heading_style="ATX", strip=["img"], table_infer_header=True)
        title = self._extract_title(result.html)
        return ExtractedPage(
            url=result.url,
            title=title,
            markdown=md,
        )

    @staticmethod
    def _fix_markdown_tables(text: str) -> str:
        """Normalize pipe-delimited blocks into valid Markdown tables.

        Fixes common issues produced by HTML-to-Markdown converters when
        the original HTML uses ``colspan`` / ``rowspan``:

        * Missing ``| --- |`` separator after the header row.
        * Inconsistent leading / trailing pipes.
        * Double pipes (``||``) representing empty cells.
        * Rows with fewer columns than the header (padded with empty cells).
        """
        pipe_line = re.compile(r"^\|?.+\|.+\|?\s*$")

        lines = text.split("\n")
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if pipe_line.match(line):
                block: list[str] = []
                while i < len(lines) and pipe_line.match(lines[i]):
                    block.append(lines[i])
                    i += 1
                result.extend(ContentExtractor._normalize_table_block(block))
            else:
                result.append(line)
                i += 1
        return "\n".join(result)

    @staticmethod
    def _normalize_table_block(block: list[str]) -> list[str]:
        """Turn a block of pipe-delimited lines into a well-formed Markdown table."""
        if len(block) < 2:
            return block

        separator_re = re.compile(r"^\|?(\s*-{3,}\s*\|)+\s*-{3,}\s*\|?\s*$")
        has_separator = bool(separator_re.match(block[1]))

        rows_to_parse = [block[0]] + block[2:] if has_separator else list(block)

        parsed: list[list[str]] = []
        for row in rows_to_parse:
            expanded = row
            while "||" in expanded:
                expanded = expanded.replace("||", "| |")
            expanded = expanded.strip()
            if not expanded.startswith("|"):
                expanded = "| " + expanded
            if not expanded.endswith("|"):
                expanded = expanded + " |"
            cells = [c.strip() for c in expanded.split("|")]
            if cells and cells[0] == "":
                cells = cells[1:]
            if cells and cells[-1] == "":
                cells = cells[:-1]
            parsed.append(cells)

        max_cols = max(len(cells) for cells in parsed)
        if max_cols < 1:
            return block

        for cells in parsed:
            while len(cells) < max_cols:
                cells.append("")

        out: list[str] = []
        for cells in parsed:
            out.append("| " + " | ".join(cells) + " |")
        sep_row = "| " + " | ".join("---" for _ in range(max_cols)) + " |"
        out.insert(1, sep_row)
        return out

    def _filter_tags(self, html: str) -> str:
        """Remove or keep only specified HTML tags using simple parsing."""
        from html.parser import HTMLParser
        from io import StringIO

        if not self.page_config.include_only_tags and not self.page_config.exclude_tags:
            return html

        class TagFilter(HTMLParser):
            def __init__(self, include_only: list[str], exclude: list[str]) -> None:
                super().__init__()
                self.include_only = [t.lower() for t in include_only]
                self.exclude = [t.lower() for t in exclude]
                self.output = StringIO()
                self._skip_depth = 0
                self._include_depth = 0 if include_only else 1  # 1 = always include

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                tag_lower = tag.lower()
                if self.exclude and tag_lower in self.exclude:
                    self._skip_depth += 1
                    return
                if self.include_only and tag_lower in self.include_only:
                    self._include_depth += 1
                if self._skip_depth == 0 and self._include_depth > 0:
                    attr_str = "".join(
                        f' {k}="{v}"' if v else f" {k}" for k, v in attrs
                    )
                    self.output.write(f"<{tag}{attr_str}>")

            def handle_endtag(self, tag: str) -> None:
                tag_lower = tag.lower()
                if self.exclude and tag_lower in self.exclude:
                    self._skip_depth = max(0, self._skip_depth - 1)
                    return
                if self._skip_depth == 0 and self._include_depth > 0:
                    self.output.write(f"</{tag}>")
                if self.include_only and tag_lower in self.include_only:
                    self._include_depth = max(0, self._include_depth - 1)

            def handle_data(self, data: str) -> None:
                if self._skip_depth == 0 and self._include_depth > 0:
                    self.output.write(data)

        parser = TagFilter(
            include_only=self.page_config.include_only_tags,
            exclude=self.page_config.exclude_tags,
        )
        parser.feed(html)
        return parser.output.getvalue()

    @staticmethod
    def _extract_title(html: str) -> str:
        """Pull the <title> text from HTML, or return empty string."""
        import re

        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else ""
