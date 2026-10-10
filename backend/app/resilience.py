
from collections.abc import Callable
from typing import Any

from app.mock_apis import SimulatedAPIError


RETRYABLE_ERRORS = (
    TimeoutError,
    ConnectionError,
    SimulatedAPIError,
)


def call_with_retry(
    api_call: Callable[[], dict[str, Any]],
    max_attempts: int = 3,
) -> dict[str, Any]:
    """Retry transient API failures up to max_attempts."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1.")

    for attempt in range(1, max_attempts + 1):
        try:
            return api_call()
        except RETRYABLE_ERRORS:
            if attempt == max_attempts:
                raise

    raise RuntimeError("Unexpected retry loop exit.")
