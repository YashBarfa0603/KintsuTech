
from app.change_analyzer import analyze_changes


def test_added_field_is_low_risk():
    result = analyze_changes({
        "changes": [{
            "kind": "field_added",
            "path": "humidity",
            "new_type": "integer",
        }]
    })

    assert result["overall_risk"] == "low"
    assert result["severity_counts"]["low"] == 1
    assert result["changes"][0]["recommendation"]


def test_removed_field_is_high_risk():
    result = analyze_changes({
        "changes": [{
            "kind": "field_removed",
            "path": "temperature",
            "old_type": "integer",
        }]
    })

    assert result["overall_risk"] == "high"
    assert result["severity_counts"]["high"] == 1


def test_type_change_is_high_risk():
    result = analyze_changes({
        "changes": [{
            "kind": "type_changed",
            "path": "temperature",
            "old_type": "integer",
            "new_type": "string",
        }]
    })

    assert result["overall_risk"] == "high"
    assert "integer" in result["changes"][0]["explanation"]
    assert "string" in result["changes"][0]["explanation"]


def test_no_changes_has_no_risk():
    result = analyze_changes({"changes": []})

    assert result["has_changes"] is False
    assert result["overall_risk"] == "none"
    assert result["change_count"] == 0


def test_high_risk_changes_are_listed_first():
    result = analyze_changes({
        "changes": [
            {"kind": "field_added", "path": "humidity"},
            {"kind": "field_removed", "path": "temperature"},
        ]
    })

    assert result["changes"][0]["severity"] == "high"
    assert result["changes"][1]["severity"] == "low"


def test_unknown_change_kind_is_medium_risk():
    result = analyze_changes({
        "changes": [{"kind": "unknown_change", "path": "data"}]
    })

    assert result["overall_risk"] == "medium"
    assert result["severity_counts"]["medium"] == 1
