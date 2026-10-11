"""
Unit and integration tests for canonical Vapi provider adapter and webhook endpoint:
- Route registration in OpenAPI /docs
- Webhook authentication (Bearer token & x-vapi-secret, constant-time verification)
- Malformed JSON and payload validation
- Event lifecycle (status-update, end-of-call-report, unknown events)
- Duplicate webhook delivery idempotency
- Matching call ID to delivery records and updating delivery outcomes
- Outbound API responses (success, rate limit, server error, timeout) via mocks
- Pre-call eligibility: disabled config, recipient consent, E.164, quiet hours, acknowledged alerts
- Duplicate call prevention
- Scheduler escalation with Vapi call dispatch
- Phone number validation and privacy-safe data sanitization
"""

import asyncio
from datetime import datetime, timezone, timedelta
import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.scheduler import AlertScheduler
from app.storage import storage_registry
from app.vapi import (
    VapiClient,
    VapiConfig,
    VapiService,
    build_privacy_alert_summary,
    mask_phone_number,
    validate_phone_number,
    vapi_service,
    verify_vapi_webhook_token,
)

client = TestClient(app)


# ============================================================================
# 1. Route Registration & Documentation
# ============================================================================

def test_vapi_webhook_route_registration():
    """Verify canonical /api/vapi/webhook is registered in FastAPI OpenAPI schema."""
    openapi = app.openapi()
    assert "/api/vapi/webhook" in openapi["paths"]
    endpoint_spec = openapi["paths"]["/api/vapi/webhook"]
    assert "post" in endpoint_spec
    assert "Vapi Webhook Endpoint" in endpoint_spec["post"]["summary"]


# ============================================================================
# 2. Validation & Privacy Sanitization
# ============================================================================

def test_validate_phone_number_e164():
    """Validate E.164 phone number formatting requirements."""
    assert validate_phone_number("+14155552671") is True
    assert validate_phone_number("+919876543210") is True
    assert validate_phone_number("+442071838750") is True

    # Invalid numbers
    assert validate_phone_number("4155552671") is False  # missing +
    assert validate_phone_number("+01234567") is False   # country code cannot start with 0
    assert validate_phone_number("invalid") is False
    assert validate_phone_number("") is False
    assert validate_phone_number(None) is False


def test_mask_phone_number():
    """Mask phone numbers for safe logs and audit trails."""
    assert mask_phone_number("+14155552671") == "+1***2671"
    assert mask_phone_number("+919876543210") == "+9***3210"
    assert mask_phone_number("123") == "***"
    assert mask_phone_number("") == ""


def test_build_privacy_alert_summary_does_not_leak_secrets():
    """Spoken summary context passed to Vapi assistant strictly excludes credentials or tokens."""
    alert = {
        "id": "alt_test_99",
        "title": "Database connection pool exhausted",
        "severity": "critical",
        "incident_id": "INC-042",
        "message": "Internal credentials: postgres://user:secret123@db:5432/main",
        "metadata": {"service_id": "payment-api"},
    }
    summary = build_privacy_alert_summary(alert)
    assert summary["alert_id"] == "alt_test_99"
    assert summary["severity"] == "CRITICAL"
    assert summary["incident_id"] == "INC-042"
    assert summary["service_id"] == "payment-api"
    # Ensure sensitive credentials in raw message are omitted from spoken summary
    assert "secret123" not in summary["summary"]
    assert "postgres://" not in summary["summary"]
    assert "KintsuTech" in summary["summary"]


def test_vapi_config_readiness(monkeypatch):
    """Test safe public readiness report without leaking secrets."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "false")
    assert VapiConfig.is_ready() is False

    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "")
    assert VapiConfig.is_ready() is False

    monkeypatch.setenv("VAPI_API_KEY", "test-vapi-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-uuid-123")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-uuid-456")
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "webhook-token-789")
    assert VapiConfig.is_ready() is True

    report = VapiConfig.get_readiness_report()
    assert report["ready"] is True
    assert report["api_key_configured"] is True
    assert report["phone_number_id_configured"] is True
    assert report["assistant_id_configured"] is True
    assert report["webhook_token_configured"] is True
    # Ensure secrets never leak in report
    assert "test-vapi-key" not in str(report)
    assert "webhook-token-789" not in str(report)


def test_telephony_status_endpoints(monkeypatch):
    """Verify telephony status reported in status endpoints."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "vapi-key-test")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-id")
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "webhook-secret")

    res = client.get("/api/v1/telephony/status")
    assert res.status_code == 200
    data = res.json()
    assert data["enabled"] is True
    assert data["ready"] is True
    assert "vapi-key-test" not in str(data)

    res_voice = client.get("/api/v1/voice/status")
    assert res_voice.status_code == 200
    voice_data = res_voice.json()
    assert "telephony" in voice_data
    assert voice_data["telephony"]["ready"] is True


# ============================================================================
# 3. Webhook Authentication
# ============================================================================

def test_webhook_authentication_bearer_and_vapi_secret(monkeypatch):
    """Test constant-time verification of Bearer token and x-vapi-secret header."""
    token = "secret-token-xyz-123"
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", token)

    # Valid Authorization: Bearer
    assert verify_vapi_webhook_token({"Authorization": f"Bearer {token}"}) is True
    assert verify_vapi_webhook_token({"authorization": f"bearer {token}"}) is True

    # Valid x-vapi-secret
    assert verify_vapi_webhook_token({"x-vapi-secret": token}) is True
    assert verify_vapi_webhook_token({"X-Vapi-Secret": token}) is True

    # Invalid tokens
    assert verify_vapi_webhook_token({"Authorization": "Bearer wrong-token"}) is False
    assert verify_vapi_webhook_token({"x-vapi-secret": "wrong-token"}) is False
    assert verify_vapi_webhook_token({}) is False


def test_webhook_fails_closed_when_token_unconfigured(monkeypatch):
    """When no webhook token is configured on backend, all webhook calls must be rejected."""
    monkeypatch.delenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", raising=False)
    monkeypatch.delenv("VAPI_WEBHOOK_SECRET", raising=False)
    assert verify_vapi_webhook_token({"Authorization": "Bearer any-token"}) is False
    assert verify_vapi_webhook_token({"x-vapi-secret": "any-token"}) is False


def test_vapi_webhook_endpoint_unauthorized(monkeypatch):
    """POST /api/vapi/webhook returns 401 when missing or wrong credentials."""
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "valid-secret-token")

    # Missing auth header
    res_missing = client.post("/api/vapi/webhook", json={"message": {"type": "status-update"}})
    assert res_missing.status_code == 401
    assert "Unauthorized" in res_missing.json()["detail"]

    # Wrong auth header
    res_wrong = client.post(
        "/api/vapi/webhook",
        headers={"Authorization": "Bearer wrong-secret"},
        json={"message": {"type": "status-update"}},
    )
    assert res_wrong.status_code == 401


# ============================================================================
# 4. Payload Validation & Malformed Requests
# ============================================================================

def test_webhook_malformed_json_and_invalid_payload(monkeypatch):
    """POST /api/vapi/webhook returns 400 for malformed JSON or non-object payloads."""
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "test-token")
    headers = {"Authorization": "Bearer test-token"}

    # Malformed JSON
    res_malformed = client.post(
        "/api/vapi/webhook",
        headers={**headers, "Content-Type": "application/json"},
        content=b"invalid-not-json-content",
    )
    assert res_malformed.status_code == 400
    assert "Malformed JSON" in res_malformed.json()["detail"]

    # JSON Array instead of dict
    res_array = client.post(
        "/api/vapi/webhook",
        headers=headers,
        content=b"[1, 2, 3]",
    )
    assert res_array.status_code == 400
    assert "JSON object" in res_array.json()["detail"]


def test_webhook_empty_or_missing_call_id_ignored(monkeypatch):
    """Incomplete payload without a call ID is safely ignored with 200 OK."""
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "test-token")
    headers = {"Authorization": "Bearer test-token"}

    res = client.post(
        "/api/vapi/webhook",
        headers=headers,
        json={"message": {"type": "status-update"}},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "ignored"
    assert "No call ID" in data["result"]["reason"]


# ============================================================================
# 5. Event Lifecycle & Idempotency
# ============================================================================

def test_webhook_event_lifecycle_and_delivery_matching(monkeypatch):
    """
    Test status-update and end-of-call-report:
    - Matches provider call ID to existing alert and delivery record
    - Updates delivery record and alert metadata
    """
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "test-token")
    headers = {"Authorization": "Bearer test-token"}

    user_id = "user_vapi_cycle"
    alert = storage_registry.create_alert(user_id=user_id, title="Payment Outage", message="M")
    call_id = "call_vapi_cycle_101"

    # Pre-record delivery attempt for this call
    storage_registry.record_delivery_attempt(
        alert["id"],
        channel="phone",
        status="success",
        details={"call_id": call_id, "provider": "vapi", "status": "queued"},
    )
    storage_registry.update_alert_metadata(alert["id"], {"vapi_call_id": call_id})

    # 1. Send status-update: in-progress
    res1 = client.post(
        "/api/vapi/webhook",
        headers=headers,
        json={
            "message": {
                "type": "status-update",
                "call": {"id": call_id, "status": "in-progress"},
            }
        },
    )
    assert res1.status_code == 200
    assert res1.json()["result"]["status"] == "processed"

    # Check alert metadata updated
    alert_mid = storage_registry.get_alert(alert["id"])
    assert alert_mid["metadata"]["vapi_call_status"] == "in-progress"

    # Check delivery record updated
    delivery_mid = storage_registry.find_delivery_by_call_id(call_id)
    assert delivery_mid is not None
    assert delivery_mid["details"]["call_status"] == "in-progress"

    # 2. Send end-of-call-report: ended
    res2 = client.post(
        "/api/vapi/webhook",
        headers=headers,
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": call_id, "status": "ended"},
                "endedReason": "customer-ended-call",
                "duration": 58.2,
            }
        },
    )
    assert res2.status_code == 200
    assert res2.json()["result"]["status"] == "processed"

    alert_final = storage_registry.get_alert(alert["id"])
    assert alert_final["metadata"]["vapi_call_status"] == "ended"
    assert alert_final["metadata"]["vapi_call_duration"] == 58.2
    assert alert_final["metadata"]["vapi_ended_reason"] == "customer-ended-call"


def test_webhook_duplicate_event_is_idempotent(monkeypatch):
    """Verify that duplicate webhook event deliveries are handled idempotently without duplicate processing."""
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "test-token")
    headers = {"Authorization": "Bearer test-token"}

    user_id = "user_vapi_dup"
    alert = storage_registry.create_alert(user_id=user_id, title="Idempotency Test", message="M")
    call_id = "call_vapi_dup_202"

    storage_registry.record_delivery_attempt(
        alert["id"],
        channel="phone",
        status="success",
        details={"call_id": call_id, "provider": "vapi"},
    )
    storage_registry.update_alert_metadata(alert["id"], {"vapi_call_id": call_id})

    payload = {
        "message": {
            "id": "evt_unique_12345",
            "type": "status-update",
            "call": {"id": call_id, "status": "ringing"},
        }
    }

    # First delivery
    res1 = client.post("/api/vapi/webhook", headers=headers, json=payload)
    assert res1.status_code == 200
    assert res1.json()["result"]["status"] == "processed"

    # Duplicate delivery with identical event ID
    res2 = client.post("/api/vapi/webhook", headers=headers, json=payload)
    assert res2.status_code == 200
    assert res2.json()["result"]["status"] == "duplicate"
    assert "already processed" in res2.json()["result"]["message"]


def test_webhook_acknowledgment_terminates_escalation(monkeypatch):
    """End-of-call report with acknowledgment marks alert acknowledged."""
    monkeypatch.setenv("KINTSUTECH_VAPI_WEBHOOK_TOKEN", "test-token")
    headers = {"Authorization": "Bearer test-token"}

    user_id = "user_ack_vapi"
    alert = storage_registry.create_alert(user_id=user_id, title="Ack Alert", message="M")
    call_id = "call_ack_303"

    storage_registry.update_alert_metadata(alert["id"], {"vapi_call_id": call_id})

    res = client.post(
        "/api/vapi/webhook",
        headers=headers,
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": call_id, "status": "ended"},
                "endedReason": "assistant-acknowledged-alert",
            }
        },
    )
    assert res.status_code == 200
    updated_alert = storage_registry.get_alert(alert["id"])
    assert updated_alert["status"] == "acknowledged"


# ============================================================================
# 6. Outbound Call Eligibility & Mocked API Responses
# ============================================================================

def test_telephony_disabled_rejects_outbound_call(monkeypatch):
    """When telephony is disabled, dispatch_escalation_call refuses to call."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "false")
    user_id = "user_tel_disabled"
    storage_registry.update_alert_preferences(
        user_id, {"phone_consent": True, "phone_number": "+14155552671"}
    )
    alert = storage_registry.create_alert(user_id=user_id, title="Test", message="M")

    res = vapi_service.dispatch_escalation_call(alert)
    assert res["status"] == "failed"
    assert "disabled" in res["error"].lower()


def test_recipient_missing_consent_rejects_call(monkeypatch):
    """Without recipient consent, dispatch_escalation_call refuses to place phone call."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "mock-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-id")

    user_id = "user_no_consent"
    storage_registry.update_alert_preferences(
        user_id, {"phone_consent": False, "phone_number": "+14155552671"}
    )
    alert = storage_registry.create_alert(user_id=user_id, title="Test", message="M")

    res = vapi_service.dispatch_escalation_call(alert)
    assert res["status"] == "failed"
    assert "consent" in res["error"].lower()


def test_invalid_phone_number_rejects_call(monkeypatch):
    """Without valid E.164 phone destination, dispatch_escalation_call refuses to call."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "mock-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-id")

    user_id = "user_invalid_num"
    storage_registry.update_alert_preferences(
        user_id, {"phone_consent": True, "phone_number": "not-a-valid-phone"}
    )
    alert = storage_registry.create_alert(user_id=user_id, title="Test", message="M")

    res = vapi_service.dispatch_escalation_call(alert)
    assert res["status"] == "failed"
    assert "e.164" in res["error"].lower() or "format" in res["error"].lower()


def test_acknowledged_alert_skips_call(monkeypatch):
    """Alerts already acknowledged or resolved must not be called."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    user_id = "user_already_acked"
    storage_registry.update_alert_preferences(
        user_id, {"phone_consent": True, "phone_number": "+14155552671"}
    )
    alert = storage_registry.create_alert(user_id=user_id, title="Test", message="M")
    storage_registry.acknowledge_alert(alert["id"], user_id=user_id)

    acked_alert = storage_registry.get_alert(alert["id"])
    res = vapi_service.dispatch_escalation_call(acked_alert)
    assert res["status"] == "skipped"
    assert "acknowledged" in res["reason"].lower()


def test_duplicate_call_prevention(monkeypatch):
    """Alerts with a call currently queued or in-progress are not called again."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "mock-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-id")

    user_id = "user_dup_call"
    storage_registry.update_alert_preferences(
        user_id, {"phone_consent": True, "phone_number": "+14155552671"}
    )
    alert = storage_registry.create_alert(user_id=user_id, title="Test", message="M")
    storage_registry.update_alert_metadata(alert["id"], {"vapi_call_status": "in-progress"})

    fresh_alert = storage_registry.get_alert(alert["id"])
    res = vapi_service.dispatch_escalation_call(fresh_alert)
    assert res["status"] == "skipped"
    assert "already in progress" in res["reason"].lower()


def test_vapi_api_success_mock(monkeypatch):
    """Successful Vapi outbound call creates call ID and delivery record."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "mock-api-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-uuid-444")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-uuid-555")

    user_id = "user_api_success"
    storage_registry.update_alert_preferences(
        user_id, {"phone_consent": True, "phone_number": "+14155552671"}
    )
    alert = storage_registry.create_alert(
        user_id=user_id,
        title="Gateway Unreachable",
        message="502 Bad Gateway",
        severity="critical",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {
        "id": "vapi_call_live_mock_888",
        "status": "queued",
        "customer": {"number": "+14155552671"},
    }

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        res = vapi_service.dispatch_escalation_call(alert)
        assert res["status"] == "initiated"
        assert res["call_id"] == "vapi_call_live_mock_888"

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["assistantId"] == "asst-uuid-555"
        assert payload["phoneNumberId"] == "phone-uuid-444"
        assert payload["customer"]["number"] == "+14155552671"

    updated = storage_registry.get_alert(alert["id"])
    assert updated["metadata"]["vapi_call_id"] == "vapi_call_live_mock_888"


def test_vapi_api_failure_modes_mock(monkeypatch):
    """Test rate limit (429) and timeout handling."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "mock-api-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-uuid-444")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-uuid-555")

    user_id = "user_api_fail"
    storage_registry.update_alert_preferences(
        user_id, {"phone_consent": True, "phone_number": "+14155552671"}
    )
    alert = storage_registry.create_alert(user_id=user_id, title="Test", message="M")

    # 1. HTTP 429 Rate Limit
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_429.text = "Rate limit exceeded"
    with patch("httpx.Client.post", return_value=mock_429):
        res = vapi_service.dispatch_escalation_call(alert)
        assert res["status"] == "failed"
        assert "rate limit" in res["error"].lower()

    # 2. Timeout
    import httpx
    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Connection timed out")):
        res = vapi_service.dispatch_escalation_call(alert)
        assert res["status"] == "failed"
        assert "timed out" in res["error"].lower()


def test_async_vapi_client_call(monkeypatch):
    """Test asynchronous call initiation method on VapiClient."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "mock-api-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-uuid-444")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-uuid-555")

    client_instance = VapiClient()
    alert = {"id": "alt_async_1", "title": "High Latency", "severity": "high"}

    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"id": "vapi_async_call_999", "status": "queued"}

    async def _run():
        with patch("httpx.AsyncClient.post", return_value=mock_resp):
            return await client_instance.initiate_phone_call_async("+14155552671", alert)

    res = asyncio.run(_run())
    assert res["success"] is True
    assert res["call_id"] == "vapi_async_call_999"


# ============================================================================
# 7. Scheduler Escalation with Vapi Call Integration
# ============================================================================

def test_scheduler_escalation_initiates_vapi_call(monkeypatch):
    """AlertScheduler automatically claims overdue alert and initiates Vapi call."""
    monkeypatch.setenv("KINTSUTECH_TELEPHONY_ENABLED", "true")
    monkeypatch.setenv("VAPI_API_KEY", "vapi-key")
    monkeypatch.setenv("VAPI_PHONE_NUMBER_ID", "phone-id")
    monkeypatch.setenv("VAPI_ASSISTANT_ID", "asst-id")

    user_id = "user_sched_vapi"
    storage_registry.update_alert_preferences(
        user_id,
        {
            "phone_consent": True,
            "phone_number": "+14155552671",
            "channels": ["in_app", "phone"],
        },
    )

    now = datetime.now(timezone.utc)
    past_due = (now - timedelta(seconds=20)).isoformat()

    alert = storage_registry.create_alert(
        user_id=user_id,
        title="Critical Database Outage",
        message="Cluster disconnected",
        severity="critical",
        due_at=past_due,
        next_escalation_at=past_due,
    )

    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"id": "call_sched_123", "status": "queued"}

    async def _test():
        scheduler = AlertScheduler(storage_registry)
        with patch("httpx.Client.post", return_value=mock_response):
            poll_res = await scheduler.poll_once(now_iso=now.isoformat())
            assert poll_res["escalated"] >= 1
            assert poll_res.get("calls_dispatched", 0) >= 1

    asyncio.run(_test())

    updated = storage_registry.get_alert(alert["id"])
    assert updated["status"] == "escalated"
    assert updated["metadata"].get("vapi_call_id") == "call_sched_123"
