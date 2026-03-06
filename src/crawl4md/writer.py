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

    Supports two usage modes:

    **Batch mode** (original API)::

        writer = FileWriter()
        files = writer.write(pages, output_dir, max_file_size_mb)

    **Incremental mode** (for flushing during a crawl)::

        writer = FileWriter(output_dir, max_file_size_mb)
        for page in pages:
            writer.add(page)
        files = writer.flush()
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        max_file_size_mb: float = 15.0,
    ) -> None:
        self._output_dir = Path(output_dir) if output_dir else None
        self._max_bytes = int(max_file_size_mb * _MB)
        self._max_file_size_mb = max_file_size_mb
        self._file_index = 1
        self._current_chunks: list[str] = []
        self._current_size = 0
        self._bytes_on_disk = 0  # bytes already written to the current file
        self._files: list[Path] = []

    # ------------------------------------------------------------------
    # Incremental API
    # ------------------------------------------------------------------

    def add(self, page: ExtractedPage) -> None:
        """Add a single page to the write buffer.

        When the current file would exceed ``max_file_size_mb``, the
        buffer is flushed and a new file is started automatically.
        """
        assert self._output_dir is not None, "output_dir required for incremental mode"
        block = self._format_page(page)
        block_size = len(block.encode("utf-8"))

        if block_size > self._max_bytes:
            warnings.warn(
                f"Page {page.url} ({block_size / _MB:.1f} MB) exceeds the "
                f"{self._max_file_size_mb} MB limit and will be saved as its own file.",
                stacklevel=2,
            )
            # Flush current buffer to the current file first
            self._flush_buffer()
            # If the current file already has data, move to a new file
            if self._bytes_on_disk > 0:
                self._file_index += 1
                self._bytes_on_disk = 0
            # Write oversized page alone in its own file
            self._write_file([block])
            self._file_index += 1
            self._bytes_on_disk = 0
            return

        total = self._bytes_on_disk + self._current_size + block_size
        if total > self._max_bytes and (self._current_chunks or self._bytes_on_disk > 0):
            # Current file is full — flush buffer, then start a new file
            self._flush_buffer()
            self._file_index += 1
            self._bytes_on_disk = 0

        self._current_chunks.append(block)
        self._current_size += block_size

    def flush(self) -> list[Path]:
        """Flush the in-memory buffer to disk and return all files created."""
        self._flush_buffer()
        return list(self._files)

    # ------------------------------------------------------------------
    # Batch API (backward-compatible)
    # ------------------------------------------------------------------

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
                    files.append(self._write_to(output_dir, file_index, current_chunks))
                    file_index += 1
                    current_chunks = []
                    current_size = 0
                # Write oversized page alone
                files.append(self._write_to(output_dir, file_index, [block]))
                file_index += 1
                continue

            if current_size + block_size > max_bytes and current_chunks:
                files.append(self._write_to(output_dir, file_index, current_chunks))
                file_index += 1
                current_chunks = []
                current_size = 0

            current_chunks.append(block)
            current_size += block_size

        if current_chunks:
            files.append(self._write_to(output_dir, file_index, current_chunks))

        return files

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _flush_buffer(self) -> None:
        """Append the in-memory buffer to the current file on disk."""
        if not self._current_chunks:
            return
        assert self._output_dir is not None
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"content_{self._file_index:03d}.txt"
        with path.open("a", encoding="utf-8") as fh:
            fh.write("".join(self._current_chunks))
        if path not in self._files:
            self._files.append(path)
        self._bytes_on_disk += self._current_size
        self._current_chunks = []
        self._current_size = 0

    def _write_file(self, chunks: list[str]) -> None:
        """Write chunks to the current file index (used for oversized pages)."""
        assert self._output_dir is not None
        self._output_dir.mkdir(parents=True, exist_ok=True)
        path = self._output_dir / f"content_{self._file_index:03d}.txt"
        path.write_text("".join(chunks), encoding="utf-8")
        if path not in self._files:
            self._files.append(path)

    @staticmethod
    def _format_page(page: ExtractedPage) -> str:
        """Format a single page as a text block with URL header."""
        header = f"URL: {page.url}"
        if page.title:
            header += f"\nTitle: {page.title}"
        return f"{_SEPARATOR}{header}\n{_SEPARATOR}{page.markdown}\n"

    @staticmethod
    def _write_to(output_dir: Path, index: int, chunks: list[str]) -> Path:
        """Write chunks to a numbered .txt file (batch mode helper)."""
        filename = f"content_{index:03d}.txt"
        path = output_dir / filename
        path.write_text("".join(chunks), encoding="utf-8")
        return path
