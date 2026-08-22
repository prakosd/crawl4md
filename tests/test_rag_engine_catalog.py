from __future__ import annotations

from rag_engine.catalog import (
    CHAT_MODEL_OPTIONS,
    DEFAULT_CHAT_MODEL,
    ECHO_MODEL,
    get_chat_model_info,
)


def test_default_model_is_in_options() -> None:
    assert any(info.model_id == DEFAULT_CHAT_MODEL for info in CHAT_MODEL_OPTIONS)


def test_echo_model_is_local_and_keyless() -> None:
    info = get_chat_model_info(ECHO_MODEL)

    assert info is not None
    assert info.kind == "local"
    assert not info.requires_api_key


def test_unknown_model_returns_none() -> None:
    assert get_chat_model_info("nope/model") is None


def test_cloud_models_require_a_key() -> None:
    for info in CHAT_MODEL_OPTIONS:
        if info.kind == "cloud":
            assert info.requires_api_key


def test_lookup_ignores_surrounding_whitespace() -> None:
    assert get_chat_model_info(f"  {ECHO_MODEL}  ") is not None


def test_every_model_has_a_valid_size() -> None:
    for info in CHAT_MODEL_OPTIONS:
        assert info.size in {"small", "medium", "large"}


def test_broken_apac_models_removed_and_replacements_present() -> None:
    ids = {info.model_id for info in CHAT_MODEL_OPTIONS}
    # APAC-unavailable (invalid identifier) / legacy models were removed.
    assert "apac.anthropic.claude-3-5-haiku-20241022-v1:0" not in ids
    assert "apac.anthropic.claude-3-5-sonnet-20241022-v2:0" not in ids
    assert "apac.meta.llama3-3-70b-instruct-v1:0" not in ids
    # Active APAC Claude replacements and in-Region Qwen3 models are catalogued.
    assert "apac.anthropic.claude-sonnet-4-5-20250929-v1:0" in ids
    assert "apac.anthropic.claude-haiku-4-5-20251001-v1:0" in ids
    assert "qwen.qwen3-32b-v1:0" in ids
    assert "qwen.qwen3-next-80b-a3b-v1:0" in ids
    assert "qwen.qwen3-235b-a22b-2507-v1:0" in ids


def test_openai_direct_models_present() -> None:
    ids = {info.model_id for info in CHAT_MODEL_OPTIONS}
    for model_id in ("gpt-5-nano", "gpt-4.1-nano", "gpt-5-mini", "gpt-4.1", "o3"):
        assert model_id in ids


def test_default_model_is_pinned_to_bedrock_claude() -> None:
    # Pinned explicitly so reordering CHAT_MODEL_OPTIONS never shifts the default.
    assert DEFAULT_CHAT_MODEL == "anthropic.claude-3-5-sonnet-20240620-v1:0"
