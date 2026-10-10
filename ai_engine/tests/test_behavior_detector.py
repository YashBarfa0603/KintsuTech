from behavior_detector import detect_behavior_changes


def test_detects_api_status_change():
    result = detect_behavior_changes(
        {"status": "ok"},
        {"status": "error"},
    )

    assert result["has_behavior_changes"] is True
    assert result["behavior_change_count"] == 1
    assert result["changes"][0]["path"] == "status"


def test_detects_http_status_code_change():
    result = detect_behavior_changes(
        {"status": "ok"},
        {"status": "error"},
        baseline_status_code=200,
        current_status_code=500,
    )

    assert result["behavior_change_count"] == 2
    assert any(
        change["kind"] == "http_status_changed"
        for change in result["changes"]
    )


def test_detects_success_flag_change():
    result = detect_behavior_changes(
        {"success": True},
        {"success": False},
    )

    assert result["has_behavior_changes"] is True


def test_detects_error_indicator_added():
    result = detect_behavior_changes(
        {"status": "ok"},
        {"status": "ok", "error": "Service unavailable"},
    )

    assert result["has_behavior_changes"] is True
    assert any(
        change["kind"] == "behavior_indicator_added"
        for change in result["changes"]
    )


def test_ignores_normal_data_value_changes():
    result = detect_behavior_changes(
        {"temperature": 28, "humidity": 60},
        {"temperature": 29, "humidity": 61},
    )

    assert result["has_behavior_changes"] is False
    assert result["behavior_change_count"] == 0


def test_unchanged_response_has_no_behavior_changes():
    result = detect_behavior_changes(
        {"status": "ok", "success": True},
        {"status": "ok", "success": True},
        baseline_status_code=200,
        current_status_code=200,
    )

    assert result["has_behavior_changes"] is False
