from __future__ import annotations

import io
import os
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app_support.generated_files import (
    GeneratedFile,
    ReadyDownload,
    build_download_tree,
    build_folder_zip_bytes,
    build_ready_download,
    collapse_artifact_run_folder,
    collect_success_content_files,
    delete_generated_folder,
    download_folder_icon,
    download_tree_entry_sort_key,
    files_excluding,
    find_latest_crawl_dir,
    find_ready_download_in_session,
    find_site_graph_file,
    find_site_graph_for_result,
    folder_zip_cache_token,
    format_file_size,
    format_run_timestamp_label,
    generated_file_sort_key,
    generated_files_cache_token,
    import_signed_zip,
    import_target_name,
    is_history_folder,
    is_run_folder,
)

_MODIFIED_AT = datetime(2026, 5, 17, 10, 0, tzinfo=timezone.utc)


def _generated_file(relative_path: str) -> GeneratedFile:
    return GeneratedFile(
        path=Path(relative_path),
        relative_path=relative_path,
        name=Path(relative_path).name,
        size_bytes=10,
        modified_at=_MODIFIED_AT,
        file_type="md",
        download_allowed=True,
    )


def test_build_download_tree_nests_generated_files_by_relative_path() -> None:
    root_file = _generated_file("summary.md")
    nested_file = _generated_file("crawl_run/final/content.md")

    tree = build_download_tree([nested_file, root_file])

    assert tree["summary.md"] == root_file
    assert tree["crawl_run"]["final"]["content.md"] == nested_file


def test_files_excluding_drops_only_the_named_path() -> None:
    log_file = _generated_file("logs/app.log")
    content_file = _generated_file("crawl_run/final/content.md")

    remaining = files_excluding([content_file, log_file], "logs/app.log")

    assert remaining == [content_file]
    # The tree built from the remaining files must not contain the excluded log,
    # so its preview widget key is not created a second time.
    assert "logs" not in build_download_tree(remaining)


def test_files_excluding_keeps_all_when_path_is_none() -> None:
    content_file = _generated_file("crawl_run/final/content.md")
    log_file = _generated_file("logs/app.log")

    assert files_excluding([content_file, log_file], None) == [content_file, log_file]


def test_collapse_artifact_run_folder_merges_single_timestamp_child() -> None:
    local_timezone = timezone(timedelta(hours=10), "AEST")
    crawl_tree = {
        "2026-05-19_18-17-52": {
            "final": {"content.md": _generated_file("crawl_1/final/content.md")},
            "round_1": {},
        }
    }

    label, folder_node = collapse_artifact_run_folder(
        "crawl_1_parlor",
        crawl_tree,
        local_timezone=local_timezone,
    )

    assert label == "crawl_1_parlor/2026-05-19_18-17-52 (20 May 2026 04:17 AEST)"
    assert folder_node == crawl_tree["2026-05-19_18-17-52"]


def test_collapse_artifact_run_folder_keeps_folder_when_not_single_timestamp_child() -> None:
    crawl_tree = {
        "2026-05-19_18-17-52": {},
        "2026-05-19_18-17-53": {},
    }

    label, folder_node = collapse_artifact_run_folder("crawl_1_parlor", crawl_tree)

    assert label == "crawl_1_parlor"
    assert folder_node == crawl_tree


def test_collapse_artifact_run_folder_keeps_non_timestamp_child() -> None:
    crawl_tree = {"final": {"content.md": _generated_file("crawl_1/final/content.md")}}

    label, folder_node = collapse_artifact_run_folder("crawl_1_parlor", crawl_tree)

    assert label == "crawl_1_parlor"
    assert folder_node == crawl_tree


def test_collapse_artifact_run_folder_merges_vector_timestamp_child() -> None:
    local_timezone = timezone(timedelta(hours=10), "AEST")
    vector_tree = {
        "2026-05-19_18-17-52": {
            "chroma": {
                "chroma.sqlite3": _generated_file(
                    "vector_1/2026-05-19_18-17-52/chroma/chroma.sqlite3"
                )
            },
            "manifest.json": _generated_file("vector_1/2026-05-19_18-17-52/manifest.json"),
        }
    }

    label, folder_node = collapse_artifact_run_folder(
        "vector_01_pentagram",
        vector_tree,
        local_timezone=local_timezone,
    )

    assert label == "vector_01_pentagram/2026-05-19_18-17-52 (20 May 2026 04:17 AEST)"
    assert folder_node == vector_tree["2026-05-19_18-17-52"]


def test_download_folder_icon_maps_artifact_type_to_material_icon() -> None:
    assert download_folder_icon("crawl_1_parlor") == ":material/travel_explore:"
    assert download_folder_icon("vector_01_pentagram") == ":material/database:"
    assert download_folder_icon("search_history") == ":material/search:"
    assert download_folder_icon("final") == ":material/folder_open:"
    assert download_folder_icon("2026-05-19_18-17-52") == ":material/folder_open:"


def test_generated_file_sort_key_orders_numbered_crawl_runs_descending() -> None:
    paths = [
        "crawl_01_boulder/final/content.md",
        "crawl_10_river/final/content.md",
        "summary.md",
        "crawl_2_cedar/final/content.md",
    ]

    assert sorted(paths, key=generated_file_sort_key) == [
        "crawl_10_river/final/content.md",
        "crawl_2_cedar/final/content.md",
        "crawl_01_boulder/final/content.md",
        "summary.md",
    ]


def test_download_tree_entry_sort_key_orders_top_level_crawl_folders_descending() -> None:
    entries = {
        "crawl_01_boulder": {},
        "crawl_10_river": {},
        "summary.md": _generated_file("summary.md"),
        "notes": {},
    }

    assert [
        name
        for name, entry in sorted(
            entries.items(),
            key=lambda item: download_tree_entry_sort_key(item[0], item[1], top_level=True),
        )
    ] == ["crawl_10_river", "crawl_01_boulder", "notes", "summary.md"]


def test_download_tree_entry_sort_key_orders_vector_folders_after_crawl_newest_first() -> None:
    entries = {
        "crawl_02_river": {},
        "vector_01_alpha": {},
        "vector_10_omega": {},
        "summary.md": _generated_file("summary.md"),
    }

    assert [
        name
        for name, entry in sorted(
            entries.items(),
            key=lambda item: download_tree_entry_sort_key(item[0], item[1], top_level=True),
        )
    ] == ["crawl_02_river", "vector_10_omega", "vector_01_alpha", "summary.md"]


def test_format_run_timestamp_label_prefers_progress_history_timestamp(tmp_path: Path) -> None:
    local_timezone = timezone(timedelta(hours=10), "AEST")
    progress_path = tmp_path / "progress_history.jsonl"
    progress_path.write_text(
        '{"timestamp":"2026-06-01T03:58:32+00:00"}\n',
        encoding="utf-8",
    )
    progress_file = GeneratedFile(
        path=progress_path,
        relative_path="crawl_01_boulder/2026-01-01_00-00-00/progress_history.jsonl",
        name="progress_history.jsonl",
        size_bytes=progress_path.stat().st_size,
        modified_at=_MODIFIED_AT,
        file_type="jsonl",
        download_allowed=True,
    )

    assert (
        format_run_timestamp_label(
            "2026-01-01_00-00-00",
            {"progress_history.jsonl": progress_file},
            local_timezone=local_timezone,
        )
        == "2026-01-01_00-00-00 (1 June 2026 13:58 AEST)"
    )


def test_generated_files_cache_token_handles_missing_path(tmp_path: Path) -> None:
    assert generated_files_cache_token(tmp_path / "missing") == (0.0, 0)


@pytest.mark.parametrize(
    ("size_bytes", "expected"),
    [
        (410, "0.4 KB"),
        (0, "0.0 KB"),
        (1024, "1.0 KB"),
        (int(5.9 * 1024 * 1024), "5.9 MB"),
        (2 * 1024 * 1024 * 1024, "2.0 GB"),
    ],
)
def test_format_file_size_picks_readable_unit(size_bytes: int, expected: str) -> None:
    assert format_file_size(size_bytes) == expected


def test_generated_files_cache_token_reflects_path_stat(tmp_path: Path) -> None:
    output_path = tmp_path / "session"
    output_path.mkdir()

    first_token = generated_files_cache_token(output_path)
    next_mtime = first_token[0] + 10
    os.utime(output_path, (next_mtime, next_mtime))
    second_token = generated_files_cache_token(output_path)

    assert second_token[0] > first_token[0]
    assert second_token[1] == first_token[1]


def test_import_target_name_advances_sequence_keeping_kind_and_word(tmp_path: Path) -> None:
    (tmp_path / "crawl_01_river").mkdir()
    (tmp_path / "crawl_02_lake").mkdir()
    (tmp_path / "vector_01_alpha").mkdir()

    assert import_target_name(tmp_path, "crawl_02_lake") == "crawl_03_lake"
    assert import_target_name(tmp_path, "vector_01_alpha") == "vector_02_alpha"
    assert import_target_name(tmp_path, "random_export") == "import_01_upload"


def test_import_target_name_works_when_session_folder_does_not_exist(tmp_path: Path) -> None:
    # Risk: in a fresh browser session the session folder does not yet exist;
    # import_target_name must not raise FileNotFoundError. Type: regression.
    session = tmp_path / "session_new"
    assert not session.exists()

    # Should return sequence 01 for all kinds without crashing.
    assert import_target_name(session, "crawl_01_river") == "crawl_01_river"
    assert import_target_name(session, "random_export") == "import_01_upload"


def test_import_signed_zip_roundtrip_extracts_to_new_folder(tmp_path: Path) -> None:
    session = tmp_path / "session"
    run = session / "crawl_01_river" / "final"
    run.mkdir(parents=True)
    (run / "page.md").write_text("hello", encoding="utf-8")
    signed = build_folder_zip_bytes(session, "crawl_01_river", signing_secret="k")

    new_name = import_signed_zip(session, signed, "k")

    assert new_name == "crawl_02_river"
    assert (session / "crawl_02_river" / "final" / "page.md").read_text(encoding="utf-8") == "hello"


def test_import_signed_zip_rejects_wrong_secret(tmp_path: Path) -> None:
    session = tmp_path / "session"
    (session / "crawl_01_river").mkdir(parents=True)
    (session / "crawl_01_river" / "a.md").write_text("x", encoding="utf-8")
    signed = build_folder_zip_bytes(session, "crawl_01_river", signing_secret="k")

    assert import_signed_zip(session, signed, "other") is None


# ── delete_generated_folder ────────────────────────────────────────────────


def test_is_run_folder_detects_crawl_and_vector_prefixes() -> None:
    assert is_run_folder("crawl_01_boulder") is True
    assert is_run_folder("vector_01_pentagram") is True
    assert is_run_folder("final") is False
    assert is_run_folder("2026-05-17_10-00-00") is False


def test_is_history_folder_detects_search_and_basic_rag_qa_history() -> None:
    assert is_history_folder("search_history") is True
    assert is_history_folder("basic_rag_qa_history") is True
    # Run folders and plain folders are not history folders.
    assert is_history_folder("crawl_01_boulder") is False
    assert is_history_folder("vector_01_pentagram") is False
    assert is_history_folder("final") is False


def test_find_site_graph_file_locates_nested_site_graph() -> None:
    files = [
        _generated_file("crawl_01/2026-05-17_10-00-00/logs/site_graph.jsonl"),
        _generated_file("crawl_01/2026-05-17_10-00-00/final/sorted_success_content_001.md"),
    ]
    tree = build_download_tree(files)

    found = find_site_graph_file(tree["crawl_01"])

    assert found is not None
    assert found.name == "site_graph.jsonl"
    assert found.relative_path == "crawl_01/2026-05-17_10-00-00/logs/site_graph.jsonl"


def test_find_site_graph_file_returns_none_when_absent() -> None:
    files = [_generated_file("vector_01/manifest.json")]
    tree = build_download_tree(files)

    assert find_site_graph_file(tree["vector_01"]) is None


# Risk: the ready-result panel needs the crawl run's site graph from a download's
# relative path (``<crawl>/<ts>/...``). Verify it resolves the run's logs graph.
# Type: unit.
def test_find_site_graph_for_result_locates_run_logs(tmp_path: Path) -> None:
    graph = tmp_path / "crawl_01_river" / "2026-05-17_10-00-00" / "logs" / "site_graph.jsonl"
    graph.parent.mkdir(parents=True)
    graph.write_text("{}\n", encoding="utf-8")

    found = find_site_graph_for_result(
        tmp_path, "crawl_01_river/2026-05-17_10-00-00/final/success_content.zip"
    )

    assert found is not None
    assert found.relative_path == "crawl_01_river/2026-05-17_10-00-00/logs/site_graph.jsonl"


# Risk: a crawl that predates site graphs (or any missing graph) must yield no
# button rather than a broken one. Verify a None result. Type: unit.
def test_find_site_graph_for_result_returns_none_when_absent(tmp_path: Path) -> None:
    (tmp_path / "crawl_01_river" / "2026-05-17_10-00-00").mkdir(parents=True)

    assert (
        find_site_graph_for_result(
            tmp_path, "crawl_01_river/2026-05-17_10-00-00/final/success_content.zip"
        )
        is None
    )


def test_delete_generated_folder_removes_folder_and_contents(tmp_path: Path) -> None:
    run_dir = tmp_path / "crawl_01" / "2026-05-17_10-00-00"
    run_dir.mkdir(parents=True)
    (run_dir / "content_001.md").write_text("data", encoding="utf-8")

    deleted = delete_generated_folder(tmp_path, "crawl_01")

    assert deleted is True
    assert not (tmp_path / "crawl_01").exists()
    assert tmp_path.exists()


def test_delete_generated_folder_prunes_empty_parents(tmp_path: Path) -> None:
    nested = tmp_path / "crawl_01" / "2026-05-17_10-00-00" / "final"
    nested.mkdir(parents=True)
    (nested / "content.md").write_text("data", encoding="utf-8")

    deleted = delete_generated_folder(tmp_path, "crawl_01/2026-05-17_10-00-00/final")

    assert deleted is True
    # The emptied run and crawl folders are pruned up to the session root.
    assert not (tmp_path / "crawl_01").exists()
    assert tmp_path.exists()


def test_delete_generated_folder_returns_false_for_session_root(tmp_path: Path) -> None:
    assert delete_generated_folder(tmp_path, "") is False
    assert tmp_path.exists()


def test_delete_generated_folder_returns_false_when_missing(tmp_path: Path) -> None:
    assert delete_generated_folder(tmp_path, "crawl_01") is False


def test_delete_generated_folder_returns_false_for_file_target(tmp_path: Path) -> None:
    (tmp_path / "summary.md").write_text("x", encoding="utf-8")

    assert delete_generated_folder(tmp_path, "summary.md") is False
    assert (tmp_path / "summary.md").exists()


def test_delete_generated_folder_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        delete_generated_folder(tmp_path, "../outside_dir")


# ── collect_success_content_files ────────────────────────────────────────────


def _make_final_dir(root: Path) -> Path:
    final = root / "final"
    final.mkdir(parents=True)
    return final


def test_collect_prefers_sorted_success_files(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    sorted_f = final / "sorted_success_content_001_of_001.md"
    unsorted_f = final / "success_content_001.md"
    sorted_f.write_text("sorted", encoding="utf-8")
    unsorted_f.write_text("unsorted", encoding="utf-8")

    result = collect_success_content_files(tmp_path, tmp_path)

    assert result == [sorted_f]


def test_collect_falls_back_to_unsorted_success_files(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    content_f = final / "success_content_001.md"
    content_f.write_text("content", encoding="utf-8")

    result = collect_success_content_files(tmp_path, tmp_path)

    assert result == [content_f]


def test_collect_excludes_zip_from_fallback(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    content_f = final / "success_content_001.md"
    zip_f = final / "success_content.zip"
    content_f.write_text("content", encoding="utf-8")
    zip_f.write_bytes(b"PK")

    result = collect_success_content_files(tmp_path, tmp_path)

    assert result == [content_f]


def test_collect_returns_empty_when_no_final_dir(tmp_path: Path) -> None:
    assert collect_success_content_files(tmp_path, tmp_path) == []


def test_collect_returns_empty_for_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "session"
    root.mkdir()

    assert collect_success_content_files(outside, root) == []


# ── build_ready_download ─────────────────────────────────────────────────────


def test_build_ready_download_returns_none_when_no_success_files(tmp_path: Path) -> None:
    _make_final_dir(tmp_path)

    assert build_ready_download(tmp_path, tmp_path) is None


def test_build_ready_download_returns_single_file_directly(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    content_f = final / "sorted_success_content_001_of_001.md"
    content_f.write_text("# Page", encoding="utf-8")

    result = build_ready_download(tmp_path, tmp_path)

    assert isinstance(result, ReadyDownload)
    assert result.source_count == 1
    assert result.file.path == content_f
    assert result.file.file_type == "md"
    assert not (final / "success_content.zip").exists()


def test_build_ready_download_creates_zip_for_multiple_files(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    (final / "sorted_success_content_001_of_002.md").write_text("# A", encoding="utf-8")
    (final / "sorted_success_content_002_of_002.md").write_text("# B", encoding="utf-8")

    result = build_ready_download(tmp_path, tmp_path)

    assert isinstance(result, ReadyDownload)
    assert result.source_count == 2
    assert result.file.name == "success_content.zip"
    assert result.file.file_type == "zip"
    assert (final / "success_content.zip").exists()


def test_build_ready_download_reuses_zip_when_up_to_date(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    (final / "sorted_success_content_001_of_002.md").write_text("# A", encoding="utf-8")
    (final / "sorted_success_content_002_of_002.md").write_text("# B", encoding="utf-8")
    build_ready_download(tmp_path, tmp_path)
    zip_path = final / "success_content.zip"
    future_mtime = zip_path.stat().st_mtime + 100
    os.utime(zip_path, (future_mtime, future_mtime))

    build_ready_download(tmp_path, tmp_path)

    assert zip_path.stat().st_mtime == future_mtime


def test_build_ready_download_respects_download_limit(tmp_path: Path) -> None:
    final = _make_final_dir(tmp_path)
    content_f = final / "sorted_success_content_001_of_001.md"
    content_f.write_bytes(b"x" * 20)

    result = build_ready_download(tmp_path, tmp_path, download_limit_bytes=10)

    assert result is not None
    assert result.file.download_allowed is False


def test_build_ready_download_returns_none_for_path_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "session"
    root.mkdir()

    assert build_ready_download(outside, root) is None


# ── find_ready_download_in_session ────────────────────────────────────────────


def _make_crawl_run(session_root: Path, crawl_name: str, run_name: str) -> Path:
    """Create crawl_name/run_name/final/ structure and return the run dir."""
    run_dir = session_root / crawl_name / run_name
    (run_dir / "final").mkdir(parents=True)
    return run_dir


def test_find_ready_download_in_session_returns_none_for_missing_root(tmp_path: Path) -> None:
    assert find_ready_download_in_session(tmp_path / "missing") is None


def test_find_ready_download_in_session_returns_none_when_no_crawl_dirs(tmp_path: Path) -> None:
    (tmp_path / "not_a_crawl").mkdir()

    assert find_ready_download_in_session(tmp_path) is None


def test_find_ready_download_in_session_returns_none_when_no_success_content(
    tmp_path: Path,
) -> None:
    _make_crawl_run(tmp_path, "crawl_1_word", "2026-05-20_12-00-00")

    assert find_ready_download_in_session(tmp_path) is None


def test_find_ready_download_in_session_returns_single_crawl_result(tmp_path: Path) -> None:
    run_dir = _make_crawl_run(tmp_path, "crawl_1_word", "2026-05-20_12-00-00")
    content = run_dir / "final" / "sorted_success_content_001_of_001.md"
    content.write_text("# Page", encoding="utf-8")

    result = find_ready_download_in_session(tmp_path)

    assert isinstance(result, ReadyDownload)
    assert result.file.path == content


def test_find_latest_crawl_dir_prefers_latest_utc_timestamp_slug(tmp_path: Path) -> None:
    older_run = _make_crawl_run(tmp_path, "crawl_01_word", "2026-05-20_10-00-00")
    newer_run = _make_crawl_run(tmp_path, "crawl_01_word", "2026-05-20_12-00-00")
    newer_mtime = older_run.stat().st_mtime - 100
    os.utime(newer_run, (newer_mtime, newer_mtime))

    assert find_latest_crawl_dir(tmp_path / "crawl_01_word") == newer_run


def test_find_ready_download_in_session_returns_highest_numbered_crawl(tmp_path: Path) -> None:
    lower_run = _make_crawl_run(tmp_path, "crawl_2_word", "2026-05-20_12-00-00")
    higher_run = _make_crawl_run(tmp_path, "crawl_10_other", "2026-05-20_10-00-00")
    (lower_run / "final" / "sorted_success_content_001_of_001.md").write_text(
        "lower",
        encoding="utf-8",
    )
    higher_content = higher_run / "final" / "sorted_success_content_001_of_001.md"
    higher_content.write_text("higher", encoding="utf-8")
    lower_mtime = higher_run.stat().st_mtime + 100
    os.utime(lower_run, (lower_mtime, lower_mtime))

    result = find_ready_download_in_session(tmp_path)

    assert result is not None
    assert result.file.path == higher_content


def test_find_ready_download_in_session_falls_back_to_older_crawl(tmp_path: Path) -> None:
    empty_run = _make_crawl_run(tmp_path, "crawl_2_empty", "2026-05-20_12-00-00")
    old_run = _make_crawl_run(tmp_path, "crawl_1_word", "2026-05-20_10-00-00")
    old_content = old_run / "final" / "sorted_success_content_001_of_001.md"
    old_content.write_text("content", encoding="utf-8")
    # Make empty_run clearly newer
    new_mtime = old_run.stat().st_mtime + 100
    os.utime(empty_run, (new_mtime, new_mtime))

    result = find_ready_download_in_session(tmp_path)

    assert result is not None
    assert result.file.path == old_content


# ── build_folder_zip_bytes / folder_zip_cache_token ──────────────────


def test_build_folder_zip_bytes_nests_all_files_under_folder_name(tmp_path: Path) -> None:
    run_dir = tmp_path / "crawl_01" / "2026-05-17_10-00-00"
    (run_dir / "final").mkdir(parents=True)
    (run_dir / "final" / "content.md").write_text("body", encoding="utf-8")
    (tmp_path / "crawl_01" / "notes.txt").write_text("note", encoding="utf-8")

    payload = build_folder_zip_bytes(tmp_path, "crawl_01")

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {
            "crawl_01/2026-05-17_10-00-00/final/content.md",
            "crawl_01/notes.txt",
        }
        assert archive.read("crawl_01/notes.txt") == b"note"


def test_build_folder_zip_bytes_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_folder_zip_bytes(tmp_path, "../outside")


def test_build_folder_zip_bytes_rejects_non_folder(tmp_path: Path) -> None:
    (tmp_path / "crawl_01").mkdir()
    (tmp_path / "crawl_01" / "file.md").write_text("x", encoding="utf-8")

    with pytest.raises(ValueError):
        build_folder_zip_bytes(tmp_path, "crawl_01/file.md")


def test_build_folder_zip_bytes_rejects_session_root(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        build_folder_zip_bytes(tmp_path, "")


def test_build_folder_zip_bytes_skips_symlinks(tmp_path: Path) -> None:
    run_dir = tmp_path / "crawl_01"
    run_dir.mkdir()
    (run_dir / "real.md").write_text("real", encoding="utf-8")
    secret = tmp_path.parent / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    try:
        (run_dir / "link.txt").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform")

    payload = build_folder_zip_bytes(tmp_path, "crawl_01")

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert archive.namelist() == ["crawl_01/real.md"]


def test_folder_zip_cache_token_changes_when_contents_change(tmp_path: Path) -> None:
    run_dir = tmp_path / "crawl_01"
    run_dir.mkdir()
    (run_dir / "a.md").write_text("a", encoding="utf-8")

    before = folder_zip_cache_token(tmp_path, "crawl_01")
    (run_dir / "b.md").write_text("bb", encoding="utf-8")
    after = folder_zip_cache_token(tmp_path, "crawl_01")

    assert before != after
    assert after[0] == 2


def test_folder_zip_cache_token_empty_for_missing_folder(tmp_path: Path) -> None:
    assert folder_zip_cache_token(tmp_path, "nope") == (0, 0.0, 0)
