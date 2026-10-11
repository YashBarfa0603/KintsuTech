import pytest
from fastapi.testclient import TestClient

from app.main import app, health_monitor
from app.storage import storage_registry


@pytest.fixture
def client():
    return TestClient(app)


def test_agent_chat_what_is_kintsutech(client):
    response = client.post("/api/v1/agent/chat", json={"message": "What is KintsuTech?"})
    assert response.status_code == 200
    data = response.json()
    assert "KintsuTech" in data["response"]
    assert "Kintsugi" in data["response"]
    assert "Detect" in data["response"]
    assert "system_knowledge" in data["tools_used"]
    assert len(data["suggestions"]) > 0


def test_agent_chat_weather_api_failing(client):
    # Test query when healthy
    response = client.post("/api/v1/agent/chat", json={"message": "Why is my weather API failing?"})
    assert response.status_code == 200
    data = response.json()
    assert "get_service_status" in data["tools_used"]
    assert "Weather" in data["response"]
    assert "evidence" in data
    assert "service_status" in data["evidence"]


def test_agent_chat_weather_with_failure_record(client):
    # Record a failure in health monitor to test failure explanation
    health_monitor.record_failure("weather", 150.0, "ProviderTimeoutError: Upstream connection timed out")
    response = client.post("/api/v1/agent/chat", json={"message": "Why is my weather API failing?"})
    assert response.status_code == 200
    data = response.json()
    assert "failed calls" in data["response"].lower() or "failure" in data["response"].lower()
    assert "ProviderTimeoutError" in data["response"] or "timeout" in data["response"].lower()


def test_agent_chat_detected_changes(client):
    response = client.post("/api/v1/agent/chat", json={"message": "What API changes were detected?"})
    assert response.status_code == 200
    data = response.json()
    assert "list_incidents" in data["tools_used"]
    assert "get_service_baseline" in data["tools_used"]
    assert "baseline" in data["response"].lower()


def test_agent_chat_latest_incidents(client):
    response = client.post("/api/v1/agent/chat", json={"message": "Show me the latest incidents."})
    assert response.status_code == 200
    data = response.json()
    assert "list_incidents" in data["tools_used"]
    assert "incident" in data["response"].lower()


def test_agent_chat_affected_consumers(client):
    response = client.post("/api/v1/agent/chat", json={"message": "Which consumers are affected by this API change?"})
    assert response.status_code == 200
    data = response.json()
    assert "calculate_dependency_impact" in data["tools_used"]
    assert "impact" in data["evidence"]
    assert "Consumers" in data["response"] or "Impact" in data["response"]


def test_agent_chat_explain_repair(client):
    response = client.post("/api/v1/agent/chat", json={"message": "Explain the proposed repair."})
    assert response.status_code == 200
    data = response.json()
    assert "explain_repair" in data["tools_used"]
    assert "repair" in data["response"].lower() or "adapter" in data["response"].lower()


def test_agent_chat_validation_status(client):
    response = client.post("/api/v1/agent/chat", json={"message": "Has this repair passed validation?"})
    assert response.status_code == 200
    data = response.json()
    assert "get_incident_evidence" in data["tools_used"]
    assert "validation" in data["response"].lower()


def test_agent_chat_rollback_consequences(client):
    response = client.post("/api/v1/agent/chat", json={"message": "What happens if I roll back the repair?"})
    assert response.status_code == 200
    data = response.json()
    assert "get_rollback_info" in data["tools_used"]
    assert "rollback" in data["response"].lower()
    assert "Audit" in data["response"] or "audit" in data["response"]


def test_agent_chat_system_health(client):
    response = client.post("/api/v1/agent/chat", json={"message": "Summarize the current system health."})
    assert response.status_code == 200
    data = response.json()
    assert "get_system_health" in data["tools_used"]
    assert "Platform Status" in data["response"]
    assert "health" in data["evidence"]


def test_agent_chat_empty_message_validation(client):
    response = client.post("/api/v1/agent/chat", json={"message": ""})
    assert response.status_code == 422


def test_agent_chat_whitespace_message_validation(client):
    response = client.post("/api/v1/agent/chat", json={"message": "    "})
    assert response.status_code == 422


def test_agent_chat_oversized_message_validation(client):
    oversized = "a" * 2001
    response = client.post("/api/v1/agent/chat", json={"message": oversized})
    assert response.status_code == 422
