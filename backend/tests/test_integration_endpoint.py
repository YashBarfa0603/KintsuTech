
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_integration_change_analysis_detects_type_change():
    response = client.post(
        "/api/v1/integrations/change-analysis",
        json={
            "service": "weather",
            "baseline": {"temperature": 30},
            "current": {"temperature": "30"},
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["service"] == "weather"
    assert data["has_changes"] is True
    assert data["overall_risk"] == "high"
    assert data["change_count"] == 1
    assert data["changes"][0]["kind"] == "type_changed"
    assert data["changes"][0]["severity"] == "high"


def test_integration_change_analysis_with_no_changes():
    response = client.post(
        "/api/v1/integrations/change-analysis",
        json={
            "service": "weather",
            "baseline": {"temperature": 30},
            "current": {"temperature": 30},
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert data["has_changes"] is False
    assert data["overall_risk"] == "none"
    assert data["change_count"] == 0


def test_integration_change_analysis_rejects_extra_request_fields():
    response = client.post(
        "/api/v1/integrations/change-analysis",
        json={
            "service": "weather",
            "baseline": {},
            "current": {},
            "unexpected": "not allowed",
        },
    )

    assert response.status_code == 422
