
from behavior_checks import check_pagination, check_rate_limit


def test_pagination_accepts_valid_next_page():
    result = check_pagination(
        {
            "items": [{"id": 1}],
            "has_next_page": True,
            "next_cursor": "cursor-2",
        },
        baseline_status="verified",
        current_cursor="cursor-1",
        previous_cursors=["cursor-0"],
    )

    assert result["status"] == "UNCHANGED"
    assert result["differences"] == []


def test_pagination_detects_missing_cursor():
    result = check_pagination(
        {
            "items": [{"id": 1}],
            "has_next_page": True,
        },
        baseline_status="verified",
    )

    assert result["status"] == "CHANGED"
    assert any(
        difference["reason"] == "next_page_without_cursor"
        for difference in result["differences"]
    )


def test_pagination_detects_repeated_cursor():
    result = check_pagination(
        {
            "items": [{"id": 1}],
            "has_next_page": True,
            "next_cursor": "cursor-1",
        },
        baseline_status="verified",
        current_cursor="cursor-1",
    )

    assert result["status"] == "CHANGED"
    assert any(
        difference["reason"] == "cursor_did_not_advance"
        for difference in result["differences"]
    )


def test_pagination_detects_cursor_after_last_page():
    result = check_pagination(
        {
            "items": [],
            "has_next_page": False,
            "next_cursor": "cursor-2",
        },
        baseline_status="verified",
    )

    assert result["status"] == "CHANGED"
    assert any(
        difference["reason"] == "cursor_present_when_no_next_page"
        for difference in result["differences"]
    )


def test_pagination_detects_missing_items():
    result = check_pagination(
        {
            "has_next_page": False,
        },
        baseline_status="verified",
    )

    assert result["status"] == "CHANGED"
    assert any(
        difference["reason"] == "missing_items_field"
        for difference in result["differences"]
    )


def test_unverified_pagination_does_not_claim_change():
    result = check_pagination(
        {
            "items": [],
            "has_next_page": True,
        },
        baseline_status="unverified",
    )

    assert result["status"] == "UNVERIFIED"
    assert result["differences"]


def test_rate_limit_accepts_429_with_retry_after():
    result = check_rate_limit(
        429,
        {"Retry-After": "5"},
        baseline_status="verified",
    )

    assert result["status"] == "UNCHANGED"
    assert result["observed"]["rate_limited"] is True
    assert result["observed"]["retry_after"] == "5"
    assert result["differences"] == []


def test_rate_limit_detects_missing_retry_after():
    result = check_rate_limit(
        429,
        {},
        baseline_status="verified",
    )

    assert result["status"] == "CHANGED"
    assert any(
        difference["reason"] == "retry_after_missing"
        for difference in result["differences"]
    )


def test_rate_limit_detects_unexpected_status():
    result = check_rate_limit(
        200,
        {},
        baseline_status="verified",
    )

    assert result["status"] == "CHANGED"
    assert result["observed"]["rate_limited"] is False


def test_unverified_rate_limit_does_not_claim_change():
    result = check_rate_limit(
        200,
        {},
        baseline_status="unverified",
    )

    assert result["status"] == "UNVERIFIED"
    assert result["differences"]


def test_rate_limit_header_names_are_case_insensitive():
    result = check_rate_limit(
        429,
        {"rEtRy-AfTeR": "10"},
        baseline_status="verified",
    )

    assert result["status"] == "UNCHANGED"
    assert result["observed"]["retry_after"] == "10"
