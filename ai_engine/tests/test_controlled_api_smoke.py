
import httpx

from behavior_checks import check_rate_limit
from pagination_runner import run_pagination


def make_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    )


def test_pagination_uses_real_cursor_requests():
    requested_cursors = []

    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        requested_cursors.append(cursor)

        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "items": [{"id": 1}],
                    "has_next_page": True,
                    "next_cursor": "page-2",
                },
            )

        if cursor == "page-2":
            return httpx.Response(
                200,
                json={
                    "items": [{"id": 2}],
                    "has_next_page": False,
                    "next_cursor": None,
                },
            )

        return httpx.Response(400, json={"error": "unexpected cursor"})

    with make_client(handler) as client:
        result = run_pagination(client, "/products")

    assert result["status"] == "COMPLETED"
    assert result["pages_fetched"] == 2
    assert result["total_items"] == 2
    assert requested_cursors == [None, "page-2"]


def test_rate_limit_uses_actual_status_and_retry_after_header():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"Retry-After": "1"},
            json={"message": "Rate limit exceeded"},
        )

    with make_client(handler) as client:
        response = client.get("/products")

    result = check_rate_limit(
        response.status_code,
        response.headers,
        baseline_status="verified",
    )

    assert response.status_code == 429
    assert result["observed"]["rate_limited"] is True
    assert result["observed"]["retry_after_present"] is True
    assert result["observed"]["retry_after"] == "1"
    assert result["status"] == "UNCHANGED"
