import json
import secrets
import socket
import time
from unittest.mock import patch
import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import compute_adapter_hash
from app.storage import StorageRegistry, WebhookIdempotencyModel, storage_registry
from app.webhooks import WebhookManager, sanitize_error
from sqlalchemy import func, select


client = TestClient(app)


def test_subscription_persistence_after_reopening_database(tmp_path):
    """Ensure subscriptions survive StorageRegistry and WebhookManager restarts."""
    db_file = tmp_path / "kintsu_subs.db"
    db_url = f"sqlite:///{db_file}"

    # Step 1: Initialize storage and subscribe
    storage1 = StorageRegistry(db_url)
    mgr1 = WebhookManager(secret="global_secret_123", storage=storage1)
    sub = mgr1.subscribe(
        target_url="https://api.kintsutech.com/webhooks/receiver",
        events=["incident.created", "repair.validated"],
        secret="target_secret_789",
        description="Persistent webhook subscription test",
    )
    sub_id = sub["id"]

    # Step 2: Simulate application shutdown & restart by initializing new instances
    storage2 = StorageRegistry(db_url)
    mgr2 = WebhookManager(secret="global_secret_123", storage=storage2)

    # Step 3: Verify subscription exists with correct metadata and redacted secret
    subs = mgr2.list_subscriptions()
    assert len(subs) == 1
    reloaded_sub = subs[0]
    assert reloaded_sub["id"] == sub_id
    assert reloaded_sub["target_url"] == "https://api.kintsutech.com/webhooks/receiver"
    assert reloaded_sub["events"] == ["incident.created", "repair.validated"]
    assert reloaded_sub["description"] == "Persistent webhook subscription test"
    assert "secret" not in reloaded_sub
    assert reloaded_sub["secret_configured"] is True

    # Step 4: Verify internal retrieval preserves secret for HMAC signing
    internal_subs = storage2.list_webhook_subscriptions(include_secret=True)
    assert len(internal_subs) == 1
    assert internal_subs[0]["secret"] == "target_secret_789"


def test_delivery_history_persistence_after_reopening_database(tmp_path):
    """Ensure delivery history survives StorageRegistry restarts."""
    db_file = tmp_path / "kintsu_deliv.db"
    db_url = f"sqlite:///{db_file}"

    # Step 1: Record delivery in first instance
    storage1 = StorageRegistry(db_url)
    delivery_record = {
        "delivery_id": "del_persist_001",
        "event_id": "evt_phase5b_100",
        "event_type": "repair.validated",
        "subscription_id": "sub_xyz_999",
        "target_url": "https://api.kintsutech.com/target",
        "attempts": 2,
        "status": "delivered",
        "status_code": 200,
        "error": None,
        "timestamp": "2026-10-11T09:30:00Z",
    }
    storage1.record_webhook_delivery(delivery_record)

    # Step 2: Restart storage
    storage2 = StorageRegistry(db_url)
    mgr2 = WebhookManager(storage=storage2)

    # Step 3: Retrieve delivery logs
    logs = mgr2.get_delivery_logs()
    assert len(logs) == 1
    log = logs[0]
    assert log["delivery_id"] == "del_persist_001"
    assert log["event_id"] == "evt_phase5b_100"
    assert log["event_type"] == "repair.validated"
    assert log["subscription_id"] == "sub_xyz_999"
    assert log["target_url"] == "https://api.kintsutech.com/target"
    assert log["attempts"] == 2
    assert log["status"] == "delivered"
    assert log["status_code"] == 200
    assert log["error"] is None


def test_secret_redaction_from_every_subscription_api_response(monkeypatch):
    """Verify webhook secrets are never returned by any subscription API response."""
    test_key = "phase5b-secret-test-key"
    monkeypatch.setenv("KINTSUTECH_API_KEY", test_key)
    headers = {"X-API-Key": test_key}

    # 1. POST /api/v1/webhooks/subscriptions
    create_resp = client.post(
        "/api/v1/webhooks/subscriptions",
        json={
            "target_url": "https://api.kintsutech.com/secure-listener",
            "events": ["repair.activated"],
            "secret": "confidential_shared_hmac_secret",
            "description": "Redaction verification endpoint",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    created_data = create_resp.json()
    assert created_data["status"] == "subscribed"
    created_sub = created_data["subscription"]
    assert "secret" not in created_sub
    assert created_sub["secret_configured"] is True
    sub_id = created_sub["id"]

    # 2. GET /api/v1/webhooks/subscriptions
    list_resp = client.get("/api/v1/webhooks/subscriptions", headers=headers)
    assert list_resp.status_code == 200
    all_subs = list_resp.json()["subscriptions"]
    target_sub = next((s for s in all_subs if s["id"] == sub_id), None)
    assert target_sub is not None
    assert "secret" not in target_sub
    assert target_sub["secret_configured"] is True

    # 3. GET /api/v1/webhooks/subscriptions/{subscription_id}
    detail_resp = client.get(f"/api/v1/webhooks/subscriptions/{sub_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail_sub = detail_resp.json()["subscription"]
    assert detail_sub["id"] == sub_id
    assert "secret" not in detail_sub
    assert detail_sub["secret_configured"] is True


def test_non_blocking_background_dispatch_on_slow_receiver(monkeypatch):
    """Verify API response returns immediately without waiting for slow subscribers."""
    test_key = "phase5b-async-key"
    monkeypatch.setenv("KINTSUTECH_API_KEY", test_key)
    headers = {"X-API-Key": test_key}

    # Setup isolated storage for manager
    test_storage = StorageRegistry()
    test_mgr = WebhookManager(secret="async_test_secret", storage=test_storage)
    test_mgr.subscribe(
        target_url="https://api.kintsutech.com/slow-endpoint",
        events=["repair.rollback_completed"],
    )

    def slow_mock_post(*args, **kwargs):
        # Simulate network latency of 1.0 second
        time.sleep(1.0)
        return httpx.Response(200, json={"status": "ok"})

    event = test_mgr.create_event(
        "repair.rollback_completed",
        {"service_id": "weather", "authorizer": "ops_team"},
        service_id="weather",
    )

    # Patch httpx.Client.post to be slow
    with patch.object(httpx.Client, "post", side_effect=slow_mock_post):
        start_time = time.perf_counter()
        future = test_mgr.dispatch_event_background(event)
        elapsed_dispatch = time.perf_counter() - start_time

        # Background dispatch call must return immediately (< 100ms)
        assert elapsed_dispatch < 0.15, f"dispatch_event_background blocked for {elapsed_dispatch:.3f}s"

        # Wait for the future to finish in background thread
        future.result(timeout=3.0)

    # Confirm delivery log was recorded by the background thread
    deliveries = test_mgr.get_delivery_logs()
    assert len(deliveries) == 1
    assert deliveries[0]["status"] == "delivered"


def test_retry_count_timeout_failure_and_success_delivery():
    """Verify bounded retry count, failure status, and successful retry recovery."""
    test_storage = StorageRegistry()
    mgr = WebhookManager(secret="retry_test_secret", storage=test_storage)
    mgr.subscribe(
        target_url="https://api.kintsutech.com/retry-endpoint",
        events=["incident.created"],
    )

    # Case A: Persistent failure (500) retries up to max_attempts (3) with backoff
    attempts_called = 0

    def failing_handler(request: httpx.Request):
        nonlocal attempts_called
        attempts_called += 1
        return httpx.Response(500, text="Internal Server Error")

    mock_client_failing = httpx.Client(transport=httpx.MockTransport(failing_handler))
    event1 = mgr.create_event("incident.created", {"incident_id": "INC-ERR-1"})

    results_failing = mgr.dispatch_event(
        event1,
        client=mock_client_failing,
        max_attempts=3,
        backoff_base=0.01,
    )
    assert len(results_failing) == 1
    assert results_failing[0]["status"] == "failed"
    assert results_failing[0]["attempts"] == 3
    assert attempts_called == 3
    assert results_failing[0]["status_code"] == 500
    assert "HTTP 500" in results_failing[0]["error"]

    # Case B: Transient failure recovers on attempt 2
    attempts_recovered = 0

    def recovering_handler(request: httpx.Request):
        nonlocal attempts_recovered
        attempts_recovered += 1
        if attempts_recovered < 2:
            return httpx.Response(503, text="Service Unavailable")
        return httpx.Response(200, json={"received": True})

    mock_client_recovering = httpx.Client(transport=httpx.MockTransport(recovering_handler))
    event2 = mgr.create_event("incident.created", {"incident_id": "INC-REC-2"})

    results_recovering = mgr.dispatch_event(
        event2,
        client=mock_client_recovering,
        max_attempts=3,
        backoff_base=0.01,
    )
    assert len(results_recovering) == 1
    assert results_recovering[0]["status"] == "delivered"
    assert results_recovering[0]["attempts"] == 2
    assert results_recovering[0]["status_code"] == 200
    assert results_recovering[0]["error"] is None


def test_ssrf_and_redirect_protection_at_dispatch():
    """Verify SSRF filtering and redirect-blocking at dispatch time."""
    test_storage = StorageRegistry()
    mgr = WebhookManager(secret="ssrf_dispatch_sec", storage=test_storage)

    # 1. SSRF via DNS rebinding (resolves to private loopback 127.0.0.1)
    mgr.storage.create_webhook_subscription({
        "id": "sub_ssrf_test",
        "target_url": "https://rebinding.malicious.com/hook",
        "events": ["*"],
        "secret": "s1",
        "description": "ssrf test",
        "created_at": "2026-10-11T09:00:00Z",
    })

    def fake_loopback_dns(host, port):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    event = mgr.create_event("incident.created", {"data": "test"})
    results = mgr.dispatch_event(event, dns_resolver=fake_loopback_dns)
    assert len(results) == 1
    assert results[0]["status"] == "failed"
    assert results[0]["attempts"] == 0
    assert "SSRF blocked" in results[0]["error"]

    # 2. Redirect protection (follow_redirects=False prevents following 302 to metadata service)
    def redirect_handler(request: httpx.Request):
        return httpx.Response(
            302,
            headers={"Location": "http://169.254.169.254/latest/meta-data"},
        )

    redirect_client = httpx.Client(
        transport=httpx.MockTransport(redirect_handler),
        follow_redirects=False,
    )
    mgr.storage.create_webhook_subscription({
        "id": "sub_redirect_test",
        "target_url": "https://api.kintsutech.com/redirect-target",
        "events": ["*"],
        "secret": "s2",
        "description": "redirect test",
        "created_at": "2026-10-11T09:00:00Z",
    })

    event_redir = mgr.create_event("repair.activated", {"data": "test"})
    results_redir = mgr.dispatch_event(event_redir, client=redirect_client, max_attempts=1)
    redirect_log = next(r for r in results_redir if r["subscription_id"] == "sub_redirect_test")
    assert redirect_log["status"] == "failed"
    assert redirect_log["status_code"] == 302
    assert "HTTP 302" in redirect_log["error"]


def test_new_event_types_dispatched_only_after_successful_operations(monkeypatch):
    """Verify incident.created and repair.validated are only emitted after operations succeed."""
    test_key = "phase5b-events-key"
    monkeypatch.setenv("KINTSUTECH_API_KEY", test_key)
    headers = {"X-API-Key": test_key}

    dispatched_events = []

    def mock_dispatch_background(event, **kwargs):
        dispatched_events.append(event)

    with patch("app.main.webhook_manager.dispatch_event_background", side_effect=mock_dispatch_background):
        # 1. Incident Created via AI Analyze (with changes)
        resp_ai = client.post(
            "/api/v1/ai/analyze",
            json={
                "baseline": {"temperature": 20, "condition": "sunny"},
                "current": {"temp_c": 20, "weather_desc": "sunny"},
                "create_incident_on_change": True,
                "include_impact": True,
                "service_id": "weather",
            },
        )
        assert resp_ai.status_code == 200
        incident_events = [e for e in dispatched_events if e["type"] == "incident.created"]
        assert len(incident_events) == 1
        assert incident_events[0]["service_id"] == "weather"
        incident_id = resp_ai.json()["incident_id"]

        # 2. Repair Validated (Success)
        adapter = {
            "operation": "copy_field",
            "source_field": "temp_c",
            "target_field": "temperature",
            "semantics_confirmed": True,
        }
        val_resp = client.post(
            "/api/v1/repairs/validate",
            json={
                "incident_id": incident_id,
                "adapter": adapter,
                "test_cases": [{"input": {"temp_c": 22}, "expected": {"temp_c": 22, "temperature": 22}}],
            },
        )
        assert val_resp.status_code == 200
        validated_events = [e for e in dispatched_events if e["type"] == "repair.validated"]
        assert len(validated_events) == 1
        assert validated_events[0]["data"]["incident_id"] == incident_id
        val_payload = validated_events[0]["data"]["validation"]
        assert val_payload.get("eligible_for_activation") is True or val_payload.get("passed") is True

        # 3. Repair Validation Failure: Does NOT emit repair.validated
        inc_fail = storage_registry.create_incident("weather", title="Validation Fail Test", severity="low", differences=[])
        client.post(
            "/api/v1/repairs/validate",
            json={
                "incident_id": inc_fail["id"],
                "adapter": adapter,
                "test_cases": [{"input": {"temp_c": 22}, "expected": {"temp_c": 999, "temperature": 999}}],
            },
        )
        # Length of repair.validated events must remain 1
        validated_events_after = [e for e in dispatched_events if e["type"] == "repair.validated"]
        assert len(validated_events_after) == 1

        # 4. Repair Activation Failure: Tampered adapter rejected, repair.activated NOT emitted
        tampered_adapter = {
            "operation": "copy_field",
            "source_field": "tampered_field",
            "target_field": "temperature",
        }
        failed_act_resp = client.post(
            "/api/v1/repairs/activate",
            json={
                "incident_id": incident_id,
                "adapter": tampered_adapter,
                "authorizer": "lead",
            },
            headers=headers,
        )
        assert failed_act_resp.status_code == 400
        activated_events = [e for e in dispatched_events if e["type"] == "repair.activated"]
        assert len(activated_events) == 0

        # 5. Successful Activation emits repair.activated
        success_act_resp = client.post(
            "/api/v1/repairs/activate",
            json={
                "incident_id": incident_id,
                "adapter": adapter,
                "authorizer": "lead",
            },
            headers=headers,
        )
        assert success_act_resp.status_code == 200
        activated_events = [e for e in dispatched_events if e["type"] == "repair.activated"]
        assert len(activated_events) == 1
        assert activated_events[0]["type"] == "repair.activated"


def test_duplicate_event_handling_and_bounded_idempotency_retention():
    """Verify duplicate event detection and bounded retention pruning."""
    storage = StorageRegistry()
    mgr = WebhookManager(secret="idemp_sec", storage=storage)

    # 1. Deduplication detection
    assert mgr.is_duplicate_event("evt_idemp_001") is False
    assert mgr.is_duplicate_event("evt_idemp_001") is True

    # 2. Dispatch deduplication (same event dispatched twice skips second dispatch)
    mgr.subscribe(
        target_url="https://api.kintsutech.com/receiver",
        events=["*"],
    )
    calls = 0

    def mock_post(request: httpx.Request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"status": "ok"})

    mock_client = httpx.Client(transport=httpx.MockTransport(mock_post))
    event = mgr.create_event("repair.activated", {"action": "activate"})

    first_dispatch = mgr.dispatch_event(event, client=mock_client)
    assert len(first_dispatch) == 1
    assert calls == 1

    second_dispatch = mgr.dispatch_event(event, client=mock_client)
    assert len(second_dispatch) == 0
    assert calls == 1  # No duplicate request made!

    # 3. Bounded idempotency retention pruning
    # Insert 25 records with max_retention=10
    for i in range(25):
        storage.is_duplicate_webhook_event(f"evt_bounded_{i:03d}", max_retention=10)

    # Inspect SQLite table count
    with storage._get_session() as session:
        total = session.scalar(select(func.count(WebhookIdempotencyModel.event_id)))
        assert total == 10

        # Verify the 10 most recent remain and oldest 15 were purged
        retained = session.scalars(select(WebhookIdempotencyModel.event_id)).all()
        assert "evt_bounded_000" not in retained
        assert "evt_bounded_014" not in retained
        assert "evt_bounded_024" in retained


def test_error_sanitization_in_delivery_records():
    """Verify sensitive tokens and secrets are redacted from delivery error details."""
    secret = f"mock-subscriber-key-{secrets.token_hex(16)}"
    raw_error = (
        f"Request failed with authorization Bearer my_secret_token_abc and "
        f"secret {secret} and X-API-Key: sensitive_api_key_555"
    )

    sanitized = sanitize_error(raw_error, secret=secret)
    assert secret not in sanitized
    assert "my_secret_token_abc" not in sanitized
    assert "sensitive_api_key_555" not in sanitized
    assert "[REDACTED]" in sanitized


def test_existing_phase5a_auth_and_adapter_hash_enforcement(monkeypatch):
    """Verify Phase 5A authentication and adapter hash binding remain fully enforced."""
    key = "regression-test-key-5a"
    monkeypatch.setenv("KINTSUTECH_API_KEY", key)

    # 1. Protected webhook endpoints reject missing credentials
    assert client.post("/api/v1/webhooks/subscriptions", json={}).status_code == 401
    assert client.get("/api/v1/webhooks/subscriptions").status_code == 401
    assert client.get("/api/v1/webhooks/subscriptions/sub_nonexistent").status_code == 401

    # 2. Protected repair endpoints reject missing credentials
    assert client.post("/api/v1/repairs/activate", json={}).status_code == 401
    assert client.post("/api/v1/repairs/rollback", json={}).status_code == 401

    # 3. Validated adapter hash tampering rejected
    inc = storage_registry.create_incident("weather", title="Tamper Test", severity="low", differences=[])
    inc_id = inc["id"]

    adapter_valid = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }
    client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": adapter_valid,
            "test_cases": [{"input": {"temp_c": 15}, "expected": {"temp_c": 15, "temperature": 15}}],
        },
    )

    # Tamper with adapter fields during activation
    adapter_tampered = dict(adapter_valid)
    adapter_tampered["target_field"] = "unexpected_field"

    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": adapter_tampered,
            "authorizer": "lead",
        },
        headers={"X-API-Key": key},
    )
    assert act_resp.status_code == 400
    assert "does not match validated adapter" in act_resp.json()["detail"]
