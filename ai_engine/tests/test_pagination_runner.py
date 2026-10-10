
import httpx

from pagination_runner import run_pagination


def make_client(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    )


def test_follows_multiple_pages():
    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")

        if cursor is None:
            return httpx.Response(
                200,
                json={
                    "items": [{"id": 1}],
                    "has_next_page": True,
                    "next_cursor": "cursor-2",
                },
            )

        if cursor == "cursor-2":
            return httpx.Response(
                200,
                json={
                    "items": [{"id": 2}],
                    "has_next_page": False,
                    "next_cursor": None,
                },
            )

        return httpx.Response(400, json={"error": "unexpected cursor"})

    client = make_client(handler)

    try:
        result = run_pagination(client, "/products")
    finally:
        client.close()

    assert result["status"] == "COMPLETED"
    assert result["pages_fetched"] == 2
    assert result["total_items"] == 2
    assert result["stop_reason"] == "last_page"


def test_detects_repeated_cursor():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [{"id": 1}],
                "has_next_page": True,
                "next_cursor": "cursor-2",
            },
        )

    client = make_client(handler)

    try:
        result = run_pagination(client, "/products")
    finally:
        client.close()

    assert result["status"] == "PAGINATION_ERROR"
    assert result["stop_reason"] == "repeated_cursor"
    assert result["pages_fetched"] == 2


def test_stops_at_maximum_page_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")

        next_cursor = (
            "cursor-2" if cursor is None
            else f"cursor-{int(cursor.split('-')[1]) + 1}"
        )

        return httpx.Response(
            200,
            json={
                "items": [{"id": 1}],
                "has_next_page": True,
                "next_cursor": next_cursor,
            },
        )

    client = make_client(handler)

    try:
        result = run_pagination(
            client,
            "/products",
            max_pages=3,
        )
    finally:
        client.close()

    assert result["status"] == "MAX_PAGES_REACHED"
    assert result["pages_fetched"] == 3
    assert result["stop_reason"] == "max_pages_reached"


def test_detects_missing_cursor():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [{"id": 1}],
                "has_next_page": True,
            },
        )

    client = make_client(handler)

    try:
        result = run_pagination(client, "/products")
    finally:
        client.close()

    assert result["status"] == "PAGINATION_ERROR"
    assert result["stop_reason"] == "next_page_without_valid_cursor"


def test_rejects_invalid_pagination_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"items": "not-a-list", "has_next_page": False},
        )

    client = make_client(handler)

    try:
        result = run_pagination(client, "/products")
    finally:
        client.close()

    assert result["status"] == "INVALID_RESPONSE"
    assert result["stop_reason"] == "invalid_pagination_fields"


def test_rejects_zero_max_pages():
    client = make_client(
        lambda request: httpx.Response(200, json={})
    )

    try:
        try:
            run_pagination(client, "/products", max_pages=0)
        except ValueError as exc:
            assert "at least 1" in str(exc)
        else:
            raise AssertionError("Expected ValueError")
    finally:
        client.close()
