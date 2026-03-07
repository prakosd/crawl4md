"""Real-time progress reporting for Jupyter and terminal."""

from __future__ import annotations

import time
from datetime import datetime, timedelta


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

    def __init__(
        self,
        total: int,
        *,
        action: str = "Crawled",
        prior_success: int = 0,
        prior_fail: int = 0,
    ) -> None:
        self.total = total
        self.count = 0
        self.action = action
        self._start_time = time.time()
        self._use_notebook = _in_notebook()
        self._prior_success = prior_success
        self._prior_fail = prior_fail
        self._round_success = 0
        self._round_fail = 0

    def _elapsed(self) -> str:
        seconds = int(time.time() - self._start_time)
        minutes, secs = divmod(seconds, 60)
        return f"{minutes:02d}:{secs:02d}"

    def _eta_remaining(self) -> str:
        """Estimated time remaining."""
        if self.count == 0:
            return "estimating..."
        elapsed = time.time() - self._start_time
        remaining = elapsed / self.count * (self.total - self.count)
        mins, secs = divmod(int(remaining), 60)
        hours, mins = divmod(mins, 60)
        if hours > 0:
            return f"{hours}h {mins:02d}m {secs:02d}s"
        return f"{mins:02d}:{secs:02d}"

    def _eta_finish_time(self) -> str:
        """Estimated wall-clock finish time."""
        if self.count == 0:
            return "estimating..."
        elapsed = time.time() - self._start_time
        remaining = elapsed / self.count * (self.total - self.count)
        finish = datetime.now() + timedelta(seconds=remaining)
        return finish.strftime("%H:%M:%S")

    def update(self, url: str, *, success: bool = True) -> None:
        """Report that a page has been processed."""
        self.count += 1
        if success:
            self._round_success += 1
        else:
            self._round_fail += 1
        eta = f"~{self._eta_remaining()} left, done ~{self._eta_finish_time()}"
        msg = f"[{self.count}/{self.total}] ({self._elapsed()}) {self.action}: {url}"
        total_crawled = self._prior_success + self._prior_fail + self._round_success + self._round_fail
        total_success = self._prior_success + self._round_success
        total_fail = self._prior_fail + self._round_fail
        stats = f"Total: {total_crawled} crawled, {total_success} succeeded, {total_fail} failed"

        if self._use_notebook:
            from IPython.display import clear_output, display  # type: ignore[import-untyped]

            clear_output(wait=True)
            display(_ProgressWidget(self.count, self.total, msg, eta, stats))
        else:
            print(f"{msg}  |  {eta}")
            print(stats)

    def finish(self, output_dir: str | None = None) -> None:
        """Report that processing is complete."""
        msg = f"\nDone! {self.action} {self.count} page(s) in {self._elapsed()}."
        if output_dir:
            msg += f"\nOutput folder: {output_dir}"
        if self._use_notebook:
            from IPython.display import clear_output  # type: ignore[import-untyped]

            clear_output(wait=True)
            print(msg)
        else:
            print(msg)


class _ProgressWidget:
    """Simple HTML progress bar for Jupyter notebooks."""

    def __init__(self, current: int, total: int, label: str, eta: str = "", stats: str = "") -> None:
        self.current = current
        self.total = total
        self.label = label
        self.eta = eta
        self.stats = stats

    def _repr_html_(self) -> str:
        pct = int(self.current / self.total * 100) if self.total else 0
        return (
            f"<div>{self.label}</div>"
            f'<div style="background:#eee;border-radius:4px;overflow:hidden;height:20px;">'
            f'<div style="background:#4CAF50;height:100%;width:{pct}%;'
            f'transition:width 0.3s;"></div></div>'
            f"<div>{self.current} / {self.total} pages"
            f"{(' &nbsp;|&nbsp; ' + self.eta) if self.eta else ''}</div>"
            f"{('<div style=\"margin-top:4px;color:#555;\">' + self.stats + '</div>') if self.stats else ''}"
        )
