---
description: "Use when editing the artifact_store package in src/artifact_store/ or its tests. Covers the pure-foundation boundary, naming/timestamp single source of truth, path containment, and zip-slip-safe archive extraction."
applyTo: "src/artifact_store/**, tests/test_artifact_store_*.py"
---

# artifact_store

Shared, UI-agnostic foundation for managing persisted project artifacts. It is the
lowest layer: `crawl4md`, `vector_indexer`, and the Streamlit app all depend on it.

## Constraints

- **Pure foundation.** `artifact_store` must not import `streamlit`, `app_support`, `crawl4md`, `crawl4ai`, or `pymupdf`. It uses the standard library plus `log4py` (the logging base layer, itself pure stdlib) only. A boundary test enforces this.
- **Single source of truth for naming.** `naming.py` owns the UTC timestamp slug (`format_utc_timestamp_slug`, `parse_utc_timestamp_slug`, `UTC_TIMESTAMP_SLUG_FORMAT`), folder prefixes (`CRAWL_FOLDER_PREFIX`, `VECTOR_FOLDER_PREFIX`), and the generic sequence helpers (`format_sequence_id`, `folder_name`, `parse_folder_sequence`, `sequence_sort_key`). `crawl4md.naming` re-exports/wraps these; do not duplicate the timestamp format or sequence regex elsewhere.
- **Path containment.** `paths.ensure_within_root(root, path)` is the only directory-traversal guard. Call it before reading or writing any discovered/extracted file.
- **Zip-slip safety.** `archives.py` accepts only `.md`/`.txt` members (`TEXT_MEMBER_SUFFIXES`) and rejects unsafe member names (`is_safe_member_name`: absolute paths, drive prefixes, `..`). `extract_text_members` re-checks containment with `ensure_within_root`; `extract_all_members` does the same for any file type (full-folder re-import), enforcing containment before any bytes are written. The in-memory text-member paths (`iter_text_members`, `extract_text_members`) read each member with a per-member cap (`_MAX_MEMBER_BYTES`, 50 MiB) so a decompression bomb cannot exhaust memory; oversized text members are skipped like unsupported ones. `extract_all_members` serves only HMAC-verified (trusted) re-imports, so it streams each member to disk in `_COPY_CHUNK_BYTES` chunks (bounded memory) with **no** per-member size cap — large vector stores (`chroma.sqlite3`, `data_level0.bin`) import intact. Skipped unsafe/oversized members are logged at WARNING via `log4py` (`get_logger(__name__)`).
- **Signed archives.** `sign_zip_bytes`/`verify_zip_bytes` add and check an HMAC-SHA256 `.crawl4md.sig` sidecar (excluded from the payload and never extracted) so a downloaded zip can be re-uploaded only to an instance with the same key and unaltered contents. Digest folds members in sorted, length-prefixed order, chunk-streamed; verify is constant-time and never raises on tamper/bad-zip.
- **Crawl-result discovery.** `crawl_results.list_crawl_result_files(session_root)` returns each crawl's success content for indexing. It prefers the final sorted output (`final/sorted_success_content_*`), then unsorted final files, then the newest `round_N/` snapshot so stopped/in-progress crawls are still selectable. URL lists, failed-page content, and the generated `success_content.zip` are excluded. Keep it free of UI concerns; return the lightweight `CrawlResultFile` dataclass, not the app's `GeneratedFile`.
- **Structured messages.** `messages.py` owns `LibraryMessage` (`code`, `default_text`, `params`, `severity`) — the shared primitive every library uses to report warnings/errors to any UI. `str()` returns `default_text`; `as_dict()` is JSON-serializable. Per-library message codes/builders live in that library (`crawl4md.messages`, `vector_indexer.messages`), not here; `artifact_store` only owns the primitive.
- Group module-level constants as `_UPPER_SNAKE_CASE`; compile regexes once (use `functools.cache` for prefix-parameterized patterns, not `lru_cache(maxsize=None)`).

## Tests

- Live in `tests/` (run by `python -m pytest tests/ -q`, linted by `ruff check src/ tests/`).
- Use `tmp_path` only — no real network or filesystem outside the fixture.
- Cover naming round-trips, containment rejection, zip-slip rejection, and crawl-result discovery edge cases.
