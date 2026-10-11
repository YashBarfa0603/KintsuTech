
import httpx

from retry_runner import run_retry_check


def test_retry_runner_waits_and_retries_successfully():
    requests = []

    def handler(request):
        requests.append(request)

        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0.05"},
                json={"error_type": "rate_limit_exceeded"},
            )

        return httpx.Response(200, json={"message": "success"})

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    ) as client:
        result = run_retry_check(
            client,
            "/products",
            baseline_status="unverified",
        )

    assert result["initial_status_code"] == 429
    assert result["retry_status_code"] == 200
    assert result["retry_attempted"] is True
    assert result["elapsed_seconds"] >= 0.05
    assert len(requests) == 2
    assert result["timing_check"]["status"] == "UNVERIFIED"


def test_retry_runner_handles_missing_retry_after():
    def handler(request):
        return httpx.Response(
            429,
            json={"error_type": "rate_limit_exceeded"},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    ) as client:
        result = run_retry_check(
            client,
            "/products",
            baseline_status="unverified",
        )

    assert result["initial_status_code"] == 429
    assert result["retry_attempted"] is False
    assert result["reason"] == "retry_after_missing"


def test_retry_runner_does_not_retry_when_response_is_not_429():
    def handler(request):
        return httpx.Response(200, json={"message": "success"})

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    ) as client:
        result = run_retry_check(
            client,
            "/products",
            baseline_status="unverified",
        )

    assert result["initial_status_code"] == 200
    assert result["retry_attempted"] is False
    assert result["reason"] == "initial_response_not_rate_limited"


def test_retry_runner_rejects_negative_retry_after():
    def handler(request):
        return httpx.Response(
            429,
            headers={"Retry-After": "-1"},
            json={"error": "rate_limited"},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    ) as client:
        result = run_retry_check(
            client,
            "/products",
            baseline_status="unverified",
        )

    assert result["initial_status_code"] == 429
    assert result["retry_attempted"] is False
    assert result["reason"] == "invalid_retry_after_value"


def test_retry_runner_rejects_excessive_retry_after():
    def handler(request):
        return httpx.Response(
            429,
            headers={"Retry-After": "100"},
            json={"error": "rate_limited"},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    ) as client:
        result = run_retry_check(
            client,
            "/products",
            baseline_status="unverified",
        )

    assert result["initial_status_code"] == 429
    assert result["retry_attempted"] is False
    assert result["reason"] == "retry_after_exceeds_maximum_delay"


def test_retry_runner_captures_retry_network_error():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0.01"},
                json={"error": "rate_limited"},
            )
        raise httpx.ConnectError("Network dropped during retry", request=request)

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    ) as client:
        result = run_retry_check(
            client,
            "/products",
            baseline_status="unverified",
        )

    assert result["initial_status_code"] == 429
    assert result["retry_attempted"] is True
    assert "retry_error" in result

