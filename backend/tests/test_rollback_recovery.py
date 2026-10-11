from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.storage import storage_registry


client = TestClient(app)


def test_phase1_eligible_adapter_activation_transforms_compatible_request():
    """
    Test Phase 1 requirement:
    - An eligible adapter can be activated.
    - The active adapter transforms a compatible request.
    """
    # 1. Ensure 'weather' service exists and has an incident
    inc = storage_registry.create_incident(
        "weather",
        title="Field rename: temp_c to temperature",
        severity="medium",
        differences=[{"kind": "field_removed", "path": "temperature"}],
    )
    inc_id = inc["id"]

    adapter_config = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    # 2. Validate the adapter first (guard requirement)
    val_resp = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": adapter_config,
            "test_cases": [
                {
                    "input": {"temp_c": 21.5, "condition": "Cloudy"},
                    "expected": {"temp_c": 21.5, "condition": "Cloudy", "temperature": 21.5},
                }
            ],
        },
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["validation"]["eligible_for_activation"] is True

    # 3. Activate the validated adapter
    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": adapter_config,
            "authorizer": "lead_sre_operator",
            "note": "Validated with field test case",
        },
    )
    assert act_resp.status_code == 200
    act_data = act_resp.json()
    assert act_data["status"] == "activated"
    assert act_data["activation"]["incident_id"] == inc_id
    assert act_data["activation"]["service_id"] == "weather"
    assert act_data["activation"]["authorizer"] == "lead_sre_operator"

    # 4. Prove the active adapter transforms a compatible request
    payload = {"temp_c": 26.0, "city": "Bengaluru", "condition": "Sunny"}
    compat_resp = client.post("/api/v1/compatible/weather", json=payload)
    assert compat_resp.status_code == 200
    compat_data = compat_resp.json()

    assert compat_data["status"] == "adapted"
    assert compat_data["incident_id"] == inc_id
    # Transformed data includes original fields plus the mapped target field
    assert compat_data["data"]["temperature"] == 26.0
    assert compat_data["data"]["temp_c"] == 26.0
    assert compat_data["data"]["city"] == "Bengaluru"


def test_phase1_rollback_removes_adapter_and_restores_unadapted_state():
    """
    Test Phase 1 requirement:
    - Rollback removes the active adapter.
    - After rollback, the compatibility endpoint returns the original input unchanged with a clear reason.
    """
    # Verify weather currently has an active adapter (from previous test or set one up)
    svc = storage_registry.get_service("weather")
    if not svc or not svc.get("active_adapter"):
        # Set up an active adapter
        inc = storage_registry.create_incident("weather", title="Rollback test", severity="low", differences=[])
        storage_registry.record_validation(inc["id"], {"eligible_for_activation": True})
        storage_registry.activate_repair(
            inc["id"],
            {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"},
        )

    # Trigger rollback
    rb_resp = client.post(
        "/api/v1/repairs/rollback",
        json={
            "service_id": "weather",
            "authorizer": "incident_commander",
            "reason": "Routine rollback test for recovery verification",
        },
    )
    assert rb_resp.status_code == 200
    rb_data = rb_resp.json()
    assert rb_data["status"] == "rolled_back"
    assert rb_data["rollback"]["service_id"] == "weather"
    assert rb_data["rollback"]["authorizer"] == "incident_commander"
    assert rb_data["rollback"]["reason"] == "Routine rollback test for recovery verification"

    # Verify service metadata confirms active_adapter is None
    svc_after = storage_registry.get_service("weather")
    assert svc_after["active_adapter"] is None

    # Prove compatibility endpoint returns original input UNCHANGED with a clear reason
    original_input = {"temp_c": 31.2, "humidity": 75}
    recovered_resp = client.post("/api/v1/compatible/weather", json=original_input)
    assert recovered_resp.status_code == 200
    rec_data = recovered_resp.json()

    assert rec_data["status"] == "unchanged"
    assert rec_data["data"] == original_input
    assert "temperature" not in rec_data["data"]
    assert rec_data["reason"] == "No active compatibility adapter."


def test_phase1_invalid_activation_and_rollback_produce_appropriate_errors():
    """
    Test Phase 1 requirement:
    - Invalid incident IDs and invalid rollback requests produce appropriate errors.
    """
    # 1. Activation with non-existent incident ID -> 400
    bad_act = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": "INC-NONEXISTENT",
            "adapter": {"operation": "copy_field", "source_field": "a", "target_field": "b"},
            "authorizer": "test",
        },
    )
    assert bad_act.status_code == 400
    assert "not found" in bad_act.json()["detail"].lower()

    # 2. Activation with unvalidated incident -> 400
    unval_inc = storage_registry.create_incident("weather", title="Unvalidated", severity="low", differences=[])
    unval_act = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": unval_inc["id"],
            "adapter": {"operation": "copy_field", "source_field": "a", "target_field": "b"},
            "authorizer": "test",
        },
    )
    assert unval_act.status_code == 400
    assert "validation" in unval_act.json()["detail"].lower()

    # 3. Rollback with non-existent service ID -> 400
    bad_rb_svc = client.post(
        "/api/v1/repairs/rollback",
        json={
            "service_id": "non_existent_service",
            "authorizer": "test",
            "reason": "Test",
        },
    )
    assert bad_rb_svc.status_code == 400
    assert "not found" in bad_rb_svc.json()["detail"].lower()

    # 4. Rollback when no active adapter exists on service -> 400
    # Make sure weather has no active adapter
    weather_svc = storage_registry.get_service("weather")
    assert weather_svc["active_adapter"] is None
    redundant_rb = client.post(
        "/api/v1/repairs/rollback",
        json={
            "service_id": "weather",
            "authorizer": "test",
            "reason": "Trying to rollback when nothing is active",
        },
    )
    assert redundant_rb.status_code == 400
    assert "no active adapter" in redundant_rb.json()["detail"].lower()

    # 5. Rollback with missing required body -> 422 Unprocessable Entity
    missing_body_rb = client.post(
        "/api/v1/repairs/rollback",
        json={},
    )
    assert missing_body_rb.status_code == 422


def test_phase1_audit_trail_records_activation_and_rollback():
    """
    Test Phase 1 requirement:
    - The audit trail records activation and rollback.
    """
    # Set up and activate an adapter
    inc = storage_registry.create_incident("weather", title="Audit test", severity="medium", differences=[])
    storage_registry.record_validation(inc["id"], {"eligible_for_activation": True})
    client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc["id"],
            "adapter": {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"},
            "authorizer": "audit_auditor_1",
            "note": "Activation for audit trail test",
        },
    )

    # Roll back
    client.post(
        "/api/v1/repairs/rollback",
        json={
            "service_id": "weather",
            "authorizer": "audit_auditor_2",
            "reason": "Rollback for audit trail test",
        },
    )

    # Fetch audit log
    audit_resp = client.get("/api/v1/repairs/audit")
    assert audit_resp.status_code == 200
    audit_entries = audit_resp.json()["audit_log"]
    assert len(audit_entries) >= 2

    # Verify repair_activated record
    act_entries = [e for e in audit_entries if e["event"] == "repair_activated" and e.get("authorizer") == "audit_auditor_1"]
    assert len(act_entries) >= 1
    act_entry = act_entries[0]
    assert act_entry["service_id"] == "weather"
    assert act_entry["incident_id"] == inc["id"]
    assert "timestamp" in act_entry

    # Verify repair_rolled_back record
    rb_entries = [e for e in audit_entries if e["event"] == "repair_rolled_back" and e.get("authorizer") == "audit_auditor_2"]
    assert len(rb_entries) >= 1
    rb_entry = rb_entries[0]
    assert rb_entry["service_id"] == "weather"
    assert rb_entry["reason"] == "Rollback for audit trail test"
    assert "timestamp" in rb_entry


def test_phase1_compatible_weather_schema_validation():
    """
    Test edge cases for compatible_weather endpoint when adapter is active:
    - Missing source field -> 422 Unprocessable Entity
    - Conflicting existing target field -> 409 Conflict
    """
    inc = storage_registry.create_incident("weather", title="Edge cases", severity="low", differences=[])
    storage_registry.record_validation(inc["id"], {"eligible_for_activation": True})
    storage_registry.activate_repair(
        inc["id"],
        {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"},
    )

    # Missing source field 'temp_c'
    res_missing = client.post("/api/v1/compatible/weather", json={"city": "London", "humidity": 80})
    assert res_missing.status_code == 422
    assert "source field 'temp_c' is missing" in res_missing.json()["detail"].lower()

    # Conflicting target field 'temperature' with different value
    res_conflict = client.post("/api/v1/compatible/weather", json={"temp_c": 15.0, "temperature": 25.0})
    assert res_conflict.status_code == 409
    assert "already exists" in res_conflict.json()["detail"].lower()

    # Cleanup: rollback
    storage_registry.rollback_repair("weather", reason="Cleanup edge case test")
