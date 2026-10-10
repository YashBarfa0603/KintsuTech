
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AIAnalysisResult(BaseModel):
    """Validated result returned by the AI engine."""

    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=2000)
    risk_level: Literal["none", "low", "medium", "high"]
    recommendations: list[str] = Field(default_factory=list)
    repair_proposal: dict[str, Any] | None = None
