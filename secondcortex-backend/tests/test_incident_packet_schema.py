from models.schemas import IncidentPacketResponse


def test_incident_packet_schema_aliases() -> None:
    payload = IncidentPacketResponse(
        incident_id="inc_1",
        summary="Auth failure after deploy",
        confidence=0.74,
        hypotheses=[],
        recovery_options=[],
        contradictions=[],
        evidence_nodes=[],
        disproof_checks=[],
    )
    dumped = payload.model_dump(by_alias=True)
    assert "incidentId" in dumped
    assert "recoveryOptions" in dumped
    assert "disproofChecks" in dumped
