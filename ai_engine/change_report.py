
from typing import Any


def build_unified_change_report(
    schema_report: dict[str, Any],
    behavior_report: dict[str, Any],
    text_diff: list[dict[str, str]],
    pagination_reports: list[dict[str, Any]] | None = None,
    rate_limit_reports: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Combine schema, behavior, Myers diff, pagination, and rate-limit
    evidence into one report.

    Only verified, classified changes are added as confirmed findings.
    All supplied detector reports remain available in evidence.
    """
    pagination_reports = pagination_reports or []
    rate_limit_reports = rate_limit_reports or []

    changes: list[dict[str, Any]] = []

    for change in schema_report.get("changes", []):
        changes.append({
            "source": "structural",
            **change,
        })

    for change in behavior_report.get("changes", []):
        changes.append({
            "source": "behavioral",
            **change,
        })

    for operation in text_diff:
        if operation.get("operation") in ("insert", "delete"):
            changes.append({
                "source": "text_diff",
                "kind": operation["operation"],
                "value": operation["value"],
            })

    def add_check_findings(
        reports: list[dict[str, Any]],
        source: str,
    ) -> None:
        for report in reports:
            # Unverified observations are retained as evidence, but they
            # must not be promoted to confirmed changes.
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
    }

    return {
        "has_changes": bool(changes),
        "total_change_count": len(changes),
        "breaking_change_count": schema_report.get(
            "breaking_change_count", 0
        ),
        "summary": summary,
        "changes": changes,
        "evidence": {
            "schema_report": schema_report,
            "behavior_report": behavior_report,
            "text_diff": text_diff,
            "pagination_reports": pagination_reports,
            "rate_limit_reports": rate_limit_reports,
        },
    }
