"""Safe extraction of members from user-supplied zip archives.

Downstream tools accept ``.zip`` uploads that may contain arbitrary members. The
text helpers enforce a strict allow-list (``.md``/``.txt`` only); ``extract_all_members``
keeps every member (e.g. a binary vector store) for trusted, HMAC-verified
re-imports. All paths reject any member name that could escape the destination
directory (zip-slip protection).
"""

from __future__ import annotations

import hashlib
import hmac
import io
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from artifact_store.paths import ensure_within_root
from log4py import get_logger

__all__ = [
    "SIGNATURE_MEMBER",
    "TEXT_MEMBER_SUFFIXES",
    "extract_all_members",
    "extract_text_members",
    "is_safe_member_name",
    "iter_text_members",
    "sign_zip_bytes",
    "verify_zip_bytes",
]

TEXT_MEMBER_SUFFIXES = frozenset({".md", ".txt"})

# Sidecar member that carries the archive's HMAC signature. It is excluded from
# the signed payload and never extracted as content.
SIGNATURE_MEMBER = ".crawl4md.sig"

# Members are hashed in fixed-size chunks so signing/verifying large members
# never loads a whole file into memory.
_HMAC_CHUNK_BYTES = 1024 * 1024

# Per-member decompressed-size cap for in-memory reads. ``member.read`` on the
# text-member paths is bounded to this many bytes so a decompression bomb (a tiny
# compressed member that inflates to gigabytes) cannot exhaust memory; oversized
# text members are skipped like other unsupported members. The trusted
# full-folder re-import path streams to disk instead (see ``extract_all_members``)
# and is not subject to this cap.
_MAX_MEMBER_BYTES = 50 * 1024 * 1024

# Chunk size for streaming a trusted archive member to disk without buffering the
# whole (potentially large) file in memory.
_COPY_CHUNK_BYTES = 1024 * 1024

_logger = get_logger(__name__)


def is_safe_member_name(name: str) -> bool:
    """Return True when a zip member name is safe to extract.

    Rejects empty names, directory entries, absolute paths, Windows drive
    prefixes, and any parent-directory traversal so extraction cannot escape the
    destination directory.
    """
    if not name or name.endswith("/"):
        return False
    normalized = name.replace("\\", "/")
    first_segment = normalized.split("/", 1)[0]
    if normalized.startswith("/") or ":" in first_segment:
        return False
    return ".." not in PurePosixPath(normalized).parts


def _is_text_member(name: str) -> bool:
    return PurePosixPath(name).suffix.lower() in TEXT_MEMBER_SUFFIXES


def iter_text_members(zip_path: Path | str) -> Iterator[tuple[str, bytes]]:
    """Yield ``(member_name, data)`` for safe ``.md``/``.txt`` members of a zip.

    Unsafe member names, unsupported file types, and members whose decompressed
    size exceeds ``_MAX_MEMBER_BYTES`` (decompression-bomb guard) are skipped
    silently; the caller decides how to surface skipped counts.
    """
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if not is_safe_member_name(name):
                _logger.warning("Skipping unsafe zip member name: %r", name)
                continue
            if not _is_text_member(name):
                continue
            with archive.open(info) as member:
                data = member.read(_MAX_MEMBER_BYTES + 1)
            if len(data) > _MAX_MEMBER_BYTES:
                _logger.warning("Skipping oversized zip member %r (decompression-bomb guard)", name)
                continue
            yield name, data


def extract_text_members(zip_path: Path | str, dest_dir: Path | str) -> list[Path]:
    """Extract safe ``.md``/``.txt`` members of *zip_path* into *dest_dir*.

    Returns the list of written file paths. Containment is enforced against
    *dest_dir* so no member can be written outside it.
    """
    destination = Path(dest_dir)
    destination.mkdir(parents=True, exist_ok=True)
    resolved_dest = destination.resolve()
    written: list[Path] = []
    for name, data in iter_text_members(zip_path):
        try:
            target = ensure_within_root(resolved_dest, destination / name)
        except ValueError:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(target)
    return written


def extract_all_members(zip_path: Path | str, dest_dir: Path | str) -> list[Path]:
    """Extract every safe member of *zip_path* into *dest_dir* (any file type).

    Unlike ``extract_text_members`` this keeps binary members (e.g. a vector
    store), so a previously exported folder can be re-imported intact. The
    signature sidecar is skipped, unsafe names are rejected, and containment is
    enforced before any bytes are written. Each member is streamed to disk in
    fixed-size chunks so memory stays bounded regardless of member size; because
    this path serves only HMAC-verified (trusted) re-imports there is no
    per-member size cap, so large vector stores import intact. Returns the
    written file paths.
    """
    destination = Path(dest_dir)
    destination.mkdir(parents=True, exist_ok=True)
    resolved_dest = destination.resolve()
    written: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename
            if info.is_dir() or name == SIGNATURE_MEMBER:
                continue
            if not is_safe_member_name(name):
                _logger.warning("Skipping unsafe zip member name: %r", name)
                continue
            try:
                target = ensure_within_root(resolved_dest, destination / name)
            except ValueError:
                _logger.warning("Skipping zip member outside destination: %r", name)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as member, target.open("wb") as handle:
                while chunk := member.read(_COPY_CHUNK_BYTES):
                    handle.write(chunk)
            written.append(target)
    return written


def _archive_digest(archive: zipfile.ZipFile, secret: str) -> str:
    """Compute the HMAC-SHA256 digest of a zip's content members (sidecar excluded).

    Members are folded in sorted name order, each prefixed with its length, so the
    digest is stable and unambiguous regardless of zip ordering. Bytes are read in
    chunks to bound memory.
    """
    mac = hmac.new(secret.encode("utf-8"), digestmod=hashlib.sha256)
    members = sorted(
        (i for i in archive.infolist() if not i.is_dir() and i.filename != SIGNATURE_MEMBER),
        key=lambda i: i.filename,
    )
    for info in members:
        name = info.filename.encode("utf-8")
        mac.update(len(name).to_bytes(8, "big"))
        mac.update(name)
        with archive.open(info) as member:
            while chunk := member.read(_HMAC_CHUNK_BYTES):
                mac.update(chunk)
    return mac.hexdigest()


def sign_zip_bytes(zip_bytes: bytes, secret: str) -> bytes:
    """Return *zip_bytes* with an HMAC ``.crawl4md.sig`` sidecar member added.

    The signature binds the archive to *secret*; a matching key is required to
    verify it later. Any pre-existing sidecar is replaced.
    """
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as source:
        digest = _archive_digest(source, secret)
        names = [i.filename for i in source.infolist() if i.filename != SIGNATURE_MEMBER]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
            for name in names:
                out.writestr(name, source.read(name))
            out.writestr(SIGNATURE_MEMBER, digest)
    return buffer.getvalue()


def verify_zip_bytes(zip_bytes: bytes, secret: str) -> bool:
    """Return True when *zip_bytes* carries a valid signature for *secret*.

    Returns False for a missing sidecar, a tampered payload, a wrong key, or a
    corrupt archive — never raises for those cases.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            if SIGNATURE_MEMBER not in archive.namelist():
                return False
            expected = archive.read(SIGNATURE_MEMBER).decode("utf-8", "replace")
            actual = _archive_digest(archive, secret)
    except zipfile.BadZipFile:
        return False
    return hmac.compare_digest(expected, actual)
