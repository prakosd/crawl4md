"""Generated output file helpers for the crawl4md Streamlit app."""

from __future__ import annotations

import calendar
import io
import json
import mimetypes
import os
import re
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path, PurePosixPath
from typing import Any

from artifact_store.archives import (
    extract_all_members,
    is_safe_member_name,
    sign_zip_bytes,
    verify_zip_bytes,
)
from artifact_store.naming import (
    BASIC_RAG_QA_FOLDER_PREFIX,
    SEARCH_FOLDER_PREFIX,
    VECTOR_FOLDER_PREFIX,
    folder_name,
    format_sequence_id,
    format_utc_timestamp_slug,
    parse_folder_sequence,
    sequence_sort_key,
)
from crawl4md.naming import (
    CRAWL_FOLDER_PREFIX,
    crawl_sequence_sort_key,
    parse_crawl_folder_sequence,
    parse_utc_timestamp_slug,
)

from app_support.basic_rag_qa.basic_rag_qa_history import BASIC_QA_HISTORY_DIRNAME
from app_support.semantic_search.search_history import SEARCH_HISTORY_DIRNAME
from app_support.session_manager import ensure_within_root

_ACTIVITY_LOG_FILE = "activity_log.txt"
_CRAWL_DIR_PREFIX = CRAWL_FOLDER_PREFIX
_VECTOR_DIR_PREFIX = VECTOR_FOLDER_PREFIX
_SEARCH_DIR_PREFIX = SEARCH_FOLDER_PREFIX
_BASIC_RAG_QA_DIR_PREFIX = BASIC_RAG_QA_FOLDER_PREFIX
# Fixed per-session history folders (not timestamped runs). They get the same
# Export + Delete controls as run folders so a user can download or clear their
# accumulated search / Q&A history straight from the download tree.
_HISTORY_FOLDER_NAMES = frozenset({SEARCH_HISTORY_DIRNAME, BASIC_QA_HISTORY_DIRNAME})
# Material icons for download-tree folders, picked by artifact type so a crawl
# run reads as exploration and a vector index as a database at a glance.
_FOLDER_ICON_DEFAULT = ":material/folder_open:"
_FOLDER_ICON_CRAWL = ":material/travel_explore:"
_FOLDER_ICON_VECTOR = ":material/database:"
_FOLDER_ICON_SEARCH = ":material/search:"
_FOLDER_ICON_BASIC_RAG_QA = ":material/question_answer:"
_DEFAULT_DOWNLOAD_LIMIT_BYTES = 50 * 1024 * 1024
_DEFAULT_PREVIEW_MAX_BYTES = 256 * 1024
_BYTES_PER_KB = 1024
_BYTES_PER_MB = 1024 * 1024
_BYTES_PER_GB = 1024 * 1024 * 1024
_HIDDEN_FILE_PREFIX = "."
_FINAL_DIR_NAME = "final"
_LOGS_DIR_NAME = "logs"
_MISSING_CACHE_TOKEN = (0.0, 0)
_EMPTY_FOLDER_ZIP_TOKEN = (0, 0.0, 0)
_PROGRESS_HISTORY_FILE = "progress_history.jsonl"
_SITE_GRAPH_FILENAME = "site_graph.jsonl"
_RUN_FOLDER_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}$")
_SORTED_SUCCESS_CONTENT_GLOB = "sorted_success_content_*"
_SUCCESS_CONTENT_GLOB = "success_content_*"
_SUCCESS_ZIP_NAME = "success_content.zip"
_TEXT_PREVIEW_EXTENSIONS = frozenset(
    {
        ".cfg",
        ".conf",
        ".csv",
        ".htm",
        ".html",
        ".ini",
        ".json",
        ".jsonl",
        ".log",
        ".md",
        ".rst",
        ".text",
        ".toml",
        ".tsv",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }
)


@dataclass(frozen=True)
class GeneratedFile:
    """Metadata for a generated file that can be shown in Streamlit."""

    path: Path
    relative_path: str
    name: str
    size_bytes: int
    modified_at: datetime
    file_type: str
    download_allowed: bool


@dataclass(frozen=True)
class TextPreview:
    """A capped text preview payload suitable for inline UI display."""

    text: str
    truncated: bool


@dataclass(frozen=True)
class ReadyDownload:
    """A ready-to-download crawl result, either a single file or a zip."""

    file: GeneratedFile
    source_count: int


@dataclass(frozen=True)
class _ScannedGeneratedFile:
    path: Path
    relative_path: str
    name: str
    size_bytes: int
    modified_at: datetime
    file_type: str


def list_generated_files(
    session_root: Path | str,
    search_root: Path | str | None = None,
    *,
    download_limit_bytes: int = _DEFAULT_DOWNLOAD_LIMIT_BYTES,
) -> list[GeneratedFile]:
    """List generated files under the current session only."""
    root = Path(session_root).resolve()
    target_root = ensure_within_root(root, search_root or root)
    if not target_root.exists():
        return []

    return [
        GeneratedFile(
            path=file.path,
            relative_path=file.relative_path,
            name=file.name,
            size_bytes=file.size_bytes,
            modified_at=file.modified_at,
            file_type=file.file_type,
            download_allowed=file.size_bytes <= download_limit_bytes,
        )
        for file in _scan_generated_files(root, target_root)
    ]


def generated_files_cache_token(path: Path | str) -> tuple[float, int]:
    """Return a cheap cache token for Streamlit generated-file listings."""
    try:
        stat_result = Path(path).stat()
    except OSError:
        return _MISSING_CACHE_TOKEN
    return (stat_result.st_mtime, stat_result.st_size)


def is_run_folder(name: str) -> bool:
    """Return ``True`` when *name* is a top-level crawl/vector run folder."""
    return name.startswith(_CRAWL_DIR_PREFIX) or name.startswith(_VECTOR_DIR_PREFIX)


def is_history_folder(name: str) -> bool:
    """Return ``True`` when *name* is a fixed per-session history folder.

    Search history (``search_history``) and Basic RAG Q&A history
    (``basic_rag_qa_history``) are single, fixed-name folders rather than
    timestamped runs, so they need their own predicate: the download tree gives
    them the same Export + Delete controls as run folders.
    """
    return name in _HISTORY_FOLDER_NAMES


def delete_generated_folder(session_root: Path | str, relative_path: str) -> bool:
    """Delete one generated folder (and all its contents) within the session.

    Returns ``True`` when a folder was removed. After deletion, parent
    directories that became empty are removed too, stopping at — and never
    removing — the session root. Returns ``False`` for the session root itself or
    a non-folder target. Raises ``ValueError`` when *relative_path* escapes the
    session root (path containment is enforced via :func:`ensure_within_root`).
    """
    root = Path(session_root).resolve()
    target = ensure_within_root(root, root / relative_path)
    if target == root or not target.is_dir():
        return False
    shutil.rmtree(target)
    _prune_empty_parents(target.parent, root)
    return True


def build_folder_zip_bytes(
    session_root: Path | str, relative_path: str, *, signing_secret: str | None = None
) -> bytes:
    """Return a zip archive of one session folder's full contents.

    Every file under *relative_path* is added recursively, nested under the
    folder's own name so extracting the archive recreates the named folder. When
    *signing_secret* is given, an HMAC ``.crawl4md.sig`` sidecar is added so the
    zip can later be verified on upload. Raises ``ValueError`` when *relative_path*
    is the session root, is not a folder, or escapes it (containment via
    :func:`ensure_within_root`).
    """
    root = Path(session_root).resolve()
    target = ensure_within_root(root, root / relative_path)
    if target == root or not target.is_dir():
        raise ValueError(f"Not a session folder: {relative_path!r}")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(target.rglob("*")):
            if path.is_file() and not path.is_symlink():
                arcname = f"{target.name}/{path.relative_to(target).as_posix()}"
                archive.write(path, arcname)
    raw = buffer.getvalue()
    return sign_zip_bytes(raw, signing_secret) if signing_secret else raw


# Bundled sample crawl/index exports a user can import to skip Steps 1-2.
FIXTURES_ROOT = Path(__file__).resolve().parents[4] / "data" / "fixtures"
_IMPORT_DIR_PREFIX = "import_"


def zip_top_folder(zip_bytes: bytes) -> str | None:
    """Return the single top-level folder name inside a zip, or None if not unique."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            tops = {
                n.split("/", 1)[0]
                for n in archive.namelist()
                if is_safe_member_name(n) and "/" in n
            }
    except zipfile.BadZipFile:
        return None
    return next(iter(tops)) if len(tops) == 1 else None


def _next_sequence(session_root: Path, prefix: str) -> int:
    if not session_root.is_dir():
        return 1
    sequences = [
        seq
        for path in session_root.iterdir()
        if path.is_dir()
        for seq in [parse_folder_sequence(path.name, prefix=prefix)]
        if seq is not None
    ]
    return max(sequences) + 1 if sequences else 1


def import_target_name(session_root: Path | str, top_folder: str) -> str:
    """Return a conflict-free folder name for re-importing *top_folder*.

    Crawl and vector exports keep their kind and trailing word but get the next
    free sequence number; anything else lands under a numbered ``import_`` folder.
    """
    root = Path(session_root).resolve()
    for prefix in (_CRAWL_DIR_PREFIX, _VECTOR_DIR_PREFIX):
        if top_folder.startswith(prefix) and parse_folder_sequence(top_folder, prefix=prefix):
            suffix = top_folder[len(prefix) :].split("_", 1)
            word = suffix[1] if len(suffix) > 1 else "import"
            return folder_name(prefix, format_sequence_id(_next_sequence(root, prefix), word))
    return folder_name(
        _IMPORT_DIR_PREFIX, format_sequence_id(_next_sequence(root, _IMPORT_DIR_PREFIX), "upload")
    )


def _extract_zip_to_new_folder(session_root: Path | str, zip_bytes: bytes) -> str:
    """Extract *zip_bytes* into a new conflict-free folder under *session_root*.

    Shared by signed-upload and sample-fixture import: names the folder to avoid
    clashing with existing ones and extracts zip-slip-safely
    (:func:`extract_all_members`). Returns the created folder name.
    """
    root = Path(session_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    top = zip_top_folder(zip_bytes) or _IMPORT_DIR_PREFIX
    new_name = import_target_name(root, top)
    staging = Path(tempfile.mkdtemp(dir=root))
    try:
        extract_all_members(io.BytesIO(zip_bytes), staging)
        children = [p for p in staging.iterdir() if p.is_dir()]
        source = children[0] if len(children) == 1 else staging
        destination = ensure_within_root(root, root / new_name)
        shutil.move(str(source), str(destination))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return new_name


def import_signed_zip(session_root: Path | str, zip_bytes: bytes, secret: str) -> str | None:
    """Verify and extract an uploaded zip into a new conflict-free session folder.

    Returns the created folder name, or None when the signature is invalid. The
    contents are renamed to avoid clashing with existing folders; extraction is
    zip-slip-safe (:func:`extract_all_members`).
    """
    if not verify_zip_bytes(zip_bytes, secret):
        return None
    return _extract_zip_to_new_folder(session_root, zip_bytes)


def history_exists(session_root: Path | str, dirname: str) -> bool:
    """Return ``True`` when *dirname* is a non-empty history folder in the session."""
    directory = Path(session_root) / dirname
    return directory.is_dir() and any(directory.iterdir())


def import_history_zip(session_root: Path | str, zip_bytes: bytes, secret: str) -> str | None:
    """Verify and extract a history zip, replacing that history folder in place.

    Only the fixed per-session history folders (``search_history``,
    ``basic_rag_qa_history``) may be imported this way; any other top-level folder
    is rejected so a crafted zip can't overwrite crawl/vector output. Any existing
    folder of that name is deleted and replaced. Extraction is zip-slip-safe
    (:func:`extract_all_members`). Returns the replaced folder name, or None when
    the signature is invalid or the zip isn't a recognized history export.
    """
    if not verify_zip_bytes(zip_bytes, secret):
        return None
    top = zip_top_folder(zip_bytes)
    if top not in _HISTORY_FOLDER_NAMES:
        return None
    root = Path(session_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    destination = ensure_within_root(root, root / top)
    staging = Path(tempfile.mkdtemp(dir=root))
    try:
        extract_all_members(io.BytesIO(zip_bytes), staging)
        source = staging / top
        if not source.is_dir():
            return None
        if destination.exists():
            shutil.rmtree(destination)
        shutil.move(str(source), str(destination))
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return top


@dataclass(frozen=True)
class SampleFixture:
    """One bundled sample archive under ``data/fixtures/<category>/``."""

    category: str
    name: str
    size_bytes: int


def list_sample_fixtures() -> list[SampleFixture]:
    """Return the bundled sample ``.zip`` fixtures, sorted by category then name.

    Each fixture is a ready-made crawl or vector-index export a user can import to
    skip Steps 1-2. Returns an empty list when the fixtures folder is absent.
    """
    if not FIXTURES_ROOT.is_dir():
        return []
    fixtures: list[SampleFixture] = []
    for category_dir in sorted(p for p in FIXTURES_ROOT.iterdir() if p.is_dir()):
        for archive in sorted(category_dir.glob("*.zip")):
            try:
                size = archive.stat().st_size
            except OSError:
                continue
            fixtures.append(SampleFixture(category_dir.name, archive.name, size))
    return fixtures


def _sample_fixture_path(category: str, name: str) -> Path | None:
    """Resolve a fixture ``.zip`` within :data:`FIXTURES_ROOT`, guarding traversal."""
    try:
        target = ensure_within_root(FIXTURES_ROOT, FIXTURES_ROOT / category / name)
    except ValueError:
        return None
    return target if target.is_file() and target.suffix == ".zip" else None


def import_sample_fixture(session_root: Path | str, category: str, name: str) -> str | None:
    """Extract a bundled sample archive into a new conflict-free session folder.

    Reads ``data/fixtures/<category>/<name>`` — a trusted repo file, so no
    signature check — and extracts it like a normal import. Returns the created
    folder name, or None when the fixture is missing, out of root, or unreadable.
    """
    source = _sample_fixture_path(category, name)
    if source is None:
        return None
    try:
        zip_bytes = source.read_bytes()
    except OSError:
        return None
    return _extract_zip_to_new_folder(session_root, zip_bytes)


def folder_zip_cache_token(session_root: Path | str, relative_path: str) -> tuple[int, float, int]:
    """Return a cheap change token (file count, newest mtime, total size) for a folder.

    Lets the app cache a folder's zip and rebuild only when its contents change.
    Returns the empty token for a missing, non-folder, or out-of-root path.
    """
    root = Path(session_root).resolve()
    try:
        target = ensure_within_root(root, root / relative_path)
    except ValueError:
        return _EMPTY_FOLDER_ZIP_TOKEN
    if not target.is_dir():
        return _EMPTY_FOLDER_ZIP_TOKEN
    count = 0
    newest = 0.0
    total = 0
    for path in target.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            stat_result = path.stat()
        except OSError:
            continue
        count += 1
        total += stat_result.st_size
        newest = max(newest, stat_result.st_mtime)
    return (count, newest, total)


def _prune_empty_parents(start: Path, root: Path) -> None:
    """Remove now-empty directories from *start* up to (excluding) *root*."""
    current = start.resolve()
    root = root.resolve()
    while current != root and root in current.parents:
        try:
            current.rmdir()  # only succeeds while the directory is empty
        except OSError:
            return
        current = current.parent


def _scan_generated_files(root: Path, target_root: Path) -> list[_ScannedGeneratedFile]:
    scanned: list[_ScannedGeneratedFile] = []
    stack = [target_root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                dir_entries = sorted(entries, key=lambda entry: entry.name)
        except OSError:
            continue
        for entry in dir_entries:
            entry_path = Path(entry.path)
            try:
                safe_path = ensure_within_root(root, entry_path)
            except ValueError:
                continue
            relative = safe_path.relative_to(root)
            if any(part.startswith(_HIDDEN_FILE_PREFIX) for part in relative.parts):
                continue
            try:
                if entry.is_dir(follow_symlinks=False):
                    stack.append(safe_path)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            file_type = safe_path.suffix.lower().lstrip(".") or "file"
            scanned.append(
                _ScannedGeneratedFile(
                    path=safe_path,
                    relative_path=relative.as_posix(),
                    name=safe_path.name,
                    size_bytes=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    file_type=file_type,
                )
            )
    return sorted(scanned, key=lambda file: generated_file_sort_key(file.relative_path))


def generated_file_sort_key(relative_path: str) -> tuple[int, int, str, str]:
    """Return a sort key that orders numbered crawl runs newest-first."""
    parts = PurePosixPath(relative_path).parts
    if not parts:
        return (1, 0, "", "")
    sequence = parse_crawl_folder_sequence(parts[0])
    if sequence is None:
        return (1, 0, relative_path.lower(), "")
    return (0, -sequence, parts[0].lower(), "/".join(parts[1:]).lower())


def is_text_previewable(path_or_name: Path | str) -> bool:
    """Return True when the file can be shown as plain text in preview UI."""
    file_name = Path(path_or_name).name
    lower_name = file_name.lower()
    if any(lower_name.endswith(ext) for ext in _TEXT_PREVIEW_EXTENSIONS):
        return True
    mime_type = mimetypes.guess_type(file_name)[0]
    return bool(mime_type and mime_type.startswith("text/"))


def preview_created_timestamp(stat_result: Any, *, platform_name: str = os.name) -> float | None:
    """Return a reliable creation timestamp for preview metadata when available."""
    birthtime = getattr(stat_result, "st_birthtime", None)
    if isinstance(birthtime, (int, float)):
        return float(birthtime)
    if platform_name == "nt":
        ctime = getattr(stat_result, "st_ctime", None)
        if isinstance(ctime, (int, float)):
            return float(ctime)
    return None


def read_text_preview(
    path: Path | str,
    *,
    max_bytes: int = _DEFAULT_PREVIEW_MAX_BYTES,
) -> TextPreview:
    """Read up to *max_bytes* from a file and decode as UTF-8 replacement text."""
    if max_bytes < 1:
        raise ValueError("Preview byte limit must be at least 1.")
    preview_path = Path(path)
    if not preview_path.exists() or not preview_path.is_file():
        return TextPreview(text="", truncated=False)
    with preview_path.open("rb") as file_obj:
        raw_bytes = file_obj.read(max_bytes + 1)
    truncated = len(raw_bytes) > max_bytes
    if truncated:
        raw_bytes = raw_bytes[:max_bytes]
    return TextPreview(text=raw_bytes.decode("utf-8", errors="replace"), truncated=truncated)


def read_recent_lines(path: Path | str, *, max_lines: int | None) -> list[str]:
    """Read UTF-8 text file lines, optionally limited to the last *max_lines*."""
    log_path = Path(path)
    if not log_path.exists() or not log_path.is_file():
        return []
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if max_lines is None:
        return lines
    if max_lines < 1:
        return []
    return lines[-max_lines:]


def find_latest_crawl_dir(crawl_base: Path | str) -> Path | None:
    """Return the newest crawler-created timestamp directory under a crawl base."""
    base = Path(crawl_base)
    if not base.exists():
        return None
    candidates = [path for path in base.iterdir() if path.is_dir()]
    if not candidates:
        return None
    return sorted(candidates, key=_crawl_timestamp_dir_sort_key)[0]


def _crawl_timestamp_dir_sort_key(path: Path) -> tuple[int, float, str]:
    parsed = parse_utc_timestamp_slug(path.name)
    if parsed is not None:
        return (0, -parsed.timestamp(), path.name.lower())
    try:
        modified_at = path.stat().st_mtime
    except OSError:
        modified_at = 0.0
    return (1, -modified_at, path.name.lower())


def activity_log_path(crawl_dir: Path | str | None) -> Path | None:
    """Return the activity log path for a crawl output directory when present."""
    if crawl_dir is None:
        return None
    base = Path(crawl_dir)
    log_path = base / _LOGS_DIR_NAME / _ACTIVITY_LOG_FILE
    if log_path.exists():
        return log_path
    # Fall back to the legacy location (crawls written before the logs/ subdir).
    legacy_path = base / _ACTIVITY_LOG_FILE
    return legacy_path if legacy_path.exists() else None


def build_download_tree(files: list[GeneratedFile]) -> dict[str, Any]:
    """Return a nested path tree for generated-file download rendering."""
    tree: dict[str, Any] = {}
    for file in files:
        parts = PurePosixPath(file.relative_path).parts
        node = tree
        for folder in parts[:-1]:
            node = node.setdefault(folder, {})
        node[parts[-1]] = file
    return tree


def find_site_graph_file(node: Mapping[str, Any]) -> GeneratedFile | None:
    """Return the ``site_graph.jsonl`` file within a download-tree *node*, if any.

    Searches the nested folder mapping (as built by :func:`build_download_tree`)
    depth-first and returns the first matching :class:`GeneratedFile`, or ``None``
    when the folder holds no site graph — e.g. a vector index or a crawl produced
    before site graphs existed. Lets the download tree render the "Explore in 3D"
    control in a crawl folder's action row (beside Export) rather than deep beside
    the file itself.
    """
    for name, entry in node.items():
        if isinstance(entry, GeneratedFile):
            if name == _SITE_GRAPH_FILENAME:
                return entry
        elif isinstance(entry, Mapping):
            found = find_site_graph_file(entry)
            if found is not None:
                return found
    return None


def find_site_graph_for_result(
    session_root: Path | str,
    relative_path: str,
    *,
    download_limit_bytes: int = _DEFAULT_DOWNLOAD_LIMIT_BYTES,
) -> GeneratedFile | None:
    """Return the ``site_graph.jsonl`` for a ready download's crawl run, if any.

    A ready result's *relative_path* starts with ``<crawl_folder>/<timestamp>/``; the
    run's site graph lives at ``<crawl_folder>/<timestamp>/logs/site_graph.jsonl``.
    Returns ``None`` when the run predates site graphs or the path escapes the root,
    so the ready-result panel offers "Explore in 3D" only when it applies.
    """
    root = Path(session_root).resolve()
    parts = PurePosixPath(relative_path).parts
    if len(parts) < 2:
        return None
    try:
        candidate = ensure_within_root(
            root, root / parts[0] / parts[1] / _LOGS_DIR_NAME / _SITE_GRAPH_FILENAME
        )
        stat = candidate.stat()
    except (OSError, ValueError):
        return None
    return GeneratedFile(
        path=candidate,
        relative_path=candidate.relative_to(root).as_posix(),
        name=candidate.name,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        file_type=candidate.suffix.lower().lstrip(".") or "file",
        download_allowed=stat.st_size <= download_limit_bytes,
    )


def files_excluding(files: list[GeneratedFile], relative_path: str | None) -> list[GeneratedFile]:
    """Return *files* without the entry at *relative_path* (``None`` keeps all).

    A file rendered on its own (e.g. the live session log shown above the tree)
    must be dropped from the tree; otherwise it renders twice in one pass and its
    per-file widget key collides (``StreamlitDuplicateElementKey``).
    """
    if relative_path is None:
        return list(files)
    return [file for file in files if file.relative_path != relative_path]


def download_tree_entry_sort_key(
    name: str,
    entry: Any,
    *,
    top_level: bool = False,
) -> tuple[int, int, str]:
    """Return a tree-entry sort key with newest numbered crawl/vector folders first."""
    if isinstance(entry, dict):
        if top_level and parse_crawl_folder_sequence(name) is not None:
            _, sequence_key, name_key = crawl_sequence_sort_key(name)
            return (0, sequence_key, name_key)
        if top_level and parse_folder_sequence(name, prefix=_VECTOR_DIR_PREFIX) is not None:
            _, sequence_key, name_key = sequence_sort_key(name, prefix=_VECTOR_DIR_PREFIX)
            return (1, sequence_key, name_key)
        return (2, 0, name.lower())
    return (3, 0, name.lower())


def collapse_artifact_run_folder(
    folder_name: str,
    folder_node: dict[str, Any],
    *,
    local_timezone: tzinfo | None = None,
) -> tuple[str, dict[str, Any]]:
    """Merge a crawl/vector folder and its single timestamp child into one label."""
    label = folder_name
    is_artifact_dir = folder_name.startswith(_CRAWL_DIR_PREFIX) or folder_name.startswith(
        _VECTOR_DIR_PREFIX
    )
    if not is_artifact_dir or len(folder_node) != 1:
        return label, folder_node

    child_name, child_entry = next(iter(folder_node.items()))
    if not isinstance(child_entry, dict) or not _RUN_FOLDER_PATTERN.fullmatch(child_name):
        return label, folder_node

    timestamp_label = format_run_timestamp_label(
        child_name,
        child_entry,
        local_timezone=local_timezone,
    )
    return f"{label}/{timestamp_label}", child_entry


def download_folder_icon(folder_name: str) -> str:
    """Return the Material icon for a download-tree folder by its artifact type.

    Crawl runs (``crawl_*``), vector indexes (``vector_*``), search history
    (``search_*``), and prompt history (``basic_rag_qa_*``) get distinct icons so the
    tree is scannable; every other folder keeps the neutral folder icon.
    """
    if folder_name.startswith(_CRAWL_DIR_PREFIX):
        return _FOLDER_ICON_CRAWL
    if folder_name.startswith(_VECTOR_DIR_PREFIX):
        return _FOLDER_ICON_VECTOR
    if folder_name.startswith(_SEARCH_DIR_PREFIX):
        return _FOLDER_ICON_SEARCH
    if folder_name.startswith(_BASIC_RAG_QA_DIR_PREFIX):
        return _FOLDER_ICON_BASIC_RAG_QA
    return _FOLDER_ICON_DEFAULT


def format_run_timestamp_label(
    folder_name: str,
    folder_node: dict[str, Any] | None = None,
    *,
    local_timezone: tzinfo | None = None,
) -> str:
    """Return a timestamp folder label with a local-time companion when possible."""
    timestamp = _progress_history_timestamp(folder_node) if folder_node is not None else None
    if timestamp is None:
        timestamp = parse_utc_timestamp_slug(folder_name)
    if timestamp is None:
        return folder_name
    return f"{folder_name} ({_format_local_timestamp(timestamp, local_timezone=local_timezone)})"


def format_history_folder_label(
    folder_name: str,
    folder_node: dict[str, Any] | None = None,
    *,
    local_timezone: tzinfo | None = None,
) -> str:
    """Return a history folder label with its created timestamp, like run folders.

    History folders aren't timestamped on disk, so the created time comes from the
    first record and renders as a ``<slug> (local time)`` suffix mirroring crawl /
    vector runs. Falls back to the plain name when the history has no records yet.
    """
    timestamp = _history_created_timestamp(folder_name, folder_node)
    if timestamp is None:
        return folder_name
    slug = format_utc_timestamp_slug(timestamp)
    return f"{folder_name}/{slug} ({_format_local_timestamp(timestamp, local_timezone=local_timezone)})"


def format_file_size(size_bytes: int) -> str:
    """Return a compact human-readable file size like '5.9 MB' or '0.4 KB'.

    Sub-megabyte files read in KB and larger ones in MB/GB (one decimal) so the
    download tree stays scannable; sizes never fall back to raw bytes.
    """
    if size_bytes >= _BYTES_PER_GB:
        return f"{size_bytes / _BYTES_PER_GB:.1f} GB"
    if size_bytes >= _BYTES_PER_MB:
        return f"{size_bytes / _BYTES_PER_MB:.1f} MB"
    return f"{size_bytes / _BYTES_PER_KB:.1f} KB"


def format_local_datetime(
    value: datetime, *, local_timezone: tzinfo | None = None, abbreviate_month: bool = False
) -> str:
    """Format a UTC datetime as a local-time label (e.g. '1 July 2026 15:39 AEST').

    Reuses the same server-local formatting the download tree applies to run
    folders, so history timestamps read consistently across the app. Set
    ``abbreviate_month`` for a three-letter month (e.g. '1 Jul 2026 15:39 AEST').
    """
    return _format_local_timestamp(
        value, local_timezone=local_timezone, abbreviate_month=abbreviate_month
    )


def _format_local_timestamp(
    value: datetime, *, local_timezone: tzinfo | None = None, abbreviate_month: bool = False
) -> str:
    target_timezone = local_timezone or datetime.now().astimezone().tzinfo or timezone.utc
    local_value = value.astimezone(timezone.utc).astimezone(target_timezone)
    zone_name = local_value.tzname() or "local"
    months = calendar.month_abbr if abbreviate_month else calendar.month_name
    month_name = months[local_value.month]
    return (
        f"{local_value.day} {month_name} {local_value.year} "
        f"{local_value.hour:02d}:{local_value.minute:02d} {zone_name}"
    )


def _progress_history_timestamp(folder_node: dict[str, Any] | None) -> datetime | None:
    progress_file = _find_generated_file(folder_node, _PROGRESS_HISTORY_FILE)
    if progress_file is None:
        return None
    try:
        with progress_file.path.open(encoding="utf-8") as handle:
            for line in handle:
                timestamp = _timestamp_from_progress_history_line(line)
                if timestamp is not None:
                    return timestamp
    except OSError:
        return None
    return None


def _find_generated_file(
    folder_node: dict[str, Any] | None, file_name: str
) -> GeneratedFile | None:
    if folder_node is None:
        return None
    for name, entry in folder_node.items():
        if isinstance(entry, GeneratedFile) and name == file_name:
            return entry
        if isinstance(entry, dict):
            found = _find_generated_file(entry, file_name)
            if found is not None:
                return found
    return None


def _parse_iso_utc(value: object) -> datetime | None:
    """Parse an ISO-8601 string (``Z`` or offset, naive treated as UTC) to UTC."""
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_from_progress_history_line(line: str) -> datetime | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    return _parse_iso_utc(payload.get("timestamp"))


def _history_created_timestamp(
    folder_name: str, folder_node: dict[str, Any] | None
) -> datetime | None:
    """Return the created time of a history folder from its first record.

    History logs (``<folder_name>.jsonl``) append oldest-first, so the first
    parseable ``timestamp_utc`` is when the history began.
    """
    history_file = _find_generated_file(folder_node, f"{folder_name}.jsonl")
    if history_file is None:
        return None
    try:
        with history_file.path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    continue
                timestamp = _parse_iso_utc(payload.get("timestamp_utc"))
                if timestamp is not None:
                    return timestamp
    except OSError:
        return None
    return None


def collect_success_content_files(crawl_output_dir: Path, root: Path) -> list[Path]:
    """Return success content files from the final/ folder of a crawl output directory.

    Prefers ``sorted_success_content_*`` files. Falls back to ``success_content_*``
    (excluding any .zip file) when sorted files are absent.
    """
    try:
        safe_dir = ensure_within_root(root, crawl_output_dir)
    except ValueError:
        return []
    final_dir = safe_dir / _FINAL_DIR_NAME
    if not final_dir.exists():
        return []
    files = sorted(f for f in final_dir.glob(_SORTED_SUCCESS_CONTENT_GLOB) if f.is_file())
    if not files:
        files = sorted(
            f
            for f in final_dir.glob(_SUCCESS_CONTENT_GLOB)
            if f.is_file() and f.suffix.lower() != ".zip"
        )
    return files


def _refresh_success_zip(source_files: list[Path], zip_path: Path) -> None:
    """Create or refresh success_content.zip when any source file is newer."""
    if zip_path.exists():
        zip_mtime = zip_path.stat().st_mtime
        if all(f.stat().st_mtime <= zip_mtime for f in source_files):
            return
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in source_files:
            zf.write(f, f.name)


def build_ready_download(
    crawl_output_dir: Path | str,
    session_root: Path | str,
    *,
    download_limit_bytes: int = _DEFAULT_DOWNLOAD_LIMIT_BYTES,
) -> ReadyDownload | None:
    """Return the ready-to-download success result for a finished or stopped crawl.

    Returns a single-file ``ReadyDownload`` when only one success content file exists,
    or a zip-based ``ReadyDownload`` when multiple files are present. Returns ``None``
    when no successful content is available or the path is outside the session root.
    """
    root = Path(session_root).resolve()
    try:
        output_dir = ensure_within_root(root, Path(crawl_output_dir))
    except ValueError:
        return None
    source_files = collect_success_content_files(output_dir, root)
    if not source_files:
        return None
    if len(source_files) == 1:
        download_path = source_files[0]
    else:
        zip_path = output_dir / _FINAL_DIR_NAME / _SUCCESS_ZIP_NAME
        _refresh_success_zip(source_files, zip_path)
        download_path = zip_path
    try:
        stat = download_path.stat()
    except OSError:
        return None
    relative = download_path.relative_to(root)
    gf = GeneratedFile(
        path=download_path,
        relative_path=relative.as_posix(),
        name=download_path.name,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        file_type=download_path.suffix.lower().lstrip(".") or "file",
        download_allowed=stat.st_size <= download_limit_bytes,
    )
    return ReadyDownload(file=gf, source_count=len(source_files))


def find_ready_download_in_session(
    session_root: Path | str,
    *,
    download_limit_bytes: int = _DEFAULT_DOWNLOAD_LIMIT_BYTES,
) -> ReadyDownload | None:
    """Return the most recent ready-to-download result within a session folder.

    Scans ``crawl_*`` subdirectories of *session_root*, finds the newest run
    directory in each, and returns the first ``ReadyDownload`` found when
    searching newest-first. Returns ``None`` when no crawl in the session has
    success content.
    """
    root = Path(session_root).resolve()
    if not root.is_dir():
        return None
    candidates: list[tuple[tuple[int, int, str], tuple[int, float, str], Path]] = []
    for crawl_dir in root.iterdir():
        if not crawl_dir.is_dir() or not crawl_dir.name.startswith(_CRAWL_DIR_PREFIX):
            continue
        run_dir = find_latest_crawl_dir(crawl_dir)
        if run_dir is None:
            continue
        candidates.append(
            (
                crawl_sequence_sort_key(crawl_dir.name),
                _crawl_timestamp_dir_sort_key(run_dir),
                run_dir,
            )
        )
    for _, _, run_dir in sorted(candidates):
        ready = build_ready_download(run_dir, root, download_limit_bytes=download_limit_bytes)
        if ready is not None:
            return ready
    return None
