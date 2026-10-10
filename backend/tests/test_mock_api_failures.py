
import pytest

from app.mock_apis import (
    SimulatedAPIError,
    call_weather_api,
)


def test_success_mode_returns_weather_data():
    response = call_weather_api("success")

    assert response["city"] == "Indore"
    assert response["temperature"] == 30


def test_server_error_mode():
    with pytest.raises(SimulatedAPIError, match="503"):
        call_weather_api("server_error")


def test_timeout_mode():
    with pytest.raises(TimeoutError):
        call_weather_api("timeout")


def test_unavailable_mode():
    with pytest.raises(ConnectionError):
        call_weather_api("unavailable")


def test_invalid_mode():
    with pytest.raises(ValueError, match="Unsupported mode"):
        call_weather_api("invalid")
