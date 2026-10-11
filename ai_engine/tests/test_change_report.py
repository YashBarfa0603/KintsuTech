from change_report import build_unified_change_report


def test_combines_all_three_change_sources():
    schema = {
        "has_changes": True,
        "change_count": 1,
        "breaking_change_count": 1,
        "changes": [
            {
                "kind": "field_removed",
                "path": "temperature",
            }
        ],
    }

    behavior = {
        "has_behavior_changes": True,
        "behavior_change_count": 1,
        "changes": [
            {
                "kind": "http_status_changed",
                "path": "$http_status",
                "old_value": 200,
                "new_value": 500,
            }
        ],
    }

    text_diff = [
        {"operation": "equal", "value": "GET /products"},
        {"operation": "delete", "value": "limit=20"},
        {"operation": "insert", "value": "limit=10"},
    ]

    report = build_unified_change_report(
        schema,
        behavior,
        text_diff,
    )

    assert report["has_changes"] is True
    assert report["total_change_count"] == 4
    assert report["breaking_change_count"] == 1

    assert report["summary"] == {
        "structural_changes": 1,
        "behavioral_changes": 1,
        "text_diff_changes": 2,
        "pagination_changes": 0,
        "rate_limit_changes": 0,
        "retry_timing_changes": 0,
    }


def test_unchanged_inputs_produce_no_changes():
    report = build_unified_change_report(
        {
            "has_changes": False,
            "change_count": 0,
            "breaking_change_count": 0,
            "changes": [],
        },
        {
            "has_behavior_changes": False,
            "behavior_change_count": 0,
            "changes": [],
        },
        [
            {"operation": "equal", "value": "GET /products"},
        ],
    )

    assert report["has_changes"] is False
    assert report["total_change_count"] == 0
    assert report["changes"] == []


def test_preserves_original_evidence():
    schema = {
        "breaking_change_count": 0,
        "changes": [],
    }

    behavior = {
        "changes": [
            {"kind": "behavior_value_changed", "path": "success"}
        ],
    }

    text_diff = [
        {"operation": "insert", "value": "success=false"},
    ]

    report = build_unified_change_report(
        schema,
        behavior,
        text_diff,
    )

    assert report["evidence"]["schema_report"] == schema
    assert report["evidence"]["behavior_report"] == behavior
    assert report["evidence"]["text_diff"] == text_diff


def test_text_deletion_is_not_automatically_breaking():
    report = build_unified_change_report(
        {"breaking_change_count": 0, "changes": []},
        {"changes": []},
        [{"operation": "delete", "value": "old setting"}],
    )

    assert report["has_changes"] is True
    assert report["breaking_change_count"] == 0


def test_empty_reports_are_handled():
    report = build_unified_change_report({}, {}, [])

    assert report["has_changes"] is False
    assert report["total_change_count"] == 0
    assert report["breaking_change_count"] == 0


def test_unified_report_includes_pagination_and_rate_limit_changes():
    report = build_unified_change_report(
        schema_report={
            "changes": [],
            "breaking_change_count": 0,
        },
        behavior_report={"changes": []},
        text_diff=[],
        pagination_reports=[
            {
                "check": "pagination",
                "status": "CHANGED",
                "differences": [
                    {"reason": "next_page_without_cursor"}
                ],
            }
        ],
        rate_limit_reports=[
            {
                "check": "rate_limit",
                "status": "CHANGED",
                "differences": [
                    {"reason": "retry_after_missing"}
                ],
            }
        ],
    )

    assert report["has_changes"] is True
    assert report["summary"]["pagination_changes"] == 1
    assert report["summary"]["rate_limit_changes"] == 1
    assert report["summary"]["retry_timing_changes"] == 0
    assert report["total_change_count"] == 2

    assert report["changes"][0]["source"] == "pagination"
    assert report["changes"][1]["source"] == "rate_limit"


def test_unified_report_includes_retry_timing_changes():
    retry_timing = {
        "case_id": "RETRY-001",
        "check": "retry_timing",
        "status": "CHANGED",
        "baseline_status": "verified",
        "differences": [
            {
                "reason": "retry_too_early",
                "required_delay_seconds": 1.0,
                "observed_delay_seconds": 0.2,
            }
        ],
    }

    report = build_unified_change_report(
        schema_report={
            "changes": [],
            "breaking_change_count": 0,
        },
        behavior_report={"changes": []},
        text_diff=[],
        retry_timing_reports=[retry_timing],
    )

    assert report["has_changes"] is True
    assert report["summary"]["retry_timing_changes"] == 1
    assert report["total_change_count"] == 1
    assert report["changes"][0]["source"] == "retry_timing"
    assert report["evidence"]["retry_timing_reports"] == [retry_timing]


def test_unverified_checks_are_preserved_but_not_confirmed():
    pagination = {
        "check": "pagination",
        "status": "UNVERIFIED",
        "differences": [
            {"reason": "next_page_without_cursor"}
        ],
    }

    report = build_unified_change_report(
        schema_report={
            "changes": [],
            "breaking_change_count": 0,
        },
        behavior_report={"changes": []},
        text_diff=[],
        pagination_reports=[pagination],
    )

    assert report["has_changes"] is False
    assert report["total_change_count"] == 0
    assert report["evidence"]["pagination_reports"] == [pagination]


def test_unverified_retry_timing_is_preserved_but_not_confirmed():
    retry_timing = {
        "case_id": "RETRY-001",
        "check": "retry_timing",
        "status": "UNVERIFIED",
        "baseline_status": "unverified",
        "differences": [
            {"reason": "retry_too_early"}
        ],
    }

    report = build_unified_change_report(
        schema_report={
            "changes": [],
            "breaking_change_count": 0,
        },
        behavior_report={"changes": []},
        text_diff=[],
        retry_timing_reports=[retry_timing],
    )

    assert report["has_changes"] is False
    assert report["total_change_count"] == 0
    assert report["summary"]["retry_timing_changes"] == 0
    assert report["evidence"]["retry_timing_reports"] == [retry_timing]
