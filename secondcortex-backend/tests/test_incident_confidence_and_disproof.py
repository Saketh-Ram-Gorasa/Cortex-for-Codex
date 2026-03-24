from services.incident_archaeology import IncidentArchaeologyService


def test_disproof_checks_generated_for_each_hypothesis() -> None:
    service = IncidentArchaeologyService()
    checks = service.build_disproof_checks([
        {"id": "h1", "cause": "cache race"},
        {"id": "h2", "cause": "stale config"},
    ])
    assert len(checks) == 2
    assert all("disprove" in c.lower() or "falsify" in c.lower() for c in checks)
