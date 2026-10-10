
import pytest

from app.health_monitor import APIHealthMonitor


def test_new_service_has_unknown_status():
    monitor = APIHealthMonitor()

    health = monitor.get_service_health("weather")

    assert health["status"] == "unknown"
    assert health["total_calls"] == 0


def test_successful_call_is_recorded():
    monitor = APIHealthMonitor()

    monitor.record_success("weather", 120.0)
    health = monitor.get_service_health("weather")

    assert health["status"] == "healthy"
    assert health["total_calls"] == 1
    assert health["successful_calls"] == 1
    assert health["failed_calls"] == 0


def test_failed_call_is_recorded():
    monitor = APIHealthMonitor()

    monitor.record_failure("weather", 250.0, "Connection timeout")
    health = monitor.get_service_health("weather")

    assert health["status"] == "degraded"
    assert health["total_calls"] == 1
    assert health["failed_calls"] == 1
    assert health["failure_rate_percent"] == 100.0


def test_average_response_time_is_calculated():
    monitor = APIHealthMonitor()

    monitor.record_success("weather", 100.0)
    monitor.record_success("weather", 300.0)

    health = monitor.get_service_health("weather")

    assert health["average_response_time_ms"] == 200.0


def test_failure_rate_is_calculated():
    monitor = APIHealthMonitor()

    monitor.record_success("weather", 100.0)
    monitor.record_success("weather", 150.0)
    monitor.record_failure("weather", 200.0, "Server error")

    health = monitor.get_service_health("weather")

    assert health["failure_rate_percent"] == pytest.approx(33.33, abs=0.01)


def test_failure_creates_incident():
    monitor = APIHealthMonitor()

    monitor.record_failure("weather", 250.0, "Connection timeout")
    incidents = monitor.get_recent_incidents()

    assert len(incidents) == 1
    assert incidents[0]["service"] == "weather"
    assert incidents[0]["error"] == "Connection timeout"
    assert "timestamp" in incidents[0]


def test_recent_incidents_are_newest_first():
    monitor = APIHealthMonitor()

    monitor.record_failure("weather", 100.0, "First error")
    monitor.record_failure("weather", 200.0, "Second error")

    incidents = monitor.get_recent_incidents()

    assert incidents[0]["error"] == "Second error"
    assert incidents[1]["error"] == "First error"


def test_incident_history_is_limited():
    monitor = APIHealthMonitor(max_incidents=2)

    monitor.record_failure("weather", 100.0, "First error")
    monitor.record_failure("weather", 100.0, "Second error")
    monitor.record_failure("weather", 100.0, "Third error")

    incidents = monitor.get_recent_incidents()

    assert len(incidents) == 2
    assert incidents[0]["error"] == "Third error"
    assert incidents[1]["error"] == "Second error"


def test_invalid_response_time_is_rejected():
    monitor = APIHealthMonitor()

    with pytest.raises(ValueError):
        monitor.record_success("weather", -1)


def test_invalid_incident_limit_is_rejected():
    with pytest.raises(ValueError):
        APIHealthMonitor(max_incidents=0)
