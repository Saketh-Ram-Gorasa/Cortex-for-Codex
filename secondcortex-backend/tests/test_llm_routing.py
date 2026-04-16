from __future__ import annotations

import asyncio

import services.llm_client as llm_client


def _configure_common(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "llm_provider_default", "openai")
    monkeypatch.setattr(llm_client.settings, "openai_api_key", "fake-key")
    monkeypatch.setattr(llm_client.settings, "openai_api_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(llm_client.settings, "openai_chat_model", "chat-default")
    monkeypatch.setattr(llm_client.settings, "openai_embedding_model", "embed-default")
    monkeypatch.setattr(llm_client.settings, "groq_model", "llama-3.1-8b-instant")
    monkeypatch.setattr(llm_client.settings, "groq_api_key", "groq-key")
    monkeypatch.setattr(llm_client.settings, "github_token", "gh-token")
    monkeypatch.setattr(llm_client.settings, "github_models_endpoint", "https://models.inference.ai.azure.com")


def test_route_resolution_uses_task_override_and_fallback(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider_retriever", "groq")
    monkeypatch.setattr(llm_client.settings, "llm_fallback_provider_retriever", "openai")

    route = llm_client.resolve_route("retriever")

    assert route.provider == "groq"
    assert route.model == "llama-3.1-8b-instant"
    assert route.fallback_provider == "openai"
    assert route.fallback_model == "chat-default"


def test_validate_configuration_reports_missing_openai_key(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "openai_api_key", "")

    errors = llm_client.validate_llm_configuration()

    assert any("OPENAI_API_KEY is required for provider 'openai'" in e for e in errors)


def test_provider_fallback_is_used_when_primary_fails(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider_planner", "openai")
    monkeypatch.setattr(llm_client.settings, "llm_fallback_provider_planner", "groq")

    calls: list[str] = []

    async def fake_call_with_provider(*, provider, task, endpoint, model, payload, auth_variant="default"):
        calls.append(f"{provider}:{model}")
        if provider == "openai":
            raise RuntimeError("500 upstream error")
        return {"provider": provider, "model": model}

    monkeypatch.setattr(llm_client, "_call_with_provider", fake_call_with_provider)

    async def run():
        route = llm_client.resolve_route("planner")
        return await llm_client._call_with_fallbacks(
            route=route,
            endpoint="chat.completions",
            payload={"messages": [{"role": "user", "content": "plan"}], "temperature": 0.2, "max_tokens": 20},
        )

    result = asyncio.run(run())
    assert result["provider"] == "groq"
    assert calls[0].startswith("openai")
    assert calls[1].startswith("groq")


def test_openai_primary_routes_and_defaults(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider_planner", "openai")
    monkeypatch.setattr(llm_client.settings, "openai_api_key", "")

    monkeypatch.setattr(llm_client.settings, "llm_fallback_provider_planner", "")

    async def fake_call_with_provider(*, provider, task, endpoint, model, payload, auth_variant="default"):
        return {"provider": provider, "model": model}

    monkeypatch.setattr(llm_client, "_call_with_provider", fake_call_with_provider)

    async def run():
        route = llm_client.resolve_route("planner")
        return await llm_client._call_with_fallbacks(
            route=route,
            endpoint="chat.completions",
            payload={"messages": [{"role": "user", "content": "plan"}], "temperature": 0.2, "max_tokens": 20},
        )

    result = asyncio.run(run())
    assert result["provider"] == "openai"
    assert result["model"] == "chat-default"


def test_azure_openai_alias_normalizes_to_openai(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider_default", "azure_openai")
    monkeypatch.setattr(llm_client.settings, "llm_fallback_provider_planner", "azure_openai")

    route = llm_client.resolve_route("planner")

    assert route.provider == "openai"
    assert route.fallback_provider == "openai"
    assert route.model == "chat-default"
