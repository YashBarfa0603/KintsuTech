
from fastapi.testclient import TestClient

from app.main import app, observer

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
