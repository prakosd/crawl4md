"""Chat-model selector helpers for the RAG pages (Steps 4-5).

Mirrors ``vector_form_ui``'s embedding selector: the pure option/label helpers
(``chat_model_choices``, ``chat_model_label``) are unit-testable without Streamlit
and drive the model pickers on the Basic and Conversational RAG pages.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence

from rag_engine import CHAT_MODEL_OPTIONS, ECHO_MODEL, ChatModelInfo, get_chat_model_info

from app_support.i18n import Strings
from app_support.model_pricing import ModelPrice, get_model_price, load_pricing_catalog
from app_support.settings import get_settings

__all__ = [
    "chat_model_choices",
    "chat_model_info_for",
    "chat_model_label",
    "chat_model_options",
    "resolve_chat_model_choices",
    "resolve_offered_from_pricing",
]

_settings = get_settings()
_RAG_LLM_MODEL_ORDER = tuple(
    model.strip() for model in _settings.rag_llm_models.split(",") if model.strip()
)
_RAG_DEFAULT_LLM_MODEL = _settings.rag_default_llm_model
_CATALOG_MODEL_IDS = tuple(info.model_id for info in CHAT_MODEL_OPTIONS)
# The offline echo model is the silent fallback in rag_engine.resolve_chat_model;
# it is never offered in the picker (it produces no real answer).
_OFFERED_MODEL_IDS = tuple(mid for mid in _CATALOG_MODEL_IDS if mid != ECHO_MODEL)
# Size bands (from the pricing config) offered in the picker; the rest are hidden.
_RAG_LLM_SIZE_BANDS = frozenset(
    band.strip() for band in _settings.rag_llm_size_bands.split(",") if band.strip()
)

# Maps a model's size to its localized picker label key (shown after the label).
_SIZE_STRING_KEYS = {
    "small": "RAG_LLM_SIZE_SMALL",
    "medium": "RAG_LLM_SIZE_MEDIUM",
    "large": "RAG_LLM_SIZE_LARGE",
}

# Open fallback used only if a selected model is ever absent from the catalog;
# the catalog covers every id in ``chat_model_options()``.
_UNKNOWN_MODEL_INFO = ChatModelInfo(
    model_id="",
    provider="",
    label="",
    size="medium",
    kind="cloud",
    requires_api_key=True,
)


def resolve_chat_model_choices(
    configured: Sequence[str], allowed: Sequence[str], default: str
) -> tuple[list[str], int]:
    """Return the ordered chat-model options and the default-selected index.

    Only models the library catalogs (*allowed*) are offered, ordered by the
    operator's *configured* list so ``.env`` fully controls which models appear
    (a catalogued model left out of *configured* is hidden — unlike the embedding
    picker, the chat list is meant to be curated). If *configured* names nothing
    valid, every allowed model is shown so the picker is never empty. The index
    points at *default* when it is among the options, otherwise the first option.
    """
    allowed_set = set(allowed)
    ordered = [model for model in dict.fromkeys(configured) if model in allowed_set]
    if not ordered:
        ordered = list(allowed)
    default_index = ordered.index(default) if default in ordered else 0
    return ordered, default_index


def resolve_offered_from_pricing(
    priced_models: Sequence[ModelPrice],
    size_bands: Collection[str],
    callable_ids: Collection[str],
) -> list[str]:
    """Return callable priced models whose size band is allowed, in catalog order."""
    allowed = set(size_bands)
    known = set(callable_ids)
    return [
        model.model_id
        for model in priced_models
        if model.size_band in allowed and model.model_id in known
    ]


def chat_model_choices() -> tuple[list[str], int]:
    """Return the offered chat-model ids and the default-selected index.

    Driven by the pricing config filtered to the allowed size bands; falls back to
    the ``.env``-curated catalog list when that config is missing or matches
    nothing. Echo is never offered — it is the automatic offline fallback.
    """
    offered = resolve_offered_from_pricing(
        load_pricing_catalog().models, _RAG_LLM_SIZE_BANDS, _OFFERED_MODEL_IDS
    )
    if not offered:
        return resolve_chat_model_choices(
            _RAG_LLM_MODEL_ORDER, _OFFERED_MODEL_IDS, _RAG_DEFAULT_LLM_MODEL
        )
    default_index = (
        offered.index(_RAG_DEFAULT_LLM_MODEL) if _RAG_DEFAULT_LLM_MODEL in offered else 0
    )
    return offered, default_index


def chat_model_options() -> list[str]:
    """Return the chat-model ids offered in the selector (config-driven)."""
    return chat_model_choices()[0]


def chat_model_info_for(model_id: str) -> ChatModelInfo:
    """Return catalog metadata for *model_id*, or an open fallback."""
    return get_chat_model_info(model_id) or _UNKNOWN_MODEL_INFO


def chat_model_label(model_id: str, strings: Strings) -> str:
    """Return the picker label: the pricing display metadata, or a catalog fallback.

    Priced models read ``provider · name · cloud service · size band`` from the
    pricing config; anything without a price (e.g. echo) falls back to the catalog
    label with its size and offline/cloud tag.
    """
    price = get_model_price(model_id)
    if price is not None:
        return (
            f"{price.provider} · {price.display_name} · {price.cloud_service} · {price.size_band}"
        )
    info = get_chat_model_info(model_id)
    if info is None:
        return model_id
    tag_key = "RAG_LLM_TAG_OFFLINE" if info.kind == "local" else "RAG_LLM_TAG_CLOUD"
    return f"{info.label} · {strings[_SIZE_STRING_KEYS[info.size]]} · {strings[tag_key]}"
