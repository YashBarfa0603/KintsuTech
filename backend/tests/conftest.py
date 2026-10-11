import pytest

from app.auth import AuthenticatedUser, get_current_user
from app.main import app
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


@pytest.fixture(autouse=True)
def mock_authenticated_user_for_general_tests():
    """
    Provide default mock authenticated user for general endpoint tests.
    """
    mock_user = AuthenticatedUser(
        id="test-mock-user-uuid",
        email="developer@kintsutech.com",
        role="authenticated",
        user_metadata={"full_name": "Kintsu Developer"},
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    yield mock_user
    app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture(autouse=True)
def mock_ollama_for_offline_tests(monkeypatch):
    """
    Ensure tests that execute the full AI repair pipeline can run cleanly offline
    without requiring a running Ollama daemon.
    """
    try:
        import repair_pipeline
        from schemas import RepairProposal

        def fallback_analyze(*args, **kwargs):
            return RepairProposal(
                change_summary="The temperature field was replaced by temp_c.",
                evidence=["Field removed: temperature", "Field added: temp_c"],
                potential_impact="Downstream consumers reading temperature may fail.",
                proposed_repair="Use a field-copy compatibility adapter.",
                confidence=0.85,
                requires_validation=True,
            )

        monkeypatch.setattr(repair_pipeline, "analyze_api_change", fallback_analyze)
    except Exception:
        pass
    yield
