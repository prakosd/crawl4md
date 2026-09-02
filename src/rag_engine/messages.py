"""Stable message codes and builders for the rag_engine result contract.

Every warning or error a UI sees on a :class:`~rag_engine.models.RagAnswer` is a
:class:`~artifact_store.LibraryMessage` built here. Each carries a stable
``code`` (which a UI maps to a localized template) plus the structured ``params``
behind it; ``default_text`` is the English shown when no localization exists.
"""

from __future__ import annotations

from artifact_store import SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING, LibraryMessage

__all__ = [
    "CODE_AUX_MODEL_FALLBACK",
    "CODE_EMBEDDING_UNAVAILABLE",
    "CODE_EMPTY_QUESTION",
    "CODE_FOLLOWUPS_GENERATION_FAILED",
    "CODE_FOLLOWUPS_NONE_VALID",
    "CODE_GENERATION_FAILED",
    "CODE_INDEX_NOT_FOUND",
    "CODE_INDEX_UNREADABLE",
    "CODE_MODEL_FALLBACK_ECHO",
    "CODE_MODEL_UNAVAILABLE",
    "CODE_NO_CONTEXT",
    "CODE_PLAN_SKIPPED_OFFLINE",
    "CODE_PLAN_UNPARSABLE",
    "CODE_PROGRESS_ANSWER",
    "CODE_PROGRESS_PLAN",
    "CODE_PROGRESS_RERANK",
    "CODE_PROGRESS_RETRIEVE",
    "CODE_PROGRESS_STATE",
    "CODE_RERANK_UNAVAILABLE",
    "CODE_RETRIEVAL_FAILED",
    "CODE_RETRIEVAL_PARTIAL_FAILURE",
    "CODE_SSL_CERTIFICATE",
    "aux_model_fallback",
    "classify_generation_failure",
    "embedding_unavailable",
    "empty_question",
    "followups_generation_failed",
    "followups_none_valid",
    "index_not_found",
    "index_unreadable",
    "model_fallback_echo",
    "model_unavailable",
    "no_context",
    "plan_skipped_offline",
    "plan_unparsable",
    "progress_answer",
    "progress_plan",
    "progress_rerank",
    "progress_retrieve",
    "progress_state",
    "rerank_unavailable",
    "retrieval_failed",
    "retrieval_partial_failure",
]

CODE_INDEX_NOT_FOUND = "rag.index_not_found"
CODE_INDEX_UNREADABLE = "rag.index_unreadable"
CODE_EMBEDDING_UNAVAILABLE = "rag.embedding_unavailable"
CODE_MODEL_UNAVAILABLE = "rag.model_unavailable"
CODE_MODEL_FALLBACK_ECHO = "rag.model_fallback_echo"
CODE_RETRIEVAL_FAILED = "rag.retrieval_failed"
CODE_GENERATION_FAILED = "rag.generation_failed"
CODE_NO_CONTEXT = "rag.no_context"
CODE_EMPTY_QUESTION = "rag.empty_question"
CODE_SSL_CERTIFICATE = "rag.ssl_certificate"
CODE_PLAN_SKIPPED_OFFLINE = "rag.chat.plan_skipped_offline"
CODE_PLAN_UNPARSABLE = "rag.chat.plan_unparsable"
CODE_AUX_MODEL_FALLBACK = "rag.chat.aux_model_fallback"
CODE_RERANK_UNAVAILABLE = "rag.rerank.unavailable"
CODE_FOLLOWUPS_NONE_VALID = "rag.followups.none_valid"
CODE_FOLLOWUPS_GENERATION_FAILED = "rag.followups.generation_failed"
CODE_RETRIEVAL_PARTIAL_FAILURE = "rag.retrieval.partial_failure"
CODE_PROGRESS_PLAN = "rag.progress.plan"
CODE_PROGRESS_RETRIEVE = "rag.progress.retrieve"
CODE_PROGRESS_RERANK = "rag.progress.rerank"
CODE_PROGRESS_ANSWER = "rag.progress.answer"
CODE_PROGRESS_STATE = "rag.progress.state"

# Substrings that mark a TLS/SSL certificate failure inside a backend exception.
_SSL_ERROR_SIGNATURES = (
    "certificate_verify_failed",
    "certificate verify failed",
    "sslcertverificationerror",
    "ssl: certificate",
)


def _warn(code: str, text: str, **params: object) -> LibraryMessage:
    return LibraryMessage(code=code, default_text=text, params=params, severity=SEVERITY_WARNING)


def _error(code: str, text: str, **params: object) -> LibraryMessage:
    return LibraryMessage(code=code, default_text=text, params=params, severity=SEVERITY_ERROR)


def index_not_found(path: str) -> LibraryMessage:
    return _error(CODE_INDEX_NOT_FOUND, f"No vector index was found at {path}.", path=path)


def index_unreadable(path: str, detail: str) -> LibraryMessage:
    return _error(
        CODE_INDEX_UNREADABLE,
        f"The vector index at {path} could not be read: {detail}",
        path=path,
        detail=detail,
    )


def embedding_unavailable(detail: str) -> LibraryMessage:
    return _error(
        CODE_EMBEDDING_UNAVAILABLE,
        f"The embedding model for this index is unavailable: {detail}",
        detail=detail,
    )


def model_unavailable(model: str, detail: str) -> LibraryMessage:
    return _error(
        CODE_MODEL_UNAVAILABLE,
        f"The chat model {model!r} is unavailable: {detail}",
        model=model,
        detail=detail,
    )


def model_fallback_echo(requested_model: str, detail: str) -> LibraryMessage:
    return _warn(
        CODE_MODEL_FALLBACK_ECHO,
        f"The selected chat model could not be used: {detail} "
        "Falling back to the offline echo model, which repeats the question "
        "instead of generating an answer.",
        requested_model=requested_model,
        detail=detail,
    )


def no_context() -> LibraryMessage:
    return _warn(
        CODE_NO_CONTEXT,
        "No relevant context was found in the index for this question.",
    )


def empty_question() -> LibraryMessage:
    return _error(CODE_EMPTY_QUESTION, "Enter a question to ask.")


def retrieval_failed(detail: str) -> LibraryMessage:
    return _error(CODE_RETRIEVAL_FAILED, f"Retrieving context failed: {detail}", detail=detail)


def classify_generation_failure(detail: str) -> LibraryMessage:
    """Return an SSL-specific or generic generation-failure error."""
    if any(signature in detail.lower() for signature in _SSL_ERROR_SIGNATURES):
        return _error(
            CODE_SSL_CERTIFICATE,
            "Could not reach the chat model because its TLS/SSL certificate "
            f"could not be verified: {detail}",
            detail=detail,
        )
    return _error(CODE_GENERATION_FAILED, f"Generating the answer failed: {detail}", detail=detail)


def plan_skipped_offline() -> LibraryMessage:
    return _warn(
        CODE_PLAN_SKIPPED_OFFLINE,
        "Query planning was skipped because the offline echo model was used; "
        "the question was answered as a single query.",
    )


def plan_unparsable() -> LibraryMessage:
    return _warn(
        CODE_PLAN_UNPARSABLE,
        "The planner returned an unreadable response; the question was treated as a single query.",
    )


def aux_model_fallback(detail: str) -> LibraryMessage:
    return _warn(
        CODE_AUX_MODEL_FALLBACK,
        "No small auxiliary model was available for planning and follow-ups; "
        f"using the main answer model instead: {detail}",
        detail=detail,
    )


def rerank_unavailable(mode: str, detail: str) -> LibraryMessage:
    return _warn(
        CODE_RERANK_UNAVAILABLE,
        f"Re-ranking ({mode}) is unavailable ({detail}); "
        "results were kept in their original search order.",
        mode=mode,
        detail=detail,
    )


def followups_none_valid() -> LibraryMessage:
    return _warn(
        CODE_FOLLOWUPS_NONE_VALID,
        "No follow-up suggestions passed validation for this answer.",
    )


def followups_generation_failed(detail: str) -> LibraryMessage:
    return _warn(
        CODE_FOLLOWUPS_GENERATION_FAILED,
        f"Generating follow-up suggestions failed: {detail}",
        detail=detail,
    )


def retrieval_partial_failure(detail: str) -> LibraryMessage:
    return _warn(
        CODE_RETRIEVAL_PARTIAL_FAILURE,
        f"Retrieval failed for one or more sub-questions: {detail}",
        detail=detail,
    )


def _progress(code: str, text: str) -> LibraryMessage:
    return LibraryMessage(code=code, default_text=text, params={}, severity=SEVERITY_INFO)


def progress_plan() -> LibraryMessage:
    return _progress(CODE_PROGRESS_PLAN, "Breaking your question into parts…")


def progress_retrieve() -> LibraryMessage:
    return _progress(CODE_PROGRESS_RETRIEVE, "Searching the knowledge base…")


def progress_rerank() -> LibraryMessage:
    return _progress(CODE_PROGRESS_RERANK, "Ranking the best matches…")


def progress_answer() -> LibraryMessage:
    return _progress(CODE_PROGRESS_ANSWER, "Writing the answer…")


def progress_state() -> LibraryMessage:
    return _progress(CODE_PROGRESS_STATE, "Finalizing…")
