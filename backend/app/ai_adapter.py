
from typing import Any, Protocol

from app.ai_schemas import AIAnalysisResult


class AIEngine(Protocol):
    """Interface the AI engine must implement."""

    def analyze_changes(
        self,
        *,
        service: str,
        baseline: dict[str, Any],
        current: dict[str, Any],
        detected_changes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Return a structured AI analysis result."""
        ...


class AIAdapter:
    """Backend-owned adapter for an injected AI engine."""

    def __init__(self, engine: AIEngine) -> None:
        self._engine = engine

    def analyze(
        self,
        *,
        service: str,
        baseline: dict[str, Any],
        current: dict[str, Any],
        detected_changes: list[dict[str, Any]],
    ) -> AIAnalysisResult:
        raw_result = self._engine.analyze_changes(
            service=service,
            baseline=baseline,
            current=current,
            detected_changes=detected_changes,
        )

        if not isinstance(raw_result, dict):
            raise ValueError("AI engine must return a dictionary")

        return AIAnalysisResult.model_validate(raw_result)
