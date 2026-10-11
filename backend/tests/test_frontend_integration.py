import json
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.storage import storage_registry


client = TestClient(app)


def test_frontend_health_and_readiness_contract():
    # 1. Liveness
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "KintsuTech"
    assert "version" in data
    assert "environment" in data

    # 2. Readiness
    resp = client.get("/api/v1/health/readiness")
    assert resp.status_code == 200
    r_data = resp.json()
    assert r_data["status"] == "ready"
    assert r_data["storage_ready"] is True
    assert r_data["services_registered"] >= 1
    assert r_data["dependency_nodes"] >= 1


def test_frontend_full_lifecycle_detect_validate_activate_rollback():
    """
    End-to-end integration test simulating frontend user flow:
    1. Inspect services and baselines.
    2. Detect API change with impact analysis and auto-incident creation.
    3. Retrieve the created incident and evidence.
    4. Verify that activation is BLOCKED before independent validation.
    5. Perform deterministic validation with regression test cases.
    6. Activate repair with authorized reviewer.
    7. Rollback repair to baseline.
    8. Check audit trail.
    """
    # Step 1: Frontend queries services
    resp = client.get("/api/v1/services")
    assert resp.status_code == 200
    services = resp.json()["services"]
    assert any(s["id"] == "weather" for s in services)

    # Step 2: Frontend queries baseline
    b_resp = client.get("/api/v1/services/weather/baseline")
    assert b_resp.status_code == 200
    baseline_data = b_resp.json()["baseline"]["data"]

    # Step 3: Frontend submits changed payload to AI analysis endpoint
    current_payload = dict(baseline_data)
    # simulate field rename: temperature -> temp_c
    if "temperature" in current_payload:
        del current_payload["temperature"]
    current_payload["temp_c"] = 28

    mock_repair_workflow = {
        "status": "pending_review",
        "proposal": {
            "change_summary": "The 'temperature' field was replaced by 'temp_c'.",
            "evidence": ["Field removed: temperature", "Field added: temp_c"],
            "potential_impact": "Downstream consumers reading temperature may fail.",
            "proposed_repair": "Use a field-copy compatibility adapter.",
            "confidence": 0.85,
            "requires_validation": True,
        },
        "validation": {
            "eligible_for_activation": False,
            "status": "pending_review",
            "tests_passed": 0,
            "tests_failed": 0,
            "errors": ["Independent review required."],
        },
    }

    with patch("app.main.run_change_workflow") as mock_workflow:
        mock_workflow.return_value = {
            "change_report": {
                "has_changes": True,
                "total_change_count": 2,
                "breaking_change_count": 1,
                "summary": {"structural_changes": 2},
                "changes": [
                    {"source": "structural", "kind": "field_removed", "path": "temperature"},
                    {"source": "structural", "kind": "field_added", "path": "temp_c"},
                ],
                "evidence": {},
            },
            "repair_workflow": mock_repair_workflow,
        }

        analyze_resp = client.post(
            "/api/v1/ai/analyze",
            json={
                "service_id": "weather",
                "include_impact": True,
                "create_incident_on_change": True,
                "baseline": baseline_data,
                "current": current_payload,
            },
        )

    assert analyze_resp.status_code == 200
    analysis = analyze_resp.json()

    assert analysis["change_report"]["has_changes"] is True
    assert "impact_analysis" in analysis
    assert analysis["impact_analysis"]["impact_level"] == "critical"
    assert "incident_id" in analysis
    incident_id = analysis["incident_id"]

    # Step 4: Frontend fetches incident and evidence
    inc_resp = client.get(f"/api/v1/incidents/{incident_id}")
    assert inc_resp.status_code == 200
    incident = inc_resp.json()["incident"]
    assert incident["id"] == incident_id
    assert incident["status"] == "open"
    assert len(incident["differences"]) == 2

    # Step 5: Frontend attempts unauthorized activation without validation -> MUST BE REJECTED (400)
    adapter_config = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    premature_act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": incident_id,
            "adapter": adapter_config,
            "authorizer": "frontend_user",
        },
    )
    assert premature_act_resp.status_code == 400
    assert "validation" in premature_act_resp.json()["detail"].lower()

    # Step 6: Frontend performs independent deterministic validation
    val_resp = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": incident_id,
            "adapter": adapter_config,
            "test_cases": [
                {
                    "input": {"temp_c": 28},
                    "expected": {"temp_c": 28, "temperature": 28},
                }
            ],
        },
    )
    assert val_resp.status_code == 200
    val_data = val_resp.json()["validation"]
    assert val_data["eligible_for_activation"] is True
    assert val_data["tests_passed"] == 1

    # Step 7: Frontend activates repair with authorization
    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": incident_id,
            "adapter": adapter_config,
            "authorizer": "lead_architect",
            "note": "Tested against representative sample",
        },
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["status"] == "activated"

    # Verify service shows active adapter in service list
    svc_resp = client.get("/api/v1/services/weather")
    assert svc_resp.status_code == 200
    assert svc_resp.json()["service"]["active_adapter"] is not None

    # Step 8: Frontend triggers instant rollback
    rb_resp = client.post(
        "/api/v1/repairs/rollback",
        json={
            "service_id": "weather",
            "authorizer": "incident_lead",
            "reason": "Reverting adapter after test run",
        },
    )
    assert rb_resp.status_code == 200
    assert rb_resp.json()["status"] == "rolled_back"

    # Verify adapter is now deactivated
    svc_after = client.get("/api/v1/services/weather").json()["service"]
    assert svc_after["active_adapter"] is None

    # Step 9: Audit log contains complete timeline
    audit_resp = client.get("/api/v1/repairs/audit")
    assert audit_resp.status_code == 200
    audit_events = [item["event"] for item in audit_resp.json()["audit_log"]]
    assert "repair_validated" in audit_events
    assert "repair_activated" in audit_events
    assert "repair_rolled_back" in audit_events
