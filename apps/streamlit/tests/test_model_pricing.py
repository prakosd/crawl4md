"""Tests for the model pricing/metadata catalog (app_support.model_pricing)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app_support import model_pricing
from app_support.model_pricing import (
    ModelPricingCatalog,
    estimate_cost,
    get_model_price,
    load_pricing_catalog,
    pricing_captured,
    pricing_sources,
    read_pricing_catalog,
    render_pricing_markdown,
)

_VALID_YAML = """
pricing_captured: "2026-08-19"
region: ap-southeast-2
sources:
  - name: Test Source
    url: https://example.test/pricing
models:
  - model_id: test.model-a
    display_name: Model A
    provider: TestCo
    cloud_service: Amazon Bedrock
    size_band: Small
    price_in_per_1m: 1.0
    price_out_per_1m: 2.0
  - model_id: test.model-b
    display_name: Model B
    provider: TestCo
    cloud_service: OpenAI API
    size_band: Medium
"""


def _catalog_from(text: str, tmp_path: Path) -> ModelPricingCatalog:
    path = tmp_path / "model_pricing.yaml"
    path.write_text(text, encoding="utf-8")
    return read_pricing_catalog(path)


def _use_catalog(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str) -> None:
    catalog = _catalog_from(text, tmp_path)
    monkeypatch.setattr(model_pricing, "load_pricing_catalog", lambda: catalog)


def test_read_valid_catalog(tmp_path: Path) -> None:
    catalog = _catalog_from(_VALID_YAML, tmp_path)

    assert catalog.pricing_captured == "2026-08-19"
    assert [source.name for source in catalog.sources] == ["Test Source"]
    assert {model.model_id for model in catalog.models} == {"test.model-a", "test.model-b"}


def test_read_missing_file_returns_empty(tmp_path: Path) -> None:
    catalog = read_pricing_catalog(tmp_path / "nope.yaml")

    assert catalog.models == []
    assert catalog.pricing_captured == ""


def test_read_invalid_yaml_returns_empty(tmp_path: Path) -> None:
    assert _catalog_from("models: [unterminated", tmp_path).models == []


def test_read_invalid_schema_returns_empty(tmp_path: Path) -> None:
    # A model entry missing every required field but model_id.
    assert _catalog_from("models:\n  - model_id: x\n", tmp_path).models == []


def test_get_model_price_found_and_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_catalog(monkeypatch, tmp_path, _VALID_YAML)

    price = get_model_price("test.model-a")
    assert price is not None
    assert price.display_name == "Model A"
    assert get_model_price("unknown.model") is None


def test_estimate_cost_math(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_catalog(monkeypatch, tmp_path, _VALID_YAML)

    # 1,000,000 in x $1 + 500,000 out x $2 = 1.0 + 1.0
    assert estimate_cost("test.model-a", 1_000_000, 500_000) == pytest.approx(2.0)


def test_estimate_cost_none_without_price(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_catalog(monkeypatch, tmp_path, _VALID_YAML)

    assert estimate_cost("test.model-b", 1000, 1000) is None  # Model B has no price
    assert estimate_cost("unknown", 1000, 1000) is None


def test_pricing_captured_and_sources(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _use_catalog(monkeypatch, tmp_path, _VALID_YAML)

    assert pricing_captured() == "2026-08-19"
    sources = pricing_sources()
    assert [(source.name, source.url) for source in sources] == [
        ("Test Source", "https://example.test/pricing")
    ]


def test_bundled_catalog_loads() -> None:
    catalog = load_pricing_catalog()

    assert catalog.pricing_captured
    assert catalog.sources
    assert len(catalog.models) >= 15
    for model in catalog.models:
        if model.price_in_per_1m is not None:
            assert model.price_out_per_1m is not None


def test_every_priced_model_is_callable() -> None:
    from rag_engine.catalog import CHAT_MODEL_OPTIONS

    callable_ids = {info.model_id for info in CHAT_MODEL_OPTIONS}
    for model in load_pricing_catalog().models:
        assert model.model_id in callable_ids, f"{model.model_id} missing from rag_engine catalog"


def test_openai_direct_models_are_priced() -> None:
    prices = {model.model_id: model for model in load_pricing_catalog().models}
    # A few of the OpenAI Direct API additions carry their published prices.
    assert prices["gpt-5-nano"].price_in_per_1m == pytest.approx(0.05)
    assert prices["gpt-4o-mini"].price_out_per_1m == pytest.approx(0.60)
    assert prices["gpt-4o-mini"].cloud_service == "OpenAI API"
    # GPT-4o is reclassified Large per the pricing source (blended ~$4.4).
    assert prices["gpt-4o"].size_band == "Large"


def test_models_sorted_by_cloud_then_provider_size_name() -> None:
    band_rank = {"XS": 0, "Small": 1, "Medium": 2, "Large": 3, "XL": 4, "Frontier": 5}
    cloud_rank = {"Amazon Bedrock": 0, "OpenAI API": 1}
    keys = [
        (
            cloud_rank[model.cloud_service],
            model.provider,
            band_rank[model.size_band],
            model.display_name,
        )
        for model in load_pricing_catalog().models
    ]
    assert keys == sorted(keys)


def test_render_pricing_markdown_table(tmp_path: Path) -> None:
    catalog = _catalog_from(_VALID_YAML, tmp_path)

    md = render_pricing_markdown(catalog)

    assert "| Provider | Model | Cloud service | Size | Input $/1M | Output $/1M |" in md
    assert "region `ap-southeast-2`" in md
    assert "captured 2026-08-19" in md
    assert "| TestCo | Model A | Amazon Bedrock | Small | $1.000 | $2.000 |" in md
    assert "| TestCo | Model B | OpenAI API | Medium | — | — |" in md  # unpriced -> em dash
    assert "[Test Source](https://example.test/pricing)" in md


def test_render_pricing_markdown_uses_bundled_catalog_by_default() -> None:
    md = render_pricing_markdown()

    assert "GPT-4o mini" in md
    assert "Amazon Bedrock" in md
