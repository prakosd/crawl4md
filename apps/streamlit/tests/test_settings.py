from __future__ import annotations

import pytest
from pydantic import ValidationError

from app_support.settings import Settings, get_settings


def test_settings_load_values_from_env_defaults() -> None:
    # .env.defaults is the single source of truth: Settings() reads every value
    # from it, since the model declares no in-code fallbacks.
    settings = Settings()

    assert settings.rag_top_k == 4
    assert settings.basic_rag_qa_top_results == 5
    assert settings.basic_rag_qa_default_tone == "Neutral"
    assert (
        settings.basic_rag_qa_prompt_template_file
        == "apps/streamlit/config/basic_rag_qa_prompt.txt"
    )
    assert settings.basic_rag_qa_session_token_quota == 5700000
    assert settings.basic_rag_qa_session_cost_quota == 1.0
    assert "Neutral" in settings.basic_rag_qa_tones.split(",")
    assert "echo" not in settings.rag_llm_models.split(",")
    assert "qwen.qwen3-32b-v1:0" in settings.rag_llm_models.split(",")
    assert settings.rag_default_llm_model == "apac.amazon.nova-lite-v1:0"
    assert settings.semantic_search_top_n == 5
    assert settings.semantic_search_default_tab == "raw"
    assert settings.vector_chunk_size == 600
    assert settings.vector_embedding_dimension == 512
    assert settings.vector_default_embedding_model == "all-MiniLM-L6-v2"
    assert "all-MiniLM-L6-v2" in settings.vector_embedding_models
    assert settings.crawl_timeout == 60.0
    assert settings.crawl_max_file_size_mb == 10.0
    assert settings.ui_download_limit_mb == 500
    assert settings.session_retention_days == 7
    assert settings.log_level == "INFO"
    assert settings.log_file == "logs/app.log"
    assert settings.crawl_default_urls == "https://www.ato.gov.au/"
    assert settings.crawl_include_only_paths == "ato.gov.au"
    assert settings.crawl_exclude_paths == "ato.gov.au/api/"
    assert settings.crawl_exclude_tags == "nav, script, form, style"
    assert settings.crawl_default_output_extension == ".md"
    assert settings.crawl_proxy_on_initial is False


def test_settings_read_overrides_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_TOP_K", "9")
    monkeypatch.setenv("VECTOR_CHUNK_SIZE", "900")
    monkeypatch.setenv("UI_PREVIEW_LIMIT_KB", "512")
    monkeypatch.setenv("SESSION_RETENTION_DAYS", "30")
    monkeypatch.setenv("SEMANTIC_SEARCH_DEFAULT_TAB", "preview")

    # The process environment takes precedence over the .env.defaults file.
    settings = Settings()

    assert settings.rag_top_k == 9
    assert settings.vector_chunk_size == 900
    assert settings.ui_preview_limit_kb == 512
    assert settings.session_retention_days == 30
    assert settings.semantic_search_default_tab == "preview"


def test_settings_ignore_unrelated_secret_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    # Secret credentials live alongside config in ".env"; the settings model must
    # ignore them rather than fail on unknown keys.
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "should-be-ignored")

    settings = Settings()

    assert not hasattr(settings, "aws_secret_access_key")


def test_settings_require_env_defaults_present(monkeypatch: pytest.MonkeyPatch) -> None:
    # With no env file and the relevant variables unset, the required fields are
    # missing — .env.defaults is mandatory because the model carries no in-code
    # fallbacks, so construction fails fast.
    for key in ("RAG_TOP_K", "VECTOR_CHUNK_SIZE", "CRAWL_LIMIT", "UI_DOWNLOAD_LIMIT_MB"):
        monkeypatch.delenv(key, raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_get_settings_is_cached_singleton() -> None:
    assert get_settings() is get_settings()
