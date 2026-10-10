
import pytest

from app.mock_apis import get_weather_response


def test_weather_v1_returns_original_schema():
    assert get_weather_response(1) == {
        "city": "Indore",
        "temperature": 30,
        "condition": "Sunny",
    }


def test_weather_v2_simulates_schema_change():
    response = get_weather_response(2)

    assert response["temperature"] == "30"
    assert isinstance(response["temperature"], str)
    assert response["humidity"] == 45


def test_unsupported_version_raises_error():
    with pytest.raises(ValueError):
        get_weather_response(3)


def test_response_mutation_does_not_change_mock_data():
    response = get_weather_response(1)
    response["city"] = "Changed"

    assert get_weather_response(1)["city"] == "Indore"
