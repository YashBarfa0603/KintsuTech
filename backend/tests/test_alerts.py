"""
Comprehensive tests for KintsuTech alert lifecycle, storage, APIs,
authorization, event integration, background scheduler, and delivery consent.
"""

from datetime import datetime, timedelta, timezone
import json
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from app.auth import AuthenticatedUser, get_current_user
from app.alerts import (
    AlertService,
    is_in_quiet_hours,
    resolve_recipient_user_id,
    warrants_alert,
)
from app.main import app
from app.scheduler import AlertScheduler
from app.storage import (
    StorageRegistry,
    storage_registry,
    validate_alert_transition,
)

client = TestClient(app)


# ============================================================================
# A. Storage Tests
# ============================================================================

def test_alert_creation_succeeds():
    alert = storage_registry.create_alert(
        user_id="user_1",
        title="Test Alert",
        message="Test Message",
        severity="high",
    )
    assert alert["id"].startswith("alt_")
    assert alert["user_id"] == "user_1"
    assert alert["title"] == "Test Alert"
    assert alert["message"] == "Test Message"
    assert alert["severity"] == "high"
    assert alert["status"] == "pending"
    assert alert["escalation_level"] == 0
    assert alert["attempt_count"] == 0


def test_alert_ids_are_unique():
    a1 = storage_registry.create_alert(user_id="u1", title="A1", message="M1")
    a2 = storage_registry.create_alert(user_id="u1", title="A2", message="M2")
    assert a1["id"] != a2["id"]


def test_alert_retrieval_succeeds_and_unknown_returns_none():
    alert = storage_registry.create_alert(user_id="u1", title="A", message="M")
    fetched = storage_registry.get_alert(alert["id"])
    assert fetched is not None
    assert fetched["id"] == alert["id"]

    assert storage_registry.get_alert("alt_non_existent") is None


def test_listing_is_scoped_to_correct_user():
    storage_registry.create_alert(user_id="u1", title="A1", message="M1")
    storage_registry.create_alert(user_id="u2", title="A2", message="M2")

    u1_alerts = storage_registry.list_alerts(user_id="u1")
    u2_alerts = storage_registry.list_alerts(user_id="u2")

    assert len(u1_alerts) == 1
    assert u1_alerts[0]["title"] == "A1"
    assert len(u2_alerts) == 1
    assert u2_alerts[0]["title"] == "A2"


def test_status_severity_and_incident_filtering():
    storage_registry.create_alert(
        user_id="u1", title="A1", message="M1", severity="critical", incident_id="INC-001"
    )
    storage_registry.create_alert(
        user_id="u1", title="A2", message="M2", severity="low", incident_id="INC-002"
    )

    crit = storage_registry.list_alerts(user_id="u1", severity="critical")
    assert len(crit) == 1
    assert crit[0]["title"] == "A1"

    inc = storage_registry.list_alerts(user_id="u1", incident_id="INC-002")
    assert len(inc) == 1
    assert inc[0]["title"] == "A2"

    pend = storage_registry.list_alerts(user_id="u1", status="pending")
    assert len(pend) == 2


def test_acknowledgment_updates_status_and_timestamp():
    alert = storage_registry.create_alert(user_id="u1", title="A", message="M")
    acked = storage_registry.acknowledge_alert(alert["id"], user_id="u1", note="Reviewing now")
    assert acked["status"] == "acknowledged"
    assert acked["acknowledged_at"] is not None


def test_repeated_acknowledgment_is_idempotent():
    alert = storage_registry.create_alert(user_id="u1", title="A", message="M")
    ack1 = storage_registry.acknowledge_alert(alert["id"], user_id="u1")
    ack2 = storage_registry.acknowledge_alert(alert["id"], user_id="u1")
    assert ack1["status"] == "acknowledged"
    assert ack2["status"] == "acknowledged"
    assert ack1["acknowledged_at"] == ack2["acknowledged_at"]


def test_resolution_and_cancellation():
    alert1 = storage_registry.create_alert(user_id="u1", title="A1", message="M1")
    resolved = storage_registry.resolve_alert(alert1["id"], user_id="u1", note="Fixed")
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None

    alert2 = storage_registry.create_alert(user_id="u1", title="A2", message="M2")
    cancelled = storage_registry.cancel_alert(alert2["id"], user_id="u1", reason="False positive")
    assert cancelled["status"] == "cancelled"


def test_duplicate_idempotency_keys_do_not_create_duplicates():
    a1 = storage_registry.create_alert(
        user_id="u1",
        title="Event 1",
        message="Msg 1",
        idempotency_key="idemp_key_100",
    )
    a2 = storage_registry.create_alert(
        user_id="u1",
        title="Event 1 Duplicate",
        message="Msg 1 Duplicate",
        idempotency_key="idemp_key_100",
    )
    assert a1["id"] == a2["id"]
    assert a1["title"] == a2["title"]


def test_distinct_event_keys_create_distinct_alerts():
    a1 = storage_registry.create_alert(user_id="u1", title="A1", message="M1", idempotency_key="key_1")
    a2 = storage_registry.create_alert(user_id="u1", title="A2", message="M2", idempotency_key="key_2")
    assert a1["id"] != a2["id"]


def test_invalid_status_transitions_are_rejected():
    with pytest.raises(ValueError):
        validate_alert_transition("resolved", "pending")
    with pytest.raises(ValueError):
        validate_alert_transition("cancelled", "delivering")
    with pytest.raises(ValueError):
        validate_alert_transition("acknowledged", "escalated")


def test_delivery_attempts_and_history_persist():
    alert = storage_registry.create_alert(user_id="u1", title="A", message="M")
    deliv = storage_registry.record_delivery_attempt(
        alert["id"],
        channel="in_app",
        status="success",
        details={"dest": "user_feed"},
    )
    assert deliv["channel"] == "in_app"
    assert deliv["status"] == "success"

    history = storage_registry.get_alert_history(alert["id"], user_id="u1")
    assert len(history) == 1
    assert history[0]["channel"] == "in_app"


def test_existing_data_survives_normal_restart():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_restart.db")
        sr1 = StorageRegistry(db_url=f"sqlite:///{db_path}")
        alert = sr1.create_alert(user_id="u_restart", title="Restart Test", message="Survives restart")
        alert_id = alert["id"]
        sr1.close()

        # Reopen with new instance on same file
        sr2 = StorageRegistry(db_url=f"sqlite:///{db_path}")
        recovered = sr2.get_alert(alert_id)
        assert recovered is not None
        assert recovered["title"] == "Restart Test"
        sr2.close()


# ============================================================================
# B. API and Authorization Tests
# ============================================================================

def test_unauthenticated_requests_are_rejected():
    prev_override = app.dependency_overrides.pop(get_current_user, None)
    try:
        res = client.get("/api/v1/alerts")
        assert res.status_code == 401
    finally:
        if prev_override:
            app.dependency_overrides[get_current_user] = prev_override


def test_authenticated_user_can_create_and_list_alerts():
    u = AuthenticatedUser(id="user_api_test", email="api@kintsu.io")
    app.dependency_overrides[get_current_user] = lambda: u

    create_res = client.post(
        "/api/v1/alerts",
        json={"title": "API Alert", "message": "API Created", "severity": "high"},
    )
    assert create_res.status_code == 201
    alert_id = create_res.json()["id"]

    list_res = client.get("/api/v1/alerts")
    assert list_res.status_code == 200
    items = list_res.json()
    assert any(a["id"] == alert_id for a in items)


def test_user_cannot_retrieve_acknowledge_or_resolve_another_users_alert():
    user1 = AuthenticatedUser(id="user_owner", email="owner@kintsu.io")
    user2 = AuthenticatedUser(id="user_attacker", email="attacker@kintsu.io")

    app.dependency_overrides[get_current_user] = lambda: user1
    alert = storage_registry.create_alert(user_id="user_owner", title="Secret", message="Owner Only")

    # Switch to user 2
    app.dependency_overrides[get_current_user] = lambda: user2

    get_res = client.get(f"/api/v1/alerts/{alert['id']}")
    assert get_res.status_code == 404

    ack_res = client.post(f"/api/v1/alerts/{alert['id']}/acknowledge")
    assert ack_res.status_code == 404

    res_res = client.post(f"/api/v1/alerts/{alert['id']}/resolve")
    assert res_res.status_code == 404


def test_invalid_request_bodies_return_validation_errors():
    u = AuthenticatedUser(id="user_val", email="val@kintsu.io")
    app.dependency_overrides[get_current_user] = lambda: u

    res = client.post("/api/v1/alerts", json={})
    assert res.status_code == 422


def test_preferences_can_be_read_and_updated():
    u = AuthenticatedUser(id="user_pref", email="pref@kintsu.io")
    app.dependency_overrides[get_current_user] = lambda: u

    read_res = client.get("/api/v1/alert-preferences")
    assert read_res.status_code == 200
    assert read_res.json()["min_severity"] == "medium"

    update_res = client.put(
        "/api/v1/alert-preferences",
        json={
            "min_severity": "critical",
            "quiet_hours_enabled": True,
            "quiet_hours_start": "23:00",
            "quiet_hours_end": "07:00",
        },
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["min_severity"] == "critical"
    assert updated["quiet_hours_enabled"] is True


def test_openapi_schema_includes_alert_routes():
    res = client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    paths = schema.get("paths", {})
    assert "/api/v1/alerts" in paths
    assert "/api/v1/alerts/{alert_id}" in paths
    assert "/api/v1/alerts/{alert_id}/acknowledge" in paths
    assert "/api/v1/alerts/{alert_id}/resolve" in paths
    assert "/api/v1/alert-preferences" in paths
    assert "/api/v1/voice/status" in paths


# ============================================================================
# C. Event Integration Tests
# ============================================================================

def test_important_timeline_change_creates_alert():
    service = AlertService(storage_registry)
    incident = {
        "id": "INC-101",
        "service_id": "weather",
        "title": "Severe drift detected",
        "severity": "critical",
        "differences": [{"path": "temp", "breaking": True}],
    }
    alert = service.handle_incident_event(incident, recipient_user_id="user_event")
    assert alert is not None
    assert alert["incident_id"] == "INC-101"
    assert alert["severity"] == "critical"


def test_insignificant_change_does_not_create_alert():
    service = AlertService(storage_registry)
    # Set user preference to high
    storage_registry.update_alert_preferences("user_quiet", {"min_severity": "high"})
    incident = {
        "id": "INC-102",
        "service_id": "weather",
        "title": "Minor doc change",
        "severity": "low",
        "differences": [{"path": "description", "breaking": False}],
    }
    alert = service.handle_incident_event(incident, recipient_user_id="user_quiet")
    assert alert is None


def test_replayed_events_do_not_create_duplicate_alerts():
    service = AlertService(storage_registry)
    incident = {
        "id": "INC-103",
        "service_id": "weather",
        "title": "Schema breaking change",
        "severity": "high",
        "differences": [{"path": "units", "breaking": True}],
    }
    a1 = service.handle_incident_event(incident, recipient_user_id="user_replay")
    a2 = service.handle_incident_event(incident, recipient_user_id="user_replay")
    assert a1 is not None and a2 is not None
    assert a1["id"] == a2["id"]


# ============================================================================
# D. Scheduler Tests
# ============================================================================

def test_alert_is_processed_when_due_and_not_before():
    import asyncio

    async def _test():
        scheduler = AlertScheduler(storage_registry)
        now = datetime.now(timezone.utc)
        future_due = (now + timedelta(seconds=600)).isoformat()
        past_due = (now - timedelta(seconds=10)).isoformat()

        # Alert not due
        a_future = storage_registry.create_alert(
            user_id="u_sched",
            title="Future Alert",
            message="Not due yet",
            due_at=future_due,
            next_escalation_at=future_due,
        )

        # Poll before due
        res_early = await scheduler.poll_once(now_iso=now.isoformat())
        assert a_future["id"] not in [a["id"] for a in storage_registry.list_alerts("u_sched", status="escalated")]

        # Alert past due
        a_past = storage_registry.create_alert(
            user_id="u_sched",
            title="Overdue Alert",
            message="Should escalate",
            due_at=past_due,
            next_escalation_at=past_due,
        )
        # Mark a_past delivered so it's waiting for ack
        storage_registry.record_delivery_attempt(a_past["id"], channel="in_app", status="success")

        res_late = await scheduler.poll_once(now_iso=now.isoformat())
        updated_past = storage_registry.get_alert(a_past["id"])
        assert updated_past["status"] == "escalated"
        assert updated_past["escalation_level"] >= 1

    asyncio.run(_test())


def test_acknowledged_and_resolved_alerts_are_not_escalated():
    import asyncio

    async def _test():
        scheduler = AlertScheduler(storage_registry)
        now = datetime.now(timezone.utc)
        past_due = (now - timedelta(seconds=50)).isoformat()

        a1 = storage_registry.create_alert(
            user_id="u_stop",
            title="Acked Alert",
            message="M",
            due_at=past_due,
            next_escalation_at=past_due,
        )
        storage_registry.acknowledge_alert(a1["id"], user_id="u_stop")

        a2 = storage_registry.create_alert(
            user_id="u_stop",
            title="Resolved Alert",
            message="M",
            due_at=past_due,
            next_escalation_at=past_due,
        )
        storage_registry.resolve_alert(a2["id"], user_id="u_stop")

        await scheduler.poll_once(now_iso=now.isoformat())

        assert storage_registry.get_alert(a1["id"])["status"] == "acknowledged"
        assert storage_registry.get_alert(a2["id"])["status"] == "resolved"

    asyncio.run(_test())


def test_concurrent_workers_do_not_double_claim():
    now_iso = datetime.now(timezone.utc).isoformat()
    a = storage_registry.create_alert(user_id="u_conc", title="Claim Test", message="Lock test")

    claim1 = storage_registry.claim_due_alerts(lock_duration_seconds=30, limit=10, now_iso=now_iso)
    claim2 = storage_registry.claim_due_alerts(lock_duration_seconds=30, limit=10, now_iso=now_iso)

    claimed_ids_1 = [x["id"] for x in claim1]
    claimed_ids_2 = [x["id"] for x in claim2]

    assert a["id"] in claimed_ids_1
    assert a["id"] not in claimed_ids_2



def test_quiet_hours_calculation_and_timezones():
    pref = {
        "quiet_hours_enabled": True,
        "quiet_hours_start": "22:00",
        "quiet_hours_end": "08:00",
        "timezone": "UTC",
    }
    # 23:30 UTC -> inside quiet hours
    t1 = datetime(2026, 10, 11, 23, 30, tzinfo=timezone.utc)
    assert is_in_quiet_hours(pref, t1) is True

    # 12:00 UTC -> outside quiet hours
    t2 = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)
    assert is_in_quiet_hours(pref, t2) is False


# ============================================================================
# F. Delivery and Consent Tests
# ============================================================================

def test_telephony_disabled_by_default_and_unverified_rejected():
    service = AlertService(storage_registry)
    alert = storage_registry.create_alert(
        user_id="u_phone",
        title="Phone Alert",
        message="Call Me",
        delivery_channel="phone",
    )
    # Without phone consent/number, delivery must fail safely
    attempt = service.deliver_alert(alert, channel="phone")
    assert attempt["status"] == "failed"
    assert "Telephony is disabled" in attempt["error"] or "consent" in attempt["error"]
