from fastapi.testclient import TestClient


def test_query_response_includes_interaction_and_filters_critical_commands(monkeypatch):
    import main as main_module

    main_module.app.dependency_overrides[main_module.get_current_user] = lambda: "u1"
    client = TestClient(main_module.app)

    class FakePlan:
        retrieved_context = []

    async def fake_plan(*args, **kwargs):
        return FakePlan()

    async def fake_recall(*args, **kwargs):
        return []

    async def fake_exec(*args, **kwargs):
        return {
            "summary": "Drafted actions.",
            "commands": [
                {"type": "run_command", "command": "rm -rf /tmp/bad"},
                {"type": "open_file", "filePath": "README.md"},
            ],
        }

    monkeypatch.setattr(main_module.planner, "plan", fake_plan)
    monkeypatch.setattr(main_module.vector_db, "recall_facts", fake_recall)
    monkeypatch.setattr(main_module.executor, "synthesize", fake_exec)

    main_module.settings.human_interaction_mode = "prompt"
    main_module.settings.human_interaction_deny_patterns = "rm -rf,git reset --hard"
    main_module.settings.human_interaction_max_actions = 8

    resp = client.post("/api/v1/query", json={"question": "restore context"})
    assert resp.status_code == 200

    payload = resp.json()
    assert payload.get("interaction") is not None
    assert payload["interaction"]["mode"] == "prompt"
    assert len(payload.get("commands", [])) == 1
    assert payload["commands"][0]["type"] == "open_file"

    main_module.app.dependency_overrides.clear()
