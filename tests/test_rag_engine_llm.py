from __future__ import annotations

import logging

import pytest

from rag_engine import messages
from rag_engine.catalog import DEFAULT_CHAT_MODEL, ECHO_MODEL, get_chat_model_info
from rag_engine.config import ConversationalConfig, RagConfig
from rag_engine.llm import (
    ChatModelUnavailable,
    ResolvedChatModel,
    build_chat_model,
    build_echo_chat_model,
    resolve_auxiliary_model,
    resolve_chat_model,
)


def test_echo_model_builds_and_echoes_offline() -> None:
    from langchain_core.messages import HumanMessage

    model = build_echo_chat_model()
    response = model.invoke([HumanMessage("hello world")])

    assert "hello world" in response.content


def test_unknown_model_is_unavailable() -> None:
    with pytest.raises(ChatModelUnavailable):
        build_chat_model("nope/model")


def test_bedrock_without_credentials_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(ChatModelUnavailable):
        build_chat_model(DEFAULT_CHAT_MODEL)


def test_openai_without_key_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ChatModelUnavailable):
        build_chat_model("gpt-4o-mini")


def test_resolve_falls_back_to_echo(caplog: pytest.LogCaptureFixture) -> None:
    sentinel = object()

    def failing_build(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        raise ChatModelUnavailable("no credentials")

    with caplog.at_level(logging.WARNING, logger="rag_engine"):
        resolved, warnings = resolve_chat_model(
            "gpt-4o", build=failing_build, echo_build=lambda: sentinel
        )

    assert resolved.model_id == ECHO_MODEL
    assert resolved.model is sentinel
    assert any(w.code == messages.CODE_MODEL_FALLBACK_ECHO for w in warnings)
    assert any("falling back to echo" in record.getMessage() for record in caplog.records)


def test_resolve_available_model_has_no_warnings() -> None:
    sentinel = object()

    def build(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        return sentinel

    resolved, warnings = resolve_chat_model("gpt-4o", build=build, echo_build=lambda: object())

    assert resolved.model is sentinel
    assert resolved.model_id == "gpt-4o"
    assert warnings == []


def test_resolve_echo_request_failure_raises() -> None:
    def failing_build(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        raise ChatModelUnavailable("echo broken")

    with pytest.raises(ChatModelUnavailable):
        resolve_chat_model(ECHO_MODEL, build=failing_build, echo_build=lambda: object())


def test_thinking_disabled_kwargs_targets_only_bedrock_qwen() -> None:
    from rag_engine.llm import thinking_disabled_model_kwargs

    qwen = thinking_disabled_model_kwargs("qwen.qwen3-32b-v1:0", "bedrock_converse")
    assert qwen == {
        "additional_model_request_fields": {"chat_template_kwargs": {"enable_thinking": False}}
    }
    assert thinking_disabled_model_kwargs("apac.amazon.nova-lite-v1:0", "bedrock_converse") == {}
    assert thinking_disabled_model_kwargs("gpt-4o-mini", "openai") == {}
    assert thinking_disabled_model_kwargs(ECHO_MODEL, "echo") == {}


class _SentinelModel:
    """Stand-in chat model; never invoked in auxiliary-resolution tests."""


def test_aux_model_explicit_id_uses_resolver() -> None:
    captured: dict[str, str] = {}

    def resolver(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        captured["model_id"] = model_id
        return ResolvedChatModel(model=_SentinelModel(), model_id=model_id), []

    config = ConversationalConfig(aux_model_id="echo")
    resolved, warnings = resolve_auxiliary_model(config, resolver=resolver)

    assert captured["model_id"] == "echo"
    assert resolved.model_id == "echo"
    assert warnings == []


def test_aux_model_auto_picks_first_available_small_cloud() -> None:
    def builder(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        return _SentinelModel()

    resolved, warnings = resolve_auxiliary_model(ConversationalConfig(), builder=builder)

    info = get_chat_model_info(resolved.model_id)
    assert info is not None
    assert info.size == "small"
    assert info.kind == "cloud"
    assert warnings == []


def test_aux_model_falls_back_to_main_when_none_available() -> None:
    def builder(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        raise ChatModelUnavailable("no credentials")

    def resolver(model_id: str, *, temperature: float = 0.0, max_tokens: int = 1024):
        return ResolvedChatModel(model=build_echo_chat_model(), model_id=model_id), []

    config = ConversationalConfig(rag=RagConfig(llm_model="echo"))
    resolved, warnings = resolve_auxiliary_model(config, builder=builder, resolver=resolver)

    assert resolved.model_id == "echo"
    assert any(w.code == messages.CODE_AUX_MODEL_FALLBACK for w in warnings)
