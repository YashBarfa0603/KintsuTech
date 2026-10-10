
import httpx

from behavior_runner import (
    compare_expected,
    load_behavior_cases,
    run_behavior_case,
)


def test_compare_expected_detects_changed_value():
    differences = compare_expected(
        {"default_page_size": 20},
        {"default_page_size": 10},
    )

    assert len(differences) == 1
    assert differences[0]["reason"] == "value_changed"


def test_compare_expected_detects_missing_field():
    differences = compare_expected(
        {"error_type": "validation_error"},
        {},
    )

    assert len(differences) == 1
    assert differences[0]["reason"] == "missing_field"


def test_compare_expected_accepts_matching_values():
    assert compare_expected(
        {"status_code": 400},
        {"status_code": 400},
    ) == []


def test_load_behavior_cases():
    cases = load_behavior_cases()

    assert len(cases) > 0
    assert all("id" in case and "request" in case for case in cases)


def test_runner_detects_changed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"default_page_size": 10},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    )

    case = {
        "id": "DEFAULT-TEST",
        "name": "Changed page size",
        "baseline_status": "verified",
        "request": {
            "method": "GET",
            "path": "/products",
            "query": {},
        },
        "expected": {"default_page_size": 20},
    }

    try:
        result = run_behavior_case(client, case)
    finally:
        client.close()

    assert result["status"] == "CHANGED"
    assert result["passed"] is False
    assert len(result["differences"]) == 1
    assert result["differences"][0]["field"] == "default_page_size"
    assert result["differences"][0]["expected"] == 20
    assert result["differences"][0]["actual"] == 10


def test_runner_accepts_matching_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error_type": "validation_error"},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    )

    case = {
        "id": "ERROR-TEST",
        "name": "Invalid input",
        "baseline_status": "verified",
        "request": {
            "method": "GET",
            "path": "/products",
            "query": {},
        },
        "expected": {
            "status_code": 400,
            "error_type": "validation_error",
        },
    }

    try:
        result = run_behavior_case(client, case)
    finally:
        client.close()

    assert result["status"] == "UNCHANGED"
    assert result["passed"] is True
    assert result["differences"] == []


def test_matching_response_with_unverified_baseline_is_not_verified():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"default_page_size": 20},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    )

    case = {
        "id": "UNVERIFIED-TEST",
        "name": "Unverified default",
        "baseline_status": "unverified",
        "request": {
            "method": "GET",
            "path": "/products",
            "query": {},
        },
        "expected": {"default_page_size": 20},
    }

    try:
        result = run_behavior_case(client, case)
    finally:
        client.close()

    assert result["status"] == "UNVERIFIED"
    assert result["passed"] is False
    assert result["differences"] == []
