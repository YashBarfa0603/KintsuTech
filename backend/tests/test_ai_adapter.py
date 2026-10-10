from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.ai_adapter import AIAdapter, analyze_changes
from app.ai_schemas import AIAnalysisResult


class FakeAIEngine:
    def analyze_changes(self, **kwargs):
        return {
            "summary": "Temperature field changed type.",
            "risk_level": "high",
            "recommendations": ["Review API consumers."],
        }


def test_adapter_returns_validated_result():
    adapter = AIAdapter(FakeAIEngine())

    result = adapter.analyze(
        service="weather",
        baseline={"temperature": 30},
        current={"temperature": "30"},
        detected_changes=[
            {"kind": "type_changed", "path": "temperature"}
        ],
    )

    assert isinstance(result, AIAnalysisResult)
    assert result.risk_level == "high"


def test_adapter_rejects_non_dictionary_result():
    class InvalidAIEngine:
        def analyze_changes(self, **kwargs):
            return "not a dictionary"

    adapter = AIAdapter(InvalidAIEngine())

    with pytest.raises(ValueError, match="must return a dictionary"):
        adapter.analyze(
            service="weather",
            baseline={},
            current={},
            detected_changes=[],
        )


def test_adapter_rejects_malformed_ai_result():
    class MalformedAIEngine:
        def analyze_changes(self, **kwargs):
            return {
                "summary": "Potential change.",
                "risk_level": "critical",
            }

    adapter = AIAdapter(MalformedAIEngine())

    with pytest.raises(ValidationError):
        adapter.analyze(
            service="weather",
            baseline={},
            current={},
            detected_changes=[],
        )


def test_adapter_maps_workflow_to_backend_contract():
    workflow_result = {
        "change_report": {
            "has_changes": True,
            "changes": [
                {
                    "source": "structural",
                    "kind": "field_removed",
                    "path": "temperature",
                    "old_type": "integer",
                }
            ],
        },
        "repair_workflow": {
            "proposal": {
                "change_summary": "Temperature field was removed.",
                "evidence": ["Field removal was detected."],
                "potential_impact": "Older clients may fail.",
                "proposed_repair": "Review a compatibility adapter.",
                "confidence": 0.9,
                "requires_validation": True,
            },
            "validation": {
                "status": "pending_review",
                "eligible_for_activation": False,
            },
        },
    }

    with patch(
        "app.ai_adapter.run_change_workflow",
        return_value=workflow_result,
    ):
        result = analyze_changes(
            service="weather",
            baseline={"temperature": 30},
            current={"temp_c": 30},
            detected_changes={
                "changes": [
                    {
                        "kind": "field_removed",
                        "path": "temperature",
                        "old_type": "integer",
                    }
                ]
            },
        )

    assert set(result) == {
        "summary",
        "risk_level",
        "recommendations",
        "repair_proposal",
    }
    assert result["risk_level"] == "high"
    assert result["recommendations"]
    assert result["repair_proposal"]["validation_status"] == (
        "pending_review"
    )
    assert result["repair_proposal"]["eligible_for_activation"] is False


def test_adapter_returns_none_risk_when_no_changes():
    with patch(
        "app.ai_adapter.run_change_workflow",
        return_value={
            "change_report": {"has_changes": False, "changes": []},
            "repair_workflow": {
                "status": "no_changes_detected",
                "proposal": None,
                "validation": None,
            },
        },
    ):
        result = analyze_changes(
            service="weather",
            baseline={"temperature": 30},
            current={"temperature": 30},
            detected_changes=[],
        )

    assert result["risk_level"] == "none"
    assert result["recommendations"] == []
    assert "repair_proposal" not in result


def test_adapter_rejects_empty_service():
    with pytest.raises(ValueError, match="service"):
        analyze_changes(
            service="",
            baseline={},
            current={},
            detected_changes=[],
        )
