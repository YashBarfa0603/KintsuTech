
from app.change_detector import detect_changes


def test_identical_responses_have_no_changes():
    baseline = {"temperature": 25, "city": "Indore"}

    result = detect_changes(baseline, baseline.copy())

    assert result["has_changes"] is False
    assert result["breaking_change_count"] == 0


def test_added_field_is_detected():
    baseline = {"temperature": 25}
    current = {"temperature": 25, "humidity": 60}

    result = detect_changes(baseline, current)

    assert result["has_changes"] is True
    assert any(
        change["kind"] == "field_added"
        and change["path"] == "humidity"
        for change in result["changes"]
    )
    assert result["breaking_change_count"] == 0


def test_removed_field_is_potentially_breaking():
    baseline = {"temperature": 25, "city": "Indore"}
    current = {"city": "Indore"}

    result = detect_changes(baseline, current)

    assert result["breaking_change_count"] == 1
    assert result["changes"][0]["kind"] == "field_removed"


def test_type_change_is_detected():
    baseline = {"price": 100}
    current = {"price": "100"}

    result = detect_changes(baseline, current)

    assert result["breaking_change_count"] == 1
    assert result["changes"][0]["kind"] == "type_changed"
    assert result["changes"][0]["old_type"] == "integer"
    assert result["changes"][0]["new_type"] == "string"


def test_nested_field_removal_is_detected():
    baseline = {
        "location": {
            "city": "Indore",
            "country": "India",
        }
    }
    current = {
        "location": {
            "country": "India",
        }
    }

    result = detect_changes(baseline, current)

    assert any(
        change["kind"] == "field_removed"
        and change["path"] == "location.city"
        for change in result["changes"]
    )


def test_boolean_is_not_treated_as_integer():
    baseline = {"available": 1}
    current = {"available": True}

    result = detect_changes(baseline, current)

    assert result["changes"][0]["kind"] == "type_changed"
    assert result["changes"][0]["old_type"] == "integer"
    assert result["changes"][0]["new_type"] == "boolean"
