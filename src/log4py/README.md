# log4py

A tiny, dependency-free logging toolkit — the lowest layer of rag-playground. It
uses only the Python standard library and depends on **no** other project
package, so every library (`artifact_store`, `crawl4md`, `vector_indexer`,
`rag_engine`) and the Streamlit app can import it freely.

## Why

Logging is a cross-cutting concern. `log4py` gives every module one consistent
way to obtain a logger and lets the *application* decide — in one place — the
threshold, format, and destinations. It follows the Python logging HOWTO's advice
for libraries: modules only emit records (and attach a `NullHandler`), never
output handlers, so importing a library stays silent until an app opts in.

## API

```python
from log4py import get_logger

_logger = get_logger(__name__)          # module-level logger, silent by default
_logger.info("Indexed %d chunks", n)    # %-style deferred formatting
```

The application turns logging on once:

```python
from log4py import configure_logging

configure_logging(
    level="INFO",                        # DEBUG < INFO < WARNING < ERROR (WARN = WARNING)
    logger_names=("crawl4md", "vector_indexer", "rag_engine", "artifact_store"),
    log_file="logs/app.log",             # optional rotating file (stderr always unless stream=False)
)
```

- `get_logger(name)` → a standard `logging.Logger`, with a `NullHandler` attached
  once to its top-level logger so unconfigured use produces no output.
- `configure_logging(*, level, logger_names=(), stream=True, log_file=None,
  log_file_router=None, max_bytes, backup_count)` — attaches a stderr
  `StreamHandler` and/or a `RotatingFileHandler` to each named logger. Pass your
  package names to keep project logs separate from third-party (chromadb,
  urllib3, playwright) noise; pass nothing to configure the **root** logger
  (captures everything). Idempotent: a repeated call (e.g. a Streamlit rerun)
  replaces rather than stacks handlers.

## Per-context file routing

A single process that serves many contexts (e.g. one Streamlit server with many
browser sessions) can route each record to its own file without reconfiguring:

```python
from log4py import configure_logging

configure_logging(
    level="INFO",
    logger_names=("crawl4md", "vector_indexer", "rag_engine", "artifact_store"),
    log_file_router=current_session_log_path,   # () -> Path | None
)
```

`log_file_router` is a zero-argument callback invoked **per record**; return a
`Path` to append that record to (parents created, rotation applied per path) or
`None` to skip the file for that record. It takes precedence over `log_file`.
Because background worker threads do not inherit the caller's context, set the
routing context (e.g. a `contextvars.ContextVar`) at the start of each thread so
its logs land in the right file.

## Log line format

```
2026-07-05 11:13:01 INFO crawl4md.crawler Starting crawl of 1 URL (limit 100)
```

`<datetime> <LEVEL> <logger name> <message>` — the logger name tracks the
package/module hierarchy, so it's obvious where each event originated.

## Level guidance

| Level | Use for |
|---|---|
| `DEBUG` | Detailed diagnostics: per-item decisions, retries, skips. |
| `INFO` | Lifecycle milestones and counts: start/finish of an operation. |
| `WARNING` | Recoverable/unexpected: fallbacks, skipped files, WAF hits, cancellations. |
| `ERROR` | A caught failure that stopped a function (use `logger.exception` in `except`). |

Never log secrets, credentials, PII, prompt text, or query content.
