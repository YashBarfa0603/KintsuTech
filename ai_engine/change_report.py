from typing import Any


def build_unified_change_report(
    schema_report: dict[str, Any],
    behavior_report: dict[str, Any],
    text_diff: list[dict[str, str]],
    pagination_reports: list[dict[str, Any]] | None = None,
    rate_limit_reports: list[dict[str, Any]] | None = None,
    retry_timing_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Combine structural, behavioral, text-diff, pagination,
    rate-limit, and retry-timing evidence into one report.

    Only classified changes are added as findings.
    Successful traversal metrics remain evidence, not change findings.
    """

    pagination_reports = pagination_reports or []
    rate_limit_reports = rate_limit_reports or []
    retry_timing_reports = retry_timing_reports or []

    changes: list[dict[str, Any]] = []

    # Structural changes
    for change in schema_report.get("changes", []):
        changes.append({
            "source": "structural",
            **change,
        })

    # Behavioral changes
    for change in behavior_report.get("changes", []):
        changes.append({
            "source": "behavioral",
            **change,
        })

    # Text differences
    for operation in text_diff:
        if operation.get("operation") in ("insert", "delete"):
            changes.append({
                "source": "text_diff",
                "kind": operation["operation"],
                "value": operation["value"],
            })

    # Classified findings from controlled checks
    def add_check_findings(
        reports: list[dict[str, Any]],
        source: str,
    ) -> None:
        for report in reports:
            if report.get("status") != "CHANGED":
                continue

            for difference in report.get("differences", []):
                changes.append({
                    "source": source,
                    "check": report.get("check", source),
                    **difference,
                })

    add_check_findings(pagination_reports, "pagination")
    add_check_findings(rate_limit_reports, "rate_limit")
    add_check_findings(retry_timing_reports, "retry_timing")

    # Pagination metrics: evidence, not automatically findings.
    completed_runs = [
        report.get("traversal", report)
        for report in pagination_reports
        if report.get("traversal", report).get("status") == "COMPLETED"
    ]

    failed_runs = [
        report.get("traversal", report)
        for report in pagination_reports
        if report.get("traversal", report).get("status")
        in {
            "REQUEST_FAILED",
            "INVALID_RESPONSE",
            "PAGINATION_ERROR",
            "MAX_PAGES_REACHED",
        }
    ]

    pagination_metrics = {
        "runs": len(pagination_reports),
        "completed_runs": len(completed_runs),
        "failed_or_incomplete_runs": len(failed_runs),
        "total_pages_fetched": sum(
            report.get("pages_fetched", 0)
            for report in completed_runs + failed_runs
        ),
        "total_items_fetched": sum(
            report.get("total_items", 0)
            for report in completed_runs + failed_runs
        ),
    }

    # Summary by finding source
    summary = {
        "structural_changes": sum(
            change["source"] == "structural" for change in changes
        ),
        "behavioral_changes": sum(
            change["source"] == "behavioral" for change in changes
        ),
        "text_diff_changes": sum(
            change["source"] == "text_diff" for change in changes
        ),
        "pagination_changes": sum(
            change["source"] == "pagination" for change in changes
        ),
        "rate_limit_changes": sum(
            change["source"] == "rate_limit" for change in changes
        ),
        "retry_timing_changes": sum(
            change["source"] == "retry_timing" for change in changes
        ),
    }

    return {
        "has_changes": bool(changes),
        "total_change_count": len(changes),
        "breaking_change_count": schema_report.get(
            "breaking_change_count", 0
        ),
        "summary": summary,
        "pagination_metrics": pagination_metrics,
        "changes": changes,
        "evidence": {
            "schema_report": schema_report,
            "behavior_report": behavior_report,
            "text_diff": text_diff,
            "pagination_reports": pagination_reports,
            "rate_limit_reports": rate_limit_reports,
            "retry_timing_reports": retry_timing_reports,
        },
    }
