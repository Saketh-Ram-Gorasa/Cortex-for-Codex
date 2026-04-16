from __future__ import annotations

import asyncio

import services.llm_client as llm_client


def test_task_chat_completion_passes_payload(monkeypatch):
    captured = {}

    def fake_resolve_route(task: str):
        return llm_client.RouteSelection(
            task=task,
            provider="openai",
            fallback_provider=None,
            model="chat-model",
            fallback_model=None,
            auth_mode=None,
        )

    async def fake_call_with_fallbacks(*, route, endpoint, payload):
        captured["route"] = route
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(llm_client, "resolve_route", fake_resolve_route)
    monkeypatch.setattr(llm_client, "_call_with_fallbacks", fake_call_with_fallbacks)

    async def run():
        return await llm_client.task_chat_completion(
            task="planner",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.33,
            max_tokens=222,
        )

    result = asyncio.run(run())
    assert result["ok"] is True
    assert captured["endpoint"] == "chat.completions"
    assert captured["route"].task == "planner"
    assert captured["payload"]["messages"][0]["content"] == "hello"
    assert captured["payload"]["temperature"] == 0.33
    assert captured["payload"]["max_tokens"] == 222


def test_task_embedding_create_passes_payload(monkeypatch):
    captured = {}

    def fake_resolve_route(task: str):
        return llm_client.RouteSelection(
            task=task,
            provider="openai",
            fallback_provider=None,
            model="embed-model",
            fallback_model=None,
            auth_mode=None,
        )

    async def fake_call_with_fallbacks(*, route, endpoint, payload):
        captured["route"] = route
        captured["endpoint"] = endpoint
        captured["payload"] = payload
        return {"ok": True}

    monkeypatch.setattr(llm_client, "resolve_route", fake_resolve_route)
    monkeypatch.setattr(llm_client, "_call_with_fallbacks", fake_call_with_fallbacks)

    async def run():
        return await llm_client.task_embedding_create(task="embeddings", input="abc")

    result = asyncio.run(run())
    assert result["ok"] is True
    assert captured["endpoint"] == "embeddings"
    assert captured["route"].task == "embeddings"
    assert captured["payload"]["input"] == "abc"
