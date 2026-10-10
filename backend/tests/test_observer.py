
from app.observer import APIObserver


def test_first_response_creates_baseline():
    observer = APIObserver()

    result = observer.capture(
        "weather",
        {"city": "Indore", "temperature": 28},
    )

    assert result["baseline_created"] is True
    assert result["has_changes"] is False


def test_changed_response_is_detected():
    observer = APIObserver()
    observer.capture("weather", {"temperature": 28})

    result = observer.capture("weather", {"temperature": "28"})

    assert result["has_changes"] is True
    assert result["breaking_change_count"] == 1


def test_original_baseline_is_preserved():
    observer = APIObserver()
    observer.capture("weather", {"temperature": 28})

    observer.capture("weather", {"temp_c": 28})
    result = observer.capture("weather", {"temperature": 29})

    assert result["has_changes"] is False


def test_services_have_independent_baselines():
    observer = APIObserver()
    observer.capture("weather", {"temperature": 28})
    observer.capture("payment", {"status": "paid"})

    result = observer.capture("payment", {"status": "pending"})

    assert result["has_changes"] is False


def test_nested_response_is_compared():
    observer = APIObserver()
    observer.capture(
        "weather",
        {"location": {"city": "Indore"}},
    )

    result = observer.capture(
        "weather",
        {"location": {"city": "Bhopal"}},
    )

    assert result["has_changes"] is False
