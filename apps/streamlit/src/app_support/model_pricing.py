"""Language-model pricing & display metadata for the RAG model picker.

Loads ``apps/streamlit/config/model_pricing.yaml`` — display/cost metadata joined
to :mod:`rag_engine`'s callable catalog by ``model_id``. Pure Python, no Streamlit,
so it stays unit-testable. Prices are USD per 1,000,000 tokens; a model with no
published price yields ``None`` from :func:`estimate_cost`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from log4py import get_logger
from pydantic import BaseModel, Field, ValidationError

__all__ = [
    "ModelPrice",
    "ModelPricingCatalog",
    "PricingSource",
    "estimate_cost",
    "get_model_price",
    "load_pricing_catalog",
    "pricing_captured",
    "pricing_sources",
    "read_pricing_catalog",
    "render_pricing_markdown",
]

_logger = get_logger(__name__)
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "model_pricing.yaml"
_TOKENS_PER_MILLION = 1_000_000


class PricingSource(BaseModel):
    """A named source the pricing figures were taken from."""

    name: str
    url: str


class ModelPrice(BaseModel):
    """Display + cost metadata for one chat model, keyed by its callable ``model_id``."""

    model_id: str
    display_name: str
    provider: str
    cloud_service: str
    size_band: str
    price_in_per_1m: float | None = None
    price_out_per_1m: float | None = None


class ModelPricingCatalog(BaseModel):
    """The pricing catalog: capture date, region, sources, and per-model metadata."""

    pricing_captured: str = ""
    region: str = ""
    sources: list[PricingSource] = Field(default_factory=list)
    models: list[ModelPrice] = Field(default_factory=list)


def read_pricing_catalog(path: Path) -> ModelPricingCatalog:
    """Read and validate a pricing catalog from *path*; empty catalog on any failure."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        _logger.warning("Model pricing config not found at %s: %s", path, exc)
        return ModelPricingCatalog()
    except yaml.YAMLError as exc:
        _logger.warning("Model pricing config is not valid YAML: %s", exc)
        return ModelPricingCatalog()
    try:
        return ModelPricingCatalog.model_validate(raw or {})
    except (ValidationError, ValueError) as exc:
        _logger.warning("Model pricing config failed validation: %s", exc)
        return ModelPricingCatalog()


@lru_cache(maxsize=1)
def load_pricing_catalog() -> ModelPricingCatalog:
    """Return the bundled pricing catalog, loaded and cached once."""
    return read_pricing_catalog(_CONFIG_PATH)


def get_model_price(model_id: str) -> ModelPrice | None:
    """Return the pricing/display metadata for *model_id*, or None when uncatalogued."""
    target = model_id.strip()
    for model in load_pricing_catalog().models:
        if model.model_id == target:
            return model
    return None


def estimate_cost(
    model_id: str, input_tokens: int | None, output_tokens: int | None
) -> float | None:
    """Return the USD cost estimate for a request, or None when the price is unknown."""
    price = get_model_price(model_id)
    if price is None or price.price_in_per_1m is None or price.price_out_per_1m is None:
        return None
    in_cost = (input_tokens or 0) / _TOKENS_PER_MILLION * price.price_in_per_1m
    out_cost = (output_tokens or 0) / _TOKENS_PER_MILLION * price.price_out_per_1m
    return in_cost + out_cost


def pricing_captured() -> str:
    """Return the date (from the config) the prices were captured."""
    return load_pricing_catalog().pricing_captured


def pricing_sources() -> list[PricingSource]:
    """Return the sources the prices were taken from."""
    return list(load_pricing_catalog().sources)


def _price_cell(value: float | None) -> str:
    """Render a per-1M price for the Markdown table, or an em dash when unpriced."""
    return "—" if value is None else f"${value:,.3f}"


def render_pricing_markdown(catalog: ModelPricingCatalog | None = None) -> str:
    """Render the pricing catalog as a human-readable Markdown table (read-only).

    Columns: Provider, Model, Cloud service, Size, Input $/1M, Output $/1M — one
    row per model, in catalog order. A leading line notes the region and capture
    date and a trailing line lists the sources, so the preview is self-describing.
    Unpriced models show an em dash. Defaults to the bundled catalog.
    """
    catalog = catalog or load_pricing_catalog()
    meta: list[str] = ["USD per 1M tokens"]
    if catalog.region:
        meta.append(f"region `{catalog.region}`")
    if catalog.pricing_captured:
        meta.append(f"captured {catalog.pricing_captured}")
    lines = [" · ".join(meta), ""]
    lines.append("| Provider | Model | Cloud service | Size | Input $/1M | Output $/1M |")
    lines.append("| --- | --- | --- | --- | ---: | ---: |")
    for model in catalog.models:
        lines.append(
            f"| {model.provider} | {model.display_name} | {model.cloud_service} "
            f"| {model.size_band} | {_price_cell(model.price_in_per_1m)} "
            f"| {_price_cell(model.price_out_per_1m)} |"
        )
    if catalog.sources:
        links = ", ".join(f"[{source.name}]({source.url})" for source in catalog.sources)
        lines += ["", f"Sources: {links}"]
    return "\n".join(lines)
