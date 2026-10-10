
from typing import Any, Mapping


def _classify(
    differences: list[dict[str, Any]],
    baseline_status: str,
) -> str:
    """Classify observations only when the baseline is trusted."""
    if baseline_status not in {"verified", "unverified"}:
        return "INVALID_BASELINE"

    if baseline_status == "unverified":
        return "UNVERIFIED"

    return "CHANGED" if differences else "UNCHANGED"


def check_pagination(
    body: Mapping[str, Any],
    *,
    baseline_status: str = "unverified",
    items_field: str = "items",
    has_next_field: str = "has_next_page",
    cursor_field: str = "next_cursor",
    current_cursor: Any = None,
    previous_cursors: list[Any] | None = None,
) -> dict[str, Any]:
    """
    Check pagination signals in one response.

    Field names are configurable because APIs use different formats.
    This function checks response evidence; it does not fetch another page.
    """
    previous_cursors = previous_cursors or []
    differences: list[dict[str, Any]] = []
    observed: dict[str, Any] = {}

    items = body.get(items_field)
    has_next = body.get(has_next_field)
    next_cursor = body.get(cursor_field)

    observed["items_present"] = items_field in body
    observed["items_is_list"] = isinstance(items, list)
    observed["has_next_page"] = has_next
    observed["next_cursor_present"] = (
        cursor_field in body and next_cursor not in (None, "")
    )
    observed["next_cursor"] = next_cursor

    if items_field not in body:
        differences.append({
            "field": items_field,
            "reason": "missing_items_field",
        })
    elif not isinstance(items, list):
        differences.append({
            "field": items_field,
            "reason": "items_not_a_list",
        })

    if not isinstance(has_next, bool):
        differences.append({
            "field": has_next_field,
            "reason": "missing_or_invalid_has_next_flag",
        })
    elif has_next:
        if next_cursor in (None, ""):
            differences.append({
                "field": cursor_field,
                "reason": "next_page_without_cursor",
            })
        elif next_cursor == current_cursor:
            differences.append({
                "field": cursor_field,
                "reason": "cursor_did_not_advance",
                "actual": next_cursor,
            })
        elif next_cursor in previous_cursors:
            differences.append({
                "field": cursor_field,
                "reason": "cursor_repeated",
                "actual": next_cursor,
            })
    else:
        if next_cursor not in (None, ""):
            differences.append({
                "field": cursor_field,
                "reason": "cursor_present_when_no_next_page",
                "actual": next_cursor,
            })

    return {
        "check": "pagination",
        "status": _classify(differences, baseline_status),
        "baseline_status": baseline_status,
        "observed": observed,
        "differences": differences,
    }


def check_rate_limit(
    status_code: int,
    headers: Mapping[str, Any],
    *,
    baseline_status: str = "unverified",
    expected_status_code: int = 429,
    require_retry_after: bool = True,
) -> dict[str, Any]:
    """
    Inspect a response for rate-limit signals.

    Call this with a response from an authorized, controlled test.
    It does not generate repeated requests or exhaust a quota.
    """
    differences: list[dict[str, Any]] = []

    normalized_headers = {
        str(key).lower(): str(value)
        for key, value in headers.items()
    }

    retry_after = normalized_headers.get("retry-after")

    observed = {
        "status_code": status_code,
        "rate_limited": status_code == 429,
        "retry_after_present": retry_after is not None,
        "retry_after": retry_after,
    }

    if status_code != expected_status_code:
        differences.append({
            "field": "status_code",
            "expected": expected_status_code,
            "actual": status_code,
            "reason": "status_code_changed",
        })

    if require_retry_after and status_code == 429 and retry_after is None:
        differences.append({
            "field": "Retry-After",
            "reason": "retry_after_missing",
        })

    return {
        "check": "rate_limit",
        "status": _classify(differences, baseline_status),
        "baseline_status": baseline_status,
        "observed": observed,
        "differences": differences,
    }
