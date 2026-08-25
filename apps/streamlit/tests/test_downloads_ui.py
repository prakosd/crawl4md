from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app_support import downloads_ui


class _State(dict):
    """A session_state stand-in supporting both attribute and item access."""

    __getattr__ = dict.get  # type: ignore[assignment]
    __setattr__ = dict.__setitem__  # type: ignore[assignment]


# Risk: importing a history zip must replace in place, flag the success toast, and
# bust the file-listing caches so the panel repopulates. Type: unit.
def test_import_uploaded_history_zip_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = MagicMock()
    fake_st.session_state = _State()
    list_cache = MagicMock()
    tree_cache = MagicMock()
    monkeypatch.setattr(downloads_ui, "st", fake_st)
    monkeypatch.setattr(
        downloads_ui, "get_settings", lambda: SimpleNamespace(zip_signing_secret="k")
    )
    monkeypatch.setattr(downloads_ui, "_session_root", lambda: Path("/session"))
    monkeypatch.setattr(
        downloads_ui, "import_history_zip", lambda root, data, secret: "search_history"
    )
    monkeypatch.setattr(downloads_ui, "_cached_list_generated_files", list_cache)
    monkeypatch.setattr(downloads_ui, "_cached_download_tree", tree_cache)

    downloads_ui._import_uploaded_history_zip(b"zip")

    assert fake_st.session_state["upload_done_folder"] == "search_history"
    assert fake_st.session_state["upload_dialog_open"] is False
    list_cache.clear.assert_called_once()
    tree_cache.clear.assert_called_once()
    fake_st.rerun.assert_called_once()


# Risk: a rejected history import (bad signature / foreign folder) must not flag a
# success toast, but must still close the dialog. Type: unit.
def test_import_uploaded_history_zip_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_st = MagicMock()
    fake_st.session_state = _State()
    monkeypatch.setattr(downloads_ui, "st", fake_st)
    monkeypatch.setattr(
        downloads_ui, "get_settings", lambda: SimpleNamespace(zip_signing_secret="k")
    )
    monkeypatch.setattr(downloads_ui, "_session_root", lambda: Path("/session"))
    monkeypatch.setattr(downloads_ui, "import_history_zip", lambda root, data, secret: None)

    downloads_ui._import_uploaded_history_zip(b"zip")

    assert "upload_done_folder" not in fake_st.session_state
    assert fake_st.session_state["upload_dialog_open"] is False
    fake_st.rerun.assert_called_once()


# Risk: the preview modal shows file timestamps; a bad epoch must not crash the
# dialog. Verify the UTC formatter returns a stable string. Type: unit.
def test_format_preview_timestamp_utc_formats_epoch() -> None:
    assert downloads_ui._format_preview_timestamp_utc(0) == "1970-01-01 00:00:00 UTC"


# Risk: a missing timestamp must render as "no value" rather than raising.
# Type: unit.
def test_format_preview_timestamp_utc_none_returns_none() -> None:
    assert downloads_ui._format_preview_timestamp_utc(None) is None


# Risk: an out-of-range timestamp (e.g. corrupt stat) must be swallowed, not
# crash the preview dialog. Type: unit.
def test_format_preview_timestamp_utc_out_of_range_returns_none() -> None:
    assert downloads_ui._format_preview_timestamp_utc(1e300) is None


# Risk: after a browser reset clears the session, the session folder does not yet
# exist and holds no files; the panel must still show so Import is reachable.
# Type: unit.
def test_should_show_files_panel_idle_shows_even_without_files() -> None:
    assert downloads_ui._should_show_files_panel(job_alive=False, has_files=False) is True
    assert downloads_ui._should_show_files_panel(job_alive=False, has_files=True) is True


# Risk: an empty panel must not flash mid-write; while a job runs, show the panel
# only once it holds files. Type: unit.
def test_should_show_files_panel_hides_empty_panel_during_active_job() -> None:
    assert downloads_ui._should_show_files_panel(job_alive=True, has_files=False) is False
    assert downloads_ui._should_show_files_panel(job_alive=True, has_files=True) is True
