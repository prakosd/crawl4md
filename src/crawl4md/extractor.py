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
            favor_recall=True,
        )
        md = self._fix_markdown_tables(extracted or "")
        md = self._clean_markdown(md)
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
        md = self._clean_markdown(md)
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

    # ------------------------------------------------------------------
    # Markdown post-processing
    # ------------------------------------------------------------------

    @staticmethod
    def _clean_markdown(text: str) -> str:
        """Post-process extracted Markdown for readability.

        Applies a chain of safe transforms:

        1. Collapse 3+ consecutive blank lines into one.
        2. Deduplicate consecutive identical paragraphs.
        3. Compact product-listing blocks (name + price pairs) into bullet lists.
        4. Compact runs of short standalone paragraphs into bullet lists.
        """
        text = ContentExtractor._collapse_blank_lines(text)
        text = ContentExtractor._dedup_paragraphs(text)
        text = ContentExtractor._compact_product_listings(text)
        text = ContentExtractor._compact_short_paragraphs(text)
        return text

    @staticmethod
    def _collapse_blank_lines(text: str) -> str:
        """Replace runs of 3+ blank lines with a single blank line."""
        return re.sub(r"\n{3,}", "\n\n", text)

    @staticmethod
    def _compact_product_listings(text: str) -> str:
        """Detect repeated name→price sequences and reformat as bullet lists.

        A *product entry* is one or more non-blank, non-price, non-heading
        lines (the name / description) followed by exactly one price line
        matching ``$XX.XX`` (with optional ``from`` prefix).  Short lines
        (< 80 chars) adjacent to a product entry that don't look like a
        product name themselves are kept as indented sub-text (badges like
        "New", "3 offers available", promotional blurbs, etc.).

        The transform only fires when **3 or more** consecutive product
        entries are found, to avoid false positives on article pages that
        mention prices incidentally.
        """
        price_re = re.compile(r"^(?:from\s+)?\$[\d,]+(?:\.\d{2})?$")
        heading_re = re.compile(r"^#{1,6}\s")
        hr_re = re.compile(r"^---+$")

        lines = text.split("\n")
        result: list[str] = []
        i = 0

        while i < len(lines):
            # Try to collect a run of product entries starting here
            entries: list[dict] = []
            j = i
            while j < len(lines):
                entry, j = ContentExtractor._try_parse_product_entry(
                    lines, j, price_re, heading_re, hr_re,
                )
                if entry is None:
                    break
                entries.append(entry)

            if len(entries) >= 3:
                # Emit as bullet list
                for entry in entries:
                    result.append(f"- **{entry['name']}** — {entry['price']}")
                    for badge in entry["badges"]:
                        result.append(f"  {badge}")
                i = j
            else:
                result.append(lines[i])
                i += 1

        return "\n".join(result)

    @staticmethod
    def _try_parse_product_entry(
        lines: list[str],
        start: int,
        price_re: re.Pattern[str],
        heading_re: re.Pattern[str],
        hr_re: re.Pattern[str],
    ) -> tuple[dict | None, int]:
        """Try to parse a single product entry (badges + name + price) at *start*.

        Returns ``(entry_dict, next_index)`` on success, or
        ``(None, start)`` if the lines at *start* don't form a product entry.
        """
        i = start
        # Skip blank lines between entries
        while i < len(lines) and lines[i].strip() == "":
            i += 1
        if i >= len(lines):
            return None, start

        # Collect all non-blank, non-price, non-heading, non-hr content lines.
        # Blank lines between content lines are allowed (badges and names are
        # often separated by blank lines in the extracted Markdown).
        content_lines: list[str] = []
        j = i
        while j < len(lines):
            line = lines[j].strip()
            if not line:
                # Look ahead past blanks for the next non-blank line
                k = j
                while k < len(lines) and lines[k].strip() == "":
                    k += 1
                if k < len(lines) and price_re.match(lines[k].strip()):
                    # Blanks before a price — stop collecting content
                    break
                if k >= len(lines):
                    break
                nxt = lines[k].strip()
                if heading_re.match(nxt) or hr_re.match(nxt):
                    break
                # Otherwise skip blanks and continue collecting
                j = k
                continue
            if price_re.match(line) or heading_re.match(line) or hr_re.match(line):
                break
            content_lines.append(line)
            j += 1

        if not content_lines:
            return None, start

        # Skip blank lines between content and price
        while j < len(lines) and lines[j].strip() == "":
            j += 1

        if j >= len(lines):
            return None, start

        # Expect a price line
        price_line = lines[j].strip()
        if not price_re.match(price_line):
            return None, start
        j += 1

        # Split content_lines into badges (before name) and the name itself.
        # The last content line (or group of long lines) is the name;
        # short preceding lines are pre-badges.
        pre_badges: list[str] = []
        name_parts: list[str] = list(content_lines)

        # Peel off leading short lines as badges (< 40 chars or ends with '!')
        while len(name_parts) > 1:
            candidate = name_parts[0]
            if len(candidate) < 40 or candidate.endswith("!"):
                pre_badges.append(name_parts.pop(0))
            else:
                break

        # Collect post-badges: short lines after price (offers, promo text).
        # Stop if the line looks like it could be the next product name
        # (i.e. it's followed by a price line within a few lines).
        post_badges: list[str] = []
        while j < len(lines):
            line = lines[j].strip()
            if not line:
                j += 1
                continue
            if price_re.match(line) or heading_re.match(line) or hr_re.match(line):
                break
            # Peek ahead: if a price follows this line (skipping blanks),
            # this line is the next product name, not a badge.
            k = j + 1
            while k < len(lines) and lines[k].strip() == "":
                k += 1
            if k < len(lines) and price_re.match(lines[k].strip()):
                break
            if len(line) < 80 and (len(line) < 40 or line.endswith("!")):
                post_badges.append(line)
                j += 1
            else:
                break

        name = " ".join(name_parts)
        return {
            "name": name,
            "price": price_line,
            "badges": pre_badges + post_badges,
        }, j

    @staticmethod
    def _dedup_paragraphs(text: str) -> str:
        """Remove consecutive duplicate paragraphs (separated by blank lines)."""
        paragraphs = re.split(r"\n{2,}", text)
        deduped: list[str] = []
        for para in paragraphs:
            if not deduped or para.strip() != deduped[-1].strip():
                deduped.append(para)
        return "\n\n".join(deduped)

    @staticmethod
    def _compact_short_paragraphs(text: str) -> str:
        """Convert runs of 3+ short single-line paragraphs into bullet lists.

        Sequences of short standalone lines separated by blank lines
        (typical of CSS-layout content losing its visual grouping) are
        collapsed into ``- item`` bullet lists.  Headings, horizontal
        rules, existing list items, and multi-line paragraphs are left
        untouched and act as boundaries for the runs.
        """
        paragraphs = re.split(r"\n\n+", text)
        heading_re = re.compile(r"^#{1,6}\s")
        hr_re = re.compile(r"^---+$")
        list_re = re.compile(r"^[-*+]\s")
        max_len = 120

        result: list[str] = []
        run: list[str] = []

        def flush_run() -> None:
            if len(run) >= 3:
                for item in run:
                    result.append(f"- {item}")
            else:
                for item in run:
                    result.append(item)
            run.clear()

        for para in paragraphs:
            stripped = para.strip()
            is_single_line = "\n" not in stripped
            is_short = len(stripped) <= max_len
            is_special = (
                heading_re.match(stripped)
                or hr_re.match(stripped)
                or list_re.match(stripped)
                or not stripped
            )

            if is_single_line and is_short and not is_special:
                run.append(stripped)
            else:
                flush_run()
                result.append(para)

        flush_run()
        return "\n\n".join(result)

    @staticmethod
    def _extract_title(html: str) -> str:
        """Pull the <title> text from HTML, or return empty string."""
        import re

        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        return match.group(1).strip() if match else ""
