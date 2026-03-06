"""Real-time progress reporting for Jupyter and terminal."""

from __future__ import annotations

import time


def _in_notebook() -> bool:
    """Detect whether we are running inside a Jupyter/IPython notebook."""
    try:
        from IPython import get_ipython  # type: ignore[import-untyped]

        shell = get_ipython()
        if shell is None:
            return False
        return shell.__class__.__name__ == "ZMQInteractiveShell"
    except ImportError:
        return False


class ProgressReporter:
    """Displays crawl progress to the user in real time."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.count = 0
        self._start_time = time.time()
        self._use_notebook = _in_notebook()

    def _elapsed(self) -> str:
        seconds = int(time.time() - self._start_time)
        minutes, secs = divmod(seconds, 60)
        return f"{minutes:02d}:{secs:02d}"

    def update(self, url: str) -> None:
        """Report that a page has been crawled."""
        self.count += 1
        msg = (
            f"[{self.count}/{self.total}] ({self._elapsed()}) Crawled: {url}"
        )

        if self._use_notebook:
            from IPython.display import clear_output, display  # type: ignore[import-untyped]

            clear_output(wait=True)
            display(_ProgressWidget(self.count, self.total, msg))
        else:
            print(msg)

    def finish(self, output_dir: str) -> None:
        """Report that crawling is complete."""
        msg = (
            f"\nDone! Crawled {self.count} page(s) in {self._elapsed()}.\n"
            f"Output folder: {output_dir}"
        )
        if self._use_notebook:
            from IPython.display import clear_output  # type: ignore[import-untyped]

            clear_output(wait=True)
            print(msg)
        else:
            print(msg)


class _ProgressWidget:
    """Simple HTML progress bar for Jupyter notebooks."""

    def __init__(self, current: int, total: int, label: str) -> None:
        self.current = current
        self.total = total
        self.label = label

    def _repr_html_(self) -> str:
        pct = int(self.current / self.total * 100) if self.total else 0
        return (
            f"<div>{self.label}</div>"
            f'<div style="background:#eee;border-radius:4px;overflow:hidden;height:20px;">'
            f'<div style="background:#4CAF50;height:100%;width:{pct}%;'
            f'transition:width 0.3s;"></div></div>'
            f"<div>{self.current} / {self.total} pages</div>"
        )
