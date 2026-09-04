"""Tests for crawl4md.progress — ProgressReporter and activity helpers."""

from __future__ import annotations

import csv
import time
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from crawl4md._internal.activity_log import ActivityLogger
from crawl4md.progress import (
    _ACTIVITY_LOG_CSV_FILE,
    _ACTIVITY_LOG_CSV_HEADER,
    _ACTIVITY_LOG_FLUSH_EVERY,
    _ACTIVITY_LOG_TXT_FILE,
    _MAX_LOG_ENTRIES,
    _RATE_MIN_PAGES,
    ProgressReporter,
    _activity_category,
    _activity_icon,
    _fmt_duration,
)


class TestActivityHelpers:
    """Tests for the module-level activity helper functions."""

    def test_activity_icon(self):
        assert _activity_icon("Reading page x") == "🌐"
        assert _activity_icon("Downloading PDF example.pdf") == "📥"
        assert _activity_icon("Saving page content") == "💾"
        assert _activity_icon("Saving progress (5 pages)") == "💾"
        assert _activity_icon("Pausing to avoid blocks (5.0s)") == "⏸️"
        assert _activity_icon("Waiting before retry (3.0s)") == "⏳"
        assert _activity_icon("Website is blocking us") == "🛡️"
        assert _activity_icon("Finding more pages on x") == "🔍"
        assert _activity_icon("Found 5 new pages on x") == "🔗"
        assert _activity_icon("Skipped example.com (redirect)") == "⏭️"
        assert _activity_icon("No content found on x") == "📭"
        assert _activity_icon("Something else") == "⚙️"
        assert _activity_icon("❌ FAILED \u2014 Reading page x") == "❌"

    def test_fmt_duration_ranges(self):
        assert _fmt_duration(0.01) == "<0.1s"
        assert _fmt_duration(0.5) == "0.5s"
        assert _fmt_duration(45.3) == "45.3s"
        assert _fmt_duration(125) == "2m 05s"

    def test_activity_category(self):
        assert _activity_category("Reading page example.com") == "crawl"
        assert _activity_category("Downloading PDF example.com/f.pdf") == "crawl"
        assert _activity_category("Saving page content") == "extract"
        assert _activity_category("Saving PDF content") == "extract"
        assert _activity_category("Saving progress") == "flush"
        assert _activity_category("Pausing to avoid blocks (5.0s)") == "delay"
        assert _activity_category("Waiting before retry (3s)") == "delay"
        assert _activity_category("Website is blocking us \u2014 waiting 30s") == "delay"
        assert _activity_category("Finding more pages on x") == "discover"
        assert _activity_category("Found 5 new pages on x") == "discover"
        assert _activity_category("Something else") == "other"
        # Failed activities keep their category based on the underlying label
        assert _activity_category("\u274c FAILED \u2014 Reading page x") == "crawl"


class TestProgressReporter:
    """Tests for ProgressReporter activity tracking."""

    def test_set_activity_records_to_log(self):
        """set_activity closes previous activity and records its duration."""
        reporter = ProgressReporter(5)

        reporter.set_activity("Reading page A")
        time.sleep(0.05)
        reporter.set_activity("Saving page content")

        assert len(reporter._activity_log) == 1
        ts, label, dur = reporter._activity_log[0]
        assert isinstance(ts, datetime)
        assert label == "Reading page A"
        assert dur >= 0.04  # Should have captured the sleep

        assert reporter._current_activity == "Saving page content"
        assert reporter._activity_start > 0

    def test_activity_log_capped(self):
        """Activity log does not exceed _MAX_LOG_ENTRIES."""
        reporter = ProgressReporter(10)

        for i in range(_MAX_LOG_ENTRIES + 5):
            reporter.set_activity(f"Activity {i}")

        # Close the last one
        reporter._close_activity()
        assert len(reporter._activity_log) == _MAX_LOG_ENTRIES

    def test_update_closes_activity(self):
        """update() should close the current activity."""
        reporter = ProgressReporter(5)

        reporter.set_activity("Reading page X")
        reporter.update("https://example.com/x", success=True)

        assert reporter._current_activity == ""
        assert len(reporter._activity_log) == 1
        assert reporter._activity_log[0][1] == "Reading page X"

    def test_update_increments_counts(self):
        reporter = ProgressReporter(3)

        reporter.update("https://example.com/a", success=True)
        reporter.update("https://example.com/b", success=False)

        assert reporter.count == 2
        assert reporter._round_success == 1
        assert reporter._round_fail == 1

    def test_finish_closes_activity(self):
        reporter = ProgressReporter(2)

        reporter.set_activity("Reading page something")
        reporter.finish()

        assert reporter._current_activity == ""
        assert len(reporter._activity_log) == 1

    def test_round_label_stored(self):
        reporter = ProgressReporter(5, round_label="First pass")
        assert reporter._round_label == "First pass"

    def test_no_activity_calls_still_works(self):
        """Reporter without any set_activity calls should still function."""
        reporter = ProgressReporter(2)

        reporter.update("https://example.com/a", success=True)
        reporter.update("https://example.com/b", success=True)
        reporter.finish()

        assert reporter.count == 2
        assert list(reporter._activity_log) == []

    def test_custom_max_log_entries(self):
        """Custom max_log_entries is respected."""
        reporter = ProgressReporter(20, max_log_entries=3)

        for i in range(10):
            reporter.set_activity(f"Activity {i}")
        reporter._close_activity()

        assert len(reporter._activity_log) == 3

    def test_update_activity_label_keeps_timer(self):
        """update_activity_label changes label without closing activity."""
        reporter = ProgressReporter(5)

        reporter.set_activity("Finding more pages on example.com")
        start = reporter._activity_start
        time.sleep(0.05)

        reporter.update_activity_label("Found 5 new pages on example.com")

        # Label changed but timer was NOT reset
        assert reporter._current_activity == "Found 5 new pages on example.com"
        assert reporter._activity_start == start
        # No new log entry created
        assert len(reporter._activity_log) == 0

    def test_default_max_log_entries_is_ten(self):
        """Default _MAX_LOG_ENTRIES is 10."""
        assert _MAX_LOG_ENTRIES == 10

    def test_set_activity_without_previous(self):
        """First set_activity should not crash (no previous to close)."""
        reporter = ProgressReporter(5)

        reporter.set_activity("First activity")
        assert reporter._current_activity == "First activity"
        assert list(reporter._activity_log) == []

    def test_close_activity_noop_when_empty(self):
        """_close_activity on empty state is a no-op."""
        reporter = ProgressReporter(5)

        reporter._close_activity()
        assert list(reporter._activity_log) == []
        assert reporter._current_activity == ""

    def test_update_marks_failed_activity(self):
        """update() with success=False prepends fail marker to activity label."""
        reporter = ProgressReporter(5)

        reporter.set_activity("Reading page example.com/blocked")
        reporter.update("https://example.com/blocked", success=False)

        assert len(reporter._activity_log) == 1
        label = reporter._activity_log[0][1]
        assert label.startswith("\u274c FAILED")
        assert "Reading page example.com/blocked" in label

    def test_update_success_no_fail_marker(self):
        """update() with success=True does NOT add fail marker."""
        reporter = ProgressReporter(5)

        reporter.set_activity("Reading page example.com/ok")
        reporter.update("https://example.com/ok", success=True)

        assert len(reporter._activity_log) == 1
        label = reporter._activity_log[0][1]
        assert not label.startswith("\u274c")

    def test_eta_remaining_seconds_none_before_first_update(self):
        """Returns None when no pages have been processed yet."""
        reporter = ProgressReporter(10)

        assert reporter.eta_remaining_seconds() is None

    def test_eta_remaining_seconds_returns_float_after_first_update(self):
        """Returns a non-negative float after at least one page is processed."""
        reporter = ProgressReporter(10)
        reporter.update("https://example.com/a", success=True)

        result = reporter.eta_remaining_seconds()
        assert result is not None
        assert isinstance(result, float)
        assert result >= 0.0

    def test_eta_remaining_seconds_zero_when_all_done(self):
        """Returns 0.0 when all pages are processed (total == count)."""
        reporter = ProgressReporter(2)
        reporter.update("https://example.com/a", success=True)
        reporter.update("https://example.com/b", success=True)

        result = reporter.eta_remaining_seconds()
        assert result == 0.0

    def test_eta_remaining_seconds_returns_proportional_estimate(self):
        """Returns elapsed/count * remaining_pages as a raw float."""
        reporter = ProgressReporter(10)
        reporter.count = 1
        reporter._start_time = time.time() - 2.0  # simulate 2s elapsed

        result = reporter.eta_remaining_seconds()
        # elapsed≈2, count=1, remaining_pages=9 → raw≈18.0
        assert result is not None
        assert isinstance(result, float)
        assert 16.0 <= result <= 20.0  # allow for slight timing variation


class TestActivityLogDisk:
    """Tests for flushing the activity log to disk (TXT + CSV)."""

    def test_activity_logger_writes_txt_and_csv(self, tmp_path: Path):
        logger = ActivityLogger(
            log_dir=tmp_path,
            round_label="First pass",
            icon_for_label=lambda _label: "*",
            format_duration=lambda _duration: "0.1s",
        )

        logger.append(datetime(2026, 1, 2, 3, 4, 5), "Reading page", 0.123)
        logger.close()

        txt_path = tmp_path / _ACTIVITY_LOG_TXT_FILE
        assert "[First pass] * Reading page (0.1s)" in txt_path.read_text(encoding="utf-8")

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        with csv_path.open(encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == _ACTIVITY_LOG_CSV_HEADER.split(",")
        assert rows[1] == ["2026-01-02T03:04:05", "First pass", "Reading page", "0.123"]

    def test_activity_log_appends_txt_to_disk(self, tmp_path: Path):
        """Closing an activity writes a human-readable line to activity_log.txt."""
        reporter = ProgressReporter(5, round_label="First pass", log_dir=tmp_path)
        reporter.set_activity("Reading page example.com")
        time.sleep(0.05)
        reporter.set_activity("Saving page content")  # closes previous
        reporter.close()

        txt_path = tmp_path / _ACTIVITY_LOG_TXT_FILE
        assert txt_path.exists()
        lines = txt_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        line = lines[0]
        assert "[First pass]" in line
        assert "\U0001f310" in line  # 🌐 crawl icon
        assert "Reading page example.com" in line
        # Duration in parentheses at end
        assert line.endswith(")")
        assert "Saving page content" in lines[1]

    def test_activity_log_appends_csv_to_disk(self, tmp_path: Path):
        """Closing an activity writes a CSV row to activity_log.csv."""
        reporter = ProgressReporter(5, round_label="First pass", log_dir=tmp_path)
        reporter.set_activity("Reading page example.com")
        time.sleep(0.05)
        reporter.set_activity("Saving page content")  # closes previous
        reporter.close()

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        assert csv_path.exists()
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))
        assert len(reader) == 3  # header + 2 data rows
        assert reader[0] == _ACTIVITY_LOG_CSV_HEADER.split(",")
        row = reader[1]
        assert row[1] == "First pass"
        assert row[2] == "Reading page example.com"
        assert float(row[3]) >= 0.0  # duration is a valid float
        assert reader[2][2] == "Saving page content"

    def test_csv_header_written_once(self, tmp_path: Path):
        """Multiple activities produce only one CSV header row."""
        reporter = ProgressReporter(10, log_dir=tmp_path)
        for i in range(4):
            reporter.set_activity(f"Activity {i}")
        reporter.close()

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))
        # 1 header + 4 data rows
        assert len(reader) == 5
        header_rows = [r for r in reader if r == _ACTIVITY_LOG_CSV_HEADER.split(",")]
        assert len(header_rows) == 1

    def test_existing_csv_header_not_rewritten(self, tmp_path: Path):
        """Appending to an existing CSV log does not duplicate its header."""
        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        csv_path.write_text(_ACTIVITY_LOG_CSV_HEADER + "\n", encoding="utf-8")

        reporter = ProgressReporter(10, log_dir=tmp_path)
        for i in range(3):
            reporter.set_activity(f"Activity {i}")
        reporter.close()

        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))

        header_rows = [r for r in reader if r == _ACTIVITY_LOG_CSV_HEADER.split(",")]
        assert len(reader) == 4
        assert len(header_rows) == 1

    def test_disk_log_keeps_handles_open_between_entries(self, tmp_path: Path):
        """Repeated activity writes reuse one TXT and one CSV file handle."""
        open_calls: list[str] = []
        original_open = Path.open

        def counting_open(path: Path, *args, **kwargs):
            if path.name in {_ACTIVITY_LOG_TXT_FILE, _ACTIVITY_LOG_CSV_FILE}:
                open_calls.append(path.name)
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", counting_open):
            reporter = ProgressReporter(20, log_dir=tmp_path)
            for i in range(_ACTIVITY_LOG_FLUSH_EVERY + 2):
                reporter.set_activity(f"Activity {i}")
            reporter.close()

        assert open_calls.count(_ACTIVITY_LOG_TXT_FILE) == 1
        assert open_calls.count(_ACTIVITY_LOG_CSV_FILE) == 1

    def test_disk_log_unlimited(self, tmp_path: Path):
        """Disk logs capture all activities even when in-memory list is capped."""
        reporter = ProgressReporter(20, max_log_entries=3, log_dir=tmp_path)
        for i in range(5):
            reporter.set_activity(f"Activity {i}")
        reporter.close()

        # In-memory log is capped at 3
        assert len(reporter._activity_log) == 3

        # Disk has all 5
        txt_path = tmp_path / _ACTIVITY_LOG_TXT_FILE
        txt_lines = txt_path.read_text(encoding="utf-8").splitlines()
        assert len(txt_lines) == 5

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))
        assert len(reader) == 6  # 1 header + 5 data rows

    def test_no_files_when_log_dir_none(self, tmp_path: Path):
        """Default (log_dir=None) creates no disk files."""
        reporter = ProgressReporter(5)
        reporter.set_activity("Reading page something")
        time.sleep(0.01)
        reporter.set_activity("Saving page content")
        reporter.close()

        # No activity log files anywhere
        assert not (tmp_path / _ACTIVITY_LOG_TXT_FILE).exists()
        assert not (tmp_path / _ACTIVITY_LOG_CSV_FILE).exists()

    def test_csv_escapes_commas_in_labels(self, tmp_path: Path):
        """Labels containing commas are properly CSV-escaped."""
        label = "Reading page example.com/a,b,c"
        reporter = ProgressReporter(5, log_dir=tmp_path)
        reporter.set_activity(label)
        time.sleep(0.01)
        reporter.close()

        csv_path = tmp_path / _ACTIVITY_LOG_CSV_FILE
        with csv_path.open(encoding="utf-8", newline="") as fh:
            reader = list(csv.reader(fh))
        assert len(reader) == 2
        assert reader[1][2] == label  # csv.reader correctly unescapes


class TestShortenUrl:
    """Tests for the _shorten_url() helper in crawler.py."""

    def test_short_url_unchanged(self):
        from crawl4md.crawler import _shorten_url

        url = "https://example.com/page"
        assert _shorten_url(url) == url

    def test_long_url_truncated(self):
        from crawl4md.crawler import _shorten_url

        url = "https://example.com/" + "a" * 80
        result = _shorten_url(url)
        assert len(result) <= 60
        assert "\u2026" in result  # ellipsis

    def test_scheme_stripped_before_truncation(self):
        from crawl4md.crawler import _shorten_url

        # Just over threshold with scheme, under without
        url = "https://" + "x" * 55
        result = _shorten_url(url)
        assert not result.startswith("https://")


class TestFriendlyEta:
    """Tests for _eta_remaining_friendly()."""

    def test_no_pages_returns_placeholder(self):
        reporter = ProgressReporter(10)
        result = reporter._eta_remaining_friendly()
        assert result == "estimating..."

    def test_less_than_a_minute(self):
        reporter = ProgressReporter(10)
        reporter.count = 9
        reporter._start_time = time.time() - 9  # 1s per page, ~1s left
        result = reporter._eta_remaining_friendly()
        assert result == "Less than a minute left"

    def test_minutes_pluralised(self):
        reporter = ProgressReporter(10)
        reporter.count = 2
        reporter._start_time = time.time() - 120  # 60s per page, ~4 min left
        result = reporter._eta_remaining_friendly()
        assert "minutes" in result
        assert result.startswith("About")

    def test_hours_included(self):
        reporter = ProgressReporter(100)
        reporter.count = 1
        reporter._start_time = time.time() - 3600  # 1h per page, 99h left
        result = reporter._eta_remaining_friendly()
        assert "hour" in result


class TestPagesPerMinute:
    """Tests for the pages-per-minute rate in terminal output."""

    def test_rate_shown_after_min_pages(self, capsys):
        reporter = ProgressReporter(10)
        reporter.count = _RATE_MIN_PAGES - 1
        reporter._round_success = _RATE_MIN_PAGES - 1
        reporter._start_time = time.time() - 60  # 60s elapsed
        reporter.update("https://example.com/x", success=True)  # count reaches min
        out = capsys.readouterr().out
        assert "pages/min" in out

    def test_rate_not_shown_before_min_pages(self, capsys):
        reporter = ProgressReporter(10)
        reporter._start_time = time.time() - 60
        reporter.update("https://example.com/x", success=True)  # count == 1
        out = capsys.readouterr().out
        assert "pages/min" not in out
