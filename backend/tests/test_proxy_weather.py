from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.provider_client import (
    ProviderConnectionError,
    ProviderResponseError,
    ProviderTimeoutError,
    weather_provider_client,
)
from app.storage import storage_registry


client = TestClient(app)


def test_proxy_weather_no_active_adapter_returns_unchanged(monkeypatch):
    """
    Test Phase 3 requirement:
    - With no active adapter, the proxy returns the provider response unchanged.
    - Reports adapted: False and incident_id: None.
    """
    mock_payload = {"city": "Indore", "temperature": 30, "condition": "Sunny"}
    monkeypatch.setattr(weather_provider_client, "fetch_weather", lambda params=None: dict(mock_payload))

    # Verify weather service currently has no active adapter
    svc = storage_registry.get_service("weather")
    assert svc["active_adapter"] is None

    resp = client.get("/api/v1/proxy/weather")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "unchanged"
    assert data["adapted"] is False
    assert data["incident_id"] is None
    assert data["data"] == mock_payload
    assert data["source"] == "provider"


def test_proxy_weather_active_adapter_automatically_adapts(monkeypatch):
    """
    Test Phase 3 requirement:
    - With an active adapter, the proxy automatically maps temp_c to temperature.
    - Reports adapted: True and the responsible incident ID.
    """
    # 1. Create incident, validate repair, and activate adapter
    inc = storage_registry.create_incident(
        "weather",
        title="Breaking change: temperature renamed to temp_c",
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

    storage_registry.record_validation(inc_id, {"eligible_for_activation": True, "tests_passed": 1})
    storage_registry.activate_repair(inc_id, adapter_config, authorizer="lead_sre_operator")

    # 2. Mock provider returning the breaking/renamed payload
    provider_payload = {"city": "Indore", "temp_c": 28.5, "condition": "Sunny"}
    monkeypatch.setattr(weather_provider_client, "fetch_weather", lambda params=None: dict(provider_payload))

    # 3. Call consumer-facing proxy
    resp = client.get("/api/v1/proxy/weather")
    assert resp.status_code == 200
    res_data = resp.json()

    assert res_data["status"] == "adapted"
    assert res_data["adapted"] is True
    assert res_data["incident_id"] == inc_id
    assert res_data["data"]["temperature"] == 28.5
    assert res_data["data"]["temp_c"] == 28.5
    assert res_data["data"]["city"] == "Indore"


def test_proxy_weather_rollback_disables_automatic_adaptation(monkeypatch):
    """
    Test Phase 3 requirement:
    - Rollback disables automatic adaptation in the proxy endpoint.
    - The provider response is returned unadapted.
    """
    # Setup active adapter
    inc = storage_registry.create_incident("weather", title="Rollback proxy test", severity="low", differences=[])
    storage_registry.record_validation(inc["id"], {"eligible_for_activation": True})
    storage_registry.activate_repair(
        inc["id"],
        {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"},
        authorizer="lead_engineer",
    )

    provider_payload = {"city": "Indore", "temp_c": 28.5, "condition": "Sunny"}
    monkeypatch.setattr(weather_provider_client, "fetch_weather", lambda params=None: dict(provider_payload))

    # Roll back
    rb_resp = client.post(
        "/api/v1/repairs/rollback",
        json={"service_id": "weather", "authorizer": "incident_lead", "reason": "Proxy rollback test"},
    )
    assert rb_resp.status_code == 200
    assert rb_resp.json()["status"] == "rolled_back"

    # Now call proxy -> should NOT adapt
    proxy_resp = client.get("/api/v1/proxy/weather")
    assert proxy_resp.status_code == 200
    data = proxy_resp.json()

    assert data["status"] == "unchanged"
    assert data["adapted"] is False
    assert data["incident_id"] is None
    assert data["data"] == provider_payload
    assert "temperature" not in data["data"]


def test_proxy_weather_missing_source_field_fails_safely(monkeypatch):
    """
    Test Phase 3 requirement:
    - Missing source field is safely rejected with 422 Unprocessable Entity.
    """
    inc = storage_registry.create_incident("weather", title="Missing source test", severity="low", differences=[])
    storage_registry.record_validation(inc["id"], {"eligible_for_activation": True})
    storage_registry.activate_repair(
        inc["id"],
        {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"},
        authorizer="ops",
    )

    # Provider payload missing 'temp_c'
    bad_payload = {"city": "Indore", "condition": "Rainy"}
    monkeypatch.setattr(weather_provider_client, "fetch_weather", lambda params=None: dict(bad_payload))

    resp = client.get("/api/v1/proxy/weather")
    assert resp.status_code == 422
    assert "missing" in resp.json()["detail"].lower()


def test_proxy_weather_conflicting_target_field_fails_safely(monkeypatch):
    """
    Test Phase 3 requirement:
    - Conflicting target field is safely rejected with 409 Conflict.
    """
    inc = storage_registry.create_incident("weather", title="Conflict test", severity="low", differences=[])
    storage_registry.record_validation(inc["id"], {"eligible_for_activation": True})
    storage_registry.activate_repair(
        inc["id"],
        {"operation": "copy_field", "source_field": "temp_c", "target_field": "temperature"},
        authorizer="ops",
    )

    # Provider payload already has conflicting 'temperature' with different value
    conflict_payload = {"city": "Indore", "temp_c": 20.0, "temperature": 35.0}
    monkeypatch.setattr(weather_provider_client, "fetch_weather", lambda params=None: dict(conflict_payload))

    resp = client.get("/api/v1/proxy/weather")
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"].lower()


def test_proxy_weather_provider_timeout_produces_504(monkeypatch):
    """
    Test Phase 3 requirement:
    - Provider request timeout produces controlled HTTP 504 Gateway Timeout.
    """
    def raise_timeout(params=None):
        raise ProviderTimeoutError("Weather provider request timed out.")

    monkeypatch.setattr(weather_provider_client, "fetch_weather", raise_timeout)

    resp = client.get("/api/v1/proxy/weather")
    assert resp.status_code == 504
    assert "timed out" in resp.json()["detail"].lower()


def test_proxy_weather_provider_connection_error_produces_502(monkeypatch):
    """
    Test Phase 3 requirement:
    - Provider connection failure produces controlled HTTP 502 Bad Gateway.
    """
    def raise_connection_error(params=None):
        raise ProviderConnectionError("Could not connect to weather provider.")

    monkeypatch.setattr(weather_provider_client, "fetch_weather", raise_connection_error)

    resp = client.get("/api/v1/proxy/weather")
    assert resp.status_code == 502
    assert "connect" in resp.json()["detail"].lower()


def test_proxy_weather_provider_invalid_json_produces_502(monkeypatch):
    """
    Test Phase 3 requirement:
    - Provider invalid JSON or HTTP error produces controlled HTTP 502 Bad Gateway.
    """
    def raise_response_error(params=None):
        raise ProviderResponseError("Weather provider returned invalid JSON payload.")

    monkeypatch.setattr(weather_provider_client, "fetch_weather", raise_response_error)

    resp = client.get("/api/v1/proxy/weather")
    assert resp.status_code == 502
    assert "invalid" in resp.json()["detail"].lower()


def test_raw_mock_weather_endpoint_remains_available():
    """
    Test Phase 3 requirement:
    - Raw mock endpoint /api/v1/mock/weather remains available for testing and inspection.
    """
    resp_v1 = client.get("/api/v1/mock/weather?version=1")
    assert resp_v1.status_code == 200
    assert resp_v1.json()["temperature"] == 30

    resp_v2 = client.get("/api/v1/mock/weather?version=2")
    assert resp_v2.status_code == 200
    assert resp_v2.json()["temperature"] == "30"

    resp_renamed = client.get("/api/v1/mock/weather?schema=temp_c")
    assert resp_renamed.status_code == 200
    assert "temp_c" in resp_renamed.json()
    assert "temperature" not in resp_renamed.json()
