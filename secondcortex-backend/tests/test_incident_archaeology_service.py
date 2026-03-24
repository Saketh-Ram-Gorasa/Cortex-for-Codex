from services.incident_archaeology import IncidentArchaeologyService


def test_confidence_penalized_when_contradictions_exist() -> None:
    service = IncidentArchaeologyService()
    score = service.compute_confidence(
        coverage=0.8,
        recency=0.9,
        contradiction_count=2,
        evidence_count=6,
    )
    assert score < 0.8
