from __future__ import annotations

import asyncio

import services.llm_client as llm_client


def _configure_common(monkeypatch):
    monkeypatch.setattr(llm_client.settings, "llm_provider_default", "azure_openai")
    monkeypatch.setattr(llm_client.settings, "azure_openai_base_url", "https://unit-test.openai.azure.com/openai/v1/")
    monkeypatch.setattr(llm_client.settings, "azure_openai_auth_mode", "managed_identity_then_key")
    monkeypatch.setattr(llm_client.settings, "azure_openai_api_key", "fake-key")
    monkeypatch.setattr(llm_client.settings, "azure_openai_deployment", "chat-default")
    monkeypatch.setattr(llm_client.settings, "azure_openai_deployment_retriever", "retriever-deploy")
    monkeypatch.setattr(llm_client.settings, "azure_openai_deployment_embeddings", "embed-deploy")
    monkeypatch.setattr(llm_client.settings, "groq_model", "llama-3.1-8b-instant")
    monkeypatch.setattr(llm_client.settings, "groq_api_key", "groq-key")
    monkeypatch.setattr(llm_client.settings, "github_token", "gh-token")
    monkeypatch.setattr(llm_client.settings, "github_models_endpoint", "https://models.inference.ai.azure.com")


def test_route_resolution_uses_task_override_and_fallback(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider_retriever", "groq")
    monkeypatch.setattr(llm_client.settings, "llm_fallback_provider_retriever", "azure_openai")

    route = llm_client.resolve_route("retriever")

    assert route.provider == "groq"
    assert route.model == "llama-3.1-8b-instant"
    assert route.fallback_provider == "azure_openai"
    assert route.fallback_model == "retriever-deploy"


def test_validate_configuration_reports_missing_key_for_key_mode(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "azure_openai_auth_mode", "key")
    monkeypatch.setattr(llm_client.settings, "azure_openai_api_key", "")

    errors = llm_client.validate_llm_configuration()

    assert any("AZURE_OPENAI_API_KEY is required for auth mode 'key'" in e for e in errors)


def test_managed_identity_falls_back_to_azure_key_on_auth_error(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider_executor", "azure_openai")
    monkeypatch.setattr(llm_client.settings, "llm_fallback_provider_executor", "")
    monkeypatch.setattr(llm_client.settings, "azure_openai_deployment_executor", "executor-deploy")

    calls: list[str] = []

    async def fake_call_with_provider(*, provider, task, endpoint, model, payload, auth_variant="default"):
        calls.append(f"{provider}:{auth_variant}:{endpoint}:{model}")
        if auth_variant == "default":
            raise RuntimeError("401 unauthorized managed identity failure")
        return {"ok": True, "auth_variant": auth_variant, "task": task}

    monkeypatch.setattr(llm_client, "_call_with_provider", fake_call_with_provider)

    async def run():
        route = llm_client.resolve_route("executor")
        return await llm_client._call_with_fallbacks(
            route=route,
            endpoint="chat.completions",
            payload={"messages": [{"role": "user", "content": "hi"}], "temperature": 0.1, "max_tokens": 10},
        )

    result = asyncio.run(run())
    assert result["ok"] is True
    assert calls[0].startswith("azure_openai:default")
    assert calls[1].startswith("azure_openai:key")


def test_provider_fallback_is_used_when_primary_fails(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider_planner", "azure_openai")
    monkeypatch.setattr(llm_client.settings, "llm_fallback_provider_planner", "groq")
    monkeypatch.setattr(llm_client.settings, "azure_openai_deployment_planner", "planner-deploy")

    calls: list[str] = []

    async def fake_call_with_provider(*, provider, task, endpoint, model, payload, auth_variant="default"):
        calls.append(f"{provider}:{model}")
        if provider == "azure_openai":
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
    assert calls[0].startswith("azure_openai")
    assert calls[1].startswith("groq")


def test_azure_404_retries_with_default_deployment(monkeypatch):
    _configure_common(monkeypatch)
    monkeypatch.setattr(llm_client.settings, "llm_provider_planner", "azure_openai")
    monkeypatch.setattr(llm_client.settings, "llm_fallback_provider_planner", "")
    monkeypatch.setattr(llm_client.settings, "azure_openai_deployment_planner", "missing-planner-deploy")
    monkeypatch.setattr(llm_client.settings, "azure_openai_deployment", "chat-default")

    calls: list[str] = []

    async def fake_call_with_provider(*, provider, task, endpoint, model, payload, auth_variant="default"):
        calls.append(model)
        if model == "missing-planner-deploy":
            raise RuntimeError("Error code: 404 - {'error': {'code': '404', 'message': 'Resource not found'}}")
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
    assert result["provider"] == "azure_openai"
    assert result["model"] == "chat-default"
    assert calls[0] == "missing-planner-deploy"
    assert calls[1] == "chat-default"
