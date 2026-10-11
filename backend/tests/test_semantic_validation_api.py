import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.provider_client import weather_provider_client
from app.storage import storage_registry
from consumer_contracts import contract_registry


client = TestClient(app)


def test_api_validate_repair_with_consumer_contracts():
    """Verify POST /api/v1/repairs/validate evaluates consumer contracts."""
    inc = storage_registry.create_incident("weather", title="Contract Test Incident", severity="low", differences=[])
    inc_id = inc["id"]

    contract = {
        "consumer_id": "mobile_app",
        "service_id": "weather",
        "version": "1.0",
        "mandatory": True,
        "fields": {
            "temperature": {
                "type": "number",
                "required": True,
                "nullable": False,
                "minimum": 0.0,
                "maximum": 50.0,
            },
        },
    }

    adapter = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    # Case A: Passes test cases and contract constraints
    resp_pass = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": adapter,
            "test_cases": [{"input": {"temp_c": 25.0}, "expected": {"temp_c": 25.0, "temperature": 25.0}}],
            "consumer_contracts": [contract],
        },
    )
    assert resp_pass.status_code == 200
    data_pass = resp_pass.json()["validation"]
    assert data_pass["eligible_for_activation"] is True
    assert data_pass["contracts_passed"] == 1
    assert data_pass["contracts_failed"] == 0

    # Case B: Violates contract maximum (temperature 75.0 > 50.0)
    resp_fail = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": adapter,
            "test_cases": [{"input": {"temp_c": 75.0}, "expected": {"temp_c": 75.0, "temperature": 75.0}}],
            "consumer_contracts": [contract],
        },
    )
    assert resp_fail.status_code == 200
    data_fail = resp_fail.json()["validation"]
    assert data_fail["eligible_for_activation"] is False
    assert data_fail["contracts_failed"] == 1
    assert any("exceeds maximum" in err for err in data_fail["errors"])


def test_api_convert_units_validation_activation_and_proxy_adaptation(monkeypatch):
    """Verify convert_units end-to-end: validation, authorized activation, and proxy adaptation."""
    test_key = "phase5c-test-key"
    monkeypatch.setenv("KINTSUTECH_API_KEY", test_key)
    headers = {"X-API-Key": test_key}

    inc = storage_registry.create_incident("weather", title="Unit Conversion Incident", severity="medium", differences=[])
    inc_id = inc["id"]

    # Celsius to Fahrenheit conversion: F = C * 1.8 + 32.0
    adapter = {
        "operation": "convert_units",
        "source_field": "temp_c",
        "target_field": "temperature",
        "scale": 1.8,
        "offset": 32.0,
        "semantics_confirmed": True,
    }

    # 1. Validate convert_units adapter
    val_resp = client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": adapter,
            "test_cases": [
                {"input": {"temp_c": 0.0}, "expected": {"temp_c": 0.0, "temperature": 32.0}},
                {"input": {"temp_c": 20.0}, "expected": {"temp_c": 20.0, "temperature": 68.0}},
            ],
        },
    )
    assert val_resp.status_code == 200
    assert val_resp.json()["validation"]["eligible_for_activation"] is True

    # 2. Authorized activation
    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": adapter,
            "authorizer": "thermal_engineer",
            "note": "Celsius to Fahrenheit adaptation",
        },
        headers=headers,
    )
    assert act_resp.status_code == 200
    assert act_resp.json()["status"] == "activated"

    # 3. Upstream proxy returns converted Fahrenheit output
    mock_provider_payload = {"city": "Indore", "temp_c": 20.0, "condition": "Sunny"}
    monkeypatch.setattr(weather_provider_client, "fetch_weather", lambda params=None: dict(mock_provider_payload))

    proxy_resp = client.get("/api/v1/proxy/weather")
    assert proxy_resp.status_code == 200
    proxy_data = proxy_resp.json()
    assert proxy_data["status"] == "adapted"
    assert proxy_data["adapted"] is True
    assert proxy_data["data"]["temp_c"] == 20.0
    assert proxy_data["data"]["temperature"] == 68.0


def test_api_activation_rejected_on_tampered_adapter_hash(monkeypatch):
    """Verify that altering adapter parameters after validation causes activation failure."""
    test_key = "phase5c-tamper-key"
    monkeypatch.setenv("KINTSUTECH_API_KEY", test_key)
    headers = {"X-API-Key": test_key}

    inc = storage_registry.create_incident("weather", title="Tamper Hash Test", severity="low", differences=[])
    inc_id = inc["id"]

    valid_adapter = {
        "operation": "convert_units",
        "source_field": "temp_c",
        "target_field": "temperature",
        "scale": 1.8,
        "offset": 32.0,
        "semantics_confirmed": True,
    }

    # Validate with scale=1.8
    client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": valid_adapter,
            "test_cases": [{"input": {"temp_c": 0.0}, "expected": {"temp_c": 0.0, "temperature": 32.0}}],
        },
    )

    # Tamper: change scale to 1.5 during activation
    tampered_adapter = dict(valid_adapter)
    tampered_adapter["scale"] = 1.5

    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": tampered_adapter,
            "authorizer": "lead",
        },
        headers=headers,
    )
    assert act_resp.status_code == 400
    assert "Requested adapter configuration does not match validated adapter" in act_resp.json()["detail"]


def test_api_activation_rejected_on_contract_version_mismatch(monkeypatch):
    """Verify activation fails if requested contract version differs from validated version."""
    test_key = "phase5c-version-key"
    monkeypatch.setenv("KINTSUTECH_API_KEY", test_key)
    headers = {"X-API-Key": test_key}

    inc = storage_registry.create_incident("weather", title="Version Binding Test", severity="low", differences=[])
    inc_id = inc["id"]

    adapter = {
        "operation": "copy_field",
        "source_field": "temp_c",
        "target_field": "temperature",
        "semantics_confirmed": True,
    }

    contract_v1 = {
        "consumer_id": "mobile_app",
        "service_id": "weather",
        "version": "1.0",
        "mandatory": True,
        "fields": {"temperature": "number"},
    }

    # Validate against version 1.0
    client.post(
        "/api/v1/repairs/validate",
        json={
            "incident_id": inc_id,
            "adapter": adapter,
            "test_cases": [{"input": {"temp_c": 20.0}, "expected": {"temp_c": 20.0, "temperature": 20.0}}],
            "consumer_contracts": [contract_v1],
        },
    )

    # Attempt activation with mismatched contract_version '2.0'
    act_resp = client.post(
        "/api/v1/repairs/activate",
        json={
            "incident_id": inc_id,
            "adapter": adapter,
            "authorizer": "lead",
            "contract_version": "2.0",
        },
        headers=headers,
    )
    assert act_resp.status_code == 400
    assert "Requested contract version '2.0' does not match validated contract version '1.0'" in act_resp.json()["detail"]


def test_api_consumer_contracts_endpoints(monkeypatch):
    """Verify GET and POST endpoints for downstream consumer contracts."""
    test_key = "phase5c-contracts-key"
    monkeypatch.setenv("KINTSUTECH_API_KEY", test_key)

    # 1. Unauthenticated registration rejected
    unauth_resp = client.post(
        "/api/v1/contracts",
        json={
            "consumer_id": "frontend_portal",
            "service_id": "products",
            "version": "1.0",
            "fields": {"price": "number"},
        },
    )
    assert unauth_resp.status_code == 401

    # 2. Authenticated registration succeeds
    auth_resp = client.post(
        "/api/v1/contracts",
        json={
            "consumer_id": "frontend_portal",
            "service_id": "products",
            "version": "1.0",
            "fields": {"price": {"type": "number", "minimum": 0.0}},
            "description": "Storefront product contract",
        },
        headers={"X-API-Key": test_key},
    )
    assert auth_resp.status_code == 200
    assert auth_resp.json()["status"] == "registered"

    # 3. List contracts filtered by service
    list_resp = client.get("/api/v1/contracts?service_id=products")
    assert list_resp.status_code == 200
    contracts = list_resp.json()["contracts"]
    assert any(c["consumer_id"] == "frontend_portal" for c in contracts)
