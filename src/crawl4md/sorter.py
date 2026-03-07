"""ContentSorter — sorts extracted pages by URL path for grouped output."""

from __future__ import annotations

from urllib.parse import urlparse

from crawl4md.config import ExtractedPage


class ContentSorter:
    """Sorts pages so that content from related URL paths is grouped together.

    Pages are sorted lexicographically by their URL path segments, which
    naturally clusters pages under the same directory (e.g. all
    ``/personal/mobile/...`` pages appear together).  The sort is stable,
    so pages with identical paths retain their original crawl order.
    """

    @staticmethod
    def sort(pages: list[ExtractedPage]) -> list[ExtractedPage]:
        """Return a new list of pages sorted by URL path segments."""
        return sorted(pages, key=ContentSorter._sort_key)

    @staticmethod
    def _sort_key(page: ExtractedPage) -> tuple[str, ...]:
        """Generate a sort key from URL path segments."""
        parsed = urlparse(page.url)
        segments = [s for s in parsed.path.split("/") if s]
        return tuple(segments)
