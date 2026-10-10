
from copy import deepcopy
from typing import Any


_WEATHER_V1: dict[str, Any] = {
    "city": "Indore",
    "temperature": 30,
    "condition": "Sunny",
}

_WEATHER_V2: dict[str, Any] = {
    "city": "Indore",
    "temperature": "30",
    "condition": "Sunny",
    "humidity": 45,
}


def get_weather_response(version: int = 1) -> dict[str, Any]:
    """Return a simulated third-party weather API response."""
    if version == 1:
        return deepcopy(_WEATHER_V1)

    if version == 2:
        return deepcopy(_WEATHER_V2)

    raise ValueError("Unsupported weather API version. Use 1 or 2.")


class SimulatedAPIError(Exception):
    """Raised when the mock third-party API fails."""


def call_weather_api(mode: str = "success") -> dict[str, Any]:
    """Simulate success or common third-party API failures."""
    if mode == "success":
        return get_weather_response(version=1)

    if mode == "server_error":
        raise SimulatedAPIError("Simulated API server error (HTTP 503).")

    if mode == "timeout":
        raise TimeoutError("Simulated API request timeout.")

    if mode == "unavailable":
        raise ConnectionError("Simulated API connection failure.")

    raise ValueError(
        "Unsupported mode. Use success, server_error, timeout, or unavailable."
    )
