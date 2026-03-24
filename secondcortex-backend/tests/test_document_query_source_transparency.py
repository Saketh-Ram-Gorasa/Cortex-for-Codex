from fastapi.testclient import TestClient


def test_query_response_includes_document_source(monkeypatch):
    import main as main_module

    main_module.app.dependency_overrides[main_module.get_current_user] = lambda: "u1"
    client = TestClient(main_module.app)

    class FakePlan:
        retrieved_context = [{"id": "doc-1", "activeFile": "Design Doc", "gitBranch": "external"}]

    async def fake_plan(*args, **kwargs):
        return FakePlan()

    async def fake_recall(*args, **kwargs):
        return []

    async def fake_exec(*args, **kwargs):
        return {"summary": "See external design guidance.", "sources": [{"type": "document", "id": "doc-1"}]}

    monkeypatch.setattr(main_module.planner, "plan", fake_plan)
    monkeypatch.setattr(main_module.vector_db, "recall_facts", fake_recall)
    monkeypatch.setattr(main_module.executor, "synthesize", fake_exec)

    resp = client.post("/api/v1/query", json={"question": "How should auth fallback work?"})
    assert resp.status_code == 200
    assert any(src.get("type") == "document" for src in resp.json().get("sources", []))

    main_module.app.dependency_overrides.clear()