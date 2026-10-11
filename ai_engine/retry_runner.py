import time
from typing import Any

import httpx

from behavior_checks import check_retry_timing


def run_retry_check(
    client: httpx.Client,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    baseline_status: str = "unverified",
) -> dict[str, Any]:
    """Make one request and retry once after a numeric Retry-After delay."""

    first_response = client.get(path, params=params)

    result: dict[str, Any] = {
        "check": "retry_timing",
        "initial_status_code": first_response.status_code,
        "retry_status_code": None,
        "retry_attempted": False,
        "elapsed_seconds": None,
        "timing_check": None,
    }

    if first_response.status_code != 429:
        result["reason"] = "initial_response_not_rate_limited"
        return result

    retry_after = first_response.headers.get("Retry-After")

    if retry_after is None:
        result["reason"] = "retry_after_missing"
        result["timing_check"] = check_retry_timing(
            0,
            None,
            baseline_status=baseline_status,
        )
        return result

    try:
        delay_seconds = float(retry_after)
    except ValueError:
        result["reason"] = "unsupported_retry_after_format"
        return result

    if delay_seconds < 0:
        result["reason"] = "invalid_retry_after_value"
        return result

    if delay_seconds > 10.0:
        result["reason"] = "retry_after_exceeds_maximum_delay"
        return result

    # Start timing after receiving the 429 response.
    wait_started = time.monotonic()
    time.sleep(delay_seconds)

    # Measure elapsed time immediately before sending the retry.
    elapsed_seconds = time.monotonic() - wait_started

    result["retry_attempted"] = True
    result["elapsed_seconds"] = elapsed_seconds

    result["timing_check"] = check_retry_timing(
        delay_seconds,
        elapsed_seconds,
        baseline_status=baseline_status,
    )

    try:
        retry_response = client.get(path, params=params)
        result["retry_status_code"] = retry_response.status_code
    except httpx.HTTPError as exc:
        result["retry_error"] = str(exc)

    return result
