"""Downloads / Output-Files UI for the Streamlit app.

Renders the Output Files panel: the download tree (per-file download + preview,
per-folder zip export + delete), the signed-zip import dialog, the ready-result
download panel, and the file-preview modal. Extracted from ``streamlit_app.py``
so the shell keeps only navigation, session, and job orchestration. Shared
constants and shell helpers come from ``app_runtime`` (no import cycle: nothing
here imports ``streamlit_app``). ``st.session_state`` is a global singleton, so
these renderers read/write the same state the shell owns.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Mapping
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st
from artifact_store.archives import verify_zip_bytes

from app_support.app_runtime import (
    _DEFAULT_LANGUAGE,
    _DIALOG_PLACEHOLDER_TITLE,
    _DOWNLOAD_LIMIT_BYTES,
    _DOWNLOADS_REFRESH_INTERVAL,
    _ICON_BUTTON_WIDTH_PX,
    _PREVIEW_DIALOG_CONTENT_KEY,
    _PREVIEW_DIALOG_SCOPE_CLASS,
    _PREVIEW_DIALOG_VIEWPORT_HEIGHT,
    _PREVIEW_DIALOG_VIEWPORT_WIDTH,
    _PREVIEW_DIALOG_WIDTH,
    _PREVIEW_LIMIT_BYTES,
    _PREVIEW_LIMIT_KIB,
    _STATUS_ROW_STYLE,
    _UTC_DISPLAY_FORMAT,
    _auto_refresh_fragment,
    _cached_download_tree,
    _cached_list_generated_files,
    _crawl_job_active,
    _files_actions_busy,
    _job_is_alive,
    _session_root,
    _vector_job_active,
)
from app_support.dialog_ui import (
    SCROLLABLE_DIALOG_CONTENT_HEIGHT_PX,
    render_confirm_dialog,
    scrollable_dialog_css,
)
from app_support.focus import click_widget
from app_support.generated_files import (
    build_folder_zip_bytes,
    collapse_artifact_run_folder,
    delete_generated_folder,
    download_folder_icon,
    download_tree_entry_sort_key,
    files_excluding,
    find_site_graph_file,
    find_site_graph_for_result,
    format_file_size,
    format_history_folder_label,
    generated_files_cache_token,
    history_exists,
    import_history_zip,
    import_sample_fixture,
    import_signed_zip,
    import_target_name,
    is_history_folder,
    is_run_folder,
    list_sample_fixtures,
    zip_top_folder,
)
from app_support.i18n import get_strings
from app_support.settings import get_settings
from app_support.site_graph_3d.launcher import render_explore_3d_button
from app_support.support import (
    GeneratedFile,
    ReadyDownload,
    build_ready_download,
    ensure_within_root,
    find_ready_download_in_session,
    is_text_previewable,
    preview_created_timestamp,
    read_text_preview,
)


def _format_preview_timestamp_utc(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(_UTC_DISPLAY_FORMAT)
    except (OverflowError, OSError, ValueError):
        return None


def _on_preview_dismiss() -> None:
    st.session_state.preview_file_relative_path = ""


@st.dialog(
    _DIALOG_PLACEHOLDER_TITLE,
    width=_PREVIEW_DIALOG_WIDTH,
    on_dismiss=_on_preview_dismiss,
)
def _file_preview_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    preview_relative_path = str(st.session_state.get("preview_file_relative_path", ""))
    if not preview_relative_path:
        return
    session_folder = _session_root()
    try:
        file_path = ensure_within_root(session_folder, session_folder / preview_relative_path)
    except ValueError:
        st.session_state.preview_file_relative_path = ""
        return
    file_name = Path(preview_relative_path).name
    st.markdown(
        scrollable_dialog_css(
            _PREVIEW_DIALOG_SCOPE_CLASS,
            _PREVIEW_DIALOG_CONTENT_KEY,
            width=_PREVIEW_DIALOG_VIEWPORT_WIDTH,
            height=_PREVIEW_DIALOG_VIEWPORT_HEIGHT,
        ),
        unsafe_allow_html=True,
    )
    st.subheader(file_name)
    if not file_path.exists() or not file_path.is_file():
        st.warning(strings["FILES_PREVIEW_MISSING"].format(file=preview_relative_path))
        return
    if not is_text_previewable(file_name):
        st.info(strings["FILES_PREVIEW_UNSUPPORTED"].format(file=file_name))
        return
    try:
        current_stat = file_path.stat()
    except OSError:
        st.warning(strings["FILES_PREVIEW_MISSING"].format(file=preview_relative_path))
        return
    current_size = current_stat.st_size

    path_text = strings["FILES_PREVIEW_PATH"].format(path=preview_relative_path)
    size_text = strings["FILES_PREVIEW_SIZE"].format(size_kib=round(current_size / 1024, 1))
    modified_display = _format_preview_timestamp_utc(current_stat.st_mtime)
    modified_text = (
        strings["FILES_PREVIEW_MODIFIED_AT"].format(value=modified_display)
        if modified_display
        else None
    )

    created_timestamp = preview_created_timestamp(current_stat)
    created_display = _format_preview_timestamp_utc(created_timestamp)
    created_text = (
        strings["FILES_PREVIEW_CREATED_AT"].format(value=created_display)
        if created_display
        else None
    )

    caption_html = (
        f'<div style="{_STATUS_ROW_STYLE}"><span>{path_text}</span><span>{size_text}</span></div>'
    )
    if modified_text and created_text:
        caption_html += (
            f'<div style="{_STATUS_ROW_STYLE}">'
            f"<span>{modified_text}</span><span>{created_text}</span></div>"
        )
    elif modified_text:
        caption_html += f"<div>{modified_text}</div>"
    elif created_text:
        caption_html += f"<div>{created_text}</div>"

    st.caption(caption_html, unsafe_allow_html=True)

    try:
        preview = read_text_preview(file_path, max_bytes=_PREVIEW_LIMIT_BYTES)
    except OSError:
        st.warning(strings["FILES_PREVIEW_READ_ERROR"].format(file=preview_relative_path))
        return

    with st.container(
        height=SCROLLABLE_DIALOG_CONTENT_HEIGHT_PX,
        border=False,
        key=_PREVIEW_DIALOG_CONTENT_KEY,
    ):
        if preview.text:
            st.code(
                preview.text,
                language="text",
                line_numbers=True,
                wrap_lines=False,
            )
        else:
            st.info(strings["FILES_PREVIEW_EMPTY"].format(file=file_name))
        if preview.truncated:
            st.caption(strings["FILES_PREVIEW_TRUNCATED"].format(limit_kib=_PREVIEW_LIMIT_KIB))


def _on_delete_folder_dismiss() -> None:
    st.session_state.delete_folder_relative_path = ""


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_delete_folder_dismiss)
def _delete_folder_confirmation_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    relative_path = str(st.session_state.get("delete_folder_relative_path", ""))
    if not relative_path:
        return
    folder_name = Path(relative_path).name

    def _cancel() -> None:
        st.session_state.delete_folder_relative_path = ""
        st.rerun()

    render_confirm_dialog(
        title=strings["FILES_DELETE_FOLDER_DIALOG_TITLE"],
        body=strings["FILES_DELETE_FOLDER_DIALOG_BODY"].format(folder=folder_name),
        body_as_warning=True,
        cancel_label=strings["FILES_DELETE_DIALOG_CANCEL"],
        cancel_key="delete_folder_cancel_button",
        on_cancel=_cancel,
        confirm_label=strings["FILES_DELETE_FOLDER_DIALOG_CONFIRM"],
        confirm_key="delete_folder_confirm_button",
        confirm_icon=":material/delete_forever:",
        on_confirm=lambda: _delete_folder(relative_path),
    )


def _delete_folder(relative_path: str) -> None:
    session_folder = _session_root()
    try:
        deleted = delete_generated_folder(session_folder, relative_path)
    except (OSError, ValueError):
        deleted = False
    st.session_state.delete_folder_relative_path = ""
    if deleted:
        prefix = f"{relative_path}/"
        preview_path = str(st.session_state.get("preview_file_relative_path", ""))
        if preview_path == relative_path or preview_path.startswith(prefix):
            st.session_state.preview_file_relative_path = ""
        _cached_list_generated_files.clear()
        _cached_download_tree.clear()
    st.rerun()


def _render_file_preview_button(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    previewable = is_text_previewable(file.name)
    preview_help = (
        strings["FILES_PREVIEW_HELP"].format(file=file.name)
        if previewable
        else strings["FILES_PREVIEW_UNSUPPORTED"].format(file=file.name)
    )
    if st.button(
        label=strings["FILES_PREVIEW_BUTTON"],
        width=_ICON_BUTTON_WIDTH_PX,
        key=f"preview_{st.session_state.session_id}_{file.relative_path}",
        help=preview_help,
        disabled=_files_actions_busy() or not previewable,
    ):
        st.session_state.preview_file_relative_path = file.relative_path
        st.rerun()


def _render_folder_zip_button(relative_path: str) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    folder_name = Path(relative_path).name
    # Nothing is built on render: a folder zip reads and compresses every file
    # (heavy for vector indexes), and st.download_button needs the bytes upfront.
    # Clicking opens a modal that builds it on demand and auto-starts the
    # download, so the file tree stays fast and low-memory even with big indexes.
    if st.button(
        strings["FILES_DOWNLOAD_ZIP_BUTTON"],
        width="content",
        key=f"export_zip_{st.session_state.session_id}_{relative_path}",
        help=strings["FILES_DOWNLOAD_ZIP_HELP"].format(folder=folder_name),
        disabled=_files_actions_busy(),
    ):
        st.session_state.export_folder_relative_path = relative_path
        st.session_state.pop("export_zip_payload", None)
        st.session_state.export_autoclicked = False
        st.rerun()


def _on_export_dismiss() -> None:
    st.session_state.export_folder_relative_path = ""
    st.session_state.pop("export_zip_payload", None)
    st.session_state.pop("export_autoclicked", None)


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_export_dismiss)
def _export_folder_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    relative_path = str(st.session_state.get("export_folder_relative_path", ""))
    if not relative_path:
        return
    folder_name = Path(relative_path).name

    # Build once and reuse across the dialog's reruns (bounded: cleared on
    # dismiss), so the auto-click rerun never rebuilds the zip. The spinner shows
    # inside the modal, which blocks the rest of the UI while preparing.
    payload = st.session_state.get("export_zip_payload")
    if not isinstance(payload, dict) or payload.get("relative_path") != relative_path:
        session_folder = _session_root()
        with st.spinner(strings["FILES_EXPORT_PREPARING"].format(folder=folder_name)):
            try:
                zip_bytes = build_folder_zip_bytes(
                    session_folder,
                    relative_path,
                    signing_secret=get_settings().zip_signing_secret,
                )
            except (OSError, ValueError):
                st.error(strings["FILES_DOWNLOAD_ZIP_TOO_LARGE"].format(folder=folder_name))
                return
        payload = {"relative_path": relative_path, "bytes": zip_bytes}
        st.session_state.export_zip_payload = payload
        st.session_state.export_autoclicked = False

    zip_bytes = payload["bytes"]
    if len(zip_bytes) > _DOWNLOAD_LIMIT_BYTES:
        st.warning(strings["FILES_DOWNLOAD_ZIP_TOO_LARGE"].format(folder=folder_name))
        return

    download_key = f"export_download_{relative_path}"
    st.download_button(
        label=strings["FILES_DOWNLOAD_ZIP_BUTTON"],
        data=zip_bytes,
        file_name=f"{folder_name}.zip",
        mime="application/zip",
        width="stretch",
        key=download_key,
        help=strings["FILES_DOWNLOAD_ZIP_HELP"].format(folder=folder_name),
    )
    st.caption(strings["FILES_EXPORT_DOWNLOAD_STARTED"])
    # Auto-start the download once. The click triggers a rerun, so re-injecting
    # the click script would loop — guard it behind a one-shot flag. The visible
    # button above remains as a manual fallback if the browser blocks the click.
    if not st.session_state.get("export_autoclicked"):
        st.session_state.export_autoclicked = True
        click_widget(download_key)


def _render_open_export_dialog() -> None:
    export_path = str(st.session_state.get("export_folder_relative_path", ""))
    if not export_path:
        return
    if not (_session_root() / export_path).is_dir():
        _on_export_dismiss()
        return
    _export_folder_dialog()


def _render_folder_delete_button(relative_path: str) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    folder_name = Path(relative_path).name
    if st.button(
        label=strings["FILES_DELETE_FOLDER_BUTTON"],
        icon=":material/delete_forever:",
        key=f"delete_folder_{st.session_state.session_id}_{relative_path}",
        help=strings["FILES_DELETE_FOLDER_HELP"].format(folder=folder_name),
        disabled=_files_actions_busy(),
    ):
        st.session_state.delete_folder_relative_path = relative_path
        st.rerun()


def render_generated_file_download(file: GeneratedFile) -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    try:
        current_size = file.path.stat().st_size
    except OSError:
        return
    with st.container(
        horizontal=True,
        vertical_alignment="center",
        width="content",
        gap="xxsmall",
    ):
        _render_file_preview_button(file)
        size_label = format_file_size(current_size)
        if not file.download_allowed or current_size > _DOWNLOAD_LIMIT_BYTES:
            st.button(
                label=f"📄 {file.name} • {size_label}",
                disabled=True,
                help=strings["FILES_DOWNLOAD_TOO_LARGE"].format(file=file.name),
                key=f"download_blocked_{st.session_state.session_id}_{file.relative_path}",
            )
        else:
            mime_type = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            with file.path.open("rb") as file_obj:
                file_bytes = file_obj.read()
            st.download_button(
                label=f"📄 {file.name} • {size_label}",
                data=file_bytes,
                file_name=file.name,
                mime=mime_type,
                key=f"download_{st.session_state.session_id}_{file.relative_path}",
                disabled=_files_actions_busy(),
            )


def render_download_tree(
    tree: Mapping[str, Any], *, allow_run_folder_collapse: bool = True
) -> None:
    entries = sorted(
        tree.items(),
        key=lambda item: download_tree_entry_sort_key(
            item[0],
            item[1],
            top_level=allow_run_folder_collapse,
        ),
    )
    for name, entry in entries:
        if isinstance(entry, dict):
            folder_label = name
            folder_node: Mapping[str, Any] = entry
            if allow_run_folder_collapse:
                if is_history_folder(name):
                    folder_label = format_history_folder_label(name, entry)
                else:
                    folder_label, folder_node = collapse_artifact_run_folder(name, entry)
            with st.expander(folder_label, icon=download_folder_icon(name)):
                render_download_tree(
                    folder_node,
                    allow_run_folder_collapse=False,
                )
                if allow_run_folder_collapse and (is_run_folder(name) or is_history_folder(name)):
                    with st.container(
                        horizontal=True,
                        vertical_alignment="center",
                        width="content",
                        gap="xxsmall",
                    ):
                        _render_folder_zip_button(name)
                        # A crawl folder's site graph opens the 3D "universe"
                        # viewer (see app_support.site_graph_3d); place it right
                        # of Export. Other folders (vector, history) have none.
                        site_graph = find_site_graph_file(folder_node)
                        if site_graph is not None:
                            render_explore_3d_button(site_graph, disabled=_files_actions_busy())
                        _render_folder_delete_button(name)
            continue
        render_generated_file_download(entry)


def _render_ready_result_panel() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    session_root = _session_root()
    active_output_dir = str(st.session_state.get("active_output_dir", ""))
    ready: ReadyDownload | None = None
    if active_output_dir:
        ready = build_ready_download(
            active_output_dir,
            session_root,
            download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
        )
    if ready is None:
        ready = find_ready_download_in_session(
            session_root,
            download_limit_bytes=_DOWNLOAD_LIMIT_BYTES,
        )
    if ready is not None:
        _render_ready_result(ready, strings, session_root)


def _render_ready_result(ready: ReadyDownload, strings: dict[str, Any], session_root: Path) -> None:
    is_zip = ready.file.file_type == "zip"
    subtitle = (
        strings["READY_RESULT_ZIP_SUBTITLE"].format(count=ready.source_count)
        if is_zip
        else strings["READY_RESULT_SINGLE_SUBTITLE"]
    )
    path_parts = ready.file.relative_path.split("/")
    crawl_label = path_parts[0] if path_parts else ""
    timestamp = path_parts[1] if len(path_parts) > 1 else ""
    if crawl_label:
        subtitle = f"{subtitle} ({crawl_label})"
    if crawl_label and timestamp:
        download_name = f"{crawl_label}_{timestamp}.{ready.file.file_type}"
    else:
        download_name = ready.file.name
    st.markdown(
        f'<h3 style="margin-bottom:0;padding-bottom:0">{strings["READY_RESULT_HEADER"]}</h3>'
        f'<p style="opacity:0.7;font-size:0.875rem;margin:0 0 0.75rem">'
        f"{subtitle}</p>",
        unsafe_allow_html=True,
    )
    if not ready.file.download_allowed:
        st.warning(strings["READY_RESULT_TOO_LARGE"])
        return
    try:
        file_bytes = ready.file.path.read_bytes()
    except OSError:
        return
    mime_type = mimetypes.guess_type(download_name)[0] or "application/octet-stream"
    # With a site graph, put Download and Explore in 3D side by side (50/50);
    # otherwise Download spans the full width on its own.
    site_graph = find_site_graph_for_result(session_root, ready.file.relative_path)
    download_col: Any = nullcontext()
    explore_col = None
    if site_graph is not None:
        download_col, explore_col = st.columns(2, vertical_alignment="center")
    with download_col:
        st.download_button(
            label=strings["READY_RESULT_DOWNLOAD_BUTTON"],
            data=file_bytes,
            file_name=download_name,
            mime=mime_type,
            key=f"ready_result_{st.session_state.session_id}_{st.session_state.get('crawl_id', '')}",
            width="stretch",
        )
    if explore_col is not None:
        with explore_col:
            render_explore_3d_button(
                site_graph, disabled=_files_actions_busy(), key_suffix="ready", full_width=True
            )


def _render_open_preview_dialog(files: list[GeneratedFile]) -> None:
    preview_relative_path = str(st.session_state.get("preview_file_relative_path", ""))
    if not preview_relative_path:
        return
    file_by_relative_path = {file.relative_path: file for file in files}
    if preview_relative_path not in file_by_relative_path:
        st.session_state.preview_file_relative_path = ""
        return
    _file_preview_dialog()


def _render_open_delete_folder_dialog() -> None:
    delete_folder_path = str(st.session_state.get("delete_folder_relative_path", ""))
    if not delete_folder_path:
        return
    target = _session_root() / delete_folder_path
    if not target.is_dir():
        st.session_state.delete_folder_relative_path = ""
        return
    _delete_folder_confirmation_dialog()


def _open_upload_dialog() -> None:
    st.session_state.pop("upload_zip_file", None)  # drop any prior pending file
    st.session_state.upload_dialog_open = True


def _render_import_button() -> None:
    """Render the Import button (mirrors the Export button style) at the top of the tree."""
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.button(
        label=strings["FILES_UPLOAD_BUTTON"],
        width="content",
        key="open_upload_dialog",
        help=strings["FILES_UPLOAD_BUTTON_HELP"],
        on_click=_open_upload_dialog,
        disabled=_files_actions_busy(),
    )


def _on_upload_dismiss() -> None:
    st.session_state.upload_dialog_open = False


def _import_uploaded_zip(zip_bytes: bytes) -> None:
    secret = get_settings().zip_signing_secret
    try:
        added = import_signed_zip(_session_root(), zip_bytes, secret)
    except (OSError, ValueError):
        added = None
    st.session_state.upload_dialog_open = False
    if added:
        st.session_state.upload_done_folder = added
        _cached_list_generated_files.clear()
        _cached_download_tree.clear()
    st.rerun()


def _import_uploaded_history_zip(zip_bytes: bytes) -> None:
    """Replace a per-session history folder in place from an uploaded history zip."""
    secret = get_settings().zip_signing_secret
    try:
        replaced = import_history_zip(_session_root(), zip_bytes, secret)
    except (OSError, ValueError):
        replaced = None
    st.session_state.upload_dialog_open = False
    if replaced:
        st.session_state.upload_done_folder = replaced
        _cached_list_generated_files.clear()
        _cached_download_tree.clear()
    st.rerun()


_SAMPLE_CATEGORY_CRAWL = "crawl_results"
_SAMPLE_CATEGORY_VECTOR = "vector_indexes"


def _import_sample_fixture_action(category: str, name: str) -> None:
    """Import a bundled sample into the session, then flag a success toast.

    Ends with a full app rerun (not the fragment-scoped one) so the shell fires
    the toast — same pattern as the signed-zip import.
    """
    added = import_sample_fixture(_session_root(), category, name)
    if added:
        st.session_state.sample_import_done_folder = added
        _cached_list_generated_files.clear()
        _cached_download_tree.clear()
    st.rerun()


def _render_sample_data_panel() -> None:
    """Render the collapsed Sample data panel: one-click import of bundled fixtures.

    Lets a user skip Steps 1-2 by importing a ready-made crawl or index into the
    session, then jump to Semantic search. Trusted repo files, so no signature
    check. One nested panel per fixtures category; each archive imports on click.
    """
    fixtures = list_sample_fixtures()
    if not fixtures:
        return
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    with st.expander(strings["FILES_SAMPLE_PANEL_TITLE"], expanded=False):
        st.caption(strings["FILES_SAMPLE_PANEL_CAPTION"])
        for category in sorted({fixture.category for fixture in fixtures}):
            if category == _SAMPLE_CATEGORY_CRAWL:
                label = strings["FILES_SAMPLE_CATEGORY_CRAWL_RESULTS"]
            elif category == _SAMPLE_CATEGORY_VECTOR:
                label = strings["FILES_SAMPLE_CATEGORY_VECTOR_INDEXES"]
            else:
                label = category.replace("_", " ").capitalize()
            with st.expander(label, expanded=False):
                for fixture in fixtures:
                    if fixture.category != category:
                        continue
                    if st.button(
                        label=f"{fixture.name} • {format_file_size(fixture.size_bytes)}",
                        icon=":material/move_to_inbox:",
                        help=strings["FILES_SAMPLE_IMPORT_HELP"],
                        key=f"sample_import_{fixture.category}_{fixture.name}",
                        disabled=_files_actions_busy(),
                    ):
                        _import_sample_fixture_action(fixture.category, fixture.name)


@st.dialog(_DIALOG_PLACEHOLDER_TITLE, width="small", on_dismiss=_on_upload_dismiss)
def _upload_folder_dialog() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    st.subheader(strings["FILES_UPLOAD_DIALOG_TITLE"])
    uploaded = st.file_uploader(strings["FILES_UPLOAD_PROMPT"], type=["zip"], key="upload_zip_file")
    if uploaded is None:
        return
    zip_bytes = uploaded.getvalue()
    # Fast-fail check; import_signed_zip re-verifies to avoid a TOCTOU gap.
    if not verify_zip_bytes(zip_bytes, get_settings().zip_signing_secret):
        st.error(strings["FILES_UPLOAD_INVALID"])
        return

    def _cancel() -> None:
        st.session_state.upload_dialog_open = False
        st.rerun()

    top = zip_top_folder(zip_bytes) or ""
    if is_history_folder(top):
        # History imports replace that folder in place. Always confirm (consistent
        # with crawl/vector import); warn when there is existing data to overwrite.
        overwrite = history_exists(_session_root(), top)
        if overwrite:
            body = strings["FILES_UPLOAD_HISTORY_OVERWRITE_BODY"].format(folder=top)
            confirm_label = strings["FILES_UPLOAD_HISTORY_OVERWRITE_CONFIRM"]
        else:
            body = strings["FILES_UPLOAD_HISTORY_IMPORT_BODY"].format(folder=top)
            confirm_label = strings["FILES_UPLOAD_CONFIRM"]
        render_confirm_dialog(
            body=body,
            body_as_warning=overwrite,
            cancel_label=strings["FILES_UPLOAD_CANCEL"],
            cancel_key="upload_cancel_button",
            on_cancel=_cancel,
            confirm_label=confirm_label,
            confirm_key="upload_confirm_button",
            confirm_icon=":material/upload:",
            on_confirm=lambda: _import_uploaded_history_zip(zip_bytes),
        )
        return

    target = import_target_name(_session_root(), top)
    render_confirm_dialog(
        body=strings["FILES_UPLOAD_CONFIRM_BODY"].format(folder=target),
        cancel_label=strings["FILES_UPLOAD_CANCEL"],
        cancel_key="upload_cancel_button",
        on_cancel=_cancel,
        confirm_label=strings["FILES_UPLOAD_CONFIRM"],
        confirm_key="upload_confirm_button",
        confirm_icon=":material/upload:",
        on_confirm=lambda: _import_uploaded_zip(zip_bytes),
    )


def _session_log_generated_file() -> GeneratedFile | None:
    """Return a GeneratedFile for the current session's log, or None if absent.

    Built from a fresh ``stat`` (not the cached file listing), so the row always
    reflects the live log size even as it grows during a crawl.
    """
    relative_path = get_settings().log_file
    log_path = _session_root() / relative_path
    if not log_path.is_file():
        return None
    try:
        stat_result = log_path.stat()
    except OSError:
        return None
    return GeneratedFile(
        path=log_path,
        relative_path=relative_path,
        name=log_path.name,
        size_bytes=stat_result.st_size,
        modified_at=datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc),
        file_type="log",
        download_allowed=stat_result.st_size <= _DOWNLOAD_LIMIT_BYTES,
    )


def _should_show_files_panel(*, job_alive: bool, has_files: bool) -> bool:
    """Decide whether the 📁 Files & folders panel renders this run.

    While a crawl/index job is active, show it only when it already holds files,
    so an empty panel never flashes mid-write. When idle, always show it — even
    before the session folder exists — so the Import button stays reachable after
    a browser reset clears the session and its outputs.
    """
    if job_alive:
        return has_files
    return True


def _downloads_body() -> None:
    strings = get_strings(st.session_state.get("language", _DEFAULT_LANGUAGE))
    session_folder = _session_root()
    session_folder_str = str(session_folder.resolve())
    files = _cached_list_generated_files(
        session_folder_str,
        session_folder_str,
        _DOWNLOAD_LIMIT_BYTES,
        generated_files_cache_token(session_folder),
    )
    # Merge in the (live) session log, replacing any stale cached entry, so the
    # tree, dataframe, and preview all reflect its current state.
    session_log = _session_log_generated_file()
    if session_log is not None:
        files = files_excluding(files, session_log.relative_path)
        files.append(session_log)
    # The session log is rendered on its own above the tree; keep it out of the
    # tree so its preview widget key is not created twice in the same pass.
    tree_files = files_excluding(files, session_log.relative_path if session_log else None)
    download_tree = _cached_download_tree(tuple(tree_files))
    job_alive = _job_is_alive(st.session_state.job)
    subtitle_text = (
        strings["FILES_DOWNLOADS_IN_PROGRESS"] if job_alive else strings["FILES_DOWNLOADS_SUBTITLE"]
    )
    st.markdown(
        f'<h3 style="padding-bottom:0">{strings["FILES_DOWNLOADS_SUBHEADER"]}</h3>'
        f'<p style="opacity:0.6;font-size:0.875rem;margin:0 0 0rem">{subtitle_text}</p>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("upload_dialog_open"):
        _upload_folder_dialog()
    st.markdown(
        """
        <style>
        div[data-testid="stElementContainer"][class*="st-key-delete_folder_"] button {
            color: #dc3545;
        }
        div[data-testid="stElementContainer"][class*="st-key-delete_folder_"] button:hover {
            color: #c82333; border-color: #dc3545;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    # The Import button always renders (disabled mid-job) so its position stays
    # stable; the panel-visibility rule itself lives in _should_show_files_panel.
    show_panel = _should_show_files_panel(job_alive=job_alive, has_files=bool(files))
    if show_panel:
        with st.expander(strings["FILES_CRAWL_RESULT_LABEL"], expanded=True):
            _render_import_button()
            if session_log is not None:
                render_generated_file_download(session_log)
            render_download_tree(download_tree)

    if files:
        rows = [
            {
                strings["FILES_COL_NAME"]: file.relative_path,
                strings["FILES_COL_TYPE"]: file.file_type,
                strings["FILES_COL_SIZE"]: round(file.size_bytes / (1024 * 1024), 3),
                strings["FILES_COL_MODIFIED"]: file.modified_at.strftime(_UTC_DISPLAY_FORMAT),
            }
            for file in files
        ]
        with st.expander(strings["FILES_HEADER"], expanded=False):
            st.dataframe(rows, hide_index=True, width="stretch", lazy=True)

    _render_sample_data_panel()

    _render_open_preview_dialog(files)
    _render_open_delete_folder_dialog()
    _render_open_export_dialog()


def _render_downloads() -> None:
    """Auto-rerun downloads only while a crawl or vector-index job is active."""
    _auto_refresh_fragment(
        _downloads_body,
        active=_crawl_job_active() or _vector_job_active(),
        interval=_DOWNLOADS_REFRESH_INTERVAL,
    )
