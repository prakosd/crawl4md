# artifact_store

Shared, UI-agnostic foundation for managing persisted project artifacts. It is the
shared foundation the `crawl4md` core library, the `vector_indexer` and `rag_engine`
libraries, and the Streamlit app all build on. It depends on the Python standard
library plus `log4py` (the zero-dependency logging base layer) only — no crawler,
no UI, no third-party packages.

## Why it exists

Crawl outputs, uploaded files, and vector indexes all need the same primitives:
consistent timestamped folder names, safe path handling, and safe archive reading.
`artifact_store` keeps that logic in one place so every producer and consumer stays
consistent and no module re-implements (or diverges on) naming or path safety.

## Modules

| Module | Responsibility |
|---|---|
| `naming.py` | Single source of truth for the UTC timestamp slug, the `crawl_` / `vector_` folder prefixes, and generic sequence helpers (`format_sequence_id`, `folder_name`, `parse_folder_sequence`, `sequence_sort_key`). `crawl4md.naming` re-exports these. |
| `paths.py` | `ensure_within_root(root, path)` — the directory-traversal guard used before any file read or write. |
| `archives.py` | Zip-slip-safe extraction of `.md` / `.txt` members only, capped per member to guard against decompression bombs (`iter_text_members`, `extract_text_members`, `is_safe_member_name`). Plus `extract_all_members` (any file type, for full-folder re-import — streams each member to disk in bounded chunks with no size cap, since it serves only HMAC-verified archives) and `sign_zip_bytes` / `verify_zip_bytes` (HMAC `.crawl4md.sig` sidecar). |
| `crawl_results.py` | `list_crawl_result_files(session_root)` — discover a crawl's success content, preferring the final sorted output and falling back to `round_N/` snapshots for stopped crawls. |
| `messages.py` | `LibraryMessage` — the shared structured-message primitive (`code`, `default_text`, `params`, `severity`) every library uses to report warnings/errors/progress to any UI. |

## Structured messages

`LibraryMessage` lets the libraries report user-facing warnings and errors as
**data**, so any UI can localize them without parsing English text. `str(message)`
returns `default_text` (a complete English sentence), and `message.as_dict()` returns
a JSON-serializable `{code, text, severity, params}`.

```python
from artifact_store import LibraryMessage, SEVERITY_WARNING

message = LibraryMessage(
    code="vector.dimension_mismatch",
    default_text="Requested dimension 1024 is unsupported; using 384.",
    params={"requested_dimension": 1024, "actual_dimension": 384},
    severity=SEVERITY_WARNING,
)
str(message)        # English fallback for logs/JSON
message.as_dict()   # {code, text, severity, params} for a UI to localize
```

`crawl4md`, `vector_indexer`, and `rag_engine` build their messages on this primitive;
see [docs/BUILDING_ANOTHER_UI.md](../../docs/BUILDING_ANOTHER_UI.md) for the full contract.


## Examples

```python
from artifact_store import (
    format_utc_timestamp_slug,
    VECTOR_FOLDER_PREFIX,
    folder_name,
    ensure_within_root,
    iter_text_members,
    list_crawl_result_files,
)

run_dir = folder_name(VECTOR_FOLDER_PREFIX, "01_navigate")  # "vector_01_navigate"
slug = format_utc_timestamp_slug()                          # "2026-06-01_12-09-15"

# Reject paths that escape a root before reading/writing
safe = ensure_within_root("outputs/session_x", "outputs/session_x/final/a.md")

# Read only the .md/.txt members of an uploaded zip, skipping unsafe or oversized members
for name, data in iter_text_members("uploaded.zip"):
    ...

# List indexable crawl outputs for a session
files = list_crawl_result_files("outputs/streamlit_sessions/session_x")
```

## Boundary

A test asserts `artifact_store` imports nothing from `streamlit`, `app_support`,
`crawl4md`, `crawl4ai`, or `pymupdf`. Keep it that way: this package must remain a
dependency-free foundation that any future library or UI can reuse.
