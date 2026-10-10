
from typing import Any

import httpx


def run_pagination(
    client: httpx.Client,
    path: str,
    *,
    query: dict[str, Any] | None = None,
    items_field: str = "items",
    has_next_field: str = "has_next_page",
    cursor_field: str = "next_cursor",
    cursor_param: str = "cursor",
    max_pages: int = 10,
) -> dict[str, Any]:
    """
    Fetch pages by following cursors.

    Stops when there is no next page, a cursor repeats, a response is
    invalid, a request fails, or max_pages is reached.
    """
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")

    params = dict(query or {})
    pages: list[dict[str, Any]] = []
    seen_cursors: set[str] = set()
    current_cursor = params.get(cursor_param)
    stop_reason = "unknown"

    for page_number in range(1, max_pages + 1):
        request_params = dict(params)

        if current_cursor is not None:
            request_params[cursor_param] = current_cursor
        else:
            request_params.pop(cursor_param, None)

        try:
            response = client.get(path, params=request_params)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "status": "REQUEST_FAILED",
                "pages_fetched": len(pages),
                "pages": pages,
                "stop_reason": "request_or_response_error",
                "error": str(exc),
            }

        if not isinstance(body, dict):
            return {
                "status": "INVALID_RESPONSE",
                "pages_fetched": len(pages),
                "pages": pages,
                "stop_reason": "response_not_object",
            }

        items = body.get(items_field)
        has_next = body.get(has_next_field)
        next_cursor = body.get(cursor_field)

        if not isinstance(items, list) or not isinstance(has_next, bool):
            return {
                "status": "INVALID_RESPONSE",
                "pages_fetched": len(pages),
                "pages": pages,
                "stop_reason": "invalid_pagination_fields",
            }

        pages.append({
            "page_number": page_number,
            "item_count": len(items),
            "items": items,
            "has_next_page": has_next,
            "next_cursor": next_cursor,
        })

        if not has_next:
            stop_reason = "last_page"
            break

        if not isinstance(next_cursor, str) or not next_cursor.strip():
            return {
                "status": "PAGINATION_ERROR",
                "pages_fetched": len(pages),
                "pages": pages,
                "stop_reason": "next_page_without_valid_cursor",
            }

        if next_cursor == current_cursor or next_cursor in seen_cursors:
            return {
                "status": "PAGINATION_ERROR",
                "pages_fetched": len(pages),
                "pages": pages,
                "stop_reason": "repeated_cursor",
            }

        seen_cursors.add(next_cursor)
        current_cursor = next_cursor
    else:
        stop_reason = "max_pages_reached"

    status = (
        "MAX_PAGES_REACHED"
        if stop_reason == "max_pages_reached"
        else "COMPLETED"
    )

    return {
        "status": status,
        "pages_fetched": len(pages),
        "pages": pages,
        "stop_reason": stop_reason,
        "total_items": sum(page["item_count"] for page in pages),
    }
