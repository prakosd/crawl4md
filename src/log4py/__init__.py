"""log4py — a tiny, dependency-free logging toolkit for Python libraries and apps.

``log4py`` is the lowest layer of the project: pure standard library, no
dependencies (not even on the other project packages), so any library can depend
on it. Libraries obtain a logger through :func:`get_logger` and emit records
freely; the *application* decides the threshold, format, and
destinations with a single :func:`configure_logging` call. Libraries never attach
their own output handlers, so importing a library stays silent until an app opts
in — the behaviour recommended by the Python logging HOWTO for libraries.

Log lines read ``<datetime> <LEVEL> <logger name> <message>``, for example::

    2026-07-05 11:13:01 INFO crawl4md.crawler Starting crawl of 1 URL (limit 100)

Levels follow the standard threshold model (``DEBUG`` < ``INFO`` < ``WARNING`` <
``ERROR``): configuring at ``WARNING`` shows ``WARNING`` and ``ERROR`` only. The
user-facing ``WARN`` alias is accepted for ``WARNING``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path

__all__ = ["DATE_FORMAT", "LOG_FORMAT", "configure_logging", "get_logger"]

# Emitted line layout: datetime, level, logger name, then the message.
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Rotating-file defaults keep the on-disk log bounded without operator tuning.
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_BACKUP_COUNT = 3

# Tags handlers this module installs so a repeated configure_logging call
# (tests or a re-init) replaces them instead of stacking duplicates.
_MANAGED_HANDLER_ATTR = "_log4py_managed"

# The logger names a previous configure_logging call attached handlers to, so the
# next call can detach them even if it targets a different set of loggers.
_configured_logger_names: set[str] = set()


def get_logger(name: str) -> logging.Logger:
    """Return a library logger that stays silent until an app configures logging.

    A :class:`logging.NullHandler` is attached once to the caller's top-level
    logger (the first dotted segment of *name*), so libraries can log freely
    without producing output — or "No handlers could be found" noise — before any
    application calls :func:`configure_logging`.
    """
    logger = logging.getLogger(name)
    root_logger = logging.getLogger(name.split(".", 1)[0])
    if not any(isinstance(handler, logging.NullHandler) for handler in root_logger.handlers):
        root_logger.addHandler(logging.NullHandler())
    return logger


def _resolve_level(level: int | str) -> int:
    """Return the numeric logging level for an int or (case-insensitive) name."""
    if isinstance(level, bool):  # bool is an int subclass; reject it explicitly.
        raise ValueError(f"Unknown log level: {level!r}")
    if isinstance(level, int):
        return level
    normalized = str(level).strip().upper()
    resolved = logging.getLevelName(normalized)
    if not isinstance(resolved, int):
        raise ValueError(f"Unknown log level: {level!r}")
    return resolved


class _RoutingFileHandler(logging.Handler):
    """Route each record to a rotating file chosen at emit time by a callback.

    ``file_router`` returns the destination path for the *current* record, or
    ``None`` to skip the file (e.g. no active context yet). One
    ``RotatingFileHandler`` is created and cached per distinct path, so records
    for different contexts (e.g. app sessions) land in separate files without the
    caller reconfiguring logging. The router runs on the emitting thread, so a
    context set per background thread routes that thread's logs correctly.
    """

    def __init__(
        self,
        file_router: Callable[[], Path | None],
        *,
        max_bytes: int,
        backup_count: int,
    ) -> None:
        super().__init__()
        self._file_router = file_router
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._handlers: dict[str, RotatingFileHandler] = {}

    def emit(self, record: logging.LogRecord) -> None:
        handler = self._handler_for_current_record()
        if handler is not None:
            handler.emit(record)

    def _handler_for_current_record(self) -> RotatingFileHandler | None:
        try:
            path = self._file_router()
        except Exception:  # noqa: BLE001 - a router error must never break logging
            return None
        if path is None:
            return None
        key = str(path)
        handler = self._handlers.get(key)
        if handler is None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(
                    path,
                    maxBytes=self._max_bytes,
                    backupCount=self._backup_count,
                    encoding="utf-8",
                )
            except OSError:
                return None
            handler.setFormatter(self.formatter)
            self._handlers[key] = handler
        return handler

    def close(self) -> None:
        for handler in self._handlers.values():
            handler.close()
        self._handlers.clear()
        super().close()


def configure_logging(
    *,
    level: int | str = "INFO",
    logger_names: tuple[str, ...] | list[str] = (),
    stream: bool = True,
    log_file: Path | str | None = None,
    log_file_router: Callable[[], Path | None] | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    backup_count: int = _DEFAULT_BACKUP_COUNT,
) -> None:
    """Configure the given loggers to emit at *level* to stderr and/or a file.

    Call once from the application. Safe to call repeatedly: any
    handlers a previous call installed are detached (and file handlers closed)
    first, so a Streamlit rerun never stacks duplicate handlers.

    Args:
        level: Threshold level as a name (``"DEBUG"``/``"INFO"``/``"WARNING"`` or
            ``"WARN"``/``"ERROR"``) or numeric value. Records below it are dropped.
        logger_names: Top-level logger names to configure (e.g. your package
            names). Each keeps project logging separate from third-party loggers.
            When empty, the **root** logger is configured instead, which also
            captures third-party libraries.
        stream: When True, emit to ``stderr``.
        log_file: When given, also emit to this fixed rotating file (parents
            created). Ignored when ``log_file_router`` is set.
        log_file_router: When given, emit to a rotating file chosen per record by
            this callback (returning ``None`` skips the file). Takes precedence
            over ``log_file`` and lets records route to per-context files (e.g.
            one file per app session) without reconfiguring.
        max_bytes: Rotate each file once it reaches this size.
        backup_count: Number of rotated files to retain.
    """
    resolved_level = _resolve_level(level)
    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # An empty selection configures the root logger (name ""), capturing all
    # loggers; a non-empty selection isolates the named loggers from third parties.
    targets = tuple(logger_names) if logger_names else ("",)

    _detach_managed_handlers()

    handlers: list[logging.Handler] = []
    if stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        handlers.append(stream_handler)
    if log_file_router is not None:
        routing_handler = _RoutingFileHandler(
            log_file_router, max_bytes=max_bytes, backup_count=backup_count
        )
        routing_handler.setFormatter(formatter)
        handlers.append(routing_handler)
    elif log_file is not None:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    for handler in handlers:
        setattr(handler, _MANAGED_HANDLER_ATTR, True)

    # Attach the same handler instances to every target logger. A record fires
    # only its nearest ancestor's handlers (propagation stops below), so a single
    # shared RotatingFileHandler avoids concurrent-rotation races on one file.
    for name in targets:
        logger = logging.getLogger(name)
        logger.setLevel(resolved_level)
        for handler in handlers:
            logger.addHandler(handler)
        if name:  # Keep project logs from also bubbling to the root's handlers.
            logger.propagate = False

    _configured_logger_names.clear()
    _configured_logger_names.update(targets)


def _detach_managed_handlers() -> None:
    """Remove and close handlers installed by a previous configure_logging call."""
    detached: set[logging.Handler] = set()
    for name in _configured_logger_names:
        logger = logging.getLogger(name)
        for handler in [h for h in logger.handlers if getattr(h, _MANAGED_HANDLER_ATTR, False)]:
            logger.removeHandler(handler)
            detached.add(handler)
    for handler in detached:
        # Close file handlers (routing or fixed) to release their files; never
        # close the stderr stream.
        if isinstance(handler, (RotatingFileHandler, _RoutingFileHandler)):
            handler.close()
