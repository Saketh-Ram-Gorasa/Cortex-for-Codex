from __future__ import annotations

from config import Settings


def test_legacy_env_aliases_are_still_accepted(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://legacy-resource.openai.azure.com/v1")
    monkeypatch.setenv("OPENAI_EMBEDDING", "legacy-embed-model")

    cfg = Settings(_env_file=None)

    assert cfg.llm_provider_default == "openai"
    assert cfg.openai_api_base_url == "https://legacy-resource.openai.azure.com/v1"
    assert cfg.openai_embedding_model == "legacy-embed-model"


def test_task_specific_provider_override_vars_parse(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_DEFAULT", "openai")
    monkeypatch.setenv("LLM_PROVIDER_PLANNER", "groq")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER_PLANNER", "github_models")
    monkeypatch.setenv("OPENAI_CHAT_MODEL", "planner-model")

    cfg = Settings(_env_file=None)

    assert cfg.llm_provider_default == "openai"
    assert cfg.llm_provider_planner == "groq"
    assert cfg.llm_fallback_provider_planner == "github_models"
    assert cfg.openai_chat_model == "planner-model"


def test_azure_openai_env_alias_is_preserved_for_compat(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER_DEFAULT", "azure_openai")

    cfg = Settings(_env_file=None)

    assert cfg.llm_provider_default == "azure_openai"
