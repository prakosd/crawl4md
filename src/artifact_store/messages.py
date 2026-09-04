"""UI-agnostic structured messages for libraries to report to any frontend.

A :class:`LibraryMessage` carries a stable machine-readable ``code`` plus the
structured ``params`` behind it, so a UI can localize or restyle the message
without parsing English prose. ``default_text`` is a ready-to-show English
sentence, so logs and JSON manifests stay readable even when no
localization layer is present (``str(message)`` returns it).

This module is part of the pure foundation: standard library only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

__all__ = [
    "MESSAGE_SEVERITIES",
    "SEVERITY_ERROR",
    "SEVERITY_INFO",
    "SEVERITY_WARNING",
    "LibraryMessage",
]

SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_ERROR = "error"
MESSAGE_SEVERITIES = frozenset({SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_ERROR})


@dataclass(frozen=True)
class LibraryMessage:
    """A structured, localizable message emitted by a library.

    Attributes:
        code: Stable identifier a UI maps to a localized template, e.g.
            ``"vector.dimension_mismatch"``. Not meant to be shown verbatim.
        default_text: Complete English sentence shown when no localization is
            available. ``str(message)`` returns this, so logs and
            JSON manifests stay readable.
        params: Structured values behind the message (counts, names, URLs) that a
            UI can interpolate into its own localized template.
        severity: One of :data:`MESSAGE_SEVERITIES`
            (``"info"`` / ``"warning"`` / ``"error"``).
    """

    code: str
    default_text: str
    params: Mapping[str, object] = field(default_factory=dict)
    severity: str = SEVERITY_INFO

    def __str__(self) -> str:
        return self.default_text

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation for manifests and APIs."""
        return {
            "code": self.code,
            "text": self.default_text,
            "severity": self.severity,
            "params": dict(self.params),
        }
