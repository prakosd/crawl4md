"""FileWriter — combines extracted pages into size-limited .txt files."""

from __future__ import annotations

import warnings
from pathlib import Path

from crawl4md.config import ExtractedPage

_SEPARATOR = "\n\n" + "=" * 80 + "\n"
_MB = 1024 * 1024


class FileWriter:
    """Writes extracted Markdown content to numbered .txt files.

    Each page is preceded by a URL header and separator.  Files are split
    when adding another page would exceed ``max_file_size_mb``.  A single
    page is **never** split across two files.
    """

    def write(
        self,
        pages: list[ExtractedPage],
        output_dir: Path | str,
        max_file_size_mb: float = 15.0,
    ) -> list[Path]:
        """Write pages to numbered text files and return created paths."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        max_bytes = int(max_file_size_mb * _MB)
        files: list[Path] = []
        current_chunks: list[str] = []
        current_size = 0
        file_index = 1

        for page in pages:
            block = self._format_page(page)
            block_size = len(block.encode("utf-8"))

            if block_size > max_bytes:
                warnings.warn(
                    f"Page {page.url} ({block_size / _MB:.1f} MB) exceeds the "
                    f"{max_file_size_mb} MB limit and will be saved as its own file.",
                    stacklevel=2,
                )
                # Flush current buffer first
                if current_chunks:
                    files.append(self._flush(output_dir, file_index, current_chunks))
                    file_index += 1
                    current_chunks = []
                    current_size = 0
                # Write oversized page alone
                files.append(self._flush(output_dir, file_index, [block]))
                file_index += 1
                continue

            if current_size + block_size > max_bytes and current_chunks:
                files.append(self._flush(output_dir, file_index, current_chunks))
                file_index += 1
                current_chunks = []
                current_size = 0

            current_chunks.append(block)
            current_size += block_size

        if current_chunks:
            files.append(self._flush(output_dir, file_index, current_chunks))

        return files

    @staticmethod
    def _format_page(page: ExtractedPage) -> str:
        """Format a single page as a text block with URL header."""
        header = f"URL: {page.url}"
        if page.title:
            header += f"\nTitle: {page.title}"
        return f"{_SEPARATOR}{header}\n{_SEPARATOR}{page.markdown}\n"

    @staticmethod
    def _flush(output_dir: Path, index: int, chunks: list[str]) -> Path:
        """Write chunks to a numbered .txt file."""
        filename = f"content_{index:03d}.txt"
        path = output_dir / filename
        path.write_text("".join(chunks), encoding="utf-8")
        return path
