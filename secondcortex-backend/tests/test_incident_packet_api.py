from fastapi.testclient import TestClient


def test_incident_packet_endpoint_shape(monkeypatch):
    import main as main_module

    main_module.app.dependency_overrides[main_module.get_current_user] = lambda: "u1"
    client = TestClient(main_module.app)

    async def fake_build(*args, **kwargs):
        return {
            "incidentId": "inc_123",
            "summary": "Likely auth cache race",
            "confidence": 0.71,
            "hypotheses": [],
            "recoveryOptions": [],
            "contradictions": [],
            "evidenceNodes": [],
            "disproofChecks": [],
        }

    monkeypatch.setattr(main_module, "_build_incident_packet", fake_build)
    res = client.post("/api/v1/incident/packet", json={"question": "Why auth failed?"})
    assert res.status_code == 200
    body = res.json()
    assert "incidentId" in body
    assert "hypotheses" in body
    assert "recoveryOptions" in body

    main_module.app.dependency_overrides.clear()
