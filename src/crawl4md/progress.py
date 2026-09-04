"""Real-time progress reporting for the terminal."""

from __future__ import annotations

import time
from collections import deque
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from crawl4md._internal.activity_log import (
    _ACTIVITY_LOG_CSV_FILE as _ACTIVITY_LOG_CSV_FILE,
)
from crawl4md._internal.activity_log import (
    _ACTIVITY_LOG_CSV_HEADER as _ACTIVITY_LOG_CSV_HEADER,
)
from crawl4md._internal.activity_log import (
    _ACTIVITY_LOG_FLUSH_EVERY as _ACTIVITY_LOG_FLUSH_EVERY,
)
from crawl4md._internal.activity_log import (
    _ACTIVITY_LOG_TXT_FILE as _ACTIVITY_LOG_TXT_FILE,
)
from crawl4md._internal.activity_log import (
    ActivityLogger,
)

# Maximum number of recent activities shown in the activity log.
_MAX_LOG_ENTRIES = 10

# ---------------------------------------------------------------------------
# ETA / duration formatting
# ---------------------------------------------------------------------------
# Shown while ETA cannot yet be calculated (no pages completed).
_ETA_PLACEHOLDER = "estimating..."
# Durations shorter than this threshold are displayed as "<0.1s".
_SHORT_DURATION_THRESHOLD = 0.1

# ---------------------------------------------------------------------------
# Activity icon mapping (keyword → emoji)
# ---------------------------------------------------------------------------
_ACTIVITY_ICONS: dict[str, str] = {
    "failed": "❌",
    "skip": "⏭️",
    "no content": "📭",
    "reading page": "🌐",
    "downloading": "📥",
    "saving": "💾",
    "pausing": "⏸️",
    "waiting": "⏳",
    "blocking": "🛡️",
    "finding": "🔍",
    "found": "🔗",
}
# Fallback icon when no keyword matches.
_ACTIVITY_ICON_DEFAULT = "⚙️"

# Minimum completed pages before showing pages-per-minute rate.
_RATE_MIN_PAGES = 2


def _fmt_duration(seconds: float) -> str:
    """Format a duration as a compact human-readable string."""
    if seconds < _SHORT_DURATION_THRESHOLD:
        return "<0.1s"
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins, secs = divmod(int(seconds), 60)
    return f"{mins}m {secs:02d}s"


def _activity_category(label: str) -> str:
    """Categorise an activity label for ETA averaging."""
    low = label.lower()
    if "reading page" in low or "downloading" in low:
        return "crawl"
    if "saving page" in low or "saving pdf" in low:
        return "extract"
    if "saving progress" in low:
        return "flush"
    if "pausing" in low or "waiting" in low or "blocking" in low:
        return "delay"
    if "finding" in low or "found" in low:
        return "discover"
    return "other"


def _activity_icon(label: str) -> str:
    """Pick a small icon for the activity label."""
    low = label.lower()
    for keyword, icon in _ACTIVITY_ICONS.items():
        if keyword in low:
            return icon
    return _ACTIVITY_ICON_DEFAULT


class ProgressReporter:
    """Displays crawl progress to the user in real time."""

    def __init__(
        self,
        total: int,
        *,
        action: str = "Crawled",
        prior_success: int = 0,
        prior_fail: int = 0,
        round_label: str = "",
        max_log_entries: int = _MAX_LOG_ENTRIES,
        log_dir: Path | None = None,
    ) -> None:
        self.total = total
        self.count = 0
        self.action = action
        self._start_time = time.time()
        self._prior_success = prior_success
        self._prior_fail = prior_fail
        self._round_success = 0
        self._round_fail = 0
        self._round_label = round_label
        self._max_log_entries = max_log_entries
        self._log_dir = log_dir

        # Activity tracking
        self._current_activity: str = ""
        self._activity_start: float = 0.0
        self._activity_log: deque[tuple[datetime, str, float]] = deque(
            maxlen=max_log_entries if max_log_entries > 0 else None
        )
        self._activity_logger = ActivityLogger(
            log_dir=log_dir,
            round_label=round_label,
            icon_for_label=_activity_icon,
            format_duration=_fmt_duration,
        )

    def __del__(self) -> None:
        with suppress(Exception):
            self._close_disk_log_handles()

    def _elapsed(self) -> str:
        seconds = int(time.time() - self._start_time)
        minutes, secs = divmod(seconds, 60)
        return f"{minutes:02d}:{secs:02d}"

    def _eta_remaining(self) -> str:
        """Estimated time remaining."""
        if self.count == 0:
            return _ETA_PLACEHOLDER
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
            return _ETA_PLACEHOLDER
        elapsed = time.time() - self._start_time
        remaining = elapsed / self.count * (self.total - self.count)
        finish = datetime.now() + timedelta(seconds=remaining)
        return finish.strftime("%H:%M:%S")

    def _eta_remaining_friendly(self) -> str:
        """Estimated time remaining as natural language (e.g. 'About 3 minutes left')."""
        if self.count == 0:
            return _ETA_PLACEHOLDER
        elapsed = time.time() - self._start_time
        remaining = int(elapsed / self.count * (self.total - self.count))
        if remaining < 60:
            return "Less than a minute left"
        hours, mins = divmod(remaining // 60, 60)
        if hours > 0:
            parts = [f"{hours} hour{'s' if hours != 1 else ''}"]
            if mins > 0:
                parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
            return f"About {' '.join(parts)} left"
        return f"About {mins} minute{'s' if mins != 1 else ''} left"

    def eta_remaining_seconds(self) -> float | None:
        """Remaining seconds estimated from current rate, or None if not yet computable."""
        if self.count == 0:
            return None
        elapsed = time.time() - self._start_time
        return elapsed / self.count * max(self.total - self.count, 0)

    # ------------------------------------------------------------------
    # Activity tracking
    # ------------------------------------------------------------------

    def set_activity(self, activity: str) -> None:
        """Record a new current activity (e.g. 'Crawling …', 'Extracting')."""
        self._close_activity()
        self._current_activity = activity
        self._activity_start = time.time()

    def _close_activity(self) -> None:
        """Close the current activity and append it to the log."""
        if self._current_activity and self._activity_start > 0:
            duration = time.time() - self._activity_start
            ts = datetime.now()
            self._activity_log.append((ts, self._current_activity, duration))
            self._append_to_disk(ts, self._current_activity, duration)
        self._current_activity = ""
        self._activity_start = 0.0

    def _append_to_disk(self, ts: datetime, label: str, duration: float) -> None:
        """Append one activity entry to the TXT and CSV log files on disk."""
        self._activity_logger.append(ts, label, duration)

    def _ensure_disk_log_handles(self):
        return self._activity_logger.ensure_handles()

    def _flush_disk_logs(self) -> None:
        self._activity_logger.flush()

    def _close_disk_log_handles(self) -> None:
        self._activity_logger.close()

    def close(self) -> None:
        self._close_activity()
        self._close_disk_log_handles()

    def update_activity_label(self, label: str) -> None:
        """Update the label of the current activity without closing it."""
        self._current_activity = label

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def update(self, url: str, *, success: bool = True) -> None:
        """Report that a page has been processed."""
        if not success and self._current_activity:
            self._current_activity = f"\u274c FAILED \u2014 {self._current_activity}"
        self._close_activity()
        self.count += 1
        if success:
            self._round_success += 1
        else:
            self._round_fail += 1

        eta = self._eta_remaining_friendly()
        msg = f"[{self.count}/{self.total}] ({self._elapsed()}) {self.action}: {url}"
        total_crawled = (
            self._prior_success + self._prior_fail + self._round_success + self._round_fail
        )
        total_success = self._prior_success + self._round_success
        total_fail = self._prior_fail + self._round_fail
        rate_info = ""
        elapsed = time.time() - self._start_time
        if self.count >= _RATE_MIN_PAGES and elapsed > 0:
            rate = self.count / elapsed * 60
            rate_info = f" (~{rate:.0f} pages/min)"
        stats = (
            f"\u2705 {total_success}  \u274c {total_fail}"
            f"  \U0001f4c4 {total_crawled} total{rate_info}"
        )
        print(f"{msg}  |  {eta}")
        print(stats)

    def finish(self, output_dir: str | None = None) -> None:
        """Report that processing is complete."""
        self.close()
        msg = f"\nDone! {self.action} {self.count} page(s) in {self._elapsed()}."
        if output_dir:
            msg += f"\nOutput folder: {output_dir}"
        print(msg)
