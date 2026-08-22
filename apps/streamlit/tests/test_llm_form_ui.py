from __future__ import annotations

from rag_engine import CHAT_MODEL_OPTIONS, ECHO_MODEL

from app_support.i18n import STRINGS_EN
from app_support.model_pricing import ModelPrice, get_model_price
from app_support.rag_shared.llm_form_ui import (
    chat_model_info_for,
    chat_model_label,
    chat_model_options,
    resolve_chat_model_choices,
    resolve_offered_from_pricing,
)
from app_support.settings import get_settings


def test_options_are_config_driven_and_catalogued() -> None:
    options = chat_model_options()
    catalog_ids = {info.model_id for info in CHAT_MODEL_OPTIONS}

    assert set(options) <= catalog_ids  # only catalogued (callable) models are offered
    assert get_settings().rag_default_llm_model in options
    assert ECHO_MODEL not in options  # echo is the silent fallback, never offered
    # The picker is driven by the pricing config: every offered model is priced.
    assert all(get_model_price(model_id) is not None for model_id in options)


def test_resolve_chat_model_choices_curates_and_orders() -> None:
    options, index = resolve_chat_model_choices(["b", "x", "a"], ["a", "b", "c"], "a")

    assert options == ["b", "a"]  # "x" dropped (uncatalogued); order follows configured
    assert options[index] == "a"


def test_resolve_chat_model_choices_falls_back_to_all_when_none_valid() -> None:
    options, index = resolve_chat_model_choices(["x"], ["a", "b"], "b")

    assert options == ["a", "b"]
    assert options[index] == "b"


def test_label_offline_falls_back_and_priced_uses_config() -> None:
    echo_label = chat_model_label(ECHO_MODEL, STRINGS_EN)
    assert STRINGS_EN["RAG_LLM_TAG_OFFLINE"] in echo_label  # no price -> catalog tag fallback

    priced_label = chat_model_label("gpt-4o-mini", STRINGS_EN)
    # Order: provider · model name · cloud service · size band.
    assert priced_label == "OpenAI · GPT-4o mini · OpenAI API · Small"


def test_label_unknown_model_returns_id() -> None:
    assert chat_model_label("unknown/model", STRINGS_EN) == "unknown/model"


def test_resolve_offered_filters_by_band_and_callable() -> None:
    priced = [
        ModelPrice(model_id="a", display_name="A", provider="P", cloud_service="C", size_band="XS"),
        ModelPrice(
            model_id="b", display_name="B", provider="P", cloud_service="C", size_band="Large"
        ),
        ModelPrice(
            model_id="c", display_name="C", provider="P", cloud_service="C", size_band="Small"
        ),
    ]

    offered = resolve_offered_from_pricing(priced, {"XS", "Small"}, {"a", "c"})

    assert offered == ["a", "c"]  # "b" hidden (band); unlisted ids hidden; order preserved


def test_medium_and_large_models_hidden_under_xs_small() -> None:
    from app_support.model_pricing import load_pricing_catalog

    callable_ids = {info.model_id for info in CHAT_MODEL_OPTIONS}
    offered = resolve_offered_from_pricing(
        load_pricing_catalog().models, {"XS", "Small"}, callable_ids
    )

    assert "gpt-5-nano" in offered and "gpt-4o-mini" in offered  # Small still shows
    assert "gpt-5-mini" not in offered  # Medium hidden
    assert "gpt-4o" not in offered and "o3" not in offered  # Large hidden


def test_info_for_unknown_returns_open_fallback() -> None:
    info = chat_model_info_for("unknown/model")

    assert info.model_id == ""
    assert info.kind == "cloud"


def test_info_for_echo_is_local() -> None:
    info = chat_model_info_for(ECHO_MODEL)

    assert info.kind == "local"
    assert not info.requires_api_key
