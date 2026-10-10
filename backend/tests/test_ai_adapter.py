
import pytest
from pydantic import ValidationError

from app.ai_adapter import AIAdapter
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
