from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from agents.retriever import RetrieverAgent
from models.schemas import MemoryMetadata, MemoryOperation, SnapshotPayload


class _FakeVectorDB:
    async def generate_embedding(self, text: str) -> list[float]:
        return [0.1, 0.2]

    async def upsert_snapshot(self, snapshot, user_id: str | None = None) -> None:
        return None

    async def upsert_fact(self, fact, user_id: str | None = None) -> None:
        return None


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str) -> None:
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str) -> None:
        self.choices = [_Choice(content)]


def test_manual_note_is_structured_by_llm(monkeypatch):
    retriever = RetrieverAgent(_FakeVectorDB())
    captured: dict[str, object] = {}

    async def fake_chat_completion(**kwargs):
        return _Response(
            json.dumps(
                {
                    "title": "Payment Retry Decision",
                    "tags": ["payments", "retry_logic"],
                    "body": "Retry failed payments with exponential backoff and alert on final failure.",
                    "summary": "Defines payment retry policy.",
                    "entities": ["PaymentService", "RetryPolicy"],
                }
            )
        )

    async def fake_route_operation(payload, previous=None):
        captured["shadow_graph"] = payload.shadow_graph
        captured["function_context"] = payload.function_context
        return MemoryMetadata(operation=MemoryOperation.NOOP, summary="noop")

    monkeypatch.setattr("agents.retriever.task_chat_completion", fake_chat_completion)
    monkeypatch.setattr(retriever, "_route_operation", fake_route_operation)

    payload = SnapshotPayload(
        timestamp=datetime.now(tz=timezone.utc),
        workspaceFolder="repo",
        activeFile="secondcortex://notes/manual-note.md",
        languageId="markdown",
        shadowGraph="Developer note:\nNeed robust payment retries under transient 5xx failures.",
        gitBranch=None,
        terminalCommands=[],
        functionContext={
            "source": "manual_note",
            "noteEntities": ["Payments", "Retry"],
            "noteLength": 62,
        },
    )

    asyncio.run(retriever.process_snapshot(payload, user_id="u1"))

    shadow_graph = str(captured["shadow_graph"])
    function_context = captured["function_context"]

    assert "Structured developer note:" in shadow_graph
    assert "Title: Payment Retry Decision" in shadow_graph
    assert "Tags: payments, retry_logic" in shadow_graph
    assert "Body:" in shadow_graph

    assert isinstance(function_context, dict)
    assert function_context.get("noteTitle") == "Payment Retry Decision"
    assert function_context.get("noteTags") == ["payments", "retry_logic"]
    assert function_context.get("noteStructuredBy") == "llm"
    assert "PaymentService" in function_context.get("noteEntities", [])


def test_manual_note_uses_fallback_when_llm_fails(monkeypatch):
    retriever = RetrieverAgent(_FakeVectorDB())
    captured: dict[str, object] = {}

    async def fake_chat_completion(**kwargs):
        raise RuntimeError("LLM unavailable")

    async def fake_route_operation(payload, previous=None):
        captured["shadow_graph"] = payload.shadow_graph
        captured["function_context"] = payload.function_context
        return MemoryMetadata(operation=MemoryOperation.NOOP, summary="noop")

    monkeypatch.setattr("agents.retriever.task_chat_completion", fake_chat_completion)
    monkeypatch.setattr(retriever, "_route_operation", fake_route_operation)

    payload = SnapshotPayload(
        timestamp=datetime.now(tz=timezone.utc),
        workspaceFolder="repo",
        activeFile="secondcortex://notes/manual-note.md",
        languageId="markdown",
        shadowGraph="Developer note:\nCapture rollback plan for checkout API and monitor spike in 500s.",
        gitBranch=None,
        terminalCommands=[],
        functionContext={
            "source": "manual_note",
            "noteEntities": ["CheckoutAPI", "RollBack"],
            "noteLength": 70,
        },
    )

    asyncio.run(retriever.process_snapshot(payload, user_id="u1"))

    function_context = captured["function_context"]
    assert isinstance(function_context, dict)
    assert function_context.get("noteStructuredBy") == "fallback"
    assert "checkoutapi" in function_context.get("noteTags", [])
    assert "rollback" in function_context.get("noteTags", [])


def test_non_manual_snapshot_skips_note_structuring(monkeypatch):
    retriever = RetrieverAgent(_FakeVectorDB())
    llm_calls = {"count": 0}

    async def fake_chat_completion(**kwargs):
        llm_calls["count"] += 1
        return _Response("{}")

    async def fake_route_operation(payload, previous=None):
        return MemoryMetadata(operation=MemoryOperation.NOOP, summary="noop")

    monkeypatch.setattr("agents.retriever.task_chat_completion", fake_chat_completion)
    monkeypatch.setattr(retriever, "_route_operation", fake_route_operation)

    payload = SnapshotPayload(
        timestamp=datetime.now(tz=timezone.utc),
        workspaceFolder="repo",
        activeFile="src/app.py",
        languageId="python",
        shadowGraph="Refactor app startup sequence.",
        gitBranch="main",
        terminalCommands=[],
        functionContext={"activeSymbol": "main"},
    )

    stored = asyncio.run(retriever.process_snapshot(payload, user_id="u1"))

    assert llm_calls["count"] == 0
    assert stored.shadow_graph == "Refactor app startup sequence."
