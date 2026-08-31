from __future__ import annotations

from app_support.crawl.form_defaults import (
    DEFAULT_ACTIVITY_LOG_SIZE,
    DEFAULT_MAX_CONCURRENT,
    DEFAULT_OUTPUT_EXTENSION,
    DEFAULT_URLS,
    OUTPUT_EXTENSION_OPTIONS,
    default_form_values,
    form_state_from_submitted,
)
from app_support.support import build_configs


def test_default_form_values_include_required_build_config_keys() -> None:
    values = default_form_values()

    assert values["urls"] == DEFAULT_URLS
    assert values["output_extension"] == DEFAULT_OUTPUT_EXTENSION
    assert values["activity_log_size"] == DEFAULT_ACTIVITY_LOG_SIZE
    assert values["max_concurrent"] == DEFAULT_MAX_CONCURRENT
    assert set(OUTPUT_EXTENSION_OPTIONS) >= {DEFAULT_OUTPUT_EXTENSION, ".txt"}
    assert {
        "exclude_paths",
        "include_only_paths",
        "limit",
        "max_depth",
        "max_concurrent",
        "flush_interval",
        "delay",
        "max_retries",
        "exclude_tags",
        "include_only_tags",
        "wait_for",
        "timeout",
        "max_file_size_mb",
        "extract_main_content",
    }.issubset(values)


def test_default_form_values_returns_independent_dicts() -> None:
    first = default_form_values()
    second = default_form_values()

    first["urls"] = "https://changed.example"

    assert second["urls"] == DEFAULT_URLS


def test_default_form_values_build_valid_configs() -> None:
    crawler_config, page_config, activity_log_size = build_configs(default_form_values())

    assert crawler_config.urls == [DEFAULT_URLS]
    assert crawler_config.max_concurrent == DEFAULT_MAX_CONCURRENT
    assert page_config.output_extension == DEFAULT_OUTPUT_EXTENSION
    assert activity_log_size == DEFAULT_ACTIVITY_LOG_SIZE


def test_form_state_from_submitted_keeps_user_values_and_drops_control_flags() -> None:
    submitted = default_form_values() | {
        "submitted": True,
        "stop_submitted": False,
        "urls": "https://user.example",
        "limit": 42,
        "extract_main_content": False,
    }

    persisted = form_state_from_submitted(submitted)

    assert persisted.keys() == default_form_values().keys()
    assert "submitted" not in persisted
    assert "stop_submitted" not in persisted
    assert persisted["urls"] == "https://user.example"
    assert persisted["limit"] == 42
    assert persisted["extract_main_content"] is False


def test_form_state_from_submitted_fills_missing_fields_with_defaults() -> None:
    persisted = form_state_from_submitted({"urls": "https://only-urls.example"})

    assert persisted["urls"] == "https://only-urls.example"
    assert persisted["output_extension"] == DEFAULT_OUTPUT_EXTENSION
    assert persisted["activity_log_size"] == DEFAULT_ACTIVITY_LOG_SIZE
