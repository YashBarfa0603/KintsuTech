
from fastapi.testclient import TestClient

from app.main import app, observer

from unittest.mock import patch


def test_ai_analyze_endpoint_calls_workflow():
    expected_result = {
        "change_report": {
            "has_changes": True,
            "total_change_count": 1,
            "changes": [
                {
                    "source": "structural",
                    "kind": "field_removed",
                    "path": "temperature",
                }
            ],
        },
        "repair_workflow": {
            "status": "pending_review",
            "proposal": None,
            "validation": {
                "eligible_for_activation": False,
                "status": "pending_review",
            },
        },
    }

    with patch(
        "app.main.run_change_workflow",
        return_value=expected_result,
    ) as mocked_workflow:
        response = client.post(
            "/api/v1/ai/analyze",
            json={
                "baseline": {"temperature": 30},
                "current": {"temp_c": 30},
            },
        )

    assert response.status_code == 200
    assert response.json() == expected_result

    mocked_workflow.assert_called_once_with(
        baseline={"temperature": 30},
        current={"temp_c": 30},
        behavior_report=None,
        text_diff=None,
        pagination_reports=None,
        rate_limit_reports=None,
    )


def test_ai_analyze_endpoint_rejects_invalid_request():
    response = client.post(
        "/api/v1/ai/analyze",
        json={"baseline": {"temperature": 30}},
    )

    assert response.status_code == 422


def test_ai_analyze_endpoint_handles_workflow_failure():
    with patch(
        "app.main.run_change_workflow",
        side_effect=RuntimeError("Simulated workflow failure"),
    ):
        response = client.post(
            "/api/v1/ai/analyze",
            json={
                "baseline": {"temperature": 30},
                "current": {"temp_c": 30},
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "AI analysis is temporarily unavailable."
    )

client = TestClient(app)


def setup_function():
    observer._baselines.clear()


def test_health_endpoint():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_mock_weather_versions():
    original = client.get("/api/v1/mock/weather?version=1")
    changed = client.get("/api/v1/mock/weather?version=2")

    assert original.status_code == 200
    assert original.json()["temperature"] == 30
    assert changed.status_code == 200
    assert changed.json()["temperature"] == "30"


def test_observer_detects_weather_changes():
    baseline = client.post("/api/v1/observe/weather?version=1")
    changed = client.post("/api/v1/observe/weather?version=2")

    assert baseline.status_code == 200
    assert baseline.json()["observation"]["has_changes"] is False

    result = changed.json()["observation"]

    assert result["has_changes"] is True
    assert result["change_count"] == 2
    assert result["breaking_change_count"] == 1


def test_invalid_weather_version_returns_400():
    response = client.get("/api/v1/mock/weather?version=3")

    assert response.status_code == 400


def test_resilience_endpoint_success():
    response = client.get("/api/v1/resilience/weather?mode=success")

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["data"]["city"] == "Indore"


def test_resilience_endpoint_failure():
    response = client.get(
        "/api/v1/resilience/weather?mode=timeout&max_attempts=2"
    )

    assert response.status_code == 503
    assert "failed after retries" in response.json()["detail"]


def test_resilience_endpoint_invalid_mode():
    response = client.get("/api/v1/resilience/weather?mode=invalid")

    assert response.status_code == 400


def test_monitor_health_endpoint():
    # Record a successful weather API call.
    success = client.get("/api/v1/resilience/weather?mode=success")
    assert success.status_code == 200

    response = client.get("/api/v1/monitor/health")

    assert response.status_code == 200

    data = response.json()
    assert data["service"] == "weather"
    assert data["total_calls"] >= 1
    assert data["successful_calls"] >= 1
    assert "failure_rate_percent" in data
    assert "average_response_time_ms" in data


def test_monitor_incidents_endpoint():
    # Trigger a simulated failure to create an incident.
    failure = client.get(
        "/api/v1/resilience/weather?mode=timeout&max_attempts=1"
    )
    assert failure.status_code == 503

    response = client.get("/api/v1/monitor/incidents")

    assert response.status_code == 200

    data = response.json()
    assert data["service"] == "weather"
    assert data["incident_count"] >= 1
    assert len(data["incidents"]) >= 1
    assert data["incidents"][0]["error"]
    assert data["incidents"][0]["timestamp"]


def test_analyze_changes_endpoint():
    response = client.post(
        "/api/v1/analyze/changes",
        json={
            "baseline": {
                "city": "Indore",
                "temperature": 30,
                "condition": "Sunny",
            },
            "current": {
                "city": "Indore",
                "temperature": "30",
                "condition": "Sunny",
                "humidity": 45,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["has_changes"] is True
    assert data["overall_risk"] == "high"
    assert data["change_count"] == 2
    assert data["severity_counts"]["high"] == 1
    assert data["severity_counts"]["low"] == 1


def test_analyze_changes_endpoint_no_changes():
    response = client.post(
        "/api/v1/analyze/changes",
        json={
            "baseline": {
                "city": "Indore",
                "temperature": 30,
            },
            "current": {
                "city": "Indore",
                "temperature": 30,
            },
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["has_changes"] is False
    assert data["overall_risk"] == "none"
    assert data["change_count"] == 0

def test_ai_adapter_endpoint_returns_expected_contract():
    from unittest.mock import patch

    with patch(
        "app.main.analyze_with_adapter",
        return_value={
            "summary": "Detected 1 API change finding(s).",
            "risk_level": "high",
            "recommendations": ["Review affected consumers."],
            "repair_proposal": {
                "validation_status": "pending_review",
                "eligible_for_activation": False,
            },
        },
    ) as mocked_adapter:
        response = client.post(
            "/api/v1/analyze/changes/ai",
            json={
                "baseline": {"temperature": 30},
                "current": {"temp_c": 30},
            },
        )

    assert response.status_code == 200

    data = response.json()
    assert data["risk_level"] == "high"
    assert data["recommendations"]
    assert data["repair_proposal"]["eligible_for_activation"] is False

    mocked_adapter.assert_called_once()