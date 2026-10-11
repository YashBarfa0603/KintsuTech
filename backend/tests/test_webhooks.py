import json
import time
import httpx
import pytest

from app.webhooks import WebhookManager


def test_signature_verification():
    mgr = WebhookManager(secret="test_secret_123")
    payload = json.dumps({"action": "schema_change"}).encode("utf-8")

    # Generate valid signature
    valid_sig = mgr.sign_payload(payload)

    assert mgr.verify_signature(payload, valid_sig) is True
    # Test without sha256= prefix
    assert mgr.verify_signature(payload, valid_sig.replace("sha256=", "")) is True
    # Test invalid signature
    assert mgr.verify_signature(payload, "sha256=bad_hex") is False
    assert mgr.verify_signature(payload, None) is False


def test_timestamp_freshness():
    mgr = WebhookManager()
    now = time.time()

    assert mgr.verify_timestamp(str(now)) is True
    # 10 minutes ago should fail (tolerance is 300s)
    assert mgr.verify_timestamp(str(now - 600)) is False
    assert mgr.verify_timestamp("invalid_time") is False
    assert mgr.verify_timestamp(None) is False


def test_idempotency_deduplication():
    mgr = WebhookManager()
    event_id = "evt_unique_123"

    assert mgr.is_duplicate_event(event_id) is False
    # Second time must be recognized as duplicate
    assert mgr.is_duplicate_event(event_id) is True


def test_subscription_and_dispatch_with_mock():
    mgr = WebhookManager(secret="dispatch_secret")
    mgr.subscribe(
        target_url="http://mock-subscriber/webhook",
        events=["incident.created"],
    )

    received_requests = []

    def mock_handler(request: httpx.Request):
        received_requests.append(request)
        return httpx.Response(200, json={"status": "ok"})

    client = httpx.Client(transport=httpx.MockTransport(mock_handler))

    event = mgr.create_event("incident.created", {"incident_id": "INC-001"})
    delivery_logs = mgr.dispatch_event(event, client=client)

    assert len(delivery_logs) == 1
    assert delivery_logs[0]["status"] == "delivered"
    assert len(received_requests) == 1
    # Check headers
    assert "X-KintsuTech-Signature" in received_requests[0].headers
    assert received_requests[0].headers["X-KintsuTech-Event"] == "incident.created"
