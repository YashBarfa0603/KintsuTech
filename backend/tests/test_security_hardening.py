import json
import socket
from unittest.mock import patch
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.security import (
    compute_adapter_hash,
    is_disallowed_ip,
    validate_target_url,
)
from app.storage import storage_registry
from app.webhooks import WebhookManager


client = TestClient(app)


# 1. Authentication & Authorization Tests


def test_api_key_missing_and_invalid_rejected(monkeypatch):
    """Ensure missing and invalid API keys return HTTP 401 on protected endpoints."""
    monkeypatch.setenv("KINTSUTECH_API_KEY", "super-secret-api-key-5a")

    # Missing API key header on repair activation
    resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": "INC-001",
            "adapter": {"operation": "copy_field", "source_field": "a", "target_field": "b"},
            "authorizer": "admin_user",
        },
    )
    assert resp.status_code == 401
    assert "Missing API key" in resp.json()["detail"]

    # Invalid API key header
    resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": "INC-001",
            "adapter": {"operation": "copy_field", "source_field": "a", "target_field": "b"},
        },
        headers={"X-API-Key": "incorrect-key"},
    )
    assert resp.status_code == 401
    assert "Invalid API key" in resp.json()["detail"]

    # Missing API key on rollback
    resp = client.post(
        "/api/v1/repairs/rollback",
        json={"service_id": "weather", "authorizer": "admin_user"},
    )
    assert resp.status_code == 401

    # Invalid Bearer token on rollback
    resp = client.post(
        "/api/v1/repairs/rollback",
        json={"service_id": "weather", "authorizer": "admin_user"},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert resp.status_code == 401

    # Missing API key on baseline modification
    resp = client.post(
        "/api/v1/services/weather/baseline",
        json={"data": {"temperature": 25}},
    )
    assert resp.status_code == 401

    # Missing API key on webhook subscription
    resp = client.post(
        "/api/v1/webhooks/subscriptions",
        json={"target_url": "https://api.kintsutech.com/hook", "events": ["*"]},
    )
    assert resp.status_code == 401

    # Missing API key on webhook subscription listing
    resp = client.get("/api/v1/webhooks/subscriptions")
    assert resp.status_code == 401

    # Missing API key on MCP tool execution
    resp = client.post(
        "/api/v1/mcp/tools/call",
        json={"name": "list_services", "arguments": {}},
    )
    assert resp.status_code == 401


def test_production_fails_safely_when_auth_unconfigured(monkeypatch):
    """Ensure production mode fails safely with 401 when no server API key is configured."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("KINTSUTECH_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": "INC-001",
            "adapter": {"operation": "copy_field", "source_field": "a", "target_field": "b"},
        },
    )
    assert resp.status_code == 401
    assert "KINTSUTECH_API_KEY is not configured" in resp.json()["detail"]


def test_authorized_activation_and_rollback(monkeypatch):
    """Verify that requests with valid API key are successfully authorized."""
    key = "valid-phase5a-test-key"
    monkeypatch.setenv("KINTSUTECH_API_KEY", key)

    # Setup incident and validated adapter
    inc = storage_registry.create_incident(
        "weather",
        title="Auth Test Incident",
        severity="low",
        differences=[],
    )
    inc_id = inc["id"]

    adapter = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    # Validate adapter
    val_resp = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": adapter,
            "test_cases": [{"input": {"temp_c": 20}, "expected": {"temp_c": 20, "temperature": 20}}],
        },
    )
    assert val_resp.status_code == 200

    # Authorized activation using X-API-Key
    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": adapter,
            "authorizer": "audited_lead",
        },
        headers={"X-API-Key": key},
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["status"] == "activated"

    # Authorized rollback using Authorization: Bearer
    rb_resp = client.post(
        "/api/v1/repairs/rollback",
        json={
            "service_id": "weather",
            "authorizer": "audited_lead",
            "reason": "Test authorized rollback",
        },
        headers={"Authorization": f"Bearer {key}"},
    )
    assert rb_resp.status_code == 200
    assert rb_resp.json()["status"] == "rolled_back"


def test_public_endpoints_accessible_without_credentials(monkeypatch):
    """Ensure public monitoring, proxy, and discovery endpoints remain accessible without auth."""
    monkeypatch.setenv("KINTSUTECH_API_KEY", "configured-secret-key")

    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/health/readiness").status_code == 200
    assert client.get("/api/v1/proxy/weather").status_code == 200
    assert client.get("/api/v1/services").status_code == 200
    assert client.get("/api/v1/services/weather").status_code == 200
    assert client.get("/api/v1/services/weather/baseline").status_code == 200
    assert client.get("/api/v1/dependencies/graph").status_code == 200
    assert client.get("/api/v1/incidents").status_code == 200
    assert client.get("/api/v1/mcp/tools").status_code == 200


# 2. Webhook Security & SSRF Tests


def test_webhook_secret_redaction(monkeypatch):
    """Verify that webhook secrets are never returned in subscription listings."""
    mgr = WebhookManager(secret="private_signing_key_456")
    sub = mgr.subscribe(
        target_url="https://api.kintsutech.com/alerts",
        events=["repair.activated"],
        secret="custom_subscriber_secret_789",
    )

    subs = mgr.list_subscriptions()
    assert len(subs) >= 1
    found = next(s for s in subs if s["id"] == sub["id"])
    assert "secret" not in found
    assert found["secret_configured"] is True


def test_webhook_ssrf_rejects_forbidden_destinations():
    """Verify strict rejection of loopback, private, link-local, multicast, and metadata addresses."""
    # Loopback IP literals
    with pytest.raises(ValueError, match="forbidden IP range"):
        validate_target_url("http://127.0.0.1:8000/webhook")

    with pytest.raises(ValueError, match="forbidden IP range"):
        validate_target_url("http://127.0.0.2:9000/webhook")

    # Localhost hostnames
    with pytest.raises(ValueError, match="forbidden internal hostname"):
        validate_target_url("http://localhost:8000/webhook")

    with pytest.raises(ValueError, match="forbidden internal hostname"):
        validate_target_url("http://service.local/webhook")

    # Private RFC 1918 subnets
    with pytest.raises(ValueError, match="forbidden IP range"):
        validate_target_url("http://10.0.0.1/webhook")

    with pytest.raises(ValueError, match="forbidden IP range"):
        validate_target_url("http://172.16.0.10/webhook")

    with pytest.raises(ValueError, match="forbidden IP range"):
        validate_target_url("http://192.168.1.1/webhook")

    # Cloud metadata / Link-local addresses
    with pytest.raises(ValueError, match="forbidden IP range"):
        validate_target_url("http://169.254.169.254/latest/meta-data")

    with pytest.raises(ValueError, match="forbidden IP range"):
        validate_target_url("http://169.254.1.1/webhook")

    # Unspecified / Broadcast
    with pytest.raises(ValueError, match="forbidden IP range"):
        validate_target_url("http://0.0.0.0:8000/webhook")


def test_webhook_ssrf_rejects_hostname_resolving_to_forbidden_ip():
    """Verify DNS resolution catches hostnames that resolve to internal/forbidden IPs."""
    # Mock DNS resolving to loopback
    def mock_loopback_resolver(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    with pytest.raises(ValueError, match="resolves to a forbidden IP address"):
        validate_target_url("http://attacker-controlled.com/webhook", dns_resolver=mock_loopback_resolver)

    # Mock DNS resolving to cloud metadata
    def mock_metadata_resolver(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", port))]

    with pytest.raises(ValueError, match="resolves to a forbidden IP address"):
        validate_target_url("http://rebound-cloud.com/webhook", dns_resolver=mock_metadata_resolver)


def test_webhook_allows_public_https_destination_without_network_call():
    """Verify valid public HTTPS destination passes validation without contacting external servers."""
    def mock_public_resolver(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]

    # Should succeed without error
    validate_target_url("https://safe-subscriber.com/webhook", dns_resolver=mock_public_resolver)


# 3. Adapter Validation-to-Activation Binding Tests


def test_adapter_tampering_rejected_by_hash_mismatch():
    """
    Verify security integrity:
    1. Validate safe Adapter A for an incident.
    2. Attempt to activate untrusted Adapter B for the same incident -> REJECTED (hash mismatch).
    3. Activate validated Adapter A -> SUCCEEDS.
    """
    inc = storage_registry.create_incident(
        "weather",
        title="Tamper Protection Test",
        severity="medium",
        differences=[{"kind": "field_removed", "path": "temperature"}],
    )
    inc_id = inc["id"]

    adapter_a = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    adapter_b = {
        "operation": "copy_field",
        "source_field": "malicious_field",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    # Step 1: Validate Adapter A
    val_resp = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": adapter_a,
            "test_cases": [
                {"input": {"temp_c": 22}, "expected": {"temp_c": 22, "temperature": 22}}
            ],
        },
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["validation"]["eligible_for_activation"] is True
    assert "adapter_hash" in val_resp.json()["validation"]

    # Step 2: Attempt to activate Adapter B (tampered) -> MUST FAIL (HTTP 400)
    tamper_act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": adapter_b,
            "authorizer": "operator",
        },
    )
    assert tamper_act_resp.status_code == 400
    assert "does not match validated adapter" in tamper_act_resp.json()["detail"].lower()

    # Step 3: Activate validated Adapter A -> MUST SUCCEED (HTTP 200)
    valid_act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": adapter_a,
            "authorizer": "verified_lead",
        },
    )
    assert valid_act_resp.status_code == 200
    assert valid_act_resp.json()["status"] == "activated"


def test_storage_layer_enforces_adapter_hash_directly():
    """Verify that storage_registry.activate_repair enforces hash check directly in Python layer."""
    inc = storage_registry.create_incident("weather", title="Direct Storage Test", severity="low", differences=[])
    inc_id = inc["id"]

    adapter_validated = {"operation": "copy_field", "source_field": "a", "target_field": "b"}
    adapter_tampered = {"operation": "copy_field", "source_field": "x", "target_field": "y"}

    # Record validation with adapter_validated
    storage_registry.record_validation(
        inc_id,
        {"eligible_for_activation": True, "tests_passed": 1},
        adapter_config=adapter_validated,
    )

    # Calling activate_repair with tampered adapter must raise ValueError
    with pytest.raises(ValueError, match="does not match validated adapter"):
        storage_registry.activate_repair(inc_id, adapter_tampered)

    # Calling activate_repair with validated adapter must succeed
    result = storage_registry.activate_repair(inc_id, adapter_validated)
    assert result["service_id"] == "weather"
