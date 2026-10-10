
import pytest

from app.resilience import call_with_retry


def test_success_on_first_attempt():
    result = call_with_retry(lambda: {"status": "ok"})

    assert result == {"status": "ok"}


def test_retries_then_succeeds():
    attempts = 0

    def flaky_api():
        nonlocal attempts
        attempts += 1

        if attempts < 3:
            raise TimeoutError("Temporary timeout")

        return {"status": "ok"}

    result = call_with_retry(flaky_api, max_attempts=3)

    assert result == {"status": "ok"}
    assert attempts == 3


def test_raises_after_max_attempts():
    attempts = 0

    def failing_api():
        nonlocal attempts
        attempts += 1
        raise ConnectionError("API unavailable")

    with pytest.raises(ConnectionError, match="API unavailable"):
        call_with_retry(failing_api, max_attempts=3)

    assert attempts == 3


def test_invalid_max_attempts():
    with pytest.raises(ValueError, match="at least 1"):
        call_with_retry(lambda: {"status": "ok"}, max_attempts=0)


def test_does_not_retry_success():
    attempts = 0

    def healthy_api():
        nonlocal attempts
        attempts += 1
        return {"status": "ok"}

    call_with_retry(healthy_api, max_attempts=3)

    assert attempts == 1


def test_does_not_retry_non_retryable_error():
    attempts = 0

    def invalid_request():
        nonlocal attempts
        attempts += 1
        raise ValueError("Invalid request")

    with pytest.raises(ValueError, match="Invalid request"):
        call_with_retry(invalid_request, max_attempts=3)

    assert attempts == 1
