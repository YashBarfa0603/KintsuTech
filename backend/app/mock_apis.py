
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
