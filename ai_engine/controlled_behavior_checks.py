
import os
from typing import Any

import httpx

from behavior_checks import check_pagination, check_rate_limit
from behavior_runner import load_behavior_cases
from pagination_runner import run_pagination


def run_controlled_behavior_checks() -> dict[str, Any]:
    """Run real pagination and rate-limit checks against a controlled API."""

    base_url = os.environ.get("KINTSUTECH_API_URL")
    if not base_url:
        raise RuntimeError(
            "Set KINTSUTECH_API_URL to an API you control."
        )

    pagination_reports = []
    rate_limit_reports = []

    cases = load_behavior_cases()

    with httpx.Client(
        base_url=base_url,
        timeout=10.0,
        follow_redirects=False,
    ) as client:
        for case in cases:
            category = case.get("category")
            request_data = case.get("request", {})
            method = request_data.get("method", "GET").upper()
            path = request_data.get("path", "/")
            query = request_data.get("query", {})
            baseline_status = case.get("baseline_status", "unverified")

            if method != "GET":
                continue

            if category == "pagination":
                try:
                    response = client.get(path, params=query)
                    response.raise_for_status()
                    body = response.json()

                    if not isinstance(body, dict):
                        raise ValueError("Pagination response must be a JSON object.")

                    pagination_check = check_pagination(
                        body,
                        baseline_status=baseline_status,
                        items_field=case.get("items_field", "products"),
                        has_next_field=case.get(
                            "has_next_field", "has_next_page"
                        ),
                        cursor_field=case.get(
                            "cursor_field", "next_cursor"
                        ),
                    )

                    traversal = run_pagination(
                        client,
                        path,
                        query=query,
                        items_field=case.get("items_field", "products"),
                        has_next_field=case.get(
                            "has_next_field", "has_next_page"
                        ),
                        cursor_field=case.get(
                            "cursor_field", "next_cursor"
                        ),
                        cursor_param=case.get("cursor_param", "cursor"),
                        max_pages=case.get("max_pages", 10),
                    )

                    pagination_reports.append({
                        "case_id": case.get("id"),
                        "check": "pagination",
                        "status": pagination_check["status"],
                        "baseline_status": baseline_status,
                        "differences": pagination_check["differences"],
                        "observed": pagination_check["observed"],
                        "traversal": traversal,
                    })

                except (httpx.HTTPError, ValueError) as exc:
                    pagination_reports.append({
                        "case_id": case.get("id"),
                        "check": "pagination",
                        "status": "UNVERIFIED",
                        "baseline_status": baseline_status,
                        "differences": [],
                        "error": str(exc),
                    })

            elif category == "rate_limit":
                try:
                    response = client.get(path, params=query)

                    expected = case.get("expected", {})
                    expected_status = expected.get(
                        "rate_limited_status_code", 429
                    )

                    report = check_rate_limit(
                        response.status_code,
                        response.headers,
                        baseline_status=baseline_status,
                        expected_status_code=expected_status,
                    )

                    rate_limit_reports.append({
                        "case_id": case.get("id"),
                        **report,
                    })

                except httpx.HTTPError as exc:
                    rate_limit_reports.append({
                        "case_id": case.get("id"),
                        "check": "rate_limit",
                        "status": "UNVERIFIED",
                        "baseline_status": baseline_status,
                        "differences": [],
                        "error": str(exc),
                    })

    return {
        "pagination_reports": pagination_reports,
        "rate_limit_reports": rate_limit_reports,
    }
