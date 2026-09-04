from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pytest

from artifact_store.archives import (
    SIGNATURE_MEMBER,
    extract_all_members,
    extract_text_members,
    is_safe_member_name,
    iter_text_members,
    sign_zip_bytes,
    verify_zip_bytes,
)


def _make_zip(path: Path, members: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)


def _zip_bytes(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_is_safe_member_name_accepts_normal_paths() -> None:
    assert is_safe_member_name("notes.md")
    assert is_safe_member_name("sub/dir/notes.txt")


def test_is_safe_member_name_rejects_traversal_and_absolute() -> None:
    assert not is_safe_member_name("../escape.txt")
    assert not is_safe_member_name("/etc/passwd")
    assert not is_safe_member_name("C:/Windows/system.ini")
    assert not is_safe_member_name("dir/")
    assert not is_safe_member_name("")


def test_iter_text_members_keeps_only_supported_text_files(tmp_path: Path) -> None:
    zip_path = tmp_path / "input.zip"
    _make_zip(
        zip_path,
        {
            "keep.md": b"# md",
            "nested/keep.txt": b"txt",
            "skip.py": b"print()",
            "skip.json": b"{}",
        },
    )

    members = dict(iter_text_members(zip_path))

    assert set(members) == {"keep.md", "nested/keep.txt"}
    assert members["keep.md"] == b"# md"


def test_iter_text_members_skips_unsafe_members(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    zip_path = tmp_path / "evil.zip"
    _make_zip(
        zip_path,
        {
            "ok.md": b"ok",
            "../escape.md": b"bad",
        },
    )

    with caplog.at_level(logging.WARNING, logger="artifact_store"):
        members = dict(iter_text_members(zip_path))

    assert set(members) == {"ok.md"}
    assert any("unsafe zip member" in record.getMessage() for record in caplog.records)


def test_iter_text_members_skips_oversized_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("artifact_store.archives._MAX_MEMBER_BYTES", 8)
    zip_path = tmp_path / "bomb.zip"
    _make_zip(zip_path, {"small.md": b"hi", "huge.txt": b"x" * 4096})

    with caplog.at_level(logging.WARNING, logger="artifact_store"):
        members = dict(iter_text_members(zip_path))

    assert set(members) == {"small.md"}
    assert members["small.md"] == b"hi"
    assert any("oversized zip member" in record.getMessage() for record in caplog.records)


def test_extract_text_members_writes_only_supported_files(tmp_path: Path) -> None:
    zip_path = tmp_path / "input.zip"
    _make_zip(
        zip_path,
        {
            "a.md": b"a",
            "deep/b.txt": b"b",
            "c.bin": b"binary",
        },
    )
    dest = tmp_path / "out"

    written = extract_text_members(zip_path, dest)

    written_names = sorted(p.name for p in written)
    assert written_names == ["a.md", "b.txt"]
    assert (dest / "a.md").read_bytes() == b"a"
    assert (dest / "deep" / "b.txt").read_bytes() == b"b"
    assert not (dest / "c.bin").exists()


def test_extract_text_members_does_not_escape_destination(tmp_path: Path) -> None:
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"ok.md": b"ok", "../escape.txt": b"bad"})
    dest = tmp_path / "out"

    written = extract_text_members(zip_path, dest)

    assert [p.name for p in written] == ["ok.md"]
    assert not (tmp_path / "escape.txt").exists()


_SECRET = "shared-key"


def test_sign_then_verify_roundtrip() -> None:
    signed = sign_zip_bytes(_zip_bytes({"a.md": b"a", "data/b.bin": b"\x00\x01"}), _SECRET)
    assert SIGNATURE_MEMBER in zipfile.ZipFile(io.BytesIO(signed)).namelist()
    assert verify_zip_bytes(signed, _SECRET) is True


def test_verify_fails_with_wrong_secret() -> None:
    signed = sign_zip_bytes(_zip_bytes({"a.md": b"a"}), _SECRET)
    assert verify_zip_bytes(signed, "other-key") is False


def test_verify_fails_when_member_tampered() -> None:
    signed = sign_zip_bytes(_zip_bytes({"a.md": b"a"}), _SECRET)
    with zipfile.ZipFile(io.BytesIO(signed)) as src:
        sig = src.read(SIGNATURE_MEMBER)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as new:
        new.writestr("a.md", b"tampered")
        new.writestr(SIGNATURE_MEMBER, sig)
    assert verify_zip_bytes(out.getvalue(), _SECRET) is False


def test_verify_fails_without_signature_and_on_bad_zip() -> None:
    assert verify_zip_bytes(_zip_bytes({"a.md": b"a"}), _SECRET) is False
    assert verify_zip_bytes(b"not a zip", _SECRET) is False


def test_extract_all_members_keeps_binary_and_skips_sidecar(tmp_path: Path) -> None:
    signed = sign_zip_bytes(_zip_bytes({"a.md": b"a", "db/index.bin": b"\x00\xff"}), _SECRET)
    zip_path = tmp_path / "signed.zip"
    zip_path.write_bytes(signed)
    dest = tmp_path / "out"

    written = extract_all_members(zip_path, dest)

    assert sorted(p.name for p in written) == ["a.md", "index.bin"]
    assert (dest / "db" / "index.bin").read_bytes() == b"\x00\xff"
    assert not (dest / SIGNATURE_MEMBER).exists()


def test_extract_all_members_streams_large_member_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("artifact_store.archives._COPY_CHUNK_BYTES", 8)
    payload = bytes(range(256)) * 4  # spans many 8-byte streaming chunks
    zip_path = tmp_path / "store.zip"
    _make_zip(zip_path, {"chroma/data_level0.bin": payload})
    dest = tmp_path / "out"

    written = extract_all_members(zip_path, dest)

    assert [p.name for p in written] == ["data_level0.bin"]
    assert (dest / "chroma" / "data_level0.bin").read_bytes() == payload


def test_extract_all_members_ignores_member_size_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("artifact_store.archives._MAX_MEMBER_BYTES", 4)
    payload = b"\x00\xff" * 4096  # far larger than the (patched) text-path cap
    zip_path = tmp_path / "store.zip"
    _make_zip(zip_path, {"chroma.sqlite3": payload})
    dest = tmp_path / "out"

    extract_all_members(zip_path, dest)

    assert (dest / "chroma.sqlite3").read_bytes() == payload


def test_extract_all_members_skips_unsafe_member(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    zip_path = tmp_path / "evil.zip"
    _make_zip(zip_path, {"ok.bin": b"\x01", "../escape.bin": b"bad"})
    dest = tmp_path / "out"

    with caplog.at_level(logging.WARNING, logger="artifact_store"):
        written = extract_all_members(zip_path, dest)

    assert [p.name for p in written] == ["ok.bin"]
    assert not (tmp_path / "escape.bin").exists()
    assert any("unsafe zip member" in record.getMessage() for record in caplog.records)
