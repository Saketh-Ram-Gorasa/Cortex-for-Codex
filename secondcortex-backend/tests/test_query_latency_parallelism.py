from time import perf_counter

import asyncio

from fastapi.testclient import TestClient


def test_query_parallelizes_planning_and_fact_recall(monkeypatch):
    import main as main_module

    main_module.app.dependency_overrides[main_module.get_current_user] = lambda: "u1"
    client = TestClient(main_module.app)

    call_times: dict[str, float] = {}

    class FakePlan:
        retrieved_context = []

    async def fake_plan(*args, **kwargs):
        call_times["plan_start"] = perf_counter()
        await asyncio.sleep(0.15)
        call_times["plan_end"] = perf_counter()
        return FakePlan()

    async def fake_recall(*args, **kwargs):
        call_times["recall_start"] = perf_counter()
        await asyncio.sleep(0.15)
        call_times["recall_end"] = perf_counter()
        return []

    async def fake_exec(*args, **kwargs):
        return {"summary": "Drafted actions.", "commands": []}

    def fake_save_chat_message(*args, **kwargs):
        return None

    monkeypatch.setattr(main_module.planner, "plan", fake_plan)
    monkeypatch.setattr(main_module.vector_db, "recall_facts", fake_recall)
    monkeypatch.setattr(main_module.executor, "synthesize", fake_exec)
    monkeypatch.setattr(main_module.user_db, "save_chat_message", fake_save_chat_message)

    try:
        resp = client.post("/api/v1/query", json={"question": "restore context"})
        assert resp.status_code == 200

        overlap = min(call_times["plan_end"], call_times["recall_end"]) - max(
            call_times["plan_start"], call_times["recall_start"]
        )
        assert overlap > 0.05, f"planner and fact recall did not overlap (overlap={overlap:.3f}s)"
    finally:
        main_module.app.dependency_overrides.clear()