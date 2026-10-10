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

    with (
        patch(
            "change_workflow.run_behavior_suite",
            return_value=suite_report,
        ) as mocked_suite,
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
    mocked_report.assert_called_once()

    behavior_report = mocked_report.call_args.kwargs["behavior_report"]

    assert behavior_report["suite_evidence"] == suite_report
    assert len(behavior_report["changes"]) == 1
    assert behavior_report["changes"][0]["kind"] == "behavior_case_changed"
    assert behavior_report["changes"][0]["case_id"] == "TEST-001"

    assert result["change_report"] == expected_report
    assert result["repair_workflow"]["status"] == "no_changes_detected"


def test_real_report_builder_includes_verified_behavior_finding():
    from change_report import build_unified_change_report

    report = build_unified_change_report(
        schema_report={
            "has_changes": False,
            "total_change_count": 0,
            "changes": [],
        },
        behavior_report={
            "changes": [
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
        },
        text_diff=[],
        pagination_reports=[],
        rate_limit_reports=[],
    )

    assert report["has_changes"] is True
    assert report["total_change_count"] >= 1
    assert any(
        change.get("kind") == "behavior_case_changed"
        for change in report["changes"]
    )


def test_unverified_behavior_is_not_promoted_to_finding():
    from change_report import build_unified_change_report

    report = build_unified_change_report(
        schema_report={
            "has_changes": False,
            "total_change_count": 0,
            "changes": [],
        },
        behavior_report={
            "changes": [],
            "suite_evidence": {
                "results": [
                    {
                        "case_id": "TEST-UNVERIFIED",
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
            },
        },
        text_diff=[],
        pagination_reports=[],
        rate_limit_reports=[],
    )

    assert report["has_changes"] is False
    assert report["total_change_count"] == 0
    assert report["changes"] == []