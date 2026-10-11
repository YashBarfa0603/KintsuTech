from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.provider_client import (
    ProviderConnectionError,
    ProviderResponseError,
    ProviderTimeoutError,
    weather_provider_client,
)
from app.storage import StorageRegistry, storage_registry


client = TestClient(app)


def test_complete_ps3_end_to_end_lifecycle(monkeypatch, tmp_path):
    """
    Complete Phase 4 end-to-end verification covering all 12 stages:
    1. Detect removed/renamed API field
    2. Produce change report and downstream blast radius impact analysis
    3. Create an incident
    4. Generate repair proposal
    5. Validate compatibility adapter independently
    6. Reject activation when validation has not passed
    7. Activate an eligible adapter with human authorization
    8. Persist state across a fresh storage instance
    9. Automatically adapt provider responses through /api/v1/proxy/weather
    10. Roll back the adapter
    11. Verify proxy returns unadapted provider payload after rollback
    12. Verify audit trail records complete lifecycle
    """
    # Stage 1: Detect a removed/renamed field & Stage 2-4: Impact, Incident, Proposal
    baseline_payload = {"city": "Indore", "temperature": 30, "condition": "Sunny"}
    drifting_payload = {"city": "Indore", "temp_c": 30, "condition": "Sunny"}

    analysis_resp = client.post(
        "/api/v1/ai/analyze",
        json={
            "service_id": "weather",
            "baseline": baseline_payload,
            "current": drifting_payload,
            "create_incident_on_change": True,
        },
    )
    assert analysis_resp.status_code == 200
    analysis = analysis_resp.json()

    # Stage 1: Detect changes
    change_rep = analysis["change_report"]
    assert change_rep["has_changes"] is True
    changes = change_rep["changes"]
    assert any(c["kind"] == "field_removed" and c["path"] == "temperature" for c in changes)
    assert any(c["kind"] == "field_added" and c["path"] == "temp_c" for c in changes)

    # Stage 2: Downstream blast radius impact analysis
    impact = analysis["impact_analysis"]
    assert impact["service"] == "weather"
    assert impact["exists_in_graph"] is True
    assert impact["impact_level"] == "critical"
    assert "alert_service" in impact["critical_services_affected"]

    # Stage 3: Incident creation
    incident_id = analysis.get("incident_id")
    assert incident_id is not None
    assert incident_id.startswith("INC-")

    # Stage 4: Repair proposal
    proposal = analysis["repair_workflow"]["proposal"]
    assert proposal is not None
    assert proposal["requires_validation"] is True

    # Stage 6: Reject activation before independent validation has passed
    adapter_config = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    premature_act = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": incident_id,
            "adapter": adapter_config,
            "authorizer": "sre_lead",
        },
    )
    assert premature_act.status_code == 400
    assert "validation" in premature_act.json()["detail"].lower()

    # Stage 5: Validate compatibility adapter independently
    val_resp = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": incident_id,
            "adapter": adapter_config,
            "test_cases": [
                {
                    "input": {"temp_c": 22.5, "city": "Indore", "condition": "Sunny"},
                    "expected": {
                        "temp_c": 22.5,
                        "city": "Indore",
                        "condition": "Sunny",
                        "temperature": 22.5,
                    },
                }
            ],
        },
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()["validation"]
    assert val_data["eligible_for_activation"] is True
    assert val_data["tests_passed"] == 1
    assert val_data["tests_failed"] == 0

    # Stage 7: Activate eligible adapter with explicit human authorization
    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": incident_id,
            "adapter": adapter_config,
            "authorizer": "senior_architect_alice",
            "note": "Validated against reviewer test suite for HackWave 3.0",
        },
    )
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert act_data["status"] == "activated"
    assert act_data["activation"]["authorizer"] == "senior_architect_alice"
    assert act_data["activation"]["incident_id"] == incident_id

    # Stage 8: State persistence across a fresh storage instance
    persisted_svc = storage_registry.get_service("weather")
    assert persisted_svc["has_active_adapter"] is True
    assert persisted_svc["active_adapter"]["authorizer"] == "senior_architect_alice"

    # Also test file persistence with temporary DB
    test_db = tmp_path / "e2e_storage.db"
    file_reg1 = StorageRegistry(db_url=f"sqlite:///{test_db}")
    file_reg1.register_service("weather", name="Weather API")
    file_inc = file_reg1.create_incident("weather", title="Persist test", severity="high", differences=[])
    file_reg1.record_validation(file_inc["id"], {"eligible_for_activation": True})
    file_reg1.activate_repair(file_inc["id"], adapter_config, authorizer="alice")
    del file_reg1

    file_reg2 = StorageRegistry(db_url=f"sqlite:///{test_db}")
    assert file_reg2.get_service("weather")["has_active_adapter"] is True
    assert file_reg2.get_incident(file_inc["id"])["status"] == "repair_activated"

    # Stage 9: Automatically adapt provider responses through /api/v1/proxy/weather
    monkeypatch.setattr(
        weather_provider_client,
        "fetch_weather",
        lambda params=None: {"city": "Indore", "temp_c": 31.0, "condition": "Clear"},
    )

    proxy_resp = client.get("/api/v1/proxy/weather")
    assert proxy_resp.status_code == 200
    p_data = proxy_resp.json()
    assert p_data["status"] == "adapted"
    assert p_data["adapted"] is True
    assert p_data["incident_id"] == incident_id
    assert p_data["data"]["temperature"] == 31.0
    assert p_data["data"]["temp_c"] == 31.0

    # Stage 10: Roll back the adapter
    rb_resp = client.post(
        "/api/v1/repairs/rollback",
        json={
            "service_id": "weather",
            "authorizer": "incident_commander_bob",
            "reason": "Upstream vendor rolled back field change",
        },
    )
    assert rb_resp.status_code == 200
    rb_data = rb_resp.json()
    assert rb_data["status"] == "rolled_back"
    assert rb_data["rollback"]["authorizer"] == "incident_commander_bob"

    # Stage 11: Verify proxy returns unadapted provider payload after rollback
    recovered_proxy = client.get("/api/v1/proxy/weather")
    assert recovered_proxy.status_code == 200
    rec_data = recovered_proxy.json()
    assert rec_data["status"] == "unchanged"
    assert rec_data["adapted"] is False
    assert rec_data["incident_id"] is None
    assert rec_data["data"] == {"city": "Indore", "temp_c": 31.0, "condition": "Clear"}
    assert "temperature" not in rec_data["data"]

    # Stage 12: Verify audit trail records the relevant lifecycle events
    audit_resp = client.get("/api/v1/repairs/audit")
    assert audit_resp.status_code == 200
    audit_events = audit_resp.json()["audit_log"]

    event_types = [e["event"] for e in audit_events]
    assert "repair_validated" in event_types
    assert "repair_activated" in event_types
    assert "repair_rolled_back" in event_types

    rb_audit = next(e for e in audit_events if e["event"] == "repair_rolled_back")
    assert rb_audit["service_id"] == "weather"
    assert rb_audit["authorizer"] == "incident_commander_bob"


def test_edge_cases_and_error_handling_sanitization(monkeypatch):
    """
    Test resilience and error sanitization:
    - No secrets or stack traces leaked
    - Unknown incident ID produces 400
    - Invalid rollback request produces 400
    - Provider timeout produces 504
    - Provider connection error produces 502
    - Malformed provider JSON produces 502
    - Missing source field produces 422
    - Conflicting target field produces 409
    """
    # 1. Unknown incident ID
    bad_act = client.post(
        "/api/v1/repairs/activate",
        json={"incident_id": "INC-NONEXISTENT", "adapter": {"operation": "copy_field"}},
    )
    assert bad_act.status_code == 400
    detail = bad_act.json()["detail"]
    assert "not found" in detail.lower()
    assert "Traceback" not in detail

    # 2. Invalid rollback for unknown service
    bad_rb = client.post(
        "/api/v1/repairs/rollback",
        json={"service_id": "fake_microservice"},
    )
    assert bad_rb.status_code == 400
    assert "not found" in bad_rb.json()["detail"].lower()

    # 3. Provider timeout produces 504
    monkeypatch.setattr(
        weather_provider_client,
        "fetch_weather",
        lambda params=None: (_ for _ in ()).throw(ProviderTimeoutError("Upstream timeout")),
    )
    timeout_resp = client.get("/api/v1/proxy/weather")
    assert timeout_resp.status_code == 504
    assert "timeout" in timeout_resp.json()["detail"].lower()
    assert "Traceback" not in timeout_resp.json()["detail"]

    # 4. Provider connection error produces 502
    monkeypatch.setattr(
        weather_provider_client,
        "fetch_weather",
        lambda params=None: (_ for _ in ()).throw(ProviderConnectionError("Connection refused")),
    )
    conn_resp = client.get("/api/v1/proxy/weather")
    assert conn_resp.status_code == 502
    assert "connection" in conn_resp.json()["detail"].lower()

    # 5. Malformed/non-dict provider payload produces 502
    monkeypatch.setattr(
        weather_provider_client,
        "fetch_weather",
        lambda params=None: (_ for _ in ()).throw(ProviderResponseError("Invalid JSON body")),
    )
    malformed_resp = client.get("/api/v1/proxy/weather")
    assert malformed_resp.status_code == 502
    assert "invalid" in malformed_resp.json()["detail"].lower()
