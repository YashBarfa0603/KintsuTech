import pytest

from app.mock_apis import get_weather_response
from app.storage import storage_registry


@pytest.fixture(autouse=True)
def clean_test_storage():
    """
    Ensure the global storage_registry starts each test with the baseline seeded
    state, preventing cross-test pollution while testing full API endpoints.
    """
    storage_registry.reset()
    storage_registry.register_service(
        "weather",
        name="Mock Weather Service",
        base_url="http://127.0.0.1:8000/api/v1/mock/weather",
        description="Simulated third-party weather API",
    )
    storage_registry.save_baseline(
        "weather",
        get_weather_response(1),
        description="Initial known-good Weather v1 baseline",
    )
    yield
