
import json
import os
from pathlib import Path
from typing import Any

import httpx


BASE_DIR = Path(__file__).resolve().parent
CASES_FILE = BASE_DIR / "behavior_cases.json"

VALID_BASELINE_STATUSES = {"verified", "unverified"}


def load_behavior_cases() -> list[dict[str, Any]]:
    """Load and validate behavioral test cases."""
    with CASES_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    cases = data.get("cases", [])

    if not isinstance(cases, list):
        raise ValueError("'cases' must be a JSON list")

    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("Every behavior case must be a JSON object")

        status = case.get("baseline_status", "unverified")

        if status not in VALID_BASELINE_STATUSES:
            raise ValueError(
                f"Invalid baseline_status in case {case.get('id', 'UNKNOWN')}"
            )

    return cases


def compare_expected(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare explicitly expected fields with observed values."""
    differences = []

    for key, expected_value in expected.items():
        if key not in actual:
            differences.append({
                "field": key,
                "expected": expected_value,
                "actual": None,
                "reason": "missing_field",
            })
        elif actual[key] != expected_value:
            differences.append({
                "field": key,
                "expected": expected_value,
                "actual": actual[key],
                "reason": "value_changed",
            })

    return differences


def run_behavior_case(
    client: httpx.Client,
    case: dict[str, Any],
) -> dict[str, Any]:
    """Run a case without treating an unverified baseline as a contract."""
    case_id = case.get("id", "UNKNOWN")
    name = case.get("name", "Unnamed case")
    baseline_status = case.get("baseline_status", "unverified")

    request_data = case.get("request", {})
    method = request_data.get("method", "GET").upper()
    path = request_data.get("path", "/")
    query = request_data.get("query", {})

    if baseline_status not in VALID_BASELINE_STATUSES:
        return {
            "case_id": case_id,
            "name": name,
            "status": "INVALID_BASELINE",
            "passed": False,
            "differences": [],
            "observed": None,
            "error": f"Unsupported baseline status: {baseline_status}",
        }

    try:
        response = client.request(
            method=method,
            url=path,
            params=query,
        )

        try:
            body = response.json()
        except ValueError:
            body = {"raw_text": response.text}

        actual = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
        }

        expected = case.get("expected", {})

        if not isinstance(expected, dict):
            raise ValueError("'expected' must be a JSON object")

        comparable_actual = dict(body) if isinstance(body, dict) else {}
        comparable_actual["status_code"] = response.status_code

        differences = compare_expected(expected, comparable_actual)

        # An unverified baseline can produce observations, but not a
        # confirmed change or a verified pass.
        if baseline_status != "verified":
            status = "UNVERIFIED"
        elif differences:
            status = "CHANGED"
        else:
            status = "UNCHANGED"

        return {
            "case_id": case_id,
            "name": name,
            "baseline_status": baseline_status,
            "status": status,
            "passed": status == "UNCHANGED",
            "differences": differences,
            "observed": actual,
        }

    except (httpx.HTTPError, ValueError) as exc:
        return {
            "case_id": case_id,
            "name": name,
            "baseline_status": baseline_status,
            "status": (
                "UNVERIFIED"
                if baseline_status == "unverified"
                else "REQUEST_FAILED"
            ),
            "passed": False,
            "differences": [],
            "observed": None,
            "error": str(exc),
        }


def run_behavior_suite() -> dict[str, Any]:
    """Run configured cases and summarize verified outcomes."""
    base_url = os.environ.get("KINTSUTECH_API_URL")

    if not base_url:
        raise RuntimeError(
            "Set KINTSUTECH_API_URL to the base URL of an API you control."
        )

    cases = load_behavior_cases()
    results = []

    with httpx.Client(
        base_url=base_url,
        timeout=10.0,
        follow_redirects=False,
    ) as client:
        for case in cases:
            results.append(run_behavior_case(client, case))

    counts = {
        status: sum(result["status"] == status for result in results)
        for status in (
            "UNCHANGED",
            "CHANGED",
            "UNVERIFIED",
            "REQUEST_FAILED",
            "INVALID_BASELINE",
        )
    }

    return {
        "total": len(results),
        "counts": counts,
        "results": results,
    }


if __name__ == "__main__":
    report = run_behavior_suite()
    print(json.dumps(report, indent=2, ensure_ascii=False))
