from __future__ import annotations

from artifact_store import SEVERITY_ERROR, SEVERITY_INFO, SEVERITY_WARNING
from rag_engine import messages


def test_model_fallback_echo_is_a_warning() -> None:
    message = messages.model_fallback_echo("gpt-4o", "no credentials")

    assert message.code == messages.CODE_MODEL_FALLBACK_ECHO
    assert message.severity == SEVERITY_WARNING
    assert message.params["requested_model"] == "gpt-4o"


def test_classify_generation_failure_detects_ssl() -> None:
    message = messages.classify_generation_failure("CERTIFICATE_VERIFY_FAILED while connecting")

    assert message.code == messages.CODE_SSL_CERTIFICATE
    assert message.severity == SEVERITY_ERROR


def test_classify_generation_failure_generic() -> None:
    message = messages.classify_generation_failure("some random failure")

    assert message.code == messages.CODE_GENERATION_FAILED
    assert message.severity == SEVERITY_ERROR


def test_index_not_found_is_an_error() -> None:
    message = messages.index_not_found("/tmp/x")

    assert message.code == messages.CODE_INDEX_NOT_FOUND
    assert message.severity == SEVERITY_ERROR
    assert message.params["path"] == "/tmp/x"


def test_no_context_is_a_warning() -> None:
    message = messages.no_context()

    assert message.code == messages.CODE_NO_CONTEXT
    assert message.severity == SEVERITY_WARNING


def test_plan_skipped_offline_is_a_warning() -> None:
    message = messages.plan_skipped_offline()

    assert message.code == messages.CODE_PLAN_SKIPPED_OFFLINE
    assert message.severity == SEVERITY_WARNING


def test_plan_unparsable_is_a_warning() -> None:
    message = messages.plan_unparsable()

    assert message.code == messages.CODE_PLAN_UNPARSABLE
    assert message.severity == SEVERITY_WARNING


def test_aux_model_fallback_carries_detail() -> None:
    message = messages.aux_model_fallback("no small cloud model")

    assert message.code == messages.CODE_AUX_MODEL_FALLBACK
    assert message.severity == SEVERITY_WARNING
    assert message.params["detail"] == "no small cloud model"


def test_rerank_unavailable_carries_mode() -> None:
    message = messages.rerank_unavailable("local", "sentence-transformers not installed")

    assert message.code == messages.CODE_RERANK_UNAVAILABLE
    assert message.severity == SEVERITY_WARNING
    assert message.params["mode"] == "local"


def test_followups_none_valid_is_a_warning() -> None:
    message = messages.followups_none_valid()

    assert message.code == messages.CODE_FOLLOWUPS_NONE_VALID
    assert message.severity == SEVERITY_WARNING


def test_followups_generation_failed_is_a_warning() -> None:
    message = messages.followups_generation_failed("boom")

    assert message.code == messages.CODE_FOLLOWUPS_GENERATION_FAILED
    assert message.severity == SEVERITY_WARNING


def test_retrieval_partial_failure_is_a_warning() -> None:
    message = messages.retrieval_partial_failure("q2 failed")

    assert message.code == messages.CODE_RETRIEVAL_PARTIAL_FAILURE
    assert message.severity == SEVERITY_WARNING


def test_progress_builders_are_info_severity_with_stage_codes() -> None:
    pairs = (
        (messages.progress_plan(), messages.CODE_PROGRESS_PLAN),
        (messages.progress_retrieve(), messages.CODE_PROGRESS_RETRIEVE),
        (messages.progress_rerank(), messages.CODE_PROGRESS_RERANK),
        (messages.progress_answer(), messages.CODE_PROGRESS_ANSWER),
        (messages.progress_state(), messages.CODE_PROGRESS_STATE),
    )
    for message, code in pairs:
        assert message.code == code
        assert message.severity == SEVERITY_INFO
        assert message.default_text
