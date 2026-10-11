import json
import time
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.webhooks import webhook_manager
from app.storage import storage_registry


client = TestClient(app)


def test_service_endpoints():
    # List services (seeded with weather)
    resp = client.get("/api/v1/services")
    assert resp.status_code == 200
    services = resp.json()["services"]
    assert any(s["id"] == "weather" for s in services)

    # Register new service
    resp = client.post(
        "/api/v1/services/inventory",
        json={
            "name": "Inventory API",
            "base_url": "http://127.0.0.1:9000/inventory",
            "description": "Stock tracking",
            "is_critical": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "registered"

    # Get details
    resp = client.get("/api/v1/services/inventory")
    assert resp.status_code == 200
    assert resp.json()["service"]["is_critical"] is True

    # Save baseline
    resp = client.post(
        "/api/v1/services/inventory/baseline",
        json={"data": {"stock": 100}, "description": "Baseline v1"},
    )
    assert resp.status_code == 200
    assert resp.json()["baseline"]["version"] == 1

    # Retrieve baseline
    resp = client.get("/api/v1/services/inventory/baseline")
    assert resp.status_code == 200
    assert resp.json()["baseline"]["data"]["stock"] == 100


def test_dependency_endpoints():
    # Check weather dependencies
    resp = client.get("/api/v1/services/weather/dependencies")
    assert resp.status_code == 200
    data = resp.json()
    assert data["service_id"] == "weather"
    assert data["impact"]["exists_in_graph"] is True
    assert "alert_service" in data["impact"]["all_downstream_dependents"]

    # Check full graph topology
    resp = client.get("/api/v1/dependencies/graph")
    assert resp.status_code == 200
    assert resp.json()["dependency_graph"]["node_count"] > 0


def test_incident_and_repair_endpoints():
    # Seed an incident
    inc = storage_registry.create_incident(
        "weather",
        title="Weather field rename test",
        severity="high",
        differences=[{"kind": "field_removed", "path": "temperature"}],
    )
    inc_id = inc["id"]

    # List incidents
    resp = client.get("/api/v1/incidents")
    assert resp.status_code == 200
    assert resp.json()["incident_count"] >= 1

    # Get specific incident
    resp = client.get(f"/api/v1/incidents/{inc_id}")
    assert resp.status_code == 200
    assert resp.json()["incident"]["id"] == inc_id

    # Attempt activation before validation -> MUST FAIL 400
    resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": {
                "operation": "copy_field",
                "source_field": "temp_c",
                "target_field": "temperature",
                "semantics_confirmed": True,
            },
            "authorizer": "operator",
        },
    )
    assert resp.status_code == 400
    assert "validation" in resp.json()["detail"]

    # Validate repair
    val_resp = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": {
                "operation": "copy_field",
                "source_field": "temp_c",
                "target_field": "temperature",
                "semantics_confirmed": True,
            },
            "test_cases": [
                {
                    "input": {"temp_c": 28},
                    "expected": {"temp_c": 28, "temperature": 28},
                }
            ],
        },
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["validation"]["eligible_for_activation"] is True

    # Now activate repair -> Should succeed
    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": {
                "operation": "copy_field",
                "source_field": "temp_c",
                "target_field": "temperature",
                "semantics_confirmed": True,
            },
            "authorizer": "senior_sre",
            "note": "Verified by test suite",
        },
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["status"] == "activated"

    # Rollback
    rb_resp = client.post(
        "/api/v1/repairs/rollback",
        json={
            "service_id": "weather",
            "authorizer": "incident_lead",
            "reason": "Test rollback endpoint",
        },
    )
    assert rb_resp.status_code == 200
    assert rb_resp.json()["status"] == "rolled_back"

    # Audit log
    audit_resp = client.get("/api/v1/repairs/audit")
    assert audit_resp.status_code == 200
    assert len(audit_resp.json()["audit_log"]) > 0


def test_webhook_endpoints():
    # Outgoing subscription (public HTTPS destination)
    sub_resp = client.post(
        "/api/v1/webhooks/subscriptions",
        json={
            "target_url": "https://api.kintsutech.com/webhook",
            "events": ["repair.activated"],
            "description": "Alerting system",
        },
    )
    assert sub_resp.status_code == 200
    assert sub_resp.json()["status"] == "subscribed"

    # List subscriptions (secret must be redacted)
    list_resp = client.get("/api/v1/webhooks/subscriptions")
    assert list_resp.status_code == 200
    subs = list_resp.json()["subscriptions"]
    assert len(subs) >= 1
    assert "secret" not in subs[0]
    assert subs[0]["secret_configured"] is True

    # Incoming webhook receiver with HMAC signature
    payload = json.dumps({"id": "evt_test_101", "type": "ping"}).encode("utf-8")
    sig = webhook_manager.sign_payload(payload)

    resp = client.post(
        "/api/v1/webhooks/incoming",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-KintsuTech-Signature": sig,
            "X-Timestamp": str(time.time()),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "accepted"

    # Invalid signature should be rejected with 401
    bad_resp = client.post(
        "/api/v1/webhooks/incoming",
        content=payload,
        headers={
            "Content-Type": "application/json",
            "X-KintsuTech-Signature": "sha256=invalid_hash",
        },
    )
    assert bad_resp.status_code == 401


def test_mcp_api_endpoints():
    # Discover tools
    tools_resp = client.get("/api/v1/mcp/tools")
    assert tools_resp.status_code == 200
    tools = tools_resp.json()["tools"]
    assert any(t["name"] == "calculate_dependency_impact" for t in tools)

    # Call tool via POST /api/v1/mcp/tools/call
    call_resp = client.post(
        "/api/v1/mcp/tools/call",
        json={
            "name": "calculate_dependency_impact",
            "arguments": {"service_id": "weather"},
        },
    )
    assert call_resp.status_code == 200
    assert call_resp.json()["tool"] == "calculate_dependency_impact"
    assert "impact" in call_resp.json()["result"]
