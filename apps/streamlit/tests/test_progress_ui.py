from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app_support import progress_ui


# Risk: activity-log lines are rendered as raw HTML; unescaped markup would be an
# injection vector. Verify HTML is escaped. Type: unit.
def test_linkify_log_line_escapes_html() -> None:
    result = progress_ui._linkify_log_line("<script>alert(1)</script>")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


# Risk: URLs in the log should become safe new-tab links (noopener). Type: unit.
def test_linkify_log_line_wraps_urls_as_safe_links() -> None:
    result = progress_ui._linkify_log_line("see https://example.com/x for details")
    assert '<a href="https://example.com/x"' in result
    assert 'target="_blank"' in result
    assert 'rel="noopener noreferrer"' in result


# Risk: every Step 1 progress metric shows a leading icon (Streamlit 1.61 icon=)
# so the cards stay scannable. Type: unit.
def test_render_progress_metrics_all_have_icons(monkeypatch: pytest.MonkeyPatch) -> None:
    class _State(dict):
        __getattr__ = dict.get  # type: ignore[assignment]

    fake_st = MagicMock()
    fake_st.session_state = _State(language="EN", started_at=None, job_state="completed")
    monkeypatch.setattr(progress_ui, "st", fake_st)

    progress_ui.render_progress_and_files(
        processed=1, successful=1, failed=0, discovered=2, limit=10, state="completed"
    )

    column_metric = fake_st.columns.return_value.__getitem__.return_value.metric
    column_icons = [call.kwargs.get("icon") for call in column_metric.call_args_list]
    assert column_icons and all(column_icons)
    # A non-running state renders through st.metric with the status emoji as icon.
    state_icons = [call.kwargs.get("icon") for call in fake_st.metric.call_args_list]
    assert state_icons and all(state_icons)


# Risk: a progress event must update the per-chunk counters that drive the bar and
# caption. Type: unit.
def test_apply_vector_index_event_progress_sets_chunk_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace()
    monkeypatch.setattr(progress_ui.st, "session_state", state)

    progress_ui._apply_vector_index_event(
        {"event": "progress", "processed_chunks": 3, "total_chunks": 10}
    )

    assert state.vector_index_state == "running"
    assert state.vector_index_progress == {"processed": 3, "total": 10}


# Risk: a stage-only progress event must set the stage (for the indeterminate
# caption) without overwriting chunk counts. Type: unit.
def test_apply_vector_index_event_progress_sets_stage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace()
    monkeypatch.setattr(progress_ui.st, "session_state", state)

    progress_ui._apply_vector_index_event({"event": "progress", "stage": "embedding"})

    assert state.vector_index_stage == "embedding"
    assert not hasattr(state, "vector_index_progress")


# Risk: a terminal event must capture the final counts into the result panel.
# Type: unit.
def test_apply_vector_index_event_terminal_builds_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = SimpleNamespace()
    monkeypatch.setattr(progress_ui.st, "session_state", state)

    progress_ui._apply_vector_index_event(
        {
            "event": "completed",
            "indexed_file_count": 2,
            "indexed_chunk_count": 40,
            "skipped_file_count": 1,
            "warnings": [],
            "errors": [],
        }
    )

    assert state.vector_index_state == "completed"
    assert state.vector_index_result["state"] == "completed"
    assert state.vector_index_result["indexed_file_count"] == 2
    assert state.vector_index_result["indexed_chunk_count"] == 40
    assert state.vector_index_result["skipped_file_count"] == 1
