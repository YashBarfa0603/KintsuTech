
from unittest.mock import patch

import change_workflow


def test_verified_behavior_findings_reach_unified_report():
    suite_report = {
        "results": [
            {
                "case_id": "TEST-001",
                "name": "Verified response behavior",
                "status": "CHANGED",
                "baseline_status": "verified",
                "differences": [
                    {
                        "field": "status_code",
                        "expected": 200,
                        "actual": 500,
                    }
                ],
            }
        ]
    }

    expected_report = {
        "has_changes": False,
        "total_change_count": 0,
        "changes": [],
    }

    controlled_reports = {
        "pagination_reports": [],
        "rate_limit_reports": [],
    }

    with (
        patch(
            "change_workflow.run_behavior_suite",
            return_value=suite_report,
        ) as mocked_suite,
        patch(
            "change_workflow.run_controlled_behavior_checks",
            return_value=controlled_reports,
        ) as mocked_controlled_checks,
        patch(
            "change_workflow.build_unified_change_report",
            return_value=expected_report,
        ) as mocked_report,
    ):
        result = change_workflow.run_change_workflow(
            baseline={"temperature": 30},
            current={"temperature": 30},
            run_behavior_tests=True,
        )

    mocked_suite.assert_called_once_with()
    mocked_controlled_checks.assert_called_once_with()
    mocked_report.assert_called_once()

    passed_behavior_report = mocked_report.call_args.kwargs[
        "behavior_report"
    ]

    assert passed_behavior_report["changes"] == [
        {
            "kind": "behavior_case_changed",
            "case_id": "TEST-001",
            "name": "Verified response behavior",
            "differences": [
                {
                    "field": "status_code",
                    "expected": 200,
                    "actual": 500,
                }
            ],
        }
    ]

    assert result["change_report"] == expected_report


def test_unverified_behavior_is_not_promoted_to_confirmed_finding():
    suite_report = {
        "results": [
            {
                "case_id": "TEST-002",
                "name": "Unverified response behavior",
                "status": "UNVERIFIED",
                "baseline_status": "unverified",
                "differences": [
                    {
                        "field": "status_code",
                        "expected": 200,
                        "actual": 500,
                    }
                ],
            }
        ]
    }

    expected_report = {
        "has_changes": False,
        "total_change_count": 0,
        "changes": [],
    }

    with (
        patch(
            "change_workflow.run_behavior_suite",
            return_value=suite_report,
        ),
        patch(
            "change_workflow.run_controlled_behavior_checks",
            return_value={
                "pagination_reports": [],
                "rate_limit_reports": [],
            },
        ),
        patch(
            "change_workflow.build_unified_change_report",
            return_value=expected_report,
        ) as mocked_report,
    ):
        change_workflow.run_change_workflow(
            baseline={"temperature": 30},
            current={"temperature": 30},
            run_behavior_tests=True,
        )

    passed_behavior_report = mocked_report.call_args.kwargs[
        "behavior_report"
    ]

    assert passed_behavior_report["changes"] == []
    assert passed_behavior_report["suite_evidence"] == suite_report
