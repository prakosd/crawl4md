from __future__ import annotations

import zipfile
from pathlib import Path

from vector_indexer import messages
from vector_indexer.document_loader import load_documents


def test_loads_md_and_txt_files(tmp_path: Path) -> None:
    md = tmp_path / "a.md"
    md.write_text("# heading", encoding="utf-8")
    txt = tmp_path / "b.txt"
    txt.write_text("plain text", encoding="utf-8")

    result = load_documents([md, txt])

    assert {doc.source for doc in result.documents} == {"a.md", "b.txt"}
    assert result.skipped_file_count == 0


def test_unsupported_file_is_skipped(tmp_path: Path) -> None:
    binary = tmp_path / "c.bin"
    binary.write_bytes(b"\x00\x01")

    result = load_documents([binary])

    assert result.documents == []
    assert result.skipped_file_count == 1
    assert result.warnings


def test_zip_contributes_only_md_and_txt(tmp_path: Path) -> None:
    zip_path = tmp_path / "input.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("keep.md", "markdown")
        archive.writestr("nested/keep.txt", "text")
        archive.writestr("skip.py", "code")

    result = load_documents([zip_path])

    sources = sorted(doc.source for doc in result.documents)
    assert sources == ["input.zip:keep.md", "input.zip:nested/keep.txt"]


def test_zip_without_text_members_warns(tmp_path: Path) -> None:
    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("only.py", "code")

    result = load_documents([zip_path])

    assert result.documents == []
    assert any(warning.code == messages.CODE_ARCHIVE_EMPTY for warning in result.warnings)
    assert any("No .md or .txt" in str(warning) for warning in result.warnings)


def test_unreadable_text_file_is_skipped_with_warning(tmp_path: Path) -> None:
    # A directory whose name ends in ".md" dispatches to the text loader, where
    # read_text raises OSError (IsADirectoryError) — the unreadable-file branch.
    fake = tmp_path / "looks_like.md"
    fake.mkdir()

    result = load_documents([fake])

    assert result.documents == []
    assert result.skipped_file_count == 1
    assert any(warning.code == messages.CODE_FILE_UNREADABLE for warning in result.warnings)


def test_corrupt_zip_is_skipped_with_warning(tmp_path: Path) -> None:
    zip_path = tmp_path / "bad.zip"
    zip_path.write_bytes(b"not a real zip archive")

    result = load_documents([zip_path])

    assert result.documents == []
    assert result.skipped_file_count == 1
    assert any(warning.code == messages.CODE_ARCHIVE_UNREADABLE for warning in result.warnings)
