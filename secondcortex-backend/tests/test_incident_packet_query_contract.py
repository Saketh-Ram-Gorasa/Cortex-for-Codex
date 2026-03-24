from fastapi.testclient import TestClient


def test_incident_packet_contains_contradictions_and_disproof_checks(monkeypatch):
    import main as main_module

    main_module.app.dependency_overrides[main_module.get_current_user] = lambda: "u1"
    client = TestClient(main_module.app)

    async def fake_build(*args, **kwargs):
        return {
            "incidentId": "inc_1",
            "summary": "test",
            "confidence": 0.6,
            "hypotheses": [],
            "recoveryOptions": [],
            "contradictions": ["A says X, B says Y"],
            "evidenceNodes": [],
            "disproofChecks": ["Check if issue persists after cache bypass"],
        }

    monkeypatch.setattr(main_module, "_build_incident_packet", fake_build)
    res = client.post("/api/v1/incident/packet", json={"question": "why failed"})
    assert res.status_code == 200
    body = res.json()
    assert "contradictions" in body
    assert "disproofChecks" in body

    main_module.app.dependency_overrides.clear()
